#!/usr/bin/env python3
"""Verify a completed isolated-provider matrix without hiding environment gaps."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time

ROOT = Path('/root/host_fs/kdlock')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    base, original, candidate_dir = args.base.resolve(), args.prepared.resolve(), args.candidate.resolve()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert not (base/'health.json').exists()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](base, rt.idle)
    scheduler = module('scheduler', ROOT/'bench/mutex_api_compare/run.py')
    validator = module('candidate', ROOT/'bench/mutex_api_compare/entry_candidate.py')
    report = module('comparison_report', ROOT/'bench/mutex_api_compare/report.py')
    candidate = validator.candidate_inputs(
        scheduler, original, candidate_dir/'candidate.json',
        'd8b5b56daa3110cf3e276ca8c2198c2b05eda1bd79630210142163f57bc8f9ac')
    matrix = base/'matrix'
    assert sha(matrix/'candidate.json') == candidate['manifest_sha256']
    assert sha(matrix/'replay-scheduler.py') == sha(Path(scheduler.__file__))
    records, plan, status = (read(matrix/(name+'.json')) for name in ('records', 'plan', 'status'))
    assert status['state'] == 'COMPLETE' and status['completed'] == status['planned'] == 120
    assert len(records) == len(plan) == len(status['sessions']) == 120
    assert len({r['name'] for r in records}) == 120
    assert read(matrix/'execution-order.json') == [list(r) for r in scheduler.replay_order()]
    frozen = read(original/'frozen-inputs.json')
    original_count = sum(len(v['files']) for v in frozen.values())
    frozen.update(candidate['bundles'])
    faults, retired, candidate_sessions = [], [], []
    for index, (row, spec, receipt) in enumerate(zip(records, plan, status['sessions'])):
        assert spec['sequence'] == index and all(row[k] == v for k, v in spec.items())
        assert row['name'] == receipt['name']
        path = Path(row['evidence_path'])
        assert row == read(path/'session.json') and path.is_relative_to(matrix/'measurements')
        key = scheduler.bundle_key(row['comparison_workload'], row['comparison_arm'], candidate)
        inputs = frozen[key]
        assert row['source_identity'] == inputs['source_identity']
        assert path == matrix/'measurements'/key/row['name']
        if row['comparison_arm'] == 'public-kd':
            assert row['provider_sha256'] == candidate['provider_sha256']
            assert row['provider_candidate'] == candidate['manifest_sha256']
            candidate_sessions.append(row['name'])
        else:
            assert 'provider_candidate' not in row and key.startswith(('current/', 'baseline/'))
        assert row['execution_status'] in ('OK', 'NO_JIT') and row['drained']
        assert not row.get('cleanup_error')
        assert not any(row.get(k) for k in ('perf_record', 'pmu', 'diagnostic'))
        m = row['measurement']
        synthetic = row['comparison_workload'] in ('c08', 'rcuht')
        assert (m['complete'] and m['data_ok']) if synthetic else m['ok']
        assert len(m['workers']) == row['threads']
        assert [w['cpu'] for w in m['workers']] == row['cpus']
        assert all(w['completed'] > 0 and w['error'] == 0 and w['observed_cpu'] == w['cpu']
                   for w in m['workers'])
        assert sum(w['completed'] for w in m['workers']) == m['completed'] > 0
        assert m['wall_ns'] > 0
        if row['arm'] == 'kdlock':
            assert row['retired'] == dict(state=2, modules=0, writers=0, frames=0)
            assert row['published_before'] == row['published_after']
            assert 0 <= row['jit_bodies'] <= m['completed']
            if not synthetic:
                assert 0 <= row['jit_completions'] <= row['jit_bodies']
            retired.append(dict(name=row['name'], retired=row['retired']))
        for line in (path/'kernel.log').read_text().splitlines():
            if rt.FAULT.search(line):
                faults.append(dict(name=row['name'], line=line))
    assert len(candidate_sessions) == 30 and len(retired) == 60 and not faults
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot == read(matrix/'environment.json')['boot_id'] == read(original/'matrix/environment.json')['boot_id']
    endpoints = {}
    for endpoint in ('before', 'after'):
        try:
            comparison = scheduler.same_environment(
                read(original/'matrix/host-state.json'), read(base/('host-'+endpoint+'.json')),
                read(original/'matrix/environment.json'), read(matrix/'environment.json'),
                read(original/'matrix/topology.json'), read(matrix/'topology.json'))
            endpoints[endpoint] = dict(passed=True, comparison=comparison)
        except ValueError as error:
            endpoints[endpoint] = dict(passed=False, error=str(error))
    assert endpoints['before']['passed']
    for path, name in ((Path(__file__), 'verify-inline-run.py'),
                       (Path(str(original)+'-archives')/'archives.json', 'original-archives.json'),
                       (Path(str(candidate_dir)+'-archives')/'archives.json', 'candidate-archives.json')):
        shutil.copyfile(path, base/name)
    health = dict(idle=True, boot_id=boot, checked_unix=time.time(), sessions=120,
                  functionally_valid=120, score_eligible=sum(report.accepted(r) for r in records),
                  original_input_files=original_count,
                  candidate_immutable_files=len(candidate['immutable_files']),
                  candidate_sessions=candidate_sessions, candidate_provider_sha256=candidate['provider_sha256'],
                  classes=dict(Counter(report.execution_class(r) for r in records)),
                  exact_retirements=retired, per_session_kernel_faults=faults,
                  host_endpoints=endpoints, within_run_host_interference='UNMEASURED',
                  p95_latency='UNMEASURED', overall_acceptance='OPEN',
                  script_sha256=sha(Path(__file__)))
    (base/'health.json').write_text(json.dumps(health, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: health[k] for k in ('idle', 'sessions', 'functionally_valid',
                                           'score_eligible', 'classes', 'overall_acceptance')}))


if __name__ == '__main__':
    main()
