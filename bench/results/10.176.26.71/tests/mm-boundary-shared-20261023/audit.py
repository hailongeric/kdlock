#!/usr/bin/env python3
"""Read-only offline evidence audit on the source host; no live tests."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[5]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mm-boundary-shared-20261023'


def main():
    digest=lambda data:hashlib.sha256(data).hexdigest()
    archive=RAW/'collect-1/essential.tar.gz'
    receipt=json.loads((RAW/'collect-1/receipt.json').read_text())
    assert archive.stat().st_size==receipt['bytes'] and digest(archive.read_bytes())==receipt['sha256']
    with tarfile.open(archive) as tar:
        members={p.name:p for p in tar.getmembers()}
        assert len(members)==len(tar.getmembers()) and all(not p.name.startswith('/') and '..' not in Path(p.name).parts and p.isfile() for p in members.values())
        read=lambda name:tar.extractfile(name).read()
        load=lambda name:json.loads(read(name))
        run=load('focused-1/result.json');build=load('build-1/result.json');inputs=load('control/inputs.json')
        assert run['passed'] and run['drained'] and build['passed'] and inputs['commit']==build['source_commit']
        for name,h in inputs['files'].items():
            assert digest(subprocess.check_output(['git','show',inputs['commit']+':'+name],cwd=ROOT))==h,name
        samples=[];count=0;probe_sources=0;generated={};new=[];smoke=[]
        for name in members:
            if name.startswith('probes-1/') and name.endswith(('.c','.h','.inc','.py')):
                if name.endswith('.mod.c'):
                    # Kbuild-generated module metadata is an output, not a
                    # maintained Git input. Preserve its exact archive hash.
                    generated[name]=digest(read(name));continue
                rel='tests/kernel/mmap_lock/'+name[len('probes-1/'):]
                assert rel in inputs['files'] and digest(read(name))==inputs['files'][rel],rel
                probe_sources+=1
        for case in run['cases']:
            prefix='focused-1/'+case['name']+'/'
            for name,key in [('client.json','client_sha256'),('kernel.log','kernel_log_sha256')]:
                assert digest(read(prefix+name))==case[key];count+=1
            row=load(prefix+'client.json');log=read(prefix+'kernel.log').decode();controls=load(prefix+'receipt-controls.json')
            assert case['passed'] and case['drained'] and row['idle'] and not row['errors'] and controls['passed']
            assert len(controls['rejected_corruptions'])==case['negative_controls']
            (new if case['name'].startswith(('shared-native-','shared-target-')) else smoke).append(case)
            records=re.findall(r'KD_MM_BOUNDARY_SHARED_PRIVATE done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+).*',log)
            assert len(records)==case['evidence'].get('remote_shared_removals',0)
            for r in records:assert r[2]!=r[3] and int(r[0],16)==row['mm']
            if case['name'] in ('shared-target-prefix-rr','shared-target-suffix-free','shared-target-suffix-error','shared-target-prefix-change-busy','shared-target-suffix-change-near-zero','shared-target-prefix-free-table'):
                samples.append(dict(case=case['name'],receipts=[line for line in log.splitlines() if any(tag in line for tag in
                    ('KD_MM_BOUNDARY_SHARED_PRIVATE ','absent_change ','edge_private_busy ','KD_MM_UNMAP handback ','KD_MM_UNMAP ack '))]))
        totals=dict(cases=len(run['cases']),new_cases=len(new),preservation_cases=len(smoke),
            negative_controls=sum(c['negative_controls'] for c in new+smoke),new_negative_controls=sum(c['negative_controls'] for c in new),
            new_remote=sum(c['evidence'].get('remote_shared_removals',0) for c in new),
            no_probe_hold_remote=sum(c['evidence'].get('remote_private_without_probe_holds',0) for c in new),
            remote_errors=sum(c['evidence'].get('remote_boundary_errors',0) for c in new),
            acks=sum(c['evidence'].get('matched_acks',0) for c in new),cancelled=sum(c['evidence'].get('cancelled',0) for c in new),
            native_success_comparisons=len(run['native_comparisons']),native_error_comparisons=len(run['native_error_comparisons']))
        assert totals==dict(cases=69,new_cases=61,preservation_cases=8,negative_controls=1954,new_negative_controls=1714,
            new_remote=44,no_probe_hold_remote=2,remote_errors=2,acks=5,cancelled=2,native_success_comparisons=27,native_error_comparisons=2)
        print(json.dumps(dict(passed=True,archive=receipt,source_commit=inputs['commit'],input_hashes_verified=len(inputs['files']),
            probe_source_hashes_verified=probe_sources,generated_outputs=generated,case_file_hashes_verified=count,totals=totals,samples=samples),indent=2))


if __name__=='__main__':main()
