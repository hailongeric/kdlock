#!/usr/bin/env python3
"""One read-only audit of this milestone's frozen evidence on the source host."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
ROOT=Path(__file__).resolve().parents[5]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mm-neighbor-replace-20261024'


def main():
    digest=lambda b:hashlib.sha256(b).hexdigest()
    archive=RAW/'collect-1/essential.tar.gz'
    receipt=json.loads((RAW/'collect-1/receipt.json').read_text())
    assert archive.stat().st_size==receipt['bytes'] and digest(archive.read_bytes())==receipt['sha256']
    with tarfile.open(archive) as tar:
        members={p.name:p for p in tar.getmembers()}
        assert len(members)==len(tar.getmembers()) and all(p.isfile() and not p.name.startswith('/') and '..' not in Path(p.name).parts for p in members.values())
        read=lambda n:tar.extractfile(n).read()
        load=lambda n:json.loads(read(n))
        run,build,inputs=load('focused-1/result.json'),load('build-1/result.json'),load('control/inputs.json')
        assert run['passed'] and run['drained'] and build['passed'] and not build['kernel_rebuilt'] and not build['kernel_installed']
        assert inputs['commit']==build['source_commit']
        assert 'Unit tests: 2 passed, 0 failed' in read('build-1/basic.log').decode()
        for name,h in inputs['files'].items():assert digest(subprocess.check_output(['git','show',inputs['commit']+':'+name],cwd=ROOT))==h,name
        source_count=0
        for name in members:
            if name.startswith('probes-1/') and name.endswith(('.c','.h','.inc','.py')):
                rel='tests/kernel/mmap_lock/'+name[len('probes-1/'):]
                assert rel in inputs['files'] and digest(read(name))==inputs['files'][rel],rel
                source_count+=1
        new=[];smoke=[];samples=[];hashes=0;replaced=0;peer=0
        for case in run['cases']:
            prefix='focused-1/'+case['name']+'/'
            for name,key in [('client.json','client_sha256'),('kernel.log','kernel_log_sha256')]:
                assert digest(read(prefix+name))==case[key];hashes+=1
            row,log,controls=load(prefix+'client.json'),read(prefix+'kernel.log').decode(),load(prefix+'receipt-controls.json')
            assert row['idle'] and not row['errors'] and case['passed'] and case['drained'] and controls['passed']
            assert len(controls['rejected_corruptions'])==case['negative_controls']
            (new if case['name'].startswith('neighbor-') else smoke).append(case)
            bodies=list(re.finditer(r'KD_MM_BOUNDARY_SHARED_(?:MISSING|EMPTY|ZERO|PRIVATE) done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+)[^\n]*',log))
            assert len(bodies)==case['evidence']['remote_boundary_removals']
            for body in bodies:
                r=body.groups();assert r[2]!=r[3] and int(r[0],16)==row['mm']
                if row.get('neighbor_gate_test'):
                    if int(r[2])==row['origins'][1]['tid']:replaced+=1
                    else:peer+=1
            if row.get('neighbor_gate_test'):
                queued=log.index('KD_MM_NEIGHBOR queued ');retired=log.index('KD_MM_NEIGHBOR retired ')
                assert queued<retired and all(retired<body.start() for body in bodies)
            if case['name'] in ('neighbor-missing-target-prefix-ur-keep-left','neighbor-missing-target-suffix-zu-keep-right',
                                'neighbor-missing-target-prefix-uu-lose-left','neighbor-missing-target-suffix-uu-lose-right',
                                'neighbor-empty-target-prefix-zu-keep-right','neighbor-zero-target-suffix-uu-keep-right',
                                'neighbor-private-target-prefix-uu-keep-left','neighbor-missing-target-suffix-error','neighbor-missing-target-prefix-cancel'):
                samples.append(dict(case=case['name'],writer=row.get('neighbor_body'),neighbors=row['neighbors'],
                    receipts=[line for line in log.splitlines() if any(tag in line for tag in ('KD_MM_NEIGHBOR ','KD_MM_BOUNDARY_SHARED_','KD_MM_UNMAP handback ','KD_MM_UNMAP ack '))]))
        total=lambda rows,key:sum(c['evidence'].get(key,0) for c in rows)
        totals=dict(cases=len(run['cases']),new_cases=len(new),preservation_cases=len(smoke),
            negative_controls=sum(c['negative_controls'] for c in new+smoke),new_negative_controls=sum(c['negative_controls'] for c in new),
            new_remote=total(new,'remote_boundary_removals'),replaced_neighbor_remote=replaced,unchanged_peer_remote=peer,new_remote_without_private_holds=total(new,'remote_boundary_without_private_holds'),
            smoke_remote=total(smoke,'remote_boundary_removals'),remote_errors=total(new,'remote_boundary_errors'),
            acks=total(new,'matched_acks'),cancelled=total(new,'cancelled'),native_success_comparisons=len(run['native_comparisons']),native_error_comparisons=len(run['native_error_comparisons']))
        assert totals==dict(cases=38,new_cases=34,preservation_cases=4,negative_controls=1241,new_negative_controls=1091,new_remote=14,replaced_neighbor_remote=7,unchanged_peer_remote=7,new_remote_without_private_holds=8,smoke_remote=8,remote_errors=2,acks=7,cancelled=2,native_success_comparisons=14,native_error_comparisons=2)
        recovery=json.loads((RAW/'recovery-1/result.json').read_text());health=json.loads((RAW/'final-health-2.json').read_text());host=json.loads((RAW/'final-host.json').read_text())
        assert recovery['passed'] and recovery['idle'] and recovery['recovery_preserved'] and recovery['release']==health['release']=='6.1.159-kdclobber2'
        assert health['passed'] and not health['test_modules'] and health['temporary_ram_builds_absent'] and host['snapshot_listed'] and host['pins_verified']
        print(json.dumps(dict(passed=True,archive=receipt,source_commit=inputs['commit'],input_hashes_verified=len(inputs['files']),probe_source_hashes_verified=source_count,case_file_hashes_verified=hashes,totals=totals,samples=samples),indent=2))

if __name__=='__main__':main()
