#!/usr/bin/env python3
"""Separate admission, one frozen client, immediate host capture and cleanup.

The source controller captures the host immediately after run returns, before
finish performs validation or unload. No existing client or frozen runner is
edited. Readiness binds prior correctness instead of rerunning the API suite.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys

ROOT=Path('/root/host_fs/kdlock')
if ROOT.exists():sys.path.insert(0,str(ROOT/'bench/mmap_lock'))
import plain

ORDER=[(0,'native'),(0,'kd'),(1,'kd'),(1,'native'),(2,'native'),(2,'kd')]
CASES=[('mmap',1),('mmap',16),('fault',1),('fault',16)]
CONTROL=ROOT/'bench/results/10.176.26.71/tests/serial-continuation-20261022/run_remote.py'
BOUNDARY=ROOT/'bench/mutex_api_compare/rcuht_boundary.py'


def binding(path):return dict(path=str(path),sha256=plain.rt.digest(path))


def verify_binding(row):
    path=Path(row['path'])
    plain.rt.require(plain.rt.digest(path)==row['sha256'],'bound receipt changed: '+str(path))
    return plain.common.load(path)


def fault_check(out, label):
    messages=plain.rt.command(['dmesg'],out/(label+'.log'))
    plain.rt.require(not plain.rt.FAULT.search(messages),'kernel fault; retain loaded payload')


def health(module):return Path('/sys/module',module,'parameters/health').read_text().strip()


def expected_health(task, destroyed):
    return 'files=0 '+('mm_refs=0 ' if task=='mmap' else '')+f'destroyed={destroyed} release_errors=0'


def load_and_run(out, inputs, result):
    task=result['task'];n=result['threads'];key='writer' if task=='mmap' else 'fault'
    fault_check(out,'before-load-dmesg')
    plain.rt.command(['insmod',inputs['binaries'][key+'_payload'],
                      *(['observe=0'] if task=='mmap' else [])],out/'load.log')
    fault_check(out,'after-load-dmesg')
    plain.rt.require(health(result['module'])==expected_health(task,0),'payload starts with retained references')
    args=[inputs['binaries'][key+'_plain'],*([str(n),'plain'] if task=='mmap' else ['0','fault',str(n),'plain'])]
    result['state']='CLIENT_RUNNING';plain.rt.write_json(out/'client-result.json',result)
    plain.rt.command(args,out/'client.log',timeout=120)


def validate_and_unload(out, client):
    fault_check(out,'before-unload-dmesg')
    rows=[json.loads(line) for line in (out/'client.log').read_text().splitlines()]
    measured=plain.validate_plain(rows,client['spec'])
    value=health(client['module'])
    plain.rt.require(value==expected_health(client['task'],1),'exact file/VMA/mm drain differs')
    plain.rt.command(['rmmod',client['module']],out/'unload.log')
    fault_check(out,'after-unload-dmesg')
    return measured,value


def block_binding(block, repeat, mode, boot, previous, inputs_sha):
    plain.rt.require(0<=block<len(ORDER) and ORDER[block]==(repeat,mode),'ordered boot block differs')
    if block==0:
        plain.rt.require(previous is None,'first boot must not have a predecessor')
        return []
    plain.rt.require(previous is not None and previous['passed'] and previous['drained'] and
        previous['final_idle'] and previous['block']==block-1 and len(previous['sessions'])==4 and
        previous['inputs_sha256']==inputs_sha and len(previous['boot_ids'])==block and
        len(set(previous['boot_ids']))==block and boot not in previous['boot_ids'],
        'complete preceding block and distinct new boot required')
    return previous['boot_ids']


def case_binding(index, task, threads, repeat, readiness, previous):
    plain.rt.require(0<=index<len(CASES) and CASES[index]==(task,threads) and
        repeat==readiness['repeat'],'ordered task/count/repeat differs')
    if index==0:
        plain.rt.require(previous is None,'first case must not have a predecessor')
    else:
        plain.rt.require(previous is not None and previous['passed'] and previous['drained'] and
            previous['final_idle'] and previous['case']==index-1 and
            previous['boot_id']==readiness['boot_id'] and previous['inputs_sha256']==readiness['inputs_sha256'],
            'preceding case must complete and drain on this boot')


def prerequisites(inputs, paths):
    rows=[plain.common.load(path) for path in paths]
    plain.rt.require({row['kernel_mmap_mode'] for row in rows}=={'native','kd'} and all(
        row['passed'] and row['drained'] and row['final_idle'] and row['action']=='validate' and
        row['inputs_sha256']==plain.rt.digest(inputs) for row in rows),
        'unchanged binaries require both completed correctness modes')
    return [binding(path) for path in paths]


def endpoint_check(host, environment, topology):
    old=plain.common.load(plain.common.ORIGINAL/'host-state.json')
    tasks=lambda h:sorted(h['qemu'][0]['tasks'],key=lambda t:t['tid'])
    plain.rt.require(host['pins_verified'] and host['snapshot_listed'] and
        len(host['qemu'])==1 and len(tasks(host))==67 and tasks(host)==tasks(old),
        'strict original QEMU thread set differs')
    expected=plain.common.load(plain.common.ORIGINAL/'environment.json')
    expected.update(boot_id=environment['boot_id'],cmdline=environment['cmdline'])
    return plain.common.scheduler.same_environment(old,host,expected,environment,
        plain.common.load(plain.common.ORIGINAL/'topology.json'),topology)


def ready(a):
    plain.rt.require(not a.output.resolve().is_relative_to(a.inputs.resolve().parent),
                     'readiness cannot alter frozen preparation')
    out=a.output;out.mkdir()
    result=dict(passed=False,action='ready',api_probe_repeated=False,accepted=False)
    try:
        plain.prepared_inputs(a.inputs)
        if a.previous:
            previous=plain.common.load(a.previous)
            plain.rt.require(previous['driver_sha256']==plain.rt.digest(Path(__file__)) and
                previous['controller_sha256']==plain.rt.digest(CONTROL),'campaign control revision changed')
        boot_ids=block_binding(a.block,a.repeat,a.mode,a.boot_id,
            plain.common.load(a.previous) if a.previous else None,plain.rt.digest(a.inputs))
        result['validated']=prerequisites(a.inputs,a.validated)
        result.update(plain.profile(a,out))
        identity=plain.common.kernel_identity.capture(argparse.Namespace(kernel_source=plain.SOURCE,
            kernel_baseline=plain.BUNDLE),out,plain.rt.command)
        plain.rt.require(identity['running_build_id']==plain.BUILD_ID and
            plain.rt.digest(plain.BUNDLE/'manifest.json')==plain.MANIFEST_SHA and
            plain.rt.digest(plain.SOURCE/'vmlinux')==plain.mapping.SITES['vmlinux_sha256'],
            'candidate image or exact writer-proof ELF changed')
        result.update(kernel_identity=identity,inputs=binding(a.inputs),transition=binding(a.transition),
            inputs_sha256=plain.rt.digest(a.inputs),driver_sha256=plain.rt.digest(Path(__file__)),
            source_driver_sha256=plain.rt.digest(ROOT/'bench/mmap_lock/serial.py'),
            endpoint_helper=binding(BOUNDARY),controller_driver=binding(CONTROL),
            block=a.block,repeat=a.repeat,boot_ids=boot_ids+[a.boot_id],
            previous=binding(a.previous) if a.previous else None)
        fault_check(out,'ready-dmesg')
        result['passed']=True
    finally:plain.rt.write_json(out/'result.json',result)


def run(a):
    readiness=plain.common.load(a.ready)
    inputs_path=Path(readiness['inputs']['path'])
    plain.rt.require(not a.output.resolve().is_relative_to(inputs_path.resolve().parent),
                     'session cannot alter frozen preparation')
    parent=a.ready.parent.parent
    expected=parent/f'case-{a.case}-{a.task}-{a.threads}'
    plain.rt.require(a.output.resolve()==expected.resolve(),'unique case output path required')
    previous_path=(parent/f'case-{a.case-1}-{CASES[a.case-1][0]}-{CASES[a.case-1][1]}'/'result.json'
                   if a.case else None)
    case_binding(a.case,a.task,a.threads,a.repeat,readiness,
                 plain.common.load(previous_path) if previous_path else None)
    out=a.output;out.mkdir()
    result=dict(passed=False,drained=False,accepted=False,state='ADMISSION',action='measure',
                task=a.task,threads=a.threads,repeat=a.repeat)
    try:
        plain.rt.require(readiness['passed'] and readiness['boot_id']==a.boot_id and
            readiness['kernel_mmap_mode']==a.mode and
            readiness['driver_sha256']==plain.rt.digest(Path(__file__)) and
            readiness['source_driver_sha256']==plain.rt.digest(ROOT/'bench/mmap_lock/serial.py'),
            'fresh same-boot readiness and exact driver required')
        verify_binding(readiness['inputs'])
        inputs=plain.prepared_inputs(inputs_path)
        a.transition=Path(readiness['transition']['path']);verify_binding(readiness['transition'])
        for row in readiness['validated']:verify_binding(row)
        for row in (readiness['endpoint_helper'],readiness['controller_driver']):
            plain.rt.require(plain.rt.digest(Path(row['path']))==row['sha256'],'control source changed')
        if readiness['previous']:verify_binding(readiness['previous'])
        result.update(plain.profile(a,out))
        host_sha=plain.rt.digest(a.host_state)
        earlier=[plain.common.load(parent/f'case-{i}-{CASES[i][0]}-{CASES[i][1]}'/'result.json')
                 for i in range(a.case)]
        plain.rt.require(host_sha not in {r['admission_host_sha256'] for r in earlier},
                         'each case requires a new host capture')
        if previous_path:
            preceding_host=plain.common.load(previous_path.parent/'host-endpoint.json')
            plain.rt.require(plain.common.load(a.host_state)['captured_utc']>preceding_host['captured_utc'],
                             'new admission must follow the preceding endpoint')
        spec=plain.specification(a.task,a.threads,a.mode,a.repeat)
        key='writer' if a.task=='mmap' else 'fault'
        module='kd_mmap_writer_native' if a.task=='mmap' else 'kd_mmap_fault'
        result.update(state='LOADING',spec=spec,module=module,ready=binding(a.ready),
            inputs_sha256=plain.rt.digest(inputs_path),driver_sha256=plain.rt.digest(Path(__file__)),
            block=readiness['block'],case=a.case,admission_host_sha256=host_sha,
            predecessor=binding(previous_path) if previous_path else None)
        plain.rt.write_json(out/'client-result.json',result)
        load_and_run(out,inputs,result)
        # Do not validate, scan hashes, unload, wait or fetch more guest state
        # here. The controller's immediate host endpoint is the next action.
        result.update(passed=True,state='CLIENT_RETURNED',cleanup_pending=True)
    except BaseException as error:result['error']=repr(error);raise
    finally:plain.rt.write_json(out/'client-result.json',result)


def finish(a):
    out=a.output
    plain.rt.require(not (out/'result.json').exists(),'final session receipt already exists')
    client=plain.common.load(out/'client-result.json')
    result=dict(client,passed=False,drained=False,accepted=False)
    try:
        plain.rt.require(client['passed'] and client['state']=='CLIENT_RETURNED' and
            client['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip() and
            client['driver_sha256']==plain.rt.digest(Path(__file__)),'matching returned client required')
        readiness=verify_binding(client['ready'])
        verify_binding(readiness['inputs']);verify_binding(readiness['transition'])
        for row in readiness['validated']:verify_binding(row)
        plain.rt.require(client['inputs_sha256']==readiness['inputs_sha256']==readiness['inputs']['sha256'],
                         'client input binding differs')
        plain.rt.require(plain.rt.digest(BOUNDARY)==readiness['endpoint_helper']['sha256'],
                         'endpoint helper changed')
        inputs=plain.prepared_inputs(Path(readiness['inputs']['path']))
        controller=plain.common.load(out/'controller.json');host=plain.common.load(out/'host-endpoint.json')
        plain.rt.require(controller['driver_sha256']==readiness['controller_driver']['sha256'],
                         'source controller changed')
        plain.rt.require(controller['admission_sha256']==client['admission_host_sha256'] and
            0<=controller['admission_age_seconds']<=300,'capture-to-launch admission link differs')
        boundary=runpy.run_path(str(ROOT/'bench/mutex_api_compare/rcuht_boundary.py'))
        endpoint=dict(checked=True,passed=False,immediate=controller.get('immediate',False),
            result_sha256=plain.rt.digest(out/'client-result.json'),host_sha256=plain.rt.digest(out/'host-endpoint.json'))
        boundary['endpoint_link'](endpoint,controller,host,endpoint['result_sha256'],endpoint['host_sha256'],str(out/'client-result.json'))
        try:
            endpoint['comparison']=endpoint_check(host,plain.common.load(out/'environment.json'),plain.common.load(out/'topology.json'))
            endpoint['passed']=True
        except (plain.rt.Failure,ValueError) as error:endpoint['error']=repr(error)
        endpoint['controller_sha256']=plain.rt.digest(out/'controller.json')
        plain.rt.write_json(out/'endpoint.json',endpoint)
        measured,health_value=validate_and_unload(out,client)
        plain.common.verify_maps(inputs['files']);plain.common.idle(Path('/root'))
        modules=sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
        plain.rt.require(modules==client['modules'],'runtime modules did not return to baseline')
        result.update(passed=True,drained=True,final_idle=True,cleanup_pending=False,measurement=measured,
            health=health_value,endpoint=endpoint,host_endpoint='PASS' if endpoint['passed'] else 'FAIL',
            state='COMPLETED_ACCEPTED' if endpoint['passed'] else 'COMPLETED_REJECTED',
            acceptance_scope='Session evidence qualification only; no performance-gain or regression-resolution claim',
            p95_status='DEFERRED',seven_mutex_causes='UNRESOLVED')
    except BaseException as error:result['error']=repr(error);raise
    finally:plain.rt.write_json(out/'result.json',result)
    if result['passed'] and result['case']==3:
        cases=[plain.common.load(out.parent/f'case-{i}-{task}-{n}'/'result.json')
               for i,(task,n) in enumerate(CASES)]
        plain.rt.require(all(r['passed'] and r['drained'] and r['final_idle'] for r in cases),
                         'completed block requires four drained cases')
        block=dict(action='measure',passed=True,drained=True,final_idle=True,accepted=False,
            block=readiness['block'],boot_ids=readiness['boot_ids'],boot_id=result['boot_id'],
            driver_sha256=result['driver_sha256'],controller_sha256=readiness['controller_driver']['sha256'],
            kernel_mmap_mode=result['kernel_mmap_mode'],inputs_sha256=result['inputs_sha256'],
            sessions=[dict(r['spec'],**{k:r[k] for k in ('passed','drained','measurement','host_endpoint')},
                           receipt=binding(out.parent/f'case-{i}-{CASES[i][0]}-{CASES[i][1]}'/'result.json'))
                      for i,r in enumerate(cases)],
            host_endpoint='PASS' if all(r['host_endpoint']=='PASS' for r in cases) else 'FAIL')
        plain.rt.write_json(out.parent/'block-result.json',block)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('ready','run','finish'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--host-state',type=Path);p.add_argument('--boot-id');p.add_argument('--mode',choices=('native','kd'))
    p.add_argument('--transition',type=Path);p.add_argument('--inputs',type=Path)
    p.add_argument('--validated',type=Path,nargs=2);p.add_argument('--ready',type=Path)
    p.add_argument('--task',choices=('mmap','fault'));p.add_argument('--threads',type=int,choices=(1,16))
    p.add_argument('--repeat',type=int,choices=range(3),default=0)
    p.add_argument('--block',type=int,choices=range(6));p.add_argument('--case',type=int,choices=range(4))
    p.add_argument('--previous',type=Path);a=p.parse_args()
    plain.rt.require(not a.output.resolve().is_relative_to(ROOT) and
        plain.rt.digest(Path(__file__))==plain.rt.digest(ROOT/'bench/mmap_lock/serial.py'),
        'exact external serial driver and output required')
    if a.action=='finish':finish(a)
    else:
        original=a.action;a.action='measure'
        (ready if original=='ready' else run)(a)


if __name__=='__main__':main()
