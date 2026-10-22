#!/usr/bin/env python3
"""Collect the requested nano matrix serially in its isolated 40-vCPU guest."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
OUT = Path('/root/kdlock-evidence/380G10/bench/nano-20261022T072222Z')
PYTHON = '/root/kdlock-evidence/clobber-20260918/venv/bin/python3'
WORKERS = [*range(1, 9), 12, 16, 20, 24, 28, 32, 36]
SNAPSHOT = 'before-nano-20261022T072222Z'


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def load(path):
    return json.loads(path.read_text())


def plan():
    common = ['--threads', *map(str, WORKERS), '--collector-cpu', '38',
              '--repeats', '3', '--duration-ms', '2000', '--peak-window-ms', '300',
              '--peak-settle-ms', '300', '--sample-ms', '10',
              '--kernel-source', '/root/linux-6.1.159-kdclobber2',
              '--kernel-baseline', '/root/kdlock-kernel-baselines/mutex-clobber2-20260919']
    jobs = []
    for family in ('spin', 'mutex', 'rwlock', 'rwsem'):
        backends = ['native', 'kdlock'] if family == 'rwsem' else ['native', 'tclock', 'kdlock']
        payloads = [('cacheline', ['--cachelines', '1', '8'], 2),
                    ('list16', ['--list-nodes', '16'], 1),
                    ('list128', ['--list-nodes', '128'], 1),
                    ('rcuht', [], 1)]
        for label, options, sizes in payloads:
            name = family + '-' + label
            workload = 'list' if label.startswith('list') else label
            if family in ('spin', 'mutex'):
                runner = ROOT / 'bench/tclock_compare' / ('run.py' if family == 'spin' else 'run_mutex.py')
                arguments = ['--cpus', '0-35', '--workload', workload,
                             '--keep-going-no-jit', *options]
                if family == 'mutex':
                    arguments += ['--mutex-api', 'public']
                mixes = 1
            else:
                runner = ROOT / 'bench/rwlock_compare/run.py'
                arguments = ['--cpus', *map(str, range(36)), '--lock-kind', family,
                             '--workloads', workload, '--write-percent', '1', '20',
                             '--post-work-rounds', '4', '--delegate', 'on', *options]
                mixes = 2
            jobs.append(dict(name=name, family=family, expected_sessions=sizes * mixes * len(backends) * 15 * 3,
                             argv=[PYTHON, str(runner), *common, '--backends', *backends,
                                   *arguments, '--output', str(OUT / 'matrix' / name)]))
    assert sum(job['expected_sessions'] for job in jobs) == 3600
    return jobs


def idle():
    for row in Path('/proc/modules').read_text().splitlines():
        name = row.split()[0]
        assert not name.startswith(('kdlock', 'kd_', 'tclock', 'tc_', 'spin_cacheline',
                                    'mutex_cacheline', 'rwlock_bench')), ('module remains', name)
    for task in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            comm = task.read_text().strip()
        except FileNotFoundError:
            continue
        assert comm not in ('sc_worker', 'rb_worker', 'kd_test', 'daemon'), ('task remains', str(task), comm)


def verify_inputs(manifest, boot):
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
    for name, digest in manifest.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, ('source changed', name)
    assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-39'


def audit_job(job, code):
    folder = OUT / 'matrix' / job['name']
    specs = load(folder / 'plan.json')
    assert len(specs) == job['expected_sessions']
    no_jit = []
    for spec in specs:
        record = load(folder / spec['name'] / 'session.json')
        measurement = record.get('measurement', {})
        assert record.get('drained') is True and not record.get('cleanup_error'), spec['name']
        assert measurement.get('complete') is True and measurement.get('data_ok') is True, spec['name']
        state = record['execution_status']
        assert state in ('OK', 'NO_JIT'), (spec['name'], state)
        if state == 'NO_JIT':
            assert record.get('jit_bodies') == 0, spec['name']
            no_jit.append(spec['name'])
    assert code == (1 if no_jit else 0), (job['name'], code, no_jit)
    return dict(collected=len(specs), drained=True, no_jit_failures=no_jit,
                all_execution_checks_passed=not no_jit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    jobs = plan()
    if args.dry_run:
        print(json.dumps(jobs, indent=2))
        return
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert sys.executable == PYTHON
    assert os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1'
    assert os.environ.get('KDLOCK_SNAPSHOT_TAG') == SNAPSHOT
    assert not (OUT / 'matrix-status.json').exists()
    assert (OUT / 'host-before-matrix.json').exists()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    manifest = load(OUT / 'source-sha256.json')
    (OUT / 'matrix').mkdir()
    (OUT / 'plans').mkdir()
    save(OUT / 'matrix-plan.json', jobs)
    result = dict(state='PREFLIGHT', started_utc=datetime.now(timezone.utc).isoformat(),
                  pid=os.getpid(), boot_id=boot, expected_sessions=3600,
                  missing_backend={'rwsem/tclock': 'No TCLock sleeping-rwsem implementation'}, jobs=[])
    with open('/run/lock/kdlock-nano-20261022.lock', 'a') as slot:
        fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
        idle()
        verify_inputs(manifest, boot)
        try:
            for job in jobs:
                preview = subprocess.run(job['argv'] + ['--dry-run'], capture_output=True,
                                         text=True, cwd=ROOT, timeout=60)
                assert preview.returncode == 0, preview.stderr
                rows = json.loads(preview.stdout)
                assert len(rows) == job['expected_sessions']
                save(OUT / 'plans' / (job['name'] + '.json'), rows)
            result['state'] = 'RUNNING'
            save(OUT / 'matrix-status.json', result)
            for job in jobs:
                assert not (OUT / 'STOP').exists(), 'STOP requested at drained job boundary'
                idle()
                verify_inputs(manifest, boot)
                row = dict(name=job['name'], state='STARTING', expected_sessions=job['expected_sessions'])
                result['jobs'].append(row)
                save(OUT / 'matrix-status.json', result)
                print('START', job['name'], job['expected_sessions'], flush=True)
                with (OUT / (job['name'] + '.console.log')).open('wb') as log:
                    child = subprocess.Popen(job['argv'], stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                    row.update(state='RUNNING', pid=child.pid)
                    save(OUT / 'matrix-status.json', result)
                    # A deadline preserves the child for inspection; it does not prove drain.
                    try:
                        code = child.wait(timeout=21600)
                    except BaseException:
                        row['state'] = 'UNKNOWN_DRAIN'
                        raise
                row.update(state='EXITED', returncode=code)
                save(OUT / 'matrix-status.json', result)
                row.update(audit_job(job, code))
                idle()
                verify_inputs(manifest, boot)
                row['state'] = 'COLLECTED'
                save(OUT / 'matrix-status.json', result)
                print('COLLECTED', job['name'], row['collected'], flush=True)
            result.update(state='COLLECTED', final_idle=True, collected_sessions=3600,
                          finished_utc=datetime.now(timezone.utc).isoformat())
            save(OUT / 'health.json', dict(idle=True, boot_id=boot, modules=Path('/proc/modules').read_text()))
            (OUT / 'dmesg-final.log').write_text(subprocess.check_output(['dmesg'], text=True))
        except BaseException as error:
            result.update(state='STOPPED', error=repr(error))
            raise
        finally:
            save(OUT / 'matrix-status.json', result)


if __name__ == '__main__':
    main()
