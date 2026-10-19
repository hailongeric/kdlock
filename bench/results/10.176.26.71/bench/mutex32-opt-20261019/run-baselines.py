#!/usr/bin/env python3
"""Bounded VM-only matched mutex measurements; no source mutation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--version', required=True)
p.add_argument('--commit', required=True)
a = p.parse_args()
root = Path('/root/host_fs/kdlock')
assert Path.cwd() == root and os.uname().release == '6.1.159-kdclobber2'
base = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-opt-20261019') / a.version
base.mkdir()
python = sys.executable
common = ['--backends', 'kdlock', '--threads', '8', '60', '--repeats', '3',
          '--duration-ms', '2000', '--collector-cpu', '63']
synthetic = [python, 'bench/tclock_compare/run_mutex.py', '--cpus', '0-59']
api = [python, 'bench/real_api/run.py', '--cpus', ','.join(map(str, range(60))),
       '--entries', '16']
commands = [
    ('profile', synthetic + ['--backends', 'kdlock', '--cachelines', '8',
        '--threads', '8', '60', '--repeats', '1', '--duration-ms', '2000',
        '--collector-cpu', '63', '--perf-record']),
    ('synthetic', synthetic + common + ['--cachelines', '1', '8', '--keep-going-no-jit']),
    ('seek', api + common + ['--kinds', 'seek', '--queries', 'set', '--require-jit']),
    ('pipe', api + ['--backends', 'kdlock', '--threads', '8', '--repeats', '3',
        '--duration-ms', '2000', '--collector-cpu', '63', '--kinds', 'pipebytes',
        '--queries', 'query']),
]
for name, command in commands:
    command += ['--output', str(base / name)]
    receipt = {'version': a.version, 'source_commit': a.commit,
               'argv': command, 'cwd': str(root), 'started_unix': time.time()}
    path = base / (name + '-command.json')
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    print('START', a.version, name, flush=True)
    try:
        with (base / (name + '-command.log')).open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    except subprocess.TimeoutExpired:
        receipt.update(error='TIMEOUT: drain not established', finished_unix=time.time())
        path.write_text(json.dumps(receipt, indent=2) + '\n')
        raise
    receipt.update(exit_code=result.returncode, finished_unix=time.time())
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    print('FINISH', a.version, name, result.returncode, flush=True)
    if result.returncode:
        print((base / (name + '-command.log')).read_text()[-8000:], flush=True)
        raise SystemExit(result.returncode)
