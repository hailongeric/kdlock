"""Complete the approved scoped MM pair after the preserved Nano/build prerequisites."""
from pathlib import Path
import base64,hashlib,json,shlex,subprocess,time
T=Path('/tmp');O=T/'kdlock-reader-mm-followthrough-r2-20261101';O.mkdir(exist_ok=False)
C=T/'kdlock-reader-recovery-mm-r2-20261101.json';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(C)=='6d950639b6b9ae30049b36fa26f88a2c584418b7bd70a2b96f8a96afb0239003';c=json.loads(C.read_bytes())
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71'];VM='/home/eric/vm/qemu-scripts/vm_ssh.sh';PY=c['python']
G='/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reader-kernel-actions-r2-20261101'
r=dict(completed=False,phase='WAITING_FOR_BUILD',actions=[],mm=[],uploads=[],started=time.time(),performance_accepted=False)
def save():(O/'status.json').write_text(json.dumps(r,indent=2)+'\n')
def run(argv,name,bound=120,data=None,allow_disconnect=False):
 r['phase']=name;save()
 with (O/(name+'.stdout')).open('xb') as out,(O/(name+'.stderr')).open('xb') as err:
  ch=subprocess.Popen(argv,stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);r['child_pid']=ch.pid;save();ch.communicate(data,timeout=bound)
 assert ch.returncode==0 or (allow_disconnect and ch.returncode==255),(name,ch.returncode)
 return (O/(name+'.stdout')).read_bytes(),ch.returncode

def guest(code,name,bound=120):return run(SSH+[shlex.join([VM,'python3 -'])],name,bound,code.encode())[0]
def readfile(path,name):
 code="from pathlib import Path\nimport base64,hashlib,json\np=Path("+repr(path)+");d=p.read_bytes();print(json.dumps({'data':base64.b64encode(d).decode(),'sha256':hashlib.sha256(d).hexdigest()}))\n"
 x=json.loads(guest(code,name));data=base64.b64decode(x['data'],validate=True);assert hashlib.sha256(data).hexdigest()==x['sha256'];(O/(name+'.json')).write_bytes(data);return json.loads(data),dict(path=path,sha256=x['sha256'])
def upload(local,target):
 local=Path(local);digest=sha(local);code="from pathlib import Path\nimport hashlib,os,sys\np=Path("+repr(target)+");h="+repr(digest)+"\nd=sys.stdin.buffer.read();assert os.geteuid()==0 and hashlib.sha256(d).hexdigest()==h and p.parent.is_dir() and not p.is_symlink()\nif p.exists():assert p.is_file() and p.read_bytes()==d\nelse:\n with p.open('xb') as f:f.write(d)\nassert hashlib.sha256(p.read_bytes()).hexdigest()==h\n"
 run(SSH+[shlex.join([VM,shlex.join(['python3','-c',code])])],'upload-'+str(len(r['uploads'])),120,local.read_bytes());r['uploads'].append(dict(local=str(local),path=target,sha256=digest));save();return dict(path=target,sha256=digest)
def action(controller,act,config,boot,label,prior=None,append=None,mode=None):
 out=T/('kdlock-reader-action-'+label+'-r2-20261101');argv=['python3',str(T/'kdlock-reader-kernel-action-20261101.py'),'--controller',controller,'--action',act,'--config',str(config),'--config-sha256',sha(config),'--boot-id',boot,'--guest-output',G+'/'+label,'--output',str(out)]
 for key,ref in [('prior',prior),('append',append)]:
  if ref:argv+=['--'+key,ref['path'],'--'+key+'-sha256',ref['sha256']]
 if mode:argv+=['--mode',mode]
 run(argv,label,4500);s=json.loads((out/'status.json').read_bytes());r['actions'].append(dict(label=label,status=str(out/'status.json'),**s));save()
 if act in ['request','normal-request']:
  assert s.get('reboot_action_invoked') and s.get('completion_requires_readback');return dict(path=G+'/'+label+'/result.json')
 assert s['completed'];return dict(path=s['result_path'],sha256=s['result_sha256'])
def observe_boot(old,release,label,request):
 code="from pathlib import Path\nimport json,os\nprint(json.dumps({'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'cmdline':Path('/proc/cmdline').read_text().strip()}))\n"
 end=time.monotonic()+600;i=0
 while True:
  assert time.monotonic()<end,'new boot observation timed out; no additional reboot requested'
  data,rc=run(SSH+[shlex.join([VM,'python3 -'])],label+'-observe-'+str(i),45,code.encode(),allow_disconnect=True);i+=1
  if rc==0:
   x=json.loads(data)
   if x['boot_id']!=old:
    assert x['release']==release,x;r[label+'-observed']=x;save();break
  time.sleep(10)
 req,ref=readfile(request['path'],label+'-durable-request');assert req['boot_id']==old and any(z.get('name')=='reboot' and z.get('pid') for z in req['commands']);return x['boot_id'],ref

def view(action_name,boot,label,transfer=None):
 inputs=dict(action=action_name,boot=boot,recipe=c['harness']['source'],manifest=c['harness']['manifest'],commit=c['harness']['commit'])
 if transfer:inputs['transfer']=upload(transfer,'/tmp/'+Path(transfer).parent.name+'-transfer.json')
 code='v='+repr(inputs)+'\n'+'''from pathlib import Path
import hashlib,json,os,runpy,subprocess,sys,time
assert os.geteuid()==0 and Path('/proc/sys/kernel/random/boot_id').read_text().strip()==v['boot']
root=Path('/root/host_fs/kdlock');recipe=Path(v['recipe']);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(v['manifest']['path'])==v['manifest']['sha256'];m=json.loads(Path(v['manifest']['path']).read_bytes());assert m['source_commit']==v['commit']
for n,z in m['files'].items():assert sha(recipe/n)==z['sha256']
sys.path.insert(0,str(recipe/'bench/spin_cacheline'));import bench_runtime as rt
idle=runpy.run_path(str(recipe/'bench/archive_run.py'))['idle'];idle(root,rt.idle);idle(recipe,rt.idle)
if v['action']=='bind':
 assert not root.is_mount()
 subprocess.run(['mount','--bind',str(recipe),str(root)],check=True,timeout=30)
 subprocess.run(['mount','-o','remount,bind,ro',str(root)],check=True,timeout=30)
 assert root.is_mount() and os.path.samefile(root,recipe) and os.statvfs(root).f_flag & os.ST_RDONLY
else:
 assert v['action']=='unbind' and root.is_mount() and os.path.samefile(root,recipe) and os.statvfs(root).f_flag & os.ST_RDONLY
 assert sha(v['transfer']['path'])==v['transfer']['sha256'];t=json.loads(Path(v['transfer']['path']).read_bytes());assert t['completed']
 subprocess.run(['umount',str(root)],check=True,timeout=30);assert not root.is_mount()
idle(root,rt.idle);print(json.dumps(dict(completed=True,action=v['action'],boot_id=v['boot'],recipe=v['recipe'],manifest=v['manifest'],finished=time.time())))
'''
 result=json.loads(guest(code,label,180));assert result['completed'];r[label]=result;save()
def mm(arm,boot,bundle_sha):
 local=T/('kdlock-reader-mm-'+arm+'-r2-20261101');view('bind',boot,arm+'-source-bind')
 run(['python3',str(T/'kdlock-reader-recovery-mm-sequence-r2-20261101.py'),'--config',str(C),'--config-sha256',sha(C),'--arm',arm,'--boot-id',boot,'--bundle-sha256',bundle_sha,'--output',str(local)],arm+'-mm',15000)
 seq=json.loads((local/'status.json').read_bytes());assert seq['completed'] and seq['arm']==arm and seq['boot_id']==boot
 sr=upload(local/'status.json','/tmp/kdlock-reader-mm-'+arm+'-sequence-r2-20261101.json');sc=upload(T/'kdlock-reader-recovery-mm-sequence-r2-20261101.py','/tmp/kdlock-reader-recovery-mm-sequence-r2-20261101.py')
 arc=T/'kdlock-reader-recovery-mm-archive-r2-20261101.py';upload(arc,str(arc));b=dict(schema=1,arm=arm,boot_id=boot,bundle_manifest_sha256=bundle_sha,config=dict(path=str(C),sha256=sha(C)),owners=seq['owners'],sequence=sr,sequence_controller=sc)
 bp=O/(arm+'-archive-bindings.json');bp.write_text(json.dumps(b,indent=2)+'\n');br=upload(bp,'/tmp/kdlock-reader-mm-'+arm+'-archive-bindings-r2-20261101.json')
 run(SSH+[shlex.join([VM,shlex.join([PY,str(arc),'--bindings',br['path'],'--bindings-sha256',br['sha256']])])],arm+'-archive',4000)
 control=c['campaign']+'/'+arm+'-archive-control';archives=c['campaign']+'/'+arm+'-archives'
 refs={}
 for key,path in [('archive-owner',control+'/owner.json'),('archive',archives+'/archives.json'),('inventory',archives+'/input-inventory.json'),('aliases',control+'/alias-map.json'),('preservation-map',control+'/preservation-map.json')]:
  value,ref=readfile(path,arm+'-archive-'+key);refs[key]=ref
  if key=='archive-owner':assert value['completed'] and value['idle'] and not value['drain_unknown']
 dest=T/('kdlock-reader-mm-'+arm+'-evidence-r2-20261101');argv=['python3',str(T/'kdlock-reader-recovery-mm-fetch-r2-20261101.py'),'--arm',arm,'--boot-id',boot,'--destination',str(dest)]
 for key,ref in refs.items():argv+=['--'+key+'-sha256',ref['sha256']]
 run(argv,arm+'-fetch',1900);transfer=json.loads((dest/'transfer.json').read_bytes());assert transfer['completed']
 r['mm'].append(dict(arm=arm,boot_id=boot,bundle_sha256=bundle_sha,sequence=str(local/'status.json'),evidence=str(dest),archive_refs=refs));save();view('unbind',boot,arm+'-source-unbind',dest/'transfer.json')
try:
 save();end=time.monotonic()+36000
 while True:
  assert time.monotonic()<end,'build wait expired; no install started'
  b=json.loads((T/'kdlock-reader-scope4-build-coordinate-r3-20261101/status.json').read_bytes());assert not b.get('error'),b.get('error')
  if b['completed']:break
  time.sleep(5)
 nano=json.loads((T/'kdlock-reader-recovery-campaign-20261101/status.json').read_bytes());offline=json.loads((T/'kdlock-reader-recovery-offline-watch-20261101/status.json').read_bytes());assert nano['completed'] and offline['completed']
 built,bref=readfile(b['build_result'],'build-receipt');assert bref['sha256']==b['build_result_sha256'] and built['passed'] and built['state']=='COMPLETE' and not built['drain_unknown']
 k=json.loads((T/'kdlock-reader-scope4-kernel-r3-20261101.json').read_bytes());assert built['source_commit']==k['commit'] and built['provider_commit']==k['provider_commit'] and built['release']==k['release']
 old=json.loads((T/'kdlock-writer-queue-scope3-install-config-20261031.json').read_bytes())
 config={key:old[key] for key in ['schema','install_controller_sha256','python','data_mount','snapshot','normal_build','normal_bundle','normal_bundle_sha256']}
 config.update({key:k[key] for key in ['recipe','manifest','manifest_sha256','commit','provider_commit','source','build','release','ubuntu']})
 config.update(kernel_config_sha256=built['outputs']['.config']['sha256'],build_result=bref['path'],build_result_sha256=bref['sha256'],stage='/mnt/kdlock-builds2/kdlock-scope4-modules-stage-9f9fb90e-20261101',variants=dict(native='kdscope4-native',kd='kdscope4-kd'),bundles=dict(native='/root/kdlock-kernel-baselines/linux70-kdscope4-native-20261101',kd=c['arms']['recovery']['bundle']),mmap_prepare=k['mmap_prepare']+'/prepare.json',api_prepare=k['api_prepare']+'/prepare.json')
 I=T/'kdlock-reader-scope4-install-r2-20261101.json';assert not I.exists();I.write_text(json.dumps(config,indent=2)+'\n');r['install_config']=dict(path=str(I),sha256=sha(I));save();boot=k['boot_id']
 stage=action('install','stage',I,boot,'scope4-stage');installed=action('install','install',I,boot,'scope4-install',prior=stage);append=action('install','append',I,boot,'scope4-append',prior=installed)
 arm=action('promoted','arm',C,boot,'scope3-arm',append=append);request=action('promoted','request',C,boot,'scope3-request',prior=arm);boot,request=observe_boot(boot,'7.0.0-38-kdscope3','scope3',request);captured=action('promoted','capture',C,boot,'scope3-capture',prior=request)
 mm('promoted',boot,'c0b832fc285a665b566022160d45b6ea1f93d148158872d313f1590bc22138c0')
 arm=action('install','arm',I,boot,'scope4-arm',prior=append,mode='kd');request=action('install','request',I,boot,'scope4-request',prior=arm);boot,request=observe_boot(boot,k['release'],'scope4',request);captured=action('install','capture',I,boot,'scope4-capture',prior=request)
 cv,cr=readfile(captured['path'],'scope4-captured-result');assert cr==captured;mm('recovery',boot,cv['bundle_manifest_sha256'])
 request=action('install','normal-request',I,boot,'normal-request',prior=captured);boot,request=observe_boot(boot,'7.0.0-38-kdlock1','normal',request);restored=action('install','normal-verify',I,boot,'normal-verify',prior=request)
 pool='/tmp/kdlock-reader-recovery-pool-restore-20261101';cmd=['sudo','-n','taskset','-c','63','python3','/tmp/kdlock-reader-recovery-pool-r2-20261101.py','restore','--capture-helper','/tmp/kdlock-qemu-stable-pool-capture-host-20261030.py','--inventory','/tmp/kdlock-qemu-readonly-inventory-20261030.json','--snapshot',c['pool']['snapshot'],'--cohort',c['pool']['cohort'],'--policy','/tmp/kdlock-reader-recovery-pool-activate-r2-20261101/result.json','--policy-sha256',c['pool']['activation']['sha256'],'--output',pool,'--idle-confirmed','--nano-archived']
 run(SSH+[shlex.join(cmd)],'pool-restore',180);d,_=run(SSH+[shlex.join(['cat',pool+'/result.json'])],'pool-restoration-read',30);p=json.loads(d);assert p['completed'] and p['restored_settings'] and not p['policy_state_unknown'];r.update(completed=True,normal_restoration=restored,pool_restoration=p,finished=time.time())
except BaseException as e:r['error']=repr(e);raise
finally:r['finished']=time.time();save();print(json.dumps(r),flush=True)
