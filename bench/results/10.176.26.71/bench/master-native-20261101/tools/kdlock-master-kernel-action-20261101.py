"""Run one explicit scoped-kernel action using fresh host and exact input records."""
from pathlib import Path
import argparse,base64,hashlib,json,shlex,subprocess,time
p=argparse.ArgumentParser()
p.add_argument('--controller',choices=['install','promoted'],required=True)
p.add_argument('--action',required=True)
for k in ['config','output']:p.add_argument('--'+k,type=Path,required=True)
for k in ['config-sha256','boot-id','guest-output']:p.add_argument('--'+k,required=True)
for k in ['prior','prior-sha256','append','append-sha256','mode','bundle-manifest-sha256']:p.add_argument('--'+k)
a=p.parse_args()
T=Path('/tmp');sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
assert sha(a.config)==a.config_sha256;c=json.loads(a.config.read_bytes())
controller=T/('kdlock-writer-queue-install-boot-20261031.py' if a.controller=='install' else 'kdlock-reader-promoted-boot-20261101.py')
allowed=['stage','install','append','arm','request','capture','normal-request','normal-verify'] if a.controller=='install' else ['arm','request','capture'];assert a.action in allowed
assert a.output.is_absolute() and not a.output.exists()
assert a.guest_output.startswith('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/')
a.output.mkdir();SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71'];VM='/home/eric/vm/qemu-scripts/vm_ssh.sh'
r=dict(completed=False,controller=str(controller),controller_sha256=sha(controller),action=a.action,boot_id=a.boot_id,config_sha256=a.config_sha256,guest_output=a.guest_output,uploads=[],started=time.time())
def save():(a.output/'status.json').write_text(json.dumps(r,indent=2)+'\n')
def run(argv,name,bound=120,data=None,allow_transport=False):
 r['phase']=name;save()
 with (a.output/(name+'.stdout')).open('xb') as out,(a.output/(name+'.stderr')).open('xb') as err:
  child=subprocess.Popen(argv,stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);r['child_pid']=child.pid;save();child.communicate(data,timeout=bound)
 r[name+'_returncode']=child.returncode;save()
 assert child.returncode==0 or (allow_transport and child.returncode==255),(name,child.returncode)
 return (a.output/(name+'.stdout')).read_bytes(),child.returncode

def upload(path,target):
 path=Path(path);data=path.read_bytes();h=sha(path)
 code="from pathlib import Path\nimport hashlib,os,sys\np=Path("+repr(target)+");expected="+repr(h)+"\nd=sys.stdin.buffer.read();assert os.geteuid()==0 and hashlib.sha256(d).hexdigest()==expected and p.parent.is_dir() and not p.is_symlink()\nif p.exists():assert p.is_file() and p.read_bytes()==d\nelse:\n with p.open('xb') as f:f.write(d)\nassert hashlib.sha256(p.read_bytes()).hexdigest()==expected\n"
 run(SSH+[shlex.join([VM,shlex.join(['python3','-c',code])])],'upload-'+str(len(r['uploads'])),120,data)
 r['uploads'].append(dict(local=str(path),path=target,sha256=h));save()
try:
 save();upload(a.config,str(a.config));upload(controller,str(controller))
 activation=json.loads((T/'kdlock-master-pool-activate-20261101.result.json').read_bytes());activation_sha=sha(T/'kdlock-master-pool-activate-20261101.result.json')
 assert activation_sha=='b1c758c635abc72b16a113ee106251c636f2d48dc10d850d1e43d6891336be69'
 remote='/tmp/'+a.output.name+'-host'
 cmd=['sudo','-n','taskset','-c','63','python3','/tmp/kdlock-master-pool-20261101.py','verify','--capture-helper','/tmp/kdlock-qemu-stable-pool-capture-host-20261030.py','--inventory','/tmp/kdlock-qemu-readonly-inventory-20261030.json','--snapshot','kdlock-builddisk-clean-20261031','--cohort','master-native-20261101','--policy','/tmp/kdlock-master-pool-activate-20261101/result.json','--policy-sha256',activation_sha,'--output',remote]
 run(SSH+[shlex.join(cmd)],'host-verify',150)
 for leaf,name in [('result.json','pool.json'),('after.host.json','host.json')]:
  d,rc=run(SSH+[shlex.join(['cat',remote+'/'+leaf])],'read-'+name,30);(a.output/name).write_bytes(d)
 pool=json.loads((a.output/'pool.json').read_bytes());assert pool['completed'] and not pool['mutation_attempted'] and not pool['policy_state_unknown'] and pool['activation_receipt_sha256']==activation_sha and pool['captures']['after']['sha256']==sha(a.output/'host.json')
 host_remote='/tmp/'+a.output.name+'.host.json';upload(a.output/'host.json',host_remote)
 argv=[c['python'],str(controller),a.action,'--config',str(a.config),'--config-sha256',a.config_sha256,'--boot-id',a.boot_id,'--host-state',host_remote,'--host-state-sha256',sha(a.output/'host.json'),'--output',a.guest_output]
 for k in ['prior','prior-sha256','append','append-sha256','mode','bundle-manifest-sha256']:
  v=getattr(a,k.replace('-','_'))
  if v is not None:argv+=['--'+k,v]
 r['argv']=argv;save();d,rc=run(SSH+[shlex.join([VM,shlex.join(['env','PYTHONDONTWRITEBYTECODE=1']+argv)])],'action',4000,allow_transport=a.action in ['request','normal-request'])
 if a.action in ['request','normal-request']:
  r.update(transport_disconnected=rc==255,reboot_action_invoked=True,completion_requires_readback=True)
 else:
  code="from pathlib import Path\nimport base64,hashlib,json\np=Path("+repr(a.guest_output+'/result.json')+");d=p.read_bytes();print(json.dumps({'data':base64.b64encode(d).decode(),'sha256':hashlib.sha256(d).hexdigest()}))\n"
  d,_=run(SSH+[shlex.join([VM,'python3 -'])],'readback',120,code.encode());x=json.loads(d);b=base64.b64decode(x['data'],validate=True);assert hashlib.sha256(b).hexdigest()==x['sha256'];(a.output/'result.json').write_bytes(b);result=json.loads(b)
  assert result['passed'] and result['action']==a.action and result['config_sha256']==a.config_sha256 and result['controller_sha256']==sha(controller) and result['boot_id']==a.boot_id and result['final_idle'] and not result['drain_unknown']
  r.update(completed=True,result_path=a.guest_output+'/result.json',result_sha256=x['sha256'])
except BaseException as e:r['error']=repr(e);raise
finally:r['finished']=time.time();save();print(json.dumps(r),flush=True)
