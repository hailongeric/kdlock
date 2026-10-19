#!/usr/bin/env python3
"""Remove only reviewed compact-only runtime sources after idle old-source sync."""
import hashlib
import json
import os
from pathlib import Path
import runpy

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-traffic-20261019')
PATHS = ('include/kd_mutex_aux.h', 'kernel_module/kd_mutex_aux.c')

if os.uname().release != '6.1.159-kdclobber2' or Path.cwd() != ROOT:
    raise RuntimeError('use the idle recovery VM checkout')
runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']()
manifest = json.loads((BASE / 'checks-fetchadd/source-sha256.json').read_text())
receipt = BASE / 'old256-source-cleanup.json'
if receipt.exists():
    raise RuntimeError('cleanup receipt already exists')
rows = []
for name in PATHS:
    path = ROOT / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_symlink() or digest != manifest[name]:
        raise RuntimeError('unexpected obsolete source bytes: ' + name)
    rows.append(dict(path=name, sha256=digest, removed=False))
record = dict(source_commit='0324e60d6791948e9762a9916a50e8e026f073b0',
              reason='These two compact-only runtime paths are absent from the reviewed old commit.',
              idle=True, files=rows, complete=False)
receipt.write_text(json.dumps(record, indent=2) + '\n')
for row in rows:
    (ROOT / row['path']).unlink()
    row['removed'] = True
    receipt.write_text(json.dumps(record, indent=2) + '\n')
record['complete'] = all(not (ROOT / name).exists() for name in PATHS)
receipt.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
