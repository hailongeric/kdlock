#!/usr/bin/env python3
"""Capture an idle boundary without modifying benchmark inputs or modules."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

SOURCE=Path('/root/host_fs/kdlock')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('collection',type=Path);p.add_argument('--label',required=True)
    a=p.parse_args();base=a.collection.resolve()
    assert re.fullmatch('[a-z][a-z0-9-]*',a.label)
    assert not (base/(a.label+'-health.json')).exists()
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(SOURCE/'bench'),str(SOURCE/'bench/spin_cacheline')]
    from bench_runtime import idle as common_idle, FAULT
    from archive_run import idle
    idle(base,common_idle)
    original=json.loads((base/'owner.json').read_text())
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot==original['boot_id']
    now=time.time();uptime=float(Path('/proc/uptime').read_text().split()[0])
    start_uptime=original['started']-(now-uptime)
    dmesg=subprocess.check_output(['dmesg'],text=True,timeout=15)
    (base/(a.label+'-dmesg.log')).write_text(dmesg)
    recent=[]
    for line in dmesg.splitlines():
        match=re.match(r'\[\s*([0-9.]+)\]',line)
        if match and float(match[1])>=start_uptime and FAULT.search(line):recent.append(line)
    faults=[str(path.relative_to(base)) for path in base.glob('*/*/kernel.log')
        if FAULT.search(path.read_text())]
    idle(base,common_idle)
    result=dict(idle=True,boot_id=boot,kernel=os.uname().release,captured=now,
        new_faults_in_retained_dmesg=recent,per_session_kernel_faults=faults,
        collection_start_uptime_estimate=start_uptime,
        scope='Idle boundary; retained per-session logs and retained dmesg since collection start. No unload, reboot or new measurement.')
    (base/(a.label+'-health.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    assert not recent and not faults, 'kernel fault evidence retained; investigate before continuing'

if __name__=='__main__':main()
