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
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/mm-absent-target-20261023')
TREE = Path('/dev/shm/kdmm13-identity')
BUNDLE = Path('/root/kdlock-kernel-baselines/mmap-kdmm13-20261023')
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
    a=parser.parse_args()
    assert a.run.replace('-','').isalnum()
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdmm13'
    assert 'kd_mmap=on' in Path('/proc/cmdline').read_text().split()
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED']=='1'
    idle()
    build=json.loads((BASE/f'build-{a.build_attempt}/result.json').read_text());assert build['passed']
    for files in build['binaries'].values():
        for name,digest in files.items():assert rt.digest(BASE/name)==digest
    probes=Path(build['probe_directory'])
    out=BASE/a.run;out.mkdir()
    result=dict(passed=False,drained=False,timing=False,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                kernel_identity=kernel_identity.check(TREE,BUNDLE),build_receipt=str(BASE/f'build-{a.build_attempt}/result.json'),cases=[])
    rt.write_json(out/'result.json',result)
    validators={kind:runpy.run_path(str(probes/(kind+'_partial')/'receipts.py')) for kind in ('resident','zero')}
    controls={kind:runpy.run_path(str(probes/(kind+'_partial')/'controls.py'))['check'] for kind in ('resident','zero')}
    validators['target']=runpy.run_path(str(probes/'zero_target/receipts.py'))
    controls['target']=runpy.run_path(str(probes/'zero_target/controls.py'))['check']
    validators['absent']=runpy.run_path(str(probes/'absent_target/receipts.py'))
    controls['absent']=runpy.run_path(str(probes/'absent_target/controls.py'))['check']
    # Representative unordered survivor pairs, at all three target positions.
    # Historical per-slot tests cover the opposite mixed ordering; this change
    # only admits the empty target and never changes survivor handling.
    shapes=[f'{position}-{pair}' for position in ('prefix','middle','suffix')
            for pair in ('rr','rz','ru','zz','zu','uu')]
    matrix=[(f'{route}-{shape}',[route,shape],None,'absent') for shape in shapes for route in ('native','target')]
    error_cases=[(f'absent-error-{route}-{point}', ['error',route,'resident','middle-zz',str(point)],None,'absent')
                 for point in (1,2) for route in ('native','kd')]
    changes=[(route+'-'+mode,[route,mode],None,'absent') for mode in ('change-zero','change-private') for route in ('native','target')]
    refusals=[('target-'+mode,['target',mode],None,'absent') for mode in ('refusal','missing-table','cancel-empty')]
    plans=[('unmap_body','kd_mm_unmap_test',matrix+error_cases+changes+refusals+[
        ('zero-target-resident-smoke',['target','middle-rz'],None,'target'),
        ('zero-target-empty-smoke',['target','prefix-uu'],None,'target'),
        ('resident-target-zero-smoke',['zero','middle-zz'],None,'zero'),
        ('resident-smoke',['resident','middle'],None,'resident')])]
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
                args=[probes/('absent_target' if check=='absent' else 'zero_target' if check=='target' else check+'_partial' if check in validators else 'partial_unmap' if check=='partial' else family)/'client',*flags]
                if width is not None:args+=['--pages',str(width)]
                command(args,case/'client.json',180)
                logs();row=json.loads((case/'client.json').read_text())
                checks=[]
                if check in validators:
                    validator_body=validators[check]
                    evidence=validator_body['validate'](row,messages)
                    checks=controls[check](row,messages,validator_body['validate'])
                    rt.write_json(case/'receipt-controls.json',dict(passed=True,rejected_corruptions=checks))
                    if check=='absent' and flags[0]=='error':
                        key=(check,'-'.join(flags[2:]))
                        if row['native']:native_rows[key]=row
                        else:
                            validator_body['compare_native'](native_rows[key],row)
                            result['native_error_comparisons'].append(key)
                    elif check=='absent' and flags[0]=='native':native_rows[(check,row['shape'])]=row
                    elif check=='absent' and flags[0]=='target' and flags[1] in shapes+['change-zero','change-private']:
                        result['native_comparisons'].append(validator_body['compare_success'](native_rows[(check,row['shape'])],row))
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
                if name=='target-suffix-uu':print('MILESTONE 18 absent-target layouts: 36 different-task removals matched native, including zero-owned-page cases',flush=True)
            # Every open/worker/request has retired; never force an unload.
            command(['rmmod',module],out/(family+'-unload.log'),30)
            idle()
        expected=json.loads((BASE/'control/expected-guest.json').read_text())['modules']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        text=rt.command(['dmesg'],out/'final-dmesg.log');assert not rt.FAULT.search(text)
        assert len(result['cases'])==51 and len(result['native_comparisons'])==20 and len(result['native_error_comparisons'])==2
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
