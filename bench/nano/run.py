#!/usr/bin/env python3
"""Serial nano campaign owner. Execute only in the documented recovery VM."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
THREADS = [1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60]

def commands(base):
    common = ['--threads', *map(str, THREADS), '--collector-cpu', '63', '--repeats', '3',
              '--duration-ms', '2000', '--peak-window-ms', '300', '--peak-settle-ms', '300',
              '--sample-ms', '10', '--kernel-source', '/root/linux-6.1.159-kdclobber2',
              '--kernel-baseline', '/root/kdlock-kernel-baselines/mutex-clobber2-20260919']
    variants = [('cacheline', ['--cachelines', '1', '8']), ('rcuht', [])]
    for lock in ('spin', 'mutex'):
        for workload, extra in variants:
            name = lock + '-' + workload
            yield name, [sys.executable, str(ROOT/'bench/tclock_compare'/('run_mutex.py' if lock=='mutex' else 'run.py')),
                         '--backends', 'native', 'tclock', 'kdlock', '--cpus', '0-59',
                         '--workload', workload, *extra, *(['--mutex-api','public'] if lock=='mutex' else []),
                         '--keep-going-no-jit', *common, '--output', str(base/name)]
    for lock in ('rwlock', 'rwsem'):
        yield lock, [sys.executable, str(ROOT/'bench/rwlock_compare/run.py'), '--lock-kind', lock,
                     '--backends', 'native', *(['tclock'] if lock=='rwlock' else []), 'kdlock',
                     '--workloads', 'cacheline', 'rcuht', '--cachelines', '1', '8',
                     '--write-percent', '1', '20',
                     '--cpus', *map(str, range(60)), *common, '--output', str(base/lock)]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--plan-only', action='store_true')
    a=p.parse_args(); base=a.output.resolve()
    plan=list(commands(base))
    if a.plan_only:
        print(json.dumps(plan, indent=2)); return
    assert ROOT == Path('/root/host_fs/kdlock') and os.geteuid()==0
    assert os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1' and os.environ.get('KDLOCK_SNAPSHOT_TAG')
    assert os.uname().release=='6.1.159-kdclobber2'
    with open('/run/lock/kdlock-nano.lock','w') as owner:
        fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        base.mkdir(parents=True,exist_ok=False)
        (base/'commands.json').write_text(json.dumps(plan,indent=2)+'\n')
        (base/'owner.json').write_text(json.dumps(dict(pid=os.getpid(),started=time.time(),
             boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')
        statuses=[]
        for name,cmd in plan:
            if (base/'STOP').exists(): break
            if shutil.disk_usage(base).free < 2 * 1024**3:
                (base/'storage-stop.json').write_text(json.dumps(dict(block=name,free_bytes=shutil.disk_usage(base).free)))
                break
            print('START '+name,flush=True)
            with (base/(name+'.log')).open('x') as log:
                # The child owns lifecycle checks. A timeout stops the campaign;
                # it never authorizes cleanup or starting another measured case.
                try:
                    result=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=21600)
                    code=result.returncode
                except subprocess.TimeoutExpired:
                    code='TIMEOUT_UNPROVEN_DRAIN'
            statuses.append(dict(block=name,returncode=code,finished=time.time()))
            (base/'status.json').write_text(json.dumps(statuses,indent=2)+'\n')
            print('FINISH '+name+' '+str(code),flush=True)
            if code:
                failure=base/name/'failure.json'
                # Zero-delegation is retained, never relabelled as delegated.
                if code==1 and failure.exists() and json.loads(failure.read_text()).get('status')=='NO_JIT':
                    continue
                break
        (base/'owner-finished.json').write_text(json.dumps(dict(finished=time.time(),blocks=len(statuses)))+'\n')

if __name__=='__main__': main()
