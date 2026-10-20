#!/usr/bin/env python3
"""One bounded guest I/O diagnostic, never a lock-performance measurement.

The RAM and ext4 arms use the same eight workers, payload and fsync calls.
Retain all newly created files. A settle interval follows SSH/import/setup
activity so those writes can be distinguished from the declared pulse.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', choices=('ram', 'disk'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    root = Path('/root/host_fs/kdlock')
    assert Path.cwd() == root
    out = args.output.resolve()
    prefix = (Path('/dev/shm/kdlock-qemu-io-20261021') if args.storage == 'ram' else
              Path('/root/kdlock-evidence/10.176.26.71/tests/qemu-io-diagnostic-20261021'))
    assert out.is_relative_to(prefix) and out != prefix and not out.exists()
    # The diagnostic is exclusive with all lock tests and evidence writers.
    import runpy
    import sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root/'bench/spin_cacheline'))
    import bench_runtime as rt
    runpy.run_path(str(root/'bench/archive_run.py'))['idle'](out, rt.idle)
    out.mkdir(parents=True)
    filesystem = subprocess.check_output(['findmnt', '-T', str(out), '-n', '-o', 'FSTYPE'],
                                         text=True, timeout=10).strip()
    assert filesystem == ('tmpfs' if args.storage == 'ram' else 'ext4')
    assert os.statvfs(out).f_bavail*os.statvfs(out).f_frsize > 256*1024*1024
    block = bytes(range(256))*256
    expected = hashlib.sha256(block*64).hexdigest()
    result = dict(storage=args.storage, filesystem=filesystem, output=str(out),
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  pid=os.getpid(), workers=8, bytes_per_worker=len(block)*64,
                  setup_finished_ns=time.time_ns(), settle_seconds=12,
                  scope='Diagnostic I/O stimulus only; no KD module or lock workload.')
    barrier = threading.Barrier(8)

    def pulse(cpu):
        os.sched_setaffinity(0, {cpu})
        barrier.wait(timeout=10)
        started = time.time_ns()
        path = out/('worker-'+str(cpu)+'.bin')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            for _ in range(64):
                cursor = 0
                while cursor < len(block):
                    amount = os.write(fd, block[cursor:])
                    assert amount > 0
                    cursor += amount
            os.fsync(fd)
        finally:
            os.close(fd)
        finished = time.time_ns()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert path.stat().st_size == len(block)*64 and digest == expected
        return dict(cpu=cpu, tid=threading.get_native_id(),
                    affinity=sorted(os.sched_getaffinity(0)),
                    started_ns=started, fsync_finished_ns=finished,
                    verification_finished_ns=time.time_ns(), bytes=path.stat().st_size,
                    sha256=digest)

    time.sleep(12)
    result['pulse_started_ns'] = time.time_ns()
    with ThreadPoolExecutor(max_workers=8) as executor:
        rows = list(executor.map(pulse, range(8)))
    result.update(finished_ns=time.time_ns(), results=rows,
                  total_bytes=sum(r['bytes'] for r in rows), complete=True)
    assert [r['affinity'] for r in rows] == [[i] for i in range(8)]
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
