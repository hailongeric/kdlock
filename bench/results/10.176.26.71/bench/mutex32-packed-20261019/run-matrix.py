#!/usr/bin/env python3
"""VM-only fresh pipe block: six plain timings followed by two unscored profiles."""
import argparse
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
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-packed-20261019')
ARMS = ('embedded32', 'candidate', 'old256')


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=ARMS, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--profile-driver', type=Path, default=BASE / 'mutex_profile.py')
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
    out, profile_driver = args.base.resolve() / args.version, args.profile_driver.resolve(strict=True)
    if out.exists() or out.is_relative_to(ROOT) or profile_driver.is_relative_to(out):
        raise ValueError('require a new external arm directory and an existing separate profile driver')
    out.mkdir(parents=True)
    pipe = [sys.executable, 'bench/real_api/run.py', '--cpus', ','.join(map(str, range(60))),
            '--entries', '16', '--value-size', '64', '--warmup', '48000', '--warmup-ms', '1000',
            '--helper-waves', '4', '--helper-workers', '8', '--backends', 'kdlock', '--threads', '8', '60',
            '--duration-ms', '2000', '--collector-cpu', '63', '--repeats', '3', '--kinds', 'pipebytes',
            '--queries', 'query', '--output', str(out / 'pipe')]
    profile = [sys.executable, str(profile_driver), '--source-root', str(ROOT), '--commit', args.commit,
               '--output', str(out / 'profile')]
    commands = [('pipe', pipe, 6, 'pipe/records.json'), ('profile', profile, 2, 'profile/pipe/records.json')]
    receipts = []
    matrix = dict(version=args.version, source_commit=args.commit,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        profile_driver_sha256=hashlib.sha256(profile_driver.read_bytes()).hexdigest(),
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], plain_sessions=6, profile_sessions=2,
        full_suite=False, passed=False, final_idle=False, commands=receipts,
        measurement=dict(duration_ms=2000, peak_window_ms=300, peak_settle_ms=300,
                         sample_ms=10, warmup_per_worker=48000, api_warmup_ms=1000),
        notes=['Fresh sequential source blocks; no pooling with earlier rounds.',
               'Six plain timings precede the two diagnostic profiles; profile throughput is unscored.',
               'Plain NO_JIT/PARTIAL_JIT outcomes remain explicit; profiles require actual returned JIT.',
               'Compare each profile JIT share with its own plain cohort before interpreting sampled costs.'])
    save(out / 'matrix.json', matrix)
    try:
        for name, argv, count, relative in commands:
            idle()
            if hashlib.sha256(profile_driver.read_bytes()).hexdigest() != matrix['profile_driver_sha256']:
                raise RuntimeError('profile driver changed during this source block')
            receipt = dict(version=args.version, source_commit=args.commit, argv=argv, cwd=str(ROOT),
                           expected_sessions=count, timeout_seconds=900, started_unix=time.time())
            receipts.append(receipt)
            save(out / 'matrix.json', matrix)
            save(out / (name + '-command.json'), receipt)
            print('START', args.version, name, flush=True)
            try:
                with (out / (name + '-command.log')).open('w') as log:
                    result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900)
            except subprocess.TimeoutExpired:
                receipt.update(error='TIMEOUT: drain not established; no automatic cleanup', finished_unix=time.time())
                save(out / (name + '-command.json'), receipt)
                raise
            receipt.update(exit_code=result.returncode, finished_unix=time.time())
            save(out / (name + '-command.json'), receipt)
            print('FINISH', args.version, name, result.returncode, flush=True)
            if result.returncode:
                raise RuntimeError(name + ' failed; preserve its evidence and establish drain separately')
            records = json.loads((out / relative).read_text())
            expected = {(workers, repeat) for workers in (8, 60) for repeat in range(3 if name == 'pipe' else 1)}
            if len(records) != count or {(row['threads'], row['repeat']) for row in records} != expected or not all(
                    row.get('execution_status') == 'OK' and row.get('drained') is True for row in records):
                raise RuntimeError(name + ': session inventory/result/drain differs')
            if name == 'pipe':
                matrix['returned_jit_plain_sessions'] = sum(row.get('jit_completions', 0) > 0 for row in records)
            save(out / 'matrix.json', matrix)
        idle()
        matrix.update(passed=True, final_idle=True)
        save(out / 'matrix.json', matrix)
        return 0
    except BaseException as error:
        matrix.update(error=repr(error))
        save(out / 'matrix.json', matrix)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
