"""Current cohort receipts for offline archive inspection only."""
import datetime,json
from pathlib import Path
import nano_core as a
SNAPSHOT='kdlock-builddisk-clean-20261031'
COHORT='reader-recovery-20261101'
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

def load_control(directory,archive,commit):
    row=a.local_json(directory/'owner.json');c=a.local_json(directory/'config.json')
    a.need(row['passed'] and row['drained'] and row['source_unchanged'] and row['returncode']==0 and row['validated_points']==210 and row['source_commit']==commit==c['commit'],'completed exact source run required')
    a.need(c['boot']==archive.meta['boot_id'] and c['run_output']==archive.meta['guest_base'] and c['output']==c['run_output']+'-control','archive/controller binding differs')
    a.need(c['nano'] is True and c['validator_sha256']=='1857baca9f699907c9eb418e8cb347d601095be95d688e1b9d604aa3fc8a2731','point validator generation differs')
    a.need(a.sha(c['inputs'][c['validator']].encode())==c['validator_sha256'],'point validator bytes differ')
    before=checked(directory/'host-before.json',a.sha(c['inputs'][c['before']].encode()))
    reference=checked(directory/'host-reference.json',a.sha(c['inputs'][c['reference']].encode()))
    policy=a.local_json(directory/'policy-receipt.json')
    a.need(a.file_sha(directory/'policy-receipt.json')=='bbdc3ec1e800298d6a98db387f8d221da6df10539240eecd74c7fddce39502a0' and policy['completed'] and policy['action']=='activate' and policy['cohort']==COHORT and policy['stable_worker_cohort_observed'] and not policy['policy_state_unknown'] and policy['final_properties']==PROPERTIES and policy['candidate_reference']['sha256']==a.file_sha(directory/'host-reference.json') and policy['reference_tasks']==reference['qemu'][0]['tasks'],'pool activation/reference differs')
    a.need(host_identity(reference)[0]==host_identity(before)[0],'reference/task placement changed')
    strict=qualification(row['host_before'])
    archived=a.local_json(directory/'archive-owner.json');endpoint=a.local_json(directory/'endpoint-owner.json');epolicy=a.local_json(directory/'endpoint-result.json')
    after=checked(directory/'host-after.json',a.file_sha(directory/'host-endpoint.json'));after_sha=a.file_sha(directory/'host-after.json')
    a.need(archived['completed'] and archived['drained'] and archived['returncode']==0 and archived['source_commit']==commit and archived['boot_id']==c['boot'] and archived['run_owner_sha256']==a.file_sha(directory/'owner.json') and archived['archives_sha256']==a.file_sha(archive.directory/'archives.json'),'archive chain differs')
    a.need(endpoint['completed'] and endpoint['host_sha256']==after_sha and endpoint['policy_sha256']==a.file_sha(directory/'endpoint-result.json'),'endpoint capture bytes differ')
    # The endpoint binds the compact controller stdout. Its JSON must equal the
    # exact pretty-printed guest owner, whose separate hash binds the archive.
    compact=checked(directory/'controller-stdout.json',endpoint['nano_result_sha256']);a.need(compact==row,'stdout and durable owner disagree')
    a.need(epolicy['completed'] and epolicy['action']=='verify' and epolicy['cohort']==COHORT and not epolicy['mutation_attempted'] and not epolicy['policy_state_unknown'] and epolicy['controller_sha256']==policy['controller_sha256'] and epolicy['activation_receipt_sha256']==a.file_sha(directory/'policy-receipt.json') and epolicy['final_properties']==PROPERTIES and epolicy['captures']['after']['sha256']==after_sha,'endpoint pool differs')
    a.need(qualification(archived['host_endpoint'])==strict,'endpoint qualification differs')
    paths=a.local_json(directory/'prerequisite-local-paths.json');receipts={}
    for original,digest in c['prerequisites'].items():
        prior=checked(Path(paths[original]),digest);a.need(prior['passed'],'prerequisite failed: '+original);receipts[original]=prior
        if 'source_commit' in prior:a.need(prior['source_commit']==commit,'prerequisite source differs')
        if 'commit' in prior:a.need(prior['commit']==commit,'prerequisite commit differs')
        if 'finished' in prior:a.need(prior['finished']<=row['started'],'prerequisite finished after timing began')
    basic=a.local_json(Path(paths['basic-result']))
    a.need(basic['passed'] and basic['final_idle'] and basic['boot_id']==c['boot'] and basic['timing_started'] is False and basic['snapshot_tag']==SNAPSHOT and basic['host_reference_sha256']==a.file_sha(directory/'host-reference.json') and [x['family'] for x in basic['results']]==['spin','mutex','rwlock','rwsem'] and all(x['passed'] and x['drained'] and x['jit_completions']>0 for x in basic['results']),'basic returned-JIT checks incomplete')
    base=Path(paths['basic-result']).parent;guest_basic=str(Path(next(x['receipt'] for x in basic['results'])).parents[2])
    for item in basic['results']:
        checked(base/Path(item['receipt']).relative_to(guest_basic),item['receipt_sha256'])
        selected=a.local_json(base/item['family']/'source-sha256.json')
        a.need(all(c['sources'].get(n)==v for n,v in selected.items() if n in c['sources']),'basic source map differs')
        for name,digest in selected.items():a.need(a.file_sha(base/item['family']/'source'/a.safe(name))==digest,'basic captured source differs: '+name)
    source=archive.json('source-sha256.json');a.need(all(c['sources'].get(n)==v for n,v in source.items()),'Nano source map differs')
    return dict(row,boot_id=c['boot'],offline_prerequisites=dict(strict_qualified=strict,prerequisite_receipts=c['prerequisites'],basic_result_sha256=a.file_sha(Path(paths['basic-result'])),policy_sha256=a.file_sha(directory/'policy-receipt.json'),reference_sha256=a.file_sha(directory/'host-reference.json'))),before,a.file_sha(directory/'owner.json')
