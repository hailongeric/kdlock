#!/usr/bin/env python3
"""Resume the unrun serial pair after the approved admission-only retirement."""
import datetime
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
PRIOR_REPORT = ROOT/'bench/results/10.176.26.71/tests/serial-continuation-20261022'
C = runpy.run_path(str(PRIOR_REPORT/'campaign.py'))
RAW = ROOT/'bench/results/10.176.26.71/raw/bench/mmap-contention-followup-20261022/pair-2'
BASE = '/root/kdlock-evidence/10.176.26.71/bench/mmap-contention-followup-20261022'
PRIOR = '/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021'
WAIT = runpy.run_path(str(ROOT/'bench/mmap_lock/admission_wait.py'))


def source_guard(output, expected_commit):
    assert not (ROOT/'.git/index.lock').exists()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==expected_commit
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    writers=[];denied=0
    for process in Path('/proc').glob('[0-9]*'):
        try:
            for fd in (process/'fd').iterdir():
                try:
                    target=os.readlink(fd)
                    if not target.startswith(str(ROOT)+'/') or target.startswith(str(RAW.parent)+'/'):
                        continue
                    flags=int(next(s.split()[1] for s in (process/'fdinfo'/fd.name).read_text().splitlines()
                                   if s.startswith('flags:')),8)
                    if flags&os.O_ACCMODE!=os.O_RDONLY:
                        writers.append(dict(pid=int(process.name),fd=fd.name,target=target))
                except (FileNotFoundError,ProcessLookupError):pass
        except PermissionError:denied+=1
        except (FileNotFoundError,ProcessLookupError):pass
    C['save'](output,dict(captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        commit=expected_commit,writable_checkout_descriptors=writers,inaccessible_processes=denied,
        scope='OS descriptors; only this coordinator evidence directory may be open for writing'))
    assert not writers, 'competing source/evidence writer requires review'


def guest_guard(output, boot, mode):
    script="""import json,os,runpy,sys
from pathlib import Path
root=Path('/root/host_fs/kdlock');sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
expected=json.loads(Path('/root/kdlock-evidence/10.176.26.71/bench/mmap-contention-followup-20261022/preflight/guest-ownership.json').read_text())['modules']
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();modules=sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())
assert boot==EXPECTED_BOOT and modules==expected
assert os.uname().release==('6.1.159-kdclobber2' if MODE=='recovery' else '6.1.159-kdmm1')
assert [s for s in Path('/proc/cmdline').read_text().split() if s.startswith('kd_mmap=')]==([] if MODE=='recovery' else ['kd_mmap='+('off' if MODE=='native' else 'on')])
for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
 try:assert path.read_text().strip() not in ('perf','mw_time_worker','mf_time_worker')
 except (FileNotFoundError,ProcessLookupError):pass
print(json.dumps(dict(idle=True,boot_id=boot,mode=MODE,modules=modules)))
""".replace('EXPECTED_BOOT',repr(boot)).replace('MODE',repr(mode))
    C['guest'](C['PY']+" - <<'PY'\n"+script+"\nPY",output,120)


def main():
    RAW.mkdir()
    state = dict(passed=False, accepted=False, planned=['native','kd'], completed=[],
                 unrun=['native','kd'], driver_sha256=C['sha'](Path(__file__)),
                 diagnostic=True, seven_mutex_causes='UNRESOLVED',profile_commands_attempted=[],
                 settling_seconds=60, resumed_run='pair-2')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    state.update(source_commit=commit,wait_helper_sha256=C['sha'](ROOT/'bench/mmap_lock/admission_wait.py'))
    original_path = ROOT/'bench/results/10.176.26.71/raw/tests/serial-continuation-20261022/campaign-1/original-host.json'
    assert C['sha'](original_path) == '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
    original = C['load'](original_path)
    try:
        assert C['sha'](RAW.parent/'control-stop-1.json')=='e66d9493141afff777563b65ce2e84abd9711128858b302be80c686c7a781dd1'
        stop=C['load'](RAW.parent/'control-stop-1.json')
        assert stop['coordinator_pid']==792734 and stop['coordinator_exited'] and stop['command_chain_drained']
        assert stop['guest_idle'] and stop['profile_commands_attempted']==[]
        assert stop['pair_result_sha256']==C['sha'](RAW.parent/'pair-1/result.json')
        state['stop_receipt']=dict(path=str(RAW.parent/'control-stop-1.json'),sha256=C['sha'](RAW.parent/'control-stop-1.json'))
        assert not Path('/proc/792734').exists(), 'original coordinator must have exited'
        prior=C['load'](RAW.parent/'pair-1/result.json')
        assert not prior['completed'] and not prior['profile_commands_attempted']
        assert prior['admission']['mode']=='native'
        state['resumed_from']=dict(path=str(RAW.parent/'pair-1/result.json'),sha256=C['sha'](RAW.parent/'pair-1/result.json'))
        current_boot=C['load'](RAW.parent/'pair-1/native/transition.json')['boot_id'];current_mode='native'
        for mode in ('native','kd'):
            block=BASE+'/'+mode+'-2';local=RAW/mode;local.mkdir()
            source_guard(local/'source-before-transition.json',commit)
            guest_guard(local/'guest-before-transition.json',current_boot,current_mode)
            C['guest']('mkdir -- '+shlex.quote(block),local/'mkdir.log',30)
            if mode=='native':
                print('REUSE existing Native boot',current_boot,flush=True)
                C['guest']('cp -a -- '+shlex.quote(BASE+'/native-1/transition')+' '+shlex.quote(BASE+'/native-1/request')+' '+shlex.quote(BASE+'/native-1/host-transition.json')+' '+shlex.quote(block+'/'),local/'retain-transition.log',60)
                transition=C['fetch'](block+'/transition/result.json',local/'transition.json')
                assert C['sha'](local/'transition.json')==C['sha'](RAW.parent/'pair-1/native/transition.json')
                C['fetch'](block+'/request/result.json',local/'request.json')
                assert C['sha'](local/'request.json')==transition['request_sha256']
                C['fetch'](block+'/host-transition.json',local/'host-transition.json')
                assert C['sha'](local/'host-transition.json')==C['load'](local/'request.json')['host_state_sha256']
                assert transition['passed'] and transition['mode']=='native' and transition['boot_id']==current_boot
                assert stop['boot_id']==current_boot
                state['native_boot_reused']=True
            else:
                print('BOOT',mode,flush=True)
                transition=C['boot'](mode,block,local)
            current_boot=transition['boot_id'];current_mode=mode;observations=[]
            def observe(attempt):
                source_guard(local/f'source-before-observation-{attempt}.json',commit)
                guest_guard(local/f'guest-before-observation-{attempt}.json',current_boot,mode)
                # Settle after the guest read, then use the actual complete capture.
                # The unchanged guest driver still checks full admission before load.
                settling_started=time.monotonic_ns()
                time.sleep(state['settling_seconds'])
                C['save'](local/f'settling-{attempt}.json',dict(
                    guest_guard_sha256=C['sha'](local/f'guest-before-observation-{attempt}.json'),
                    elapsed_ns=time.monotonic_ns()-settling_started,
                    requested_seconds=state['settling_seconds'],mode=mode,boot_id=current_boot))
                source_guard(local/f'source-after-settle-{attempt}.json',commit)
                path=local/f'host-observation-{attempt}.json';host=C['capture'](path)
                return path,host,C['sha'](path)
            def record(row):
                observations.append(dict(row,mode=mode,boot_id=current_boot))
                C['save'](local/'observations.json',observations)
                state['admission']=dict(mode=mode,boot_id=current_boot,**row)
                C['save'](RAW/'result.json',state)
                print('ADMISSION',mode,row['attempt'],row['state'],row['threads'],flush=True)
            host_path=WAIT['wait'](original,observe,C['host_screen'],record)
            C['copy_in']([host_path],block+'/host-admission.json',local/'copy-host.log')
            session=block+'/profile';driver=BASE+'/control-1/contention_profile.py'
            args=[driver,'run','--output',session,'--host-state',block+'/host-admission.json',
                '--boot-id',transition['boot_id'],'--mode',mode,'--transition',block+'/transition/result.json',
                '--inputs',PRIOR+'/prepare-1/inputs.json','--validated',PRIOR+'/native-validation-1/result.json',
                PRIOR+'/kd-validation-1/result.json']
            print('PROFILE',mode,flush=True)
            state['profile_commands_attempted'].append(dict(mode=mode,boot_id=current_boot,session=session))
            C['save'](RAW/'result.json',state)
            C['command']([sys.executable,str(PRIOR_REPORT/'run_remote.py'),
                '--remote-command',C['remote'](args),'--receipt',session+'/client-result.json',
                '--output',str(local/'endpoint-control'),'--admission',str(host_path)],local/'launch.log',900)
            C['copy_in']([local/'endpoint-control/host-endpoint.json',local/'endpoint-control/controller.json'],
                         session+'/',local/'copy-endpoint.log')
            C['guest'](C['remote']([driver,'finish','--output',session]),local/'finish.log',300)
            result=C['fetch'](session+'/result.json',local/'result.json')
            assert result['passed'] and result['drained'] and result['final_idle'] and not result['accepted']
            state['completed'].append(dict(mode=mode,boot_id=transition['boot_id'],
                result_sha256=C['sha'](local/'result.json'),host_endpoint=result['host_endpoint']))
            state['unrun'].remove(mode);C['save'](RAW/'result.json',state)
            print('DRAINED',mode,result['host_endpoint'],flush=True)
            state.setdefault('archives',[]).append(C['seal'](block,local,transition['boot_id'],True))
        block=BASE+'/recovery-2';local=RAW/'recovery';local.mkdir()
        source_guard(local/'source-before-transition.json',commit)
        guest_guard(local/'guest-before-transition.json',current_boot,current_mode)
        C['guest']('mkdir -- '+shlex.quote(block),local/'mkdir.log',30)
        print('RESTORE recovery',flush=True)
        transition=C['boot']('recovery',block,local)
        state.update(recovery=transition,recovery_archive=C['seal'](block,local,transition['boot_id'],False),
                     passed=not state['unrun'],final_idle=True)
    except BaseException as error:
        # Do not reboot or unload automatically after an uncertain child return.
        state.update(error=repr(error),drain_requires_review=True)
        raise
    finally:
        C['save'](RAW/'result.json',state)
    print(json.dumps(dict(completed=state['completed'],unrun=state['unrun'],final_idle=True)),flush=True)


if __name__=='__main__':
    main()
