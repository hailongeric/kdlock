#!/usr/bin/env python3
"""VM-only performance-candidate KD210 run or its endpoint-bound archive.

Prepared statically on 380G10. No retry, source mutation, reboot or force unload.
Keep 8617 and acfa as separate comparison generations; this run measures KD only.
The current QEMU pool policy and all 210 measurement coordinates remain unchanged.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
COMMIT = None  # Required --commit binds every prerequisite before guest work.
BOOT = '677b7afa-5358-4ece-a650-5f4a4adecd55'
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
KDIR = '/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'
BUNDLE = '/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'
SNAPSHOT = 'linux70-kdlock1-clean-20261027'
OUT = CONTROL = ARCHIVES = None  # Required new output for this source generation.
UNIT_CONTROLLER = 'fe9208ce981a4e0d524c8366fe7cce78683f45235316e0ef85514c4555fce996'
BASIC_CONTROLLER = 'fdce682d696a6eb76b6bea511b1edc02a12655fae3eec2ac5065922ff9a6359e'
LIVE_CONTROLLER = 'fdce682d696a6eb76b6bea511b1edc02a12655fae3eec2ac5065922ff9a6359e'
ENDPOINT_CONTROLLER = '277ab27bead4e670786596f4ca5f6830327f2dcc14ce6f03436c775a6eb2e304'
COUNTS = [*range(1,9), *range(12,61,4)]
PROFILES = [('mutex-throughput','mutex',100,1), ('mutex-locality','mutex',100,16),
    ('rwsem-throughput-read','rwsem',1,1), ('rwsem-throughput-mixed','rwsem',20,1),
    ('rwsem-locality-read','rwsem',1,16), ('rwsem-locality-mixed','rwsem',20,16),
    ('rwlock-throughput-read','rwlock',1,1), ('rwlock-throughput-mixed','rwlock',20,1),
    ('rwlock-locality-read','rwlock',1,16), ('rwlock-locality-mixed','rwlock',20,16)]
POLICY = dict(total_cap=1024, numa_boundary=1024, deferred_handoff=8, scan_budget=64)
RETIREMENT = dict(state=2, modules=0, frames=0, writers=0)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    require(path.is_file() and not path.is_symlink() and path.resolve() == path,
            'canonical regular input required: '+str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    return json.loads(path.read_text())


def reviewed(path, expected):
    require(path is not None and expected is not None and
            re.fullmatch('[0-9a-f]{64}', expected) and sha(path) == expected,
            'reviewed input differs: '+str(path))
    return load(path)


def save(path, value):
    temporary = path.with_name('.'+path.name+'.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def unchanged(sync):
    require(sync.get('git_head') == COMMIT and sync.get('git_status') == '' and
            sync.get('synchronization_completed') is True and sync.get('tracked_sha256'),
            'exact clean selected source synchronization required')
    for name, digest in sync['tracked_sha256'].items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts and
                sha(ROOT/relative) == digest, 'frozen source changed: '+name)


def stable_boot():
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT,
            'guest boot changed; preserve attempt and review')


REUSE_HASHES = {
    'owner.json': '313a1ad0a38891530ec29cd2ceb5aa781d1236056b94ea21fbb47738d32a7bea',
    'unit.log': '52068e4078c5491ab420bbc729e7bb844be55fa42f475f8823df26dfb30be757',
    'sync.json': 'e8f8c60840496de5c3636039a214321ce15b8b1f241a929e812c3f1c899b3e43',
    'controller.py': 'e60a9285bca40716fdad9dcd409026471fadbc771508eccab4483797a4247b71',
}
REUSED_DRIVERS = [
    'spin/test_spin_batch.py', 'spin/test_spin_shadow.py',
    'spin/test_spin_outer_progress.py', 'spin/test_spin_proxy_context.py',
    'mutex/test_mutex_origin_instruction.py', 'execution/test_bench_completion.py',
]


def verify_unit_reuse(unit, sync, commit, evidence):
    require(unit.get('unit_selection') == {
        'fresh': False, 'prior_checks_reused': True,
        'basic': ['basic/test_control_call', 'basic/test_daemon_policy'],
        'python_drivers': ['spin/test_spin_batch_context.py'], 'expected_passes': 3,
        'reused_python_drivers': REUSED_DRIVERS, 'effective_selected_checks': 9,
    }, 'explicit selective unit coverage differs')
    reuse = unit.get('unit_reuse', {})
    require(reuse.get('prior_source_commit') == '6bf690204fdf954ab9076a762000833ec18e6261' and
            reuse.get('current_source_commit') == commit and
            reuse.get('prior_owner_completed') is False and
            reuse.get('prior_error') == "AssertionError('unit')" and
            reuse.get('prior_unit_returncode') == 2 and
            reuse.get('prior_unit_log_sha256') == REUSE_HASHES['unit.log'] and
            reuse.get('reused_python_drivers') == REUSED_DRIVERS and
            reuse.get('reused_python_passes') == 6 and
            reuse.get('same_tracked_path_set') is True and
            reuse.get('compared_tracked_inputs') == 5922 and
            reuse.get('evidence_directory') == 'unit-reuse' and
            reuse.get('retained_sha256') == REUSE_HASHES,
            'unit reuse must retain the exact failed attempt and six passes')
    require(set(evidence) == set(REUSE_HASHES) and
            all(hashlib.sha256(evidence[name]).hexdigest() == expected
                for name, expected in REUSE_HASHES.items()), 'retained unit-reuse input differs')
    prior = json.loads(evidence['owner.json'])
    old_sync = json.loads(evidence['sync.json'])
    require(prior.get('completed') is False and prior.get('error') == "AssertionError('unit')" and
            prior.get('source_commit') == reuse['prior_source_commit'] and
            prior.get('boot_id') == unit['boot_id'] and
            [row['name'] for row in prior['blocks']] == ['kernel-identity', 'unit'] and
            [row.get('returncode') for row in prior['blocks']] == [0, 2] and
            reuse.get('prior_unit_argv') == prior['blocks'][1]['argv'],
            'failed prior unit status must remain explicit')
    old, current = old_sync['tracked_sha256'], sync['tracked_sha256']
    require(old_sync['git_head'] == reuse['prior_source_commit'] and
            old_sync['git_status'] == '' and old_sync['synchronization_completed'] is True and
            sync['git_head'] == commit and len(old) == len(current) == 5922 and
            set(old) == set(current), 'unit reuse source path set differs')
    changed = {name: dict(prior=before, current=current[name])
               for name, before in old.items() if before != current[name]}
    require(set(changed) == {
        'tests/unit/spin/spin_batch_context_fixture.c',
        'bench/results/10.176.26.71/bench/continuation-nano-20261030/README.md',
    } and reuse.get('changed_inputs') == changed,
            'unit reuse permits only the reviewed fixture and failure-record changes')


def prerequisites(args, sync):
    require(args.functional_campaign is not None, 'functional campaign path required')
    require(args.basic_campaign is not None and args.basic_campaign.is_absolute(),
            'explicit external basic campaign required')
    unit = reviewed(args.unit, args.unit_sha256)
    require(unit.get('completed') is True and unit.get('final_idle') is True and
            unit.get('source_commit') == COMMIT and unit.get('boot_id') == BOOT and
            unit.get('input_sha256',{}).get('sync.json') == args.sync_sha256 and
            unit['input_sha256'].get('controller.py') == UNIT_CONTROLLER and
            [row['name'] for row in unit['blocks']] == ['kernel-identity','unit','build-provider'] and
            all(row.get('returncode') == 0 for row in unit['blocks']), 'unit/build prerequisite incomplete')
    require(sha(args.unit.parent/'controller.py') == UNIT_CONTROLLER and
            sha(args.unit.parent/'provider/manifest.json') == unit['provider_manifest_sha256'] and
            sha(args.unit.parent/'provider/kernel_module/kdlock_km.ko') == unit['provider_sha256'],
            'unit/build retained artifacts changed')
    inputs = {'unit.json':args.unit, 'sync.json':args.sync}
    reuse_paths = {name: args.unit.parent/'unit-reuse'/name for name in REUSE_HASHES}
    verify_unit_reuse(unit, sync, COMMIT,
                      {name: path.read_bytes() for name, path in reuse_paths.items()})
    inputs.update({'unit-reuse-' + name: path for name, path in reuse_paths.items()})
    basic_dependency = None
    for phase in ('basic','origin','rwsem','mixed'):
        campaign = args.basic_campaign if phase == 'basic' else args.functional_campaign
        expected_controller = BASIC_CONTROLLER if phase == 'basic' else LIVE_CONTROLLER
        owner_path = campaign/(phase+'-control/owner.json')
        owner = reviewed(owner_path, getattr(args, phase+'_owner_sha256'))
        require(owner.get('completed') is True and owner.get('final_idle') is True and
                owner.get('source_commit') == COMMIT and owner.get('boot_id') == BOOT and
                owner.get('phase') == phase and owner.get('returncode') == 0 and
                owner.get('timing_started') is False and
                owner.get('inputs',{}).get('sync.json') == args.sync_sha256 and
                owner['inputs'].get('unit.json') == args.unit_sha256 and
                owner['inputs'].get('controller.py') == expected_controller and
                all(owner['inputs'].get('unit-reuse-' + name) == expected
                    for name, expected in REUSE_HASHES.items()),
                'functional prerequisite incomplete: '+phase)
        require(sha(owner_path.parent/'controller.py') == expected_controller,
                'functional controller changed: '+phase)
        result_path = campaign/phase/'result.json'
        result = reviewed(result_path, owner['result_sha256'])
        require(result.get('passed') is True and
                result.get('drained',result.get('final_idle')) is True,
                'functional result did not drain: '+phase)
        if phase == 'basic':
            basic_dependency = {
                'campaign': str(campaign),
                'owner_path': str(owner_path), 'owner_sha256': sha(owner_path),
                'result_path': str(result_path), 'result_sha256': sha(result_path),
            }
            require(result.get('boot_id') == BOOT and result.get('timing_started') is False and
                    [row['family'] for row in result['results']] == ['spin','mutex','rwlock','rwsem'] and
                    all(row['passed'] and row['drained'] and row['jit_completions'] > 0
                        for row in result['results']), 'four-family basic prerequisite incomplete')
        else:
            require(owner.get('basic_campaign') == str(args.basic_campaign) and
                    owner.get('basic_dependency') == basic_dependency,
                    'functional basic prerequisite differs: '+phase)
            require(result.get('origin_service') == (phase != 'mixed') and
                    result.get('origin_instructions') == (phase == 'origin') and
                    result.get('mixed_spin') == (phase == 'mixed') and
                    result.get('family') == ('rwsem' if phase == 'rwsem' else 'mutex') and
                    result.get('entry_abi') == 2 and result.get('image_requirements') == 65 and
                    result.get('capabilities',{}).get('version') == 13 and
                    result['capabilities']['features'] & (1 << 13), 'functional service scope differs: '+phase)
            require(len(result['phases']) == (7 if phase == 'origin' else 5) and
                    all(row['complete'] for row in result['phases']) and
                    all(row['execution_validated'] for row in result['phases'][1:]),
                    'functional phase validation incomplete: '+phase)
            session_path = campaign/phase/'session/session.json'
            session = load(session_path)
            require(session.get('drained') is True and session.get('retired') == RETIREMENT,
                    'functional source/frame retirement incomplete: '+phase)
            inputs[phase+'-session.json'] = session_path
        inputs[phase+'-owner.json'] = owner_path
        inputs[phase+'-result.json'] = result_path
    unchanged(sync)
    return inputs


def plan_check(entries):
    require([row[0] for row in entries] == [row[0] for row in PROFILES], 'ten-profile plan changed')
    def values(command, option):
        require(command.count(option) == 1, 'missing/duplicate plan option: '+option)
        start = command.index(option)+1
        stop = next((i for i in range(start,len(command)) if command[i].startswith('--')),len(command))
        return command[start:stop]
    for (name,command),(_,family,writes,lines) in zip(entries,PROFILES):
        expected = {'--workloads':['cacheline'], '--cachelines':[str(lines)], '--lock-kind':[family],
            '--write-percent':[str(writes)], '--threads':list(map(str,COUNTS)),
            '--cpus':list(map(str,range(60))), '--collector-cpu':['63'], '--backends':['kdlock'],
            '--repeats':['1'], '--duration-ms':['2000'], '--post-work-rounds':['256'],
            '--delegate':['on'], '--mutex-batch-limit':['1024'], '--mutex-numa-boundary':['1024'],
            '--kernel-variant':['kdlock1'], '--kernel-source':[KDIR], '--kernel-baseline':[BUNDLE],
            '--output':[str(OUT/name)]}
        require(command[:2] == [PYTHON,str(ROOT/'bench/rwlock_compare/run.py')] and
                all(values(command,key) == value for key,value in expected.items()) and
                '--functional' not in command and '--require-jit' not in command and
                '--require-parity' not in command, 'literal nano child plan changed: '+name)


def verify_records(sync):
    total = 0
    for profile,family,writes,lines in PROFILES:
        records = load(OUT/profile/'records.json')
        plan = load(OUT/profile/'plan.json')
        require(len(records) == len(plan) == 21 and [row['threads'] for row in records] == COUNTS,
                'missing/duplicate point: '+profile)
        for row,spec in zip(records,plan):
            n = row['threads']
            expected = dict(arm='kdlock', repeat=0, workload='cacheline', lock_kind=family,
                write_percent=writes, cachelines=lines, cpus=list(range(n)),
                cpu_nodes=[0]*min(n,32)+[1]*max(0,n-32), collector_cpu=63,
                duration_ms=2000, peak_settle_ms=300, peak_window_ms=300, sample_ms=10,
                warmup_iterations_per_worker=48000, post_work_rounds=256, helper_waves=0,
                helper_cpus=[], mix_policy='evenly_spaced_worker_phase17', functional=False,
                delegate=True, caller_abi='clobber', call_shell='bulk_ioctl',
                entry_abi=3 if family == 'rwlock' else 2, spin_entry_ratio_limit=2,
                provider_ubsan='off', provider_mutex_policy=POLICY, delegation_batch_limit=1024)
            require(all(row.get(key) == value and spec.get(key) == value for key,value in expected.items()),
                    'point settings changed: '+row.get('name','unknown'))
            require(row.get('execution_status') == 'OK' and row.get('drained') is True and
                    row.get('retired') == RETIREMENT and row['measurement']['data_ok'] is True and
                    row['measurement']['complete'] is True, 'point correctness/drain failed')
            params = row['parameters']
            require(params.get('origin_instruction_force_suffix') == 'N' and
                    params.get('jit_timing') == 'N' and params.get('bench_quiet') == 'Y' and
                    params.get('bench_complete_probe') == 'Y', 'observation/diagnostic mode changed')
            require(0 <= row['jit_completions'] <= row['jit_bodies'] <= row['measurement']['writes'],
                    'invalid returned-JIT accounting')
            total += 1
        environment = load(OUT/profile/'environment.json')
        require(environment['topology']['role_cpus'] == [*range(60),63] and
                environment['topology']['role_nodes'] == [0]*32+[1]*29 and
                environment['python'] == PYTHON, 'point topology/interpreter changed')
        selected = load(OUT/profile/'source-sha256.json')
        require(all(sync['tracked_sha256'].get(name) == digest for name,digest in selected.items()),
                'profile source snapshot includes unmatched inputs')
        require((OUT/profile/'spin_batch.txt').read_text().strip() == '1024' and
                (OUT/profile/'mutex_batch.txt').read_text().strip() == '1024' and
                (OUT/profile/'mutex_numa_boundary.txt').read_text().strip() == '1024' and
                (OUT/profile/'mutex_batch_diag.txt').read_text().strip() == '0', 'provider build policy changed')
    require(total == 210, 'expected exactly210 KD-only measured points')
    return total


def run(args, idle, rt, functional_host):
    require(not any(path.exists() for path in (OUT,CONTROL,ARCHIVES)), 'preserve existing attempt')
    sync = reviewed(args.sync,args.sync_sha256)
    unchanged(sync)
    inputs = prerequisites(args,sync)
    original = reviewed(args.host_reference,args.host_reference_sha256)
    current = reviewed(args.host_before,args.host_before_sha256)
    admission = functional_host(original,current,datetime.datetime.now(datetime.timezone.utc),SNAPSHOT)
    require(original.get('performance_accepted') is False and current.get('performance_accepted') is False,
            'known exploratory qualification changed; review new timing context separately')
    selected = runpy.run_path(str(ROOT/'bench/rwlock_compare/run.py'))['sources']()
    require(selected and all(sync['tracked_sha256'].get(name) == digest for name,digest in selected.items()),
            'untracked/changed selected benchmark source input')
    topology = runpy.run_path(str(ROOT/'tests/protocols/cpu_placement.py'))['capture_topology']([*range(60),63])
    require(topology['role_nodes'] == [0]*32+[1]*29 and topology['online_cpus'] == list(range(64)),
            'original32/32 NUMA topology changed')
    idle(Path('/root'),rt.idle)
    require(shutil.disk_usage(OUT.parent).free > 8*1024**3, 'DATA free reserve insufficient')
    CONTROL.mkdir()
    inputs.update({'controller.py':Path(__file__).absolute(), 'host-reference.json':args.host_reference,
                   'host-before.json':args.host_before})
    for name,path in inputs.items():
        shutil.copyfile(path,CONTROL/name)
    receipt = dict(completed=False, source_commit=COMMIT, boot_id=BOOT, arm='kdlock',
        output=str(OUT), rounds_per_point=1, expected_points=210, driver_pid=os.getpid(),
        functional_campaign=str(args.functional_campaign), basic_campaign=str(args.basic_campaign),
        inputs={name:sha(CONTROL/name) for name in inputs}, host_admission=admission,
        topology=topology, performance_accepted=False, timing_qualification='exploratory; strict gate failed',
        endpoint_required=True, archive_required=True, comparison_pending=True,
        comparator_commits=['8617e97c02432a7c0b931aa8263d5edd0f6eb5b8','acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f'])
    command = [PYTHON,'bench/nano/best_case.py','--output',str(OUT),'--backends','kdlock',
        '--repeats','1','--delegate','on','--post-work-rounds','256','--mutex-batch-limit','1024',
        '--mutex-numa-boundary','1024','--threads',*map(str,COUNTS),
        '--kernel-source',KDIR,'--kernel-baseline',BUNDLE,'--kernel-variant','kdlock1']
    env = dict(os.environ,PATH=str(Path(PYTHON).parent)+':'+os.environ['PATH'],
        PYTHONDONTWRITEBYTECODE='1',KDLOCK_RECOVERY_CONFIRMED='1',KDLOCK_SNAPSHOT_TAG=SNAPSHOT)
    child = None
    save(CONTROL/'owner.json',receipt)
    try:
        with (CONTROL/'plan.json').open('xb') as output, (CONTROL/'plan.stderr').open('xb') as error:
            result = subprocess.run(command+['--plan-only'],cwd=ROOT,env=env,
                stdin=subprocess.DEVNULL,stdout=output,stderr=error,timeout=30)
        require(result.returncode == 0, 'plan-only invocation failed')
        plan_check(load(CONTROL/'plan.json'))
        unchanged(sync)
        receipt.update(command=command, started=time.time())
        with (CONTROL/'run.log').open('xb') as log:
            child = subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            receipt.update(pid=child.pid,state='RUNNING',
                start_ticks=(Path('/proc')/str(child.pid)/'stat').read_text().rsplit(')',1)[1].split()[19])
            save(CONTROL/'owner.json',receipt)
            code = child.wait(timeout=14400)
        receipt.update(returncode=code,state='EXITED',finished=time.time())
        save(CONTROL/'owner.json',receipt)
        require(code == 0, 'nano launcher failed; preserve all points and investigate drain')
        owner = load(OUT/'owner.json')
        require(owner['boot_id'] == BOOT and owner['provider_mutex_policy'] == POLICY and
                [row['profile'] for row in owner['blocks']] == [row[0] for row in PROFILES] and
                all(row['returncode'] == 0 and row['completion_unconfirmed'] is False for row in owner['blocks']) and
                all(a['finished'] <= b['started'] for a,b in zip(owner['blocks'],owner['blocks'][1:])),
                'nano block completion differs')
        points = verify_records(sync)
        stable_boot()
        unchanged(sync)
        idle(OUT,rt.idle)
        save(OUT/'final-health.json',dict(idle=True,boot_id=BOOT,time=time.time(),
            scope='completed point checks and final project idle; no independent dmesg claim'))
        receipt.update(completed=True,idle=True,validated_points=points,
            launcher_owner_sha256=sha(OUT/'owner.json'),source_manifest_sha256=sha(OUT/'source-sha256.json'))
        save(CONTROL/'owner.json',receipt)
    except BaseException as error:
        receipt.update(error=repr(error),completed=False)
        if child is not None:
            receipt.update(child_returncode=child.poll(),drain_unknown=True)
        save(CONTROL/'owner.json',receipt)
        raise
    print('COMPLETE origin-nano '+COMMIT,flush=True)


def archive(args,idle,rt,functional_host):
    owner = reviewed(CONTROL/'owner.json',args.run_owner_sha256)
    require(owner.get('completed') is True and owner.get('idle') is True and
            owner.get('source_commit') == COMMIT and owner.get('boot_id') == BOOT and
            owner.get('validated_points') == 210 and owner.get('returncode') == 0,
            'completed same-generation KD210 run required')
    require(sha(Path(__file__).absolute()) == owner['inputs']['controller.py'],
            'archive must use the exact frozen nano controller')
    require(not ARCHIVES.exists() and not (CONTROL/'archive-owner.json').exists(), 'preserve existing archive attempt')
    sync = reviewed(CONTROL/'sync.json',owner['inputs']['sync.json'])
    unchanged(sync)
    endpoint = reviewed(args.endpoint_receipt,args.endpoint_receipt_sha256)
    after = reviewed(args.host_after,args.host_after_sha256)
    require(endpoint.get('completed') is True and endpoint.get('returncode') == 0 and
            endpoint.get('source_commit') == COMMIT and
            endpoint.get('script_sha256') == ENDPOINT_CONTROLLER and
            endpoint.get('output_sha256') == args.host_after_sha256 and
            endpoint.get('completion_marker') == 'COMPLETE origin-nano '+COMMIT,
            'successful fresh endpoint required')
    before = reviewed(CONTROL/'host-before.json',owner['inputs']['host-before.json'])
    require(datetime.datetime.fromisoformat(after['captured_utc']) >=
            datetime.datetime.fromisoformat(before['captured_utc']), 'host endpoint precedes start capture')
    original = reviewed(CONTROL/'host-reference.json',owner['inputs']['host-reference.json'])
    admission = functional_host(original,after,datetime.datetime.now(datetime.timezone.utc),SNAPSHOT)
    require(after.get('performance_accepted') is False, 'endpoint timing qualification changed')
    require(sha(OUT/'owner.json') == owner['launcher_owner_sha256'] and
            sha(OUT/'source-sha256.json') == owner['source_manifest_sha256'], 'completed run metadata changed')
    verify_records(sync)
    idle(OUT,rt.idle)
    for name,path in {'host-after.json':args.host_after,'endpoint-receipt.json':args.endpoint_receipt}.items():
        require(not (CONTROL/name).exists(), 'preserve existing endpoint input')
        shutil.copyfile(path,CONTROL/name)
    receipt = dict(completed=False,source_commit=COMMIT,boot_id=BOOT,
        run_owner_sha256=args.run_owner_sha256,endpoint_receipt_sha256=args.endpoint_receipt_sha256,
        host_after_sha256=args.host_after_sha256,host_admission=admission,performance_accepted=False)
    save(CONTROL/'archive-owner.json',receipt)
    command = [PYTHON,str(ROOT/'bench/archive_run.py'),'--base',str(OUT),'--output',str(ARCHIVES),
        '--health',str(OUT/'final-health.json'),'--timeout-seconds','3600',
        '--kernel-variant','kdlock1','--kernel-source',KDIR,'--kernel-baseline',BUNDLE]
    for name,_,_,_ in PROFILES:
        command += ['--group',name+'='+name]
    child = None
    try:
        with (CONTROL/'archive.log').open('xb') as log:
            child = subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            receipt.update(pid=child.pid,argv=command)
            save(CONTROL/'archive-owner.json',receipt)
            code = child.wait(timeout=3660)
        receipt['returncode'] = code
        require(code == 0,'archive failed; preserve attempt')
        result = load(ARCHIVES/'archives.json')
        require(result.get('completed') is True and result.get('guest_idle') is True and
                result.get('boot_id') == BOOT and result.get('guest_base') == str(OUT),
                'archive completion is not confirmed')
        unchanged(sync)
        stable_boot()
        idle(OUT,rt.idle)
        receipt.update(completed=True,idle=True,archives_sha256=sha(ARCHIVES/'archives.json'),
                       comparison_pending=True)
        save(CONTROL/'archive-owner.json',receipt)
    except BaseException as error:
        receipt.update(error=repr(error),completed=False,drain_unknown=True)
        if child is not None:
            receipt['child_returncode'] = child.poll()
        save(CONTROL/'archive-owner.json',receipt)
        raise
    print('COMPLETE origin-nano archive '+COMMIT,flush=True)


def main():
    global COMMIT, OUT, CONTROL, ARCHIVES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('run','archive'))
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    for name in ('sync','unit','host-reference','host-before','host-after','endpoint-receipt'):
        parser.add_argument('--'+name,type=Path)
        parser.add_argument('--'+name+'-sha256')
    parser.add_argument('--functional-campaign',type=Path)
    parser.add_argument('--basic-campaign',type=Path)
    for name in ('basic-owner','origin-owner','rwsem-owner','mixed-owner','run-owner'):
        parser.add_argument('--'+name+'-sha256')
    args = parser.parse_args()
    if args.basic_campaign is None:
        args.basic_campaign = args.functional_campaign
    require(re.fullmatch('[0-9a-f]{40}', args.commit), 'exact validated source commit required')
    require(args.output.is_absolute() and args.output.resolve() == args.output and
            args.output.parent == Path('/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench') and
            args.commit[:8] in args.output.name, 'explicit generation-named DATA output required')
    COMMIT, OUT = args.commit, args.output
    CONTROL = OUT.with_name(OUT.name+'-control')
    ARCHIVES = OUT.with_name(OUT.name+'-archives')
    require(os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdlock1' and sys.executable == PYTHON,
            'intended guest and pinned Python required')
    require(not os.environ.get('KERNELRELEASE') and not os.environ.get('KBUILD_OUTPUT'), 'unexpected build override')
    stable_boot()
    sys.path[:0] = [str(ROOT/'bench/spin_cacheline'),str(ROOT/'bench/basic')]
    import bench_runtime as rt
    idle = runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle']
    functional_host = runpy.run_path(str(ROOT/'bench/basic/run.py'))['functional_host']
    idle(Path('/root'),rt.idle)
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            words = (proc/'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError,ProcessLookupError):
            continue
        require(not words or Path(os.fsdecode(words[0])).name not in ('make','gmake','cc1','cc1plus','ld.bfd'),
                'compiler/build remains active')
    (run if args.phase == 'run' else archive)(args,idle,rt,functional_host)


if __name__ == '__main__':
    main()
