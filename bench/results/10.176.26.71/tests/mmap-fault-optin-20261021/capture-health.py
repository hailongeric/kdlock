#!/usr/bin/env python3
"""Verify preserved attempts and actual idle in the unchanged recovery VM."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/mmap-fault-optin-20261021')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot == 'b65f0205-c8f9-4385-8b13-039cbce243a6'
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    spec = importlib.util.spec_from_file_location('archive', ROOT/'bench/archive_run.py')
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
    archive.idle(BASE, rt.idle)
    runs, faults, allocations = [], [], []
    total = 0
    for index in range(1, 6):
        name = 'live-' + str(index)
        base = BASE/name
        result = read(base/'result.json')
        assert result['boot_id'] == boot and result['accepted'] is False
        manifest = read(base/'committed-source.json')
        assert sha(base/'committed-source.json') == result['source_manifest_sha256']
        assert manifest['commit'] == result['source_commit']
        maps = [('source-sha256.json', base/'source'),
                ('prepared-source-sha256.json', base/'build/provider'),
                ('binary-sha256.json', base)]
        counts = {}
        for filename, directory in maps:
            if not (base/filename).exists():
                continue
            hashes = read(base/filename)
            for path, digest in hashes.items():
                assert sha(directory/path) == digest, (name, filename, path)
                if filename == 'source-sha256.json':
                    assert manifest['files'][path] == digest
            counts[filename] = len(hashes)
            total += len(hashes)
        assert counts['source-sha256.json'] == result['source_files']
        assert sha(base/'source/tests/kernel/mmap_fault/run.py') == result['script_sha256']
        for line in (base/'kernel.log').read_text().splitlines() if (base/'kernel.log').exists() else []:
            if rt.FAULT.search(line):
                faults.append(dict(run=name, line=line))
            if 'percpu: allocation failed' in line or 'Could not allocate' in line:
                allocations.append(dict(run=name, line=line))
        if index < 4:
            assert result['state'] == 'FAILED' and not result['passed'] and not result['cases']
            if index > 1:
                cleanup = read(base/'cleanup.json')
                assert cleanup['idle'] and cleanup['retired'] == dict(state=2, modules=0, writers=0, frames=0)
        else:
            assert result['state'] == 'COMPLETE' and result['passed'] and result['drained']
            assert result['final_idle'] and result['source_unchanged'] and result['basic_programs'] == 2
            assert result['binaries'] == read(base/'binary-sha256.json')
            assert all(case['passed'] for case in result['cases'])
            if index == 4:
                assert result['jit_counts_observed'] and result['jit_bodies'] == result['jit_completions'] == 0
                assert result['retired'] == dict(state=2, modules=0, writers=0, frames=0)
            else:
                assert result['tclock_quiescent'] and result['retired'] is None
                assert not result['jit_counts_observed'] and result['jit_bodies'] is result['jit_completions'] is None
                assert result['native_kd_prerequisite']['sha256'] == sha(BASE/'live-4/result.json')
                assert result['source_commit'] == read(BASE/'live-4/result.json')['source_commit']
        runs.append(dict(name=name, state=result['state'], passed=result['passed'],
                         source_commit=result['source_commit'], verified=counts,
                         result_sha256=sha(base/'result.json')))
    assert not faults, faults
    assert {r['run'] for r in allocations} == {'live-2', 'live-3'}
    control = BASE/'supervision'
    control.mkdir(exist_ok=False)
    for path in sorted(Path('/tmp').glob('kd-mf-live-*-supervision.log*')):
        if path.name.endswith('.command.json'):
            assert not Path('/proc', str(read(path)['pid'])).exists()
        shutil.copyfile(path, control/path.name)
    shutil.copyfile(__file__, BASE/'capture-health.py')
    archive.idle(BASE, rt.idle)
    result = dict(idle=True, boot_id=boot, kernel_release=os.uname().release,
                  finished_ns=time.time_ns(), runs=runs, verified_hashes=total,
                  per_session_kernel_faults=faults, retained_allocation_failures=allocations,
                  accepted=False, source_sha256=sha(Path(__file__)),
                  limits='Functional validation only; three preparation failures retained; timing not run.')
    with (BASE/'final-health.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
