#!/usr/bin/env python3
"""VM-only copy of compact metadata after a completed, idle grouped archive.

The raw tar archives remain authoritative. This exports top-level metadata and
one-level command/check receipts only, never source trees or raw sample arrays.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time

ROOT = Path('/root/host_fs/kdlock')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if Path.cwd() != ROOT or os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('run from the idle recovery VM checkout')
    base, archives, out = args.base.resolve(strict=True), args.archives.resolve(strict=True), args.output.resolve()
    if out.exists() or out.is_relative_to(base) or out.is_relative_to(archives) or out.is_relative_to(ROOT):
        raise ValueError('require a new external compact-output directory')
    receipt = json.loads((archives / 'archives.json').read_bytes())
    if (receipt.get('completed') is not True or receipt.get('guest_base') != str(base) or
            receipt.get('boot_id') != Path('/proc/sys/kernel/random/boot_id').read_text().strip()):
        raise RuntimeError('require the complete grouped archive from this evidence tree and boot')
    sys.dont_write_bytecode = True
    local = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))
    archive = runpy.run_path(str(ROOT / 'bench/archive_run.py'))
    archive['idle'](base, local['idle'])
    files = [path for path in base.iterdir() if path.is_file() and not path.is_symlink()]
    for folder in base.iterdir():
        if folder.is_dir() and not folder.is_symlink():
            files.extend(path for path in folder.iterdir() if path.is_file() and
                         not path.is_symlink() and path.suffix in ('.json', '.log'))
    out.mkdir(parents=True)
    hashes = {}
    for path in sorted(files):
        relative = path.relative_to(base)
        expected = digest(path)
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        if digest(destination) != expected or digest(path) != expected:
            raise RuntimeError('compact source changed during export: ' + str(relative))
        hashes[str(relative)] = expected
    shutil.copyfile(archives / 'archives.json', out / 'archives.json')
    archive['idle'](base, local['idle'])
    result = dict(passed=True, created_unix=time.time(), files=hashes,
                  archives_sha256=digest(archives / 'archives.json'),
                  note='Compact copies only; all raw source, samples and logs remain in grouped archives.')
    (out / 'compact-export.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(passed=True, files=len(hashes), output=str(out))))


if __name__ == '__main__':
    main()
