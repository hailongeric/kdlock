#!/usr/bin/env python3
"""VM-only basic and affected checks from a complete frozen source snapshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time


ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-traffic-20261019')
DRIVERS = ['mutex/test_mutex_aux.py', 'mutex/test_mutex_resources.py',
           'mutex/test_mutex_balances.py', 'mutex/test_mutex_terminal.py',
           'mutex/test_mutex_outer_progress.py', 'mutex/test_mutex_outer_api.py',
           'mutex/test_mutex_wait_clobber.py', 'mutex/test_mutex_task_cache.py',
           'execution/test_exec_capacity.py', 'infrastructure/test_provider_lifecycle.py',
           'execution/test_mutex_images.py', 'execution/test_remote_outer.py']


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
    idle = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']
    idle()
    out = args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError('a new output directory outside the checkout is required')
    out.mkdir(parents=True)
    source = out / 'source'
    hashes = {}
    # exec_capacity consumes tests/kernel/execution/exec_relay_exit_probe.c;
    # include all kernel probe source from the first attempt, alongside .inc.
    for directory in ('include', 'kernel_module', 'daemon', 'disassem',
                      'tests/unit', 'tests/protocols', 'tests/kernel'):
        for path in (ROOT / directory).rglob('*'):
            relative = path.relative_to(ROOT)
            if (not path.is_file() or any(p.startswith('.') or p == '__pycache__' for p in relative.parts)
                    or path.name.endswith('.mod.c') or
                    (path.suffix not in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch')
                     and path.name not in ('Makefile', 'requirements.txt'))):
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
        ('local', [sys.executable, 'tests/kernel/mutex/local/run.py', '--output', str(out / 'local')], ROOT, 300),
        ('rwsem', [sys.executable, 'tests/kernel/rwsem/run.py', '--output', str(out / 'rwsem')], ROOT, 300),
        ('instruction-exit', [sys.executable, 'tests/kernel/jit_escape/run.py', '--cpus', '0-7,32-39',
                              '--iterations', '200000', '--warmup-iterations', '200000',
                              '--output', str(out / 'instruction-exit')], ROOT, 900),
    ]
    receipts = []
    result_record = dict(passed=False, final_idle=False, source_unchanged=False,
                         source_revision=args.commit, unit_basic=2, unit_drivers=DRIVERS,
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
