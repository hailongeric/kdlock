#!/usr/bin/env python3
"""One explicitly bound MM step for either fresh comparison arm; VM only."""
import argparse,datetime,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
STEPS=('sites','api','mapping','faults','completed','strict-hold','mmap1-identity','mmap1-measure','endpoint')
COUNTS=[*range(1,9),*range(12,61,4)]
POLICY='mmap-functional-held-writer-v1'
MUTATIONS=['different_lock','wrong_caller_return','wrong_wait_return','wrong_adapter_return',
           'running_task','other_wait_channel','rescheduled_task','missing_chain','missing_writer_proof']


def need(value,message):
    if not value:raise RuntimeError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(4<<20),b''):h.update(chunk)
    return h.hexdigest()


def checked(reference):
    path=Path(reference['path'])
    need(path.is_file() and not path.is_symlink() and sha(path)==reference['sha256'],'input bytes differ: '+str(path))
    return json.loads(path.read_bytes())


def ref(path):return dict(path=str(Path(path)),sha256=sha(path))


def group_members(group):
    result=[]
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields=path.read_text().rsplit(')',1)[1].split()
            if int(fields[2])==group:result.append(dict(pid=int(path.parent.name),state=fields[0]))
        except (FileNotFoundError,ProcessLookupError):pass
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('step',choices=STEPS)
    for name in ('config','bindings','output'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('config-sha256','bindings-sha256'):p.add_argument('--'+name,required=True)
    a=p.parse_args();c=checked(dict(path=a.config,sha256=a.config_sha256));b=checked(dict(path=a.bindings,sha256=a.bindings_sha256))
    need(c.get('schema')==b.get('schema')==1 and c['eligibility_policy']==POLICY,'explicit campaign/eligibility required')
    root=Path('/root/host_fs/kdlock');h=c['harness'];recipe=Path(h['source']);manifest=checked(h['manifest'])
    arm_name=b['arm'];arm=c['arms'][arm_name];mode=arm_name;need(mode in ('native','kd'), 'explicit mode required');base=Path(c['campaign'])/arm_name;out=a.output;run=out/'run'
    logs=Path(c['campaign']).with_name(Path(c['campaign']).name+'-controller-logs')/arm_name
    need(out.is_absolute() and out.parent==base and out.resolve()==out and not out.exists(),'new direct arm attempt directory required')
    need(os.geteuid()==0 and sys.executable==c['python'] and os.uname().release==arm['release'],'guest/interpreter/release differs')
    need(not os.environ.get('KERNELRELEASE') and not os.environ.get('KBUILD_OUTPUT'),'external Kbuild override refused')
    need(root.is_mount() and os.path.samefile(root,recipe) and os.statvfs(root).f_flag & os.ST_RDONLY,'exact read-only canonical common source required')
    need(manifest['source_commit']==h['commit'] and re.fullmatch('[0-9a-f]{40}',h['commit']),'common harness commit differs')
    def recipe_check():
        need(root.is_mount() and os.path.samefile(root,recipe) and os.statvfs(root).f_flag & os.ST_RDONLY,'common source view changed')
        need(sha(h['manifest']['path'])==h['manifest']['sha256'],'harness manifest changed')
        for name,row in manifest['files'].items():
            if row['kind']=='directory':
                need((root/name).is_dir(), 'harness directory missing: '+name)
                continue
            path=root/name
            need(not Path(name).is_absolute() and '..' not in Path(name).parts and row['kind']=='file' and
                 path.is_file() and not path.is_symlink() and sha(path)==row['sha256'],'common harness bytes differ: '+name)
    def boot_check():
        need(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==b['boot_id'] and
             [word for word in Path('/proc/cmdline').read_text().split() if word.startswith('kd_mmap=')]==['kd_mmap='+('on' if mode=='kd' else 'off')],'same selected boot required')
    recipe_check();boot_check();bundle=Path(arm['bundle'])/'manifest.json'
    checked(dict(path=bundle,sha256=b['bundle_manifest_sha256']))
    app=c['application'];inputs=checked(app['inputs']);prepared=checked(app['preparation'])
    need(prepared.get('passed') is True and prepared.get('action')=='prepare' and prepared['inputs_sha256']==app['inputs']['sha256'] and
         inputs['binary_sha256']==app['binary_sha256'],'original application preparation differs')
    pool=c['pool'];activation=checked(pool['activation']);reference=checked(pool['reference'])
    current=checked(b['host_state']);verification=checked(b['pool_verification'])
    properties={'thread-pool-min':64,'thread-pool-max':64,'aio-max-batch':0}
    need(activation.get('completed') is True and activation.get('action')=='activate' and activation.get('cohort')==pool['cohort'] and
         activation.get('controller_sha256')==pool['controller_sha256'] and activation.get('stable_worker_cohort_observed') is True and
         activation.get('policy_state_unknown') is False and activation.get('final_properties')==properties and
         activation['candidate_reference']['sha256']==pool['reference']['sha256'] and
         activation['reference_tasks']==reference['qemu'][0]['tasks'],'actual fresh pool cohort differs')
    need(verification.get('completed') is True and verification.get('action')=='verify' and verification.get('cohort')==pool['cohort'] and
         verification.get('controller_sha256')==pool['controller_sha256'] and verification.get('mutation_attempted') is False and
         verification.get('policy_state_unknown') is False and verification.get('final_properties')==properties and
         verification['activation_receipt_sha256']==pool['activation']['sha256'] and
         verification['captures']['after']['sha256']==b['host_state']['sha256'],'fresh host verification differs')
    need(os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1' and os.environ.get('KDLOCK_SNAPSHOT_TAG')==pool['snapshot'],'actual recovery acknowledgement required')
    spec=importlib.util.spec_from_file_location('writer_queue_mm_benchmark',root/'bench/mmap1/run.py')
    bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
    now=datetime.datetime.now(datetime.timezone.utc)
    admission=bench.platform.compare_host(reference,current,now,pool['snapshot'],True)
    need(admission['original_threads']==admission['observed_threads']==131,'fresh strict task map differs')
    bench.inputs_from(Path(app['inputs']['path']));bench.idle()
    required={'mapping':('sites','api'),'strict-hold':('sites','api','mapping'),
              'mmap1-measure':('api','mapping','faults','completed','strict-hold','mmap1-identity'),
              'endpoint':('mmap1-measure',)}.get(a.step,())
    given=b.get('prerequisite_owners',{});need(set(given)==set(required),'exact prerequisite set required')
    owners={};results={};bindings={item['path']:item['sha256'] for item in (app['inputs'],app['preparation'])}
    for step in required:
        owner=checked(given[step]);result=checked(owner['result'])
        need(owner.get('completed') is True and owner.get('passed') is True and owner.get('drained') is True and
             owner.get('final_idle') is True and owner.get('drain_unknown') is False and owner.get('state')=='COMPLETE' and
             owner['controller_sha256']==sha(__file__) and owner['config_sha256']==a.config_sha256 and owner['step']==step and
             owner['arm']==arm_name and owner['boot_id']==b['boot_id'] and owner['kernel']==arm and
             owner['bundle_manifest_sha256']==b['bundle_manifest_sha256'] and owner['harness_commit']==h['commit'] and
             owner['harness_manifest_sha256']==h['manifest']['sha256'] and owner['pool_activation_sha256']==pool['activation']['sha256'] and
             owner['host_reference_sha256']==pool['reference']['sha256'],'same-generation/boot prerequisite differs: '+step)
        owners[step]=owner;results[step]=result
        for item in (given[step],owner['result']):bindings[item['path']]=item['sha256']
    host_args=['--host-state',b['host_state']['path'],'--host-reference',pool['reference']['path'],
               '--host-reference-sha256',pool['reference']['sha256']]
    kernel_args=['--kernel-variant',arm['variant'],'--kernel-source',arm['build'],'--kernel-baseline',arm['bundle']]
    platform=['--mode',mode,'--boot-id',b['boot_id'],*kernel_args,*host_args]
    def result_path(step):return owners[step]['result']['path']
    if a.step=='sites':argv=[c['python'],'bench/mmap_writer/sites.py','--mode',mode,'--boot-id',b['boot_id'],*kernel_args,'--output',str(run)]
    elif a.step=='api':argv=[c['python'],'tests/kernel/mmap_lock/run.py',*platform,'--output',str(run)]
    elif a.step=='mapping':
        adapter=c['mapping_adapter'];need(sha(adapter['path'])==adapter['sha256'] and
             sha(root/'tests/kernel/mmap_lock/mapping.py')==adapter['base_mapping_sha256'],'mapping adapter/base source differs')
        argv=[c['python'],adapter['path'],*platform,'--api-result',result_path('api'),'--writer-sites',result_path('sites'),
              '--writer-sites-sha256',owners['sites']['result']['sha256'],'--eligibility-policy','mmap-functional-v1',
              '--runner-sha256',adapter['sha256'],'--harness-commit',h['commit'],'--output',str(run)]
        bindings[adapter['path']]=adapter['sha256']
    elif a.step in ('faults','completed'):
        script='tests/kernel/mmap_lock/faults.py' if a.step=='faults' else 'tests/kernel/mmap_lock/page_fault_completed/run.py'
        argv=[c['python'],script,*platform,'--output',str(run)]
    elif a.step=='strict-hold':
        diagnostic=c['strict_diagnostic'];dm=checked(diagnostic['manifest'])
        need(dm['commit']==diagnostic['commit'] and sha(diagnostic['runner']['path'])==diagnostic['runner']['sha256'], 'diagnostic generation differs')
        argv=[c['python'],diagnostic['runner']['path'],*platform,'--api-result',result_path('api'),'--api-result-sha256',owners['api']['result']['sha256'],
              '--writer-sites',result_path('sites'),'--writer-sites-sha256',owners['sites']['result']['sha256'],
              '--diagnostic-manifest',diagnostic['manifest']['path'],'--diagnostic-manifest-sha256',diagnostic['manifest']['sha256'],
              '--harness-source',h['source'],'--harness-manifest',h['manifest']['path'],'--harness-manifest-sha256',h['manifest']['sha256'],
              '--harness-commit',h['commit'],'--output',str(run)]
        bindings[diagnostic['runner']['path']]=diagnostic['runner']['sha256'];bindings[diagnostic['manifest']['path']]=diagnostic['manifest']['sha256']
    elif a.step=='mmap1-identity':
        identity=c['identity_adapter'];need(sha(identity['path'])==identity['sha256'],'identity adapter differs')
        argv=[c['python'],identity['path'],*platform,'--inputs',app['inputs']['path'],'--output',str(run)]
        bindings[identity['path']]=identity['sha256']
    elif a.step=='mmap1-measure':
        need(results['mapping'].get('eligibility_policy')=='mmap-functional-v1' and len(results['mapping']['cases'])==6,'six prospective mapping cases required')
        held=results['strict-hold'];need(held.get('diagnostic')=='same-mm-held-writer-v1' and held.get('final_idle') is True and
             held.get('harness_commit')==h['commit'] and held.get('harness_manifest_sha256')==h['manifest']['sha256'] and
             held.get('diagnostic_commit')==c['strict_diagnostic']['commit'] and
             [case['operation'] for case in held['cases']]==['mmap','munmap'] and
             all(case.get('passed') is True and case['rejected_mutations']==MUTATIONS for case in held['cases']), 'both fresh exact held-writer witnesses required')
        argv=[c['python'],'bench/mmap1/run.py','measure',*platform,
              *[item for step in ('api','mapping','faults','completed') for item in ('--'+step+'-result',result_path(step))],
              '--inputs',app['inputs']['path'],'--identity-result',result_path('mmap1-identity'),'--model','both','--output',str(run)]
    else:argv=[]
    logs.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=False)
    active_log=logs/(out.name+'.log');need(not active_log.exists(),'external log already exists')
    control=out/'owner.json';r=dict(schema=1,state='ADMISSION',completed=False,passed=False,drained=False,final_idle=False,drain_unknown=False,
        arm=arm_name,step=a.step,boot_id=b['boot_id'],kernel=arm,config_sha256=a.config_sha256,bindings_sha256=a.bindings_sha256,
        controller_sha256=sha(__file__),harness_commit=h['commit'],harness_manifest_sha256=h['manifest']['sha256'],
        bundle_manifest_sha256=b['bundle_manifest_sha256'],pool_activation_sha256=pool['activation']['sha256'],
        host_reference_sha256=pool['reference']['sha256'],host_state_sha256=b['host_state']['sha256'],
        pool_verification_sha256=b['pool_verification']['sha256'],host_admission=admission,eligibility_policy=POLICY,
        application=app,prerequisite_owners=given,prerequisite_bindings=bindings,argv=argv,cwd=str(root),output=str(out),
        started=time.time(),child_started=False,child_returncode=None,performance_accepted=False)
    def save(path,value):
        temporary=logs/(out.name+'.'+path.name+'.tmp')
        with temporary.open('w') as stream:json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        temporary.replace(path);directory=os.open(path.parent,os.O_DIRECTORY);os.fsync(directory);os.close(directory)
    def persist():save(control,r)
    child=None;persist()
    try:
        retained=out/'inputs';retained.mkdir()
        inputs_to_copy={'config.json':a.config,'bindings.json':a.bindings,'controller.py':Path(__file__),
                       'harness-manifest.json':Path(h['manifest']['path']),'host-before.json':Path(b['host_state']['path']),
                       'host-reference.json':Path(pool['reference']['path']),'pool-activation.json':Path(pool['activation']['path']),
                       'pool-verification.json':Path(b['pool_verification']['path'])}
        for name,path in inputs_to_copy.items():
            shutil.copyfile(path,retained/name);bindings[str(path)]=sha(path);bindings[str(retained/name)]=sha(retained/name)
        if a.step=='endpoint':
            measure=owners['mmap1-measure'];grid=results['mmap1-measure']
            delay=datetime.datetime.fromisoformat(current['captured_utc']).timestamp()-measure['child_finished']
            need(0<=delay<=300,'endpoint not immediate to measured child completion')
            before=Path(measure['output'])/'inputs/host-before.json';need(sha(before)==measure['host_state_sha256'],'original timing host capture differs')
            comparison=bench.platform.compare_host(json.loads(before.read_bytes()),current,now,pool['snapshot'],True)
            need(grid.get('planned')==42 and len(grid['sessions'])==42,'completed original grid required')
            policy=checked(measure['measurement_policy']);need(policy['measurement_result']==measure['result'],'measurement policy/result differs')
            run.mkdir();result=dict(schema=1,completed=True,passed=True,drained=True,final_idle=True,boot_id=b['boot_id'],mode=mode,
                grid_points=42,rounds_per_point=1,host_strict_qualified=True,eligibility_policy=POLICY,
                measure_owner=given['mmap1-measure'],measure_result=measure['result'],measurement_policy=measure['measurement_policy'],
                host_before_sha256=measure['host_state_sha256'],host_after_sha256=b['host_state']['sha256'],
                host_reference_sha256=pool['reference']['sha256'],pool_verification_sha256=b['pool_verification']['sha256'],
                captured_utc=current['captured_utc'],capture_delay_from_child_exit_seconds=delay,
                comparison_to_reference=admission,comparison_to_before=comparison,performance_accepted=False)
            save(run/'result.json',result)
        else:
            env=dict(os.environ,PATH=str(Path(c['python']).parent)+':/usr/sbin:/usr/bin:/sbin:/bin',LC_ALL='C',PYTHONDONTWRITEBYTECODE='1')
            limit=5400 if a.step=='mmap1-measure' else 3600
            with active_log.open('x') as stream:
                child=subprocess.Popen(argv,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                r.update(state='RUNNING',child_started=True,pid=child.pid,deadline_seconds=limit,drain_unknown=True);persist()
                code=child.wait(timeout=limit)
            r.update(child_returncode=code,child_finished=time.time(),remaining_processes=group_members(child.pid));persist()
            shutil.copyfile(active_log,out/'controller.log');r['child_log_sha256']=sha(out/'controller.log')
            need(code==0 and not r['remaining_processes'],'runner failed or child group not retired')
            result=json.loads((run/('writer-sites.json' if a.step=='sites' else 'result.json')).read_bytes())
            need(result.get('captured') is True if a.step=='sites' else result.get('passed') is True and result.get('drained') is True,'runner did not complete')
        if a.step=='mapping':
            need(result.get('eligibility_policy')=='mmap-functional-v1' and result.get('writer_observation') in ('observed','inconclusive') and
                 [case['name'] for case in result['cases']]==['00-scope-1','01-cycle-1','02-cycle-16','03-lifetime-1','04-lifetime-16','05-exit-1'],
                 'complete prospective mapping plan differs')
        if a.step=='strict-hold':
            need(result.get('final_idle') is True and result.get('source_unchanged') is True and result.get('harness_commit')==h['commit'] and
                 result.get('harness_manifest_sha256')==h['manifest']['sha256'] and result.get('diagnostic_commit')==c['strict_diagnostic']['commit'] and
                 [case['operation'] for case in result['cases']]==['mmap','munmap'] and
                 all(case.get('passed') is True and case['rejected_mutations']==MUTATIONS for case in result['cases']), 'strict held-writer checks incomplete')
        if a.step=='mmap1-identity':
            need(result['diagnostic_runner']['sha256']==c['identity_adapter']['sha256'] and
                 result['diagnostic_runner']['source_commit']==c['identity_adapter']['commit'] and
                 sha(run/'diagnostic-runner.py')==c['identity_adapter']['sha256'] and
                 'kd_mmap1_identity.mod.c' not in result['source_sha256'],'corrected identity runner/source differs')
        result_file=run/('writer-sites.json' if a.step=='sites' else 'result.json')
        if a.step=='mmap1-measure':
            need(result.get('single_round') is True and result.get('planned')==42 and result['binary_sha256']==app['binary_sha256'] and
                 [(row['model'],row['workers'],row['round']) for row in result['sessions']]==[(m,n,0) for m in ('threads','processes') for n in COUNTS] and
                 all(row.get('passed') is True and row.get('drained') is True and row.get('scored') is True and row.get('instrumentation')=='none'
                     for row in result['sessions']),'exact unchanged42-point grid differs')
            policy=dict(schema=1,eligibility_policy=POLICY,harness_commit=h['commit'],harness_manifest_sha256=h['manifest']['sha256'],
                boot_id=b['boot_id'],kernel=arm,measurement_result=ref(result_file),mapping_owner=given['mapping'],strict_hold_owner=given['strict-hold'],
                mapping_result=owners['mapping']['result'],strict_hold_result=owners['strict-hold']['result'],
                mapping_policy='mmap-functional-v1',incidental_writer_observation=results['mapping']['writer_observation'],
                held_writer_policy='same-mm-held-writer-v1',fresh_same_boot_witnesses=True,host_strict_qualified=True,
                raw_measurement_changed=False,measurement_repeated=False,performance_accepted=False)
            save(out/'measurement-policy.json',policy);r['measurement_policy']=ref(out/'measurement-policy.json')
        recipe_check();need(sha(bundle)==b['bundle_manifest_sha256'],'kernel bundle changed')
        need(all(sha(path)==digest for path,digest in bindings.items()),'actual prerequisite/control bytes changed')
        bench.inputs_from(Path(app['inputs']['path']));bench.idle();bench.mm.writer.check.idle(run);boot_check()
        r.update(completed=True,state='COMPLETE',passed=True,drained=True,final_idle=True,drain_unknown=False,
                 result=ref(result_file),finished=time.time())
    except BaseException as error:
        r.update(state='FAILED',error=repr(error),automatic_retry=False,finished=time.time())
        if child is not None:r.update(child_returncode=child.poll(),drain_unknown=True)
    finally:persist()
    print(json.dumps(dict(state=r['state'],arm=arm_name,step=a.step,owner=ref(control),result=r.get('result'),drain_unknown=r['drain_unknown'])),flush=True)
    if r['completed']:print('COMPLETE writer-queue-mm '+arm_name+' '+a.step,flush=True)
    return 0 if r['completed'] else 1


if __name__=='__main__':raise SystemExit(main())
