#!/usr/bin/env python3
"""Check the retained immediate endpoint against every original control."""
import argparse
import json
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();out=a.run
    scheduler=runpy.run_path(str(ROOT/'bench/mutex_api_compare/run.py'))
    recovery=runpy.run_path(str(ROOT/'bench/mutex_api_compare/recovery_replay.py'))
    boundary=runpy.run_path(str(ROOT/'bench/mutex_api_compare/rcuht_boundary.py'))
    load=scheduler['load'];sha=scheduler['sha'];result=load(out/'result.json')
    controller=load(out/'controller.json');original=Path(result['original_inputs'])/'matrix'
    answer=dict(passed=False,checked=False,immediate=controller.get('immediate',False),
        result_sha256=sha(out/'result.json'),host_sha256=sha(out/'host-endpoint.json'),
        controller_sha256=sha(out/'controller.json'),driver_sha256=sha(Path(__file__)))
    try:
        assert result['passed'] and result['final_idle'] and result['sessions']==1
        assert controller['passed'] and controller['immediate'] and controller['host_sha256']==answer['host_sha256']
        for name,digest in scheduler['REPLAY_ENVIRONMENT_SHA256'].items():assert sha(original/name)==digest
        host=load(out/'host-endpoint.json')
        boundary['endpoint_link'](dict(answer,checked=True),controller,host,
            answer['result_sha256'],answer['host_sha256'],str(out/'result.json'))
        answer['checked']=True
        answer['comparison']=recovery['compare_environment'](scheduler['same_environment'],
            load(out/'transition.json'),load(original/'host-state.json'),host,
            load(original/'environment.json'),load(out/'matrix/environment.json'),
            load(original/'topology.json'),load(out/'matrix/topology.json'))
        answer['passed']=True
    except (AssertionError,ValueError) as error:answer['error']=repr(error)
    scheduler['save'](out/'endpoint.json',answer);print(json.dumps(answer))
    return 0 if answer['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
