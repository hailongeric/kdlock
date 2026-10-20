#!/usr/bin/env python3
"""VM-only basic and affected checks from a complete frozen source snapshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import time


ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-native-tclock-20261020')
DRIVERS = []
RUNNER_TESTS = ['bench/tclock_compare/test_direct.py', 'bench/spin_cacheline/test_peak.py',
                'bench/real_api/test_plan.py', 'bench/real_api/test_report.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, default=BASE / 'checks')
    args = parser.parse_args()
    if (Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2'
            or os.geteuid() != 0):
        raise RuntimeError('run from the maintained checkout in the recovery VM')
    if (os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1'
            or not os.environ.get('KDLOCK_SNAPSHOT_TAG')):
        raise RuntimeError('confirm the actual recovery snapshot before running')
    if not re.fullmatch(r'[0-9a-f]{7,40}', args.commit):
        raise ValueError('record a concrete committed source revision')
    if not all((ROOT / 'tests/unit' / name).is_file() for name in DRIVERS):
        raise RuntimeError('an explicitly selected affected driver is missing')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    idle = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']
    idle()
    out = args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError('a new output directory outside the checkout is required')
    out.mkdir(parents=True)
    source = out / 'source'
    hashes = {}
    # Freeze private include files and every source used by the focused checks.
    for directory in ('include', 'kernel_module', 'daemon', 'disassem',
                      'tests/unit', 'tests/protocols', 'tests/kernel',
                      'bench/spin_cacheline', 'bench/tclock_compare', 'bench/real_api',
                      'kernel_baseline', 'tclock_backend', 'workload_modules'):
        for path in (ROOT / directory).rglob('*'):
            relative = path.relative_to(ROOT)
            if (not path.is_file() or any(p.startswith('.') or p == '__pycache__' for p in relative.parts)
                    or path.name.endswith('.mod.c') or
                    (path.suffix not in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch')
                     and path.name not in ('Makefile', 'requirements.txt', 'guest.config'))):
                continue
            expected = digest(path)
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            if digest(target) != expected or digest(path) != expected:
                raise RuntimeError(f'source changed while freezing: {relative}')
            hashes[str(relative)] = expected
    write(out / 'source-sha256.json', hashes)

    def verify_sources():
        for relative, expected in hashes.items():
            if digest(source / relative) != expected or digest(ROOT / relative) != expected:
                raise RuntimeError(f'frozen/current source changed: {relative}')

    commands = [
        ('dependencies', [sys.executable, '-m', 'pip', 'check'], ROOT, 60),
        ('provider', ['make', '-C', 'kernel_module', 'KDIR=/root/linux-6.1.159-kdclobber2',
                      'W=1', 'UBSAN_SANITIZE=n'], source, 240),
        ('daemon', ['make', '-C', 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'], source, 60),
        ('unit', ['make', '-C', 'tests/unit', 'run', 'PY_TESTS=' + ' '.join(DRIVERS)], source, 300),
    ]
    commands += [(Path(path).stem, [sys.executable, path], source, 180)
                 for path in RUNNER_TESTS]

    receipts = []
    result_record = dict(passed=False, final_idle=False, source_unchanged=False,
                         source_revision=args.commit, unit_basic=2, unit_drivers=DRIVERS,
                         runner_tests=RUNNER_TESTS,
                         full_suite=False, snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
                         script_sha256=digest(Path(__file__)), commands=receipts)
    write(out / 'result.json', result_record)
    try:
        for name, command, cwd, timeout in commands:
            verify_sources()
            idle()
            print('START checks', name, flush=True)
            receipt = dict(name=name, argv=command, cwd=str(cwd), started_unix=time.time(),
                           timeout_seconds=timeout)
            receipts.append(receipt)
            write(out / 'commands.json', receipts)
            try:
                with (out / (name + '.log')).open('w') as log:
                    result = subprocess.run(command, cwd=cwd, stdout=log,
                                            stderr=subprocess.STDOUT, timeout=timeout)
            except subprocess.TimeoutExpired:
                receipt.update(error='TIMEOUT: drain not established', finished_unix=time.time())
                write(out / 'commands.json', receipts)
                raise
            receipt.update(exit_code=result.returncode, finished_unix=time.time())
            write(out / 'commands.json', receipts)
            print('FINISH checks', name, result.returncode, flush=True)
            if result.returncode:
                print((out / (name + '.log')).read_text()[-12000:], flush=True)
                result_record['error'] = f'{name} exited {result.returncode}'
                write(out / 'result.json', result_record)
                return result.returncode
        verify_sources()
        idle()
        result_record.update(passed=True, final_idle=True, source_unchanged=True)
        write(out / 'result.json', result_record)
        return 0
    except Exception as error:
        result_record['error'] = str(error)
        write(out / 'result.json', result_record)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
