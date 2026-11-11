#!/usr/bin/env python3
"""Observe the reviewed recovery child once and retain it on a deadline."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

WORK = Path('/mnt/kdlock-builds/kdlock-main-work/kernel4-fixtures-0a07f678-01a1bc4f')
OUT = WORK / 'recovery-spin-controller-01'
PYTHON = Path('/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(OUT, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--helper-sha256', required=True)
    parser.add_argument('--seconds', type=float, required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0 and math.isfinite(args.seconds) and 0 < args.seconds <= 300,
            'root and explicit bounded observer required')
    require(args.helper.resolve(strict=True) == args.helper and args.helper.is_relative_to(WORK)
            and args.helper.is_file() and not args.helper.is_symlink(), 'exact persistent work helper required')
    actual = hashlib.sha256(args.helper.read_bytes()).hexdigest()
    require(actual == args.helper_sha256 and PYTHON.is_file(), 'reviewed helper/interpreter differs')
    require(os.uname().release == '7.0.0-38-kdrebuild4' and
            Path('/proc/sys/kernel/random/boot_id').read_text().strip() == '84e4ba94-b616-4b65-9efe-820921f36c16' and
            Path('/proc/sys/kernel/tainted').read_text().strip() == '12288', 'failed boot identity differs')
    for path, minimum in ((Path('/'), 1024 ** 3), (WORK, 4 * 1024 ** 3)):
        extent = os.statvfs(path)
        require(extent.f_bavail * extent.f_frsize >= minimum, 'fresh recovery headroom is unavailable')
    require(not OUT.exists(), 'fresh observer receipt required')
    OUT.mkdir(mode=0o700)
    argv = [str(PYTHON), str(args.helper), '--max-file-bytes', str(8 * 1024 * 1024),
            '--max-history-bytes', str(32 * 1024 * 1024), '--max-archive-bytes', str(64 * 1024 * 1024)]
    save('command.json', dict(argv=argv, helper_sha256=actual, observer_seconds=args.seconds,
         unix=time.time(), policy='One ordinary attempt. Observer expiration retains child and never establishes drain.'))
    start = time.monotonic()
    with (OUT / 'stdout.log').open('xb') as log:
        child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        save('child.json', dict(pid=child.pid, unix=time.time()))
        while child.poll() is None and time.monotonic() - start < args.seconds:
            time.sleep(0.25)
        code = child.poll()
        result = dict(returncode=code, pid=child.pid, elapsed_seconds=time.monotonic() - start,
                      unix=time.time(), observer_expired=code is None, child_retained=code is None)
        log.flush()
        os.fsync(log.fileno())
    save('result.json', result)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 124 if result['observer_expired'] else result['returncode']


if __name__ == '__main__':
    raise SystemExit(main())
