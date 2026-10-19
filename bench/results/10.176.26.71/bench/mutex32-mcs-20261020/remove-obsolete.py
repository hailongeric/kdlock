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
    # Reviewed tracked additions absent from old256. These exact baseline
    # bytes are the only authorized removals; changed candidates need review.
    'old256': {
        'tests/unit/mutex/test_mutex_head.py': '590876185a17c222bc1bbff6a9fac52b13ac071f2814efface06665cc126cd18',
        'tests/unit/mutex/mutex_head_fixture.c': '2a1aa137dea2c0e63b98f19d95ccf3793fd37c78830af9d21d91fd1f055f77bf',
        'include/kd_mutex_state.h': '27d529dda4aaf1a289ebb2fcf0d266a0d4b5c0cc618c0c164715b5b740173f3e',
        'kernel_module/mutex/count.inc': '35d3533de0445789f2ae1d40063c4f091b0ce5fe42de553f594f4e6abe924368',
        'tests/unit/mutex/mutex_count_fixture.c': '961d095d05afd31028be716d4ef662c3e270683c60ca7c7d4198fef24849782c',
        'tests/unit/mutex/mutex_state_fixture.c': '01f8b563bd14668e0d1a5a120ee3a97b3a1db4665d4a87be81181f272e63849b',
        'tests/unit/mutex/mutex_state_mock.h': 'b09972d7c33049eb6e9c206a83137cd58aa93d88bf4dab47f69f3b4aed08b1f1',
        'tests/unit/mutex/test_mutex_count.py': 'd43ea8dda6cbd2f96569a37c3e45d852bc1044d34313fd6f4decef1a955bf3ac',
        'tests/unit/mutex/test_mutex_state.py': '99d5f21672fb416af4385ac447698b10e3dbda1399c41b6272a1a43155604bea',
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
