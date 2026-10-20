#!/usr/bin/env python3
"""Verify completed pipecap evidence and actual VM idle before preservation."""
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/pipecap-causal-20261021')
ORIGINAL = BASE.parent/'mutex-public-20261020-r2'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot == 'b65f0205-c8f9-4385-8b13-039cbce243a6'
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as runtime
    archive = load(ROOT/'bench/archive_run.py', 'pipecap_health_archive')
    archive.idle(BASE, runtime.idle)
    original_files, harness = {}, {}
    for bundle in read(ORIGINAL/'frozen-inputs.json').values():
        for name, digest in bundle['files'].items():
            assert sha(Path(name)) == digest, name
            assert name not in original_files or original_files[name] == digest
            original_files[name] = digest
    for name, digest in read(ORIGINAL/'harness-inputs.json').items():
        retained = ORIGINAL/'harness'/Path(name).relative_to(ROOT)
        assert sha(retained) == digest, str(retained)
        harness[str(retained)] = digest
    runs, faults = {}, []
    for name in ('run-1', 'run-2'):
        base = BASE/name
        result, state = read(base/'result.json'), read(base/'matrix/status.json')
        records, plan = read(base/'matrix/records.json'), read(base/'matrix/plan.json')
        assert len(records) == len(plan) == 48
        assert result['accepted'] is False
        for tool, digest in read(base/'tool-sha256.json').items():
            assert sha(base/'tools'/tool) == digest
        assert sha(base/'tools/perf') == result['perf_sha256']
        retirements, completed = [], []
        for row, spec in zip(records, plan):
            assert all(row.get(k) == v for k, v in spec.items()), row['name']
            if row['execution_status'] == 'NOT_RUN':
                continue
            folder = Path(row['evidence_path'])
            assert folder.is_relative_to(base/'matrix/measurements')
            assert read(folder/'session.json') == row
            assert row['drained'] and not row.get('cleanup_error'), row['name']
            if row['arm'] == 'kdlock':
                assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0)
                retirements.append(dict(name=row['name'], retired=row['retired']))
            for line in (folder/'kernel.log').read_text().splitlines():
                if runtime.FAULT.search(line):
                    faults.append(dict(name=row['name'], line=line))
            if row['execution_status'] not in ('OK', 'NO_JIT'):
                continue
            assert row['measurement']['ok']
            assert row['redirected_calls'] == row['measurement']['completed']
            if row['route_snapshot']:
                observed = read(folder/'route-snapshots.json')
                assert observed['delta'] == row['route_delta']
                assert observed['before']['timing_enabled'] == row['inclusive_jit_timing']
                assert observed['after']['timing_enabled'] == row['inclusive_jit_timing']
            completed.append(row['name'])
        if name == 'run-1':
            assert result['state'] == 'FAILED' and len(completed) == 6
            assert Counter(r['execution_status'] for r in records) == {
                'OK': 6, 'PREPARATION_FAILED': 1, 'NOT_RUN': 41}
        else:
            assert result['state'] == state['state'] == 'COMPLETE'
            assert result['final_idle'] and len(completed) == 48
        runs[name] = dict(state=result['state'], completed=len(completed),
            statuses=dict(Counter(r['execution_status'] for r in records)),
            exact_retirements=retirements, source_commit=result['source_commit'])
    assert not faults, faults
    checks = {}
    for name in ('checks-1', 'checks-2'):
        result = read(BASE/name/'result.json')
        assert result['passed'] and result['final_idle'] and result['source_unchanged']
        for path, digest in read(BASE/name/'source-sha256.json').items():
            assert sha(BASE/name/'source'/path) == digest
        checks[name] = result
    archive.idle(BASE, runtime.idle)
    answer = dict(idle=True, boot_id=boot, kernel_release=os.uname().release,
        finished_ns=time.time_ns(), runs=runs, checks=checks,
        per_session_kernel_faults=faults, verified_original_files=original_files,
        verified_retained_harness=harness, source_sha256=sha(Path(__file__)),
        accepted=False, limits='Functional preservation only; host endpoints and causal attribution remain separate.')
    with (BASE/'final-health.json').open('x') as stream:
        json.dump(answer, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(idle=True, runs=runs, original_files=len(original_files),
                         harness_files=len(harness), accepted=False)))


if __name__ == '__main__':
    main()
