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
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-mcs-20261020')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, default=BASE)
    p.add_argument('--arms', nargs='+', default=['baseline', 'candidate', 'old256', 'locality256'])
    p.add_argument('--check', action='append', default=[])
    p.add_argument('--current-arm', required=True)
    a = p.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('run from the maintained recovery VM checkout')
    output = a.base / 'final-analysis-commands-v2.json'
    if output.exists():
        raise RuntimeError('preserve the previous analysis attempt before retrying')
    receipts = []
    for name in ('summarize-v2.py', 'finalize-v2.py'):
        argv = [sys.executable, str(a.base / name), '--base', str(a.base), '--arms', *a.arms]
        if name == 'finalize-v2.py':
            for check in a.check or ['candidate=checks-candidate', 'locality256=checks-locality256']:
                argv += ['--check', check]
            argv += ['--current-arm', a.current_arm]
        receipt = dict(argv=argv, cwd=str(ROOT), timeout_seconds=240, started_unix=time.time())
        receipts.append(receipt)
        try:
            result = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=240)
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
