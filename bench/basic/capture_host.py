#!/usr/bin/env python3
"""Capture a verified host reference for Linux 7 functional checks; no timing qualification.

Run as root on the QEMU host. This reads placement, frequency and the actual
monitor snapshot list; it neither creates a snapshot nor changes host policy.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import time

SCHEMA = 2
KIND = 'kdlock-linux70-functional-host'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def cpus(text):
    result = []
    for item in text.replace(',', ' ').split():
        first, separator, last = item.partition('-')
        result.extend(range(int(first), int(last) + 1) if separator else [int(first)])
    require(len(result) == len(set(result)), 'duplicate CPU in list')
    return sorted(result)


def start_ticks(path):
    # Task comm may contain spaces and parentheses; field 22 follows its last ')'.
    return int(path.read_text().rsplit(')', 1)[1].split()[19])


def memory_bindings(qemu):
    rows = []
    for line in qemu['numa_maps'].splitlines():
        fields = line.split()
        if len(fields) < 2 or not fields[1].startswith('bind:'):
            continue
        values = dict(field.split('=', 1) for field in fields[2:] if '=' in field)
        rows.append((fields[0], fields[1], int(values['kernelpagesize_kB'])))
    require(rows and {row[1] for row in rows} == {'bind:0', 'bind:1'},
            'actual memory bindings for both host NUMA nodes required')
    return sorted(rows)


def option_values(args, option):
    return [args[index + 1] for index, value in enumerate(args[:-1]) if value == option]


def validate(host):
    require(host.get('schema') == SCHEMA and host.get('capture_kind') == KIND,
            'fresh Linux 7 host capture format required')
    require(bool(host.get('host_boot_id')), 'host boot identity required')
    require(len(host['qemu']) == 1, 'one QEMU process required')
    qemu = host['qemu'][0]
    require(qemu['pid'] > 0 and qemu['start_ticks'] > 0 and
            Path(qemu['args'][0]).name == 'qemu-system-x86_64', 'QEMU identity missing')
    tasks = qemu['tasks']
    require(len({row['tid'] for row in tasks}) == len(tasks) and
            all(row['start_ticks'] > 0 for row in tasks), 'distinct task identities required')
    vcpus = []
    for row in tasks:
        match = re.fullmatch(r'CPU (\d+)/KVM', row['comm'])
        if match:
            vcpus.append((int(match[1]), row['affinity']))
        else:
            require(row['affinity'] == [63], 'auxiliary QEMU task must stay on CPU 63')
    require(sorted(vcpus) == [(cpu, [cpu]) for cpu in range(64)],
            '64 distinct vCPUs pinned to matching host CPUs required')
    require({key: cpus(value) for key, value in host['numa'].items()} ==
            {'node0': list(range(32)), 'node1': list(range(32, 64))},
            'host NUMA CPU topology differs')
    require(option_values(qemu['args'], '-smp') == ['64,maxcpus=64,sockets=2,cores=32,threads=1']
            and option_values(qemu['args'], '-m') == ['24G'], 'QEMU CPU/memory topology differs')
    backends = [value for value in option_values(qemu['args'], '-object')
                if value.startswith('memory-backend-')]
    require(sorted(backends) == [
        'memory-backend-ram,id=mem0,size=12G,host-nodes=0,policy=bind',
        'memory-backend-ram,id=mem1,size=12G,host-nodes=1,policy=bind'],
        'two bound 12 GiB memory backends required')
    require(sorted(option_values(qemu['args'], '-numa')) == [
        'node,nodeid=0,cpus=0-31,memdev=mem0', 'node,nodeid=1,cpus=32-63,memdev=mem1'],
        'guest NUMA memory/CPU bindings differ')
    memory_bindings(qemu)
    policies = host['cpufreq']
    require(set(policies) == {f'policy{cpu}' for cpu in range(64)}, '64 CPU frequency policies required')
    for cpu in range(64):
        row = policies[f'policy{cpu}']
        require(row['scaling_driver'] and row['scaling_governor'] == 'performance' and
                row['scaling_min_freq'] == row['scaling_max_freq'] == '2000000' and
                cpus(row['affected_cpus']) == [cpu], 'fixed 2.0 GHz policy differs: ' + str(cpu))
    require(host['no_turbo'] == '1', 'intel_pstate/no_turbo must remain enabled')
    tag = host['recovery_snapshot']
    require(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', tag)), 'invalid snapshot tag')
    names = snapshot_names(host['snapshots'])
    require(host['snapshot_listed'] is True and names.count(tag) == 1,
            'selected snapshot must appear exactly once in the actual monitor table')
    require(any(value.startswith('unix:' + host['monitor_path'] + ',')
                for value in option_values(qemu['args'], '-monitor')), 'monitor path differs from QEMU')


def snapshot_names(text):
    # Match table columns, not a substring in a banner, error or command echo.
    # QEMU prints '--' when a common snapshot tag has different per-disk IDs.
    return [match[1] for line in text.splitlines()
            if (match := re.match(r'^\s*(?:\d+|--)\s+(\S+)\s+\d', line))]


def read_prompt(connection, deadline):
    data = bytearray()
    while not data.endswith(b'(qemu) '):
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'monitor response deadline expired')
        connection.settimeout(remaining)
        block = connection.recv(65536)
        require(bool(block), 'monitor closed before its prompt')
        data.extend(block)
        require(len(data) <= 2 * 1024 * 1024, 'monitor response exceeds capture bound')
    return data.decode(errors='replace')


def qemu_capture(proc):
    before = start_ticks(proc / 'stat')
    command = (proc / 'cmdline').read_bytes()
    tasks = []
    tids = sorted(int(path.name) for path in (proc / 'task').iterdir())
    for tid in tids:
        task = proc / 'task' / str(tid)
        started = start_ticks(task / 'stat')
        tasks.append(dict(tid=tid, start_ticks=started, comm=(task / 'comm').read_text().strip(),
                          affinity=sorted(os.sched_getaffinity(tid))))
        require(start_ticks(task / 'stat') == started, 'QEMU task identity changed during capture')
    require(tids == sorted(int(path.name) for path in (proc / 'task').iterdir()),
            'QEMU task list changed during capture; take a fresh capture')
    result = dict(pid=int(proc.name), start_ticks=before,
                  args=[os.fsdecode(arg) for arg in command.split(b'\0') if arg],
                  tasks=tasks, numa_maps=(proc / 'numa_maps').read_text())
    require(start_ticks(proc / 'stat') == before and (proc / 'cmdline').read_bytes() == command,
            'QEMU process identity changed during capture')
    return result


def capture(snapshot, monitor):
    require(os.geteuid() == 0, 'run as root on the QEMU host')
    candidates = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            executable = (proc / 'cmdline').read_bytes().split(b'\0')[0]
        except FileNotFoundError:
            continue
        if executable and Path(os.fsdecode(executable)).name == 'qemu-system-x86_64':
            candidates.append(proc)
    require(len(candidates) == 1, 'one QEMU process required')
    host = dict(schema=SCHEMA, capture_kind=KIND,
                captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                capture_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                qemu=[qemu_capture(candidates[0])], monitor_path=str(monitor))
    fields = ('scaling_driver', 'scaling_governor', 'scaling_min_freq', 'scaling_max_freq', 'affected_cpus')
    host['cpufreq'] = {path.name: {field: (path / field).read_text().strip() for field in fields}
                       for path in Path('/sys/devices/system/cpu/cpufreq').glob('policy*')}
    host['no_turbo'] = Path('/sys/devices/system/cpu/intel_pstate/no_turbo').read_text().strip()
    host['numa'] = {path.name: (path / 'cpulist').read_text().strip()
                    for path in Path('/sys/devices/system/node').glob('node[0-9]*')}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(8)
        connection.connect(str(monitor))
        deadline = time.monotonic() + 8
        host['monitor_banner'] = read_prompt(connection, deadline)
        connection.sendall(b'info snapshots\n')
        host['snapshots'] = read_prompt(connection, deadline)
    host['recovery_snapshot'] = snapshot
    host['snapshot_listed'] = snapshot_names(host['snapshots']).count(snapshot) == 1
    after = qemu_capture(candidates[0])
    require(all(after[key] == host['qemu'][0][key] for key in ('pid', 'start_ticks', 'args', 'tasks')),
            'QEMU process/task identities or placement changed across monitor observation')
    require(memory_bindings(after) == memory_bindings(host['qemu'][0]),
            'QEMU memory bindings changed across monitor observation')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == host['host_boot_id'],
            'host boot changed across capture')
    validate(host)
    host.update(pins_verified=True, frequency_verified=True, performance_accepted=False,
                scope='Read-only functional admission evidence; configured frequency is not effective-frequency proof. '
                      'Host observations do not establish the guest kernel identity or exclude intervening task lifetimes.')
    return host


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--monitor', type=Path, default=Path('/tmp/qemu-monitor.sock'))
    args = parser.parse_args()
    print(json.dumps(capture(args.snapshot, args.monitor), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
