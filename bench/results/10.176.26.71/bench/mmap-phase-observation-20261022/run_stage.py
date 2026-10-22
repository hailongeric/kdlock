#!/usr/bin/env python3
"""One writer, serial controls and one diagnostic on the original VM."""
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[5]
PRIOR_REPORT=ROOT/'bench/results/10.176.26.71/tests/serial-continuation-20261022'
C=runpy.run_path(str(PRIOR_REPORT/'campaign.py'))
R=runpy.run_path(str(ROOT/'bench/results/10.176.26.71/bench/mmap-contention-followup-20261022/run_pair_resume.py'))
WAIT=runpy.run_path(str(ROOT/'bench/mmap_lock/admission_wait.py'))
RAW=ROOT/'bench/results/10.176.26.71/raw/bench/mmap-phase-observation-20261022/stage-1'
BASE='/root/kdlock-evidence/10.176.26.71/bench/mmap-phase-observation-20261022'
PRIOR='/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021'
# Reuse the same source check, allowing only this stage's raw evidence writes.
R['source_guard'].__globals__['RAW']=RAW


def main():
    RAW.mkdir()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    state=dict(passed=False,accepted=False,source_commit=commit,settling_seconds=60,
        diagnostic_attempts=[],seven_mutex_causes='UNRESOLVED',driver_sha256=C['sha'](Path(__file__)))
    original_path=ROOT/'bench/results/10.176.26.71/raw/tests/serial-continuation-20261022/campaign-1/original-host.json'
    assert C['sha'](original_path)=='478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
    original=C['load'](original_path)
    block=BASE+'/kd-1';local=RAW/'kd';local.mkdir()
    boot='9545bcf9-e8ae-4515-be1b-0a5309afc18f';mode='recovery'
    def settled_guard(path):
        R['guest_guard'](path,boot,mode)
        start=time.monotonic_ns();time.sleep(60)
        C['save'](path.with_suffix('.settle.json'),dict(requested_seconds=60,
            elapsed_ns=time.monotonic_ns()-start,guest_guard_sha256=C['sha'](path)))
    try:
        R['source_guard'](local/'source-initial.json',commit)
        settled_guard(local/'guest-initial.json')
        C['guest']('mkdir -p -- '+shlex.quote(block),local/'mkdir.log',30)
        driver=block+'/phase_observation.py'
        C['copy_in']([ROOT/'bench/mmap_lock/phase_observation.py'],driver,local/'copy-driver.log')
        C['guest'](C['remote']([driver,'prepare','--output',block+'/prepare-1']),local/'prepare.log',600)
        prepared=C['fetch'](block+'/prepare-1/result.json',local/'prepared.json')
        assert prepared['passed']
        R['source_guard'](local/'source-before-transition.json',commit)
        settled_guard(local/'guest-before-transition.json')
        transition=C['boot']('kd',block,local);boot=transition['boot_id'];mode='kd'
        def admission(label):
            folder=local/label;folder.mkdir();observations=[]
            def observe(attempt):
                R['source_guard'](folder/f'source-{attempt}.json',commit)
                R['guest_guard'](folder/f'guest-{attempt}.json',boot,mode)
                start=time.monotonic_ns();time.sleep(60)
                C['save'](folder/f'settle-{attempt}.json',dict(requested_seconds=60,
                    elapsed_ns=time.monotonic_ns()-start,guest_guard_sha256=C['sha'](folder/f'guest-{attempt}.json')))
                R['source_guard'](folder/f'source-after-settle-{attempt}.json',commit)
                path=folder/f'host-{attempt}.json';host=C['capture'](path)
                return path,host,C['sha'](path)
            def record(row):
                observations.append(row);C['save'](folder/'observations.json',observations)
                state['admission']=dict(label=label,**row);C['save'](RAW/'result.json',state)
                print('ADMISSION',label,row['attempt'],row['state'],row['threads'],flush=True)
            path=WAIT['wait'](original,observe,C['host_screen'],record)
            target=block+'/'+label+'-host.json';C['copy_in']([path],target,folder/'copy-host.log')
            return path,target
        _,host=admission('controls')
        checked=block+'/controls-1/result.json'
        print('FOCUSED CONTROLS',flush=True)
        C['guest'](C['remote']([driver,'check','--output',block+'/controls-1','--prepared',block+'/prepare-1/result.json',
            '--host-state',host,'--boot-id',boot,'--transition',block+'/transition/result.json']),local/'controls.log',300)
        controls=C['fetch'](checked,local/'controls.json');assert controls['passed'] and controls['drained']
        state['controls']=dict(path=checked,sha256=C['sha'](local/'controls.json'));C['save'](RAW/'result.json',state)
        host_path,host=admission('diagnostic')
        session=block+'/diagnostic-1'
        args=[driver,'run','--output',session,'--prepared',block+'/prepare-1/result.json','--checked',checked,
            '--host-state',host,'--boot-id',boot,'--transition',block+'/transition/result.json',
            '--inputs',PRIOR+'/prepare-1/inputs.json','--validated',PRIOR+'/native-validation-1/result.json',
            PRIOR+'/kd-validation-1/result.json']
        state['diagnostic_attempts'].append(dict(boot_id=boot,session=session));C['save'](RAW/'result.json',state)
        print('SINGLE METADATA DIAGNOSTIC',flush=True)
        C['command']([sys.executable,str(PRIOR_REPORT/'run_remote.py'),'--remote-command',C['remote'](args),
            '--receipt',session+'/client-result.json','--output',str(local/'endpoint-control'),
            '--admission',str(host_path)],local/'launch.log',900)
        C['copy_in']([local/'endpoint-control/host-endpoint.json',local/'endpoint-control/controller.json'],
            session+'/',local/'copy-endpoint.log')
        C['guest'](C['remote']([driver,'finish','--output',session]),local/'finish.log',300)
        result=C['fetch'](session+'/result.json',local/'result.json')
        assert result['drained'] and result['final_idle'] and not result['accepted']
        state['diagnostic']=dict(path=session+'/result.json',sha256=C['sha'](local/'result.json'),
            usable=result['observation_usable'],host_endpoint=result['host_endpoint'])
        state['candidate_archive']=C['seal'](block,local,boot,True)
        recovery=BASE+'/recovery-1';folder=RAW/'recovery';folder.mkdir()
        R['source_guard'](folder/'source-before-transition.json',commit)
        settled_guard(folder/'guest-before-transition.json')
        C['guest']('mkdir -- '+shlex.quote(recovery),folder/'mkdir.log',30)
        print('RESTORE recovery',flush=True)
        restored=C['boot']('recovery',recovery,folder)
        state.update(recovery=restored,recovery_archive=C['seal'](recovery,folder,restored['boot_id'],False),
            passed=result['observation_usable'],final_idle=True)
    except BaseException as error:
        state.update(error=repr(error),drain_requires_review=True);raise
    finally:C['save'](RAW/'result.json',state)
    print(json.dumps(state),flush=True)


if __name__=='__main__':main()
