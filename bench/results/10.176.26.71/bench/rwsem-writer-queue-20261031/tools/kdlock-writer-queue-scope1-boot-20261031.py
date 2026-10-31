#!/usr/bin/env python3
"""One explicit existing-scope1 arm, reboot request or postboot identity action."""
import argparse,datetime,hashlib,importlib.util,json,os,re,runpy,shutil,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
SUPPORT=Path('/tmp/kdlock-writer-queue-install-boot-20261031.py')
SUPPORT_SHA='544ef3df8d43df22a0422e7f85d50d017a4b469535c6410361444c006774cdcf'
COMMIT='7814c61a0be20f5db3b9fb41b6079ef6d2938b5f'
PROVIDER='1b6f256b13e8743aa1fd7bdc958cc82ae7726463'
MANIFEST_SHA='a3f46b1e1006652d2c8c25e083eab93f76d2e2e970f896457a2ca94da4193411'
OLD_APPEND=Path('/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kernel-scope-append-r4-f7a84065-20261030/result.json')
OLD_APPEND_SHA='5d7f51277d78aef4d86c7c4f210e163700ea9876e8f78ad1b7c3a2458e95a93e'
BUNDLE=Path('/root/kdlock-kernel-baselines/linux70-kdscope1-kd-20261030')
BUNDLE_SHA='b9f13f4b7db03872c6c6d09e71144aa86013098968bcf817c35aa9bdb71e9fcb'
BUILD=Path('/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build')
BACKING=Path('/root/kdlock-build-output/linux-7.0.0-38-kdscope1')
BUILD_ID='a17d565ee157601e030d1b3c77c13e63fa62c994'
ENTRY='kdscope1-kd-20261030'
ROOT=Path('/root/host_fs/kdlock')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('arm','request','capture'))
    for name in ('config','append','prior','host-state'):
        p.add_argument('--'+name,type=Path,required=True);p.add_argument('--'+name+'-sha256',required=True)
    p.add_argument('--boot-id',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert hashlib.sha256(SUPPORT.read_bytes()).hexdigest()==SUPPORT_SHA
    spec=importlib.util.spec_from_file_location('scope1_boot_support',SUPPORT);b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
    need,sha,checked,record=b.require,b.sha,b.checked,b.record
    c=checked(a.config,a.config_sha256);recipe=Path(c['recipe']);data=Path(c['data_mount'])
    need(c['schema']==1 and os.geteuid()==0 and sys.executable==c['python'],'actual final config/root/interpreter required')
    need(c['commit']==COMMIT and c['provider_commit']==PROVIDER and c['release']=='7.0.0-38-kdscope3' and
         c['manifest_sha256']==MANIFEST_SHA and str(recipe)=='/mnt/kdlock-builds2/kdlock-scope3-recipe-7814c61a' and
         str(data)=='/mnt/kdlock-builds2' and c['snapshot']=='kdlock-builddisk-clean-20261031','current frozen cohort differs')
    boot=lambda:Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    need(boot()==a.boot_id and data.is_mount() and not ROOT.is_mount(),'current boot/DATA or unbound source differs')
    need(a.output.is_absolute() and a.output.resolve()==a.output and a.output.is_relative_to(data/'kdlock-evidence') and
         not a.output.exists(),'new persistent evidence directory required')
    manifest=checked(c['manifest'],MANIFEST_SHA);need(manifest['source_commit']==COMMIT,'recipe manifest commit differs')
    for name in ('bench/archive_run.py','bench/spin_cacheline/bench_runtime.py','bench/basic/capture_host.py','kernel_integration/linux70/verify.py'):
        need(sha(recipe/name)==manifest['files'][name]['sha256'],'maintained helper differs: '+name)
    sys.path.insert(0,str(recipe/'bench/spin_cacheline'));import bench_runtime as rt
    idle=runpy.run_path(str(recipe/'bench/archive_run.py'))['idle'];idle(recipe,rt.idle);idle(ROOT,rt.idle)
    host=checked(a.host_state,a.host_state_sha256)
    hs=importlib.util.spec_from_file_location('scope1_boot_host',recipe/'bench/basic/capture_host.py');hm=importlib.util.module_from_spec(hs);hs.loader.exec_module(hm);hm.validate(host)
    age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
    need(0<=age<240 and host['pins_verified'] and host['frequency_verified'] and host['snapshot_listed'] and host['recovery_snapshot']==c['snapshot'],'fresh actual host/recovery capture required')
    append=checked(a.append,a.append_sha256);old=checked(OLD_APPEND,OLD_APPEND_SHA);bundle=checked(BUNDLE/'manifest.json',BUNDLE_SHA);prior=checked(a.prior,a.prior_sha256)
    need(append.get('passed') is True and append.get('final_idle') is True and not append.get('drain_unknown') and
         append['action']=='append' and append['state']=='ENTRIES_APPENDED_NOT_ARMED' and append['controller_sha256']==SUPPORT_SHA and
         append['config_sha256']==a.config_sha256 and append['source_commit']==COMMIT and append['provider_commit']==PROVIDER,'current scope3 append required')
    need(old.get('passed') is True and old['state']=='ENTRIES_APPENDED_NOT_ARMED' and old['normal_default']==append['normal_default'],'original scope1 entry/default receipt differs')
    custom=Path('/boot/grub/custom.cfg');grub=Path('/boot/grub/grub.cfg');default=Path('/etc/default/grub')
    def stanza(text,entry):
        lines=text.splitlines(keepends=True);starts=[i for i,x in enumerate(lines) if re.match(r'^\s*menuentry\s',x) and re.search(r"['\"]"+re.escape(entry)+r"['\"]",x)]
        need(len(starts)==1,'one exact existing entry required');start=starts[0];indent=re.match(r'^\s*',lines[start]).group()
        end=next(i for i in range(start+1,len(lines)) if lines[i].rstrip('\n')==indent+'}')
        return ''.join(lines[start:end+1])
    def unchanged_boot():
        need(record(custom)==append['custom_after'] and stanza(custom.read_text(),ENTRY)==old['entries']['kd'],'current custom file or original scope1 entry differs')
        need(append['normal_default'] in re.findall(r'(?m)^\s*set default="([^"]+)"\s*$',grub.read_text()),'permanent normal default differs')
        need(len(bundle['installed_files'])==4 and all(x.startswith('boot/') for x in bundle['installed_files']),'original installed-file scope differs')
        for name,digest in bundle['installed_files'].items():need(sha(Path('/')/name)==digest,'old scope1 boot file differs: '+name)
    unchanged_boot();protected={str(x):record(x)for x in (custom,grub,default)}
    a.output.mkdir(parents=True)
    for src,name in [(Path(__file__),'controller.py'),(SUPPORT,'support.py'),(a.config,'config.json'),(a.append,'append.json'),(a.prior,'prior.json'),(a.host_state,'host-state.json'),(OLD_APPEND,'old-append.json'),(BUNDLE/'manifest.json','scope1-manifest.json')]:shutil.copyfile(src,a.output/name)
    r=dict(schema=1,action=a.action,passed=False,completed=False,state='STARTING',boot_id=a.boot_id,release=os.uname().release,
           controller_sha256=sha(__file__),support_sha256=SUPPORT_SHA,config_sha256=a.config_sha256,source_commit=COMMIT,provider_commit=PROVIDER,
           append=b.ref(a.append),prior=b.ref(a.prior),old_append_sha256=OLD_APPEND_SHA,bundle_manifest_sha256=BUNDLE_SHA,
           host_state_sha256=a.host_state_sha256,protected=protected,commands=[],started=time.time(),drain_unknown=False,
           performance_accepted=False,source_changed=False,default_changed=False,automatic_retry=False)
    def save():
        temp=a.output/'result.tmp'
        with temp.open('w') as f:f.write(json.dumps(r,indent=2)+'\n');f.flush();os.fsync(f.fileno())
        temp.replace(a.output/'result.json');fd=os.open(a.output,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    def command(name,argv,seconds=120):
        row=dict(name=name,argv=list(map(str,argv)),started=time.time());r['commands'].append(row);save()
        with (a.output/(name+'.log')).open('xb')as log:
            child=subprocess.Popen(row['argv'],cwd='/root',stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                                   env=dict(os.environ,LC_ALL='C',PYTHONDONTWRITEBYTECODE='1'))
            row.update(pid=child.pid,process_group=child.pid);r['drain_unknown']=True;save()
            try:code=child.wait(timeout=seconds)
            except subprocess.TimeoutExpired:row['timed_out']=True;save();raise
        row.update(returncode=code,remaining_processes=b.process_group(child.pid),finished=time.time(),log=b.ref(a.output/(name+'.log')));save()
        need(code==0 and not row['remaining_processes'],'command failed or not drained: '+name);r['drain_unknown']=False;save()
        return (a.output/(name+'.log')).read_text()
    def environment(name):
        result={}
        for line in command(name,['grub-editenv','/boot/grub/grubenv','list']).splitlines():
            key,sep,value=line.partition('=');need(sep and key and key not in result,'invalid GRUB environment');result[key]=value
        return result
    def own(action,successful=True):
        need(prior['controller_sha256']==r['controller_sha256'] and prior['action']==action and prior['config_sha256']==a.config_sha256 and
             prior['append']==r['append'] and prior['protected']==protected,'prior action generation or protected files differs')
        if successful:need(prior.get('passed') is True and prior.get('completed') is True and not prior.get('drain_unknown'),'prior action incomplete')
    save()
    try:
        env=environment('environment-before');r['environment_before']=env
        if a.action=='arm':
            need(prior.get('passed') is True and prior.get('final_idle') is True and not prior.get('drain_unknown') and
                 prior['controller_sha256']==SUPPORT_SHA and prior['action']=='capture' and prior['state']=='BOOT_RUNTIME_IDENTITY_VERIFIED' and
                 prior['config_sha256']==a.config_sha256 and prior['append']==r['append'] and prior['source_commit']==COMMIT and
                 prior['provider_commit']==PROVIDER and prior['boot_id']==a.boot_id and prior['mode']=='native' and
                 prior['release']==os.uname().release==c['release'],'actual current scope3 Native capture required')
            need(prior['verification']['ok'] is True and prior['verification']['schema']==2 and prior['verification']['runtime_policy_verified'] is True,'Native schema-2 identity incomplete')
            need([x for x in Path('/proc/cmdline').read_text().split()if x.startswith('kd_mmap=')]==['kd_mmap=off'] and not env.get('next_entry'),'current Native mode or queued entry differs')
            command('arm-existing',['grub-reboot',ENTRY]);after=environment('environment-after');need(after=={**env,'next_entry':ENTRY},'more than next_entry changed')
            r.update(state='SCOPE1_ARMED',entry=ENTRY,arm_environment_before=env,environment_after=after)
        elif a.action=='request':
            own('arm');need(prior['state']=='SCOPE1_ARMED' and prior['boot_id']==a.boot_id and env==prior['environment_after'] and env.get('next_entry')==ENTRY,'same-boot armed environment required')
            r.update(state='REBOOT_INTENT_RECORDED',reboot_requested=True,pre_request_idle=True,arm_environment_before=prior['arm_environment_before']);save()
            command('reboot',['systemctl','reboot'],30);r.update(state='REBOOT_REQUESTED_NOT_VERIFIED',passed=True,completed=True);save();return
        else:
            own('request',False)
            need(prior.get('reboot_requested') is True and prior['boot_id']!=a.boot_id and any(x.get('name')=='reboot'and x.get('pid') for x in prior['commands']),'distinct boot after durable reboot child required')
            need(os.uname().release=='7.0.0-38-kdscope1' and Path('/proc/cmdline').read_text().split()==old['expected_cmdlines']['kd'] and not env.get('next_entry'),'exact scope1 KD boot/consumed selection required')
            need(all(env.get(k)==prior['arm_environment_before'].get(k)for k in ('saved_entry','prev_saved_entry')),'saved/default GRUB state changed')
            need(BUILD.resolve()==BUILD and BACKING.resolve()==BACKING and BUILD.is_dir()and BACKING.is_dir(),'canonical scope1 build paths required')
            for name,digest in bundle['build_files'].items():need(sha(BACKING/name)==digest,'original build backing differs: '+name)
            if not BUILD.is_mount():
                need(not any(BUILD.iterdir()),'unmounted build destination must be empty');command('restore-build-bind',['mount','--bind',BACKING,BUILD])
            need(BUILD.is_mount()and os.path.samefile(BUILD,BACKING),'different output mount')
            if not Path('/sys/kernel/debug/sched/preempt').is_file():
                need(not Path('/sys/kernel/debug').is_mount(),'existing debugfs lacks preemption state');command('debugfs',['mount','-t','debugfs','debugfs','/sys/kernel/debug'])
            verified=json.loads(command('verify-scope1',[c['python'],recipe/'kernel_integration/linux70/verify.py','--variant','kdscope1-kd','--bundle',BUNDLE,'--build-root',BUILD,'--running'],900))
            need(verified.get('ok') is True and verified.get('schema')==2 and verified.get('runtime_policy_verified') is True and
                 verified.get('running_build_id')==BUILD_ID,'fresh running scope1 identity differs')
            r.update(state='BOOT_RUNTIME_IDENTITY_VERIFIED',mode='kd',verification=verified,kernel_identity=verified,running_kernel_validated=True,
                     bundle=str(BUNDLE),build=str(BUILD),backing=str(BACKING),previous_boot_id=prior['boot_id'])
        unchanged_boot();need({str(x):record(x)for x in (custom,grub,default)}==protected,'protected boot files changed')
        idle(recipe,rt.idle);idle(ROOT,rt.idle);need(boot()==a.boot_id and not ROOT.is_mount(),'boot or unbound canonical view changed')
        need(sha(a.config)==a.config_sha256 and sha(a.append)==a.append_sha256 and sha(a.prior)==a.prior_sha256 and sha(BUNDLE/'manifest.json')==BUNDLE_SHA,'action input changed')
        r.update(passed=True,completed=True,final_idle=True,drain_unknown=False)
    except BaseException as error:r.update(state='FAILED',error=repr(error));raise
    finally:r['finished']=time.time();save()
    print(json.dumps(dict(passed=r['passed'],completed=r['completed'],state=r['state'],output=str(a.output))),flush=True)

if __name__=='__main__':main()
