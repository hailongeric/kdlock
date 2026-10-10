#!/usr/bin/env python3
"""Resume a matrix stopped by a disappearing /proc task, preserving its attempt.

Run this saved helper outside the guest checkout so original frozen inputs remain
unchanged. The interrupted group is rerun in full, followed by untouched groups.
"""
import argparse
from datetime import datetime, timezone
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
PROC_TASK = re.compile(r'/proc/[0-9]+/task(?:/[0-9]+(?:/comm)?)?')


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def now():
    return datetime.now(timezone.utc).isoformat()


def verified_idle(check):
    """Require an entire original scan to succeed; retry only an exited task."""
    for attempt in range(3):
        try:
            return check()
        except FileNotFoundError as error:
            if error.errno != errno.ENOENT or not PROC_TASK.fullmatch(error.filename or '') or attempt == 2:
                raise
            print(f'IDLE RETRY: process exited while scanning {error.filename}', flush=True)
            time.sleep(0.05)


def runner_module(path):
    if path.name == 'run_mutex.py':
        path = path.with_name('run.py')
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('full_matrix_saved_runner', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-group')
    args = parser.parse_args()
    if (os.geteuid() != 0 or os.uname().release != '6.1.159-kdclobber2' or
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or
            not os.environ.get('KDLOCK_SNAPSHOT_TAG')):
        raise ValueError('run inside the verified recovery guest')
    root = args.output.resolve()
    if root.is_relative_to(ROOT):
        raise ValueError('evidence must remain outside the checkout')
    os.chdir(ROOT)
    plan = json.loads((root / 'matrix-plan.json').read_text())
    if args.run_group:
        group, = [g for g in plan if g['name'] == args.run_group]
        module = runner_module(ROOT / group['argv'][1])
        original_idle = module.idle
        module.idle = lambda: verified_idle(original_idle)
        sys.argv = group['argv'][1:]
        return module.main(lock_kind='mutex') if group['lock_kind'] == 'mutex' else module.main()
    status = json.loads((root / 'matrix-status.json').read_text())
    if status['state'] != 'FAILED' or status['snapshot_tag'] != os.environ['KDLOCK_SNAPSHOT_TAG']:
        raise ValueError('requires a failed matrix and its confirmed current snapshot')
    approved = json.loads((root / 'source-sha256-approved.json').read_text())
    for name, expected in approved.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('original approved source changed: ' + name)
    rwlock = runner_module(ROOT / 'bench/rwlock_compare/run.py')
    verified_idle(rwlock.idle)
    import bench_runtime
    dmesg = subprocess.run(['dmesg'], capture_output=True, text=True, check=True).stdout
    faults = [line for line in dmesg.splitlines() if bench_runtime.FAULT.search(line)]
    if faults:
        raise ValueError('guest kernel fault: ' + str(faults[:10]))
    failed = status['groups'][-1]
    folder = root / failed['name']
    failure = json.loads((folder / 'failure.json').read_text())
    match = re.fullmatch(r"\[Errno 2\] No such file or directory: '([^']+)'", failure['error'])
    if failure['status'] != 'FAILED' or not match or not PROC_TASK.fullmatch(match[1]):
        raise ValueError('only the verified disappearing-task failure may be resumed')
    records = json.loads((folder / 'records.json').read_text())
    executed = [r for r in records if r.get('execution_status') != 'NOT_RUN']
    if not executed or any(r.get('execution_status') != 'OK' or r.get('drained') is not True for r in executed):
        raise ValueError('interrupted attempt has failed or undrained sessions')
    if any('error' in g or g['executed_sessions'] != g['drained_sessions'] for g in status['groups'][:-1]):
        raise ValueError('earlier group is incomplete')
    start = len(status['groups']) - 1
    if [g['name'] for g in status['groups']] != [g['name'] for g in plan[:start + 1]]:
        raise ValueError('matrix group ordering differs')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    attempt = root / 'attempts' / (failed['name'] + '-' + stamp)
    attempt.parent.mkdir(exist_ok=True)
    folder.rename(attempt)
    (root / (failed['name'] + '.log')).rename(attempt / 'runner.log')
    write_json(attempt / 'matrix-status-at-stop.json', status)
    (attempt / 'driver.log').write_bytes(root.with_name(root.name + '.driver.log').read_bytes())
    receipt = dict(group=failed['name'], path=str(attempt.relative_to(root)),
                   reason=failure, executed_sessions=len(executed),
                   not_run_sessions=len(records)-len(executed), drained=True,
                   original_group_status=failed, resumed_utc=now(),
                   continuation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   policy='Preserve the interrupted attempt, rerun its entire group, then finish remaining groups.')
    status.setdefault('interrupted_attempts', []).append(receipt)
    write_json(attempt / 'continuation-receipt.json', receipt)
    status['groups'].pop()
    status['state'] = 'RUNNING'
    status.pop('finished_utc', None)
    write_json(root / 'matrix-status.json', status)
    for group in plan[start:]:
        if (root / 'STOP').exists():
            status['state'] = 'STOPPED'
            break
        verified_idle(rwlock.idle)
        print(f"START {group['name']}: {group['expected_sessions']} sessions", flush=True)
        entry = dict(name=group['name'], started_utc=now(),
                     wrapper_argv=[sys.executable, str(Path(__file__).resolve()),
                                   '--output', str(root), '--run-group', group['name']])
        status['groups'].append(entry)
        write_json(root / 'matrix-status.json', status)
        try:
            with (root / (group['name'] + '.log')).open('w') as stream:
                process = subprocess.run(entry['wrapper_argv'], stdout=stream,
                                         stderr=subprocess.STDOUT, timeout=7200)
            entry['exit_code'] = process.returncode
            verified_idle(rwlock.idle)
            rows = json.loads((root / group['name'] / 'records.json').read_text())
            entry.update(recorded_sessions=len(rows),
                         executed_sessions=sum(r.get('execution_status') != 'NOT_RUN' for r in rows),
                         drained_sessions=sum(r.get('drained') is True for r in rows),
                         status_counts={s:sum(r.get('execution_status') == s for r in rows)
                                        for s in sorted({r.get('execution_status', 'UNKNOWN') for r in rows})},
                         finished_utc=now())
            if any(entry[key] != group['expected_sessions'] for key in
                   ('recorded_sessions', 'executed_sessions', 'drained_sessions')):
                raise ValueError('incomplete or undrained group')
            if process.returncode:
                reason = json.loads((root / group['name'] / 'failure.json').read_text())
                if reason.get('status') != 'NO_JIT':
                    raise ValueError('runner failed outside a drained NO_JIT case')
            print(f"END {group['name']}: {entry['status_counts']}", flush=True)
            write_json(root / 'matrix-status.json', status)
        except Exception as error:
            entry['error'] = str(error)
            status['state'] = 'FAILED'
            write_json(root / 'matrix-status.json', status)
            raise
    else:
        verified_idle(rwlock.idle)
        status['state'] = 'COMPLETE'
    status['finished_utc'] = now()
    write_json(root / 'matrix-status.json', status)
    return 0 if status['state'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
