#!/usr/bin/env python3
"""Bounded VM-only fresh Native/TCLock/KD mutex comparison, 567 plain sessions."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-native-tclock-20261020')
WORKERS = (1, 2, 4, 8, 16, 32, 36, 48, 60)
BACKENDS = ('native', 'tclock', 'kdlock')
COLLECTIONS = ('c01', 'c08', 'rcuht', 'seek-set', 'seek-end', 'pipebytes', 'pipecap')


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def commands(python):
    common = ['--backends', *BACKENDS, '--threads', *map(str, WORKERS), '--repeats', '3',
              '--duration-ms', '2000', '--collector-cpu', '63']
    synthetic = [python, 'bench/tclock_compare/run_mutex.py', '--cpus', '0-59',
        '--peak-window-ms', '300', '--peak-settle-ms', '300', '--sample-ms', '10',
        '--iterations', '100000', '--numa', 'on', '--kd-batch-size', '1024',
        '--kd-provider-ubsan', 'off', '--spin-prefetch', '2', '--spin-entry-ratio-limit', '2',
        '--spin-delegate', 'on', '--scenario', 'plain', '--keep-going-no-jit', *common]
    api = [python, 'bench/real_api/run.py', '--cpus', ','.join(map(str, range(60))),
        '--entries', '16', '--value-size', '64', '--warmup', '48000', '--warmup-ms', '1000',
        '--helper-waves', '4', '--helper-workers', '8', *common]
    return [
        ('c01', [*synthetic, '--workload', 'cacheline', '--cachelines', '1']),
        ('c08', [*synthetic, '--workload', 'cacheline', '--cachelines', '8']),
        ('rcuht', [*synthetic, '--workload', 'rcuht']),
        ('seek-set', [*api, '--kinds', 'seek', '--queries', 'set']),
        ('seek-end', [*api, '--kinds', 'seek', '--queries', 'end']),
        ('pipebytes', [*api, '--kinds', 'pipebytes', '--queries', 'query']),
        ('pipecap', [*api, '--kinds', 'pipecap', '--queries', 'query']),
    ]


def retained_no_jit(row):
    m = row.get('measurement', {})
    return (row.get('arm') == 'kdlock' and row.get('execution_status') == 'NO_JIT'
        and row.get('jit_acceptance') == 'NO_JIT' and row.get('jit_bodies') == 0
        and row.get('drained') is True and not row.get('cleanup_error')
        and m.get('complete') is True and m.get('data_ok') is True)


def validate_records(folder, name, exit_code):
    records = json.loads((folder / 'records.json').read_text())
    expected = {(b, n, r) for b in BACKENDS for n in WORKERS for r in range(3)}
    if len(records) != 81 or {(r['arm'], r['threads'], r['repeat']) for r in records} != expected:
        raise RuntimeError(name + ': session inventory differs')
    synthetic = name in ('c01', 'c08', 'rcuht')
    rejected = []
    for row in records:
        if row.get('execution_status') == 'NO_JIT' and synthetic and retained_no_jit(row):
            rejected.append(row['name'])
        elif row.get('execution_status') != 'OK' or row.get('error'):
            raise RuntimeError(name + ': execution failed: ' + row['name'])
        if row.get('drained') is not True or row.get('cleanup_error'):
            raise RuntimeError(name + ': final drain not established')
        if any(row.get(k) for k in ('diagnostic', 'perf_record', 'pmu')):
            raise RuntimeError(name + ': ordinary cohort contains instrumentation')
        if synthetic:
            if row.get('workload') != ('rcuht' if name == 'rcuht' else 'cacheline'):
                raise RuntimeError(name + ': synthetic workload differs')
            if name != 'rcuht' and row.get('cachelines') != int(name[1:]):
                raise RuntimeError(name + ': cache-line count differs')
        else:
            kind, query = ('seek', name[5:]) if name.startswith('seek-') else (name, 'query')
            if tuple(row.get(k) for k in ('kind', 'query', 'entries', 'value_size')) != (kind, query, 16, 64):
                raise RuntimeError(name + ': API workload differs')
    if exit_code == 1 and rejected and synthetic:
        failure = json.loads((folder / 'failure.json').read_text())
        if failure.get('status') != 'NO_JIT' or failure.get('sessions') != rejected:
            raise RuntimeError(name + ': nonzero result was not solely the retained NO_JIT set')
    elif exit_code != 0 or rejected:
        raise RuntimeError(name + ': exit status and complete inventory differ')
    return dict(execution_inventory_complete=True, all_drained=True,
        non_jit_rejections=rejected, original_execution_status_counts=dict(Counter(r['execution_status'] for r in records)),
        jit_verdict_counts=dict(Counter(str(r.get('jit_acceptance') if synthetic else r.get('jit_status')) for r in records)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--base', type=Path, default=BASE)
    args = parser.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2' or os.geteuid() != 0:
        raise RuntimeError('run from the maintained checkout in the recovery VM')
    if not re.fullmatch(r'[0-9a-f]{7,40}', args.commit):
        raise ValueError('record a concrete committed source revision')
    if os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or not os.environ.get('KDLOCK_SNAPSHOT_TAG'):
        raise RuntimeError('confirm the actual recovery snapshot before execution')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    idle = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']
    idle()
    out = args.base.resolve() / 'current'
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError('require a new external current source directory')
    out.mkdir(parents=True)
    receipts = []
    started = time.monotonic()
    matrix = dict(schema=1, version='current', source_commit=args.commit,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], plain_sessions=567, profile_sessions=0,
        full_suite=False, passed=False, final_idle=False, commands=receipts,
        workers=list(WORKERS), backends=list(BACKENDS), repeats=3,
        collection_timeout_seconds=1800, total_timeout_seconds=9000,
        measurement=dict(duration_ms=2000, peak_window_ms=300, peak_settle_ms=300,
                         sample_ms=10, warmup_per_worker=48000, api_warmup_ms=1000),
        notes=['Fresh seven workload blocks from one frozen source; never pool with earlier runs.',
               'Synthetic JIT counters witness entry only; API probes count matching returned bodies.',
               'Collected drained NO_JIT rejections retain their original failure verdict and are not timing scores.',
               'Completion means complete drained inventory; it is not a claim that every session used JIT.',
               'No profiles, lock placement diagnostics or full worker grid.'])
    save(out / 'matrix.json', matrix)
    try:
        for name, command in commands(sys.executable):
            idle()
            remaining = 9000 - (time.monotonic() - started)
            if remaining < 1800:
                raise RuntimeError('total collection budget leaves less than one bounded workload; stopped idle')
            argv = [*command, '--output', str(out / name)]
            receipt = dict(source_commit=args.commit, collection=name, argv=argv, cwd=str(ROOT),
                expected_sessions=81, timeout_seconds=1800, started_unix=time.time())
            receipts.append(receipt)
            save(out / 'matrix.json', matrix)
            save(out / (name + '-command.json'), receipt)
            print('START current', name, flush=True)
            try:
                with (out / (name + '-command.log')).open('w') as log:
                    result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            except subprocess.TimeoutExpired:
                receipt.update(error='TIMEOUT: drain not established; no automatic cleanup', finished_unix=time.time())
                save(out / (name + '-command.json'), receipt)
                raise
            receipt.update(exit_code=result.returncode, finished_unix=time.time())
            save(out / (name + '-command.json'), receipt)
            receipt.update(validate_records(out / name, name, result.returncode))
            idle()
            receipt['idle_after'] = True
            save(out / (name + '-command.json'), receipt)
            save(out / 'matrix.json', matrix)
            print('FINISH current', name, result.returncode, 'drained NO_JIT rejections',
                  len(receipt['non_jit_rejections']), flush=True)
        idle()
        matrix.update(passed=True, final_idle=True,
                      non_jit_rejections=sum(len(r['non_jit_rejections']) for r in receipts),
                      elapsed_seconds=time.monotonic() - started)
        save(out / 'matrix.json', matrix)
        return 0
    except BaseException as error:
        matrix['error'] = repr(error)
        save(out / 'matrix.json', matrix)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
