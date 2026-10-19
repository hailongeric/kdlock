#!/usr/bin/env python3
"""VM-only basic and affected validation, with immutable source receipts."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

root = Path('/root/host_fs/kdlock')
assert Path.cwd() == root and os.uname().release == '6.1.159-kdclobber2'
runpy.run_path(str(root / 'tests/kernel/mutex/local/run.py'))['idle']()
out = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-opt-20261019/checks')
out.mkdir()
source = out / 'source'
hashes = {}
for directory in ('include', 'kernel_module', 'daemon', 'disassem', 'tests/unit', 'tests/protocols'):
    for path in (root / directory).rglob('*'):
        relative = path.relative_to(root)
        if (not path.is_file() or any(p.startswith('.') or p == '__pycache__' for p in relative.parts)
                or path.name.endswith('.mod.c') or
                (path.suffix not in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json')
                 and path.name not in ('Makefile', 'requirements.txt'))):
            continue
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
(out / 'source-sha256.json').write_text(json.dumps(hashes, indent=2, sort_keys=True)+'\n')
drivers = ['mutex/test_mutex_aux.py', 'mutex/test_mutex_resources.py',
           'mutex/test_mutex_balances.py', 'mutex/test_mutex_terminal.py',
           'mutex/test_mutex_outer_progress.py', 'mutex/test_mutex_outer_api.py',
           'mutex/test_mutex_wait_clobber.py', 'mutex/test_mutex_task_cache.py',
           'execution/test_exec_capacity.py', 'infrastructure/test_provider_lifecycle.py',
           'execution/test_mutex_images.py', 'execution/test_remote_outer.py']
commands = [
    ('dependencies', [sys.executable, '-m', 'pip', 'check'], root, 60),
    ('provider', ['make', '-C', 'kernel_module', 'KDIR=/root/linux-6.1.159-kdclobber2', 'W=1', 'UBSAN_SANITIZE=n'], source, 240),
    ('daemon', ['make', '-C', 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'], source, 60),
    ('unit', ['make', '-C', 'tests/unit', 'run', 'PY_TESTS='+' '.join(drivers)], source, 300),
    ('local', [sys.executable, 'tests/kernel/mutex/local/run.py', '--output', str(out / 'local')], root, 300),
    ('rwsem', [sys.executable, 'tests/kernel/rwsem/run.py', '--output', str(out / 'rwsem')], root, 300),
    ('instruction-exit', [sys.executable, 'tests/kernel/jit_escape/run.py', '--cpus', '0-7,32-39',
        '--iterations', '200000', '--warmup-iterations', '200000', '--output', str(out / 'instruction-exit')], root, 900),
]
receipts = []
for name, command, cwd, timeout in commands:
    print('START checks', name, flush=True)
    receipt = dict(name=name, argv=command, cwd=str(cwd), started_unix=time.time(), timeout_seconds=timeout)
    receipts.append(receipt)
    (out / 'commands.json').write_text(json.dumps(receipts, indent=2)+'\n')
    with (out / (name+'.log')).open('w') as log:
        result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    receipt.update(exit_code=result.returncode, finished_unix=time.time())
    (out / 'commands.json').write_text(json.dumps(receipts, indent=2)+'\n')
    print('FINISH checks', name, result.returncode, flush=True)
    if result.returncode:
        print((out/(name+'.log')).read_text()[-12000:], flush=True)
        raise SystemExit(result.returncode)
for relative, expected in hashes.items():
    assert hashlib.sha256((source/relative).read_bytes()).hexdigest() == expected, relative
    assert hashlib.sha256((root/relative).read_bytes()).hexdigest() == expected, relative
runpy.run_path(str(root / 'tests/kernel/mutex/local/run.py'))['idle']()
(out/'result.json').write_text(json.dumps(dict(passed=True, idle=True, source_unchanged=True,
    unit_basic=2, unit_drivers=drivers, full_suite=False, commands=receipts), indent=2)+'\n')
