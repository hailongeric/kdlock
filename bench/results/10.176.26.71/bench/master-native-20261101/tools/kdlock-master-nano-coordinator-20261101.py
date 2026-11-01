"""Source-host sequence for fresh Native/KD Nano measurements in the VM."""
from pathlib import Path
import ast,datetime,hashlib,json,shlex,subprocess,time
P=Path('/tmp/kdlock-master-nano-20261101');P.mkdir(exist_ok=False)
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71']
VM='/home/eric/vm/qemu-scripts/vm_ssh.sh'
state={'completed':False,'started':time.time()}
def save():
 t=P/'status.tmp';t.write_text(json.dumps(state,indent=2)+'\n');t.replace(P/'status.json')
def call(label,argv,data=None,timeout=180):
 state['phase']=label;save()
 with (P/(label+'.stdout')).open('xb') as o,(P/(label+'.stderr')).open('xb') as e:
  c=subprocess.Popen(argv,stdin=subprocess.PIPE if data else subprocess.DEVNULL,stdout=o,stderr=e,start_new_session=True)
  state['child_pid']=c.pid;save();c.communicate(data,timeout=timeout)
 assert c.returncode==0,(label,c.returncode)
 return (P/(label+'.stdout')).read_bytes()
def capture(label):
 dest='/tmp/kdlock-master-'+label+'-20261101'
 args=['sudo','-n','taskset','-c','63','python3','/tmp/kdlock-master-pool-20261101.py','verify','--capture-helper','/tmp/kdlock-qemu-stable-pool-capture-host-20261030.py','--inventory','/tmp/kdlock-qemu-readonly-inventory-20261030.json','--snapshot','kdlock-builddisk-clean-20261031','--cohort','master-native-20261101','--policy','/tmp/kdlock-master-pool-activate-20261101/result.json','--policy-sha256','b1c758c635abc72b16a113ee106251c636f2d48dc10d850d1e43d6891336be69','--output',dest]
 call(label,SSH+[shlex.join(args)],timeout=210)
 raw=call(label+'-read',SSH+[shlex.join(['cat',dest+'/after.host.json'])]);p=P/(label+'.json');p.write_bytes(raw);return p
try:
 state['phase']='waiting-for-correctness';save();deadline=time.monotonic()+7400
 while True:
  lines=Path('/tmp/kdlock-master-checks-20261101.stdout').read_text().splitlines()
  rows=[json.loads(s) for s in lines if s.startswith('{')]
  assert all(r['passed'] and r['drained'] for r in rows),rows
  assert not Path('/tmp/kdlock-master-checks-20261101.stderr').read_text().strip(),'correctness command reported an error'
  if len(rows)==4:break
  assert time.monotonic()<deadline,'correctness deadline; no measurements started'
  time.sleep(5)
 state['correctness']=rows;save();before=capture('nano-before')
 configs=json.loads(Path('/tmp/kdlock-master-checks-launch-20261101.config.json').read_text())
 c=configs[0].copy();c.pop('unit_count');c.update(output='/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench/master-native-20261101/nano-control',timeout=36000)
 base='/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench/master-native-20261101/nano'
 c['argv']=[c['python'],'bench/nano/best_case.py','--output',base,'--backends','native','kdlock','--repeats','1','--threads',*map(str,[*range(1,9),*range(12,61,4)]),'--delegate','on','--post-work-rounds','256','--mutex-batch-limit','1024','--mutex-numa-boundary','1024','--kernel-source','/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build','--kernel-baseline','/root/kdlock-kernel-baselines/linux70-kdlock1-20261027']
 c['result']=base+'/owner.json';c['inputs'][str(before)]=before.read_text()
 script=Path('/tmp/kdlock-reader-recovery-prerequisite-step-20261101.py').read_text()
 script=script.replace("assert result[c.get('success_key','passed')] is True", "assert len(result['blocks']) == 10 and all(b['returncode'] == 0 and not b['completion_unconfirmed'] for b in result['blocks'])\n   r['completed_workloads']=10")
 code=script+'\nrun('+repr(c)+')\n';ast.parse(code);(P/'nano-launch.py').write_text(code)
 (P/'config.json').write_text(json.dumps(c,indent=2)+'\n')
 call('nano',SSH+[shlex.join([VM,'taskset -c 63 python3 -'])],code.encode(),timeout=36200)
 capture('nano-after');state.update(completed=True,finished=time.time());save()
except BaseException as e:
 state.update(error=repr(e),finished=time.time());save();raise
