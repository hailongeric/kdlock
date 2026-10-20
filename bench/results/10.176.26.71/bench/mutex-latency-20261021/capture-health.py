#!/usr/bin/env python3
"""Read completed diagnostic receipts and verify idle before archival in the VM."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-latency-20261021')
ROOT = Path('/root/host_fs/kdlock')
INPUT_SHA = '5c83db1396330baef1f1ffa553d5bbb1e22e72afd2b94f5e93f87de4a22a6137'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == 'b65f0205-c8f9-4385-8b13-039cbce243a6'
    assert not Path(__file__).resolve().is_relative_to(ROOT)
    tools = BASE/'inputs-4/tools'
    scheduler = load(tools/'scheduler.py', 'latency_health_scheduler')
    scheduler.ROOT = ROOT
    prepare = load(tools/'latency_inputs.py', 'latency_health_inputs')
    inputs, original, harness = prepare.validate(scheduler, BASE/'inputs-4/inputs.json', INPUT_SHA)
    syn, _, _, _ = scheduler.runners(prepare.ORIGINAL/'harness', harness)
    archive = load(tools/'archive_run.py', 'latency_health_archive')
    archive.idle(BASE, syn.idle)
    state = read(BASE/'run-2/status.json')
    assert state['state'] == 'COMPLETE' and state['complete'] and state['completed'] == state['planned'] == 252
    records = read(BASE/'run-2/records.json')
    assert len(records) == len(state['sessions']) == 252
    faults, retirements = [], []
    pattern = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|unable to handle|'
                         r'general protection fault|Oops:|\[ERROR\]|invariant_failures=[1-9]|'
                         r'runtime error:|KASAN:|UBSAN:|scheduling while atomic', re.I)
    sampled, disabled, observations = 0, 0, 0
    insufficient = []
    for row in records:
        folder = Path(row['evidence_path'])
        assert folder.is_relative_to(BASE/'run-2') and read(folder/'session.json') == row
        assert row['execution_status'] == 'OK' and row['drained'] and not row.get('cleanup_error')
        if pattern.search((folder/'kernel.log').read_text()):
            faults.append(row['name'])
        if row['arm'] == 'kdlock':
            assert row['retired'] == dict(state=2, modules=0, writers=0, frames=0)
            retirements.append(dict(name=row['name'], retired=row['retired']))
        if row['latency_mode'] != 'plain':
            observation = read(folder/'latency.json')
            assert observation['summary'] == row['operation_latency']
            if row['latency_mode'] == 'sampled':
                sampled += 1
                observations += observation['summary']['samples']
                if not observation['summary']['sufficient']:
                    insufficient.append(row['name'])
            else:
                disabled += 1
                assert observation['summary']['samples'] == 0
    assert sampled == disabled == 84 and len(retirements) == 126 and not faults
    failed_state = read(BASE/'run-1/status.json')
    assert failed_state['state'] == 'FAILED' and failed_state['completed'] == 8
    failed = Path(read(BASE/'run-1/current.json')['evidence_path'])
    assert read(failed/'session.json')['drained']
    for row in read(BASE/'run-1/records.json'):
        assert row['execution_status'] == 'OK' and row['drained']
    archive.idle(BASE, syn.idle)
    original_host = read(prepare.ORIGINAL/'matrix/host-state.json')
    host_results = {}
    for run in ('run-1', 'run-2'):
        host = read(BASE/run/'host-after.json')
        expected = sorted(original_host['qemu'][0]['tasks'], key=lambda t: t['tid'])
        actual = sorted(host['qemu'][0]['tasks'], key=lambda t: t['tid'])
        host_results[run] = dict(captured_utc=host['captured_utc'],
            original_threads=len(expected), actual_threads=len(actual), exact_match=actual == expected)
    result = dict(idle=True, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        kernel_release=os.uname().release, finished_ns=time.time_ns(), sessions=252, drained=252,
        exact_retirements=retirements, per_session_kernel_faults=faults, sampled_sessions=sampled,
        disabled_sessions=disabled, observations=observations, insufficient_sampled_sessions=insufficient,
        failed_original_run=dict(completed_sessions=8, failed_attempt=9, drained=True,
                                 rejected_raw_samples_retained=False),
        host_endpoints=host_results, inputs_sha256=INPUT_SHA,
        original_bundle_files=sum(len(v['files']) for v in original.values()), retained_harness_files=len(harness),
        derived_immutable_files=len(inputs['immutable_files']),
        source_script_sha256=sha(Path(__file__)), accepted=False)
    target = BASE/'final-health.json'
    assert not target.exists()
    target.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'exact_retirements'}, indent=2))


if __name__ == '__main__':
    main()
