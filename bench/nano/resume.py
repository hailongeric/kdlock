#!/usr/bin/env python3
"""Resume only untouched blocks after a verified idle campaign boundary.

Run from an external tools directory in the VM. Prior failures and deliberately
withheld repetitions remain in place; this owner never retries a measured case.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SOURCE=Path('/root/host_fs/kdlock')

def save(path, value):
    path.write_text(json.dumps(value,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('collection',type=Path)
    p.add_argument('--receipt',required=True)
    p.add_argument('--check-only',action='store_true')
    a=p.parse_args();base=a.collection.resolve()
    assert a.receipt.startswith('continuation-') and Path(a.receipt).name==a.receipt
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    policy=(os.getpriority(os.PRIO_PROCESS,0),os.sched_getscheduler(0))
    assert policy==(5,os.SCHED_OTHER),policy
    assert os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1'
    assert os.environ.get('KDLOCK_SNAPSHOT_TAG')
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(SOURCE/'bench'),str(SOURCE/'bench/tclock_compare')]
    from run import idle as common_idle
    from archive_run import idle
    with open('/run/lock/kdlock-nano.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        original=json.loads((base/'owner.json').read_text())
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert original['boot_id']==boot
        receipts=[base]+sorted(p for p in base.glob('continuation*') if p.is_dir())
        done={}
        for receipt in receipts:
            assert (receipt/'owner-finished.json').is_file(),str(receipt)
            if not (receipt/'status.json').exists():continue
            for row in json.loads((receipt/'status.json').read_text()):
                assert row['block'] not in done, 'duplicate block ownership'
                done[row['block']]=row
        held={r['name'] for receipt in receipts
            if (receipt/'prefix-finished.json').is_file()
            for r in json.loads((receipt/'prefix-finished.json').read_text()).get('skipped',[])}
        for name,row in done.items():
            assert row['returncode'] in (0,1), 'unproven or abnormal termination'
            block=base/name
            if row['returncode']:
                failure=json.loads((block/'failure.json').read_text())
                assert failure['status']=='NO_JIT' or (
                    name=='spin-cacheline' and failure['status']=='DATA_ERROR' and
                    failure['error']=='finished worker progress differs from exact total')
            for spec in json.loads((block/'plan.json').read_text()):
                path=block/spec['name']/'session.json'
                if not path.exists():
                    assert name=='spin-cacheline' and spec['name'] in held, str(path)
                    continue
                r=json.loads(path.read_text())
                assert r.get('drained') is True and not r.get('cleanup_error'),str(path)
                if r['execution_status']=='DATA_ERROR':
                    assert name=='spin-cacheline' and r['error']=='finished worker progress differs from exact total'
                else:
                    assert r['execution_status']=='OK' or (r['execution_status']=='NO_JIT' and r['jit_bodies']==0)
                    assert r['measurement']['complete'] and r['measurement']['data_ok']
        idle(base,common_idle)
        commands=json.loads((base/'commands.json').read_text())
        reference=json.loads((base/'spin-cacheline'/'source-sha256.json').read_text())
        for relative,expected in reference.items():
            assert hashlib.sha256((SOURCE/relative).read_bytes()).hexdigest()==expected,relative
        if a.check_only:
            print(json.dumps(dict(untouched_blocks=[name for name,_ in commands if name not in done],
                completed_blocks=list(done),held=sorted(held))))
            return
        output=base/a.receipt;output.mkdir(exist_ok=False)
        save(output/'owner.json',dict(pid=os.getpid(),started=time.time(),boot_id=boot,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            commands_sha256=hashlib.sha256((base/'commands.json').read_bytes()).hexdigest()))
        statuses=[]
        for name,cmd in commands:
            if name in done:continue
            if (output/'STOP').exists():break
            if shutil.disk_usage(base).free<2*1024**3:
                save(output/'storage-stop.json',dict(block=name,free_bytes=shutil.disk_usage(base).free))
                break
            assert not (base/name).exists() and not (base/(name+'.log')).exists()
            for relative,expected in reference.items():
                assert hashlib.sha256((SOURCE/relative).read_bytes()).hexdigest()==expected,relative
            idle(base,common_idle)
            print('START '+name,flush=True)
            with (base/(name+'.log')).open('x') as log:
                try:
                    code=subprocess.run(cmd,cwd=SOURCE,stdout=log,stderr=subprocess.STDOUT,timeout=21600).returncode
                except subprocess.TimeoutExpired:
                    code='TIMEOUT_UNPROVEN_DRAIN'
            statuses.append(dict(block=name,returncode=code,finished=time.time()))
            save(output/'status.json',statuses)
            print('FINISH '+name+' '+str(code),flush=True)
            if code:
                failure=base/name/'failure.json'
                if code==1 and failure.exists() and json.loads(failure.read_text()).get('status')=='NO_JIT':continue
                break
        save(output/'owner-finished.json',dict(finished=time.time(),blocks=len(statuses)))

if __name__=='__main__':main()
