#!/usr/bin/env python3
"""VM-only placement diagnostic: unchanged provider, two isolated lock offsets.

This never edits source or loads a module directly. The ordinary API runner
owns each build/session/drain, and its diagnostic records remain unscored.
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
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-cacheline-20261019')


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def production(manifest):
    suffixes = ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch')
    return {name: value for name, value in manifest.items()
            if name.startswith(('include/', 'kernel_module/'))
            and not name.endswith('.mod.c')
            and (Path(name).suffix in suffixes or Path(name).name == 'Makefile')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2' or os.geteuid() != 0:
        raise RuntimeError('run from the maintained checkout in the recovery VM')
    if not re.fullmatch(r'[0-9a-f]{7,40}', args.commit):
        raise ValueError('record the committed diagnostic source revision')
    if os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or not os.environ.get('KDLOCK_SNAPSHOT_TAG'):
        raise RuntimeError('confirm the actual recovery snapshot first')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    base = args.base.resolve(strict=True)
    out = (args.output or base / 'placement').resolve()
    if out.exists() or out.is_relative_to(ROOT) or not out.is_relative_to(base):
        raise ValueError('require a new diagnostic directory under the external run base')
    idle = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']
    idle()
    sys.path.insert(0, str(ROOT / 'bench/real_api'))
    api = runpy.run_path(str(ROOT / 'bench/real_api/run.py'))
    original = api['sources']()
    baseline_path = base / 'packed32/pipe/source-sha256.json'
    baseline_matrix = json.loads((base / 'packed32/matrix.json').read_text())
    baseline = json.loads(baseline_path.read_text())
    if (baseline_matrix.get('source_commit') != '0987358' or
            not baseline_matrix.get('passed') or not baseline_matrix.get('final_idle') or
            not production(baseline) or production(original) != production(baseline)):
        raise RuntimeError('diagnostic provider differs from completed packed32 source 0987358')
    out.mkdir(parents=True)
    save(out / 'input-source-hashes.json', original)
    receipts = []
    result = dict(passed=False, final_idle=False, source_unchanged=False,
                  source_revision=args.commit, baseline_revision='0987358',
                  baseline_manifest_sha256=digest(baseline_path),
                  provider_matches_baseline=True, provider_files=len(production(original)),
                  input_source_hashes_sha256=digest(out / 'input-source-hashes.json'),
                  script_sha256=digest(Path(__file__)),
                  snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
                  diagnostic=True, score_eligible=False, offsets=[32, 40],
                  expected_sessions=12, profiles=0, commands=receipts,
                  note='Placement-only source uses the same provider as packed32. '
                       'Both offsets share one source manifest but have distinct compiled workload options. '
                       'Keep diagnostic rates separate from the three main timing cohorts.')
    save(out / 'result.json', result)

    def verify_source():
        if api['sources']() != original:
            raise RuntimeError('source changed during the placement diagnostic')

    commands = [('runner-plan', [sys.executable, 'bench/real_api/test_plan.py'], 90, None),
                ('runner-report', [sys.executable, 'bench/real_api/test_report.py'], 90, None)]
    for offset in (32, 40):
        argv = [sys.executable, 'bench/real_api/run.py', '--cpus', ','.join(map(str, range(60))),
                '--entries', '16', '--value-size', '64', '--warmup', '48000', '--warmup-ms', '1000',
                '--helper-waves', '4', '--helper-workers', '8', '--backends', 'kdlock',
                '--threads', '8', '60', '--duration-ms', '2000', '--collector-cpu', '63',
                '--repeats', '3', '--kinds', 'pipebytes', '--queries', 'query',
                '--mutex-lock-offset', str(offset), '--output', str(out / ('offset' + str(offset)))]
        commands.append(('offset' + str(offset), argv, 900, offset))
    try:
        for name, argv, bound, offset in commands:
            idle()
            verify_source()
            receipt = dict(name=name, argv=argv, cwd=str(ROOT), timeout_seconds=bound,
                           started_unix=time.time(), diagnostic=True, source_revision=args.commit)
            receipts.append(receipt)
            save(out / 'commands.json', receipts)
            save(out / 'result.json', result)
            print('START placement', name, flush=True)
            try:
                with (out / (name + '.log')).open('w') as log:
                    status = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                            timeout=bound)
            except subprocess.TimeoutExpired:
                receipt.update(error='TIMEOUT: drain not established; no automatic cleanup',
                               finished_unix=time.time())
                save(out / 'commands.json', receipts)
                raise
            receipt.update(exit_code=status.returncode, finished_unix=time.time())
            save(out / 'commands.json', receipts)
            print('FINISH placement', name, status.returncode, flush=True)
            if status.returncode:
                raise RuntimeError(name + ' failed; retain outputs and establish drain separately')
            verify_source()
            if offset is not None:
                folder = out / name
                records = json.loads((folder / 'records.json').read_text())
                manifest = json.loads((folder / 'source-sha256.json').read_text())
                # The runner includes its generated observation-provider overlay
                # after preparation; all original source bytes remain identical.
                original_saved = {path: value for path, value in manifest.items()
                                  if not path.startswith('bench/spin_cacheline/.build/provider/')}
                if original_saved != {path: value for path, value in original.items()
                                      if not path.startswith('bench/spin_cacheline/.build/provider/')}:
                    raise RuntimeError(name + ': retained source manifest differs')
                expected = {(workers, repeat) for workers in (8, 60) for repeat in range(3)}
                if len(records) != 6 or {(row['threads'], row['repeat']) for row in records} != expected:
                    raise RuntimeError(name + ': diagnostic session inventory differs')
                for row in records:
                    if (row.get('execution_status') != 'OK' or row.get('drained') is not True or
                            row.get('diagnostic') is not True or row.get('mutex_lock_offset') != offset or
                            row.get('lock_addr', -1) % 64 != offset or
                            row.get('jit_bodies') != row.get('jit_completions') or
                            row.get('jit_completions', 0) <= 0 or
                            row.get('retired') != dict(state=2, modules=0, frames=0, writers=0)):
                        raise RuntimeError(name + ': execution, placement, returned body or retirement differs')
                receipt.update(sessions=6, returned_jit_sessions=6,
                               records_sha256=digest(folder / 'records.json'),
                               source_manifest_sha256=digest(folder / 'source-sha256.json'))
                save(out / 'commands.json', receipts)
            idle()
            save(out / 'result.json', result)
        verify_source()
        idle()
        result.update(passed=True, final_idle=True, source_unchanged=True,
                      returned_jit_sessions=12, finished_unix=time.time())
        save(out / 'result.json', result)
        return 0
    except BaseException as error:
        result.update(error=repr(error), finished_unix=time.time())
        save(out / 'result.json', result)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
