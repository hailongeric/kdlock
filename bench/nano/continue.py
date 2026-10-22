#!/usr/bin/env python3
"""Continue untouched commands after a drained block boundary, never retry a failure.

Copy this owner outside the frozen source tree while idle. Collection commands,
measurement configuration and original source bytes remain unchanged.
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

def finish_prefix(block, output):
    """Continue unattempted cases; never rerun the diagnosed failing point."""
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(SOURCE/'bench/tclock_compare'))
    import run
    from session import BackendSession
    frozen=json.loads((block/'source-sha256.json').read_text())
    hashes=json.loads((block/'binary-sha256.json').read_text())
    plan=json.loads((block/'plan.json').read_text())
    assert all(r['lock_kind']=='spin' and r['workload']=='cacheline' for r in plan)
    def point(r):return tuple(r[k] for k in ('workload','cachelines','threads','arm'))
    affected=set()
    for spec in plan:
        path=block/spec['name']/'session.json'
        if not path.exists():continue
        r=json.loads(path.read_text())
        assert r['drained'] and not r.get('cleanup_error')
        if r['execution_status']=='DATA_ERROR':
            assert r['error']=='finished worker progress differs from exact total'
            raw=json.loads(path.with_name('measure.json').read_text())
            assert raw['complete'] and raw['data_ok']
            affected.add(point(r))
        else:
            assert r['execution_status']=='OK' or (r['execution_status']=='NO_JIT' and r['jit_bodies']==0)
    assert affected, 'no diagnosed failed point to isolate'
    skipped=[];completed=[]
    for spec in plan:
        if (block/spec['name']).exists():continue
        if point(spec) in affected:
            skipped.append(dict(name=spec['name'],reason='remaining repetition of failed point held; no corrected rerun'))
            continue
        if (output/'STOP').exists():raise RuntimeError('STOP at drained boundary')
        assert run.source_state()==frozen
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        run.idle()
        print('PREFIX '+spec['name'],flush=True)
        session=BackendSession(block,spec,workload_module=block/'variants'/spec['arm']/'spin_cacheline.ko')
        run.execute_session(session,True)
        completed.append(spec['name'])
        (output/'prefix-progress.json').write_text(json.dumps(dict(completed=completed,skipped=skipped),indent=2)+'\n')
    run.idle();run.report(block)
    (output/'prefix-finished.json').write_text(json.dumps(dict(completed=completed,skipped=skipped),indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('collection',type=Path);a=p.parse_args()
    base=a.collection.resolve()
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    # Match the captured original owner; do not silently normalize policy.
    assert os.getpriority(os.PRIO_PROCESS,0)==5 and os.sched_getscheduler(0)==os.SCHED_OTHER
    assert os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1' and os.environ.get('KDLOCK_SNAPSHOT_TAG')
    with open('/run/lock/kdlock-nano.lock','w') as owner:
        fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        original=json.loads((base/'owner.json').read_text())
        assert original['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert (base/'owner-finished.json').is_file()
        previous=json.loads((base/'status.json').read_text())
        done={r['block'] for r in previous}
        output=base/'continuation'
        output.mkdir(exist_ok=False)
        (output/'owner.json').write_text(json.dumps(dict(pid=os.getpid(),started=time.time(),
            boot_id=original['boot_id'],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            commands_sha256=hashlib.sha256((base/'commands.json').read_bytes()).hexdigest()),indent=2)+'\n')
        for row in previous:
            block=base/row['block']
            assert row['returncode'] in (0,1)
            if row['returncode']:
                failure=json.loads((block/'failure.json').read_text())
                if failure['status']=='DATA_ERROR':
                    assert failure['error']=='finished worker progress differs from exact total'
                    finish_prefix(block,output)
                    continue
                assert failure['status']=='NO_JIT'
            for spec in json.loads((block/'plan.json').read_text()):
                record=json.loads((block/spec['name']/'session.json').read_text())
                assert record['drained'] and not record.get('cleanup_error')
                assert record['measurement']['complete'] and record['measurement']['data_ok']
                assert record['execution_status']=='OK' or (record['execution_status']=='NO_JIT' and record['jit_bodies']==0)
        reference=json.loads((base/previous[0]['block']/'source-sha256.json').read_text())
        plan=json.loads((base/'commands.json').read_text())
        statuses=[]
        for name,cmd in plan:
            if name in done:continue
            if (output/'STOP').exists():break
            if shutil.disk_usage(base).free<2*1024**3:
                (output/'storage-stop.json').write_text(json.dumps(dict(block=name,free_bytes=shutil.disk_usage(base).free)))
                break
            assert not (base/name).exists() and not (base/(name+'.log')).exists()
            for relative,expected in reference.items():
                assert hashlib.sha256((SOURCE/relative).read_bytes()).hexdigest()==expected,relative
            print('START '+name,flush=True)
            with (base/(name+'.log')).open('x') as log:
                try:code=subprocess.run(cmd,cwd=SOURCE,stdout=log,stderr=subprocess.STDOUT,timeout=21600).returncode
                except subprocess.TimeoutExpired:code='TIMEOUT_UNPROVEN_DRAIN'
            statuses.append(dict(block=name,returncode=code,finished=time.time()))
            (output/'status.json').write_text(json.dumps(statuses,indent=2)+'\n')
            print('FINISH '+name+' '+str(code),flush=True)
            if code:
                failure=base/name/'failure.json'
                if code==1 and failure.exists() and json.loads(failure.read_text()).get('status')=='NO_JIT':continue
                break
        (output/'owner-finished.json').write_text(json.dumps(dict(finished=time.time(),blocks=len(statuses)))+'\n')

if __name__=='__main__':main()
