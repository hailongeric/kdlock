#!/usr/bin/env python3
"""Serial correctness controls; preserve the observer and return to recovery."""
import datetime
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import time

ROOT=Path(__file__).resolve().parents[5]
C=runpy.run_path(str(ROOT/'bench/results/10.176.26.71/tests/serial-continuation-20261022/campaign.py'))
R=runpy.run_path(str(ROOT/'bench/results/10.176.26.71/bench/mmap-contention-followup-20261022/run_pair_resume.py'))
WAIT=runpy.run_path(str(ROOT/'bench/mmap_lock/admission_wait.py'))
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mmap-phase-controls-20261022/stage-1'
BASE='/root/kdlock-evidence/10.176.26.71/tests/mmap-phase-controls-20261022'
R['source_guard'].__globals__['RAW']=RAW


def main():
    RAW.mkdir()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    own_stat=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    state=dict(passed=False,accepted=False,source_commit=commit,settling_seconds=60,
        timing_started=False,seven_mutex_causes='UNRESOLVED',driver_sha256=C['sha'](Path(__file__)),
        coordinator=dict(pid=os.getpid(),start_ticks=int(own_stat[19]),
            started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    original_path=ROOT/'bench/results/10.176.26.71/raw/tests/serial-continuation-20261022/campaign-1/original-host.json'
    assert C['sha'](original_path)=='478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
    original=C['load'](original_path)
    block=BASE+'/kd-1';local=RAW/'kd';local.mkdir()
    boot='4b9775c4-ac74-4db8-85c7-491f6b81f212';mode='recovery'
    def settled_guard(path):
        R['guest_guard'](path,boot,mode)
        start=time.monotonic_ns();time.sleep(60)
        C['save'](path.with_suffix('.settle.json'),dict(requested_seconds=60,
            elapsed_ns=time.monotonic_ns()-start,guest_guard_sha256=C['sha'](path)))
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
        host_path=WAIT['wait'](original,observe,C['host_screen'],record)
        host=block+'/'+label+'-host.json';C['copy_in']([host_path],host,folder/'copy-host.log')
        return host
    try:
        R['source_guard'](local/'source-initial.json',commit)
        settled_guard(local/'guest-initial.json')
        C['guest']('mkdir -p -- '+shlex.quote(block),local/'mkdir.log',30)
        admission('initial')
        driver=block+'/phase_controls.py'
        C['copy_in']([ROOT/'bench/mmap_lock/phase_controls.py'],driver,local/'copy-driver.log')
        print('PREPARE basic, receipt checks and control module',flush=True)
        C['guest'](C['remote']([driver,'prepare','--output',block+'/prepare-1']),local/'prepare.log',600)
        prepared=C['fetch'](block+'/prepare-1/result.json',local/'prepared.json')
        assert prepared['passed']
        R['source_guard'](local/'source-before-transition.json',commit)
        settled_guard(local/'guest-before-transition.json')
        transition=C['boot']('kd',block,local);boot=transition['boot_id'];mode='kd'
        host=admission('controls')
        print('FOCUSED CONTROLS',flush=True)
        C['guest'](C['remote']([driver,'check','--output',block+'/controls-1',
            '--prepared',block+'/prepare-1/result.json','--host-state',host,'--boot-id',boot,
            '--transition',block+'/transition/result.json']),local/'controls.log',300)
        controls=C['fetch'](block+'/controls-1/result.json',local/'controls.json')
        assert controls['passed'] and controls['drained'] and controls['final_idle']
        state['controls']=dict(path=block+'/controls-1/result.json',sha256=C['sha'](local/'controls.json'))
        C['save'](RAW/'result.json',state)
        state['candidate_archive']=C['seal'](block,local,boot,True)
        recovery=BASE+'/recovery-1';folder=RAW/'recovery';folder.mkdir()
        R['source_guard'](folder/'source-before-transition.json',commit)
        settled_guard(folder/'guest-before-transition.json')
        C['guest']('mkdir -- '+shlex.quote(recovery),folder/'mkdir.log',30)
        print('RESTORE recovery',flush=True)
        restored=C['boot']('recovery',recovery,folder)
        state.update(recovery=restored,recovery_archive=C['seal'](recovery,folder,restored['boot_id'],False),
            passed=True,final_idle=True)
    except BaseException as error:
        state.update(error=repr(error),drain_requires_review=True);raise
    finally:
        state['coordinator']['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        C['save'](RAW/'result.json',state)
    print(json.dumps(state),flush=True)


if __name__=='__main__':main()
