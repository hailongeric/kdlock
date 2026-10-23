#!/usr/bin/env python3
"""Compile only the strengthened userspace observer; reuse kdmm9 and its modules."""
import json
import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/mnt/kdlock-builds/mm-mixed-matrix-20261023')
PRIOR = Path('/root/kdlock-evidence/10.176.26.71/tests/mm-mixed-partial-20261023')
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
command = runpy.run_path(str(PRIOR / 'control/focus.py'))['command']


def idle():
    runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)


def main():
    idle()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    inputs = json.loads((BASE / 'control-1/inputs.json').read_text())
    for name, digest in inputs['files'].items():
        assert rt.digest(BASE / name) == digest, name
    prior = json.loads((PRIOR / 'build-2/result.json').read_text())
    assert prior['passed'] and prior['baseline_manifest_sha256'] == '645b72e4065136f3833be20e530293b46226f7c34d4aaa1b759ace051e45ce2f'
    probes = Path(prior['probe_directory'])
    reused = {}
    for files in prior['binaries'].values():
        for name, digest in files.items():
            path = PRIOR / name
            assert rt.digest(path) == digest
            reused[str(path)] = digest
    for family, names in {
        'unmap_body': ['run.py', 'client.c', 'payload/api.h'],
        'populated_unmap': ['run.py'], 'body': ['run.py'], 'fault_body': ['run.py'],
        'partial_unmap': ['receipts.py'], 'resident_partial': ['receipts.py', 'controls.py'],
    }.items():
        for name in names:
            path = probes / family / name
            reused[str(path)] = rt.digest(path)
    expected = json.loads((PRIOR / 'control/expected-guest.json').read_text())['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines()) == expected
    out = BASE / 'build-1'; out.mkdir()
    state = dict(passed=False, kernel_rebuilt=False, modules_rebuilt=False, source_commit=inputs['commit'],
                 inputs_sha256=rt.digest(BASE / 'control-1/inputs.json'), reused=reused,
                 prior_build_receipt=str(PRIOR / 'build-2/result.json'),
                 prior_build_sha256=rt.digest(PRIOR / 'build-2/result.json'))
    try:
        (BASE / 'probes-1/unmap_body').symlink_to(probes / 'unmap_body', target_is_directory=True)
        client = BASE / 'probes-1/mixed_partial/client'
        command(['cc', '-pthread', '-O2', '-Wall', '-Wextra', '-Werror', '-o', client, client.with_suffix('.c')],
                out / 'client-build.log', 120)
        command(['make', '-C', ROOT / 'tests/unit', 'run', 'PYTHON=' + sys.executable, 'PY_TESTS='], out / 'basic.log', 180)
        for name, digest in reused.items():
            assert rt.digest(Path(name)) == digest
        idle()
        state.update(passed=True, client=str(client), client_sha256=rt.digest(client), basic_programs=2)
    except BaseException as error:
        state['error'] = repr(error); raise
    finally:
        rt.write_json(out / 'result.json', state)
    print(json.dumps(state), flush=True)


if __name__ == '__main__': main()
