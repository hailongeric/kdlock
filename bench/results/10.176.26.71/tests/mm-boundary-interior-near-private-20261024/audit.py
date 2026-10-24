#!/usr/bin/env python3
"""Read-only source-host audit of this milestone's essential evidence."""
import hashlib,json,re,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mm-boundary-interior-near-private-20261024'
def main():
    digest=lambda b:hashlib.sha256(b).hexdigest()
    archive=RAW/'collect-1/essential.tar.gz';receipt=json.loads((RAW/'collect-1/receipt.json').read_text())
    assert archive.stat().st_size==receipt['bytes'] and digest(archive.read_bytes())==receipt['sha256']
    with tarfile.open(archive) as tar:
        members={m.name:m for m in tar.getmembers()}
        assert len(members)==len(tar.getmembers()) and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in members.values())
        read=lambda n:tar.extractfile(n).read()
        load=lambda n:json.loads(read(n))
        run,build,inputs=(load(n) for n in ('focused-2/result.json','build-3/result.json','control-r3/inputs.json'))
        assert run['passed'] and run['drained'] and run['idle'] and not run['new_kernel_faults']
        assert build['passed'] and build['installed'] and build['reused_kernel'] and build['reused_probe_clients']
        assert build['btf_runtime_modules']==73 and build['btf_probe_modules']==1
        assert build['changed_kernel_sources']==['mm/kd_mmap_unmap.inc']
        assert inputs['commit']==build['source_commit']
        assert 'Unit tests: 2 passed, 0 failed' in read('build-1/basic.log').decode()
        assert load('install-r3/result.json')['recovery_unchanged']
        for n,h in inputs['files'].items():
            assert digest(subprocess.check_output(['git','show',inputs['commit']+':'+n],cwd=ROOT))==h,n
        sources=0;generated={}
        for n in members:
            if not n.startswith(('probes-1/','probes-3/')) or not n.endswith(('.c','.h','.inc','.py')):continue
            if n.endswith('.mod.c'):generated[n]=digest(read(n));continue
            rel='tests/kernel/mmap_lock/'+n.split('/',1)[1]
            assert rel in inputs['files'] and digest(read(n))==inputs['files'][rel],rel
            sources+=1
        new=[];smoke=[];samples=[];hashes=0
        for case in run['cases']:
            prefix='focused-2/'+case['name']+'/'
            for n,k in [('client.json','client_sha256'),('kernel.log','kernel_log_sha256')]:
                assert digest(read(prefix+n))==case[k];hashes+=1
            row,log,controls=load(prefix+'client.json'),read(prefix+'kernel.log').decode(),load(prefix+'receipt-controls.json')
            assert row['idle'] and not row['errors'] and case['passed'] and case['drained'] and controls['passed']
            assert len(controls['rejected_corruptions'])==case['negative_controls']
            interior=not case['name'].endswith('-smoke');(new if interior else smoke).append(case)
            bodies=re.findall(r'KD_MM_BOUNDARY_INTERIOR_(?:MISSING|EMPTY|ZERO) done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+)[^\n]*',log)
            assert len(bodies)==case['evidence']['remote_boundary_removals']
            for mm,ident,origin,executor in bodies:
                assert origin!=executor and int(mm,16)==row['mm'] and 0<int(ident)<=row['groups']
            if interior:
                assert row['boundary_interior_near_private_test']==1
                near=2 if row['interior_right'] else 0
                for g,pte in enumerate(row['ptes_before']):
                    if row['injection'] and not row['native'] and g==0:continue
                    assert pte['anon']&(1<<near) and pte['none']&2
                    page=row['pages_before'][g*3+near]
                    after=row['pages_after'][g*3+near]
                    assert page['refs']==after['refs']==2 and page['pfn']==after['pfn']==pte['pfn'][near]
                    assert page['hash']==after['hash'] and page['maps']==after['maps']==1
                kept=re.findall(r'KD_MM_INTERIOR_NEAR_PRIVATE kept mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+) pfn=([0-9a-f]+) refs_before=3 refs_after=3 mapcount=1 pte_same=1 held=1 released=1 result=(0|-12)',log)
                assert len(kept)==len(bodies)+case['evidence']['remote_boundary_errors']==case['evidence']['private_near_holds_retired']
                assert len(kept)==log.count('KD_MM_INTERIOR_NEAR_PRIVATE kept ')
                assert not re.search(r'KD_MM_BOUNDARY_INTERIOR_(?:ZERO|PRIVATE|MISSING) (?:done|error) ',log)
                assert row['near_private_write_checks']==sum(bool(o['layouts'][near]['mapped']) for o in row['origins'])
            proofs=log.count('KD_MM_INTERIOR preflight ')
            assert proofs==len(bodies)+case['evidence']['remote_boundary_errors']
            assert log.count('KD_MM_INTERIOR split_bounds ')==(0 if row['injection']==1 else proofs)
            assert row['target_rechecks_accessed']==row['target_rechecks_written']==sum(not o['layouts'][1]['mapped'] for o in row['origins'])
            if case['name'] in ('interior-target-left-rr','interior-target-right-ur','interior-target-left-error1','interior-target-right-error2','interior-target-left-change-far-busy','interior-target-right-change-near-busy','interior-target-left-change-private','interior-target-right-change-zero'):
                samples.append(dict(case=case['name'],counts=row['counts'],table_bytes=[row['table_bytes_before'],row['table_bytes_after']],
                    receipts=[s for s in log.splitlines() if any(t in s for t in ('KD_MM_INTERIOR ','KD_MM_INTERIOR_NEAR_PRIVATE ','KD_MM_BOUNDARY_INTERIOR_EMPTY ','KD_MM_TEST edge_','KD_MM_UNMAP handback ','KD_MM_UNMAP ack ','KD_MM_POPULATED_RANGE rollback '))]))
        total=lambda rows,k:sum(c['evidence'].get(k,0) for c in rows)
        totals=dict(cases=len(run['cases']),new_cases=len(new),preservation_cases=len(smoke),
            negative_controls=sum(c['negative_controls'] for c in new+smoke),new_negative_controls=sum(c['negative_controls'] for c in new),
            new_remote=total(new,'remote_boundary_removals'),smoke_remote=total(smoke,'remote_boundary_removals'),
            remote_errors=total(new,'remote_boundary_errors'),private_near_holds_retired=total(new,'private_near_holds_retired'),
            private_near_rollbacks=total(new,'private_near_rollback'),acks=total(new,'matched_acks'),cancelled=total(new,'cancelled'),
            native_success_comparisons=len(run['native_comparisons']),native_error_comparisons=len(run['native_error_comparisons']))
        assert totals==dict(cases=48,new_cases=42,preservation_cases=6,negative_controls=1161,new_negative_controls=991,
            new_remote=12,smoke_remote=12,remote_errors=4,private_near_holds_retired=16,private_near_rollbacks=1,acks=10,cancelled=2,
            native_success_comparisons=16,native_error_comparisons=4)
        warnings={p:[s for s in read(p).decode().splitlines() if 'warning:' in s] for p in ('build-1/image.log','build-2/image.log','build-3/runtime-modules.log','build-3/unmap_body-module.log')}
        # The rejected boot is evidence, never a successful correctness run.
        failed=(RAW/'kd-1/failed-boot-serial.log').read_text(errors='replace')
        assert 'BPF:' in failed and 'Invalid name' in failed and 'focused-1/result.json' not in members
        recovery=json.loads((RAW/'recovery-1/result.json').read_text())
        health=json.loads((RAW/'final-health.json').read_text());host=json.loads((RAW/'final-host.json').read_text())
        assert recovery['passed'] and recovery['idle'] and recovery['recovery_preserved']
        assert recovery['release']==health['release']=='6.1.159-kdclobber2'
        assert health['passed'] and not health['test_modules'] and health['temporary_ram_builds_absent']
        assert host['snapshot_listed'] and host['pins_verified']
        identity=json.loads((RAW/'identity-r2/receipt.json').read_text())
        assert identity['passed'] and Path(identity['host_path']).stat().st_size==identity['compressed_bytes']
        assert digest(Path(identity['host_path']).read_bytes())==identity['compressed_sha256']
        print(json.dumps(dict(passed=True,archive=receipt,source_commit=inputs['commit'],input_hashes_verified=len(inputs['files']),
            probe_source_hashes_verified=sources,generated_build_sources=generated,case_file_hashes_verified=hashes,
            totals=totals,build_warnings=warnings,failed_boot='kd-1: split-BTF incompatibility before tests; corrected by build-3',samples=samples),indent=2))
if __name__=='__main__':main()
