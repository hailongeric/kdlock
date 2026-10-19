#!/usr/bin/env python3
"""Run reviewed analysis in the idle VM and retain actual command statuses."""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-cacheline-20261019')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--arms', nargs='+', default=['packed32', 'candidate', 'old256'])
    parser.add_argument('--check', action='append', metavar='ARM=DIRECTORY')
    parser.add_argument('--current-arm', default='candidate')
    args = parser.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('use the idle recovery VM checkout')
    base = args.base.resolve(strict=True)
    if base.is_relative_to(ROOT):
        raise ValueError('use an external evidence directory')
    output = base / 'final-analysis-commands.json'
    if output.exists():
        raise RuntimeError('retain the existing analysis attempt before retrying')
    sys.dont_write_bytecode = True
    local = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))
    archive = runpy.run_path(str(ROOT / 'bench/archive_run.py'))
    archive['idle'](base, local['idle'])
    rows = []
    for name in ('placement-analysis.py', 'summarize.py', 'profile-analysis.py', 'finalize.py'):
        argv = ['python3', str(base / name), '--base', str(base)]
        if name != 'placement-analysis.py':
            argv += ['--arms', *args.arms]
        if name == 'finalize.py':
            for check in args.check or ['candidate=checks-candidate']:
                argv += ['--check', check]
            argv += ['--current-arm', args.current_arm]
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
