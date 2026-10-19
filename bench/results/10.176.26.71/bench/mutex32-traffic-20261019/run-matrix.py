#!/usr/bin/env python3
"""Bounded VM-only matrix: 24 plain timings and two unscored pipe profiles.

Each invocation measures one frozen source version. Existing maintained runners
capture source, binary, publication, result and drain evidence for every group.
"""
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
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-traffic-20261019')


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    if (Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2'
            or os.geteuid() != 0):
        raise RuntimeError('run from the maintained checkout in the recovery VM')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', args.version):
        raise ValueError('version must be a single safe directory name')
    if (os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1'
            or not os.environ.get('KDLOCK_SNAPSHOT_TAG')):
        raise RuntimeError('confirm the actual recovery snapshot before running')
    idle = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']
    idle()
    out = BASE / args.version
    out.mkdir(parents=True)
    common = ['--backends', 'kdlock', '--threads', '8', '60',
              '--duration-ms', '2000', '--collector-cpu', '63']
    synthetic = [sys.executable, 'bench/tclock_compare/run_mutex.py', '--cpus', '0-59',
                 '--peak-window-ms', '300', '--peak-settle-ms', '300', '--sample-ms', '10',
                 '--iterations', '100000', '--numa', 'on', '--kd-batch-size', '1024',
                 '--kd-provider-ubsan', 'off', '--spin-prefetch', '2',
                 '--spin-entry-ratio-limit', '2', '--spin-delegate', 'on', '--scenario', 'plain']
    # real_api fixes 300/300/10 ms in make_plan; it exposes no peak CLI flags.
    api = [sys.executable, 'bench/real_api/run.py', '--cpus', ','.join(map(str, range(60))),
           '--entries', '16', '--value-size', '64', '--warmup', '48000', '--warmup-ms', '1000',
           '--helper-waves', '4', '--helper-workers', '8']
    commands = [
        ('profile', [sys.executable, '/tmp/kdlock-mutex-profile-traffic.py', '--source-root', str(ROOT), '--commit', args.commit], 2),
        ('synthetic', synthetic + common + ['--cachelines', '1', '8', '--repeats', '3', '--keep-going-no-jit'], 12),
        ('seek', api + common + ['--repeats', '3', '--kinds', 'seek', '--queries', 'set', '--require-jit'], 6),
        # Preserve a measured local outcome; do not force an admission category.
        ('pipe', api + common + ['--repeats', '3', '--kinds', 'pipebytes', '--queries', 'query'], 6),
    ]
    metadata = dict(version=args.version, source_commit=args.commit,
                    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
                    plain_sessions=24, profile_sessions=2, full_suite=False,
                    measurement=dict(duration_ms=2000, peak_window_ms=300, peak_settle_ms=300,
                                     sample_ms=10, warmup_per_worker=48000, api_warmup_ms=1000),
                    notes=['Source versions are separate sequential blocks, not randomized pairs.',
                           'Synthetic counters witness JIT entry; explicit completions are measured only by real_api.',
                           'Profiles are diagnostic and never enter timing scores; pipe NO_JIT remains a distinct execution class.'])
    write(out / 'matrix.json', dict(metadata, passed=False))
    receipts = []
    for name, command, count in commands:
        idle()
        command = command + ['--output', str(out / name)]
        receipt = dict(version=args.version, source_commit=args.commit, argv=command,
                       cwd=str(ROOT), started_unix=time.time(), expected_sessions=count,
                       timeout_seconds=900)
        receipts.append(receipt)
        path = out / (name + '-command.json')
        write(path, receipt)
        print('START', args.version, name, flush=True)
        try:
            with (out / (name + '-command.log')).open('w') as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        except subprocess.TimeoutExpired:
            receipt.update(error='TIMEOUT: drain not established', finished_unix=time.time())
            write(path, receipt)
            write(out / 'matrix.json', dict(metadata, passed=False, commands=receipts))
            raise
        receipt.update(exit_code=result.returncode, finished_unix=time.time())
        write(path, receipt)
        print('FINISH', args.version, name, result.returncode, flush=True)
        if result.returncode:
            write(out / 'matrix.json', dict(metadata, passed=False, commands=receipts))
            print((out / (name + '-command.log')).read_text()[-8000:], flush=True)
            return result.returncode
        records_path = out / name / ('pipe/records.json' if name == 'profile' else 'records.json')
        records = json.loads(records_path.read_text())
        if len(records) != count or not all(r.get('execution_status') == 'OK' and r.get('drained') is True for r in records):
            write(out / 'matrix.json', dict(metadata, passed=False, commands=receipts,
                                             error=f'{name}: session count, result or drain differs'))
            raise RuntimeError(f'{name}: session count, result or drain differs')
    idle()
    write(out / 'matrix.json', dict(metadata, passed=True, final_idle=True, commands=receipts))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
