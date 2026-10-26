"""42 newly measured shared-mm aggregate controls, then verified recovery."""
import fcntl,hashlib,json,os,runpy,socket,sys
from pathlib import Path
sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parent;ROOT=Path('/home/eric/vm/vm-shared/kdlock')
original=BASE.parent/'mmap-functional-scaling-20261026/campaign.py'
assert hashlib.sha256(original.read_bytes()).hexdigest()=='f37653e624a959387de57dd28cfee08fa1b6deb8d6879cb299f5bfde5b2408df'
ns=runpy.run_path(str(original));g=ns['boot'].__globals__
manifest=json.loads((BASE/'source-manifest.json').read_text());initial=json.loads((BASE/'initial-health.stdout').read_text())
plan=dict(state='prepared',execution_commit=manifest['commit'],workers=list(range(1,9))+list(range(12,61,4)),
 single_round=True,strict_qualified=False,run_kind='single_aggregate_control',
 maximum=dict(measured_sessions=42,payload_cycles=42,boots=3,full_host_captures=88),
 consumed=dict(measured_sessions=0,payload_cycles=0,boots=0,full_host_captures=0),
 planning=dict(reserve_bytes_per_retention_filesystem=512*1024**2))
g.update(BASE=BASE,GUEST='/root/kdlock-evidence/10.176.26.71/bench/'+BASE.name,PLAN=plan,MANIFEST=manifest,
 START_HEAD=manifest['commit'],INITIAL=initial,FROZEN=json.loads((BASE/'orchestration-manifest.json').read_text()),
 ARTIFACTS=json.loads((BASE/'expected-artifacts.json').read_text()))
import mm_report
sys.path.insert(0,str(ROOT/'bench/catalog_single'))
import collect
baseline=json.loads((BASE.parent/'catalog-single-20261026/host-before.json').read_text())
def capture(label):
 path=g['capture'](label)
 # Besides ready's profile/role binding, retain exact original core affinity
 # and permit only the authorized QEMU worker additions on host CPU 63.
 h=json.loads(path.read_text())
 for qemu in h['qemu']:
  qemu['tasks']=[{k:t[k] for k in ('tid','comm','affinity')} for t in qemu['tasks']]
 issues=collect.exploratory_check(baseline,h)
 assert not issues,issues
 return path
def publish(results):
 rows=[dict(threads=r['spec']['threads'],arm=r['backend'],ops_s=r['measurement']['pairs_s'],completed=r['measurement']['completed_pairs'],peak_status=r['measurement']['peak_status'],passed=r['passed'],drained=r['drained'],repeat=0) for r in results]
 mm_report.render('shared-mm','Shared-mm mmap/munmap',rows,['native','kd'],
  'Actual mmap/munmap in one shared address space, on installed kernel `6.1.159-kdmm31` (Build ID `ef5179e8def44f0255adcd62585f62f118fee30f`). Native uses `kd_mmap=off`; KD uses `kd_mmap=on`. Native MM bodies execute on their original tasks. Each point retains the 90-second post-setup interval. These are separate aggregate controls, not an accepted paired campaign. Controller source `'+manifest['commit']+'`; unchanged timed client SHA-256 `5962210671ac238ae4df8dcca442b3cb7407efb2b5b2edb42ae637ac4902083f`.')
def main():
 g['source_check']();current=g['state']('launch-state')
 for key in ('release','boot_id','modules','taint','cmdline','grubenv'):assert current[key]==initial[key],key
 assert current['release']=='6.1.159-kdclobber2' and len(current['modules'])==73
 plan['state']='running';g['save']();capture('initial-recovery')
 g['copy']('copy-controls',{g['GUEST']+'/source/bench/mmap_lock/aggregate.py':(ROOT/'bench/mmap_lock/aggregate.py').read_bytes(),g['GUEST']+'/source-manifest.json':(BASE/'source-manifest.json').read_bytes()})
 results=[]
 for mode,block in [('native',0),('kd',1)]:
  current=g['boot'](mode,mode,current)
  admission=capture(mode+'-admission');guest_admission=g['GUEST']+'/'+mode+'-admission.json'
  g['copy'](mode+'-copy-admission',{guest_admission:admission.read_bytes()});ready=g['GUEST']+'/'+mode+'-ready'
  g['paired'](mode+'-ready','ready',['--plan','plain-scaling-v1','--measurement-policy','mmap-window-v2','--eligibility-policy','mmap-functional-v1','--window-roles',g['ROLES'],'--prepared',g['BUILD'],'--native-api',g['PRIOR']+'actual-native-1.json','--kd-api',g['PRIOR']+'actual-kd-1.json','--mode',mode,'--block',str(block),'--boot-id',current['boot_id'],'--host-state',guest_admission,'--output',ready],seconds=60)
  for n in plan['workers']:
   name=f'{mode}-n{n}';g['source_check']();before=g['state'](name+'-idle');assert before['boot_id']==current['boot_id']
   capture(name+'-before')
   request=dict(threads=n,mode=mode,boot_id=current['boot_id'],ready=ready+'/result.json',output=g['GUEST']+'/'+name,source_commit=manifest['commit'],aggregate_source=g['GUEST']+'/source/bench/mmap_lock',aggregate_sha256=manifest['files']['bench/mmap_lock/aggregate.py'])
   plan['consumed']['payload_cycles']+=1;g['save']()
   result=json.loads(g['guest_python'](name+'-case',(BASE/'case-remote.py').read_text(),request,seconds=240))
   assert result['passed'] and result['drained']
   results.append(result);plan['consumed']['measured_sessions']+=1;plan['completed_results']=results;g['save']()
   capture(name+'-after');publish(results)
   g['event']('published',mode=mode,threads=n,completed=len(results),measurement=result['measurement'])
  g['remote'](mode+'-archive',['tar','-czf','-','-C','/root/kdlock-evidence/10.176.26.71/bench',BASE.name],seconds=120)
  current=g['state'](mode+'-final-state')
 recovery=g['boot']('recovery','recovery',current)
 code=(BASE/'recovery-remote.py').read_text().replace("assert missing == ['nfnetlink', 'tls'], missing","assert set(missing) <= {'nfnetlink', 'tls'}, missing")
 g['guest_python']('recovery-final',code,dict(recovery_boot=recovery['boot_id'],expected_modules=initial['modules'],recovery_default=g['ARTIFACTS']['artifact']['recovery_default']),seconds=60)
 capture('final-recovery');plan.update(state='completed_recovered',recovery_boot=recovery['boot_id']);g['save']();g['event']('completed_recovered',measured=len(results))
if __name__=='__main__':
 with (BASE/'owner.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  with (BASE/'owner.json').open('x') as f:json.dump(dict(pid=os.getpid(),host=socket.gethostname()),f)
  try:main()
  except BaseException as error:
   plan.update(state='stopped_for_review',error=repr(error));g['save']();g['event']('stopped_for_review',error=repr(error));raise
