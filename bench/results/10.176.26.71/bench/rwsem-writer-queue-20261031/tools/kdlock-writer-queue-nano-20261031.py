#!/usr/bin/env python3
"""Fresh source-bound KD210 arms: basic, run, local endpoint and archive phases.

Same frozen harness and one round per point. No retry, source mutation or reboot.
Historical unit/live checks retain their actual source and boot identities.
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
BOOT = None  # Explicit current ordinary-kernel boot for both fresh arms.
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
KDIR = '/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'
BUNDLE = '/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'
SNAPSHOT = None
OUT = CONTROL = ARCHIVES = None  # Required new output for this source generation.
COMMITS = ()
COHORT = ARM_INPUTS = None
RUNTIME_PATHS = ()
COMMON_PREFIXES = ('bench/basic/', 'bench/nano/', 'bench/rwlock_compare/', 'bench/spin_cacheline/', 'bench/tclock_compare/', 'bench/mmap_fault/', 'workload_modules/', 'include/', 'kernel_module/', 'daemon/', 'disassem/', 'tclock_backend/', 'tests/protocols/', 'kernel_baseline/', 'kernel_integration/')
COMMON_FILES = ('bench/archive_run.py',)
COMMON_HARNESS_SHA256 = None
BASIC = BASIC_CONTROL = None
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


def map_sha(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def configure_cohort(path, expected, commit):
    global COHORT, COMMITS, COMMON_HARNESS_SHA256, RUNTIME_PATHS, ARM_INPUTS
    cfg = reviewed(path, expected)
    require(cfg.get('schema') == 1 and cfg.get('performance_accepted') is False and
            isinstance(cfg.get('arms'), list) and len(cfg['arms']) == 2,
            'finalized two-arm cohort required')
    commits = tuple(row.get('commit') for row in cfg['arms'])
    require(all(isinstance(c,str) and re.fullmatch('[0-9a-f]{40}',c) for c in commits) and
            len(set(commits)) == 2 and commit in commits, 'exact distinct cohort commits required')
    require([row.get('label') for row in cfg['arms']] == ['baseline','candidate'],
            'baseline/candidate order must remain explicit')
    for row in cfg['arms']:
        for name in ('source_map_sha256','prior_unit_sha256','prior_live_sha256','prior_live_source_sha256'):
            require(isinstance(row.get(name),str) and re.fullmatch('[0-9a-f]{64}',row[name]),
                    'actual cohort source/prerequisite hash required: '+name)
    parent = Path(cfg.get('evidence_parent',''))
    require(parent in (Path('/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench'),
                       Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench')),
            'known DATA evidence parent required')
    for row in cfg['arms']:
        output = Path(row.get('output',''))
        require(output.parent == parent and row['commit'][:8] in output.name,
                'new generation-named cohort output required')
    paths = cfg.get('runtime_paths')
    require(isinstance(paths,list) and paths and len(paths) == len(set(paths)) and
            all(isinstance(name,str) and not Path(name).is_absolute() and
                '..' not in Path(name).parts and name.startswith(('include/','kernel_module/'))
                for name in paths), 'explicit runtime-only difference paths required')
    require(isinstance(cfg.get('common_input_sha256'),str) and
            re.fullmatch('[0-9a-f]{64}',cfg['common_input_sha256']),
            'actual common source digest required')
    COHORT, COMMITS = cfg, commits
    COMMON_HARNESS_SHA256, RUNTIME_PATHS = cfg['common_input_sha256'], tuple(paths)
    ARM_INPUTS = next(row for row in cfg['arms'] if row['commit'] == commit)


def unchanged(sync):
    require(map_sha(sync.get('tracked_sha256', {})) == ARM_INPUTS['source_map_sha256'],
            'source map differs from frozen cohort input')
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


def common_harness(sync):
    rows = {name: digest for name,digest in sync['tracked_sha256'].items()
            if (name.startswith(COMMON_PREFIXES) or name in COMMON_FILES)
            and name not in RUNTIME_PATHS}
    digest = hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(digest == COMMON_HARNESS_SHA256, 'common benchmark/provider inputs differ from both reviewed arms')
    return rows


def historical_inputs(args, sync):
    for name in ('prior_unit', 'prior_live', 'prior_live_source'):
        require(getattr(args, name+'_sha256') == ARM_INPUTS[name+'_sha256'],
                'source prerequisite differs from cohort: '+name)
    unit = reviewed(args.prior_unit,args.prior_unit_sha256)
    require(unit.get('source_commit') == COMMIT and
            (unit.get('passed') is True or unit.get('completed') is True),
            'successful same-source historical unit receipt required')
    if 'blocks' in unit:
        require(all(row.get('returncode') == 0 for row in unit['blocks']), 'historical unit/build block failed')
    else:
        require(unit.get('child_returncode') == 0 and unit.get('source_unchanged_after') is True,
                'historical focused unit failed or changed source')
    live = reviewed(args.prior_live,args.prior_live_sha256)
    require(live.get('passed') is True and live.get('drained',live.get('final_idle')) is True,
            'successful drained historical live result required')
    selected = reviewed(args.prior_live_source,args.prior_live_source_sha256)
    require(selected and selected.get('kernel_module/kd_rwsem.c') ==
            sync['tracked_sha256']['kernel_module/kd_rwsem.c'] and
            all(sync['tracked_sha256'].get(name) == digest for name,digest in selected.items()),
            'historical live source does not match this generation')
    inputs = {'prior-unit.json':args.prior_unit, 'prior-live.json':args.prior_live,
              'prior-live-source.json':args.prior_live_source}
    if unit.get('retained_checks'):
        # Keep the original failed overall receipt unchanged; only its selected
        # successful blocks qualify, with exact source equivalence for them.
        config_path = args.prior_unit.parent/'config.json'
        config = load(config_path)
        prior_sync_path = args.prior_unit.parent/'sync.json'
        prior_sync = reviewed(prior_sync_path,config['sync_sha256'])
        require(config.get('commit') == COMMIT and prior_sync.get('git_head') == COMMIT and
                prior_sync.get('tracked_sha256') == sync['tracked_sha256'] and
                len(config.get('retained_checks',[])) == len(unit['retained_checks']),
                'retained-check configuration differs from current receipt')
        inputs['prior-unit-config.json'] = config_path
        inputs['prior-unit-sync.json'] = prior_sync_path
        for index,(retained,spec) in enumerate(zip(unit['retained_checks'],config['retained_checks'])):
            history_path = Path(spec['result'])
            history = reviewed(history_path,spec['result_sha256'])
            old_sync_path = history_path.parent/'sync.json'
            old_sync = reviewed(old_sync_path,spec['sync_sha256'])
            before,after = old_sync['tracked_sha256'],sync['tracked_sha256']
            require(before.keys() == after.keys(), 'retained check source paths differ')
            changed = sorted(name for name in before if before[name] != after[name])
            allowed = ['tests/kernel/rwsem/README.md','tests/kernel/rwsem/payload/gate_signal.inc']
            require(changed == allowed and sorted(spec['changed_nonunit_paths']) == allowed and
                    retained.get('changed_nonunit_paths') == allowed and
                    retained.get('test_inputs_unchanged') is True and
                    retained.get('source_commit') == history.get('source_commit') == old_sync.get('git_head') and
                    retained.get('result') == str(history_path) and
                    retained.get('result_sha256') == spec['result_sha256'],
                    'retained selected checks lack exact input equivalence')
            selected = [row for row in history['blocks'] if row['name'] in spec['blocks']]
            require(selected == retained.get('blocks') and selected and
                    {row['name'] for row in selected} == set(spec['blocks']) and
                    all(row.get('returncode') == 0 for row in selected),
                    'retained selected block did not pass')
            prefix = 'retained-check-'+str(index)+'-'
            inputs[prefix+'result.json'] = history_path
            inputs[prefix+'sync.json'] = old_sync_path
            for row in selected:
                require(re.fullmatch('[a-z0-9_-]+',row['name']), 'invalid selected block name')
                log = history_path.parent/(row['name']+'.log')
                require(sha(log) == row['log_sha256'], 'retained selected block log differs')
                inputs[prefix+row['name']+'.log'] = log
    return inputs


def host_check(args, reference, current, functional_host):
    now = datetime.datetime.now(datetime.timezone.utc)
    functional = functional_host(reference,current,now,SNAPSHOT)
    compare = runpy.run_path(str(ROOT/'bench/mmap_fault/mm_platform.py'))['compare_host']
    return dict(functional=functional,
                timing=compare(reference,current,now,SNAPSHOT,args.host_mode == 'strict'))


def policy_check(args, reference):
    policy = reviewed(args.policy_receipt,args.policy_receipt_sha256)
    require(re.fullmatch('[0-9a-f]{64}',args.policy_controller_sha256 or '') and
            policy.get('controller_sha256') == args.policy_controller_sha256 and
            policy.get('action') == 'activate' and policy.get('completed') is True and
            policy.get('stable_worker_cohort_observed') is True and
            policy.get('policy_state_unknown') is False and
            policy.get('final_properties') == {'thread-pool-min':64,'thread-pool-max':64,'aio-max-batch':0} and
            policy.get('candidate_reference',{}).get('sha256') == args.host_reference_sha256 and
            policy.get('reference_tasks') == reference['qemu'][0]['tasks'],
            'actual completed new pool cohort/reference required')


def basic(args,idle,rt,functional_host):
    require(not BASIC.exists() and not BASIC_CONTROL.exists(), 'preserve existing basic attempt')
    sync = reviewed(args.sync,args.sync_sha256)
    unchanged(sync)
    common_harness(sync)
    inputs = historical_inputs(args,sync)
    reference = reviewed(args.host_reference,args.host_reference_sha256)
    before = reviewed(args.host_before,args.host_before_sha256)
    admission = host_check(args,reference,before,functional_host)
    policy_check(args,reference)
    idle(Path('/root'),rt.idle)
    BASIC_CONTROL.mkdir()
    inputs.update({'cohort.json':args.cohort_file,'sync.json':args.sync,'host-reference.json':args.host_reference,
                   'host-before.json':args.host_before,'policy-receipt.json':args.policy_receipt,
                   'controller.py':Path(__file__).absolute()})
    for name,path in inputs.items():
        shutil.copyfile(path,BASIC_CONTROL/name)
    owner = dict(completed=False,source_commit=COMMIT,boot_id=BOOT,phase='basic',
                 timing_started=False,prior_checks_historical=True,prior_boot_id=load(args.prior_unit).get('boot_id'),
                 inputs={name:sha(BASIC_CONTROL/name) for name in inputs},host_admission=admission,
                 policy_controller_sha256=args.policy_controller_sha256,
                 common_harness_sha256=COMMON_HARNESS_SHA256,performance_accepted=False)
    save(BASIC_CONTROL/'owner.json',owner)
    argv=[PYTHON,str(ROOT/'bench/basic/run.py'),'--output',str(BASIC),'--families',
          'spin','mutex','rwlock','rwsem','--snapshot-tag',SNAPSHOT,
          '--host-reference',str(args.host_reference),'--host-reference-sha256',args.host_reference_sha256,
          '--host-state',str(args.host_before),'--kernel-variant','kdlock1',
          '--kernel-source',KDIR,'--kernel-baseline',BUNDLE]
    child=None
    try:
        env=dict(os.environ,PATH=str(Path(PYTHON).parent)+':'+os.environ['PATH'],
                 PYTHONDONTWRITEBYTECODE='1',KDLOCK_RECOVERY_CONFIRMED='1',KDLOCK_SNAPSHOT_TAG=SNAPSHOT)
        with (BASIC_CONTROL/'run.log').open('xb') as log:
            child=subprocess.Popen(argv,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                                   stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            owner.update(state='RUNNING',pid=child.pid,argv=argv)
            save(BASIC_CONTROL/'owner.json',owner)
            code=child.wait(timeout=7600)
        owner.update(returncode=code,state='EXITED')
        require(code == 0,'fresh four-family basic failed')
        result=load(BASIC/'result.json')
        require(result.get('passed') is True and result.get('final_idle') is True and
                result.get('boot_id') == BOOT and result.get('timing_started') is False and
                [row['family'] for row in result['results']] == ['spin','mutex','rwlock','rwsem'] and
                all(row['passed'] and row['drained'] and row['jit_completions'] > 0 for row in result['results']),
                'fresh four-family returned-body proof incomplete')
        for family in ('spin','mutex','rwlock','rwsem'):
            selected=load(BASIC/family/'source-sha256.json')
            require(selected and selected.get('kernel_module/kd_rwsem.c') ==
                    sync['tracked_sha256']['kernel_module/kd_rwsem.c'] and
                    all(sync['tracked_sha256'].get(name)==digest
                        for name,digest in selected.items() if name in sync['tracked_sha256']) and
                    all(name.startswith('bench/spin_cacheline/.build/provider/')
                        for name in selected if name not in sync['tracked_sha256']) and
                    all(sha(BASIC/family/'source'/name)==digest for name,digest in selected.items()),
                    'fresh basic source snapshot differs: '+family)
        unchanged(sync)
        stable_boot()
        idle(BASIC,rt.idle)
        owner.update(completed=True,final_idle=True,result_sha256=sha(BASIC/'result.json'))
        save(BASIC_CONTROL/'owner.json',owner)
    except BaseException as error:
        owner.update(completed=False,error=repr(error))
        if child is not None:
            owner.update(child_returncode=child.poll(),drain_unknown=True)
        save(BASIC_CONTROL/'owner.json',owner)
        raise
    print('COMPLETE writer-queue-nano basic '+COMMIT,flush=True)


def prerequisites(args,sync):
    common_harness(sync)
    if args.basic_result is not None:
        require(args.basic_owner_sha256 is None, 'select one exact basic evidence route')
        result = reviewed(args.basic_result,args.basic_result_sha256)
        base = args.basic_result.parent
        require(not base.is_relative_to(ROOT) and base.is_relative_to(Path(COHORT['evidence_parent']).parent),
                'standalone basic must remain in this DATA evidence root')
        require(result.get('passed') is True and result.get('final_idle') is True and
                result.get('boot_id') == BOOT and result.get('timing_started') is False and
                result.get('snapshot_tag') == SNAPSHOT and
                result.get('host_reference_sha256') == args.host_reference_sha256 and
                [row['family'] for row in result['results']] == ['spin','mutex','rwlock','rwsem'] and
                all(row['passed'] and row['drained'] and row['jit_completions'] > 0 for row in result['results']),
                'actual fresh maintained basic result incomplete')
        require(sha(base/'reference-host.json') == args.host_reference_sha256,
                'standalone basic used another host reference')
        for family in ('spin','mutex','rwlock','rwsem'):
            selected = load(base/family/'source-sha256.json')
            require(selected and selected.get('kernel_module/kd_rwsem.c') ==
                    sync['tracked_sha256']['kernel_module/kd_rwsem.c'] and
                    all(sync['tracked_sha256'].get(name) == digest
                        for name,digest in selected.items() if name in sync['tracked_sha256']) and
                    all(name.startswith('bench/spin_cacheline/.build/provider/')
                        for name in selected if name not in sync['tracked_sha256']) and
                    all(sha(base/family/'source'/name) == digest for name,digest in selected.items()),
                    'standalone basic source snapshot differs: '+family)
        inputs = historical_inputs(args,sync)
        inputs.update({'basic-result.json':args.basic_result,'sync.json':args.sync,
                       'cohort.json':args.cohort_file,'policy-receipt.json':args.policy_receipt})
        args.basic_campaign = str(base)
        args.basic_evidence_mode = 'maintained-result'
        return inputs
    owner=reviewed(BASIC_CONTROL/'owner.json',args.basic_owner_sha256)
    require(owner.get('completed') is True and owner.get('final_idle') is True and
            owner.get('source_commit') == COMMIT and owner.get('boot_id') == BOOT and
            owner.get('returncode') == 0 and owner.get('inputs',{}).get('sync.json') == args.sync_sha256 and
            owner['inputs'].get('controller.py') == sha(Path(__file__).absolute()) and
            owner['inputs'].get('host-reference.json') == args.host_reference_sha256 and
            owner['inputs'].get('cohort.json') == args.cohort_sha256 and
            owner.get('policy_controller_sha256') == args.policy_controller_sha256 and
            owner['inputs'].get('policy-receipt.json') == args.policy_receipt_sha256,
            'fresh same-source/boot/cohort basic prerequisite incomplete')
    result=reviewed(BASIC/'result.json',owner['result_sha256'])
    require(result.get('passed') is True and result.get('final_idle') is True, 'basic result changed')
    inputs={'basic-owner.json':BASIC_CONTROL/'owner.json','basic-result.json':BASIC/'result.json','sync.json':args.sync,'cohort.json':args.cohort_file}
    for name in owner['inputs']:
        if name.startswith(('prior-','retained-check-')) or name == 'policy-receipt.json':
            require(sha(BASIC_CONTROL/name)==owner['inputs'][name],'retained prerequisite changed: '+name)
            inputs[name]=BASIC_CONTROL/name
    args.basic_campaign = str(BASIC)
    args.basic_evidence_mode = 'controller-owned'
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
    admission = host_check(args,original,current,functional_host)
    policy_check(args,original)
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
        basic_campaign=args.basic_campaign, basic_evidence_mode=args.basic_evidence_mode,
        source_prerequisites_retained=True, host_mode=args.host_mode,
        policy_controller_sha256=args.policy_controller_sha256,
        common_harness_sha256=COMMON_HARNESS_SHA256,
        inputs={name:sha(CONTROL/name) for name in inputs}, host_admission=admission,
        topology=topology, performance_accepted=False, timing_qualification=admission['timing'],
        endpoint_required=True, archive_required=True, comparison_pending=True,
        comparator_commits=list(COMMITS), historical_timings_reused=False)
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
    print('COMPLETE writer-queue-nano '+COMMIT,flush=True)


def archive(args,idle,rt,functional_host):
    owner = reviewed(CONTROL/'owner.json',args.run_owner_sha256)
    require(owner.get('completed') is True and owner.get('idle') is True and
            owner.get('source_commit') == COMMIT and owner.get('boot_id') == BOOT and
            owner.get('validated_points') == 210 and owner.get('returncode') == 0,
            'completed same-generation KD210 run required')
    require(sha(Path(__file__).absolute()) == owner['inputs']['controller.py'] and
            owner['inputs'].get('cohort.json') == args.cohort_sha256,
            'archive must use the exact frozen nano controller')
    require(not ARCHIVES.exists() and not (CONTROL/'archive-owner.json').exists(), 'preserve existing archive attempt')
    sync = reviewed(CONTROL/'sync.json',owner['inputs']['sync.json'])
    unchanged(sync)
    endpoint = reviewed(args.endpoint_receipt,args.endpoint_receipt_sha256)
    after = reviewed(args.host_after,args.host_after_sha256)
    endpoint_policy = reviewed(args.endpoint_policy,args.endpoint_policy_sha256)
    require(re.fullmatch('[0-9a-f]{64}',args.endpoint_controller_sha256 or '') and
            endpoint.get('completed') is True and endpoint.get('returncode') == 0 and
            endpoint.get('source_commit') == COMMIT and
            endpoint.get('script_sha256') == args.endpoint_controller_sha256 and
            endpoint.get('cohort_sha256') == args.cohort_sha256 and
            endpoint.get('output_sha256') == args.host_after_sha256 and
            endpoint.get('endpoint_policy_sha256') == args.endpoint_policy_sha256 and
            endpoint.get('completion_marker') == 'COMPLETE writer-queue-nano '+COMMIT,
            'successful fresh endpoint required')
    require(args.policy_controller_sha256 == owner['policy_controller_sha256'] and
            endpoint_policy.get('controller_sha256') == args.policy_controller_sha256 and
            endpoint_policy.get('action') == 'verify' and endpoint_policy.get('completed') is True and
            endpoint_policy.get('mutation_attempted') is False and
            endpoint_policy.get('policy_state_unknown') is False and
            endpoint_policy.get('activation_receipt_sha256') == owner['inputs']['policy-receipt.json'] and
            endpoint_policy.get('final_properties') == {'thread-pool-min':64,'thread-pool-max':64,'aio-max-batch':0} and
            endpoint_policy.get('captures',{}).get('after',{}).get('sha256') == args.host_after_sha256,
            'read-only endpoint pool verification differs')
    before = reviewed(CONTROL/'host-before.json',owner['inputs']['host-before.json'])
    require(datetime.datetime.fromisoformat(after['captured_utc']) >=
            datetime.datetime.fromisoformat(before['captured_utc']), 'host endpoint precedes start capture')
    original = reviewed(CONTROL/'host-reference.json',owner['inputs']['host-reference.json'])
    require(args.host_mode == owner['host_mode'], 'endpoint host classification differs')
    admission = host_check(args,original,after,functional_host)
    stamp = datetime.datetime.fromisoformat(after['captured_utc']).timestamp()
    require(0 <= stamp - owner['finished'] <= 300, 'endpoint is not immediate after completion')
    require(sha(OUT/'owner.json') == owner['launcher_owner_sha256'] and
            sha(OUT/'source-sha256.json') == owner['source_manifest_sha256'], 'completed run metadata changed')
    verify_records(sync)
    idle(OUT,rt.idle)
    for name,path in {'host-after.json':args.host_after,'endpoint-receipt.json':args.endpoint_receipt,
                      'endpoint-policy.json':args.endpoint_policy}.items():
        require(not (CONTROL/name).exists(), 'preserve existing endpoint input')
        shutil.copyfile(path,CONTROL/name)
    receipt = dict(completed=False,source_commit=COMMIT,boot_id=BOOT,
        run_owner_sha256=args.run_owner_sha256,endpoint_receipt_sha256=args.endpoint_receipt_sha256,
        endpoint_policy_sha256=args.endpoint_policy_sha256,
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
    print('COMPLETE writer-queue-nano archive '+COMMIT,flush=True)


def main():
    global COMMIT, OUT, CONTROL, ARCHIVES, BOOT, SNAPSHOT, BASIC, BASIC_CONTROL
    if len(sys.argv) > 1 and sys.argv[1] == 'endpoint':
        endpoint_main(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('basic','run','archive'))
    parser.add_argument('--commit', required=True)
    parser.add_argument('--cohort-file', type=Path, required=True)
    parser.add_argument('--cohort-sha256', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--snapshot-tag', required=True)
    parser.add_argument('--host-mode', choices=('strict','exploratory'), required=True)
    parser.add_argument('--policy-controller-sha256', required=True)
    parser.add_argument('--endpoint-controller-sha256')
    parser.add_argument('--basic-result', type=Path)
    parser.add_argument('--basic-result-sha256')
    parser.add_argument('--output', type=Path, required=True)
    for name in ('sync','prior-unit','prior-live','prior-live-source','policy-receipt',
                 'host-reference','host-before','host-after','endpoint-receipt','endpoint-policy'):
        parser.add_argument('--'+name,type=Path)
        parser.add_argument('--'+name+'-sha256')
    for name in ('basic-owner','run-owner'):
        parser.add_argument('--'+name+'-sha256')
    args = parser.parse_args()
    configure_cohort(args.cohort_file, args.cohort_sha256, args.commit)
    BOOT, SNAPSHOT = args.boot_id, args.snapshot_tag
    require(re.fullmatch('[0-9a-f]{40}', args.commit), 'exact validated source commit required')
    require(args.output.is_absolute() and args.output.resolve() == args.output and
            args.output.parent == Path(COHORT['evidence_parent']) and
            args.output == Path(ARM_INPUTS['output']) and
            args.commit[:8] in args.output.name, 'explicit cohort generation-named DATA output required')
    COMMIT, OUT = args.commit, args.output
    CONTROL = OUT.with_name(OUT.name+'-control')
    ARCHIVES = OUT.with_name(OUT.name+'-archives')
    BASIC = OUT.with_name(OUT.name+'-basic')
    BASIC_CONTROL = OUT.with_name(OUT.name+'-basic-control')
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
    {'basic':basic,'run':run,'archive':archive}[args.phase](args,idle,rt,functional_host)


import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import signal
import subprocess
import time

POOL = '/tmp/kdlock-writer-queue-pool-20261031.py'
POOL_SHA = '6f1f718b6ba72b9b4899b3437e6211d8dd891f4041acd7aca36906c12953b8b4'
CAPTURE = '/tmp/kdlock-qemu-stable-pool-capture-host-20261030.py'
INVENTORY = '/tmp/kdlock-qemu-readonly-inventory-20261030.json'
SSH = ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','eric@10.176.26.71']
VERIFY = '''import hashlib,json,os,pathlib,sys
x=json.loads(sys.argv[1]);p=pathlib.Path(x['script'])
assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
os.execv('/usr/bin/python3',['python3',str(p),*x['args']])
'''
READ = '''import base64,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);r=p/'result.json';v=json.loads(r.read_bytes())
assert v['action']=='verify' and v['completed'] is True
h=p/'after.host.json';assert v['captures']['after']['path']==str(h)
print(json.dumps({'policy':base64.b64encode(r.read_bytes()).decode(),'host':base64.b64encode(h.read_bytes()).decode()}))
'''

def endpoint_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def endpoint_require(ok,text):
    if not ok:raise RuntimeError(text)

def endpoint_main(argv):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--commit',required=True)
    p.add_argument('--cohort-file',type=Path,required=True)
    p.add_argument('--cohort-sha256',required=True)
    p.add_argument('--run-log',type=Path,required=True)
    p.add_argument('--output-prefix',type=Path,required=True)
    p.add_argument('--host-output',type=Path,required=True)
    p.add_argument('--policy',required=True)
    p.add_argument('--policy-sha256',required=True)
    p.add_argument('--snapshot-tag',required=True)
    p.add_argument('--cohort',required=True)
    a=p.parse_args(argv)
    configure_cohort(a.cohort_file,a.cohort_sha256,a.commit)
    endpoint_require(a.run_log.is_absolute() and a.output_prefix.is_absolute() and
            a.host_output.is_absolute(),'absolute paths required')
    marker='COMPLETE writer-queue-nano '+a.commit
    output=Path(str(a.output_prefix)+'.json')
    policy_output=Path(str(a.output_prefix)+'-policy.json')
    receipt=Path(str(a.output_prefix)+'-receipt.json')
    endpoint_require(not any(x.exists() for x in (output,policy_output,receipt)),'preserve existing endpoint attempt')
    record=dict(schema=1,completed=False,state='WAITING_LOCAL_RUN',source_commit=a.commit,
                completion_marker=marker,script_sha256=endpoint_sha(__file__),started=time.time(),
                cohort_sha256=a.cohort_sha256,
                policy_controller_sha256=POOL_SHA,activation_receipt_sha256=a.policy_sha256,
                snapshot_tag=a.snapshot_tag,cohort=a.cohort,host_output=str(a.host_output),
                performance_accepted=False,guest_work_started=False,calls=[])
    def save():
        temp=receipt.with_name('.'+receipt.name+'.tmp')
        temp.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n');temp.replace(receipt)
    def interrupted(signum,frame):raise InterruptedError('endpoint interrupted; child retained')
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
    child=None
    def call(name,argv):
        nonlocal child
        out=Path(str(a.output_prefix)+'-'+name+'.stdout');err=Path(str(a.output_prefix)+'-'+name+'.stderr')
        row=dict(name=name,argv=argv,started=time.time());record['calls'].append(row);save()
        with out.open('xb') as stdout,err.open('xb') as stderr:
            child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
            row['pid']=child.pid;save();code=child.wait(timeout=120)
        row.update(returncode=code,finished=time.time(),stdout_sha256=endpoint_sha(out),stderr_sha256=endpoint_sha(err));save()
        endpoint_require(code==0,name+' failed; preserve endpoint attempt')
        child=None
        return out.read_bytes()
    save()
    try:
        deadline=time.monotonic()+14500
        while time.monotonic()<deadline:
            text=a.run_log.read_text() if a.run_log.exists() else ''
            if marker+'\n' in text:break
            endpoint_require('Traceback (most recent call last):' not in text,'nano run failed before completion')
            time.sleep(5)
        else:raise TimeoutError('no completed local run; no host action started')
        record.update(state='HOST_ENDPOINT',run_log=str(a.run_log),run_log_sha256=endpoint_sha(a.run_log))
        args=['verify','--capture-helper',CAPTURE,'--inventory',INVENTORY,
              '--snapshot',a.snapshot_tag,'--cohort',a.cohort,'--policy',a.policy,
              '--policy-sha256',a.policy_sha256,'--output',str(a.host_output)]
        request=dict(script=POOL,sha256=POOL_SHA,args=args)
        call('verify',[*SSH,shlex.join(['sudo','-n','taskset','-c','63','python3','-c',VERIFY,json.dumps(request)])])
        raw=json.loads(call('read',[*SSH,shlex.join(['sudo','-n','python3','-c',READ,str(a.host_output)])]))
        policy_bytes=base64.b64decode(raw['policy'],validate=True)
        host_bytes=base64.b64decode(raw['host'],validate=True)
        policy=json.loads(policy_bytes);host=json.loads(host_bytes)
        host_sha=hashlib.sha256(host_bytes).hexdigest()
        endpoint_require(policy.get('action')=='verify' and policy.get('completed') is True and
                policy.get('controller_sha256')==POOL_SHA and policy.get('mutation_attempted') is False and
                policy.get('policy_state_unknown') is False and
                policy.get('activation_receipt_sha256')==a.policy_sha256 and
                policy.get('final_properties')=={'thread-pool-min':64,'thread-pool-max':64,'aio-max-batch':0} and
                policy['captures']['after']['sha256']==host_sha and host['recovery_snapshot']==a.snapshot_tag,
                'actual verified pool endpoint differs')
        with output.open('xb') as f:f.write(host_bytes)
        with policy_output.open('xb') as f:f.write(policy_bytes)
        record.update(completed=True,state='COMPLETE',returncode=0,output=str(output),output_sha256=host_sha,
                      endpoint_policy=str(policy_output),endpoint_policy_sha256=endpoint_sha(policy_output))
    except BaseException as error:
        record.update(completed=False,state='FAILED',error=repr(error))
        if child is not None:record.update(child_pid=child.pid,child_returncode=child.poll(),host_child_completion_unknown=True)
        raise
    finally:
        record['finished']=time.time();save()
    print(json.dumps(record),flush=True)


if __name__ == '__main__':
    main()
