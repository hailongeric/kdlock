"""Sequential master campaign continuation; guest work waits for Nano drain."""
from pathlib import Path
import ast,base64,hashlib,json,shlex,subprocess,time
T=Path('/tmp');O=T/'kdlock-master-followthrough-r2-20261101';O.mkdir(exist_ok=False)
C=T/'kdlock-master-mm-config-20261101.json';c=json.loads(C.read_text());I=T/'kdlock-reader-scope4-install-r2-20261101.json'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71'];VM='/home/eric/vm/qemu-scripts/vm_ssh.sh'
G='/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/master-actions-20261101';PY=c['python']
r={'completed':False,'started':time.time(),'actions':[],'archives':[]}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save():
 t=O/'status.tmp';t.write_text(json.dumps(r,indent=2)+'\n');t.replace(O/'status.json')
def run(argv,label,timeout=180,data=None,allow_disconnect=False):
 r['phase']=label;save()
 with (O/(label+'.stdout')).open('xb') as out,(O/(label+'.stderr')).open('xb') as err:
  child=subprocess.Popen(argv,stdin=subprocess.PIPE if data else subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
  r['child_pid']=child.pid;save();child.communicate(data,timeout=timeout)
 assert child.returncode==0 or (allow_disconnect and child.returncode==255),(label,child.returncode)
 return (O/(label+'.stdout')).read_bytes(),child.returncode

def guest(code,label,timeout=180):
 ast.parse(code);(O/(label+'.py')).write_text(code)
 return run(SSH+[shlex.join([VM,'python3 -'])],label,timeout,code.encode())[0]
def upload(path,target):
 path=Path(path);data=path.read_bytes();digest=sha(path)
 code="from pathlib import Path\nimport hashlib,sys\np=Path("+repr(target)+");d=sys.stdin.buffer.read();assert hashlib.sha256(d).hexdigest()=="+repr(digest)+"\nassert p.parent.is_dir() and not p.is_symlink()\nif p.exists():assert p.read_bytes()==d\nelse:\n with p.open('xb') as f:f.write(d)\n"
 run(SSH+[shlex.join([VM,shlex.join(['python3','-c',code])])],'upload-'+path.name,900,data)
 return {'path':target,'sha256':digest}
def readfile(path,label):
 code="from pathlib import Path\nimport base64,hashlib,json\np=Path("+repr(path)+");d=p.read_bytes();print(json.dumps({'data':base64.b64encode(d).decode(),'sha256':hashlib.sha256(d).hexdigest()}))\n"
 x=json.loads(guest(code,label));d=base64.b64decode(x['data']);assert hashlib.sha256(d).hexdigest()==x['sha256'];(O/(label+'.json')).write_bytes(d)
 return json.loads(d),{'path':path,'sha256':x['sha256']}
def action(act,boot,label,prior,mode=None):
 out=T/('kdlock-master-action-'+label+'-20261101')
 argv=['python3',str(T/'kdlock-master-kernel-action-20261101.py'),'--controller','install','--action',act,'--config',str(I),'--config-sha256',sha(I),'--boot-id',boot,'--guest-output',G+'/'+label,'--output',str(out),'--prior',prior['path'],'--prior-sha256',prior['sha256']]
 if mode:argv+=['--mode',mode]
 if act=='capture' and mode=='kd':argv+=['--bundle-manifest-sha256','5bb0fcbd453f307ae159746da133163247538acf7d3f152fa05ceeb53a633957']
 run(argv,label,4500);s=json.loads((out/'status.json').read_text());r['actions'].append({'label':label,'status':str(out/'status.json'),**s});save()
 if act in ('request','normal-request'):
  assert s['reboot_action_invoked'];return {'path':G+'/'+label+'/result.json'}
 assert s['completed'];return {'path':s['result_path'],'sha256':s['result_sha256']}
def observe(old,release,label,request):
 code="from pathlib import Path\nimport os,json\nprint(json.dumps({'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release}))\n"
 deadline=time.monotonic()+600;i=0
 while True:
  assert time.monotonic()<deadline,'boot observation deadline; no additional reboot'
  data,rc=run(SSH+[shlex.join([VM,'python3 -'])],label+'-observe-'+str(i),45,code.encode(),True);i+=1
  if rc==0:
   d=json.loads(data)
   if d['boot']!=old:
    assert d['release']==release,d;break
  time.sleep(10)
 req,ref=readfile(request['path'],label+'-request-receipt');assert req['boot_id']==old and any(x.get('name')=='reboot' and x.get('pid') for x in req['commands'])
 return d['boot'],ref

def capture(label):
 remote='/tmp/kdlock-master-'+label+'-20261101';p=c['pool']
 argv=['sudo','-n','taskset','-c','63','python3','/tmp/kdlock-master-pool-20261101.py','verify','--capture-helper','/tmp/kdlock-qemu-stable-pool-capture-host-20261030.py','--inventory','/tmp/kdlock-qemu-readonly-inventory-20261030.json','--snapshot',p['snapshot'],'--cohort',p['cohort'],'--policy','/tmp/kdlock-master-pool-activate-20261101/result.json','--policy-sha256',p['activation']['sha256'],'--output',remote]
 run(SSH+[shlex.join(argv)],label+'-host',210)
 raw,_=run(SSH+[shlex.join(['cat',remote+'/after.host.json'])],label+'-host-read');local=O/(label+'.host.json');local.write_bytes(raw)
 return upload(local,'/tmp/kdlock-master-'+label+'-20261101.host.json')

def view(act,boot,label):
 v={'action':act,'boot':boot,**c['harness']}
 code='v='+repr(v)+'\n'+'''from pathlib import Path
import hashlib,json,os,runpy,subprocess,sys
root=Path('/root/host_fs/kdlock');recipe=Path(v['source']);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==v['boot']
assert sha(v['manifest']['path'])==v['manifest']['sha256'];m=json.loads(Path(v['manifest']['path']).read_text());assert m['source_commit']==v['commit']
for name,row in m['files'].items():assert sha(recipe/name)==row['sha256']
sys.path.insert(0,str(recipe/'bench/spin_cacheline'));import bench_runtime as rt
idle=runpy.run_path(str(recipe/'bench/archive_run.py'))['idle'];idle(root,rt.idle);idle(recipe,rt.idle)
if v['action']=='bind':
 assert not root.is_mount();subprocess.run(['mount','--bind',str(recipe),str(root)],check=True,timeout=30)
 subprocess.run(['mount','-o','remount,bind,ro',str(root)],check=True,timeout=30)
 assert os.path.samefile(root,recipe) and os.statvfs(root).f_flag & os.ST_RDONLY
else:
 assert root.is_mount() and os.path.samefile(root,recipe)
 subprocess.run(['umount',str(root)],check=True,timeout=30);assert not root.is_mount()
print(json.dumps({'completed':True,'action':v['action']}))
'''
 assert json.loads(guest(code,label))['completed']

def retain(paths,label):
 target='/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/master-'+label+'-20261101.tar.gz'
 code='paths='+repr(paths)+'\ntarget='+repr(target)+'\n'+'''from pathlib import Path
import hashlib,json,runpy,sys,tarfile
root=Path('/root/host_fs/kdlock');sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
p=Path(target);assert not p.exists()
with tarfile.open(p,'x:gz') as t:
 for i,name in enumerate(paths):
  q=Path(name);assert q.exists();t.add(q,arcname=str(i)+'-'+q.name)
h=hashlib.sha256()
with p.open('rb') as f:
 for b in iter(lambda:f.read(4<<20),b''):h.update(b)
print(json.dumps({'path':str(p),'sha256':h.hexdigest(),'size':p.stat().st_size,'inputs':paths}))
'''
 d=json.loads(guest(code,label+'-archive',7200));dest=O/(label+'.tar.gz')
 with dest.open('xb') as f,(O/(label+'-fetch.stderr')).open('xb') as err:
  proc=subprocess.run(SSH+[shlex.join([VM,shlex.join(['cat',d['path']])])],stdout=f,stderr=err,timeout=3600)
 assert proc.returncode==0 and sha(dest)==d['sha256'] and dest.stat().st_size==d['size']
 r['archives'].append(dict(d,local=str(dest)));save()

def syscall(boot):
 previous=None
 for act in ('functional','measure'):
  host=capture('syscall-'+act+'-before');base=c['campaign']+'/syscall-'+act
  argv=[PY,'bench/kernel_api/run.py',act,'--output',base,'--host-state',host['path'],'--boot-id',boot,'--host-reference',c['pool']['reference']['path'],'--host-reference-sha256',c['pool']['reference']['sha256'],'--kernel-variant','kdscope4-native','--kernel-source',c['arms']['native']['build'],'--kernel-baseline',c['arms']['native']['bundle']]
  if previous:argv+=['--functional-result',previous]
  code='argv='+repr(argv)+'\n'+'''from pathlib import Path
import json,os,subprocess
root=Path('/root/host_fs/kdlock');out=Path(argv[argv.index('--output')+1]);log=out.with_name(out.name+'-controller.log');assert not out.exists() and not log.exists()
env=dict(os.environ,PATH='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin:/usr/sbin:/usr/bin:/sbin:/bin',KDLOCK_RECOVERY_CONFIRMED='1',KDLOCK_SNAPSHOT_TAG='kdlock-builddisk-clean-20261031',PYTHONDONTWRITEBYTECODE='1')
with log.open('x') as f:
 p=subprocess.Popen(argv,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);ret=p.wait(timeout=7200)
assert ret==0
r=json.loads((out/'result.json').read_text());assert r['passed'] and r['drained'];print(json.dumps({'passed':True,'sessions':len(r['sessions'])}))
'''
  result=json.loads(guest(code,'syscall-'+act,7400));assert result['sessions']==(6 if act=='functional' else 126)
  capture('syscall-'+act+'-after');previous=base+'/result.json'
 retain([c['campaign']+'/syscall-functional',c['campaign']+'/syscall-measure'],'syscall')

try:
 r['phase']='waiting-for-nano';save();deadline=time.monotonic()+40000
 while True:
  n=json.loads((T/'kdlock-master-nano-r3-20261101/status.json').read_text());assert not n.get('error'),n.get('error')
  if n['completed']:break
  assert time.monotonic()<deadline;time.sleep(10)
 retain(['/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench/master-native-20261101','/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/master-native-master-20261101'],'nano')
 archive=T/'kdlock-master-mm-e97e218f-20261101.tar';upload(archive,str(archive));upload(Path(c['harness']['manifest']['path']),c['harness']['manifest']['path'])
 # Only immutable copies are created; generated kernel bytes keep their original recipe identity.
 code='c='+repr(c)+'\narchive='+repr(str(archive))+'\n'+'''from pathlib import Path
import hashlib,json,os,runpy,shutil,sys,tarfile
root=Path('/root/host_fs/kdlock');sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
assert not root.is_mount() and shutil.disk_usage('/mnt/kdlock-builds2').free>2*1024**3
m=json.loads(Path(c['harness']['manifest']['path']).read_text());assert hashlib.sha256(Path(archive).read_bytes()).hexdigest()==m['archive_sha256']
dest=Path(c['harness']['source']);assert not dest.exists();dest.mkdir()
with tarfile.open(archive) as t:
 for x in t:
  assert not Path(x.name).is_absolute() and '..' not in Path(x.name).parts and (x.isfile() or x.isdir())
 t.extractall(dest,filter='data')
for name,row in m['files'].items():assert hashlib.sha256((dest/name).read_bytes()).hexdigest()==row['sha256']
old=Path('/mnt/kdlock-builds2/kdlock-scope4-recipe-9f9fb90e')
for directory in ('kernel_module','include','kernel_integration/real_api','kernel_integration/linux70'):
 for path in (dest/directory).rglob('*'):
  if path.is_file() and path.relative_to(dest).as_posix()!='kernel_integration/linux70/verify.py':
   assert (old/path.relative_to(dest)).read_bytes()==path.read_bytes(),str(path)
print(json.dumps({'completed':True,'recipe':str(dest),'compiled_kernel_recipe':'9f9fb90e9de861fddeb498e068c0c31122919337','provider_matches':True}))
'''
 r['source_preparation']=json.loads(guest(code,'source-prepare',900));save()
 boot='e5fdef36-89c7-416a-97d6-72ff85dbee6a';view('bind',boot,'unit-bind')
 tests='bench/test_kernel_profiles.py bench/test_mmap1.py bench/test_mmap_writer_observation.py bench/test_mmap_writer_return_sites.py bench/test_kernel_api.py infrastructure/test_linux70_scope_identity.py'
 argv=['make','-C','/root/host_fs/kdlock/tests/unit','-B','run','TESTS=','PYTHON='+PY,'PY_TESTS='+tests]
 code='argv='+repr(argv)+'\n'+'''from pathlib import Path
import subprocess
p=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/master-harness-unit-20261101.log');assert not p.exists()
with p.open('x') as f:r=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
assert r.returncode==0 and 'Unit tests: 6 passed, 0 failed' in p.read_text();print('PASS six affected Python groups; basic C checks already passed on unchanged sources')
'''
 guest(code,'harness-unit',1900);view('unbind',boot,'unit-unbind')
 append_path='/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reader-kernel-actions-r2-20261101/scope4-append/result.json'
 _,append=readfile(append_path,'existing-append')
 for mode in ('native','kd'):
  arm=action('arm',boot,mode+'-arm',append,mode);request=action('request',boot,mode+'-request',arm)
  boot,request=observe(boot,'7.0.0-38-kdscope4',mode,request);captured=action('capture',boot,mode+'-capture',request,mode)
  value,_=readfile(captured['path'],mode+'-captured');view('bind',boot,mode+'-bind')
  local=T/('kdlock-master-mm-'+mode+'-20261101')
  run(['python3',str(T/'kdlock-master-mm-sequence-20261101.py'),'--config',str(C),'--config-sha256',sha(C),'--arm',mode,'--boot-id',boot,'--bundle-sha256',value['bundle_manifest_sha256'],'--output',str(local)],mode+'-mm',18000)
  seq=json.loads((local/'status.json').read_text());assert seq['completed'];retain([c['campaign']+'/'+mode,c['campaign']+'-controller-logs/'+mode],mode+'-mm')
  if mode=='native':syscall(boot)
  view('unbind',boot,mode+'-unbind')
 request=action('normal-request',boot,'normal-request',captured);boot,request=observe(boot,'7.0.0-38-kdlock1','normal',request)
 r['normal_restoration']=action('normal-verify',boot,'normal-verify',request)
 pool=c['pool'];args=['sudo','-n','taskset','-c','63','python3','/tmp/kdlock-master-pool-20261101.py','restore','--capture-helper','/tmp/kdlock-qemu-stable-pool-capture-host-20261030.py','--inventory','/tmp/kdlock-qemu-readonly-inventory-20261030.json','--snapshot',pool['snapshot'],'--cohort',pool['cohort'],'--policy','/tmp/kdlock-master-pool-activate-20261101/result.json','--policy-sha256',pool['activation']['sha256'],'--output','/tmp/kdlock-master-pool-restore-20261101','--idle-confirmed','--nano-archived']
 run(SSH+[shlex.join(args)],'pool-restore',210);r.update(completed=True,finished=time.time());save()
except BaseException as e:r.update(error=repr(e),finished=time.time());save();raise
