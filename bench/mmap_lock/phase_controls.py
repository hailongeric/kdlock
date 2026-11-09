#!/usr/bin/env python3
"""Correctness only: three deterministic paths through the sealed observer."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
sys.path.insert(0, str(ROOT/'bench/mmap_lock'))
import phase_observation as phase

plain, rt, serial = phase.plain, phase.rt, phase.serial
SELF = ROOT/'bench/mmap_lock/phase_controls.py'
PREVIOUS = Path('/root/kdlock-evidence/10.176.26.71/bench/mmap-phase-observation-20261022/kd-1/prepare-1/result.json')
INPUTS = Path('/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021/prepare-1/inputs.json')
CASE_FIELDS = ('mode','task','tid','mm','sem','schedule_calls','first_return','voluntary','involuntary',
               'injected','self_wake','peer_task','peer_wake','peer_done','joined','blocked_before_wake')
HEADER = ('abi','checks','errors','idle','scenarios','missed')


def validate(result, observation):
    phase.valid_observer(observation)
    rt.require(result['abi']==1 and result['checks']>0 and not result['errors'] and
        result['idle']==1 and result['scenarios']==3 and not result['missed'], 'control result failed')
    cases=result['cases'];rows=observation['rows']
    rt.require(len(cases)==len(rows)==3 and [c['mode'] for c in cases]==[1,2,3] and
        len({c['task'] for c in cases})==3, 'three exact control tasks required')
    by_task={r['task']:r for r in rows}
    rt.require(set(by_task)=={c['task'] for c in cases}, 'observed task identities differ')
    for c in cases:
        r=by_task[c['task']];counts=c['counts']
        rt.require((r['tid'],r['mm'],r['last_sem'],r['sequence'])==(c['tid'],c['mm'],c['sem'],1) and
            r['counts']==counts, 'control identity or per-task counters differ')
        rt.require(counts['entries']==counts['epilogues']==counts['success']==1 and not counts['eintr'] and
            not counts['gate_error'] and
            c['joined']==c['injected']==c['self_wake']==c['first_return']==1 and
            c['schedule_calls']>=2 and c['schedule_calls']==counts['phase_schedule'] and
            counts['phase_blocked_return']>=1, 'injection or progress oracle differs')
        if c['mode']==1:
            rt.require(c['blocked_before_wake']==1 and c['voluntary']>=1 and
                counts['phase_after_block_fail']>=1 and counts['phase_blocked_return']>=2,
                'failed-after-block path was not forced')
        elif c['mode']==2:
            rt.require(c['voluntary']==c['involuntary']==0 and counts['phase_no_switch']>=1,
                'no-switch path was not forced')
        else:
            rt.require(c['voluntary']==0 and c['involuntary']>=1 and c['peer_task'] and
                c['peer_wake']==c['peer_done']==1 and counts['phase_runnable_return']>=1 and
                counts['phase_runnable_out']>=1, 'runnable-only path was not forced')


def read_control():
    stride=len(CASE_FIELDS)+len(phase.NAMES)
    data=bytearray(8*(len(HEADER)+3*stride))
    with open('/dev/kd_phase_controls','rb',buffering=0) as device:
        fcntl.ioctl(device,0x80006301|len(data)<<16,data,True)
    values=struct.unpack('='+'Q'*(len(data)//8),data)
    result=dict(zip(HEADER,values[:len(HEADER)]));result['cases']=[]
    for i in range(3):
        fields=values[len(HEADER)+i*stride:len(HEADER)+(i+1)*stride]
        result['cases'].append(dict(zip(CASE_FIELDS,fields[:len(CASE_FIELDS)]),
            counts=dict(zip(phase.NAMES,fields[len(CASE_FIELDS):]))))
    return result


def prepare(a):
    out=a.output;out.mkdir()
    result=dict(passed=False,accepted=False,state='PREPARING',files={})
    try:
        plain.common.idle(Path('/root'))
        rt.require(os.uname().release=='6.1.159-kdclobber2','prepare on preserved recovery')
        previous=phase.preparation(PREVIOUS)
        rt.require(rt.digest(INPUTS)==phase.INPUTS_SHA,'original frozen inputs required')
        plain.prepared_inputs(INPUTS)
        result['previous_preparation']=serial.binding(PREVIOUS)
        verifier=plain.common.module('control_baseline',ROOT/'kernel_baseline/verify.py')
        rt.write_json(out/'candidate-before.json',verifier.verify(plain.BUNDLE,plain.SOURCE,build=True,running=False))
        source=out/'source'
        for directory in ('tests/kernel/mmap_lock/phase_controls','tests/unit','include','daemon',
                          'workload_modules/mmap_phase_observer'):
            for path in (ROOT/directory).rglob('*'):
                rel=path.relative_to(ROOT)
                if (not path.is_file() or any(p.startswith('.') or p=='__pycache__' for p in rel.parts) or
                    path.name.endswith('.mod.c') or (path.suffix not in ('.c','.h','.inc','.S','.def','.py')
                    and path.name!='Makefile')):continue
                target=source/rel;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,target)
                result['files'][str(path)]=result['files'][str(target)]=rt.digest(path)
        for path in (SELF,ROOT/'bench/mmap_lock/phase_observation.py'):
            result['files'][str(path)]=rt.digest(path)
        rt.command([sys.executable,'-m','pip','check'],out/'dependencies.log',timeout=60)
        rt.command(['make','-C',source/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],
            out/'basic.log',timeout=180)
        rt.command([sys.executable,source/'tests/kernel/mmap_lock/phase_controls/test_receipts.py'],
            out/'receipt-tests.log',timeout=60)
        directory=source/'tests/kernel/mmap_lock/phase_controls/fixture'
        rt.command(['make','-C',directory,'KDIR='+str(plain.SOURCE),'W=1','UBSAN_SANITIZE=n'],
            out/'controls-build.log',timeout=180)
        binary=directory/'kd_mmap_phase_controls.ko'
        result['files'][str(binary)]=rt.digest(binary)
        result['binaries']=dict(controls=str(binary),observer=previous['binaries']['observer'],
                                baseline=previous['binaries']['baseline'])
        for path in result['binaries'].values():result['files'][path]=rt.digest(Path(path))
        plain.common.verify_maps(previous['files']);plain.common.verify_maps(result['files'])
        rt.write_json(out/'candidate-after.json',verifier.verify(plain.BUNDLE,plain.SOURCE,build=True,running=False))
        plain.common.idle(Path('/root'))
        result.update(passed=True,basic_programs=2,state='PREPARED')
    except BaseException as error:result['error']=repr(error);raise
    finally:rt.write_json(out/'result.json',result)


def check(a):
    out=a.output;out.mkdir()
    result=dict(passed=False,drained=False,accepted=False,state='ADMISSION',timing_started=False)
    try:
        prepared=phase.preparation(a.prepared)
        serial.verify_binding(prepared['previous_preparation']);phase.preparation(PREVIOUS)
        rt.require(rt.digest(INPUTS)==phase.INPUTS_SHA,'original frozen inputs required')
        plain.prepared_inputs(INPUTS)
        a.action='measure';result.update(plain.profile(a,out))
        result['kernel_identity']=plain.common.kernel_identity.capture(argparse.Namespace(
            kernel_source=plain.SOURCE,kernel_baseline=plain.BUNDLE),out,rt.command)
        serial.fault_check(out,'before-load-dmesg')
        rt.command(['insmod',prepared['binaries']['baseline'],'expected_kd=1'],out/'baseline-load.log')
        serial.fault_check(out,'baseline-after-load-dmesg')
        rt.command([sys.executable,ROOT/'tests/kernel/mmap_lock/run.py','--client','--mode','kd'],
            out/'baseline.json',timeout=120)
        serial.fault_check(out,'baseline-before-unload-dmesg')
        rt.command(['rmmod','kd_mmap_probe'],out/'baseline-unload.log')
        serial.fault_check(out,'baseline-after-unload-dmesg')
        rt.command(['insmod',prepared['binaries']['observer']],out/'observer-load.log')
        serial.fault_check(out,'observer-after-load-dmesg')
        rt.command(['insmod',prepared['binaries']['controls']],out/'controls-load.log')
        serial.fault_check(out,'controls-after-load-dmesg')
        control=read_control();rt.write_json(out/'controls.json',control)
        # The ioctl joined every task and retired the observer. Exporting its
        # terminal state does not stand in for those independent joins.
        observation=phase.export(out)
        serial.fault_check(out,'controls-after-run-dmesg')
        validate(control,observation)
        rt.command(['rmmod','kd_mmap_phase_controls'],out/'controls-unload.log')
        serial.fault_check(out,'controls-after-unload-dmesg')
        rt.command(['rmmod','kd_mmap_phase_observer'],out/'observer-unload.log')
        serial.fault_check(out,'observer-after-unload-dmesg')
        plain.common.verify_maps(prepared['files']);phase.preparation(PREVIOUS)
        plain.prepared_inputs(INPUTS)
        plain.common.idle(Path('/root'))
        rt.require(sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==result['modules'],
            'post-control modules differ')
        result.update(passed=True,drained=True,final_idle=True,state='CONTROLS_PASSED',
            prepared=serial.binding(a.prepared),controls=control,observer=observation)
    except BaseException as error:result['error']=repr(error);raise
    finally:rt.write_json(out/'result.json',result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','check'))
    p.add_argument('--output',type=Path,required=True)
    for name in ('host-state','transition','prepared'):p.add_argument('--'+name,type=Path)
    p.add_argument('--boot-id');p.add_argument('--mode',default='kd',choices=('kd',))
    a=p.parse_args()
    rt.require(os.geteuid()==0 and os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1' and
        os.environ.get('KDLOCK_SNAPSHOT_TAG')==plain.common.SNAPSHOT and
        not Path(__file__).resolve().is_relative_to(ROOT) and not a.output.resolve().is_relative_to(ROOT) and
        rt.digest(Path(__file__))==rt.digest(SELF),'confirmed guest and external byte-matched driver required')
    globals()[a.action](a)


if __name__=='__main__':main()
