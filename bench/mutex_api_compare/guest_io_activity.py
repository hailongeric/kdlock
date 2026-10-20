#!/usr/bin/env python3
"""Read guest process I/O metadata across one idle interval; no workload."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')


def capture():
    rows, errors = {}, []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            stat = (proc/'stat').read_text()
            start = stat.rsplit(')', 1)[1].split()[19]
            io = {k: int(v) for k, v in (line.split(': ') for line in
                                       (proc/'io').read_text().splitlines())}
            rows[proc.name] = dict(start_ticks=start, comm=(proc/'comm').read_text().strip(), io=io)
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError as error:
            errors.append(dict(pid=proc.name, error=repr(error)))
    return dict(time_ns=time.time_ns(), processes=rows, errors=errors,
                diskstats=Path('/proc/diskstats').read_text())


def main():
    assert os.geteuid() == 0 and Path.cwd() == ROOT
    assert os.uname().release == '6.1.159-kdclobber2'
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot == 'b65f0205-c8f9-4385-8b13-039cbce243a6'
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    archive['idle'](Path('/root/kdlock-evidence/10.176.26.71/bench/nano-rwlock-diagnosis-20261021'),
                    rt.idle)
    os.sched_setaffinity(0, {63})
    before = capture()
    time.sleep(12)
    after = capture()
    changed = []
    for pid, row in after['processes'].items():
        old = before['processes'].get(pid)
        if not old or old['start_ticks'] != row['start_ticks']:
            continue
        delta = {k: v-old['io'][k] for k, v in row['io'].items()}
        if not any(delta[k] for k in ('wchar', 'write_bytes', 'cancelled_write_bytes')):
            continue
        descriptors = []
        for fd in Path('/proc', pid, 'fd').glob('*'):
            try:
                target = os.readlink(fd)
                if target.startswith('/'):
                    descriptors.append(dict(fd=int(fd.name), target=target))
            except (FileNotFoundError, ProcessLookupError):
                pass
            except OSError as error:
                descriptors.append(dict(fd=int(fd.name), error=repr(error)))
        changed.append(dict(pid=int(pid), comm=row['comm'], start_ticks=row['start_ticks'],
                            delta=delta, descriptors=descriptors))
    archive['idle'](Path('/root/kdlock-evidence/10.176.26.71/bench/nano-rwlock-diagnosis-20261021'),
                    rt.idle)
    print(json.dumps(dict(boot_id=boot, scope='Read-only guest I/O metadata, no lock timing',
                          before=before, after=after, writers=changed, idle=True,
                          idle_helper_sha256=hashlib.sha256((ROOT/'bench/archive_run.py').read_bytes()).hexdigest()),
                     indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
