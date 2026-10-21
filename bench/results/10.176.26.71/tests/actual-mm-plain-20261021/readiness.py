#!/usr/bin/env python3
"""Admission-only check after both modes passed; never starts a workload."""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
sys.path.insert(0,str(ROOT/'bench/mmap_lock'))
import plain


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True);p.add_argument('--host-state',type=Path,required=True)
    p.add_argument('--boot-id',required=True);a=p.parse_args()
    out=a.base/'throughput-readiness-1'
    plain.common.idle(Path('/root'));out.mkdir()
    result=dict(passed=False,accepted=False,timing_sessions=0,p95_status='DEFERRED',
                seven_mutex_causes='UNRESOLVED',driver_sha256=plain.rt.digest(Path(__file__)))
    try:
        inputs=a.base/'prepare-1/inputs.json';plain.prepared_inputs(inputs)
        paths=[a.base/(m+'-validation-1/result.json') for m in ('native','kd')]
        rows=[plain.common.load(path) for path in paths]
        plain.rt.require({r['kernel_mmap_mode'] for r in rows}=={'native','kd'} and
            all(r['passed'] and r['drained'] and r['final_idle'] and r['action']=='validate' and
                r['inputs_sha256']==plain.rt.digest(inputs) for r in rows),
            'same frozen binaries must pass both modes')
        result.update(both_mode_correctness=True,inputs_sha256=plain.rt.digest(inputs),
                      correctness={str(path):plain.rt.digest(path) for path in paths})
        args=argparse.Namespace(action='measure',boot_id=a.boot_id,mode='kd',
                               transition=a.base/'kd-transition-1/result.json',host_state=a.host_state)
        result.update(plain.profile(args,out))
        result.update(passed=True,admission='PASS',endpoint='NOT_RUN')
    except (plain.rt.Failure,ValueError) as error:
        result.update(admission='REFUSED',error=str(error))
    finally:
        plain.common.idle(Path('/root'));result['final_idle']=True
        plain.rt.write_json(out/'result.json',result)
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__=='__main__':sys.exit(main())
