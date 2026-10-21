#!/usr/bin/env python3
"""Check the completed serial follow-up and exact original inputs in the VM."""
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-recovery-followup-20261021')
ORIGINAL = BASE.parent/'mutex-public-20261020-r2'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    sys.dont_write_bytecode = True
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    transition = read(BASE/'transition-1/result.json')
    assert boot == transition['new_boot_id'] and transition['passed']
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as runtime
    spec = importlib.util.spec_from_file_location('followup_archive', ROOT/'bench/archive_run.py')
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
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
    result = read(BASE/'run-1/result.json')
    matrix = BASE/'run-1/matrix'
    state, plan, records = (read(matrix/(name+'.json')) for name in ('status', 'plan', 'records'))
    assert result['state'] == state['state'] == 'COMPLETE'
    assert result['passed'] and result['final_idle'] and result['accepted'] is False
    assert state['completed'] == state['planned'] == len(plan) == len(records) == 84
    retirements, faults, classes = [], [], Counter()
    operations = entries = returns = 0
    for row, expected in zip(records, plan):
        assert all(row.get(k) == v for k, v in expected.items()), row['name']
        folder = Path(row['evidence_path'])
        assert folder.is_relative_to(matrix/'measurements')
        assert read(folder/'session.json') == row
        assert row['execution_status'] == 'OK' and row['drained'] and not row.get('cleanup_error')
        m = row['measurement']
        synthetic = row['comparison_workload'] in ('c08', 'rcuht')
        assert (m['complete'] and m['data_ok']) if synthetic else m['ok']
        assert len(m['workers']) == row['threads']
        assert [w['cpu'] for w in m['workers']] == row['cpus']
        assert sum(w['completed'] for w in m['workers']) == m['completed']
        assert all(w['completed'] > 0 and not w['error'] and w['observed_cpu'] == w['cpu']
                   for w in m['workers'])
        operations += m['completed']
        evidence = 'NOT_APPLICABLE'
        if row['arm'] == 'kdlock':
            assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0)
            retirements.append(dict(name=row['name'], retired=row['retired']))
            assert row['published_before'] == row['published_after']
            assert 0 <= row['jit_bodies'] <= m['completed']
            entries += row['jit_bodies']
            if synthetic:
                evidence = 'WITNESSED_JIT' if row['jit_bodies'] else 'NO_JIT'
            else:
                assert 0 <= row['jit_completions'] <= row['jit_bodies']
                returns += row['jit_completions']
                evidence = ('RETURNED_JIT' if row['jit_completions'] else
                            'PARTIAL_JIT' if row['jit_bodies'] else 'NO_JIT')
        classes[evidence] += 1
        faults.extend(dict(name=row['name'], line=line) for line in
                      (folder/'kernel.log').read_text().splitlines() if runtime.FAULT.search(line))
    assert not faults
    checks = read(BASE/'checks-1/result.json')
    assert checks['passed'] and checks['final_idle'] and checks['source_unchanged']
    for name, digest in read(BASE/'checks-1/source-sha256.json').items():
        assert sha(BASE/'checks-1/source'/name) == digest
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    assert modules == transition['modules']
    archive.idle(BASE, runtime.idle)
    answer = dict(idle=True, accepted=False, boot_id=boot, kernel_release=os.uname().release,
        sessions=84, drained=84, completed_operations=operations, jit_entries=entries,
        api_jit_returns=returns, execution_classes=dict(classes), exact_retirements=retirements,
        per_session_kernel_faults=faults, verified_original_files=original_files,
        verified_retained_harness=harness, matching_runtime_modules=True,
        source_sha256=sha(Path(__file__)), checks=checks,
        limits='Functional preservation only; host endpoint and all seven causal resolutions remain separate.')
    with (BASE/'final-health.json').open('x') as stream:
        json.dump(answer, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in answer.items() if k not in
                     ('verified_original_files', 'verified_retained_harness', 'checks', 'exact_retirements')}))


if __name__ == '__main__':
    main()
