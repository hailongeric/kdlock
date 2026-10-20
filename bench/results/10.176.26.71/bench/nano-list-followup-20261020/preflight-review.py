#!/usr/bin/env python3
"""Read the failed list preflight archive without executing its captured code."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

p = argparse.ArgumentParser(description=__doc__)
for name in ('repo', 'raw', 'report'):
    p.add_argument('--'+name, type=Path, required=True)
p.add_argument('--rwsem-only', action='store_true')
args = p.parse_args()
assert socket.gethostname() == '380G10' and not args.report.exists()
sys.dont_write_bytecode = True
helper = args.repo/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest() == \
    '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
spec = importlib.util.spec_from_file_location('inert_failed_preflight', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
a = module.Audit(SimpleNamespace(**vars(args)))
groups, links = a.load_archives()
result, health, manifest, plan = (a.jread(n+'.json') for n in
                                ('result', 'health', 'committed-source', 'task-plan'))
a.check(result['passed'] is False and result['measured_sessions'] == 0 and
        result['error'] == "ValueError('replay QEMU thread placement differs')",
        'original_admission_failure')
a.check(health['idle'] and health['preflight_passed'] is False and
        health['timing_output_absent'] and health['measured_sessions'] == 0 and
        health['result_sha256'] == a.files['result.json'], 'idle_zero_session_receipt')
a.check(manifest['commit'] == plan['source_commit'] == result['source_commit'] ==
        'f48b90e42e1538a5204d215b573a238ebd95f391' and
        len(manifest['files']) == health['unchanged_source_hashes'] == 497, 'source_identity')
for path, digest in manifest['files'].items():
    a.check(module.sha(a.git_bytes(manifest['commit'], path)) == digest, 'committed_git_source', path)
a.check(a.files['preflight.py'] == result['script_sha256'] and
        a.files['committed-source.json'] == plan['source_manifest_sha256'] and
        a.files['historical-plan.json'] == plan['historical_plan_sha256'] and
        plan['phases']['timing'] == (a.jread('historical-plan.json')['phases']['timing'][-1:]
                                   if args.rwsem_only else a.jread('historical-plan.json')['phases']['timing']),
        'unchanged_preflight_inputs')
host = a.jread('host-state.json')
assert len(host['qemu']) == 1
qemu = host['qemu'][0]
cpu_threads = [t for t in qemu['tasks'] if t['comm'].startswith('CPU ')]
if args.rwsem_only:
    a.check(a.files['reference-host-state.json'] ==
            '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a',
            'original_reference_hash')
    original = a.jread('reference-host-state.json')['qemu'][0]
    original_tids = {t['tid'] for t in original['tasks']}
    extras = [t for t in qemu['tasks'] if t['tid'] not in original_tids]
    a.check([t for t in qemu['tasks'] if t['tid'] in original_tids] == original['tasks']
            and qemu['args'] == original['args'] and result['rwsem_only'] is True and
            len(plan['phases']['timing']) == 1 and
            plan['phases']['timing'][0]['name'] == 'rwsem-w20' and
            plan['phases']['timing'][0]['expected_sessions'] == 48,
            'original_thread_identity_and_rwsem_selection')
else:
    extras = [t for t in qemu['tasks'] if t['tid'] in (421142, 421144, 421145)]
a.check(len(qemu['tasks']) == health['qemu_threads'] == (73 if args.rwsem_only else 70) and
        qemu['pid'] == 257489 and
        len(cpu_threads) == 64 and len(extras) == (6 if args.rwsem_only else 3) and
        all(t['comm'] == 'worker' and t['affinity'] == [63] for t in extras),
        'retained_extra_worker_threads')
a.check(host['snapshot_listed'] and host['pins_verified'] and
        health['boot_id'] == a.jread('environment.json')['boot_id'] == a.archive['boot_id'],
        'guest_host_identity')
output = dict(consistent=not a.issues, issues=a.issues, checks=sum(a.counts.values()),
    check_counts=dict(a.counts), groups=groups, files=len(a.files), symlinks=len(links),
    scope='Preservation PASS; original preflight remains FAILED with zero timing sessions.',
    extra_threads=extras, script_sha256=module.hashfile(Path(__file__)),
    archives_manifest_sha256=module.hashfile(args.raw/'archives.json'),
    regular_file_hash_map_sha256=module.canonical(a.files))
assert not a.issues, a.issues
args.report.mkdir(parents=True)
for name in ('result.json', 'health.json', 'host-state.json'):
    (args.report/name).write_bytes(a.contents[name])
(args.report/'archives.json').write_bytes((args.raw/'archives.json').read_bytes())
(args.report/'offline-review.json').write_text(json.dumps(output, indent=2, sort_keys=True)+'\n')
print(json.dumps({k: output[k] for k in
                 ('consistent', 'issues', 'checks', 'archives_manifest_sha256')}, sort_keys=True))
