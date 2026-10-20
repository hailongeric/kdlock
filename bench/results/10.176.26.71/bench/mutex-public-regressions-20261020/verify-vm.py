#!/usr/bin/env python3
"""After collection only: verify original inputs, session receipts and VM drain."""
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
    checked = {}
    for bundle in read(prepared/'frozen-inputs.json').values():
        for filename, digest in bundle['files'].items():
            assert sha(Path(filename)) == digest, filename
            assert filename not in checked or checked[filename] == digest
            checked[filename] = digest
    harness = {}
    for filename, digest in read(prepared/'harness-inputs.json').items():
        relative = Path(filename).relative_to(ROOT)
        retained = prepared/'harness'/relative
        assert sha(retained) == digest, str(retained)
        harness[str(retained)] = digest
    state, records, plan = read(base/'status.json'), read(base/'records.json'), read(base/'plan.json')
    assert state['state'] == 'COMPLETE' and state['completed'] == state['planned'] == 120
    assert len(records) == len(plan) == len(state['sessions']) == 120
    assert len({r['name'] for r in records}) == 120
    provenance = read(base/'replay-provenance.json')
    assert sha(base/'replay-scheduler.py') == provenance['scheduler_sha256'] == \
        sha(ROOT/'bench/mutex_api_compare/run.py')
    assert provenance['frozen_inputs_manifest_sha256'] == sha(prepared/'frozen-inputs.json')
    assert provenance['harness_manifest_sha256'] == sha(prepared/'harness-inputs.json')
    report_path = ROOT/'bench/mutex_api_compare/report.py'
    assert sha(report_path) == 'ae4a9272ac7fae6130fd8bc5f99e98f20ffd1e115ed29322b0bf962ff8b6b39c'
    spec = importlib.util.spec_from_file_location('report', report_path)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    faults, retirements = [], []
    for index, (row, planned, receipt) in enumerate(zip(records, plan, state['sessions'])):
        path = Path(planned['evidence_path'])
        assert path.is_relative_to(base/'measurements')
        assert row == read(path/'session.json')
        assert row['name'] == planned['name'] == receipt['name'] and planned['sequence'] == index
        assert row['drained'] and not row.get('cleanup_error')
        assert row['execution_status'] in ('OK', 'NO_JIT')
        if row['arm'] == 'kdlock':
            assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0)
            retirements.append(dict(name=row['name'], retired=row['retired']))
        for line in (path/'kernel.log').read_text().splitlines():
            if runtime.FAULT.search(line):
                faults.append(dict(name=row['name'], line=line))
    assert not faults, faults
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot == read(base/'environment.json')['boot_id'] == \
        read(prepared/'matrix/environment.json')['boot_id']
    reference = Path(str(prepared)+'-archives')/'archives.json'
    shutil.copyfile(reference, base/'original-archives.json')
    result = dict(idle=True, boot_id=boot, checked_unix=time.time(), sessions=120,
        accepted=sum(report.accepted(r) for r in records), drained=120,
        execution_statuses=dict(Counter(r['execution_status'] for r in records)),
        execution_classes=dict(Counter(report.execution_class(r) for r in records)),
        exact_retirements=retirements, per_session_kernel_faults=faults,
        original_frozen_files_checked=len(checked), retained_harness_files_checked=len(harness),
        frozen_input_manifests=sha(prepared/'frozen-inputs.json'),
        harness_manifest=sha(prepared/'harness-inputs.json'),
        original_archives_manifest_sha256=sha(reference),
        scheduler_sha256=sha(base/'replay-scheduler.py'),
        verified_original_files=checked, verified_retained_harness=harness,
        scope='Later independent health and unchanged input proof; no new benchmark or kernel modification.')
    (base/'health.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in
                     ('verified_original_files', 'verified_retained_harness', 'exact_retirements')}))


if __name__ == '__main__':
    main()
