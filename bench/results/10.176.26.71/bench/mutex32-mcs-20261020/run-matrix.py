#!/usr/bin/env python3
"""Bounded VM-only source block: c01/post64, SEEK_SET and pipe, 18 plain timings."""
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
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-mcs-20261020')
ARMS = ('baseline', 'candidate', 'old256')


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--base', type=Path, default=BASE)
    args = parser.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2' or os.geteuid() != 0:
        raise RuntimeError('run from the maintained checkout in the recovery VM')
    if not re.fullmatch(r'[0-9a-f]{7,40}', args.commit):
        raise ValueError('record a concrete committed source revision')
    if not re.fullmatch(r'[a-z][a-z0-9_-]*', args.version):
        raise ValueError('require one safe arm directory label')
    if os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or not os.environ.get('KDLOCK_SNAPSHOT_TAG'):
        raise RuntimeError('confirm the actual recovery snapshot before execution')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    idle = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']
    idle()
    out = args.base.resolve() / args.version
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError('require a new external source-arm directory')
    out.mkdir(parents=True)
    common = ['--backends', 'kdlock', '--threads', '8', '60', '--repeats', '3',
              '--duration-ms', '2000', '--collector-cpu', '63']
    synthetic = [sys.executable, 'bench/tclock_compare/run_mutex.py', '--cpus', '0-59',
                 '--cachelines', '1', '--peak-window-ms', '300', '--peak-settle-ms', '300',
                 '--sample-ms', '10', '--iterations', '100000', '--numa', 'on',
                 '--kd-batch-size', '1024', '--kd-provider-ubsan', 'off', '--spin-prefetch', '2',
                 '--spin-entry-ratio-limit', '2', '--spin-delegate', 'on', '--scenario', 'plain',
                 '--keep-going-no-jit', *common]
    # real_api fixes the same 300/300/10 ms peak/sample policy in its plan.
    api = [sys.executable, 'bench/real_api/run.py', '--cpus', ','.join(map(str, range(60))),
           '--entries', '16', '--value-size', '64', '--warmup', '48000', '--warmup-ms', '1000',
           '--helper-waves', '4', '--helper-workers', '8', *common]
    commands = [('synthetic', synthetic),
                ('seek', [*api, '--kinds', 'seek', '--queries', 'set']),
                ('pipe', [*api, '--kinds', 'pipebytes', '--queries', 'query'])]
    receipts = []
    matrix = dict(version=args.version, source_commit=args.commit,
        comparison_arm=args.version in ARMS,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], plain_sessions=18, profile_sessions=0,
        full_suite=False, passed=False, final_idle=False, commands=receipts,
        measurement=dict(duration_ms=2000, peak_window_ms=300, peak_settle_ms=300,
                         sample_ms=10, warmup_per_worker=48000, api_warmup_ms=1000),
        notes=['Fresh sequential source blocks; no pooling with earlier rounds or different workload classes.',
               'Synthetic c01/post64 counts JIT entries, not returned bodies.',
               'SEEK_SET and pipe count measured body entries and explicit returned completions.',
               'NO_JIT/PARTIAL_JIT outcomes remain explicit; no profile or full grid is collected.',
               'Preliminary labels remain separate from the three named comparison arms.'])
    save(out / 'matrix.json', matrix)
    try:
        for name, command in commands:
            idle()
            argv = [*command, '--output', str(out / name)]
            receipt = dict(version=args.version, source_commit=args.commit, argv=argv, cwd=str(ROOT),
                           expected_sessions=6, timeout_seconds=900, started_unix=time.time())
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
            records = json.loads((out / name / 'records.json').read_text())
            expected = {(workers, repeat) for workers in (8, 60) for repeat in range(3)}
            if len(records) != 6 or {(r['threads'], r['repeat']) for r in records} != expected or not all(
                    r.get('execution_status') == 'OK' and r.get('drained') is True for r in records):
                raise RuntimeError(name + ': session inventory/result/drain differs')
            for row in records:
                if row.get('diagnostic') or row.get('perf_record') or row.get('pmu'):
                    raise RuntimeError(name + ': ordinary cohort contains instrumentation')
                if name == 'synthetic':
                    if row.get('cachelines') != 1:
                        raise RuntimeError('synthetic workload differs from c01/post64')
                elif (row.get('kind'), row.get('query'), row.get('entries'), row.get('value_size')) != (
                        ('seek', 'set', 16, 64) if name == 'seek' else ('pipebytes', 'query', 16, 64)):
                    raise RuntimeError(name + ': API workload differs')
            matrix[name + '_jit_sessions'] = sum(r.get('jit_bodies' if name == 'synthetic' else
                                                        'jit_completions', 0) > 0 for r in records)
            save(out / 'matrix.json', matrix)
        idle()
        matrix.update(passed=True, final_idle=True)
        save(out / 'matrix.json', matrix)
        return 0
    except BaseException as error:
        matrix['error'] = repr(error)
        save(out / 'matrix.json', matrix)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
