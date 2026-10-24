#!/usr/bin/env python3
"""Read-only offline replay of the one archived campaign; no VM or live tests."""
import hashlib,json,re,runpy,subprocess,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mm-interior-near-create-20261024'
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(p.read_text())


def main():
    receipt=load(RAW/'collect-1/receipt.json');archive=RAW/'collect-1'/receipt['file']
    assert archive.stat().st_size==receipt['bytes'] and sha(archive.read_bytes())==receipt['sha256']
    with tarfile.open(archive) as t:
        files={m.name:t.extractfile(m).read() for m in t.getmembers() if m.isfile()}
    data=lambda name:json.loads(files[name])
    inputs=data('control/inputs.json');build=data('build-1/result.json');run=data('focused-1/result.json')
    assert inputs==load(RAW/'prepare-1/inputs.json') and build==load(RAW/'build-1/result.json') and run==load(RAW/'kd-1/result.json')
    assert build['passed'] and build['source_commit']==inputs['commit'] and build['kernel_relinks']==build['new_runtime_modules']==0
    assert build['new_clients']==2 and build['btf_probe_modules']==1 and build['reused_clients']==4
    assert all(build[k] for k in ('reused_kernel','reused_runtime_modules','reused_initramfs','temporary_build_mount_removed'))
    assert build['module_btf_vmlinux_sha256']=='53ff8b9c6af6fe6fc5676685fd0b7dae85a10c079ce16ec2db989a279d06f0da'
    assert build['baseline_manifest_sha256']=='bcb447e9d07cea07e6f215ee59131b6ee68fc143e8405cf6ab789d3a95af5945'
    for name,h in inputs['files'].items():
        assert sha(subprocess.check_output(['git','show',inputs['commit']+':'+name],cwd=ROOT))==h,name
    for name,h in build['sources'].items():assert sha(files['probes-1/'+name])==h,name
    assert b'Unit tests: 2 passed, 0 failed' in files['build-1/basic.log']
    assert b'BTF [M]' in files['build-1/unmap_body-module.log']
    assert run['passed'] and run['drained'] and run['idle'] and not run['new_kernel_faults'] and not run['timing']
    assert run['kernel_identity']['running_build_id']=='f103e598e99e47a63b40d044ff8cbb0390492d50'
    families={'create':'interior_near_create','empty-private-left-smoke':'boundary_interior_near_private',
        'zero-private-right-smoke':'boundary_interior_zero_near_private','empty-zero-near-left-smoke':'boundary_interior_near_empty',
        'zero-untouched-near-right-smoke':'boundary_interior_zero'}
    validators={f:runpy.run_path(str(ROOT/'tests/kernel/mmap_lock'/f/'receipts.py')) for f in families.values()}
    controls={f:runpy.run_path(str(ROOT/'tests/kernel/mmap_lock'/f/'controls.py'))['check'] for f in families.values()}
    native={};comparisons=errors=negative=0;totals={};examples=[];layouts=set();groups={k:0 for k in ('layouts','busy','errors','cancel','smoke')}
    for case in run['cases']:
        name=case['name'];prefix='focused-1/'+name+'/'
        assert case['passed'] and case['drained']
        for filename,key in [('client.json','client_sha256'),('kernel.log','kernel_log_sha256')]:assert sha(files[prefix+filename])==case[key]
        row=data(prefix+'client.json');log=files[prefix+'kernel.log'].decode()
        family=families.get(name,'interior_near_create');validator=validators[family]
        evidence=validator['validate'](row,log);assert evidence==case['evidence'],name
        corrupted=controls[family](row,log,validator['validate'])
        assert corrupted==data(prefix+'receipt-controls.json')['rejected_corruptions'] and len(corrupted)==case['negative_controls']
        negative+=len(corrupted)
        for k in ('remote_boundary_removals','created_near_different_task_removals','created_near_remote_errors',
                'created_near_holds_retired','created_near_rollback','matched_acks','cancelled','remote_boundary_without_private_holds'):
            totals[k]=totals.get(k,0)+evidence.get(k,0)
        if family=='interior_near_create':
            key=(row['boundary_zero_test'],row['interior_right'],row['shape'],row['mode'])
            if row['native']:native[key]=row
            elif row['injection']:validator['compare_native'](native[key],row);errors+=1
            elif not row['cancel']:validator['compare_success'](native[key],row);comparisons+=1
            groups['errors' if row['injection'] else 'cancel' if row['cancel'] else 'busy' if row['mode']!='create' else 'layouts']+=1
            if row['mode']=='create' and not row['native']:
                layouts.add(key[:3]);c=row['change'];o=row['origins'][1]
                body=next(m for m in re.finditer(r'KD_MM_BOUNDARY_INTERIOR_(?:EMPTY|ZERO) done '+validator['IDENT'],log) if m.group(3)==str(o['tid']))
                examples.append(dict(name=name,origin=o['tid'],executor=int(body.group(4)),modifier=c['actor'],
                    near_pfn=c['page'][0]['pfn'],zero_pfn=c['zero_pfn'],new_ancestry=not row['change_more']['anon_before']))
        else:groups['smoke']+=1
    assert len(run['cases'])==70 and len(layouts)==24 and comparisons==28 and errors==4 and negative==2632
    assert groups==dict(layouts=48,busy=8,errors=8,cancel=2,smoke=4)
    assert totals==dict(remote_boundary_removals=56,created_near_different_task_removals=24,created_near_remote_errors=4,
        created_near_holds_retired=28,created_near_rollback=1,matched_acks=4,cancelled=2,remote_boundary_without_private_holds=18)
    recovery=load(RAW/'recovery-1/result.json');health=load(RAW/'final-health.json');host=load(RAW/'final-host.json')
    assert recovery['passed'] and recovery['release']=='6.1.159-kdclobber2' and recovery['boot_id']!=run['boot_id']
    assert health['passed'] and health['idle'] and health['boot_id']==recovery['boot_id'] and health['modules']==73 and not health['test_modules']
    assert health['grub_environment']=='next_entry=\n' and health['temporary_ram_builds_absent']
    assert host['pins_verified'] and host['snapshot_listed'] and len(host['qemu'])==1 and host['qemu'][0]['pid']==257489
    result=dict(passed=True,live_reruns=0,archive=receipt,source_commit=inputs['commit'],frozen_inputs=len(inputs['files']),
        frozen_probe_sources=len(build['sources']),case_logs_verified=140,cases=70,basic_tests=2,negative_controls=negative,
        layout_count=24,native_outcome_comparisons=comparisons,native_error_comparisons=errors,groups=groups,totals=totals,examples=examples,
        boot_id=run['boot_id'],recovery_boot_id=recovery['boot_id'],unchanged_kernel=True,root_free_final=health['root_free'])
    (RAW/'collect-1/audit.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('examples','archive')},indent=2))
if __name__=='__main__':main()
