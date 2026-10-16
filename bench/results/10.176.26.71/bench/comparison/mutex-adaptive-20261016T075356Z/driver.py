#!/usr/bin/env python3
from collections import Counter
from datetime import datetime,timezone
import json,os,signal,subprocess,sys
from pathlib import Path
ROOT=Path('/root/host_fs/kdlock')
OUT=Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-adaptive-20261016T075356Z')
PY='/root/kdlock-evidence/clobber-20260918/venv/bin/python3'
SNAP='before-mutex-adaptive-20261016T075356Z'
MODE=sys.argv[1]
THREADS=[1,7,16,60] if MODE.startswith('pilot') else [*range(1,9),*range(12,61,4)]
CO=OUT/'control/kd-adaptive-compare-v8.py'
sys.path.insert(0,str(ROOT/'bench/rwlock_compare'))
import run as rw
from bench_runtime import FAULT

def now(): return datetime.now(timezone.utc).isoformat()
def save(path,value):
 p=path.with_suffix('.tmp');p.write_text(json.dumps(value,indent=2)+'\n');p.replace(path)
def health():
 rw.idle()
 assert not Path('/sys/module/real_api').exists()
 log=subprocess.check_output(['dmesg'],text=True)
 faults=[line for line in log.splitlines() if FAULT.search(line)]
 approved=json.loads((OUT/'control/expected-userspace-mutation-traps.json').read_text()) if (OUT/'control/expected-userspace-mutation-traps.json').exists() else []
 assert not any(line not in approved for line in faults),'new kernel fault; retain all state'
 assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==json.loads((OUT/'control/guest-before.json').read_text())['boot_id']
 assert Path('/sys/devices/system/cpu/online').read_text().strip()=='0-63'
 return log

def groups():
 result=[]
 common=['--threads',*map(str,THREADS),'--collector-cpu','63','--repeats','3','--duration-ms','2000']
 base=[PY,str(CO),'--baseline-root',str(OUT/'baseline-source'),'--baseline-manifest',str(OUT/'control/baseline-source-sha256.json')]
 if MODE=='pilot-v1' or MODE.startswith(('pilot-v3','pilot-v4','pilot-v5','pilot-v6','pilot-v7','pilot-v8')):
  for scenario in ('nested','early'):
   args=[PY,'bench/tclock_compare/run_mutex.py','--functional','--backends','kdlock',
    '--cachelines','1','--threads','16','--cpus','0-59','--collector-cpu','63','--repeats','1',
    '--iterations','10000','--scenario',scenario,'--owned-mutex-force-full',
    '--owned-mutex-cabi','--owned-mutex-reuse-spins','32','--owned-mutex-adaptive','--owned-mutex-numa']
   result.append(dict(name=MODE+'-functional-'+scenario,expected=1,argv=args))
 backends=['kdlock'] if MODE.startswith('pilot') else ['native','tclock','kdlock']
 for family in ('api','synthetic'):
  name=MODE+('-api-pipebytes-query-n16' if family=='api' else '-mutex-c01')
  args=base+['--family',family,*common,'--backends',*backends,'--owned-mutex-adaptive','--owned-mutex-numa']
  if family=='api':
   args+=['--kinds','pipebytes','--queries','query','--entries','16','--value-size','64',
    '--cpus',','.join(map(str,range(60))),'--warmup','48000','--warmup-ms','1000',
    '--mutex-spin-limit','4096','--owned-mutex-reuse-spins','32']
  else:
   args+=['--workload','cacheline','--cachelines','1','--cpus','0-59','--peak-window-ms','300',
    '--peak-settle-ms','300','--keep-going-no-jit','--mutex-implementation','owned-v1',
    '--owned-mutex-cabi','--owned-mutex-reuse-spins','32','--mutex-acceptance','adaptive-performance']
  result.append(dict(name=name,expected=len(THREADS)*3*(len(backends)+1),argv=args))
 for r in result: r['argv']+=['--output',str(OUT/r['name'])]
 return result

def main():
 os.chdir(ROOT)
 for s in (signal.SIGINT,signal.SIGTERM):signal.signal(s,signal.SIG_DFL)
 signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGINT,signal.SIGTERM})
 os.environ.update(KDLOCK_RECOVERY_CONFIRMED='1',KDLOCK_SNAPSHOT_TAG=SNAP,KDIR='/root/linux-6.1.159-kdclobber2')
 os.environ['PATH']=str(Path(PY).parent)+':'+os.environ['PATH']
 assert SNAP in (OUT/'control/snapshots.txt').read_text()
 status=dict(state='RUNNING',started_utc=now(),groups=[])
 plan=groups();save(OUT/(MODE+'-plan.json'),plan)
 try:
  for g in plan:
   health()
   assert not (OUT/'STOP').exists(),'STOP requested between groups'
   entry=dict(name=g['name'],started_utc=now());status['groups'].append(entry)
   save(OUT/(MODE+'-status.json'),status)
   print('START',g['name'],flush=True)
   with (OUT/(g['name']+'.log')).open('w') as f:
    rc=subprocess.run(g['argv'],stdout=f,stderr=subprocess.STDOUT,timeout=14400).returncode
   entry.update(exit_code=rc,finished_utc=now())
   health()
   rows=[json.loads(p.read_text()) for p in (OUT/g['name']).glob('*/session.json')]
   entry.update(recorded=len(rows),drained=sum(r.get('drained') is True for r in rows),statuses=dict(Counter(r.get('execution_status','UNKNOWN') for r in rows)))
   save(OUT/(MODE+'-status.json'),status)
   assert rc==0 and len(rows)==entry['drained']==g['expected'],entry
   print('END',g['name'],entry['statuses'],flush=True)
  (OUT/'control'/(MODE+'-dmesg-after.txt')).write_text(health())
  status['state']='COMPLETE'
 except Exception as e:
  status.update(state='FAILED',error=str(e));raise
 finally:
  status['finished_utc']=now();save(OUT/(MODE+'-status.json'),status)
if __name__=='__main__': main()
