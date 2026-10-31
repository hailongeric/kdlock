#!/usr/bin/env python3
"""Read whole-lifetime CPU accounting from validated original mmap1 receipts."""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import tarfile

RECIPE='7814c61a0be20f5db3b9fb41b6079ef6d2938b5f'
CONFIG='b15f6ec4b235e46907978e512b2429906f1bdfa937340ac32f0f9fe76181e602'
CANDIDATE_RECIPE='de5e4f06a6d60e531a8b329d3c7f2c5335d5e707'
CANDIDATE_CONFIG='fafaac5315038e45f150feb4d24a45913a848dfaed8e8c51236952d5087c8584'
GENERATIONS=dict(baseline=RECIPE,compatibility='9d10ae77290873df23804293f364862a2b55f385',candidate=CANDIDATE_RECIPE)
PROVENANCE='2196af5157c900d9faf9ea61b7d51d3f6852d9c3cba6351654d593d88a5ad364'
POLICY='mmap-functional-held-writer-v1'
WORKERS=[*range(1,9),*range(12,61,4)]
SCOPE='whole upstream lifetime including warmup and reaped workers'


def need(value,message):
    if not value:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as source:
        for data in iter(lambda:source.read(1<<20),b''):h.update(data)
    return h.hexdigest()


def checked(path,digest):
    need(Path(path).is_file()and not Path(path).is_symlink()and sha(path)==digest,'input differs: '+str(path))
    return json.loads(Path(path).read_bytes())


def save(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def selected_results(directory,index,wanted):
    """Check grouped bytes and retain only exact point JSON members in memory."""
    found={};prefix=index['archive_prefix']+'/'
    for group in index['groups']:
        name=group['file'];need(PurePosixPath(name).name==name and name not in('.','..'),'archive group basename differs')
        path=directory/name
        need(path.is_file()and not path.is_symlink()and path.stat().st_size==group['bytes']and sha(path)==group['sha256'],'original compressed group differs')
        with tarfile.open(path,'r|gz')as stream:
            for member in stream:
                if not member.name.startswith(prefix):continue
                relative=member.name[len(prefix):]
                if relative not in wanted:continue
                need(relative not in found and member.isfile()and member.size<=4*1024*1024,'point member shape differs')
                data=stream.extractfile(member).read()
                need(len(data)==member.size and hashlib.sha256(data).hexdigest()==wanted[relative],'original point receipt differs')
                found[relative]=json.loads(data)
    need(set(found)==set(wanted),'missing original point receipt');return found


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in('comparison','inputs','output'):p.add_argument('--'+name,type=Path,required=True)
    for name in('validation-sha256','points-sha256','inputs-sha256'):p.add_argument('--'+name,required=True)
    x=p.parse_args();validation=checked(x.comparison/'validation.json',x.validation_sha256)
    points=checked(x.comparison/'points.json',x.points_sha256);spec=checked(x.inputs,x.inputs_sha256)
    expected={(arm,model,n)for arm in('baseline','candidate')for model in('threads','processes')for n in WORKERS}
    need(validation.get('completed')is True and validation.get('validated')is True and validation.get('points')==84 and validation.get('pairs')==42 and
         validation.get('baseline_harness_commit')==RECIPE and validation.get('baseline_config_sha256')==CONFIG and
         validation.get('diagnostic_generations_separate')is True and validation.get('diagnostic_generations')==GENERATIONS and
         validation.get('diagnostic_provenance_sha256')==spec.get('diagnostic_provenance_sha256')==PROVENANCE and
         all(validation['grids'][arm]['harness_commit']==commit and validation['grids'][arm]['config_sha256']==spec['arms'][arm]['config_sha256']==config
             for arm,commit,config in(('baseline',RECIPE,CONFIG),('candidate',CANDIDATE_RECIPE,CANDIDATE_CONFIG)))and
         validation.get('inputs_sha256')==x.inputs_sha256 and
         validation.get('strict_host_qualified')is True and validation.get('shared_functional_policy')==POLICY and
         spec.get('schema')==1 and set(spec['arms'])=={'baseline','candidate'},'completed current paired comparison required')
    need(len(points)==84 and {(z['arm'],z['model'],z['workers'])for z in points}==expected and all(z['round']==0 for z in points),'complete original point map required')
    need(not x.output.exists(),'new diagnostic output required');x.output.mkdir(parents=True)
    receipt=dict(schema=2,completed=False,validated=False,script_sha256=sha(__file__),
        diagnostic_generations=GENERATIONS,diagnostic_provenance_sha256=PROVENANCE,diagnostic_generations_separate=True,
        arm_configs=dict(baseline=CONFIG,candidate=CANDIDATE_CONFIG),
        validation_sha256=x.validation_sha256,points_sha256=x.points_sha256,inputs_sha256=x.inputs_sha256,performance_accepted=False,
        scope='Whole upstream lifetime including six warmups, collector process and reaped workers; no timed-tail or parking/spinning attribution')
    save(x.output/'validation.json',receipt)
    try:
        rows=[]
        for arm in('baseline','candidate'):
            e=spec['arms'][arm];directory=Path(e['archives']);index=checked(directory/'archives.json',e['archives_sha256'])
            proof=validation['grids'][arm]['archive']
            need(proof['archive_receipt_sha256']==e['archives_sha256']and index.get('completed')is True and index.get('guest_idle')is True and
                 index['input_inventory_sha256']==proof['inventory_sha256'],'original validated archive differs')
            checked(directory/'input-inventory.json',index['input_inventory_sha256'])
            prefix=str(PurePosixPath(e['logical_steps']['mmap1-measure']['result']).parent)
            arm_points=[z for z in points if z['arm']==arm]
            wanted={f"{prefix}/{z['model']}-n{z['workers']:02d}-r00/result.json":z['result_sha256']for z in arm_points}
            original=selected_results(directory,index,wanted)
            for z in arm_points:
                member=f"{prefix}/{z['model']}-n{z['workers']:02d}-r00/result.json";r=original[member]
                need((r['model'],r['workers'],r['round'])==(z['model'],z['workers'],0)and r.get('passed')is True and r.get('drained')is True and
                     r.get('scored')is True and r.get('state')=='COMPLETE'and r.get('instrumentation')=='none'and r.get('returncode')==0 and
                     r['cpu_time_scope']==SCOPE and r['output']['completed_pairs']==z['numerator']and z['denominator']==2,'original scored point differs')
                elapsed=r['process_elapsed_ns'];user=r['user_cpu_seconds'];system=r['system_cpu_seconds'];workers=r['workers']
                need(type(elapsed)is int and elapsed>0 and type(workers)is int and workers>0 and
                     all(type(v)in(int,float)and math.isfinite(v)and v>=0 for v in(user,system)),'CPU accounting field invalid')
                seconds=Decimal(elapsed)/Decimal(1_000_000_000);total=Decimal(str(user))+Decimal(str(system));equivalents=total/seconds;occupancy=equivalents/Decimal(workers)
                rows.append(dict(arm=arm,model=r['model'],workers=workers,round=0,process_elapsed_ns=elapsed,user_cpu_seconds=user,
                    system_cpu_seconds=system,cpu_time_scope=r['cpu_time_scope'],total_cpu_seconds=float(total),aggregate_cpu_equivalents=float(equivalents),
                    worker_normalized_occupancy=float(occupancy),worker_normalized_occupancy_pct=float(occupancy*100),
                    original_pairs_per_nominal_second=z['score'],boot_id=index['boot_id'],kernel_project_commit=z['kernel_project_commit'],
                    provider_comparison_commit=z['provider_comparison_commit'],archive_index_sha256=e['archives_sha256'],
                    result_member=member,result_sha256=z['result_sha256'],performance_accepted=False))
        rows.sort(key=lambda r:(r['model'],r['workers'],r['arm']));need(len(rows)==84,'all raw CPU-accounting points required')
        save(x.output/'points.json',rows);paired=[]
        for model in('threads','processes'):
            selected=[r for r in rows if r['model']==model]
            with(x.output/(model+'.csv')).open('x',newline='')as f:
                writer=csv.DictWriter(f,fieldnames=list(selected[0]));writer.writeheader();writer.writerows(selected)
            for n in WORKERS:
                old=next(r for r in selected if r['workers']==n and r['arm']=='baseline');new=next(r for r in selected if r['workers']==n and r['arm']=='candidate')
                paired.append(dict(model=model,workers=n,baseline_occupancy=old['worker_normalized_occupancy'],candidate_occupancy=new['worker_normalized_occupancy'],
                    occupancy_percentage_point_change=new['worker_normalized_occupancy_pct']-old['worker_normalized_occupancy_pct'],
                    baseline_result_sha256=old['result_sha256'],candidate_result_sha256=new['result_sha256'],causal_attribution=None,performance_accepted=False))
        save(x.output/'comparisons.json',paired);save(x.output/'key-workers.json',[r for r in paired if r['workers']in(20,32,60)])
        need(sha(x.inputs)==x.inputs_sha256 and sha(x.comparison/'validation.json')==x.validation_sha256 and sha(x.comparison/'points.json')==x.points_sha256,'comparison inputs changed')
        receipt.update(completed=True,validated=True,points=84,pairs=42,clamped=False,files={p.name:sha(p)for p in x.output.iterdir()if p.is_file()and p.name!='validation.json'},
            limitations=['Whole upstream lifetime, including all six warmups; differs from the two-second score interval.',
                        'CPU accounting includes the upstream collector and reaped workers; denominator uses configured workers.',
                        'No spin/park/OSQ counters or causal attribution; no acceptance or score reclassification.'])
    except BaseException as error:receipt['error']=repr(error);raise
    finally:save(x.output/'validation.json',receipt)


if __name__=='__main__':main()
