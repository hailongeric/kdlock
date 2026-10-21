#!/usr/bin/env python3
"""One serial Native/KD diagnostic pair; stop on a refused prerequisite."""
import json
from pathlib import Path
import runpy
import shlex
import sys

ROOT = Path(__file__).resolve().parents[5]
PRIOR_REPORT = ROOT/'bench/results/10.176.26.71/tests/serial-continuation-20261022'
C = runpy.run_path(str(PRIOR_REPORT/'campaign.py'))
RAW = ROOT/'bench/results/10.176.26.71/raw/bench/mmap-contention-20261022/pair-1'
BASE = '/root/kdlock-evidence/10.176.26.71/bench/mmap-contention-20261022'
PRIOR = '/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021'


def main():
    RAW.mkdir()
    state = dict(passed=False, accepted=False, planned=['native','kd'], completed=[],
                 unrun=['native','kd'], driver_sha256=C['sha'](Path(__file__)),
                 diagnostic=True, seven_mutex_causes='UNRESOLVED')
    original_path = ROOT/'bench/results/10.176.26.71/raw/tests/serial-continuation-20261022/campaign-1/original-host.json'
    assert C['sha'](original_path) == '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
    original = C['load'](original_path)
    try:
        C['guest']('mkdir -- '+shlex.quote(BASE+'/control-1'),RAW/'mkdir-control.log',30)
        C['copy_in']([ROOT/'bench/mmap_lock/contention_profile.py'],BASE+'/control-1/',RAW/'copy-driver.log')
        for mode in ('native','kd'):
            block=BASE+'/'+mode+'-1';local=RAW/mode;local.mkdir()
            C['guest']('mkdir -- '+shlex.quote(block),local/'mkdir.log',30)
            print('BOOT',mode,flush=True)
            transition=C['boot'](mode,block,local)
            host_path=local/'host-admission.json';host=C['capture'](host_path)
            reason=C['host_screen'](original,host)
            if reason:
                state['refusal']=dict(mode=mode,reason=reason,host_sha256=C['sha'](host_path),
                    threads=len(host['qemu'][0]['tasks']),workload_started=False)
                C['save'](local/'refusal.json',state['refusal'])
                print('REFUSED',mode,reason,flush=True)
                state.setdefault('archives',[]).append(C['seal'](block,local,transition['boot_id'],True))
                break
            C['copy_in']([host_path],block+'/host-admission.json',local/'copy-host.log')
            session=block+'/profile';driver=BASE+'/control-1/contention_profile.py'
            args=[driver,'run','--output',session,'--host-state',block+'/host-admission.json',
                '--boot-id',transition['boot_id'],'--mode',mode,'--transition',block+'/transition/result.json',
                '--inputs',PRIOR+'/prepare-1/inputs.json','--validated',PRIOR+'/native-validation-1/result.json',
                PRIOR+'/kd-validation-1/result.json']
            print('PROFILE',mode,flush=True)
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
        block=BASE+'/recovery';local=RAW/'recovery';local.mkdir()
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
