"""Run one fresh, already booted MM arm with exact prerequisites; source host."""
from pathlib import Path
import argparse,base64,hashlib,json,shlex,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--config-sha256',required=True);p.add_argument('--arm',choices=['promoted','recovery'],required=True);p.add_argument('--boot-id',required=True);p.add_argument('--bundle-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(a.config)==a.config_sha256;c=json.loads(a.config.read_bytes());a.output.mkdir(exist_ok=False)
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71'];VM='/home/eric/vm/qemu-scripts/vm_ssh.sh';T=Path('/tmp')
controller=T/'kdlock-writer-queue-mm-20261031.py';controller_sha=sha(controller)
r=dict(completed=False,coordinator_sha256=sha(__file__),arm=a.arm,boot_id=a.boot_id,config_sha256=a.config_sha256,controller_sha256=controller_sha,steps=[],uploads=[],started=time.time())
def save():(a.output/'status.json').write_text(json.dumps(r,indent=2)+'\n')
def run(argv,label,timeout,data=None):
 r['phase']=label;save()
 with (a.output/(label+'.stdout')).open('xb') as out,(a.output/(label+'.stderr')).open('xb') as err:
  child=subprocess.Popen(argv,stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);r['child_pid']=child.pid;save();child.communicate(data,timeout=timeout);assert child.returncode==0,(label,child.returncode)
 return (a.output/(label+'.stdout')).read_bytes()
def guest(code,label,timeout=120):return run(SSH+[shlex.join([VM,'python3 -'])],label,timeout,code.encode())
def upload(local,target):
 path=Path(local);data=path.read_bytes();digest=sha(path)
 code="from pathlib import Path\nimport hashlib,os,sys\np=Path("+repr(target)+");need="+repr(digest)+"\ndata=sys.stdin.buffer.read();assert hashlib.sha256(data).hexdigest()==need and os.geteuid()==0 and p.parent.is_dir() and not p.is_symlink()\nif p.exists():assert p.is_file() and p.read_bytes()==data\nelse:\n with p.open('xb') as f:f.write(data)\nassert hashlib.sha256(p.read_bytes()).hexdigest()==need\n"
 remote=shlex.join([VM,shlex.join(['python3','-c',code])]);run(SSH+[remote],'upload-'+str(len(r['uploads'])),120,data);r['uploads'].append(dict(local=str(path),path=target,sha256=digest));save()
def capture(step):
 remote='/tmp/kdlock-reader-mm-'+a.arm+'-'+step+'-r2-20261101';pool=c['pool'];cmd=['sudo','-n','taskset','-c','63','python3','/tmp/kdlock-reader-recovery-pool-r2-20261101.py','verify','--capture-helper','/tmp/kdlock-qemu-stable-pool-capture-host-20261030.py','--inventory','/tmp/kdlock-qemu-readonly-inventory-20261030.json','--snapshot',pool['snapshot'],'--cohort',pool['cohort'],'--policy','/tmp/kdlock-reader-recovery-pool-activate-r2-20261101/result.json','--policy-sha256',pool['activation']['sha256'],'--output',remote]
 run(SSH+[shlex.join(cmd)],step+'-host-verify',150)
 for remote_leaf,leaf in [('result.json','pool.json'),('after.host.json','host.json')]:
  data=run(SSH+[shlex.join(['cat',remote+'/'+remote_leaf])],step+'-'+leaf+'-read',30);local=a.output/(step+'.'+leaf);local.write_bytes(data);upload(local,'/tmp/kdlock-reader-mm-'+a.arm+'-'+step+'-r2-20261101.'+leaf)
 verify=json.loads((a.output/(step+'.pool.json')).read_bytes());assert verify['completed'] and not verify['mutation_attempted'] and not verify['policy_state_unknown'] and verify['activation_receipt_sha256']==pool['activation']['sha256'] and verify['captures']['after']['sha256']==sha(a.output/(step+'.host.json'))
 return dict(path='/tmp/kdlock-reader-mm-'+a.arm+'-'+step+'-r2-20261101.host.json',sha256=sha(a.output/(step+'.host.json'))),dict(path='/tmp/kdlock-reader-mm-'+a.arm+'-'+step+'-r2-20261101.pool.json',sha256=sha(a.output/(step+'.pool.json')))
try:
 save();upload(a.config,str(a.config));upload(controller,str(controller))
 for ref in [c['pool']['activation'],c['pool']['reference'],c['mapping_adapter'],c['identity_adapter'],c['strict_diagnostic']['manifest']]:
  assert sha(ref['path'])==ref['sha256'];upload(ref['path'],ref['path'])
 # The existing diagnostic recipe and application are retained on DATA;
 # the VM controller checks them by their original hashes before each step.
 owners={}
 for step in ['sites','api','mapping','faults','completed','strict-hold','mmap1-identity','mmap1-measure','endpoint']:
  host,pool=capture(step)
  required={'mapping':['sites','api'],'strict-hold':['sites','api','mapping'],'mmap1-measure':['api','mapping','faults','completed','strict-hold','mmap1-identity'],'endpoint':['mmap1-measure']}.get(step,[])
  binding=dict(schema=1,arm=a.arm,boot_id=a.boot_id,bundle_manifest_sha256=a.bundle_sha256,host_state=host,pool_verification=pool,prerequisite_owners={k:owners[k] for k in required})
  file=a.output/(step+'.bindings.json');file.write_text(json.dumps(binding,indent=2)+'\n');remote='/tmp/kdlock-reader-mm-'+a.arm+'-'+step+'-r2-20261101.bindings.json';upload(file,remote)
  destination=c['campaign']+'/'+a.arm+'/'+step
  argv=[c['python'],str(controller),step,'--config',str(a.config),'--config-sha256',a.config_sha256,'--bindings',remote,'--bindings-sha256',sha(file),'--output',destination]
  env=['env','PYTHONDONTWRITEBYTECODE=1','KDLOCK_RECOVERY_CONFIRMED=1','KDLOCK_SNAPSHOT_TAG='+c['pool']['snapshot']]
  row=dict(step=step,output=destination,argv=argv,started=time.time(),completed=False);r['steps'].append(row);save()
  run(SSH+[shlex.join([VM,shlex.join(env+argv)])],step+'-action',9000)
  code="from pathlib import Path\nimport base64,hashlib,json\np=Path("+repr(destination+'/owner.json')+");d=p.read_bytes();o=json.loads(d);q=Path(o['result']['path']);b=q.read_bytes();assert hashlib.sha256(b).hexdigest()==o['result']['sha256'];print(json.dumps({'owner':base64.b64encode(d).decode(),'result':base64.b64encode(b).decode(),'sha256':hashlib.sha256(d).hexdigest()}))\n"
  data=json.loads(guest(code,step+'-readback'));body=base64.b64decode(data['owner'],validate=True);owner=json.loads(body);result=base64.b64decode(data['result'],validate=True)
  assert hashlib.sha256(body).hexdigest()==data['sha256'] and owner['completed'] and owner['passed'] and owner['drained'] and owner['final_idle'] and not owner['drain_unknown'] and owner['boot_id']==a.boot_id and owner['arm']==a.arm and owner['step']==step and owner['config_sha256']==a.config_sha256 and owner['controller_sha256']==controller_sha
  (a.output/(step+'.owner.json')).write_bytes(body);(a.output/(step+'.result.json')).write_bytes(result);owners[step]=dict(path=destination+'/owner.json',sha256=data['sha256']);row.update(completed=True,finished=time.time(),owner=owners[step]);save()
 r.update(completed=True,owners=owners,performance_accepted=False)
except BaseException as error:r['error']=repr(error);raise
finally:r['finished']=time.time();save();print(json.dumps(r),flush=True)
