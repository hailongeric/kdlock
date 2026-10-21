#!/usr/bin/env python3
"""Capture drained recovery health without rewriting earlier evidence."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/serial-continuation-20261022')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',required=True);a=p.parse_args()
    output=BASE/(a.name+'.json');rt.require(not output.exists(),'new health receipt required')
    idle=runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'];idle(Path('/root'),rt.idle)
    transition=json.loads((BASE/'transition-1/result.json').read_text())
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    modules=sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    rt.require(os.uname().release=='6.1.159-kdclobber2' and boot==transition['new_boot_id'] and
               modules==transition['modules'],'verified recovery boot/module set required')
    receipts={}
    for name in ('outer-1','direct-1'):
        path=BASE/name/'result.json';result=json.loads(path.read_text())
        records=json.loads((BASE/name/'matrix/records.json').read_text())
        rt.require(result['passed'] and result['final_idle'] and result['sessions']==1 and
            len(records)==1 and records[0]['drained'] and
            records[0]['retired']==dict(state=2,modules=0,frames=0,writers=0),'diagnostic did not retire exactly')
        endpoint=json.loads((BASE/name/'endpoint.json').read_text())
        rt.require(endpoint['checked'] and endpoint['result_sha256']==rt.digest(path),
                   'original diagnostic endpoint missing')
        receipts[name]=dict(result_sha256=rt.digest(path),endpoint_sha256=rt.digest(BASE/name/'endpoint.json'),
                            endpoint_passed=endpoint['passed'])
    control=runpy.run_path('/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021/transition.py')
    preserved=control['preserved']()
    messages=rt.command(['dmesg'],BASE/(a.name+'-dmesg.log'))
    rt.require(not rt.FAULT.search(messages),'kernel fault in retained recovery log')
    idle(Path('/root'),rt.idle)
    result=dict(passed=True,idle=True,boot_id=boot,release=os.uname().release,modules=modules,
        recovery_preserved=preserved['recovery_preserved'],diagnostics=receipts,
        new_faults_in_retained_dmesg=[],accepted=False,p95_status='DEFERRED',
        seven_mutex_causes='UNRESOLVED',driver_sha256=rt.digest(Path(__file__)))
    rt.write_json(output,result);print(json.dumps(dict(passed=True,idle=True,boot_id=boot,modules=len(modules))))


if __name__=='__main__':main()
