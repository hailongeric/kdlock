#!/usr/bin/env python3
"""VM-only initial frozen runtime build while focused fixtures are prepared."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import time

root = Path('/root/host_fs/kdlock')
out = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-embedded-20261019/build-initial')
assert Path.cwd() == root and os.uname().release == '6.1.159-kdclobber2'
runpy.run_path(str(root / 'tests/kernel/mutex/local/run.py'))['idle']()
out.mkdir(parents=True)
source = out / 'source'
hashes = {}
for directory in ('include', 'kernel_module', 'daemon'):
    for path in (root / directory).rglob('*'):
        relative = path.relative_to(root)
        if (not path.is_file() or any(p.startswith('.') or p == '__pycache__' for p in relative.parts)
                or path.name.endswith('.mod.c') or
                (path.suffix not in ('.c', '.h', '.inc', '.S', '.def', '.json')
                 and path.name != 'Makefile')):
            continue
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
(out / 'source-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
receipts = []
for name, argv in (
    ('provider', ['make', '-C', 'kernel_module', 'KDIR=/root/linux-6.1.159-kdclobber2', 'W=1', 'UBSAN_SANITIZE=n']),
    ('daemon', ['make', '-C', 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror']),
):
    print('START', name, flush=True)
    record = dict(name=name, argv=argv, started_unix=time.time(), timeout_seconds=240)
    receipts.append(record)
    with (out / (name + '.log')).open('w') as log:
        result = subprocess.run(argv, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    record.update(exit_code=result.returncode, finished_unix=time.time())
    (out / 'commands.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print('FINISH', name, result.returncode, flush=True)
    if result.returncode:
        print((out / (name + '.log')).read_text()[-16000:])
        raise SystemExit(result.returncode)
