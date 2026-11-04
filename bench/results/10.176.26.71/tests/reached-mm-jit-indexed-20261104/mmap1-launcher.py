#!/usr/bin/env python3
"""Source-host launcher for one unscored, two-model mmap1 diagnostic.

This file is prepared for review; constructing or AST-parsing it performs no
remote operation. Invocation performs idle-only metadata transfer and a fresh
physical-host capture. A persistent guest monitor starts before its controller
can activate the factory. Thereafter this launcher opens no guest sessions,
and the monitor uses direct file reads rather than inspection subprocesses.
Timeouts retain every process and report unknown lifetime; nothing is killed.
"""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

CANDIDATE = '626bd9fb78d1b2876534dce77df8aa213cfabbb9'
GUEST_ROOT = '/root/kdlock-inputs/reached-mm-indexed-code-626bd9fb-20261103'
STATE_SHA256 = '4d908ca8a24daecb3a9ea629417f6ad0feb2851dd90e0128f34e2f68943e2fd0'
MANIFEST_SHA256 = 'd8176384d6140c1f3207728e8418de358023a47a0454b81d4c38770259d64481'
BOOT = '7bc570a9-f357-4dce-a165-49e6a7ffa7b5'
BUILD_ID = '5f2fce72a33480f6e79a79b374b21a0db377ecd1'
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
KDIR = '/mnt/kdlock-builds2/linux-7.0.0-38-kdscope5/build'
BUNDLE = '/root/kdlock-kernel-baselines/linux70-kdscope5-log16-kd-20261103'
INPUTS = '/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kdscope1-mm-f7a84065-20261030/native-a/mmap1-prepare/inputs.json'
INPUTS_SHA256 = 'beeb3e82481b881ba09d77667408f29fc37366b7fe5d987f3fd02af0c5ac4dc0'
SITES = Path('/tmp/kdlock-mm-scope5-v3-elf-20261103/sites.json')
SITES_SHA256 = 'bcc3b8b23fc332904e26929e7e43961416d11db705480ed63e301dca07e1a7a1'
PREREQUISITE = '/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reached-mm-indexed-code-units-20261103/result.json'
SNAPSHOT = 'kdlock-builddisk-clean-20261031'
GUEST_LAUNCH = '/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reached-mm-indexed-jit-proof-launch-20261104'
GUEST_OUTPUT = '/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reached-mm-indexed-jit-proof-20261104'
LOCAL_OUTPUT = Path('/tmp/kdlock-reached-mm-indexed-jit-proof-launch-20261104')
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'eric@10.176.26.71']
WRAPPER = '/home/eric/vm/qemu-scripts/vm_ssh.sh'
HOST_CAPTURE_SHA256 = 'e9417457c4d33eea2a84f70af0ed2839ce5b07abbd4dd70bb84ea66fdaf9bb74'

HOST_CAPTURE = r'''from pathlib import Path
import hashlib,json,runpy
p=Path('/tmp/kdlock-qemu-stable-pool-capture-host-20261030.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()==%r
print(json.dumps(runpy.run_path(str(p))['capture'](%r,Path('/tmp/qemu-monitor.sock'))))
''' % (HOST_CAPTURE_SHA256, SNAPSHOT)

GUEST_MONITOR = r'''from pathlib import Path
import errno,hashlib,importlib.util,json,os,re,runpy,shutil,struct,subprocess,sys,time,traceback
c=json.loads(Path(sys.argv[1]).read_text())
root=Path(c['root']);launch=Path(c['launch']);out=Path(c['output'])
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def emit(event,**values):print(json.dumps(dict(event=event,**values),sort_keys=True),flush=True)
def write(name,value):
 p=launch/name;temporary=p.with_suffix(p.suffix+'.tmp')
 temporary.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');temporary.replace(p)
def notes_id():
 data=Path('/sys/kernel/notes').read_bytes();offset=0;found=[]
 while offset+12<=len(data):
  namesz,descsz,kind=struct.unpack_from('<3I',data,offset);offset+=12
  name=data[offset:offset+namesz];offset+=(namesz+3)&~3
  value=data[offset:offset+descsz];offset+=(descsz+3)&~3
  assert offset<=len(data),'incomplete running kernel note'
  if name.rstrip(b'\0')==b'GNU' and kind==3:found.append(value.hex())
 assert len(found)==1,'exact running GNU BuildID unavailable'
 return found[0]
def idle():
 runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
last_request_read=0
request_snapshot=None
postrun_models=set()
def progress():
 global last_request_read,request_snapshot
 try:
  value=json.loads((out/'result.json').read_text())
  result=dict(state=value.get('state'),passed=value.get('passed'),drained=value.get('drained'),
              models={name:{key:row.get(key) for key in ('state','passed','factory_active','completed_requests','error')}
                      for name,row in value.get('models',{}).items()})
  for model,row in value.get('models',{}).items():
   if row.get('state')=='DRAINING' and model not in postrun_models:
    parameters=Path('/sys/module/kdlock_km/parameters')
    if ((parameters/'rwsem_provider_active').read_text().strip()=='N' and
        rt.status()['frames']==0 and bench.execution.reached_observations()['active']==0):
     finished=postrun.progress(parameters,rt.status,bench.execution.reached_observations)
     write('postrun-'+model+'.json',finished);postrun_models.add(model)
  commands=value.get('commands',[])
  if commands:result['command']={key:commands[-1].get(key) for key in ('name','pid','returncode','timed_out')}
  for model in ('threads','processes'):
   try:
    rows=json.loads((out/model/'registry-progress.json').read_text())
    result.setdefault('images',{})[model]=dict(total=len(rows),ready=sum(row['status']==0 for row in rows),
      pending=sum(row['status']==-1 for row in rows),other=sum(row['status'] not in (-1,0) for row in rows))
   except (FileNotFoundError,json.JSONDecodeError):pass
  now=time.monotonic()
  if now-last_request_read>=1:
   last_request_read=now
   try:
    parameters=Path('/sys/module/kdlock_km/parameters')
    request_snapshot=dict(requests=(parameters/'service_progress').read_text(),
                          reached=(parameters/'reached_stats').read_text())
   except (FileNotFoundError,OSError):request_snapshot=None
  if request_snapshot is not None:result['runtime']=request_snapshot
  return result
 except (FileNotFoundError,json.JSONDecodeError):return {'state':'BEFORE_FIRST_RECEIPT'}

result=dict(passed=False,drained=False,accepted=False,scored=False,source_commit=c['candidate'],
            controller_started=False,processes_left_untouched=True)
child=None
kernel_fd=None
kernel_log=None
kernel_bytes=0
kernel_fault=False
kernel_losses=0
kernel_buffer=bytearray(1<<20)
kernel_view=memoryview(kernel_buffer)
kernel_iov=[kernel_buffer]
def collect_kernel():
 global kernel_bytes,kernel_fault,kernel_losses
 for _ in range(4096):
  try:
   size=os.readv(kernel_fd,kernel_iov)
   data=bytes(kernel_view[:size])
  except BlockingIOError: break
  except OSError as error:
   if error.errno!=errno.EPIPE:raise
   kernel_losses+=1
   if kernel_losses==1:emit('cursor-loss',errno=error.errno)
   continue
  if not data: break
  kernel_bytes+=len(data)
  assert kernel_bytes<=1024*1024**2,'resident diagnostic log exceeded bound'
  kernel_log.write(data)
  if rt.kernel_fault(data.decode(errors='replace')) and not kernel_fault:
   kernel_fault=True;kernel_log.flush();emit('kernel-stop',line=data.decode(errors='replace')[:1200])
try:
 assert os.geteuid()==0 and sys.executable==c['python'] and os.sched_getaffinity(0)=={62}
 assert os.environ.get('KDLOCK_PRIVATE_SOURCE_STATE_SHA256')==c['state_sha256']
 assert os.environ.get('KDLOCK_PRIVATE_SOURCE_MANIFEST_SHA256')==c['manifest_sha256']
 assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['boot']
 assert os.uname().release=='7.0.0-38-kdscope5' and notes_id()==c['build_id']
 assert [v for v in Path('/proc/cmdline').read_text().split() if v.startswith('kd_mmap=')]==['kd_mmap=on']
 assert 'log_buf_len=16M' in Path('/proc/cmdline').read_text()
 assert not out.exists()
 assert digest(root/'source-state.json')==c['state_sha256']
 assert digest(root/'source-sha256.json')==c['manifest_sha256']
 state=json.loads((root/'source-state.json').read_text());manifest=json.loads((root/'source-sha256.json').read_text())
 assert state['git_head']==c['candidate'] and state['git_status']=='' and state['files']==len(manifest)
 assert not state['omitted_missing_tracked_paths']
 for name,wanted in manifest.items():assert digest(root/name)==wanted,name
 for name,wanted in c['artifacts'].items():assert digest(launch/name)==wanted,name
 sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
 idle()
 prior_path=Path(c['prerequisite']);prior=json.loads(prior_path.read_text())
 assert prior['source_commit']==c['candidate'] and prior['passed'] and prior['final_idle']
 assert len(prior['units'])==2 and prior['units'][0]['args']==['execution/test_reached_jit.py'] and prior['units'][1]['args']==['bench/test_mmap1_delegated.py','-v'] and len(prior['cold_result']['phases'])==11 and prior['cold_returncode']==0 and prior['cold_result']['passed'] and prior['cold_result']['drained'] and all(row['returncode']==0 for row in prior['units'])
 prerequisites=dict(focused_units=dict(source_commit=prior['source_commit'],drivers=len(prior['units']),
   path=str(prior_path),sha256=digest(prior_path)))
 assert digest(c['inputs'])==c['inputs_sha256']
 spec=importlib.util.spec_from_file_location('actual_mmap1_launch_inputs',root/'bench/mmap1/run.py')
 bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
 sys.path.insert(0,str(launch));import postrun
 prepared=bench.inputs_from(Path(c['inputs']))
 # The maintained guest admission runs without an override. A private-root
 # admission mismatch stops here before building/loading any provider.
 import argparse
 admission=argparse.Namespace(mode='kd',boot_id=c['boot'],kernel_variant='kdscope5-log16-kd',
     kernel_source=Path(c['kdir']),kernel_baseline=Path(c['bundle']))
 bench.guest(admission)
 idle()
 result.update(prerequisites=prerequisites,prerequisite=None,
   inputs=dict(path=c['inputs'],sha256=c['inputs_sha256'],binary_sha256=prepared['binary_sha256']),
   boot_id=c['boot'],running_build_id=c['build_id'],before_launch_idle=True)
 # Topology admission needs the full worker affinity; point collectors pin themselves.
 argv=['taskset','-c','0-63',c['python'],str(root/'tests/kernel/mmap1_identity/delegated.py'),
   '--inputs',c['inputs'],'--inputs-sha256',c['inputs_sha256'],
   '--source-commit',c['candidate'],'--source-state',str(root/'source-state.json'),
   '--source-state-sha256',c['state_sha256'],'--source-manifest',str(root/'source-sha256.json'),
   '--source-manifest-sha256',c['manifest_sha256'],'--sites',str(launch/'sites.json'),
   '--sites-sha256',c['sites_sha256'],'--execution-mode','reached','--model-order','threads-first','--executor-cpus','0-61','--diagnostic-log-mib','512','--mode','kd','--kernel-variant','kdscope5-log16-kd',
   '--boot-id',c['boot'],'--kernel-source',c['kdir'],'--kernel-baseline',c['bundle'],
   '--host-state',str(launch/'host-before.json'),'--host-reference',str(launch/'host-reference.json'),
   '--host-reference-sha256',c['host_sha256'],'--output',c['output']]
 result.update(argv=argv,started_ns=time.monotonic_ns(),deadline_seconds=2400)
 write('monitor-result.json',result)
 kernel_fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
 os.lseek(kernel_fd,0,os.SEEK_END)
 kernel_log=(launch/'resident-kernel.log').open('xb',buffering=64*1024)
 with (launch/'controller.log').open('xb') as log:
  child=subprocess.Popen(argv,cwd=root,env=dict(os.environ),stdin=subprocess.DEVNULL,
                         stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  fields=(Path('/proc')/str(child.pid)/'stat').read_text().rsplit(')',1)[1].split()
  result.update(controller_started=True,pid=child.pid,start_ticks=int(fields[19]))
  write('monitor-result.json',result);emit('controller-start',pid=child.pid,argv=argv)
  deadline=time.monotonic()+2400;last=None;last_print=0
  while child.poll() is None:
   collect_kernel()
   assert shutil.disk_usage('/').free>1024**3,'root diagnostic headroom fell below 1 GiB'
   now=time.monotonic();row=progress();stamp=json.dumps(row,sort_keys=True)
   if stamp!=last or now-last_print>=20:
    emit('progress',pid=child.pid,elapsed_seconds=int((time.monotonic_ns()-result['started_ns'])/1e9),**row)
    last=stamp;last_print=now
   if now>=deadline:
    result.update(timed_out=True,lifetime='UNKNOWN',last_progress=row)
    write('monitor-result.json',result);emit('timeout',pid=child.pid,lifetime='UNKNOWN',processes_left_untouched=True)
    sys.exit(124)
   time.sleep(0.01)
 collect_kernel();kernel_log.close();os.close(kernel_fd)
 result.update(resident_log_bytes=kernel_bytes,resident_fault=kernel_fault,resident_losses=kernel_losses,returncode=child.returncode,finished_ns=time.monotonic_ns(),last_progress=progress())
 final=json.loads((out/'result.json').read_text()) if (out/'result.json').exists() else {}
 result['controller_result']=dict(path=str(out/'result.json'),sha256=digest(out/'result.json') if final else None,
   state=final.get('state'),passed=final.get('passed'),drained=final.get('drained'),accepted=final.get('accepted'))
 if child.returncode==0:
  assert not kernel_fault and not kernel_losses
  assert final['passed'] and final['drained'] and final['final_idle'] and not final['accepted'] and not final['scored']
  assert set(final['models'])=={'threads','processes'}
  assert all(row['passed'] and row['drained'] for row in final['models'].values())
  idle();subprocess.run(['grub-editenv','/boot/grub/grubenv','unset','next_entry'],check=True,timeout=30)
  result.update(passed=True,drained=True,final_idle=True,recovery_next_boot_cleared=True)
 write('monitor-result.json',result);emit('complete',**result)
 sys.exit(0 if result['passed'] else 1)
except Exception as error:
 result.update(error=repr(error),traceback=traceback.format_exc(),lifetime='UNKNOWN' if child else 'NOT_STARTED')
 write('monitor-result.json',result);emit('failed',**result)
 raise
'''

UPLOAD = r'''from pathlib import Path
import base64,hashlib,json,os,runpy,shutil,subprocess,sys
c=json.loads(sys.stdin.buffer.read());root=Path(c['root']);launch=Path(c['launch'])
assert os.uname().release=='7.0.0-38-kdscope5'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['boot']
assert [v for v in Path('/proc/cmdline').read_text().split() if v.startswith('kd_mmap=')]==['kd_mmap=on']
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
assert not launch.exists() and not Path(c['output']).exists()
assert shutil.disk_usage(launch.parent).free>4*1024**3
assert hashlib.sha256((root/'source-state.json').read_bytes()).hexdigest()==c['state_sha256']
assert hashlib.sha256((root/'source-sha256.json').read_bytes()).hexdigest()==c['manifest_sha256']
launch.mkdir()
for name,encoded in c.pop('file_bytes').items():
 assert Path(name).name==name
 data=base64.b64decode(encoded);assert hashlib.sha256(data).hexdigest()==c['artifacts'][name]
 with (launch/name).open('xb') as stream:stream.write(data)
 (launch/name).chmod(0o600)
with (launch/'launch.json').open('x') as stream:json.dump(c,stream,sort_keys=True,indent=2)
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
assert hashlib.sha256(Path('/etc/default/grub').read_bytes()).hexdigest()=='e02f11d6ea1b3c31d789afdae3bb5589038c49eb94dc0de18f7d8a6d0c475250'
subprocess.run(['grub-reboot','kdlock-7.0.0-38-kdscope5-log16'],check=True,timeout=30)
print(json.dumps(dict(passed=True,idle=True,recovery_next_boot='kdlock-7.0.0-38-kdscope5-log16',launch=str(launch),files=c['artifacts'],
  launch_sha256=hashlib.sha256((launch/'launch.json').read_bytes()).hexdigest())))
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    with path.open('xb') as stream:
        stream.write(data)


def main():
    assert sha(SITES.read_bytes()) == SITES_SHA256
    LOCAL_OUTPUT.mkdir(exist_ok=False)
    source = Path(__file__).resolve().read_bytes()
    save(LOCAL_OUTPUT / 'launcher.py', source)
    host = subprocess.run(SSH + ['sudo -n taskset -c 63 python3 -'], input=HOST_CAPTURE.encode(),
                          capture_output=True, timeout=60)
    save(LOCAL_OUTPUT / 'host.stderr', host.stderr)
    assert host.returncode == 0, host.stderr.decode(errors='replace')
    capture = json.loads(host.stdout)
    assert capture['snapshot_listed'] and capture['pins_verified'] and capture['frequency_verified']
    assert capture['recovery_snapshot'] == SNAPSHOT
    save(LOCAL_OUTPUT / 'host-before.json', host.stdout)
    save(LOCAL_OUTPUT / 'host-reference.json', host.stdout)
    file_bytes = {'sites.json': SITES.read_bytes(), 'host-before.json': host.stdout,
                'host-reference.json': host.stdout, 'monitor.py': GUEST_MONITOR.encode(), 'launcher.py': source,
                'postrun.py': Path('/tmp/kdlock-reached-path-translation/bench/mmap1/postrun.py').read_bytes()}
    config = dict(candidate=CANDIDATE, root=GUEST_ROOT, state_sha256=STATE_SHA256,
      manifest_sha256=MANIFEST_SHA256, boot=BOOT, build_id=BUILD_ID, python=PYTHON, kdir=KDIR,
      bundle=BUNDLE, inputs=INPUTS, inputs_sha256=INPUTS_SHA256, sites_sha256=SITES_SHA256,
      host_sha256=sha(host.stdout), snapshot=SNAPSHOT, launch=GUEST_LAUNCH, output=GUEST_OUTPUT,
      prerequisite=PREREQUISITE, artifacts={name:sha(data) for name,data in file_bytes.items()},
      reference_selection='same fresh verified capture bytes explicitly selected as reference and before',
      monitor_source_commit='626bd9fb78d1b2876534dce77df8aa213cfabbb9',
      scored=False, accepted=False, workers=2, models=['threads','processes'], rounds_per_point=1,
      file_bytes={name:base64.b64encode(data).decode() for name,data in file_bytes.items()})
    save(LOCAL_OUTPUT / 'launch.json', (json.dumps({k:v for k,v in config.items() if k!='file_bytes'},indent=2)+'\n').encode())
    environment=['env','PYTHONDONTWRITEBYTECODE=1','KDLOCK_RECOVERY_CONFIRMED=1',
      'KDLOCK_SNAPSHOT_TAG='+SNAPSHOT,'KDLOCK_PRIVATE_SOURCE_STATE_SHA256='+STATE_SHA256,
      'KDLOCK_PRIVATE_SOURCE_MANIFEST_SHA256='+MANIFEST_SHA256,
      'PATH='+str(Path(PYTHON).parent)+':/usr/sbin:/usr/bin:/sbin:/bin']
    upload_command=shlex.join(['taskset','-c','63',*environment,PYTHON,'-c',UPLOAD])
    uploaded=subprocess.run(SSH+[shlex.join([WRAPPER,upload_command])],input=json.dumps(config).encode(),
                            capture_output=True,timeout=90)
    save(LOCAL_OUTPUT / 'upload.stdout',uploaded.stdout);save(LOCAL_OUTPUT / 'upload.stderr',uploaded.stderr)
    assert uploaded.returncode==0,uploaded.stderr.decode(errors='replace')
    uploaded_receipt=json.loads(uploaded.stdout)
    assert uploaded_receipt['passed'] and uploaded_receipt['idle'] and uploaded_receipt['files']==config['artifacts']
    command=shlex.join(['taskset','-c','62',*environment,PYTHON,GUEST_LAUNCH+'/monitor.py',GUEST_LAUNCH+'/launch.json'])
    log_path=LOCAL_OUTPUT/'transport.log'
    with log_path.open('xb') as log:
        transport=subprocess.Popen(SSH+[shlex.join([WRAPPER,command])],stdin=subprocess.DEVNULL,
                                   stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        receipt=dict(source_commit=CANDIDATE,transport_pid=transport.pid,log=str(log_path),
                     guest_launch=GUEST_LAUNCH,guest_output=GUEST_OUTPUT,accepted=False,scored=False,
                     launcher_sha256=sha(source),host_sha256=sha(host.stdout),artifacts=config['artifacts'])
        (LOCAL_OUTPUT/'transport.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt),flush=True)
        deadline=time.monotonic()+2460
        while transport.poll() is None:
            if time.monotonic()>=deadline:
                receipt.update(timed_out=True,lifetime='UNKNOWN',processes_left_untouched=True)
                (LOCAL_OUTPUT/'transport.json').write_text(json.dumps(receipt,indent=2)+'\n')
                print('Transport deadline: existing processes left untouched; inspect local transport.log.',flush=True)
                return 124
            time.sleep(1)
        receipt.update(returncode=transport.returncode,transport_finished=True)
        (LOCAL_OUTPUT/'transport.json').write_text(json.dumps(receipt,indent=2)+'\n')
        return transport.returncode


if __name__ == '__main__':
    raise SystemExit(main())
