#!/usr/bin/env python3
"""Record bounded VM-only report generation separately from timing sessions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-index-20261019')
if os.uname().release != '6.1.159-kdclobber2' or os.geteuid() != 0:
    raise RuntimeError('run only in the recovery VM')
receipt = BASE / 'postprocess-commands.json'
if receipt.exists():
    raise RuntimeError('retain the existing attempt; use a reviewed new retry receipt')
rows = []
for name, interpreter in (
        ('summarize.py', '/root/kdlock-translation-venv-20261019/bin/python3'),
        ('profile-analysis.py', '/root/kdlock-translation-venv-20261019/bin/python3'),
        ('plot.py', '/root/kdlock-plot-venv-20261019/bin/python3')):
    arguments = ['--input', str(BASE / 'comparison.json')] if name == 'plot.py' else ['--base', str(BASE)]
    command = [interpreter, str(BASE / name), *arguments]
    row = dict(argv=command, started_unix=time.time(), timeout_seconds=120,
               script_sha256=hashlib.sha256((BASE / name).read_bytes()).hexdigest())
    rows.append(row)
    receipt.write_text(json.dumps(rows, indent=2) + '\n')
    try:
        with (BASE / (name + '.log')).open('x') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        row['exit_code'] = result.returncode
    except Exception as error:
        row['error'] = repr(error)
        raise
    finally:
        row['finished_unix'] = time.time()
        receipt.write_text(json.dumps(rows, indent=2) + '\n')
    print(name, result.returncode, flush=True)
    if result.returncode:
        print((BASE / (name + '.log')).read_text(), flush=True)
        raise SystemExit(result.returncode)
