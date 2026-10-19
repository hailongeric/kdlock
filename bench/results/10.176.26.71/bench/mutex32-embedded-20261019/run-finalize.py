#!/usr/bin/env python3
"""Run reviewed analysis in the idle VM and retain actual command statuses."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-embedded-20261019')


def main():
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('use the idle recovery VM checkout')
    output = BASE / 'final-analysis-commands.json'
    if output.exists():
        raise RuntimeError('retain the existing analysis attempt before retrying')
    sys.dont_write_bytecode = True
    local = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))
    archive = runpy.run_path(str(ROOT / 'bench/archive_run.py'))
    archive['idle'](BASE, local['idle'])
    rows = []
    for name in ('summarize.py', 'finalize.py'):
        argv = ['python3', str(BASE / name), '--base', str(BASE), '--arms', 'embedded32', 'old256']
        if name == 'finalize.py':
            argv += ['--check', 'embedded32=checks-embedded32', '--current-arm', 'embedded32']
        row = dict(argv=argv, cwd=str(ROOT), started_unix=time.time(), timeout_seconds=240)
        rows.append(row)
        output.write_text(json.dumps(rows, indent=2) + '\n')
        try:
            result = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
            row.update(finished_unix=time.time(), exit_code=result.returncode, stdout=result.stdout.decode(errors='replace'))
        except BaseException as error:
            row.update(finished_unix=time.time(), error=repr(error))
            output.write_text(json.dumps(rows, indent=2) + '\n')
            raise
        output.write_text(json.dumps(rows, indent=2) + '\n')
        print(row['stdout'], end='', flush=True)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
