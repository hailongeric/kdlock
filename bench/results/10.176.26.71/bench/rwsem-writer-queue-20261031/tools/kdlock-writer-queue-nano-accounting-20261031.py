#!/usr/bin/env python3
"""Offline accounting of already validated nano sessions; no measurements."""
import hashlib,json,math,statistics,tarfile
from pathlib import Path
ROOT=Path('/dev/shm/kdlock-writer-queue-nano-comparison-20261031')
OUT=Path('/tmp/kdlock-writer-queue-nano-accounting-20261031')
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def summary(raw):
 w=raw['workers'];cpu=sum(z['cpu_ns']for z in w);active=[z['kernel_finished_ns']-z['active_started_ns']for z in w];ops=[z['completed']for z in w]
 need(raw['complete']and raw['data_ok']and all(z['error']in(None,0)and z['cpu_ns']>=0 for z in w),'point accounting not complete')
 return dict(completed=raw['completed'],reads=raw['reads'],writes=raw['writes'],wall_ns=raw['wall_ns'],cpu_ns=cpu,
  cpu_over_worker_wall=cpu/(len(w)*raw['wall_ns']),cpu_over_kernel_active=cpu/sum(active),kernel_active_ns=sum(active),
  earliest_kernel_start_delay_ns=min(z['active_started_ns']for z in w)-raw['started_ns'],latest_kernel_start_delay_ns=max(z['active_started_ns']for z in w)-raw['started_ns'],
  worker_start_spread_ns=max(z['active_started_ns']for z in w)-min(z['active_started_ns']for z in w),
  kernel_finish_spread_ns=max(z['kernel_finished_ns']for z in w)-min(z['kernel_finished_ns']for z in w),
  min_worker_ops=min(ops),max_worker_ops=max(ops),worker_ops_cv=statistics.pstdev(ops)/statistics.mean(ops),
  per_worker=[{k:z[k]for k in('cpu','cpu_ns','completed','reads','writes','active_started_ns','kernel_finished_ns','observed_cpu')}for z in w],
  after={k:raw['after'][k]for k in('lock_addr','gate_addr','cnts','gate','active')})
def main():
 need(not OUT.exists(),'new output required');OUT.mkdir();receipt=dict(completed=False,source_only_archive_analysis=True,performance_accepted=False,script_sha256=sha(__file__),comparison_validation_sha256=sha(ROOT/'validation.json'))
 save(OUT/'validation.json',receipt)
 try:
  validation=json.loads((ROOT/'validation.json').read_text());need(validation['validated']and validation['strict_qualified']and validation['pairs']==210,'expected finalized comparison')
  comparisons=json.loads((ROOT/'comparison/points.json').read_text());worst={f:min((r for r in comparisons if r['lock_kind']==f),key=lambda r:r['metrics']['whole']['change_pct'])for f in('mutex','rwsem','rwlock')}
  selected={r['reference_kd']['session']for r in worst.values()};account=[];proof=[]
  for arm in('baseline','candidate'):
   points=json.loads((ROOT/arm/'points.json').read_text());campaign=json.loads((ROOT/arm/'campaign.json').read_text());directory=Path(campaign['archive']['directory']);index=json.loads((directory/'archives.json').read_text());need(sha(directory/'archives.json')==campaign['archive']['archive_receipt_sha256'],'archive index differs')
   for group in index['groups']:
    family=[p for p in points if p['profile']==group['group']]
    if not family:continue
    path=directory/group['file'];need(sha(path)==group['sha256']and path.stat().st_size==group['bytes'],'group differs');proof.append(dict(arm=arm,file=group['file'],sha256=group['sha256']))
    wanted={};found={};prefix=index['archive_prefix']+'/'
    for p in family:
     parent=p['session'].rsplit('/',1)[0]
     for leaf,digest in(('session.json',p['session_sha256']),('measure.json',p['raw_measure_sha256']),('warmup.json',p['raw_warmup_sha256'])):wanted[parent+'/'+leaf]=(digest,p)
    with tarfile.open(path,'r|gz')as stream:
     for member in stream:
      name=member.name.removeprefix(prefix)
      if name not in wanted:continue
      digest,p=wanted[name];need(member.isfile()and name not in found,'member shape');data=stream.extractfile(member).read();need(hashlib.sha256(data).hexdigest()==digest,'actual raw member differs');found[name]=json.loads(data)
      if p['session']in selected:
       target=OUT/'raw-selected'/arm/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    need(set(found)==set(wanted),'missing exact raw members')
    for p in family:
     parent=p['session'].rsplit('/',1)[0];session=found[p['session']];measure=found[parent+'/measure.json'];warmup=found[parent+'/warmup.json']
     account.append(dict(arm=arm,profile=p['profile'],lock_kind=p['lock_kind'],workload=p['workload'],write_percent=p['write_percent'],threads=p['threads'],
      session=p['session'],session_sha256=p['session_sha256'],raw_measure_sha256=p['raw_measure_sha256'],raw_warmup_sha256=p['raw_warmup_sha256'],
      execution_class=p['execution_class'],jit_completions=p['jit_completions'],jit_completion_share=p['jit_completion_share'],publication_images=p['published']['images'],
      translation_finished_ns=max(z['finished_ns']for z in session['translation']),measure_started_ns=measure['started_ns'],
      measure=summary(measure),warmup=summary(warmup),actual_measure_keys=list(measure),actual_worker_keys=list(measure['workers'][0]),
      parameter_keys=list(session['parameters'])))
  save(OUT/'all-accounting.json',account)
  pairs=[]
  for r in comparisons:
   coord=(r['lock_kind'],r['workload'],r['write_percent'],r['threads']);pair={a:next(z for z in account if z['arm']==a and(z['lock_kind'],z['workload'],z['write_percent'],z['threads'])==coord)for a in('baseline','candidate')}
   pairs.append(dict(lock_kind=r['lock_kind'],workload=r['workload'],write_percent=r['write_percent'],threads=r['threads'],whole_change_pct=r['metrics']['whole']['change_pct'],peak_change_pct=r['metrics']['peak']['change_pct'],any_observed_loss=r['any_observed_loss'],execution_transition=r['execution_transition'],
    baseline_cpu_worker_wall=pair['baseline']['measure']['cpu_over_worker_wall'],candidate_cpu_worker_wall=pair['candidate']['measure']['cpu_over_worker_wall'],
    baseline_cpu_kernel_active=pair['baseline']['measure']['cpu_over_kernel_active'],candidate_cpu_kernel_active=pair['candidate']['measure']['cpu_over_kernel_active'],
    baseline_warmup_ops_s=pair['baseline']['warmup']['completed']*1e9/pair['baseline']['warmup']['wall_ns'],candidate_warmup_ops_s=pair['candidate']['warmup']['completed']*1e9/pair['candidate']['warmup']['wall_ns'],
    baseline_start_spread_ns=pair['baseline']['measure']['worker_start_spread_ns'],candidate_start_spread_ns=pair['candidate']['measure']['worker_start_spread_ns'],
    baseline_ops_cv=pair['baseline']['measure']['worker_ops_cv'],candidate_ops_cv=pair['candidate']['measure']['worker_ops_cv'],publication_identical=pair['baseline']['publication_images']==pair['candidate']['publication_images'],performance_accepted=False))
  save(OUT/'pairs.json',pairs);save(OUT/'selected.json',{f:dict(comparison={k:r[k]for k in('lock_kind','workload','write_percent','threads','metrics','execution_transition')},accounting=[z for z in account if z['session']==r['reference_kd']['session']])for f,r in worst.items()})
  save(OUT/'group-proof.json',proof);save(OUT/'key-workers.json',[z for z in pairs if z['threads']in(20,32,36,60)])
  receipt.update(completed=True,points=len(account),pairs=len(pairs),group_count=len(proof),whole_losses=validation['summary']['whole_losses'],peak_losses=validation['summary']['peak_losses'],either_losses=validation['summary']['either_metric_losses'],strict_qualified=True,no_regression_evidence_gate=False,limits=['One sequential round, no variance estimate or causal attribution.','Worker thread CPU time brackets ioctl; whole wall includes start/config/release and collector completion.','Kernel-active interval has a different clock boundary; diagnostic ratio is not exact scheduling accounting.','No measured park/spin/OSQ/wake counter in the selected raw schema.'])
 except BaseException as e:receipt['error']=repr(e);raise
 finally:save(OUT/'validation.json',receipt)
 print(json.dumps({k:receipt.get(k)for k in('completed','points','pairs','group_count','error')}))
if __name__=='__main__':main()
