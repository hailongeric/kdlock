from pathlib import Path
import json,os,subprocess,re
ps=subprocess.check_output(['ps','-eo','pid,comm,args'],text=True)
q=[]
for line in ps.splitlines():
 parts=line.split(None,2)
 if len(parts)==3 and parts[1].startswith('qemu-system'):
  pid=int(parts[0]); tasks=[]
  for p in Path('/proc',str(pid),'task').iterdir():
   tid=int(p.name); tasks.append(dict(tid=tid,comm=(p/'comm').read_text().strip(),affinity=sorted(os.sched_getaffinity(tid))))
  q.append(dict(pid=pid,args=parts[2],tasks=tasks))
assert len(q)==1
cpus={}
for task in q[0]['tasks']:
 match=re.fullmatch(r'CPU (\d+)/KVM',task['comm'])
 if match:
  cpu=int(match.group(1)); assert task['affinity']==[cpu],task; cpus[cpu]=task['tid']
 else: assert task['affinity']==[63],task
assert set(cpus)==set(range(64))
policies={}
for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*'):
 policies[p.name]={n:(p/n).read_text().strip() for n in ('scaling_governor','scaling_min_freq','scaling_max_freq') if (p/n).exists()}
print(json.dumps(dict(qemu=q,frequency_policies=policies,vcpu_pinning_verified=True,service_cpu=63),indent=2))
