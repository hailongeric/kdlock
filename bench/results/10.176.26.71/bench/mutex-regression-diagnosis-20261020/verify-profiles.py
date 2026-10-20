#!/usr/bin/env python3
"""Verify completed diagnostic sessions and immutable inputs in the idle VM."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    args = parser.parse_args()
    base, prepared = args.base.resolve(), args.prepared.resolve()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert not (base/'health.json').exists()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as runtime
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](base, runtime.idle)
    assert sha(prepared/'frozen-inputs.json') == \
        'df8b56e19893cb2e42d92bad41de8876ff4b1b6a915b2fe67336ba761a99ea73'
    assert sha(prepared/'harness-inputs.json') == \
        '8081cbed66833c59e0c58f0aa62d9f6ff87e8c28438ac7b1252584881879bf20'
    checked, harness = {}, {}
    for bundle in read(prepared/'frozen-inputs.json').values():
        for filename, digest in bundle['files'].items():
            assert sha(Path(filename)) == digest, filename
            checked[filename] = digest
    for filename, digest in read(prepared/'harness-inputs.json').items():
        retained = prepared/'harness'/Path(filename).relative_to(ROOT)
        assert sha(retained) == digest, retained
        harness[str(retained)] = digest
    result = read(base/'result.json')
    matrix = base/'matrix'
    records, plan, state = (read(matrix/(name+'.json')) for name in ('records', 'plan', 'status'))
    assert result['passed'] and result['final_idle'] and result['state'] == 'COMPLETE'
    assert state['state'] == 'COMPLETE' and state['completed'] == state['planned'] == 40
    assert len(records) == len(plan) == len(state['sessions']) == 40
    assert len({r['name'] for r in records}) == 40
    assert sha(base/'profile_replay.py') == result['script_sha256'] == \
        sha(ROOT/'bench/mutex_api_compare/profile_replay.py')
    assert sha(base/'scheduler.py') == sha(matrix/'replay-scheduler.py') == result['scheduler_sha256']
    assert sha(base/'tools/perf') == sha(Path(result['perf_source'])) == result['perf_sha256']
    spec = importlib.util.spec_from_file_location('report', ROOT/'bench/mutex_api_compare/report.py')
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    faults, retirements = [], []
    for index, (row, planned, receipt) in enumerate(zip(records, plan, state['sessions'])):
        path = Path(row['evidence_path'])
        assert path.is_relative_to(matrix/'measurements') and row == read(path/'session.json')
        assert planned['sequence'] == index and row['name'] == planned['name'] == receipt['name']
        assert all(row[k] == v for k, v in planned.items())
        assert row['drained'] and not row.get('cleanup_error')
        assert row['execution_status'] in ('OK', 'NO_JIT') and row['repeat'] == 0
        assert row['diagnostic'] and row['perf_record'] and not row['pmu'] and not row['score_eligible']
        assert not report.accepted(row), 'diagnostic must remain ineligible for throughput acceptance'
        m = row['measurement']
        synthetic = row['comparison_workload'] in ('c08', 'rcuht')
        assert (m['complete'] and m['data_ok']) if synthetic else m['ok']
        assert len(m['workers']) == row['threads']
        assert [w['cpu'] for w in m['workers']] == row['cpus']
        assert all(w['completed'] > 0 and w['error'] == 0 and
                   w['observed_cpu'] == w['cpu'] for w in m['workers'])
        assert sum(w['completed'] for w in m['workers']) == m['completed'] > 0
        assert m['wall_ns'] > 0
        if row['arm'] == 'kdlock':
            assert row['retired'] == dict(state=2, modules=0, writers=0, frames=0)
            assert row['published_before'] == row['published_after']
            assert 0 <= row['jit_bodies'] <= m['completed']
            if not synthetic:
                assert 0 <= row['jit_completions'] <= row['jit_bodies']
            retirements.append(dict(name=row['name'], retired=row['retired']))
        for name in ('perf.data', 'perf-samples.txt', 'perf-report.txt', 'kallsyms', 'modules'):
            assert (path/name).stat().st_size > 0
        if not synthetic:
            assert row['perf_exit_code'] == 0 and row['perf_control_acks'] == ['enable', 'disable', 'stop']
        for line in (path/'kernel.log').read_text().splitlines():
            if runtime.FAULT.search(line):
                faults.append(dict(name=row['name'], line=line))
    assert not faults
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot == read(matrix/'environment.json')['boot_id'] == read(prepared/'matrix/environment.json')['boot_id']
    shutil.copyfile(Path(__file__), base/'verify-profiles.py')
    reference = Path(str(prepared)+'-archives')/'archives.json'
    shutil.copyfile(reference, base/'original-archives.json')
    health = dict(idle=True, boot_id=boot, checked_unix=time.time(), sessions=40,
        functionally_valid=40, drained=40, score_eligible=0,
        execution_statuses=dict(Counter(r['execution_status'] for r in records)),
        execution_classes=dict(Counter(report.execution_class(r) for r in records)),
        exact_retirements=retirements, per_session_kernel_faults=faults,
        original_frozen_files_checked=len(checked), retained_harness_files_checked=len(harness),
        verified_original_files=checked, verified_retained_harness=harness,
        original_archives_manifest_sha256=sha(reference), verifier_sha256=sha(Path(__file__)),
        perf_sample_validity='Pending independent loss, event, timestamp and attribution review',
        scope='Diagnostic functional/retirement and immutable-input proof; no performance acceptance.')
    with (base/'health.json').open('x') as stream:
        json.dump(health, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in health.items() if k not in
        ('verified_original_files', 'verified_retained_harness', 'exact_retirements')}))


if __name__ == '__main__':
    main()
