#!/usr/bin/env python3
"""Source-host owner of the explicitly authorized exploratory catalog run."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time

from collect import RAW, REPORT, ROOT, SSH, capture, collect, exploratory_check
from plan import commands, GUEST

BOOT = '8caa1264-4d93-4448-a6d8-6d8393d364ee'
HEALTH = '''
import json, os, runpy, shutil, sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,'bench/spin_cacheline')
import bench_runtime as rt
runpy.run_path('bench/archive_run.py')['idle'](Path(%r), rt.idle)
assert os.uname().release == '6.1.159-kdclobber2'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == %r
assert set(Path('/proc/cmdline').read_text().split()) >= {'nopvspin','nokaslr'}
assert '(voluntary)' in Path('/sys/kernel/debug/sched/preempt').read_text()
print(json.dumps(dict(idle=True,boot_id=%r,kernel=os.uname().release,
    modules=Path('/proc/modules').read_text(),taint=Path('/proc/sys/kernel/tainted').read_text().strip(),
    free_bytes=shutil.disk_usage('/root').free)))
''' % (GUEST, BOOT, BOOT)


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def health(name):
    cmd = 'cd /root/host_fs/kdlock && timeout 30 /root/kdlock-translation-venv-20261019/bin/python3 -'
    result = subprocess.run([*SSH, '-p', '2222', 'root@10.176.26.71', cmd],
                            input=HEALTH.encode(), capture_output=True, timeout=45)
    (RAW / (name + '-health.stdout')).write_bytes(result.stdout)
    (RAW / (name + '-health.stderr')).write_bytes(result.stderr)
    result.check_returncode()
    return json.loads(result.stdout)


def preserve(name):
    path = RAW / (name + '-evidence.tar.gz')
    command = f'timeout 180 tar -C {shlex.quote(GUEST)} -czf - {shlex.quote(name)}'
    with path.open('xb') as stream:
        result = subprocess.run([*SSH, '-p', '2222', 'root@10.176.26.71', command],
                                stdout=stream, stderr=subprocess.PIPE, timeout=200)
    (RAW / (name + '-archive.stderr')).write_bytes(result.stderr)
    result.check_returncode()
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        assert archive.extractfile(name + '/records.json').read() == (RAW / name / 'records.json').read_bytes()
    receipt = dict(archive=path.name, bytes=path.stat().st_size,
                   sha256=hashlib.sha256(path.read_bytes()).hexdigest(), members=len(members))
    save(RAW / (name + '-preservation.json'), receipt)


def index(status):
    rows = ['# Exploratory single-round catalog progress', '',
            'User-authorized continuation after the spin c01 67→74-task host failure. '
            'Strict timing qualification remains failed. One repetition per point; no variability estimate.', '',
            '[Original c01 result](spin-c01/README.md) · [Original plan](plan.json) · '
            '[Corrected API command plan](plan-v2.json)', '',
            '| Workload | Measured/planned | State | Table and chart |', '| --- | ---: | --- | --- |',
            '| spin-c01 | 63/63 | Correct and drained; strict host failure | [Results](spin-c01/README.md) |']
    for item in status:
        name = item['workload']
        rows.append(f"| {name} | {item.get('measured', 0)}/63 | {item['state']} | " +
                    (f'[Results]({name}/README.md)' if (REPORT / name / 'README.md').exists() else 'Pending') + ' |')
    (REPORT / 'progress.md').write_text('\n'.join(rows) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', nargs='+')
    args = parser.parse_args()
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/kdlock-catalog-matplotlib')
    baseline = json.loads((RAW / 'host-before.json').read_text())
    status_path = REPORT / 'progress.json'
    statuses = json.loads(status_path.read_text()) if status_path.exists() else []
    planned = [(name, argv) for name, argv in commands()
               if name != 'spin-c01' and (not args.only or name in args.only)]
    with (RAW / 'owner.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, argv in planned:
            if (RAW / name).exists():
                continue
            if (REPORT / 'STOP').exists():
                break
            item = dict(workload=name, state='PREFLIGHT', started=time.time(), argv=argv)
            statuses.append(item)
            save(status_path, statuses); index(statuses)
            try:
                pre = health(name + '-before')
                if pre['free_bytes'] < 2 * 1024**3:
                    raise RuntimeError('storage reserve below 2 GiB; no cleanup authorized')
                before = capture(name + '-before')
                problems = exploratory_check(baseline, before)
                if problems:
                    raise RuntimeError('; '.join(problems))
                item['state'] = 'RUNNING'
                save(status_path, statuses); index(statuses)
                environment = ['PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                               'LC_ALL=C', 'PYTHONDONTWRITEBYTECODE=1', 'KDLOCK_RECOVERY_CONFIRMED=1',
                               'KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z']
                remote = 'cd /root/host_fs/kdlock && ' + shlex.join(
                    ['env', *environment, 'timeout', '3600', 'python3', *argv])
                print('START ' + name, flush=True)
                with (RAW / (name + '.log')).open('x') as log:
                    process = subprocess.Popen([*SSH, '-p', '2222', 'root@10.176.26.71', remote],
                                               stdout=log, stderr=subprocess.STDOUT)
                    item['returncode'] = process.wait(timeout=3650)
                # A timeout or transport failure never authorizes another load.
                if item['returncode'] not in (0, 1):
                    raise RuntimeError('remote completion/drain not established: ' + str(item['returncode']))
                post = health(name + '-after')
                admitted = collect(name, exploratory=True)
                records = json.loads((RAW / name / 'records.json').read_text())
                item['measured'] = sum(r.get('execution_status') == 'OK' and r.get('drained') is True
                                       for r in records)
                item['state'] = 'COMPLETE_EXPLORATORY' if item['returncode'] == 0 else 'FAILED_DRAINED'
                item['finished'] = time.time()
                save(status_path, statuses); index(statuses)
                print('TABLE ' + str(REPORT / name / 'README.md'), flush=True)
                preserve(name)
                if not admitted:
                    raise RuntimeError('exploratory endpoint identity/placement failed')
                if item['returncode']:
                    failure = RAW / name / 'failure.json'
                    if not failure.exists() or json.loads(failure.read_text()).get('status') != 'NO_JIT':
                        raise RuntimeError('workload failed; review before any further measurements')
            except Exception as error:
                item.update(state='STOPPED', error=str(error), finished=time.time())
                save(status_path, statuses); index(statuses)
                print('STOP ' + name + ': ' + str(error), flush=True)
                return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
