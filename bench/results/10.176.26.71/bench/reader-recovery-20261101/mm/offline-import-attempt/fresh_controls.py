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

