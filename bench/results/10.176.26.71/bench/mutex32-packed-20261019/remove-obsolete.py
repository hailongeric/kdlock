#!/usr/bin/env python3
"""VM-only, exact-path removal of reviewed obsolete production source files.

This does not synchronize files or unload anything. It requires idle state,
matches every present file before deleting any, and records every action.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
KNOWN = {
    'embedded32': {
        'include/kd_mutex_aux.h': '118f02a19a0f67e7117e7d8a10d832dba96ad3956b024e82f404aa75b28ca797',
        'kernel_module/kd_mutex_aux.c': '5b5f9e1e3ba8f7f804c383e55cd22ca015c1341411958a07490817f6793bc7be',
        'tests/unit/mutex/test_mutex_aux.py': 'aad3a9797e4b72b380b161ac365363466f507883f7d45726566bd30cbef74482',
        'tests/unit/mutex/mutex_aux_fixture.c': '2ff5bfc799d33b95587cbb4019648ebe7572529d48496386e956f7a0eea78b62',
        'tests/unit/mutex/mutex_aux_mock.h': '529f8902128b5f924200416c03b56d02924623c63afe6dd35a2189869a85ae9d',
    },
    'old256': {
        'include/kd_mutex_state.h': '0e232ea6665d1ddeb6ab62544822fb46f93b7716cf5b5a30ecd8e33fee03506c',
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=tuple(KNOWN), required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2' or os.geteuid() != 0:
        raise RuntimeError('run from the maintained checkout in the recovery VM')
    if args.receipt.exists() or args.receipt.resolve().is_relative_to(ROOT):
        raise ValueError('require a new receipt outside the source checkout')
    sys.dont_write_bytecode = True
    idle = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))['idle']
    idle()
    rows = []
    for relative, expected in KNOWN[args.target].items():
        path = ROOT / relative
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError(f'not a regular source file: {relative}')
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if actual is not None and actual != expected:
            raise RuntimeError(f'unreviewed bytes at {relative}: {actual}')
        rows.append(dict(path=relative, expected_sha256=expected, observed_sha256=actual,
                         action='pending' if actual else 'already_absent'))
    receipt = dict(target=args.target, started_unix=time.time(), passed=False, files=rows)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    save()
    try:
        for row in rows:
            if row['action'] == 'pending':
                path = ROOT / row['path']
                # Recheck immediately before the reviewed unlink. Synchronization
                # must remain idle and exclusive for the complete operation.
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != row['expected_sha256']:
                    raise RuntimeError(f'source changed after review: {row["path"]}')
                path.unlink()
                row['action'] = 'removed'
                save()
        idle()
        receipt.update(passed=True, final_idle=True, finished_unix=time.time())
        save()
        print(json.dumps(receipt, sort_keys=True))
    except BaseException as error:
        receipt.update(error=repr(error), finished_unix=time.time())
        save()
        raise


if __name__ == '__main__':
    main()
