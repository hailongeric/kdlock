#!/usr/bin/env python3
"""Capture a drained workload endpoint and publish its retained receipt table."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import tarfile

from plan import GUEST
from report import render

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'bench/results/10.176.26.71/raw/bench/catalog-single-20261026'
REPORT = ROOT / 'bench/results/10.176.26.71/bench/catalog-single-20261026'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
       '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2']


def capture(name):
    script = ROOT / 'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py'
    result = subprocess.run([*SSH, 'eric@10.176.26.71', 'timeout 45 sudo -n python3 -'],
                            input=script.read_bytes(), capture_output=True, timeout=60)
    (RAW / (name + '-host.json')).write_bytes(result.stdout)
    (RAW / (name + '-host.stderr')).write_bytes(result.stderr)
    result.check_returncode()
    return json.loads(result.stdout)


def compare(before, after):
    issues = []
    for key in ('cpufreq', 'numa', 'recovery_snapshot'):
        if before[key] != after[key]:
            issues.append(key + ' changed')
    if not after.get('pins_verified') or not after.get('snapshot_listed'):
        issues.append('placement/snapshot verification missing')
    if len(before['qemu']) != 1 or len(after['qemu']) != 1:
        return issues + ['not exactly one QEMU process']
    b, a = before['qemu'][0], after['qemu'][0]
    for key in ('pid', 'args'):
        if b[key] != a[key]:
            issues.append('QEMU ' + key + ' changed')
    if sorted(b['tasks'], key=lambda t: t['tid']) != sorted(a['tasks'], key=lambda t: t['tid']):
        issues.append(f"QEMU tasks changed: {len(b['tasks'])} -> {len(a['tasks'])}")
    def bindings(q):
        return [(f[0], f[1], next((v for v in f if v.startswith('kernelpagesize_kB=')), None))
                for line in q['numa_maps'].splitlines()
                if len(f := line.split()) > 1 and f[1].startswith('bind:')]
    if not bindings(b) or bindings(b) != bindings(a):
        issues.append('NUMA memory binding changed')
    return issues


def collect(name):
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):
        raise ValueError('invalid workload name')
    after = capture(name)
    before = json.loads((RAW / 'host-before.json').read_text())
    issues = compare(before, after)
    source = RAW / name
    source.mkdir(exist_ok=False)
    files = ['plan.json', 'records.json', 'summary.json', 'environment.json',
             'source-sha256.json', 'binary-sha256.json']
    command = f'timeout 30 tar -C {GUEST}/{name} -cf - ' + ' '.join(files)
    result = subprocess.run([*SSH, '-p', '2222', 'root@10.176.26.71', command],
                            capture_output=True, timeout=45)
    (source / 'receipts.tar').write_bytes(result.stdout)
    (source / 'transfer.stderr').write_bytes(result.stderr)
    result.check_returncode()
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        for member in archive:
            if member.name not in files or not member.isfile():
                raise ValueError('unexpected receipt member')
            (source / member.name).write_bytes(archive.extractfile(member).read())
    qualification = dict(host_endpoints_passed=not issues, issues=issues,
                         baseline_tasks=len(before['qemu'][0]['tasks']),
                         endpoint_tasks=len(after['qemu'][0]['tasks']),
                         scope='Whole-workload host endpoints, not continuous observation')
    (source / 'qualification.json').write_text(json.dumps(qualification, indent=2) + '\n')
    rows = render(source, REPORT / name, name, not issues)
    print(json.dumps(dict(workload=name, measured=sum(r['whole_mops_s'] is not None for r in rows),
                         planned=len(rows), **qualification), indent=2), flush=True)
    return not issues


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workload')
    args = parser.parse_args()
    raise SystemExit(0 if collect(args.workload) else 2)
