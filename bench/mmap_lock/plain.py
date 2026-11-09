#!/usr/bin/env python3
"""Separate actual-mm tasks using one frozen artifact set across boot modes.

Preparation builds only. Validation runs serial fixed-work and plain-client
correctness, without accepting rates. Measurement requires both validations
and the unchanged host gate; acceptance additionally requires an immediate
endpoint captured by the source controller after normal guest completion.
"""
import argparse
import copy
import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/mmap_fault'))
import timing as common
rt = common.rt
writer = common.module('actual_mm_writer', ROOT / 'bench/mmap_writer/timing.py')
mapping = common.module('actual_mm_mapping', ROOT / 'tests/kernel/mmap_lock/mapping.py')
fault = common.module('actual_mm_fault', ROOT / 'tests/kernel/mmap_fault/run.py')
RELEASE = '6.1.159-kdmm1'
BUILD_ID = '687ff5a29315d732f93a618e50ac407c794bbf9b'
SOURCE = Path('/root/kdlock-kernel-work/mmap-20261021/candidate-1/linux')
BUNDLE = Path('/root/kdlock-kernel-baselines/mmap-kdmm1-20261021')
MANIFEST_SHA = '3243e17005ed55c83af417ed3979ca9e89c077b89fcacd99dab5ae117c06b34b'
HEALTH = ROOT / 'bench/results/10.176.26.71/tests/mmap-kd-kernel-20261021/correctness-final-health.json'
HEALTH_SHA = '92483de18c7be441966a000d5e060ab0c2f9986e43e70bba30697cb60f962e99'
MODES = {'native': 'off', 'kd': 'on'}
PRIOR = {
    'native-api-3.json':'bbb2346ce712a7a9246d6e52393676f49c35bbeff9ce49acc343e503d567f032',
    'kd-api-1.json':'503d8b17e861716f08500d17fed45453d5a07195a7df9c5370b4123eed80f436',
    'native-mapping-2.json':'f2ff05a71e34336d33ef4cb1faede1b98a9357c2726a3172bb852a52490744d0',
    'kd-mapping-1.json':'80f067e9eda690302927d8866b4f4b69cb113bcf04fbf041df97a2879fc94571',
    'native-faults-2.json':'b8df9cc7d7212602e4c956b8ce47fcc1abba810654eebf53e7791c584a70f061',
    'kd-faults-1.json':'d69abf254130fce75e6ab2c9f52322ea4e9e034ad16f948f3f97fd4dde3d12fc',
    'native-completed-1.json':'6f63906a21f38381180fde8bcd91d83f7221cb551f0ba4e5b442b434e2ce5b5b',
    'kd-completed-1.json':'bb0617ba2862a53f04cdcd9f1bd914cab333007b0f616fe2b8dd2a89125802b3',
}


def identity(release, boot, cmdline, modules, mode, transition, expected_modules):
    """A recorded boot authorizes only image/mode changes, not other policy drift."""
    rt.require(mode in MODES and release == RELEASE and transition['passed'] and
               transition['boot_id'] == boot and transition['mode'] == mode and
               transition['release'] == RELEASE and transition['build_id'] == BUILD_ID and
               transition['recovery_preserved'], 'candidate boot/transition identity differs')
    expected = ('BOOT_IMAGE=/boot/vmlinuz-' + RELEASE +
                ' root=UUID=aa0bde06-47f6-4049-aaaf-13d052e53961 ro nokaslr nopvspin'
                ' console=tty1 console=ttyS0 kd_mmap=' + MODES[mode])
    rt.require(cmdline.split() == expected.split(), 'candidate boot policy/mode differs')
    rt.require(sorted(modules) == sorted(expected_modules) and len(modules) == 73,
               'exact runtime module set differs')


def profile(a, out):
    rt.require(os.geteuid() == 0 and str(ROOT) == '/root/host_fs/kdlock' and
               sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3' and
               shutil.which('python3') == sys.executable and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG') == common.SNAPSHOT,
               'same confirmed VM and pinned Python required')
    common.idle(Path('/root'))
    rt.require(rt.digest(HEALTH) == HEALTH_SHA, 'module prerequisite changed')
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    rt.require(modules == common.load(HEALTH)['modules'], 'runtime module set differs')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    rt.require(boot == a.boot_id, 'recorded boot changed')
    cmdline = Path('/proc/cmdline').read_text().strip()
    if a.action == 'prepare':
        rt.require(os.uname().release == common.RELEASE, 'prepare on recovery kernel first')
    else:
        rt.require(a.mode and a.transition, 'explicit candidate mode/transition required')
        transition = common.load(a.transition)
        identity(os.uname().release, boot, cmdline, modules, a.mode, transition, common.load(HEALTH)['modules'])
        shutil.copyfile(a.transition, out / 'transition.json')
    host = common.load(a.host_state)
    age = (datetime.datetime.now(datetime.timezone.utc) -
           datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
    rt.require(0 <= age <= 300 and host['pins_verified'] and host['snapshot_listed'] and
               host['recovery_snapshot'] == common.SNAPSHOT and len(host['qemu']) == 1 and
               host['qemu'][0]['pid'] == 257489, 'fresh same-host snapshot/pin evidence required')
    shutil.copyfile(a.host_state, out / 'host-before.json')
    previous = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {63})
        collector = rt.capture_topology([63])
    finally:
        os.sched_setaffinity(0, previous)
    topology = rt.capture_topology(list(range(60)))
    environment = dict(boot_id=boot, cmdline=cmdline, python=sys.executable,
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
        packages={p: importlib.metadata.version(p) for p in ('miasm','future','pyparsing','pyelftools')},
        snapshot_tag=common.SNAPSHOT, collector_topology=collector)
    rt.require(environment['packages'] == dict(miasm='0.1.5', future='1.0.0', pyparsing='2.4.7', pyelftools='0.27') and
               '(voluntary)' in environment['preemption'] and topology['online_cpus'] == list(range(64)) and
               topology['role_nodes'] == [0]*32 + [1]*28, 'guest policy/dependency/topology differs')
    rt.write_json(out / 'environment.json', environment)
    rt.write_json(out / 'topology.json', topology)
    if a.action == 'measure':
        for name, digest in common.scheduler.REPLAY_ENVIRONMENT_SHA256.items():
            rt.require(rt.digest(common.ORIGINAL / name) == digest, 'original environment changed')
        old = common.load(common.ORIGINAL / 'host-state.json')
        tasks = lambda h: sorted(h['qemu'][0]['tasks'], key=lambda t:t['tid'])
        rt.require(len(tasks(host)) == 67 and tasks(host) == tasks(old), 'strict original QEMU thread set differs')
        expected = common.load(common.ORIGINAL / 'environment.json')
        expected.update(boot_id=boot, cmdline=cmdline)
        comparison = common.scheduler.same_environment(old, host, expected, environment,
            common.load(common.ORIGINAL / 'topology.json'), topology)
        comparison['authorized_transition'] = dict(boot_id=boot, mode=a.mode,
            transition_sha256=rt.digest(a.transition), release=RELEASE)
        rt.write_json(out / 'environment-comparison.json', comparison)
    return dict(boot_id=boot, modules=modules, kernel_mmap_mode=a.mode)


def prepare(a, out):
    rt.require(a.source_manifest and rt.digest(BUNDLE / 'manifest.json') == MANIFEST_SHA,
               'committed source and exact captured candidate required')
    verifier = common.module('actual_mm_baseline', ROOT / 'kernel_baseline/verify.py')
    rt.write_json(out / 'candidate-build.json', verifier.verify(BUNDLE, SOURCE, build=True, running=False))
    manifest = common.load(a.source_manifest)
    source = out / 'source'
    dirs = ('bench/mmap_', 'tests/kernel/mmap_', 'tests/unit/', 'tests/protocols/',
            'include/', 'daemon/', 'disassem/', 'bench/spin_cacheline/', 'kernel_baseline/', 'workload_modules/mmap_')
    selected = {k:h for k,h in manifest['files'].items() if k.startswith(dirs) or k in
                ('bench/archive_run.py', 'bench/mutex_api_compare/run.py')}
    files = {}
    for name,digest in PRIOR.items():
        path=HEALTH.parent/name
        rt.require(rt.digest(path)==digest,'selected prior correctness changed: '+name)
        prior=common.load(path)
        rt.require(prior['passed'] and prior['drained'],'selected prior correctness incomplete')
        target=out/'prior'/name;target.parent.mkdir(exist_ok=True)
        shutil.copyfile(path,target);files[str(path)]=files[str(target)]=digest
    for name, digest in selected.items():
        rt.require(rt.digest(ROOT / name) == digest, 'committed source changed: ' + name)
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        files[str(ROOT / name)] = files[str(target)] = digest
    rt.write_json(out / 'source-sha256.json', selected)
    shutil.copyfile(a.source_manifest, out / 'committed-source.json')
    rt.command([sys.executable, '-m', 'pip', 'check'], out / 'dependencies.log', timeout=60)
    rt.command(['make', '-C', source/'tests/unit', 'run', 'PY_TESTS='], out/'basic.log', timeout=180)
    rt.command([sys.executable, source/'bench/mmap_lock/test_plain.py'], out/'unit.log', timeout=120)
    binaries = {}
    for name, directory in (('writer_payload','workload_modules/mmap_writer'),
                            ('fault_payload','workload_modules/mmap_fault'),
                            ('api_payload','tests/kernel/mmap_lock/fixture')):
        # Workload source directories are intentionally copied explicitly below.
        src = source / directory
        for path in (ROOT / directory).iterdir():
            rel = str(path.relative_to(ROOT))
            if rel not in manifest['files']: continue
            rt.require(rt.digest(path) == manifest['files'][rel], 'payload source changed')
            src.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, source / rel)
            files[str(source / rel)] = manifest['files'][rel]
        args = ['make', '-C', src, 'KDIR='+str(SOURCE), 'W=1', 'UBSAN_SANITIZE=n']
        if name == 'fault_payload': args += ['MF_NATIVE_ONLY=1']
        rt.command(args, out / (name+'-build.log'), timeout=180)
        filename = {'writer_payload':'kd_mmap_writer_native.ko', 'fault_payload':'kd_mmap_fault.ko',
                    'api_payload':'kd_mmap_probe.ko'}[name]
        binary = src / filename
        imports = rt.command(['nm','-u',binary], out / (name+'-imports.txt'))
        rt.require(not re.search(r'\b(?:kd_(?!mmap_)\w+|komb_\w+|tclock_\w+)\b', imports),
                   'external provider import in actual-mm payload')
        if name == 'fault_payload':
            rt.require(rt.command(['modinfo','-F','mmap_provider',binary],out/'fault-profile.log').strip() == 'native-only' and
                       not rt.command(['modinfo','-F','depends',binary],out/'fault-depends.log').strip(),
                       'fault payload profile/dependencies differ')
        binaries[name] = str(binary)
    for name, directory, filename, pthread in (
        ('writer_fixed','mmap_writer','client.c',True), ('writer_plain','mmap_writer','timed_client.c',True),
        ('fault_fixed','mmap_fault','split_client.c',False), ('fault_plain','mmap_fault','timed_client.c',False),
        ('fault_native','mmap_fault','native_client.c',False), ('fault_api','mmap_fault','client.c',True)):
        binary = out / name
        rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror', *(['-pthread'] if pthread else []),
                    '-I'+str(source/'workload_modules'/directory), source/'bench'/directory/filename,'-o',binary],
                   out/(name+'-build.log'), timeout=60)
        binaries[name] = str(binary)
    for path in binaries.values(): files[path] = rt.digest(Path(path))
    common.verify_maps(files)
    inputs = dict(files=files, binaries=binaries, source_commit=manifest['commit'],
                  build_id=BUILD_ID, native_backing_only=True)
    rt.write_json(out/'inputs.json',inputs)
    return dict(inputs_sha256=rt.digest(out/'inputs.json'), basic_programs=2, binaries=binaries)


def specification(task, count, mode, repeat=0):
    result = (writer.spec(count,'plain',repeat) if task=='mmap' else
              common.specification('fault',count,'native','plain',repeat))
    result.update(kernel_mmap_mode=mode, task=task, warmup=None)
    return result


def validate_plain(rows, spec):
    rt.require(spec['kernel_mmap_mode'] in MODES and spec['arm']=='native' and spec['observation']=='plain',
               'actual-mm mode/backing/observation differs')
    result = writer.validate(rows,spec) if spec['task']=='mmap' else common.validate(rows,spec)
    result.update(kernel_mmap_mode=spec['kernel_mmap_mode'], backing='NATIVE', delegated=False,
                  execution='KD_LOCAL_MMAP_LOCK' if spec['kernel_mmap_mode']=='kd' else 'NATIVE_CONTROL_MMAP_LOCK',
                  p95_status='DEFERRED', sampling_cost_status='DEFERRED')
    return result


def prepared_inputs(path):
    inputs=common.load(path);prior=common.load(path.parent/'result.json')
    rt.require(prior['action']=='prepare' and prior['passed'] and prior['drained'] and
               prior['final_idle'] and prior['basic_programs']==2 and
               prior['inputs_sha256']==rt.digest(path) and inputs['build_id']==BUILD_ID and
               inputs['native_backing_only'] is True, 'successful exact preparation required')
    common.verify_maps(inputs['files'])
    return inputs


def reject_mutations(rows, spec):
    cases = {
        'live_vma': lambda r:r[1]['after'].__setitem__('vmas',1),
        'missing_join': lambda r:r[1].__setitem__('joined',0),
        'wrong_cpu': lambda r:r[1]['workers'][0].__setitem__('observed_cpu',63),
        'invalid_progress': lambda r:r[1]['samples'][0]['completed'].__setitem__(0,r[1]['completed']+1),
        'plain_latency': lambda r:r[1]['workers'][0]['latency_ns'].append(1),
    }
    if spec['task']=='mmap':
        cases.update(different_mm=lambda r:r[1]['workers'][0]['identity'].__setitem__('mm',1),
            duplicate_tid=lambda r:r[1]['workers'][0]['identity'].__setitem__('tid',r[0]['identity']['tid']),
            fault_in_mmap=lambda r:r[1]['after'].__setitem__('faults',1),
            missing_map=lambda r:r[1]['after'].__setitem__('maps',0))
    else:
        cases.update(missing_fault=lambda r:r[1]['after'].__setitem__('faults',0),
            missing_read_end=lambda r:r[1]['after'].__setitem__('read_ends',0),
            writer_in_fault=lambda r:r[1]['after'].__setitem__('writes',1),
            extra_pid=lambda r:r[0]['pids'].append(r[0]['pids'][0]))
    rejected=[]
    for name, mutate in cases.items():
        bad=copy.deepcopy(rows); mutate(bad)
        try: validate_plain(bad,spec)
        except (rt.Failure,ValueError): rejected.append(name)
        else: raise RuntimeError('invalid receipt accepted: '+name)
    return rejected


def live(a, out, inputs, result):
    b=inputs['binaries']; cases=[]; sessions=[]
    result.update(cases=cases,sessions=sessions)
    def completed(collection,row):
        collection.append(row);rt.write_json(out/'result.json',result)
    fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK); os.lseek(fd,0,os.SEEK_END)
    messages=''
    def logs():
        nonlocal messages
        while True:
            try: messages+=os.read(fd,1<<20).decode(errors='replace')+'\n'
            except BlockingIOError: break
        (out/'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages),'kernel fault; retain payload','KERNEL_FAULT')
    def command(args,name):
        data=rt.command(args,out/(name+'.log'),timeout=120); logs(); return data
    def health(module, expected):
        value=Path('/sys/module',module,'parameters/health').read_text().strip()
        rt.require(value==expected,'exact file/VMA/mm drain differs: '+value)
        return value
    try:
        # Fresh API execution establishes the active mm backend on this boot.
        command(['insmod',b['api_payload'],'expected_kd='+str(int(a.mode=='kd'))],'load-api')
        api=json.loads(command([sys.executable,ROOT/'tests/kernel/mmap_lock/run.py','--client','--mode',a.mode],'api'))
        command(['rmmod','kd_mmap_probe'],'unload-api')
        if a.action=='validate':
            command(['insmod',b['writer_payload'],'observe=1'],'load-writer-fixed')
            chain=mapping.SITES['chains'][a.mode]
            proof=[str(mapping.SITES['sites'][n]['return_offset']) for n in ('vm_mmap_pgoff','__vm_munmap')]
            proof += [chain['waiter'],*map(str,chain['wait_returns']),str(chain['adapter_return']),mapping.SITES['adapter']]
            for i,(mode,n,iters) in enumerate((('scope',1,1),('cycle',1,1000),('cycle',16,5000),
                                              ('lifetime',1,1),('lifetime',16,1),('exit',1,1))):
                name=f'writer-fixed-{i}-{mode}-{n}'
                rows=[json.loads(s) for s in command([b['writer_fixed'],mode,str(n),str(iters),*proof],name).splitlines()]
                row=mapping.validate(rows,mode,n,iters,a.mode)
                row['health']=health('kd_mmap_writer_native',f'files=0 mm_refs=0 destroyed={i+1} release_errors=0')
                if mode=='cycle' and n==16: row['rejected']=mapping.reject_mutations(rows,a.mode)
                completed(cases,dict(name=name,**row))
            command(['rmmod','kd_mmap_writer_native'],'unload-writer-fixed')
            command(['insmod',b['fault_payload']],'load-fault-fixed')
            row=json.loads(command([b['fault_native']],'fault-reject-backends'))
            rt.require(row==dict(passed=True,rejected_backends=4,selected_backend=0),'backend refusal differs')
            row['health']=health('kd_mmap_fault','files=0 destroyed=1 release_errors=0'); completed(cases,row)
            for i,(mode,n,iters) in enumerate((('fault',1,5000),('fault',16,5000),('lifetime',16,1000),('concurrent',16,1000))):
                name=f'fault-fixed-{i}-{mode}-{n}'
                rows=[json.loads(s) for s in command([b['fault_fixed'],'0',mode,str(n),str(iters)],name).splitlines()]
                row=fault.validate_split(rows,0,mode,n,iters)
                row['health']=health('kd_mmap_fault',f'files=0 destroyed={i+2} release_errors=0')
                completed(cases,dict(name=name,**row))
            command(['rmmod','kd_mmap_fault'],'unload-fault-fixed')
            command(['insmod',b['fault_payload']],'load-fault-api')
            rows=[json.loads(s) for s in command([b['fault_api'],'0'],'fault-api').splitlines()]
            row=fault.validate(rows,0)
            row['health']=health('kd_mmap_fault','files=0 destroyed=3 release_errors=0');completed(cases,row)
            command(['rmmod','kd_mmap_fault'],'unload-fault-api')
        for task in ('mmap','fault'):
            for n in (1,16):
                spec=specification(task,n,a.mode,a.repeat)
                name=f'{task}-plain-{n}'
                module='kd_mmap_writer_native' if task=='mmap' else 'kd_mmap_fault'
                key='writer' if task=='mmap' else 'fault'
                command(['insmod',b[key+'_payload'],*(['observe=0'] if task=='mmap' else [])],'load-'+name)
                args=[b[key+'_plain'],*([str(n),'plain'] if task=='mmap' else ['0','fault',str(n),'plain'])]
                rows=[json.loads(s) for s in command(args,name).splitlines()]
                measured=validate_plain(rows,spec)
                h=health(module,'files=0 '+('mm_refs=0 ' if task=='mmap' else '')+'destroyed=1 release_errors=0')
                command(['rmmod',module],'unload-'+name)
                completed(sessions,dict(**spec,passed=True,drained=True,health=h,measurement=measured,
                    rejected=reject_mutations(rows,spec) if a.action=='validate' else [],name=name))
        return dict(api=api,cases=cases,sessions=sessions)
    finally:
        try: logs()
        finally: os.close(fd)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','validate','measure'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--host-state',type=Path,required=True)
    p.add_argument('--boot-id',required=True);p.add_argument('--mode',choices=tuple(MODES))
    p.add_argument('--transition',type=Path);p.add_argument('--source-manifest',type=Path)
    p.add_argument('--inputs',type=Path);p.add_argument('--validated',type=Path,nargs=2)
    p.add_argument('--repeat',type=int,choices=range(3),default=0)
    a=p.parse_args();out=a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT),'new evidence output required')
    rt.require(a.inputs is None or not out.is_relative_to(a.inputs.resolve().parent),
               'output must be outside frozen preparation')
    common.idle(Path('/root'));out.mkdir(parents=True)
    result=dict(action=a.action,passed=False,drained=False,accepted=False,timing=a.action=='measure',
                p95_status='DEFERRED',sampling_cost_status='DEFERRED',seven_mutex_causes='UNRESOLVED')
    try:
        result.update(profile(a,out))
        if a.action=='prepare': result.update(prepare(a,out))
        else:
            rt.require(a.inputs is not None,'frozen input manifest required')
            inputs=prepared_inputs(a.inputs)
            shutil.copyfile(a.inputs,out/'inputs.json')
            shutil.copyfile(a.inputs.parent/'result.json',out/'preparation.json')
            result['inputs_sha256']=rt.digest(a.inputs)
            if a.action=='measure':
                rt.require(a.validated is not None,'both-mode binary correctness required before timing')
                prerequisites=[common.load(path) for path in a.validated]
                rt.require({r['kernel_mmap_mode'] for r in prerequisites}==set(MODES) and
                    all(r['action']=='validate' and r['passed'] and r['drained'] and r['final_idle'] and
                        r['inputs_sha256']==result['inputs_sha256'] for r in prerequisites),
                    'same frozen binaries must pass in both modes')
                rt.write_json(out/'prerequisites.json',{str(path):rt.digest(path) for path in a.validated})
            args=argparse.Namespace(kernel_source=SOURCE,kernel_baseline=BUNDLE)
            result['kernel_identity']=common.kernel_identity.capture(args,out,rt.command)
            rt.require(result['kernel_identity']['running_build_id']==BUILD_ID and
                       rt.digest(BUNDLE/'manifest.json')==MANIFEST_SHA and
                       mapping.SITES['kernel_build_id']==BUILD_ID and
                       rt.digest(SOURCE/'vmlinux')==mapping.SITES['vmlinux_sha256'],
                       'candidate identity or exact writer proof ELF differs')
            result.update(live(a,out,inputs,result));common.verify_maps(inputs['files'])
        common.idle(Path('/root'))
        rt.require(sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==result['modules'],
                   'final module set differs')
        result.update(passed=True,drained=True,final_idle=True,host_endpoint='PENDING')
    except BaseException as error:
        result['error']=repr(error);raise
    finally: rt.write_json(out/'result.json',result)
    print(json.dumps({k:result[k] for k in ('passed','drained','action','accepted')}))


if __name__=='__main__': main()
