#!/usr/bin/env python3
"""Serial correctness and fixed paired timing for the isolated unlock control.

Correctness uses joined warmup work and reports no throughput. Timing retains
the original collector and exact environment comparison, including 67 tasks.
Neither mode changes admission or the frozen original provider/workload.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
sys.dont_write_bytecode = True


def load(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('correctness', 'timing'), required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--inputs-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--host-state', type=Path, required=True)
    p.add_argument('--unit-checks', type=Path, required=True)
    p.add_argument('--task-check', type=Path, required=True)
    p.add_argument('--correctness', type=Path)
    p.add_argument('--source-commit', required=True)
    a = p.parse_args()
    control = load(ROOT/'bench/mutex_api_compare/unlock_control.py', 'unlock_control')
    require, save, read, sha = control.require, control.save, control.read, control.sha
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            Path('/proc/sys/kernel/random/boot_id').read_text().strip() == control.BOOT and
            sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3' and
            shutil.which('python3') == sys.executable, 'recorded recovery VM/Python required')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG') == 'before-mutex-kdonly-20261017T140354Z',
            'actual recovery snapshot confirmation required')
    require(not Path(__file__).resolve().is_relative_to(ROOT) and
            sha(Path(__file__)) == sha(ROOT/'bench/mutex_api_compare/unlock_run.py') and
            re.fullmatch('[0-9a-f]{40}', a.source_commit),
            'exact external runner copy required')
    out = a.output.resolve()
    require(not out.exists() and not out.is_relative_to(ROOT) and
            not out.is_relative_to(a.inputs.resolve().parent), 'new independent output required')
    scheduler, frozen, harness, syn, api = control.context(out)
    candidate = control.validate(scheduler, a.inputs, a.inputs_sha256)
    checks, task_check = read(a.unit_checks), read(a.task_check)
    require(checks['passed'] and checks['final_idle'] and checks['source_unchanged'] and
            task_check['passed'] and task_check['drained'] and task_check['acks'] == 4,
            'basic/affected tests and actual owner-ACK probe must pass first')
    if a.mode == 'timing':
        require(a.correctness is not None, 'correctness receipt required before timing')
        correctness = read(a.correctness)
        require(correctness['passed'] and correctness['mode'] == 'correctness' and
                correctness['inputs_sha256'] == a.inputs_sha256 and
                correctness['completed'] == 4 and correctness['final_idle'],
                'same derivative must pass all correctness sessions')
        expected_offset = correctness['records'][0]['actual_lock_cacheline_offset']
    transition_path = Path('/root/kdlock-evidence/10.176.26.71/bench/'
                           'mutex-recovery-followup-20261021/transition-1/result.json')
    require(sha(transition_path) ==
            '81280a1655854fead9e64c4ee752275a32eef3c3f30ce09d27b71a89621a1ca1',
            'recorded recovery transition changed')
    transition = read(transition_path)
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    require(modules == transition['modules'] and len(modules) == 73, 'runtime modules differ')
    host = read(a.host_state)
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(host['captured_utc'])).total_seconds()
    require(0 <= age <= 300 and host['pins_verified'] and host['snapshot_listed'] and
            host['recovery_snapshot'] == os.environ['KDLOCK_SNAPSHOT_TAG'],
            'fresh host placement/recovery receipt required')
    out.mkdir(parents=True)
    for name, source in (('runner.py', Path(__file__)), ('inputs.json', a.inputs),
                         ('unit-checks.json', a.unit_checks), ('task-check.json', a.task_check),
                         ('host-before.json', a.host_state), ('transition.json', transition_path),
                         ('scheduler.py', Path(scheduler.__file__)),
                         ('unlock_control.py', Path(control.__file__))):
        shutil.copyfile(source, out/name)
    syn.command([sys.executable, control.ORIGINAL/'harness/bench/spin_cacheline/kernel_identity.py',
        '--kernel-source', control.KERNEL, '--kernel-baseline',
        '/root/kdlock-kernel-baselines/mutex-clobber2-20260919'], out/'kernel-identity.json', timeout=120)
    topology = syn.runtime.capture_topology(list(range(60)))
    save(out/'topology.json', topology)
    environment = dict(boot_id=control.BOOT, cmdline=Path('/proc/cmdline').read_text().strip(),
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
        packages={n: importlib.metadata.version(n) for n in ('miasm', 'future', 'pyparsing', 'pyelftools')},
        python=sys.executable, snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
        collector_topology=syn.collector_topology(63))
    save(out/'environment.json', environment)
    old_env = read(control.ORIGINAL/'matrix/environment.json')
    require(all(environment[k] == v for k, v in old_env.items() if k in environment and k != 'boot_id')
            and topology == read(control.ORIGINAL/'matrix/topology.json'),
            'original guest configuration/topology differs')
    if a.mode == 'timing':
        followup = load(ROOT/'bench/mutex_api_compare/recovery_replay.py', 'unlock_transition')
        comparison = followup.compare_environment(scheduler.same_environment, transition,
            read(control.ORIGINAL/'matrix/host-state.json'), host, old_env, environment,
            read(control.ORIGINAL/'matrix/topology.json'), topology)
        save(out/'environment-comparison.json', comparison)
        shutil.copyfile(a.correctness, out/'correctness.json')
    bundles = {'outer': frozen['baseline/pipecap'], 'general': candidate['bundle']}
    views = {}
    for arm, item in bundles.items():
        view = out/arm
        view.mkdir()
        bundle = Path(item['bundle'])
        for name in ('source', 'build'):
            (view/name).symlink_to(bundle/name, target_is_directory=True)
        views[arm] = view
    template = next(row for row in read(control.ORIGINAL/'baseline/pipecap/plan.json')
                    if row['arm'] == 'kdlock')
    plan = ([(n, 0, arm) for n in (1, 16) for arm in ('outer', 'general')]
            if a.mode == 'correctness' else
            [(5, r, arm) for r in range(3)
             for arm in (('outer', 'general') if r % 2 == 0 else ('general', 'outer'))])
    save(out/'plan.json', plan)
    receipt = dict(passed=False, accepted=False, mode=a.mode, inputs_sha256=a.inputs_sha256,
        source_commit=a.source_commit, planned=len(plan), completed=0, final_idle=False,
        records=[], started_ns=time.time_ns(), unit_checks_sha256=sha(a.unit_checks),
        task_check_sha256=sha(a.task_check), scope='Separately named workload diagnostic; original provider.')
    save(out/'result.json', receipt)

    class MatchedSession(api.SyscallSession):
        def prepare(self):
            super().prepare()
            offset = self.record['lock_addr'] % 64
            self.record['actual_lock_cacheline_offset'] = offset
            self.save()
            require(a.mode != 'timing' or offset == expected_offset,
                    'loaded mutex placement differs from correctness/control')

    class CorrectnessSession(MatchedSession):
        def measure(self):
            s = self.record
            counts = Path('/sys/module/kdlock_km/parameters')
            before = {name: int((counts/name).read_text()) for name in
                      ('bench_jit_bodies', 'bench_jit_completions', 'address_guard_count')}
            calls = int((api.PARAM/'calls').read_text())
            s['published_before'] = self.publication()
            require(s['published_before']['source']['writers'] == 0, 'writer before correctness work')
            work = self.tell('warmup', label='correctness-work')
            s['correctness_work'] = work
            require(work['ok'] and len(work['workers']) == s['threads'] and
                work['collector_cpu'] == work['collector_observed_cpu'] == 63 and
                work['collector_error'] == 0 and
                work['completed'] == sum(w['completed'] for w in work['workers']) and
                all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and
                    w['completed'] >= s['warmup'] and
                    w['finished_ns'] >= work['started_ns']+s['warmup_ms']*1000000
                    for w in work['workers']),
                'joined correctness work failed')
            require(int((api.PARAM/'calls').read_text())-calls == work['completed'],
                    'correctness calls did not all reach protected body')
            s.update(api.jit_evidence(int((counts/'bench_jit_bodies').read_text())-before['bench_jit_bodies'],
                int((counts/'bench_jit_completions').read_text())-before['bench_jit_completions'],
                work['completed'], enabled=True))
            s['address_guard_exits'] = int((counts/'address_guard_count').read_text())-before['address_guard_count']
            s['published_after'] = self.publication()
            require(s['published_after']['source']['writers'] == 0 and
                s['published_before']['entry'] == s['published_after']['entry'] and
                s['published_before']['images'] == s['published_after']['images'], 'image changed during work')
            require(self.tell('check', label='check-after')['check'], 'post-work capacity result differs')
            self.faults()
            self.save()
            api.require(not s['require_jit'] or s['jit_completions'] > 0,
                        'required returned body absent in correctness work', 'NO_JIT')

    try:
        for n, repeat, arm in plan:
            syn.idle()
            scheduler.verify(harness)
            scheduler.verify_collector_modules(control.ORIGINAL/'harness', harness)
            scheduler.verify(bundles[arm]['files'])
            spec = dict(template, name=f'{a.mode}-pipecap-t{n:02d}-r{repeat}-{arm}',
                threads=n, cpus=list(range(n)), repeat=repeat, collector_cpu=63,
                cpu_nodes=[0]*n, diagnostic=True, score_eligible=False,
                comparison_arm='original-outer' if arm == 'outer' else 'outer-general-unlock',
                caller_shell='mutex_outer_cookie' if arm == 'outer' else 'mutex_outer_general_unlock',
                source_identity=bundles[arm]['source_identity'],
                require_jit=a.mode == 'correctness' and n == 16,
                kernel_identity=sha(out/'kernel-identity.json'), topology_identity=sha(out/'topology.json'))
            cls = CorrectnessSession if a.mode == 'correctness' else MatchedSession
            session = cls(views[arm], spec)
            print('START', spec['name'], flush=True)
            session.execute()
            require(session.record['drained'] and session.record['execution_status'] == 'OK',
                    'session failed or did not drain')
            session.record['actual_lock_cacheline_offset'] = session.record['lock_addr'] % 64
            session.save()
            receipt['records'].append(session.record)
            receipt['completed'] += 1
            save(out/'result.json', receipt)
            print('FINISH', spec['name'], 'returns', session.record['jit_completions'], flush=True)
        require(len({r['actual_lock_cacheline_offset'] for r in receipt['records']}) == 1,
                'loaded mutex cacheline placement differed between arms')
        syn.idle()
        for item in frozen.values():
            scheduler.verify(item['files'])
        scheduler.verify(harness)
        control.validate(scheduler, a.inputs, a.inputs_sha256)
        receipt.update(passed=True, final_idle=True)
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        receipt['finished_ns'] = time.time_ns()
        save(out/'result.json', receipt)


if __name__ == '__main__':
    main()
