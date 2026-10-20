#!/usr/bin/env python3
"""Serial matched plain/disabled/sampled runs for the seven original losses."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
POINTS = frozenset({('c08', 3), ('c08', 4), ('c08', 5), ('rcuht', 2),
                    ('pipebytes', 3), ('pipebytes', 5), ('pipecap', 5)})
MODES = ('plain', 'disabled', 'sampled')


def order(original):
    """Keep original arm rotation; rotate three diagnostic modes by repeat."""
    selected = [row for row in original if tuple(row[:2]) in POINTS]
    groups = {}
    for group, count, repeat, arm in selected:
        groups.setdefault((group, count, repeat), []).append(arm)
    return [(g, n, r, arm, mode)
            for (g, n, r), arms in groups.items()
            for mode in MODES[r % 3:]+MODES[:r % 3]
            for arm in arms]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    temporary = path.with_name('.'+path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    temporary.replace(path)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(value, message):
    if not value:
        raise ValueError(message)


def run(args):
    inputs_path, out = args.inputs.resolve(strict=True), args.output.resolve()
    base = inputs_path.parent
    require(not out.exists() and not out.is_relative_to(ROOT) and
            not out.is_relative_to(base) and not base.is_relative_to(out),
            'new output must be independent of source and inputs')
    tools = base/'tools'
    require(sha(Path(__file__)) == sha(tools/'latency_run.py') ==
            sha(ROOT/'bench/mutex_api_compare/latency_run.py'), 'latency driver changed')
    preparer = load(tools/'latency_inputs.py', 'latency_inputs')
    scheduler = load(tools/'scheduler.py', 'latency_scheduler')
    # The retained scheduler normally derives ROOT from its file location.
    # Its origin guard must still reject today's checkout after relocation.
    scheduler.ROOT = ROOT
    latency = load(tools/'latency.py', 'operation_latency')
    archive = load(tools/'archive_run.py', 'latency_archive')
    inputs, originals, harness = preparer.validate(scheduler, inputs_path, args.inputs_sha256)
    original = preparer.ORIGINAL
    require(not out.is_relative_to(original) and not original.is_relative_to(out),
            'output overlaps original inputs')
    syn, syn_session, bench_session, api = scheduler.runners(original/'harness', harness)
    idle = lambda: archive.idle(out.parent, syn.idle)
    idle()
    for filename, digest in scheduler.REPLAY_ENVIRONMENT_SHA256.items():
        require(sha(original/'matrix'/filename) == digest,
                'original environment evidence changed: '+filename)
    host = read(args.host_state)
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(host['captured_utc'])).total_seconds()
    require(0 <= age <= 300 and host['pins_verified'] and host['snapshot_listed'] and
            host['recovery_snapshot'] == os.environ['KDLOCK_SNAPSHOT_TAG'],
            'fresh verified host placement and recovery snapshot required')
    old_host = read(original/'matrix/host-state.json')
    original_tasks = sorted(old_host['qemu'][0]['tasks'], key=lambda t: t['tid'])
    tasks = sorted(host['qemu'][0]['tasks'], key=lambda t: t['tid'])
    require(len(tasks) == 67 and tasks == original_tasks, 'strict original QEMU thread set differs')
    packages = {name: importlib.metadata.version(name)
                for name in ('miasm', 'future', 'pyparsing', 'pyelftools')}
    environment = dict(captured_utc=datetime.now(timezone.utc).isoformat(),
        cmdline=Path('/proc/cmdline').read_text().strip(),
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
        packages=packages, python=sys.executable,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
        collector_topology=syn.collector_topology(63), argv=sys.argv)
    require({'nokaslr', 'nopvspin'} <= set(environment['cmdline'].split()) and
            '(voluntary)' in environment['preemption'] and
            Path('/sys/devices/system/cpu/online').read_text().strip() == '0-63' and
            packages == dict(miasm='0.1.5', future='1.0.0', pyparsing='2.4.7', pyelftools='0.27'),
            'original boot or dependency policy differs')
    topology = syn.runtime.capture_topology(list(range(60)))
    probe = [dict(cpus=list(range(60)))]
    syn.runtime.annotate_topology(probe, topology)
    comparison = scheduler.same_environment(old_host, host, read(original/'matrix/environment.json'),
        environment, read(original/'matrix/topology.json'), topology)
    plan = order(scheduler.execution_order())
    require(len(plan) == len(set(plan)) == 252, 'expected fixed seven-point, three-mode plan')
    out.mkdir(parents=True)
    for name, value in [('environment.json', environment), ('topology.json', topology),
                        ('environment-comparison.json', comparison), ('host-before.json', host),
                        ('execution-order.json', plan)]:
        save(out/name, value)
    shutil.copyfile(inputs_path, out/'inputs.json')
    shutil.copyfile(Path(__file__), out/'latency_run.py')
    syn.command([sys.executable, original/'harness/bench/spin_cacheline/kernel_identity.py',
        '--kernel-source', '/root/linux-6.1.159-kdclobber2', '--kernel-baseline',
        '/root/kdlock-kernel-baselines/mutex-clobber2-20260919'], out/'kernel-identity.json', timeout=120)
    state = dict(state='RUNNING', complete=False, strict_passed=False, source_commit=args.source_commit,
        measured_collection='d21a1e3; original OUTER retains 752fec1', inputs_sha256=args.inputs_sha256,
        script_sha256=sha(Path(__file__)), planned=252, completed=0, sessions=[],
        scope='Operation latency and diagnostic overhead, with unchanged original protocol checks')
    save(out/'status.json', state)
    old_syn, old_api = syn.BackendSession, api.SyscallSession

    class LatencySynthetic(old_syn):
        def run(self, argv, log, **kwargs):
            if (self.record['latency_mode'] != 'plain' and str(argv[0]) == 'insmod' and
                    Path(argv[1]) == self.workload_module):
                argv = [*argv, 'latency_sample='+str(int(self.record['latency_mode'] == 'sampled'))]
            return super().run(argv, log, **kwargs)

        def phase(self, label, *positional, **keywords):
            measured = super().phase(label, *positional, **keywords)
            if label == 'measure' and self.record['latency_mode'] != 'plain':
                result = latency.read_synthetic('/dev/mutex_cacheline', measured,
                                                self.record['latency_mode'] == 'sampled')
                save(self.path/'latency.json', result)
                self.record['operation_latency'] = result['summary']
                self.save()
            return measured

    class LatencyAPI(old_api):
        def prepare(self):
            previous = os.environ.get('KD_LATENCY_SAMPLE')
            try:
                if self.record['latency_mode'] != 'plain':
                    os.environ['KD_LATENCY_SAMPLE'] = str(int(self.record['latency_mode'] == 'sampled'))
                else:
                    os.environ.pop('KD_LATENCY_SAMPLE', None)
                return super().prepare()
            finally:
                if previous is None:
                    os.environ.pop('KD_LATENCY_SAMPLE', None)
                else:
                    os.environ['KD_LATENCY_SAMPLE'] = previous

        def tell(self, action, *positional, **keywords):
            measured = super().tell(action, *positional, **keywords)
            if action == 'measure' and self.record['latency_mode'] != 'plain':
                values = measured['operation_latency']
                require(values['version'] == 1 and
                        values['enabled'] == (self.record['latency_mode'] == 'sampled'),
                        'client latency mode differs')
                summary = latency.summarize(values['rows'], measured, values['enabled'],
                    'Userspace query block through checked return; includes syscall and complete lock/body/unlock')
                save(self.path/'latency.json', dict(rows=values['rows'], summary=summary))
                self.record['operation_latency'] = summary
                self.save()
            return measured

    syn.BackendSession, api.SyscallSession = LatencySynthetic, LatencyAPI
    records, views, templates = [], {}, {}
    for mode in MODES:
        for key in inputs['bundles']:
            item = originals[key] if mode == 'plain' else inputs['bundles'][key]
            bundle = Path(item['bundle'])
            view = out/'measurements'/mode/key
            view.mkdir(parents=True)
            for folder in ('source', 'build', 'binaries', 'variants'):
                if (bundle/folder).is_dir():
                    (view/folder).symlink_to(bundle/folder, target_is_directory=True)
            views[mode, key] = view
            templates[mode, key] = {r['arm']: r for r in read(bundle/'plan.json')}
    deadline = time.monotonic()+args.budget_seconds
    try:
        for index, (group, count, repeat, arm, mode) in enumerate(plan):
            idle()
            require(time.monotonic()+180 < deadline, 'diagnostic supervisor budget exhausted at drained boundary')
            key = ('baseline' if arm == 'baseline-kd' else 'current')+'/'+group
            item = originals[key] if mode == 'plain' else inputs['bundles'][key]
            scheduler.verify(harness)
            scheduler.verify_collector_modules(original/'harness', harness)
            scheduler.verify(item['files'])
            backend = 'kdlock' if arm.endswith('-kd') else arm
            spec = scheduler.specification(templates[mode, key][backend], group, count, repeat, arm,
                                           item, probe[0]['cpu_nodes'])
            spec.update(latency_mode=mode, diagnostic=mode != 'plain', score_eligible=False,
                        latency_inputs_sha256=args.inputs_sha256, sequence=index,
                        name=spec['name']+'-'+mode, kernel_identity=sha(out/'kernel-identity.json'),
                        topology_identity=sha(out/'topology.json'))
            view = views[mode, key]
            spec['evidence_path'] = str(view/spec['name'])
            save(out/'current.json', spec)
            print(f'START {index+1}/252 {spec["name"]}', flush=True)
            if group in ('c08', 'rcuht'):
                session = scheduler.synthetic_session(syn, syn_session, bench_session, view, spec)
            else:
                session = api.SyscallSession(view, spec)
                session.execute()
            require(session.record['drained'] and
                    session.record['execution_status'] in ('OK', 'NO_JIT'),
                    'session did not drain with an original supported result')
            if backend == 'kdlock':
                require(session.record['retired'] == dict(state=2, modules=0, writers=0, frames=0),
                        'KD source retirement differs')
            if mode != 'plain':
                require('operation_latency' in session.record, 'missing latency record')
            records.append(session.record)
            save(out/'records.json', records)
            state['completed'] = index+1
            state['sessions'].append(dict(name=spec['name'], path=str(session.path),
                status=session.record['execution_status'], drained=True))
            save(out/'status.json', state)
            print('FINISH '+json.dumps(state['sessions'][-1], sort_keys=True), flush=True)
        preparer.validate(scheduler, inputs_path, args.inputs_sha256)
        idle()
        state.update(state='COMPLETE', complete=True, final_idle=True,
                     strict_passed=all(r['execution_status'] == 'OK' for r in records))
    except BaseException as error:
        state.update(state='FAILED', error=repr(error))
        raise
    finally:
        syn.BackendSession, api.SyscallSession = old_syn, old_api
        state['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save(out/'status.json', state)
    return 0 if state['strict_passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--inputs-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--budget-seconds', type=int, default=7200)
    args = parser.parse_args()
    require(re.fullmatch(r'[0-9a-f]{40}', args.source_commit) and
            re.fullmatch(r'[0-9a-f]{64}', args.inputs_sha256) and
            300 <= args.budget_seconds <= 7200, 'explicit source, input hash and bounded budget required')
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            sys.executable == shutil.which('python3') ==
            '/root/kdlock-translation-venv-20261019/bin/python3' and
            not Path(__file__).resolve().is_relative_to(ROOT),
            'run a retained copy in the confirmed original recovery VM')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
