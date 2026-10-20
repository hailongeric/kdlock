#!/usr/bin/env python3
"""Read the existing QEMU's threads, I/O and identity without changing it.

This is diagnostic evidence, not an admission or performance pass. Optional
proc files retain their access errors. No tracing, affinity, pool parameter,
guest state or permission is modified. Run via bounded SSH on the benchmark
host; retain stdout on the source host.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import time


def read(path):
    try:
        return dict(status='READ', text=path.read_text())
    except OSError as error:
        return dict(status='DENIED' if isinstance(error, PermissionError) else 'UNAVAILABLE',
                    error=repr(error), path=str(path))


def threads(proc):
    began = time.time_ns()
    rows = []
    for task in sorted((proc/'task').iterdir(), key=lambda p: int(p.name)):
        try:
            before = (task/'stat').read_text()
            row = dict(tid=int(task.name), comm=(task/'comm').read_text().strip(),
                       affinity=sorted(os.sched_getaffinity(int(task.name))),
                       stat_before=before,
                       files={name: read(task/name) for name in
                              ('status', 'schedstat', 'wchan', 'syscall', 'io')})
            if row['comm'] == 'worker':
                row['files']['stack'] = read(task/'stack')
            row['stat_after'] = (task/'stat').read_text()
            rows.append(row)
        except (FileNotFoundError, ProcessLookupError) as error:
            rows.append(dict(tid=int(task.name), disappeared=True, error=repr(error)))
    return dict(started_ns=began, finished_ns=time.time_ns(), tasks=rows)


def monitor_queries():
    commands = ['info version', 'info block', 'info blockstats', 'info iothreads']
    rows = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as monitor:
        monitor.settimeout(8)
        monitor.connect('/tmp/qemu-monitor.sock')

        def response():
            data = bytearray()
            while not data.endswith(b'(qemu) '):
                chunk = monitor.recv(65536)
                if not chunk:
                    raise RuntimeError('monitor closed before its prompt')
                data.extend(chunk)
                if len(data) > 4*1024*1024:
                    raise RuntimeError('monitor response exceeded diagnostic bound')
            return data.decode(errors='replace')

        banner = response()
        for command in commands:
            began = time.time_ns()
            monitor.sendall(command.encode()+b'\n')
            rows.append(dict(command=command, started_ns=began,
                             response=response(), finished_ns=time.time_ns()))
    return dict(banner=banner, commands=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--cmdline-sha256', required=True)
    parser.add_argument('--monitor', action='store_true')
    args = parser.parse_args()
    proc = Path('/proc')/str(args.pid)
    command = (proc/'cmdline').read_bytes()
    assert Path(os.fsdecode(command.split(b'\0')[0])).name == 'qemu-system-x86_64'
    assert hashlib.sha256(command).hexdigest() == args.cmdline_sha256
    started = (proc/'stat').read_text().rsplit(')', 1)[1].split()[19]
    out = dict(captured_utc=datetime.now(timezone.utc).isoformat(), pid=args.pid,
               cmdline_sha256=args.cmdline_sha256,
               argv=[os.fsdecode(p) for p in command.split(b'\0') if p],
               before=threads(proc), process_io_before=read(proc/'io'),
               executable=os.readlink(proc/'exe'), maps=read(proc/'maps'),
               package_metadata=[], disk_and_log_descriptors=[])
    digest = hashlib.sha256()
    with (proc/'exe').open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    out['executable_sha256'] = digest.hexdigest()
    for paragraph in Path('/var/lib/dpkg/status').read_text().split('\n\n'):
        fields = dict(line.split(': ', 1) for line in paragraph.splitlines()
                      if line and not line[0].isspace() and ': ' in line)
        if fields.get('Package') in ('qemu-system-x86', 'qemu-system-common'):
            out['package_metadata'].append({k: fields[k] for k in
                                            ('Package', 'Version', 'Architecture', 'Status')})
    for fd in sorted((proc/'fd').iterdir(), key=lambda p: int(p.name)):
        try:
            target = os.readlink(fd)
            if target.startswith('/'):
                out['disk_and_log_descriptors'].append(dict(fd=int(fd.name), target=target))
        except (FileNotFoundError, ProcessLookupError):
            pass
    if args.monitor:
        out['monitor'] = monitor_queries()
    out['after'] = threads(proc)
    out['process_io_after'] = read(proc/'io')
    assert (proc/'cmdline').read_bytes() == command
    assert (proc/'stat').read_text().rsplit(')', 1)[1].split()[19] == started
    out['finished_utc'] = datetime.now(timezone.utc).isoformat()
    out['scope'] = 'Read-only QEMU identity/thread/I/O diagnostic; not a timing acceptance receipt.'
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
