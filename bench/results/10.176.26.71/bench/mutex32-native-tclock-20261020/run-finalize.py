#!/usr/bin/env python3
"""Run bounded retained-data analysis in the idle VM; preserve every status."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-native-tclock-20261020')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=BASE)
    args = parser.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('run from the maintained recovery VM checkout')
    output = args.base / 'final-analysis-commands.json'
    if output.exists():
        raise RuntimeError('preserve the previous analysis attempt before retrying')
    receipts = []
    for name in ('summarize.py', 'finalize.py'):
        argv = [sys.executable, str(args.base / name), '--base', str(args.base)]
        receipt = dict(argv=argv, cwd=str(ROOT), timeout_seconds=600, started_unix=time.time())
        receipts.append(receipt)
        try:
            result = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
            receipt.update(exit_code=result.returncode, stdout=result.stdout.decode(errors='replace'))
        except subprocess.TimeoutExpired:
            receipt['error'] = 'TIMEOUT: final idle not established'
            raise
        finally:
            receipt['finished_unix'] = time.time()
            output.write_text(json.dumps(receipts, indent=2, sort_keys=True) + '\n')
        print(receipt['stdout'], end='', flush=True)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
