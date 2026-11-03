#!/usr/bin/env python3
"""Serial, unscored metadata observation of the unchanged kdmm1 writer path."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
if ROOT.exists():
    sys.path.insert(0, str(ROOT/'bench/mmap_lock'))
import serial

plain, rt = serial.plain, serial.plain.rt
SELF = ROOT/'bench/mmap_lock/phase_observation.py'
COUNTS = ROOT/'workload_modules/mmap_phase_observer/counts.def'
NAMES = re.findall(r'PHASE_COUNT\((\w+)\)', COUNTS.read_text())
INPUTS_SHA = '69271dff3cbb70e098a0b7157125b32a97ee7499b5903a539d0259bc5dff9b6f'
ROW_FIELDS = ('index','task','tid','mm','last_sem','sequence','active','first_entry_ns','last_epilogue_ns')


def read_result(device, command, fields, index=0):
    data = bytearray(8*(len(fields)+len(NAMES)))
    struct.pack_into('=Q', data, 0, index)
    fcntl.ioctl(device, command | len(data)<<16, data, True)
    values = struct.unpack('='+'Q'*(len(data)//8), data)
    return dict(zip(fields, values[:len(fields)]), counts=dict(zip(NAMES,values[len(fields):])))


def export(out):
    with open('/dev/kd_mmap_phase', 'rb', buffering=0) as device:
        fcntl.ioctl(device, 0x7002)
        result = read_result(device, 0x80007003, ('abi','records','active','errors','missed'))
        result['rows'] = [read_result(device, 0xc0007004, ROW_FIELDS, i)
                          for i in range(result['records'])]
    rt.write_json(out/'observer.json', result)
    return result


def balanced(c):
    conditions = (
        c['entries'] == c['epilogues'] == c['success']+c['eintr'],
        c['entries'] == c['reserved_initial']+c['initial_fail'],
        c['phase_prepare'] == c['queued_fail']+c['phase_finish'],
        c['queued_fail'] == c['phase_schedule']+c['phase_fail_cancel'],
        c['reserved'] == c['reserved_initial']+c['reserved_queued'] == c['gate_return'],
        c['reserved_queued'] == c['phase_finish'],
        c['phase_blocked_return'] == c['phase_after_block_fail']+
            c['phase_after_block_reserve']+c['phase_after_block_cancel'],
    )
    rt.require(all(conditions) and not c['errors'], 'observer accounting differs')
    for stage in ('phase','drain'):
        rt.require(c[stage+'_schedule'] == c[stage+'_schedule_return'] ==
            sum(c[stage+'_'+part] for part in ('no_switch','runnable_return','blocked_return')),
            'schedule episode balance differs: '+stage)


def valid_observer(observation):
    rt.require(observation['abi']==1 and 0<observation['records']<=64 and
        not any(observation[k] for k in ('active','errors','missed')), 'invalid observer state')
    balanced(observation['counts'])
    rt.require(len(observation['rows'])==observation['records'] and
        len({r['task'] for r in observation['rows']})==observation['records'], 'record identities differ')
    for index,row in enumerate(observation['rows']):
        rt.require(row['index']==index and row['task'] and row['tid'] and row['mm'] and
            row['last_sem'] and not row['active'] and row['sequence']==row['counts']['entries'],
            'invalid task record')
        balanced(row['counts'])
    rt.require(all(sum(r['counts'][name] for r in observation['rows'])==observation['counts'][name]
                   for name in NAMES), 'row/aggregate accounting differs')


def validate_workers(observation, measurement):
    valid_observer(observation)
    workers = {w['identity']['tid']:w for w in measurement['workers']}
    rt.require(len(workers)==16 and len(observation['rows'])==16 and
        {r['tid'] for r in observation['rows']}==set(workers), 'exact 16 workers required')
    for row in observation['rows']:
        w=workers[row['tid']];c=row['counts']
        rt.require(row['mm']==w['identity']['mm'] and row['last_sem']==w['identity']['mmap_lock'],
            'exact worker mm/semaphore differs')
        rt.require(c['entries']==c['epilogues']==c['success']==2*w['completed'] and
            not c['eintr'] and not c['gate_error'],
            'writer calls do not match completed mmap/munmap cycles')
        # Refuse the whole diagnostic if an aggregate includes any call outside
        # this worker's interval. We do not partially filter unrecoverable counts.
        rt.require(w['active_started_ns']<=row['first_entry_ns']<=row['last_epilogue_ns']<=
            w['kernel_finished_ns'], 'aggregate crosses worker active interval')
    c=observation['counts']
    return dict(valid=True, selected_workers=16, acquisition_calls=c['entries'],
        failed_predicates_per_reservation=c['queued_fail']/c['reserved'],
        preparations_per_reservation=c['phase_prepare']/c['reserved'],
        blocked_returns_per_reservation=c['phase_blocked_return']/c['reserved'],
        failed_retries_after_block=c['phase_after_block_fail'],
        blocked_return_failure_fraction=(c['phase_after_block_fail']/c['phase_blocked_return']
            if c['phase_blocked_return'] else None), wake_fanout='NOT_MEASURED', accepted=False)


def preparation(path):
    row=plain.common.load(path)
    rt.require(row['passed'] and row['basic_programs']==2, 'observer preparation incomplete')
    plain.common.verify_maps(row['files'])
    return row


def prepare(a):
    out=a.output;out.mkdir()
    result=dict(passed=False,accepted=False,state='PREPARING',files={})
    try:
        plain.common.idle(Path('/root'))
        rt.require(os.uname().release=='6.1.159-kdclobber2', 'prepare on preserved recovery')
        verifier=plain.common.module('phase_baseline',ROOT/'kernel_baseline/verify.py')
        rt.write_json(out/'candidate-before.json',verifier.verify(plain.BUNDLE,plain.SOURCE,build=True,running=False))
        source=out/'source'
        for directory in ('workload_modules/mmap_phase_observer','tests/kernel/mmap_lock/fixture',
                          'tests/kernel/mmap_lock/phase',
                          'tests/unit','include','daemon'):
            for path in (ROOT/directory).rglob('*'):
                rel=path.relative_to(ROOT)
                if (not path.is_file() or any(p.startswith('.') or p=='__pycache__' for p in rel.parts)
                    or path.name.endswith('.mod.c') or (path.suffix not in
                    ('.c','.h','.inc','.S','.def','.py') and path.name!='Makefile')):
                    continue
                target=source/rel;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,target)
                result['files'][str(path)]=result['files'][str(target)]=rt.digest(path)
        for path in (SELF,COUNTS,ROOT/'tests/kernel/mmap_lock/run.py'):
            result['files'][str(path)]=rt.digest(path)
        rt.command([sys.executable,'-m','pip','check'],out/'dependencies.log',timeout=60)
        rt.command(['make','-C',source/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],out/'basic.log',timeout=180)
        rt.command([sys.executable,source/'tests/kernel/mmap_lock/phase/test_observation.py'],
                   out/'receipt-tests.log',timeout=60)
        binaries={}
        for label,relative,name in (
            ('observer','workload_modules/mmap_phase_observer','kd_mmap_phase_observer.ko'),
            ('baseline','tests/kernel/mmap_lock/fixture','kd_mmap_probe.ko'),
            ('fixture','tests/kernel/mmap_lock/phase/fixture','kd_mmap_phase_probe.ko')):
            rt.command(['make','-C',source/relative,'KDIR='+str(plain.SOURCE),'W=1','UBSAN_SANITIZE=n'],
                       out/(label+'-build.log'),timeout=180)
            binary=source/relative/name;binaries[label]=str(binary)
            result['files'][str(binary)]=rt.digest(binary)
        rt.write_json(out/'candidate-after.json',verifier.verify(plain.BUNDLE,plain.SOURCE,build=True,running=False))
        plain.common.verify_maps(result['files']);plain.common.idle(Path('/root'))
        result.update(passed=True,state='PREPARED',basic_programs=2,binaries=binaries)
    except BaseException as error:
        result['error']=repr(error);raise
    finally:rt.write_json(out/'result.json',result)


def check(a):
    out=a.output;out.mkdir()
    result=dict(passed=False,drained=False,accepted=False,state='ADMISSION')
    try:
        p=preparation(a.prepared)
        a.action='measure';result.update(plain.profile(a,out))
        result['kernel_identity']=plain.common.kernel_identity.capture(argparse.Namespace(
            kernel_source=plain.SOURCE,kernel_baseline=plain.BUNDLE),out,rt.command)
        serial.fault_check(out,'before-load-dmesg')
        # Observer-off baseline retains the original API and reference oracles.
        rt.command(['insmod',p['binaries']['baseline'],'expected_kd=1'],out/'baseline-load.log')
        serial.fault_check(out,'baseline-after-load-dmesg')
        rt.command([sys.executable,ROOT/'tests/kernel/mmap_lock/run.py','--client','--mode','kd'],
                   out/'baseline.json',timeout=120)
        serial.fault_check(out,'baseline-before-unload-dmesg')
        rt.command(['rmmod','kd_mmap_probe'],out/'baseline-unload.log')
        serial.fault_check(out,'baseline-after-unload-dmesg')
        rt.command(['insmod',p['binaries']['observer']],out/'observer-load.log')
        serial.fault_check(out,'observer-after-load-dmesg')
        rt.command(['insmod',p['binaries']['fixture'],'expected_kd=1','observe_phase=1'],out/'fixture-load.log')
        serial.fault_check(out,'fixture-after-load-dmesg')
        rt.command([sys.executable,ROOT/'tests/kernel/mmap_lock/run.py','--client','--mode','kd'],
                   out/'fixture.json',timeout=120)
        serial.fault_check(out,'fixture-before-export-dmesg')
        observation=export(out);valid_observer(observation)
        rt.require(observation['counts']['entries']==6 and observation['counts']['success']==4 and
            observation['counts']['eintr']==2,'focused control totals differ')
        serial.fault_check(out,'fixture-before-unload-dmesg')
        rt.command(['rmmod','kd_mmap_phase_probe'],out/'fixture-unload.log')
        serial.fault_check(out,'observer-before-unload-dmesg')
        rt.command(['rmmod','kd_mmap_phase_observer'],out/'observer-unload.log')
        serial.fault_check(out,'after-unload-dmesg')
        plain.common.verify_maps(p['files']);plain.common.idle(Path('/root'))
        rt.require(sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==result['modules'],
                   'post-control modules differ')
        result.update(passed=True,drained=True,final_idle=True,state='CONTROLS_PASSED',
            prepared=serial.binding(a.prepared),observer=observation)
    except BaseException as error:
        result['error']=repr(error);raise
    finally:rt.write_json(out/'result.json',result)


def client(args,out):
    read_fd,write_fd=os.pipe()
    gate="import os,sys; fd=int(sys.argv[1]); go=os.read(fd,1); os.close(fd); os.sched_setaffinity(0,{63}); os.execv(sys.argv[2],sys.argv[2:]) if go==b'1' else sys.exit(125)"
    receipt=dict(argv=args,state='STARTING',started_ns=time.monotonic_ns(),timeout_seconds=120)
    try:
        with (out/'client.log').open('wb') as log:
            child=subprocess.Popen([sys.executable,'-c',gate,str(read_fd),*map(str,args)],
                pass_fds=(read_fd,),stdout=log,stderr=log,start_new_session=True)
            os.close(read_fd);read_fd=-1
            receipt.update(pid=child.pid,state='WAITING_FOR_ARM')
            rt.write_json(out/'client-command.json',receipt)
            with open('/dev/kd_mmap_phase','rb',buffering=0) as device:
                fcntl.ioctl(device,0x40087001,struct.pack('=Q',child.pid))
            os.write(write_fd,b'1');os.close(write_fd);write_fd=-1
            receipt['state']='RUNNING';rt.write_json(out/'client-command.json',receipt)
            code=child.wait(timeout=120)
            receipt.update(state='EXITED',returncode=code,finished_ns=time.monotonic_ns())
            rt.write_json(out/'client-command.json',receipt)
            rt.require(code==0,'client failure requires retained state review')
    except BaseException as error:
        receipt.update(error=repr(error),state='UNKNOWN_DRAIN')
        rt.write_json(out/'client-command.json',receipt);raise
    finally:
        if read_fd>=0:os.close(read_fd)
        if write_fd>=0:os.close(write_fd)


def run(a):
    out=a.output;out.mkdir()
    result=dict(passed=False,drained=False,accepted=False,state='ADMISSION',diagnostic=True,
        diagnostic_kind='mmap16-writer-phase-metadata',endpoint_boundary='GUEST_COMMAND_EXIT',
        task='mmap',threads=16,p95_status='DEFERRED',seven_mutex_causes='UNRESOLVED')
    try:
        p=preparation(a.prepared);controls=plain.common.load(a.checked)
        rt.require(controls['passed'] and controls['drained'] and controls['final_idle'] and
            controls['prepared']==serial.binding(a.prepared), 'focused correctness required')
        rt.require(rt.digest(a.inputs)==INPUTS_SHA,'original frozen inputs required')
        inputs=plain.prepared_inputs(a.inputs);validated=serial.prerequisites(a.inputs,a.validated)
        a.action='measure';result.update(plain.profile(a,out))
        identity=plain.common.kernel_identity.capture(argparse.Namespace(
            kernel_source=plain.SOURCE,kernel_baseline=plain.BUNDLE),out,rt.command)
        rt.require(identity['running_build_id']==plain.BUILD_ID and
            rt.digest(plain.SOURCE/'vmlinux')==plain.mapping.SITES['vmlinux_sha256'],'candidate differs')
        result.update(kernel_identity=identity,inputs=serial.binding(a.inputs),validated=validated,
            transition=serial.binding(a.transition),driver_sha256=rt.digest(Path(__file__)),
            admission_host_sha256=rt.digest(a.host_state),prepared=serial.binding(a.prepared),
            checked=serial.binding(a.checked),module='kd_mmap_writer_native',
            spec=plain.specification('mmap',16,'kd'),controls=[serial.binding(path) for path in
                (SELF,COUNTS,ROOT/'bench/mmap_lock/serial.py',serial.CONTROL,serial.BOUNDARY)])
        serial.fault_check(out,'before-load-dmesg')
        rt.command(['insmod',p['binaries']['observer']],out/'observer-load.log')
        serial.fault_check(out,'observer-after-load-dmesg')
        rt.command(['insmod',inputs['binaries']['writer_payload'],'observe=0'],out/'load.log')
        serial.fault_check(out,'after-load-dmesg')
        rt.require(serial.health(result['module'])==serial.expected_health('mmap',0),'payload not empty')
        result['state']='CLIENT_RUNNING';rt.write_json(out/'client-result.json',result)
        client([inputs['binaries']['writer_plain'],'16','plain'],out)
        # Fixed endpoint comes next. No export, verification, retirement or unload.
        result.update(passed=True,state='CLIENT_RETURNED',cleanup_pending=True)
    except BaseException as error:
        result['error']=repr(error);raise
    finally:rt.write_json(out/'client-result.json',result)


def finish(a):
    out=a.output;client=plain.common.load(out/'client-result.json')
    rt.require(not (out/'result.json').exists(),'final receipt already exists')
    result=dict(client,passed=False,drained=False,accepted=False,observation_usable=False)
    try:
        rt.require(client['passed'] and client['state']=='CLIENT_RETURNED' and
            client['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip() and
            client['driver_sha256']==rt.digest(Path(__file__)),'matching normal return required')
        for row in [client['inputs'],client['transition'],client['prepared'],client['checked'],
                    *client['validated'],*client['controls']]:
            rt.require(rt.digest(Path(row['path']))==row['sha256'],'bound input/control changed')
        controller=plain.common.load(out/'controller.json');host=plain.common.load(out/'host-endpoint.json')
        rt.require(controller['driver_sha256']==rt.digest(serial.CONTROL) and
            controller['admission_sha256']==client['admission_host_sha256'] and
            0<=controller['admission_age_seconds']<=300,'endpoint/admission binding differs')
        endpoint=dict(checked=True,passed=False,immediate=controller.get('immediate',False),
            result_sha256=rt.digest(out/'client-result.json'),host_sha256=rt.digest(out/'host-endpoint.json'),
            boundary=client['endpoint_boundary'])
        runpy.run_path(str(serial.BOUNDARY))['endpoint_link'](endpoint,controller,host,
            endpoint['result_sha256'],endpoint['host_sha256'],str(out/'client-result.json'))
        try:
            endpoint['comparison']=serial.endpoint_check(host,plain.common.load(out/'environment.json'),
                                                        plain.common.load(out/'topology.json'))
            endpoint['passed']=True
        except (rt.Failure,ValueError) as error:endpoint['error']=repr(error)
        rt.write_json(out/'endpoint.json',endpoint)
        serial.fault_check(out,'before-observer-retirement-dmesg')
        observation=export(out)
        # STOP established actual task exit and retired callbacks. Invalid
        # observations are retained, but do not prevent independently safe unload.
        serial.fault_check(out,'before-observer-unload-dmesg')
        rt.command(['rmmod','kd_mmap_phase_observer'],out/'observer-unload.log')
        serial.fault_check(out,'after-observer-unload-dmesg')
        measurement,health=serial.validate_and_unload(out,client)
        inputs=plain.prepared_inputs(Path(client['inputs']['path']))
        preparation(Path(client['prepared']['path']));plain.common.verify_maps(inputs['files'])
        plain.common.idle(Path('/root'))
        rt.require(sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==client['modules'],
                   'runtime modules did not return to baseline')
        result.update(drained=True,final_idle=True,cleanup_pending=False,measurement=measurement,
            health=health,endpoint=endpoint,host_endpoint='PASS' if endpoint['passed'] else 'FAIL')
        rows=[json.loads(s) for s in (out/'client.log').read_text().splitlines()]
        try:
            result['observation']=validate_workers(observation,rows[1]);result['observation_usable']=True
        except (rt.Failure,ValueError) as error:result['observation_error']=repr(error)
        result.update(passed=result['observation_usable'],state='COMPLETE_DIAGNOSTIC')
    except BaseException as error:
        result['error']=repr(error);raise
    finally:rt.write_json(out/'result.json',result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','check','run','finish'))
    p.add_argument('--output',type=Path,required=True)
    for name in ('host-state','transition','inputs','prepared','checked'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--boot-id');p.add_argument('--mode',default='kd',choices=('kd',))
    p.add_argument('--validated',type=Path,nargs=2)
    a=p.parse_args()
    rt.require(os.geteuid()==0 and os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1' and
        os.environ.get('KDLOCK_SNAPSHOT_TAG')==plain.common.SNAPSHOT and
        not Path(__file__).resolve().is_relative_to(ROOT) and not a.output.resolve().is_relative_to(ROOT) and
        rt.digest(Path(__file__))==rt.digest(SELF),'confirmed guest and external byte-matched driver required')
    globals()[a.action](a)


if __name__=='__main__':main()
