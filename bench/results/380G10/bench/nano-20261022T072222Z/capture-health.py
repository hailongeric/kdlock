#!/usr/bin/env python3
"""Audit this completed matrix and capture idle health; execute only in its VM."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/380G10/bench/nano-20261022T072222Z')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
    import bench_runtime as runtime
    idle = runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle']
    idle(BASE, runtime.idle)
    status = read(BASE / 'matrix-status.json')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert status['state'] == 'COLLECTED' and status['final_idle']
    assert status['boot_id'] == boot == 'f84aa8f3-c211-4198-aafa-686cf93cb751'
    assert status['collected_sessions'] == 3600
    assert not Path('/proc/' + str(status['pid'])).exists(), 'controller still present'
    frozen = read(BASE / 'source-sha256.json')
    for name, expected in frozen.items():
        assert sha(ROOT / name) == expected, name
    sessions = logs = retirements = operations = 0
    faults, no_jit, classes = [], [], Counter()
    for job in read(BASE / 'matrix-plan.json'):
        folder = BASE / 'matrix' / job['name']
        plan = read(folder / 'plan.json')
        assert len(plan) == job['expected_sessions']
        for spec in plan:
            path = folder / spec['name']
            row = read(path / 'session.json')
            for key in ('name', 'arm', 'threads', 'repeat'):
                assert row[key] == spec[key], (path, key)
            assert row['drained'] and not row.get('cleanup_error'), path
            assert row['execution_status'] in ('OK', 'NO_JIT'), path
            measurement = row['measurement']
            assert measurement['complete'] and measurement['data_ok'], path
            assert row['collector_cpu'] == 38 and not row.get('collector_shared', False), path
            assert measurement['collector_cpu'] == measurement['collector_observed_cpu'] == 38, path
            assert not measurement['collector_error'], path
            assert row['cpus'] == list(range(row['threads'])), path
            workers = measurement['workers']
            assert len(workers) == row['threads'], path
            assert [worker['cpu'] for worker in workers] == row['cpus'], path
            assert sum(worker['completed'] for worker in workers) == measurement['completed'], path
            assert all(worker['completed'] > 0 and not worker['error']
                       and worker['observed_cpu'] == worker['cpu'] for worker in workers), path
            operations += measurement['completed']
            if row['arm'] == 'kdlock':
                assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0), path
                assert row['published_before'] == row['published_after'], path
                entries = row['jit_bodies']
                assert 0 <= entries <= measurement['completed'], path
                if 'jit_completions' in row:
                    returns = row['jit_completions']
                    assert 0 <= returns <= entries, path
                    klass = 'RETURNED_JIT' if returns else 'PARTIAL_JIT' if entries else 'NO_JIT'
                else:
                    klass = 'WITNESSED_JIT' if entries else 'NO_JIT'
                if row['execution_status'] == 'NO_JIT':
                    assert entries == 0, path
                    no_jit.append(str(path.relative_to(BASE)))
                retirements += 1
            else:
                klass = row['arm'].upper()
            classes[(job['family'], row['arm'], row['execution_status'], klass)] += 1
            for line in (path / 'kernel.log').read_text().splitlines():
                if runtime.FAULT.search(line):
                    faults.append(dict(session=str(path.relative_to(BASE)), line=line))
            sessions += 1
            logs += 1
    assert sessions == logs == 3600
    assert not faults, faults
    dmesg = subprocess.check_output(['dmesg'], text=True, timeout=15)
    retained_faults = [line for line in dmesg.splitlines() if runtime.FAULT.search(line)]
    assert not retained_faults, retained_faults
    (BASE / 'dmesg-postprocess.log').write_text(dmesg)
    idle(BASE, runtime.idle)
    result = dict(idle=True, boot_id=boot, kernel_release=os.uname().release,
                  captured_ns=time.time_ns(), sessions=sessions, drained=sessions,
                  kernel_logs=logs, exact_retirements=retirements, completed_operations=operations,
                  verified_frozen_source_files=len(frozen), no_jit_failures=no_jit,
                  per_session_kernel_faults=faults, new_faults_in_retained_dmesg=retained_faults,
                  execution_classes=[dict(lock=k[0], backend=k[1], status=k[2],
                                          execution_class=k[3], count=v)
                                     for k, v in sorted(classes.items())],
                  modules=Path('/proc/modules').read_text(),
                  script_sha256=sha(Path(__file__)))
    with (BASE / 'final-health.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'modules'}, indent=2))


if __name__ == '__main__':
    main()
