#!/usr/bin/env python3
"""Execute the requested 1..60 synthetic/API matrix with frozen source."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

ROOT=Path('/root/host_fs/kdlock')
OUT=Path('/root/kdlock-evidence/10.176.26.71/bench/workloads-20261015T180603Z')
THREADS=[*range(1,9),*range(12,61,4)]
CPUS=list(range(60))
PY=sys.executable
sys.path.insert(0,str(ROOT/'bench/rwlock_compare'))
import run as rw
from bench_runtime import FAULT

def now():
    return datetime.now(timezone.utc).isoformat()

def save(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    tmp.replace(path)

def source_check():
    manifest=json.loads((OUT/'control/source-sha256.json').read_text())
    for name,wanted in manifest.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==wanted,name

def health():
    rw.idle()
    assert not Path('/sys/module/real_api').exists(),'real_api module remains loaded'
    log=subprocess.check_output(['dmesg'],text=True)
    assert not FAULT.search(log),'kernel fault; preserve VM and evidence'
    assert Path('/sys/devices/system/cpu/online').read_text().strip()=='0-63'
    expected=json.loads((OUT/'control/guest-before.json').read_text())['boot_id']
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==expected
    return log

def plan():
    result=[]
    # Measure all three families early, then the remaining payloads.
    cases=[('spin','cacheline',1),('mutex','cacheline',1),('rwlock','cacheline',1)]
    cases += [(k,'cacheline',n) for n in (2,4,8,16) for k in ('spin','mutex','rwlock')]
    cases += [(k,'rcuht',0) for k in ('spin','mutex','rwlock')]
    common=['--threads',*map(str,THREADS),'--collector-cpu','63','--repeats','3',
            '--duration-ms','2000','--peak-window-ms','300','--peak-settle-ms','300',
            '--kernel-source','/root/linux-6.1.159-kdclobber2',
            '--kernel-baseline','/root/kdlock-kernel-baselines/mutex-clobber2-20260919']
    for kind,workload,lines in cases:
        name=f'{kind}-{workload}'+(f'-c{lines:02d}' if lines else '')
        backends=['native','tclock']
        if kind!='mutex' or lines==1:
            backends+=['kdlock']
        runner=('bench/rwlock_compare/run.py' if kind=='rwlock' else
                'bench/tclock_compare/run_mutex.py' if kind=='mutex' else 'bench/tclock_compare/run.py')
        args=[PY,runner,*common,'--backends',*backends,'--output',str(OUT/name)]
        if kind=='rwlock':
            args+=['--workloads',workload,'--write-percent','1','20','--cpus',*map(str,CPUS)]
        else:
            args+=['--workload',workload,'--cpus','0-59','--keep-going-no-jit']
        if lines:
            args+=['--cachelines',str(lines)]
        if kind=='mutex' and lines==1:
            args+=['--mutex-implementation','owned-v1','--owned-mutex-cabi',
                   '--owned-mutex-reuse-spins','32','--mutex-acceptance','adaptive-performance']
        result.append(dict(name=name,family='synthetic',lock_kind=kind,workload=workload,
            cachelines=lines,backends=backends,expected_sessions=63*len(backends)*(2 if kind=='rwlock' else 1),argv=args))
    apis=[('ofd',['front','tail','miss'],[16,128]),('setfd',['toggle'],[16,512]),
          ('pipebytes',['query'],[16,128]),('pipecap',['query'],[16]),
          ('seek',['set','end'],[16]),('utsname',['host','domain'],[20]),
          ('xattr',['front','tail','miss','size'],[16,128])]
    for kind,queries,counts in apis:
        family='mutex' if kind in ('pipebytes','pipecap','seek') else 'rwlock' if kind=='utsname' else 'spin'
        for query in queries:
            for entries in counts:
                name=f'api-{kind}-{query}-n{entries}'
                backends=['native','tclock']
                if kind not in ('xattr','pipebytes','pipecap','seek'):
                    backends+=['kdlock']
                args=[PY,'bench/real_api/run.py','--kinds',kind,'--queries',query,
                    '--entries',str(entries),'--value-size','64','--backends',*backends,
                    '--threads',*map(str,THREADS),'--cpus',','.join(map(str,CPUS)),
                    '--collector-cpu','63','--repeats','3','--duration-ms','2000',
                    '--warmup','48000','--warmup-ms','1000','--output',str(OUT/name)]
                result.append(dict(name=name,family='api',lock_kind=family,workload=kind,
                    query=query,entries=entries,backends=backends,expected_sessions=63*len(backends),argv=args))
    return result

def main():
    # A detached shell/unshare launch can inherit ignored termination signals.
    # Children, especially the translator, need their ordinary stop semantics.
    inherited={s.name:str(signal.getsignal(s)) for s in (signal.SIGINT,signal.SIGTERM)}
    for signum in (signal.SIGINT,signal.SIGTERM):
        signal.signal(signum,signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGINT,signal.SIGTERM})
    save(OUT/'control/launch-signals.json',dict(inherited=inherited,reset_to_default=True))
    assert os.geteuid()==0 and ROOT==Path.cwd()
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED']=='1'
    assert os.environ['KDLOCK_SNAPSHOT_TAG']=='workloads-20261015T172603Z'
    assert 'workloads-20261015T172603Z' in (OUT/'control/snapshots.txt').read_text()
    source_check(); health()
    groups=plan()
    save(OUT/'matrix-plan.json',groups)
    status=dict(started_utc=now(),threads=THREADS,worker_cpus=CPUS,collector_cpu=63,
        expected_sessions=sum(g['expected_sessions'] for g in groups),state='RUNNING',groups=[],
        exclusions=[dict(backend='kdlock',scope='mutex c02/c04/c08/c16/rcuht',reason='owned-v1 performance runner supports only c01'),
                    dict(backend='kdlock',scope='pipebytes/pipecap/seek',reason='owned mutex cannot substitute kernel-owned object'),
                    dict(backend='kdlock',scope='xattr',reason='documented pointer/context translation refusal; no accepted KD comparison')])
    save(OUT/'matrix-status.json',status)
    try:
        for group in groups:
            if (OUT/'STOP').exists():
                status['state']='STOPPED'; break
            source_check(); health()
            free=shutil.disk_usage(OUT).free
            assert free>1024**3,f'Less than 1 GiB free before {group["name"]}; archive evidence before resuming'
            entry=dict(name=group['name'],started_utc=now(),free_bytes_before=free)
            status['groups'].append(entry); save(OUT/'matrix-status.json',status)
            print(f'START {group["name"]}: {group["expected_sessions"]} sessions',flush=True)
            with (OUT/(group['name']+'.log')).open('w') as log:
                completed=subprocess.run(group['argv'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=14400)
            entry['exit_code']=completed.returncode
            health(); source_check()
            records=json.loads((OUT/group['name']/'records.json').read_text())
            entry.update(finished_utc=now(),recorded_sessions=len(records),
                executed_sessions=sum(r.get('execution_status')!='NOT_RUN' for r in records),
                drained_sessions=sum(r.get('drained') is True for r in records),
                status_counts=dict(Counter(r.get('execution_status','UNKNOWN') for r in records)))
            save(OUT/'matrix-status.json',status)
            assert len(records)==entry['executed_sessions']==entry['drained_sessions']==group['expected_sessions'], 'Incomplete or undrained group'
            if completed.returncode:
                failure=json.loads((OUT/group['name']/'failure.json').read_text())
                assert failure.get('status')=='NO_JIT','Failure outside drained NO_JIT'
            print(f'END {group["name"]}: {entry["status_counts"]}',flush=True)
        else:
            (OUT/'control/dmesg-final.txt').write_text(health()); source_check()
            status['state']='COMPLETE'
    except Exception as error:
        status.update(state='FAILED',error=str(error))
        print(f'STOP: {error}',flush=True)
        raise
    finally:
        status['finished_utc']=now(); save(OUT/'matrix-status.json',status)

if __name__=='__main__':
    main()
