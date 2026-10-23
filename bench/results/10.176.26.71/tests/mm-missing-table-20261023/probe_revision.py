#!/usr/bin/env python3
"""Guest-only probe correction; retain failed inputs and reuse the kernel/module."""
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/mm-missing-table-20261023')
sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
command = runpy.run_path('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/build-control-1/build.py')['command']


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdmm14'
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
    original = json.loads((BASE/'build-1/result.json').read_text())
    inputs = json.loads((BASE/'control-2/inputs.json').read_text())
    assert original['passed']
    for files in original['binaries'].values():
        for name, digest in files.items():
            assert rt.digest(BASE/name) == digest
    for name, digest in inputs['files'].items():
        assert rt.digest(BASE/name) == digest, name
    out = BASE/'probe-revision-2'; out.mkdir()
    probes = BASE/'probes-2'
    # Four binaries and the module retain their original identities. These
    # links also preserve include paths without copying old evidence.
    for family in ('unmap_body', 'resident_partial', 'absent_target'):
        (probes/family).symlink_to(BASE/'probes-1'/family, target_is_directory=True)
    (probes/'zero_target/client').symlink_to(BASE/'probes-1/zero_target/client')
    free = shutil.disk_usage('/').free
    source_bytes = sum((BASE/name).stat().st_size for name in inputs['files'])
    previous_bytes = (BASE/'probes-1/missing_table/client').stat().st_size
    # One executable plus compiler scratch/receipts. Base the check on the
    # observed input and binary sizes, with 2 MiB of bounded log/scratch room.
    budget = source_bytes + 4*previous_bytes + 2*1024*1024
    assert free > budget
    command(['cc', '-pthread', '-O2', '-Wall', '-Wextra', '-Werror', '-o',
             probes/'missing_table/client', probes/'missing_table/client.c'],
            out/'client-build.log', 120)
    binaries = {}
    for family, files in original['binaries'].items():
        binaries[family] = {}
        for name, digest in files.items():
            path = Path(str(name).replace('probes-1/', 'probes-2/', 1))
            actual = rt.digest(BASE/path)
            if family != 'missing_table':
                assert actual == digest
            binaries[family][str(path)] = actual
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
    rt.write_json(out/'result.json', dict(passed=True, source_commit=inputs['commit'],
        probe_directory=str(probes), binaries=binaries, source_files=inputs['files'],
        kernel_build_receipt=str(BASE/'build-1/result.json'), kernel_rebuilt=False,
        module_rebuilt=False, unchanged_clients_reused=4, basic_repeated=False,
        root_free_before=free, probe_space_budget=budget,
        root_free_after=shutil.disk_usage('/').free))
    print(json.dumps(dict(passed=True, kernel_rebuilt=False, module_rebuilt=False)))


if __name__ == '__main__':
    main()
