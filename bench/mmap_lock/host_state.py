#!/usr/bin/env python3
"""Bounded, read-only host capture; no workload, pinning, signals or retries."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import signal
import socket
import time
import sys

from host_capture_control import capture, identity, stat_fields, interrupted

SNAPSHOT = 'before-mutex-kdonly-20261017T140354Z'


def read_prompt(sock, deadline):
    data = bytearray()
    while not data.endswith(b'(qemu) '):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('total monitor deadline exceeded')
        sock.settimeout(remaining)
        block = sock.recv(65536)
        if not block:
            raise EOFError('monitor closed before prompt')
        data.extend(block)
        if len(data) > 1024 * 1024:
            raise ValueError('monitor response exceeds bound')
    return data.decode(errors='replace')


def snapshots():
    deadline = time.monotonic() + 8
    # Own only this connection. Never send quit or change monitor state.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(max(0.001, deadline - time.monotonic()))
        sock.connect('/tmp/qemu-monitor.sock')
        banner = read_prompt(sock, deadline)
        sock.settimeout(max(0.001, deadline - time.monotonic()))
        sock.sendall(b'info snapshots\n')
        return banner, read_prompt(sock, deadline)


def collect(pid, start, command_sha):
    out = dict(schema=1, passed=False, accepted=False, captured_utc=
               datetime.datetime.now(datetime.timezone.utc).isoformat(), phase='tasks')
    proc = Path('/proc') / str(pid)
    try:
        out['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        out['capture'] = capture(proc, start, command_sha)
        if not out['capture']['complete']:
            raise ValueError('incomplete QEMU capture')
        out['qemu'] = [dict(pid=pid, args=[os.fsdecode(v) for v in
            (proc / 'cmdline').read_bytes().split(b'\0') if v], tasks=out['capture']['tasks'])]
        out['phase'] = 'numa_maps'
        out['qemu'][0]['numa_maps'] = (proc / 'numa_maps').read_text()
        out['phase'] = 'host_policy'
        out['cpufreq'] = {p.name: {f: (p / f).read_text().strip() for f in
            ('scaling_driver', 'scaling_governor', 'scaling_min_freq', 'scaling_max_freq', 'affected_cpus')
            if (p / f).exists()} for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*')}
        out['numa'] = {p.name: (p / 'cpulist').read_text().strip()
                       for p in Path('/sys/devices/system/node').glob('node[0-9]*')}
        out['serial_pv_boot_lines'] = []
        with Path('/tmp/qemu-serial.log').open(errors='replace') as source:
            for line in source:
                if 'PV spinlocks disabled' in line:
                    out['serial_pv_boot_lines'].append(line.strip())
        out['phase'] = 'snapshots'
        out['monitor_banner'], out['snapshots'] = snapshots()
        out.update(recovery_snapshot=SNAPSHOT, snapshot_listed=SNAPSHOT in out['snapshots'])
        tasks = out['qemu'][0]['tasks']
        vcpu = {int(m[1]): t['affinity'] for t in tasks
                if (m := re.fullmatch(r'CPU (\d+)/KVM', t['comm']))}
        if (vcpu != {i: [i] for i in range(64)} or not out['snapshot_listed'] or
                any(t['affinity'] != [63] for t in tasks if not t['comm'].startswith('CPU '))):
            raise ValueError('vCPU/service pins or recovery snapshot differ')
        out['pins_verified'] = True
        out['phase'] = 'final_identity'
        out['final_identity'] = identity(proc, start, command_sha)
        out.update(passed=True, phase='complete')
    except BaseException as error:
        out['error'] = repr(error)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', required=True, type=int)
    p.add_argument('--start-ticks', required=True, type=int)
    p.add_argument('--cmdline-sha256', required=True)
    a = p.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    print(json.dumps(dict(host_observer_pid=os.getpid(), host_observer_start_ticks=
          stat_fields(Path('/proc/self/stat').read_text())['start_ticks'])), file=sys.stderr, flush=True)
    out = collect(a.pid, a.start_ticks, a.cmdline_sha256)
    print(json.dumps(out), flush=True)
    return int(not out['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
