#!/usr/bin/env python3
"""Serial functional smoke for KD spin, public mutex, rwlock and rwsem; no scores."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
REFERENCE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix/host-state.json')
REFERENCE_SHA = '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
FAMILIES = ('spin', 'mutex', 'rwlock', 'rwsem')
SNAPSHOT = 'before-mutex-kdonly-20261017T140354Z'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def functional_host(original, host, now):
    """Permit recorded extra I/O workers only in this unscored functional mode."""
    age = (now - datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
    require(0 <= age <= 300 and host['pins_verified'] and host['snapshot_listed'],
            'fresh verified host placement and recovery snapshot required')
    for key in ('cpufreq', 'numa', 'recovery_snapshot'):
        require(host[key] == original[key], 'host configuration differs: ' + key)
    require(len(host['qemu']) == len(original['qemu']) == 1, 'same single QEMU required')
    old, new = original['qemu'][0], host['qemu'][0]
    require(all(old[k] == new[k] for k in ('pid', 'args')), 'QEMU identity/configuration differs')
    old_tasks = {t['tid']: t for t in old['tasks']}
    new_tasks = {t['tid']: t for t in new['tasks']}
    require(len(old_tasks) == len(old['tasks']) and len(new_tasks) == len(new['tasks']),
            'duplicate host task identity')
    require(all(new_tasks.get(tid) == row for tid, row in old_tasks.items()),
            'original QEMU task identity/placement changed')
    extra = [row for tid, row in new_tasks.items() if tid not in old_tasks]
    require(all(row['comm'] == 'worker' and row['affinity'] == [63] for row in extra),
            'unexpected additional host task or placement')

    def bindings(qemu):
        rows = []
        for line in qemu['numa_maps'].splitlines():
            fields = line.split()
            if len(fields) < 2 or not fields[1].startswith('bind:'):
                continue
            values = dict(f.split('=', 1) for f in fields[2:] if '=' in f)
            rows.append((fields[0], fields[1], int(values['kernelpagesize_kB'])))
        require(rows, 'actual host memory bindings missing')
        return rows

    require(bindings(old) == bindings(new), 'host memory binding changed')
    return dict(mode='FUNCTIONAL_ONLY', performance_accepted=False,
                timing_gate='NOT_APPLICABLE', original_threads=len(old_tasks),
                observed_threads=len(new_tasks), additional_workers=extra,
                memory_bindings=bindings(new))


def plan(out, families):
    common = ['--functional', '--backends', 'kdlock', '--repeats', '1',
              '--threads', '16', '--iterations', '100000', '--collector-cpu', '63',
              '--kernel-source', '/root/linux-6.1.159-kdclobber2',
              '--kernel-baseline', '/root/kdlock-kernel-baselines/mutex-clobber2-20260919']
    rows = []
    for family in families:
        if family in ('spin', 'mutex'):
            runner = 'bench/tclock_compare/' + ('run.py' if family == 'spin' else 'run_mutex.py')
            arguments = ['--cpus', '0-15', '--workload', 'list', '--list-nodes', '16']
            if family == 'mutex':
                arguments += ['--mutex-api', 'public']
        else:
            runner = 'bench/rwlock_compare/run.py'
            arguments = ['--cpus', *map(str, range(16)), '--lock-kind', family,
                         '--workloads', 'list', '--list-nodes', '16', '--write-percent', '20',
                         '--post-work-rounds', '4', '--delegate', 'on', '--require-jit']
        rows.append(dict(family=family, output=str(out / family),
                         argv=[sys.executable, str(ROOT / runner), *common, *arguments,
                               '--output', str(out / family)]))
    return rows


def session_result(folder, family):
    specs = load(folder / 'plan.json')
    require(len(specs) == 1 and specs[0]['functional'], 'one functional session required')
    path = folder / specs[0]['name'] / 'session.json'
    row = load(path)
    require(row['execution_status'] == 'OK' and row['drained'] and
            row['measurement']['complete'] and row['measurement']['data_ok'],
            'session correctness or drain failed')
    entries, completed = row['jit_bodies'], row['jit_completions']
    require(type(entries) is int and type(completed) is int and entries >= completed > 0,
            'returned JIT body required; local/partial execution is not delegated support')
    return dict(family=family, passed=True, drained=True, execution='RETURNED_JIT',
                jit_entries=entries, jit_completions=completed,
                operations=row['measurement']['completed'],
                receipt=str(path), receipt_sha256=sha(path), performance_accepted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-state', type=Path)
    parser.add_argument('--families', nargs='+', choices=FAMILIES, default=list(FAMILIES))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    require(len(args.families) == len(set(args.families)), 'duplicate family')
    out = args.output.resolve()
    tasks = plan(out, args.families)
    if args.dry_run:
        print(json.dumps(tasks, indent=2))
        return
    require(ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0 and
            os.uname().release == '6.1.159-kdclobber2', 'original recovery guest required')
    require(sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3' and
            shutil.which('python3') == sys.executable, 'pinned Python required')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG') == SNAPSHOT, 'confirmed recovery snapshot required')
    require(args.host_state and sha(REFERENCE) == REFERENCE_SHA, 'original host reference required')
    require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
    import bench_runtime as rt
    archive_idle = runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle']
    with open('/run/lock/kdlock-basic.lock', 'a') as slot:
        fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
        archive_idle(Path('/root'), rt.idle)
        topology = rt.capture_topology(list(range(64)))
        require(topology['online_cpus'] == list(range(64)) and
                topology['role_nodes'] == [0] * 32 + [1] * 32, 'original guest topology required')
        host = functional_host(load(REFERENCE), load(args.host_state), datetime.datetime.now(datetime.timezone.utc))
        out.mkdir(parents=True)
        shutil.copyfile(args.host_state, out / 'host-state.json')
        shutil.copyfile(REFERENCE, out / 'reference-host.json')
        save(out / 'plan.json', tasks)
        save(out / 'functional-admission.json', host)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        result = dict(state='RUNNING', passed=False, final_idle=False, mode='FUNCTIONAL_ONLY',
                      performance_accepted=False, timing_started=False, boot_id=boot,
                      topology=topology, results=[], commands=[])
        controls = [Path(__file__), Path(__file__).with_name('test_run.py')]
        hashes = {str(p): sha(p) for p in controls}
        save(out / 'control-sha256.json', hashes)
        for path in controls:
            shutil.copyfile(path, out / path.name)

        def execute(name, argv, limit):
            record = dict(name=name, argv=list(map(str, argv)), state='STARTING')
            result['commands'].append(record)
            save(out / 'result.json', result)
            with (out / (name + '.log')).open('wb') as log:
                child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                record.update(state='RUNNING', pid=child.pid)
                save(out / 'result.json', result)
                # A deadline reports uncertainty; it never kills a live worker.
                try:
                    code = child.wait(timeout=limit)
                except BaseException:
                    record['state'] = 'UNKNOWN_DRAIN'
                    raise
            record.update(state='EXITED', returncode=code)
            save(out / 'result.json', result)
            require(code == 0, name + ' failed; preserve its logs and receipts')
            archive_idle(Path('/root'), rt.idle)
            require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot,
                    'guest boot changed')
            require(all(sha(Path(p)) == h for p, h in hashes.items()), 'smoke controls changed')

        try:
            execute('dependencies', [sys.executable, '-m', 'pip', 'check'], 60)
            execute('basic', ['make', '-C', str(ROOT / 'tests/unit'), 'run', 'PY_TESTS='], 180)
            execute('runner-checks', [sys.executable, ROOT / 'bench/basic/test_run.py'], 120)
            for task in tasks:
                print('FUNCTIONAL', task['family'], flush=True)
                execute(task['family'], task['argv'], 1800)
                result['results'].append(session_result(Path(task['output']), task['family']))
                save(out / 'result.json', result)
            result.update(state='COMPLETE', passed=True, final_idle=True)
        except BaseException as error:
            result.update(state='FAILED', error=repr(error))
            raise
        finally:
            save(out / 'result.json', result)
        print(json.dumps(result['results'], indent=2))


if __name__ == '__main__':
    main()
