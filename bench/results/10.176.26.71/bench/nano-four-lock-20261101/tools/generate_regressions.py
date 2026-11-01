"""Offline attribution index; sampled bottlenecks are not per-point causal proof."""
from pathlib import Path
import csv,json
root=Path('/tmp/kdlock-nano-four-lock-results-20261102/bench/results/10.176.26.71/bench/nano-four-lock-20261101')
rows=list(csv.DictReader((root/'reader-entry/points.csv').open()))
numa=list(csv.DictReader((root/'reader-entry/numa.csv').open()))
refs={
 'rwlock-admission':'include/kd_rwlock.h:56; kernel_module/spin/nondelegated.inc:46; tclock_backend/komb_rwlock.c:808',
 'rwsem-entry':'kernel_module/kd_rwsem.c:88,181,201 (1ba4cc6e); kd_down_read disassembly (87a3a41f)',
 'rwsem-phase':'kernel_module/kd_rwsem.c:127,142,406,425,437; kernel_module/kd_mutex_osq.c:113; tclock_backend/aqs.c:131,397',
 'mutex-handoff':'kernel_module/mutex/waiter.inc; kernel_module/mutex/combiner.inc:478,510',
 'spin-handoff':'kernel_module/spin/wait.inc; kernel_module/spin/queue.inc; kernel_module/spin/combiner.inc',
 'unresolved':'ANALYSIS.md: Attribution boundaries for individual regressions'}
notes={
 'rwlock-admission':'Native slow-reader gate transfer and globally updated reader count dominate sampled cycles; remote modified-line loads rise on split nodes. Exact per-point cost not isolated.',
 'rwsem-entry':'Verified unnecessary fast-success frame and final-reader context work; one-worker profiles support entry/release overhead. Candidate changes this path.',
 'rwsem-phase':'Reader OSQ handoff and exact writer phase/ACK coordination dominate contended samples; remote transfer/DRAM events increase. Individual protocol costs not isolated.',
 'mutex-handoff':'Metadata/notification transfer and bounded NUMA selection remain; split c16 remote modified-line loads increase. Small c01 penalty lacks address-level attribution.',
 'spin-handoff':'Queue/notification/stack handoff is the sampled wait path. No object-level remote event attribution; small one-round differences remain uncertain.',
 'unresolved':'No isolated causal attribution for this score; retain the negative value without inventing a code defect.'}
def cause(f,n,w,axis):
 if n==1:return 'rwsem-entry' if f=='rwsem' else 'unresolved'
 if f=='rwsem' and w==1:return 'rwsem-phase' if axis=='split/same' or n>=20 else 'unresolved'
 return {'mutex':'mutex-handoff','spin':'spin-handoff','rwlock':'rwlock-admission','rwsem':'rwsem-phase'}[f]
out=[]
def add(version,axis,f,cl,w,n,place,delta,key):
 out.append(dict(version=version,axis=axis,family=f,cachelines=int(cl),write_percent=int(w),workers=int(n),placement=place,change_pct=delta,
   evidence_class='unresolved' if key=='unresolved' else 'profiled mechanism; exact delta not isolated',mechanism=key,source=refs[key],interpretation=notes[key]))
for r in rows:
 f,cl,w,n=r['family'],int(r['cachelines']),int(r['write_percent']),int(r['workers'])
 d=float(r['before_vs_tclock_pct'])
 if d<0:add('87a3a41f','KD/TCLock',f,cl,w,n,r['placement'],d,cause(f,n,w,'KD/TCLock'))
for r in numa:
 f,cl,w,n=r['family'],int(r['cachelines']),int(r['write_percent']),int(r['workers'])
 d=float(r['kd_before_split_vs_same_pct'])
 if d<0:add('87a3a41f','split/same',f,cl,w,n,'split'+str(n),d,cause(f,n,w,'split/same'))
for folder,version in [('grouping','82203677'),('reader-entry','1ba4cc6e')]:
 for r in csv.DictReader((root/folder/'points.csv').open()):
  d=float(r['after_vs_before_pct'])
  if d>=0:continue
  f,w,n=r['family'],int(r['write_percent']),int(r['workers'])
  key='unresolved'
  if f=='rwlock' and folder=='grouping' and n>1:key='rwlock-admission'
  if f=='rwsem' and n>1 and not (w==1 and n==8):key='rwsem-phase'
  add(version,'candidate/baseline',f,int(r['cachelines']),w,n,r['placement'],d,key)
for r in csv.DictReader((root/'components.csv').open()):
 d=float(r['component_vs_baseline_pct'])
 if d<0:
  add(r['source_commit'][:8],'component/baseline','rwsem',int(r['cachelines']),int(r['write_percent']),int(r['workers']),r['placement'],d,'unresolved')
with (root/'regressions.csv').open('w') as file:
 writer=csv.DictWriter(file,fieldnames=list(out[0]),lineterminator="\n");writer.writeheader();writer.writerows(out)
lines=['# Negative observations and attribution limits','',
 'Every negative baseline KD/TCLock observation, equal-worker KD NUMA observation, and full-grid candidate/baseline observation is listed below. Positive results remain in the complete point tables. This index links each affected path to the measured mechanism or marks it unresolved; it does not claim that every one-round difference has an isolated root cause. Negative component observations are included; their complete three-point tables are in COMPONENTS.md.','',
 'Source references for the main mechanisms use `1ba4cc6e59f5451eaecafcf1c3a36861d026e5d9`, except where another commit is stated. Withdrawn grouping is described in ANALYSIS.md at `822036777ae5731f24c56cbf50751d6e075ed1e1`.','']
for key in refs:
 lines += ['## '+key,'',notes[key],'','Source: `'+refs[key]+'`.','']
for version,axis in dict.fromkeys((r['version'],r['axis']) for r in out):
 lines += ['## '+version+' '+axis,'','| Workload | Placement/workers | Change | Attribution |','|---|---|---:|---|']
 for r in out:
  if (r['version'],r['axis'])!=(version,axis):continue
  lines += [f"| {r['family']} c{r['cachelines']:02d} w{r['write_percent']:03d} | {r['placement']}/{r['workers']} | {r['change_pct']:+.2f}% | {r['mechanism']} |"]
 lines+=['']
(root/'REGRESSIONS.md').write_text('\n'.join(lines)+'\n')
print('Negative observations indexed:',len(out))
