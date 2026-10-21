#!/usr/bin/env python3
"""Source-side serial coordinator; all live work stays in the original VM."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[5]
REPORT=Path(__file__).resolve().parent
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/serial-continuation-20261022'
BASE='/root/kdlock-evidence/10.176.26.71/tests/serial-continuation-20261022'
PRIOR='/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021'
SOURCE='/root/host_fs/kdlock'
PY='env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z /root/kdlock-translation-venv-20261019/bin/python3'
CAPTURE=ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py'
ORDER=[(0,'native'),(0,'kd'),(1,'kd'),(1,'native'),(2,'native'),(2,'kd')]
CASES=[('mmap',1),('mmap',16),('fault',1),('fault',16)]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text())
def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def remote(args):return PY+' '+' '.join(shlex.quote(str(a)) for a in args)


def command(args, log, timeout=900, stdin=None, allow_failure=False):
    log.parent.mkdir(parents=True,exist_ok=True)
    receipt=log.with_suffix(log.suffix+'.command.json')
    record=dict(argv=args,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                timeout_seconds=timeout,state='STARTING',stdin_sha256=(hashlib.sha256(stdin).hexdigest()
                if stdin is not None else None))
    save(receipt,record)
    with log.open('wb') as output, log.with_suffix(log.suffix+'.stderr').open('wb') as errors:
        child=subprocess.Popen(args,stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                               stdout=output,stderr=errors)
        record.update(pid=child.pid,state='RUNNING');save(receipt,record)
        # Timeout never sends a signal; leave the command intact and stop the
        # campaign until its actual drain is established by the lead agent.
        try:child.communicate(stdin,timeout=timeout)
        except BaseException as error:
            record.update(state='UNKNOWN_DRAIN',error=repr(error),
                          observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            save(receipt,record);raise
    record.update(state='EXITED',returncode=child.returncode,
                  finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(receipt,record)
    if child.returncode and not allow_failure:raise RuntimeError(f'command exited {child.returncode}: {log}')
    return child.returncode


def guest(text, log, timeout=900, allow_failure=False):
    return command(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','2222',
             'root@10.176.26.71',text],log,timeout,allow_failure=allow_failure)


def copy_in(paths,destination,log):
    command(['scp','-o','BatchMode=yes','-o','ConnectTimeout=10','-P','2222',
             *map(str,paths),'root@10.176.26.71:'+destination],log,120)


def fetch(path,target):
    guest('cat -- '+shlex.quote(path),target,60)
    return load(target)


def capture(path):
    command(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71',
             'sudo -n python3 -'],path,30,CAPTURE.read_bytes())
    return load(path)


def host_screen(original, host):
    # This is only a host screen. The unchanged full guest/environment gate
    # runs inside serial.ready and serial.run before any payload is loaded.
    for key in ('cpufreq','numa','recovery_snapshot'):
        if original[key]!=host[key]:return 'host control differs: '+key
    if not host['pins_verified'] or not host['snapshot_listed'] or len(host['qemu'])!=1:
        return 'snapshot or placement unverified'
    before=original['qemu'][0];after=host['qemu'][0]
    for key in ('pid','args'):
        if before[key]!=after[key]:return 'QEMU '+key+' differs'
    tasks=lambda q:sorted(q['tasks'],key=lambda t:t['tid'])
    if len(tasks(after))!=67 or tasks(before)!=tasks(after):return 'strict original QEMU task set differs'
    return None


def eligible(original, label, output):
    observations=[]
    for attempt in range(1,11):
        path=output/f'{label}-host-{attempt}.json';host=capture(path)
        reason=host_screen(original,host)
        observations.append(dict(path=str(path),sha256=sha(path),reason=reason,
                                  threads=len(host['qemu'][0]['tasks'])))
        save(output/(label+'-observations.json'),observations)
        if reason is None:return path
        print(f'WAIT {label} observation {attempt}: {observations[-1]["threads"]} threads; {reason}',flush=True)
        command(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71',
                 'sudo -n python3 -'],output/f'{label}-lifetimes-{attempt}.json',30,
                 (REPORT/'observe-host.py').read_bytes())
        if attempt<10:time.sleep(60)
    raise RuntimeError('PERSISTENT_ADMISSION_REFUSAL: '+label+'; ten observations at least 60 seconds apart')


def boot(mode, block, output):
    guest('cat /proc/sys/kernel/random/boot_id',output/'boot-before.log',20)
    old_boot=(output/'boot-before.log').read_text().strip()
    host_path=output/'host-transition.json';capture(host_path)
    copy_in([host_path],block+'/host-transition.json',output/'copy-transition.log')
    transition=PRIOR+'/transition.py'
    guest(remote([transition,'request','--mode',mode,'--output',block+'/request',
                  '--host-state',block+'/host-transition.json']),output/'request.log',120,allow_failure=True)
    time.sleep(10)
    # A disconnect can follow a successfully armed reboot. Never resend the
    # request: require a changed boot before consuming the verification path.
    for attempt in range(12):
        path=output/f'boot-reachable-{attempt}.log'
        code=guest('cat /proc/sys/kernel/random/boot_id',path,20,allow_failure=True)
        observed=path.read_text().strip()
        if code==0 and observed and observed!=old_boot:break
        if attempt==11:raise RuntimeError('requested boot change unconfirmed; never resend automatically')
        time.sleep(5)
    request=fetch(block+'/request/result.json',output/'request.json')
    assert request['passed'] and request['reboot_requested'] and request['mode']==mode
    assert request['boot_id']==old_boot
    guest(remote([transition,'verify','--mode',mode,'--output',block+'/transition',
                  '--request',block+'/request/result.json']),output/'transition.log',120)
    return fetch(block+'/transition/result.json',output/'transition.json')


def seal(block, output, boot_id, candidate):
    script="""import json,runpy,sys
from pathlib import Path
sys.path.insert(0,'/root/host_fs/kdlock/bench/spin_cacheline')
import bench_runtime as rt
root=Path('/root/host_fs/kdlock');base=Path(BLOCK)
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
modules=sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())
expected=json.loads(Path('/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021/final-health.json').read_text())['modules']
assert modules==expected
messages=rt.command(['dmesg'],base/'final-dmesg.log');assert not rt.FAULT.search(messages)
rt.write_json(base/'final-health.json',dict(idle=True,boot_id=BOOT,modules=modules,new_faults_in_retained_dmesg=[]))
""".replace('BLOCK',repr(block)).replace('BOOT',repr(boot_id))
    guest(PY+" - <<'PY'\n"+script+"\nPY",output/'health.log',120)
    args=([SOURCE+'/kernel_integration/mmap_lock/archive.py','--kernel-source',
        '/root/kdlock-kernel-work/mmap-20261021/candidate-1/linux','--kernel-baseline',
        '/root/kdlock-kernel-baselines/mmap-kdmm1-20261021'] if candidate else [SOURCE+'/bench/archive_run.py'])
    args+=['--base',block,'--output',block+'-archives','--health',block+'/final-health.json',
           '--group','transition=transition','--timeout-seconds','900']
    guest(remote(args),output/'archive.log',1000)
    destination=output/'archives';destination.mkdir()
    command(['scp','-o','BatchMode=yes','-o','ConnectTimeout=10','-P','2222',
             'root@10.176.26.71:'+block+'-archives/*',str(destination)+'/'],output/'copy-archives.log',120)
    manifest=load(destination/'archives.json')
    assert manifest['completed'] and manifest['guest_idle']
    assert manifest['boot_id']==boot_id and manifest['guest_base']==block
    assert sha(destination/'input-inventory.json')==manifest['input_inventory_sha256']
    for group in manifest['groups']:
        file=destination/group['file'];assert file.stat().st_size==group['bytes'] and sha(file)==group['sha256']
    return dict(manifest_sha256=sha(destination/'archives.json'),groups=len(manifest['groups']))


def main():
    output=RAW/'campaign-1';output.mkdir()
    original=fetch('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix/host-state.json',output/'original-host.json')
    assert sha(output/'original-host.json')=='478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
    assert sha(CAPTURE)=='b0ad0d1854a0f0d60487fa9afea4d044aacf7b9fa86ec3c700d66a150cd4be1b'
    controller=BASE+'/candidate-control-1/serial.py'
    state=dict(passed=False,accepted=False,planned=24,completed=[],unrun=[dict(block=i,mode=mode,repeat=repeat,
        case=j,task=task,threads=n) for i,(repeat,mode) in enumerate(ORDER) for j,(task,n) in enumerate(CASES)],
        p95_status='DEFERRED',seven_mutex_causes='UNRESOLVED',driver_sha256=sha(Path(__file__)))
    save(output/'result.json',state)
    try:
        previous=None
        for index,(repeat,mode) in enumerate(ORDER):
            block=BASE+f'/mm-block-{index}-{mode}';local=output/f'block-{index}-{mode}';local.mkdir()
            print(f'BOOT {index} {mode} repeat {repeat}',flush=True)
            guest('mkdir -- '+shlex.quote(block),local/'mkdir.log',30)
            transition=boot(mode,block,local);boot_id=transition['boot_id']
            host=eligible(original,'ready',local)
            copy_in([host],block+'/host-ready.json',local/'copy-ready-host.log')
            args=[controller,'ready','--output',block+'/ready','--host-state',block+'/host-ready.json',
                '--boot-id',boot_id,'--mode',mode,'--transition',block+'/transition/result.json',
                '--inputs',PRIOR+'/prepare-1/inputs.json','--validated',PRIOR+'/native-validation-1/result.json',
                PRIOR+'/kd-validation-1/result.json','--block',index,'--repeat',repeat]
            if previous:args+=['--previous',previous]
            guest(remote(args),local/'ready.log',180)
            fetch(block+'/ready/result.json',local/'ready.json')
            for case,(task,n) in enumerate(CASES):
                name=f'case-{case}-{task}-{n}';session=block+'/'+name;rowdir=local/name;rowdir.mkdir()
                host=eligible(original,name,rowdir)
                copy_in([host],block+'/'+name+'-host.json',rowdir/'copy-host.log')
                args=[controller,'run','--output',session,'--host-state',block+'/'+name+'-host.json',
                    '--boot-id',boot_id,'--mode',mode,'--ready',block+'/ready/result.json',
                    '--case',case,'--task',task,'--threads',n,'--repeat',repeat]
                print(f'RUN {index} {name}',flush=True)
                command([sys.executable,str(REPORT/'run_remote.py'),'--remote-command',remote(args),
                    '--receipt',session+'/client-result.json','--output',str(rowdir/'control'),
                    '--admission',str(host)],rowdir/'launch.log',1000)
                copy_in([rowdir/'control/host-endpoint.json',rowdir/'control/controller.json'],session+'/',rowdir/'copy-endpoint.log')
                guest(remote([controller,'finish','--output',session]),rowdir/'finish.log',180)
                result=fetch(session+'/result.json',rowdir/'result.json')
                assert result['passed'] and result['drained'] and result['final_idle']
                state['completed'].append(dict(block=index,case=case,task=task,threads=n,mode=mode,repeat=repeat,
                    state=result['state'],receipt=str(rowdir/'result.json'),sha256=sha(rowdir/'result.json')))
                state['unrun']=state['unrun'][1:];save(output/'result.json',state)
                print(f'DONE {index} {name} {result["state"]}',flush=True)
            previous=block+'/block-result.json';fetch(previous,local/'block-result.json')
            state.setdefault('archives',[]).append(seal(block,local,boot_id,True));save(output/'result.json',state)
        recovery=BASE+'/campaign-recovery';local=output/'recovery';local.mkdir()
        guest('mkdir -- '+shlex.quote(recovery),local/'mkdir.log',30)
        transition=boot('recovery',recovery,local)
        state['recovery']=transition;state['recovery_archive']=seal(recovery,local,transition['boot_id'],False)
        state.update(passed=True,completed_sessions=24,final_idle=True)
    except BaseException as error:
        state.update(error=repr(error),stopped_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        raise
    finally:save(output/'result.json',state)
    print('COMPLETE 24 serial sessions; endpoint classifications remain separate; recovery restored',flush=True)


if __name__=='__main__':main()
