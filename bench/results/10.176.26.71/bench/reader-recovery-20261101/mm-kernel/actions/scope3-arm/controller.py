"""Select the existing promoted KD kernel once and verify its actual boot."""
from pathlib import Path
import argparse,datetime,hashlib,importlib.util,json,os,re,runpy,shlex,shutil,subprocess,sys,time
sys.dont_write_bytecode=True
p=argparse.ArgumentParser()
p.add_argument('action',choices=['arm','request','capture'])
for name in ['config','host-state','output']:p.add_argument('--'+name,type=Path,required=True)
for name in ['config-sha256','host-state-sha256','boot-id']:p.add_argument('--'+name,required=True)
p.add_argument('--append',type=Path);p.add_argument('--append-sha256');p.add_argument('--prior',type=Path);p.add_argument('--prior-sha256');a=p.parse_args()
def need(ok,why):
 if not ok:raise RuntimeError(why)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def checked(path,digest):
 need(sha(path)==digest,'input bytes differ: '+str(path));return json.loads(Path(path).read_bytes())
c=checked(a.config,a.config_sha256);root=Path(c['harness']['source']);m=checked(c['harness']['manifest']['path'],c['harness']['manifest']['sha256']);arm=c['arms']['promoted'];canonical=Path('/root/host_fs/kdlock');boot=lambda:Path('/proc/sys/kernel/random/boot_id').read_text().strip()
need(os.geteuid()==0 and sys.executable==c['python'] and boot()==a.boot_id,'guest/interpreter/boot differs')
need(not canonical.is_mount() and root.is_dir() and m['source_commit']==c['harness']['commit'],'source must be unbound with exact prepared recipe')
need(arm['variant']=='kdscope3-kd' and arm['release']=='7.0.0-38-kdscope3' and arm['provider_comparison_commit']=='1b6f256b13e8743aa1fd7bdc958cc82ae7726463','existing promoted kernel differs')
for name,row in m['files'].items():need(sha(root/name)==row['sha256'],'recipe changed: '+name)
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle);idle(canonical,rt.idle)
host=checked(a.host_state,a.host_state_sha256);spec=importlib.util.spec_from_file_location('reader_boot_host',root/'bench/basic/capture_host.py');hm=importlib.util.module_from_spec(spec);spec.loader.exec_module(hm);hm.validate(host)
age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds();need(0<=age<240 and host['pins_verified'] and host['frequency_verified'] and host['snapshot_listed'] and host['recovery_snapshot']==c['pool']['snapshot'],'fresh verified host/recovery required')
bundle=Path(arm['bundle']);bundle_sha='c0b832fc285a665b566022160d45b6ea1f93d148158872d313f1590bc22138c0';bm=checked(bundle/'manifest.json',bundle_sha)
for name,digest in bm['installed_files'].items():need(sha(Path('/')/name)==digest,'existing installed file differs: '+name)
need(a.output.is_absolute() and a.output.is_relative_to('/mnt/kdlock-builds2/kdlock-evidence') and not a.output.exists(),'new DATA2 output required')
prior=checked(a.prior,a.prior_sha256) if a.prior else None
custom=Path('/boot/grub/custom.cfg');grub=Path('/boot/grub/grub.cfg');defaults=Path('/etc/default/grub');protected={str(x):sha(x) for x in [custom,grub,defaults]};entry='kdlock-7.0.0-38-kdscope3-kd'
a.output.mkdir(parents=True);r=dict(passed=False,completed=False,action=a.action,boot_id=a.boot_id,controller_sha256=sha(__file__),config_sha256=a.config_sha256,harness_commit=c['harness']['commit'],bundle_manifest_sha256=bundle_sha,protected=protected,commands=[],started=time.time(),entry=entry,drain_unknown=False)
for path,name in [(Path(__file__),'controller.py'),(a.config,'config.json'),(a.host_state,'host-state.json')]:shutil.copyfile(path,a.output/name)
def save():
 t=a.output/'result.tmp'
 with t.open('w') as f:f.write(json.dumps(r,indent=2)+'\n');f.flush();os.fsync(f.fileno())
 t.replace(a.output/'result.json');fd=os.open(a.output,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def command(name,argv,bound=120):
 row=dict(name=name,argv=list(map(str,argv)),started=time.time());r['commands'].append(row);save()
 with (a.output/(name+'.log')).open('xb') as f:
  child=subprocess.Popen(row['argv'],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'));row['pid']=child.pid;r['drain_unknown']=True;save();row['returncode']=child.wait(timeout=bound)
 remaining=[]
 for path in Path('/proc').glob('[0-9]*/stat'):
  try:
   fields=path.read_text().rsplit(')',1)[1].split()
   if int(fields[2])==child.pid:remaining.append(int(path.parent.name))
  except (FileNotFoundError,ProcessLookupError):pass
 row.update(finished=time.time(),remaining_processes=remaining);save();need(not remaining,'command group remains: '+name);r['drain_unknown']=False;save();need(row['returncode']==0,'command failed: '+name);return (a.output/(name+'.log')).read_text()
def environment(name):
 lines=command(name,['grub-editenv','/boot/grub/grubenv','list']).splitlines();values={}
 for line in lines:
  k,sep,v=line.partition('=');need(sep and k not in values,'invalid boot environment');values[k]=v
 return values
def previous(action):
 need(prior and prior['passed'] and prior['completed'] and prior['action']==action and prior['config_sha256']==a.config_sha256 and prior['controller_sha256']==r['controller_sha256'] and prior['protected']==protected,'prior action differs')
verify=[c['python'],str(root/'kernel_integration/linux70/verify.py'),'--variant',arm['variant'],'--bundle',arm['bundle'],'--build-root',arm['build']]
save()
try:
 env=environment('environment-before');r['environment_before']=env
 if a.action=='arm':
  need(os.uname().release=='7.0.0-38-kdlock1' and not env.get('next_entry'),'normal boot with no queued entry required')
  appended=checked(a.append,a.append_sha256);need(appended['passed'] and appended['final_idle'] and not appended['drain_unknown'] and appended['action']=='append' and appended['release']=='7.0.0-38-kdscope4','completed scope4 append required')
  need(appended['custom_after']['sha256']==sha(custom),'current custom file differs from append receipt')
  need(appended['normal_default'] in re.findall(r'(?m)^\s*set default="([^"]+)"\s*$',grub.read_text()),'normal permanent default differs')
  text=custom.read_text();lines=text.splitlines();starts=[i for i,line in enumerate(lines) if re.match(r'^\s*menuentry\s',line) and re.search(r"['\"]"+re.escape(entry)+r"['\"]",line)];need(len(starts)==1,'one promoted entry required')
  start=starts[0];end=next(i for i in range(start+1,len(lines)) if lines[i]=='}');stanza=lines[start:end+1];linux=[shlex.split(s) for s in stanza if s.strip().startswith('linux ')];initrd=[shlex.split(s) for s in stanza if s.strip().startswith('initrd ')]
  need(len(linux)==1 and linux[0][1]=='/boot/vmlinuz-'+arm['release'] and [x for x in linux[0] if x.startswith('kd_mmap=')]==['kd_mmap=on'] and initrd==[['initrd','/boot/initrd.img-'+arm['release']]],'existing promoted image/mode differs')
  identity=json.loads(command('verify-installed',verify,900));need(identity['ok'] and identity['schema']==2,'installed source/build identity incomplete')
  command('arm-existing',['grub-reboot',entry]);after=environment('environment-after');need(after==dict(env,next_entry=entry),'more than one-shot selection changed')
  r.update(state='ARMED',environment_after=after,expected_cmdline=['BOOT_IMAGE='+linux[0][1]]+linux[0][2:],append_path=str(a.append),append_sha256=a.append_sha256)
 elif a.action=='request':
  previous('arm');need(prior['boot_id']==a.boot_id and env==prior['environment_after'],'same boot/selection required')
  r.update(state='REBOOT_INTENT',reboot_requested=True,expected_cmdline=prior['expected_cmdline'],arm_environment=prior['environment_before']);save();command('reboot',['systemctl','reboot'],30);r['state']='REBOOT_REQUESTED'
 else:
  need(prior and prior['action']=='request' and prior['config_sha256']==a.config_sha256 and prior['controller_sha256']==r['controller_sha256'] and prior['protected']==protected and prior.get('reboot_requested') and prior['boot_id']!=a.boot_id and any(x.get('name')=='reboot' and x.get('pid') for x in prior['commands']),'durable prior reboot request required')
  need(os.uname().release==arm['release'] and not env.get('next_entry') and Path('/proc/cmdline').read_text().split()==prior['expected_cmdline'],'actual promoted boot differs')
  need(all(env.get(k)==prior['arm_environment'].get(k) for k in ['saved_entry','prev_saved_entry']),'permanent boot selection changed')
  identity=json.loads(command('verify-running',verify+['--running'],900));need(identity['ok'] and identity['schema']==2 and identity['runtime_policy_verified'] and identity['running_build_id']=='0bdd45b1d7df96a0aaa1db9cd6f049ff08f75ebd','actual promoted runtime identity incomplete');r.update(state='BOOT_VERIFIED',verification=identity)
 need(all(sha(p)==h for p,h in protected.items()),'boot files/defaults changed');idle(root,rt.idle);r.update(passed=True,completed=True,final_idle=True)
except BaseException as e:r['error']=repr(e);raise
finally:r['finished']=time.time();save();print(json.dumps(r),flush=True)
