#!/usr/bin/env python3
"""VM-only fresh pipe comparison: one source, 8/60 workers, three repeats each.

No profiling or synthetic workload is run. Each invocation requires a new arm
directory; failures and interrupted inputs are retained without retry in place.
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
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-embedded-20261019')


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('embedded32', 'old256'), required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--base', type=Path, default=BASE)
    args = parser.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2' or os.geteuid() != 0:
        raise RuntimeError('run from the maintained checkout in the recovery VM')
    if not re.fullmatch(r'[0-9a-f]{7,40}', args.commit):
        raise ValueError('record a concrete committed source revision')
    if os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or not os.environ.get('KDLOCK_SNAPSHOT_TAG'):
        raise RuntimeError('confirm the real recovery snapshot before execution')
    sys.dont_write_bytecode = True
    idle = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']
    idle()
    out = args.base.resolve() / args.version
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError('require a new arm directory outside the source checkout')
    out.mkdir(parents=True)
    # Match the previous traffic round's plain pipe invocation. Helper-wave
    # options remain identical but the pipe runner never executes those waves.
    command = [sys.executable, 'bench/real_api/run.py', '--cpus', ','.join(map(str, range(60))),
               '--entries', '16', '--value-size', '64', '--warmup', '48000', '--warmup-ms', '1000',
               '--helper-waves', '4', '--helper-workers', '8', '--backends', 'kdlock',
               '--threads', '8', '60', '--duration-ms', '2000', '--collector-cpu', '63',
               '--repeats', '3', '--kinds', 'pipebytes', '--queries', 'query', '--output', str(out / 'pipe')]
    receipt = dict(version=args.version, source_commit=args.commit, argv=command, cwd=str(ROOT),
                   expected_sessions=6, timeout_seconds=900, started_unix=time.time())
    matrix = dict(version=args.version, source_commit=args.commit,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], plain_sessions=6, profile_sessions=0,
        full_suite=False, passed=False, final_idle=False, commands=[receipt],
        measurement=dict(duration_ms=2000, peak_window_ms=300, peak_settle_ms=300,
                         sample_ms=10, warmup_per_worker=48000, api_warmup_ms=1000),
        notes=['Separate fresh source blocks, not randomized pairs or prior-round pooled data.',
               'Retain any measured NO_JIT/PARTIAL_JIT outcome; returned-JIT acceptance is checked separately.',
               'No profiles are included in this pipe-only comparison.'])
    save(out / 'matrix.json', matrix)
    save(out / 'pipe-command.json', receipt)
    try:
        print('START', args.version, 'pipe', flush=True)
        with (out / 'pipe-command.log').open('w') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        receipt.update(exit_code=result.returncode, finished_unix=time.time())
        save(out / 'pipe-command.json', receipt)
        print('FINISH', args.version, 'pipe', result.returncode, flush=True)
        if result.returncode:
            matrix['error'] = 'pipe runner failed; preserve collection and establish drain separately'
            save(out / 'matrix.json', matrix)
            return result.returncode
        records = json.loads((out / 'pipe/records.json').read_text())
        if len(records) != 6 or {(row['threads'], row['repeat']) for row in records} != {
                (workers, repeat) for workers in (8, 60) for repeat in range(3)} or not all(
                row.get('execution_status') == 'OK' and row.get('drained') is True for row in records):
            raise RuntimeError('pipe session inventory/result/drain differs')
        idle()
        matrix.update(passed=True, final_idle=True,
            returned_jit_sessions=sum(row.get('jit_completions', 0) > 0 for row in records),
            no_jit_sessions=sum(not row.get('jit_bodies', 0) for row in records))
        save(out / 'matrix.json', matrix)
        return 0
    except BaseException as error:
        receipt.update(error=repr(error), finished_unix=time.time())
        if isinstance(error, subprocess.TimeoutExpired):
            receipt['error'] = 'TIMEOUT: drain not established; no automatic cleanup'
        matrix['error'] = receipt['error']
        save(out / 'pipe-command.json', receipt)
        save(out / 'matrix.json', matrix)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
