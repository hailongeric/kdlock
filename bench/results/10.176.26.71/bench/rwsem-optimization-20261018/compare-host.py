#!/usr/bin/env python3
"""Read-only comparison of captured QEMU placement and frequency policy."""
import argparse
import hashlib
import json
from pathlib import Path
import re


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('before', type=Path)
parser.add_argument('after', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
assert not args.output.exists()
captures = [json.loads(path.read_text()) for path in (args.before, args.after)]
checks = {}
for label, capture in zip(('before', 'after'), captures):
    checks[label + '_one_vm'] = len(capture['qemu']) == 1
    vm = capture['qemu'][0]
    cpus = {}
    services = []
    for task in vm['tasks']:
        match = re.fullmatch(r'CPU (\d+)/KVM', task['comm'])
        if match:
            cpu = int(match.group(1))
            assert cpu not in cpus
            cpus[cpu] = task['affinity']
        else:
            services.append(task['affinity'])
    checks[label + '_64_matching_vcpu_pins'] = cpus == {n: [n] for n in range(64)}
    checks[label + '_service_cpu_63'] = bool(services) and all(p == [63] for p in services)
checks['same_vm_pid'] = captures[0]['qemu'][0]['pid'] == captures[1]['qemu'][0]['pid']
checks['same_vm_arguments'] = captures[0]['qemu'][0]['args'] == captures[1]['qemu'][0]['args']
checks['same_frequency_policy'] = captures[0]['frequency_policies'] == captures[1]['frequency_policies']
receipt = dict(passed=all(checks.values()), checks=checks,
    input_sha256={label: hashlib.sha256(path.read_bytes()).hexdigest()
        for label, path in zip(('before', 'after'), (args.before, args.after))},
    frequency_policies=captures[1]['frequency_policies'],
    scope='Read-only offline comparison of before/after captures; no host tuning or timing test.',
    limitation='Matching frequency policy does not prove equal effective frequencies or load during measurements.')
args.output.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(passed=receipt['passed'], checks=checks)))
raise SystemExit(0 if receipt['passed'] else 1)
