#!/usr/bin/env python3
"""One serial live run using already compiled probes and existing strict validators."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/mm-interior-near-create-20261024')
TREE = Path('/dev/shm/kdmm29-identity')
BUNDLE = Path('/root/kdlock-kernel-baselines/mmap-kdmm29-20261024')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity
command = runpy.run_path('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/build-control-1/build.py')['command']


def idle():
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-attempt',type=int,default=1)
    parser.add_argument('--run',default='focused-1')
    parser.add_argument('--probe-revision',type=Path)
    a=parser.parse_args()
    assert a.run.replace('-','').isalnum()
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdmm29'
    assert 'kd_mmap=on' in Path('/proc/cmdline').read_text().split()
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED']=='1'
    idle()
    assert a.build_attempt==1
    build_path=BASE/'build-1/result.json'
    build=json.loads(build_path.read_text());assert build['passed']
    for files in build['binaries'].values():
        for name,digest in files.items():assert rt.digest(BASE/name)==digest
    probe_receipt=json.loads(a.probe_revision.read_text()) if a.probe_revision else build
    assert probe_receipt['passed']
    for files in probe_receipt['binaries'].values():
        for name,digest in files.items():assert rt.digest(BASE/name)==digest
    probes=Path(probe_receipt['probe_directory'])
    out=BASE/a.run;out.mkdir()
    result=dict(passed=False,drained=False,timing=False,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                kernel_identity=kernel_identity.check(TREE,BUNDLE),build_receipt=str(build_path),cases=[])
    result['probe_revision']=str(a.probe_revision) if a.probe_revision else str(build_path)
    rt.write_json(out/'result.json',result)
    validators={};controls={}
    families={'create':'interior_near_create','emptyprivate':'boundary_interior_near_private',
              'zeroprivate':'boundary_interior_zero_near_private','zeronear':'boundary_interior_near_zero',
              'zerointerior':'boundary_interior_zero','emptynear':'boundary_interior_near_empty'}
    for key,family in families.items():
        validators[key]=runpy.run_path(str(probes/family/'receipts.py'))
        controls[key]=runpy.run_path(str(probes/family/'controls.py'))['check']
    tasks=[]
    for target in ('empty','zero'):
        for orientation in ('left','right'):
            for near in ('u','z'):
                for far in ('r','z','u'):
                    pair=near+far if orientation=='left' else far+near
                    for route in ('native','target'):
                        tasks.append((f'create-{target}-{route}-{orientation}-{pair}',
                            [route,'middle-'+pair,orientation,'create'],target,'create'))
    for target,orientation,near,mode in [('empty','left','u','create-far-busy'),
            ('empty','right','u','create-busy'),('zero','left','z','create-busy'),
            ('zero','right','z','create-far-busy')]:
        pair=near+'r' if orientation=='left' else 'r'+near
        for route in ('native','target'):
            tasks.append((f'{target}-{route}-{orientation}-{mode}',[route,'middle-'+pair,orientation,mode],target,'create'))
    for target,orientation,pair in [('empty','left','uu'),('zero','right','rz')]:
        for mode in ('create-error1','create-error2'):
            for route in ('native','target'):
                tasks.append((f'{target}-{route}-{orientation}-{mode}',[route,'middle-'+pair,orientation,mode],target,'create'))
        tasks.append((f'{target}-target-{orientation}-create-cancel',
            ['target','middle-'+pair,orientation,'create-cancel'],target,'create'))
    tasks += [('empty-private-left-smoke',['target','middle-ru','left'],None,'emptyprivate'),
              ('zero-private-right-smoke',['target','middle-ur','right'],None,'zeroprivate'),
              ('empty-zero-near-left-smoke',['target','middle-zr','left'],None,'emptynear'),
              ('zero-untouched-near-right-smoke',['target','middle-zu','right'],None,'zerointerior')]
    assert len(tasks)==70
    plans=[('unmap_body','kd_mm_unmap_test',tasks)]
    native_rows={};result['native_error_comparisons']=[];result['native_comparisons']=[]
    fd=None;messages='';case=None

    def logs():
        nonlocal messages
        if fd is None:return
        while True:
            try:messages+=os.read(fd,1<<20).decode(errors='replace')+'\n'
            except BlockingIOError:break
        if case is not None:(case/'kernel.log').write_text(messages)
        assert not rt.FAULT.search(messages),'kernel fault: retain module and evidence'

    try:
        for family,module,tasks in plans:
            idle()
            validator=runpy.run_path(str(probes/family/'run.py'))
            command(['insmod',probes/family/'payload'/(module+'.ko')],out/(family+'-load.log'),30)
            for name,flags,width,check in tasks:
                case=out/name;case.mkdir();messages=''
                fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK);os.lseek(fd,0,os.SEEK_END)
                binary=probes/'interior_near_create'/('client-'+width) if check=='create' else probes/families[check]/'client'
                args=[binary,*flags]
                command(args,case/'client.json',180)
                logs();row=json.loads((case/'client.json').read_text())
                checks=[]
                if check in validators:
                    validator_body=validators[check]
                    evidence=validator_body['validate'](row,messages)
                    checks=controls[check](row,messages,validator_body['validate'])
                    rt.write_json(case/'receipt-controls.json',dict(passed=True,rejected_corruptions=checks))
                    if check=='create':
                        key=(width,row['shape'],row['interior_right'],row['mode'])
                        if row['native']:native_rows[key]=row
                        elif row['injection']:
                            validator_body['compare_native'](native_rows[key],row)
                            result['native_error_comparisons'].append(key)
                        elif key in native_rows:
                            result['native_comparisons'].append(dict(validator_body['compare_success'](native_rows[key],row),family=check))
                else:
                    evidence=(runpy.run_path(str(probes/'partial_unmap/receipts.py'))['validate'] if check=='partial' else validator[check])(row,messages)
                assert Path('/sys/module',module,'refcnt').read_text().strip()=='0'
                for comm in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
                    try:assert not comm.read_text().strip().startswith(('pu_r','pu_w','ub_r','ub_w','fb_r','fb_w'))
                    except (FileNotFoundError,ProcessLookupError):pass
                result['cases'].append(dict(name=name,passed=True,drained=True,checks=row['checks'],evidence=evidence,negative_controls=len(checks),
                    client_sha256=rt.digest(case/'client.json'),kernel_log_sha256=rt.digest(case/'kernel.log')))
                rt.write_json(out/'result.json',result)
                os.close(fd);fd=None
                print('PASS',name,json.dumps(evidence),flush=True)
                if name=='create-zero-target-right-uz':print('MILESTONE all 24 queued near-creation layouts match native; 24 created-near different-task removals plus 24 unchanged peer removals',flush=True)
            # Every open/worker/request has retired; never force an unload.
            command(['rmmod',module],out/(family+'-unload.log'),30)
            idle()
        expected=json.loads(Path('/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-zero-near-private-20261024/control/expected-guest.json').read_text())['modules']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        text=rt.command(['dmesg'],out/'final-dmesg.log');assert not rt.FAULT.search(text)
        assert len(result['cases'])==70 and len(result['native_comparisons'])==28 and len(result['native_error_comparisons'])==4
        result.update(passed=True,drained=True,idle=True,new_kernel_faults=[])
    except BaseException as error:
        result.update(error=repr(error));raise
    finally:
        try:logs()
        finally:
            if fd is not None:os.close(fd)
            rt.write_json(out/'result.json',result)
    print(json.dumps(dict(passed=True,drained=True,cases=len(result['cases']))),flush=True)


if __name__=='__main__':main()
