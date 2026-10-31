"""Fresh-cohort receipt checks; no guest work and no archived-code imports."""
import datetime
import json
from pathlib import Path
import nano_core as a

F7='f7a84065e84474380faa37eeadfdf534abd72a68'
CAND='66c68c17457c0ae60d09ff1f3d89b5fff16a500c'
NANO='1857baca9f699907c9eb418e8cb347d601095be95d688e1b9d604aa3fc8a2731'
ENDPOINT='1857baca9f699907c9eb418e8cb347d601095be95d688e1b9d604aa3fc8a2731'
POOL='efc8a6bbed7d20a21e46f8612665af83e899ff3fe58192df361733e3ba1dc0e8'
SNAPSHOT='kdlock-builddisk-clean-20261031'
COHORT='reader-recovery-20261101'
COHORT_SHA='bbdc3ec1e800298d6a98db387f8d221da6df10539240eecd74c7fddce39502a0'
COMMON='bf677df76ee05a5bda06f0e320307681e1990ef7c27b9a51bef773d4309e6257'
PROPERTIES={'thread-pool-min':64,'thread-pool-max':64,'aio-max-batch':0}

def save(path,value):
    p=Path(path);tmp=p.with_name('.'+p.name+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(p)

def checked(path,digest):
    a.need(a.file_sha(Path(path))==digest,'input bytes differ: '+str(path))
    return a.local_json(Path(path))

def qualification(q):
    a.need(q.get('strict_host_gate') in ('PASS','FAILED') and
           q.get('exploratory') is (q['strict_host_gate']=='FAILED') and
           q.get('original_threads')==q.get('observed_threads')==131,
           'qualification shape differs')
    a.need(q['strict_host_gate']!='PASS' or q.get('task_set_unchanged') is True,
           'strict task identity not preserved')
    return q['strict_host_gate']=='PASS'

def host_identity(row):
    a.need(row.get('pins_verified') is True and row.get('frequency_verified') is True and
           row.get('snapshot_listed') is True and row.get('no_turbo')=='1' and
           row.get('recovery_snapshot')==SNAPSHOT,'new host capture differs')
    policies=row['cpufreq']
    a.need(len(policies)==64 and all(x['scaling_governor']=='performance' and
           x['scaling_min_freq']==x['scaling_max_freq']=='2000000' for x in policies.values()),
           'fixed frequency differs')
    a.need(len(row['qemu'])==1,'one exact QEMU required')
    q=row['qemu'][0];tasks=q['tasks'];workers=[x for x in tasks if x['comm']=='worker']
    a.need(len(tasks)==131 and len(workers)==64 and all(x['affinity']==[63] for x in workers),
           'new fixed pool task count/placement differs')
    identity={k:row[k] for k in ('host_boot_id','cpufreq','no_turbo','numa','recovery_snapshot','monitor_path')}
    identity['qemu']={k:q[k] for k in ('pid','start_ticks','args')}
    identity['qemu']['tasks']=sorted(tasks,key=lambda x:x['tid'])
    return identity,datetime.datetime.fromisoformat(row['captured_utc']).timestamp(),workers

def pool(policy,reference,reference_sha):
    a.need(policy.get('completed') is True and policy.get('action')=='activate' and
           policy.get('controller_sha256')==POOL and policy.get('cohort')==COHORT and
           policy.get('stable_worker_cohort_observed') is True and
           policy.get('policy_state_unknown') is False and policy.get('final_properties')==PROPERTIES and
           policy['candidate_reference']['sha256']==reference_sha and
           policy['reference_tasks']==reference['qemu'][0]['tasks'],'new pool activation differs')

def load_control(directory,archive,commit):
    row=a.local_json(directory/'owner.json')
    a.need(commit in (F7,CAND) and row.get('completed') is True and row.get('idle') is True and
           row.get('returncode')==0 and row.get('source_commit')==commit and
           row.get('boot_id')==archive.meta['boot_id'] and row.get('output')==archive.meta['guest_base'] and
           row.get('rounds_per_point')==1 and row.get('expected_points')==row.get('validated_points')==210 and
           row.get('arm')=='kdlock' and row.get('performance_accepted') is False and
           row.get('historical_timings_reused') is False and row.get('common_harness_sha256')==COMMON,
           'fresh complete KD210 controller required')
    for name,digest in row['inputs'].items():
        a.safe(name);checked(directory/name,digest) if name.endswith('.json') else a.need(a.file_sha(directory/name)==digest,'controller bytes differ')
    a.need(row['inputs']['controller.py']==NANO and row['policy_controller_sha256']==POOL,'controller generation differs')
    sync=a.local_json(directory/'sync.json')
    a.need(sync.get('git_head')==commit and sync.get('git_status')=='' and
           sync.get('synchronization_completed') is True and sync.get('tracked_sha256'),'clean exact sync required')
    config=checked(directory/'cohort.json',COHORT_SHA)
    arm=next(x for x in config['arms'] if x['commit']==commit)
    a.need(row['inputs']['cohort.json']==COHORT_SHA and config['schema']==1 and
           config['common_input_sha256']==COMMON and arm['output']==row['output'] and
           a.sha(json.dumps(sync['tracked_sha256'],sort_keys=True,separators=(',',':')).encode())==arm['source_map_sha256'],
           'exact finalized cohort/source map differs')
    for key in ('prior-unit','prior-live','prior-live-source'):
        a.need(row['inputs'][key+'.json']==arm[key.replace('-','_')+'_sha256'],'cohort prerequisite differs: '+key)
    unit=a.local_json(directory/'prior-unit.json');live=a.local_json(directory/'prior-live.json')
    selected=a.local_json(directory/'prior-live-source.json')
    a.need(unit.get('source_commit')==commit and (unit.get('passed') is True or unit.get('completed') is True),
           'historical source-specific unit evidence differs')
    a.need(all(x.get('returncode')==0 for x in unit['blocks']) if 'blocks'in unit else
           unit.get('child_returncode')==0 and unit.get('source_unchanged_after') is True,'historical units failed')
    a.need(live.get('passed') is True and live.get('drained',live.get('final_idle')) is True and selected and
           selected.get('kernel_module/kd_rwsem.c')==sync['tracked_sha256']['kernel_module/kd_rwsem.c'] and
           all(sync['tracked_sha256'].get(k)==v for k,v in selected.items()),'historical live generation differs')
    retained=unit.get('retained_checks',[])
    a.need(bool(retained)==(commit==CAND),'selected prior-unit reuse differs')
    if retained:
        a.need(len(retained)==1,'one exact prior attempt required')
        old=checked(directory/'retained-check-0-result.json',retained[0]['result_sha256'])
        old_sync=a.local_json(directory/'retained-check-0-sync.json')
        current_sync=a.local_json(directory/'prior-unit-sync.json')
        unit_config=a.local_json(directory/'prior-unit-config.json')
        spec=unit_config['retained_checks'][0]
        a.need(old.get('passed') is False and old.get('completed') is False and
               old['source_commit']=='7fa989c124810222042f9560d0e83a7dea197d2f' and
               old_sync['git_head']==old['source_commit'] and current_sync['git_head']==commit and
               current_sync['tracked_sha256']==sync['tracked_sha256'] and
               a.file_sha(directory/'retained-check-0-sync.json')==spec['sync_sha256'] and
               a.file_sha(directory/'prior-unit-sync.json')==unit_config['sync_sha256'] and
               spec['result_sha256']==retained[0]['result_sha256'], 'retained failed attempt identity differs')
        before_map,after_map=old_sync['tracked_sha256'],sync['tracked_sha256']
        changes=['tests/kernel/rwsem/README.md','tests/kernel/rwsem/payload/gate_signal.inc']
        a.need(before_map.keys()==after_map.keys() and
               sorted(n for n in before_map if before_map[n]!=after_map[n])==changes and
               retained[0]['changed_nonunit_paths']==changes and retained[0]['test_inputs_unchanged'] is True,
               'retained selected source inputs changed')
        selected=[x for x in old['blocks'] if x['name'] in spec['blocks']]
        a.need(selected==retained[0]['blocks'] and {x['name'] for x in selected}==set(spec['blocks']) and
               all(x.get('returncode')==0 for x in selected),'retained selected block differs')
        for block in selected:
            a.need(a.file_sha(directory/('retained-check-0-'+block['name']+'.log'))==block['log_sha256'],
                   'retained selected log differs')
    a.need(row.get('basic_evidence_mode')=='maintained-result' and row.get('source_prerequisites_retained') is True,
           'actual standalone basic route required')
    result=a.local_json(directory/'basic-result.json')
    base=directory.parent/Path(row['basic_campaign']).name
    checked(base/'result.json',row['inputs']['basic-result.json'])
    a.need(result.get('passed') is True and result.get('final_idle') is True and result.get('boot_id')==row['boot_id'] and
           result.get('timing_started') is False and result.get('snapshot_tag')==SNAPSHOT and
           result.get('host_reference_sha256')==row['inputs']['host-reference.json'] and
           [x['family'] for x in result['results']]==['spin','mutex','rwlock','rwsem'] and
           all(x['passed'] and x['drained'] and x['jit_completions']>0 for x in result['results']),
           'four returned-JIT family checks incomplete')
    checked(base/'reference-host.json',row['inputs']['host-reference.json'])
    for basic in result['results']:
        checked(base/Path(basic['receipt']).relative_to(row['basic_campaign']),basic['receipt_sha256'])
        family=basic['family'];selected=a.local_json(base/family/'source-sha256.json')
        a.need(selected.get('kernel_module/kd_rwsem.c')==sync['tracked_sha256']['kernel_module/kd_rwsem.c'] and
               all(sync['tracked_sha256'].get(n)==v for n,v in selected.items() if n in sync['tracked_sha256']) and
               all(n.startswith('bench/spin_cacheline/.build/provider/') for n in selected if n not in sync['tracked_sha256']),
               'actual basic selected source differs')
        for name,digest in selected.items():
            a.need(a.file_sha(base/family/'source'/a.safe(name))==digest,'basic captured source bytes differ')
    reference=a.local_json(directory/'host-reference.json');before=a.local_json(directory/'host-before.json')
    policy=a.local_json(directory/'policy-receipt.json');pool(policy,reference,row['inputs']['host-reference.json'])
    a.need(host_identity(reference)[0]==host_identity(before)[0],'reference/campaign host differs')
    strict=qualification(row['timing_qualification'])
    a.need((row['host_mode']=='strict')==strict,'qualification mode relabelled')
    archived=a.local_json(directory/'archive-owner.json');endpoint=a.local_json(directory/'endpoint-receipt.json')
    epolicy=a.local_json(directory/'endpoint-policy.json');after_sha=a.file_sha(directory/'host-after.json')
    a.need(archived.get('completed') is True and archived.get('idle') is True and archived.get('returncode')==0 and
           archived.get('source_commit')==commit and archived.get('boot_id')==row['boot_id'] and
           archived.get('run_owner_sha256')==a.file_sha(directory/'owner.json') and
           archived.get('archives_sha256')==a.file_sha(archive.directory/'archives.json') and
           archived.get('host_after_sha256')==after_sha and
           archived.get('endpoint_receipt_sha256')==a.file_sha(directory/'endpoint-receipt.json') and
           archived.get('endpoint_policy_sha256')==a.file_sha(directory/'endpoint-policy.json'), 'archive/endpoint chain differs')
    a.need(endpoint.get('completed') is True and endpoint.get('returncode')==0 and
           endpoint.get('source_commit')==commit and endpoint.get('script_sha256')==ENDPOINT and endpoint.get('cohort_sha256')==COHORT_SHA and
           endpoint.get('completion_marker')=='COMPLETE writer-queue-nano '+commit and
           endpoint.get('output_sha256')==after_sha and endpoint.get('endpoint_policy_sha256')==a.file_sha(directory/'endpoint-policy.json'),
           'fresh endpoint receipt differs')
    a.need(epolicy.get('action')=='verify' and epolicy.get('completed') is True and epolicy.get('mutation_attempted') is False and
           epolicy.get('policy_state_unknown') is False and epolicy.get('controller_sha256')==POOL and
           epolicy.get('activation_receipt_sha256')==row['inputs']['policy-receipt.json'] and
           epolicy.get('final_properties')==PROPERTIES and epolicy['captures']['after']['sha256']==after_sha,'endpoint pool differs')
    a.need(qualification(archived['host_admission']['timing'])==strict,'endpoint qualification relabelled')
    a.need(row['launcher_owner_sha256']==archive.hashes['owner.json'] and
           row['source_manifest_sha256']==archive.hashes['source-sha256.json'],'launcher/control differs')
    return dict(row,offline_prerequisites=dict(strict_qualified=strict,basic_result_sha256=row['inputs']['basic-result.json'],basic_evidence_mode='maintained-result',cohort_sha256=COHORT_SHA,
                prior_checks_historical=True,prior_unit_sha256=row['inputs']['prior-unit.json'],
                prior_live_sha256=row['inputs']['prior-live.json'],prior_live_source_sha256=row['inputs']['prior-live-source.json'],
                retained_checks=unit.get('retained_checks',[]),control_input_hashes=row['inputs'],basic_local=str(base),
                policy_sha256=row['inputs']['policy-receipt.json'],reference_sha256=row['inputs']['host-reference.json'])),before,a.file_sha(directory/'owner.json')
