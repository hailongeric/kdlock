"""One-round private-backing campaign; stop on any uncertain completion."""
import hashlib,json,runpy,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/home/eric/vm/vm-shared/kdlock');BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'bench/catalog_single'))
import collect
collect.RAW=BASE
original=BASE.parent/'mmap-functional-scaling-20261026/campaign.py'
assert hashlib.sha256(original.read_bytes()).hexdigest()=='f37653e624a959387de57dd28cfee08fa1b6deb8d6879cb299f5bfde5b2408df'
ns=runpy.run_path(str(original));g=ns['remote'].__globals__
MANIFEST=json.loads((BASE/'source-manifest.json').read_text())
GUEST='/root/kdlock-evidence/10.176.26.71/bench/'+BASE.name
plan=dict(state='prepared',scope='private-backing mmap and CPU fault',single_round=True,strict_qualified=False,maximum={},consumed={})
g.update(BASE=BASE,GUEST=GUEST,PLAN=plan)
g['ENV'] += ['PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin']
BOOT='8caa1264-4d93-4448-a6d8-6d8393d364ee'
COMMON=['--boot-id',BOOT,'--kernel-source','/root/linux-6.1.159-kdclobber2','--kernel-baseline','/root/kdlock-kernel-baselines/mutex-clobber2-20260919']
baseline=json.loads((BASE.parent/'catalog-single-20261026/host-before.json').read_text())
def host(label):
 h=collect.capture(label);issues=collect.exploratory_check(baseline,h)
 assert not issues,issues
 path=BASE/(label+'-host.json');dest=GUEST+'/'+path.name
 g['copy'](label+'-host-copy',{dest:path.read_bytes()})
 return dest
def run(label,script,args,seconds):
 before=host(label+'-before')
 g['remote'](label,[*g['ENV'],g['PYTHON'],g['SOURCE']+'/'+script,'--host-state',before,*COMMON,*args],seconds=seconds)
 collect.capture(label+'-after')
 assert not collect.exploratory_check(baseline,json.loads((BASE/(label+'-after-host.json')).read_text()))
 return g['fetch'](label+'-result',GUEST+'/'+label+'/result.json')
def publish(label,result):
 (BASE/(label+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
 import mm_report
 mm_report.private(label,result)
 print('PUBLISHED',label,flush=True)
def main():
 for name,h in MANIFEST['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
 g['copy']('manifest-copy',{GUEST+'/source-manifest.json':(BASE/'source-manifest.json').read_bytes()})
 shared=['--source-manifest',GUEST+'/source-manifest.json','--split']
 r=run('correctness-kd','tests/kernel/mmap_fault/run.py',[*shared,'--backends','0,1','--output',GUEST+'/correctness-kd'],600)
 assert r['passed'] and r['drained'] and len(r['split_cases'])==12
 r=run('correctness-tc','tests/kernel/mmap_fault/run.py',[*shared,'--backends','2','--native-kd-result',GUEST+'/correctness-kd/result.json','--output',GUEST+'/correctness-tc'],600)
 assert r['passed'] and r['drained'] and len(r['split_cases'])==6
 r=run('prepare','bench/mmap_fault/timing.py',['prepare','--plain-only','--source-manifest',GUEST+'/source-manifest.json','--correctness-kd',GUEST+'/correctness-kd','--correctness-tc',GUEST+'/correctness-tc','--output',GUEST+'/prepare'],600)
 assert r['passed'] and r['drained'] and len(r['sessions'])==8
 g['remote']('negative-oracles',[*g['ENV'],g['PYTHON'],g['SOURCE']+'/bench/mmap_fault/check_oracles.py',GUEST+'/prepare'],seconds=60)
 for label,count in [('mmap',21),('fault',63)]:
  r=run(label,'bench/mmap_fault/timing.py',['measure','--single-round-grid','--workload',label,'--exploratory-host','--inputs',GUEST+'/prepare/inputs.json','--output',GUEST+'/'+label],1800)
  assert r['passed'] and r['drained'] and len(r['sessions'])==count
  publish(label,r)
  g['remote'](label+'-archive',['tar','-czf','-','-C',GUEST,label],seconds=120)
 g['remote']('private-full-archive',['tar','-czf','-','-C','/root/kdlock-evidence/10.176.26.71/bench',BASE.name],seconds=180)
 plan.update(state='complete',measured=84,drained=True);g['save']()
if __name__=='__main__':
 try:main()
 except BaseException as error:
  plan.update(state='stopped_for_review',error=repr(error));g['save']();raise
