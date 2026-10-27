#!/usr/bin/env python3
"""Source-host orchestration of single-round Linux 7 catalog measurements.

All builds, workload execution and telemetry run in the designated VM/host.
Publication consumes drained receipts and never turns exploratory timing into
strict qualification. A failed or uncertain coordinate is never retried here.
"""
import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from current_plan import commands
from report import render

CAMPAIGN = 'catalog-linux70-20261027'
GUEST = '/root/kdlock-evidence/10.176.26.71/bench/' + CAMPAIGN
RAW = ROOT/'bench/results/10.176.26.71/raw/bench'/CAMPAIGN
PUBLIC = ROOT/'bench/results/10.176.26.71/bench'/CAMPAIGN
SNAPSHOT = 'linux70-kdlock1-clean-20261027'
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
       '-o', 'StrictHostKeyChecking=yes', '-o', 'ServerAliveInterval=10',
       '-o', 'ServerAliveCountMax=2']
ENV = ['env', 'LC_ALL=C', 'PYTHONDONTWRITEBYTECODE=1',
       'PATH='+str(Path(PYTHON).parent)+':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
       'KDLOCK_RECOVERY_CONFIRMED=1', 'KDLOCK_SNAPSHOT_TAG='+SNAPSHOT]


def save(path, value):
    temporary = path.with_name('.'+path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def remote(label, argv, *, guest=True, code=None, seconds=60, allowed=(0,)):
    receipt = RAW/(label+'-command.json')
    if receipt.exists():
        raise ValueError('Attempt already exists: '+label)
    command = [*SSH, *(['-p', '2222', 'root@10.176.26.71'] if guest else ['eric@10.176.26.71']), shlex.join(argv)]
    result = dict(argv=command, timeout_seconds=seconds, completion_unconfirmed=True,
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(receipt, result)
    with (RAW/(label+'.stdout')).open('xb') as output, (RAW/(label+'.stderr')).open('xb') as error:
        child = subprocess.Popen(command, stdin=subprocess.PIPE if code else subprocess.DEVNULL,
                                 stdout=output, stderr=error)
        result['local_pid'] = child.pid
        save(receipt, result)
        if code:
            child.stdin.write(code.encode())
            child.stdin.close()
        deadline = time.monotonic()+seconds
        while child.poll() is None:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                result['error'] = 'Deadline expired; transport left running; guest completion and drain unproven'
                save(receipt, result)
                raise RuntimeError(result['error'])
            try:
                child.wait(timeout=min(20, remaining))
            except subprocess.TimeoutExpired:
                print('RUNNING '+label, flush=True)
    result.update(returncode=child.returncode, completion_unconfirmed=False,
                  finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(receipt, result)
    if child.returncode not in allowed:
        raise RuntimeError('Remote command failed; inspect '+label+' before further live work')
    return result


def health(label):
    code = """import json,os,runpy,shutil,sys,subprocess
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,'/root/host_fs/kdlock/bench/spin_cacheline')
import bench_runtime as rt
runpy.run_path('/root/host_fs/kdlock/bench/archive_run.py')['idle'](Path(%r),rt.idle)
assert os.uname().release=='7.0.0-38-kdlock1'
print(json.dumps(dict(idle=True,release=os.uname().release,
 boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 modules=sorted(x.split()[0] for x in Path('/proc/modules').read_text().splitlines()),
 taint=int(Path('/proc/sys/kernel/tainted').read_text()),
 root_free=shutil.disk_usage('/root').free,data_free=shutil.disk_usage('/mnt/kdlock-builds').free,
 dmesg=subprocess.check_output(['dmesg'],text=True))))
""" % GUEST
    remote(label,[*ENV,'taskset','-c','63',PYTHON,'-'],code=code)
    row=json.loads((RAW/(label+'.stdout')).read_text())
    if row['root_free']<2*1024**3:
        raise RuntimeError('Guest root free space below 2GiB reserve')
    initial=RAW/'initial-health.stdout'
    if label!='initial-health' and initial.exists():
        before=json.loads(initial.read_text())
        if any(row[k]!=before[k] for k in ('boot_id','release','modules','taint')):
            raise RuntimeError('Guest boot, module inventory or taint changed')
        # Scan the complete retained endpoint, even if the ring wrapped. Each
        # measured session also retains its own before/after fault checks;
        # endpoint observations never establish continuous log coverage.
        save(RAW/(label+'-log-coverage.json'),dict(
            original_prefix_preserved=row['dmesg'].startswith(before['dmesg']),
            scope='Complete retained endpoint scan plus per-session checks; no continuous log-coverage claim'))
        if any(marker in row['dmesg'] for marker in
               ('BUG:', 'Oops:', 'Kernel panic', 'general protection fault', 'WARNING: CPU:')):
            raise RuntimeError('New kernel fault/warning after campaign admission')
    return row


def capture(label):
    script='/home/eric/vm/vm-shared/kdlock/bench/basic/capture_host.py'
    remote(label,['timeout','45','sudo','-n','python3',script,'--snapshot',SNAPSHOT],guest=False)
    return json.loads((RAW/(label+'.stdout')).read_text())


def compare(reference,current):
    problems=[]
    for key in ('host_boot_id','cpufreq','no_turbo','numa','recovery_snapshot'):
        if current[key]!=reference[key]:problems.append(key+' changed')
    b,a=reference['qemu'][0],current['qemu'][0]
    for key in ('pid','start_ticks','args'):
        if a[key]!=b[key]:problems.append('QEMU '+key+' changed')
    # CPU63 worker creation/retirement is recorded under the already-authorized
    # exploratory policy; permanent service/vCPU identities remain exact.
    permanent=lambda q:{t['tid']:t for t in q['tasks'] if t['comm']!='worker'}
    if permanent(a)!=permanent(b):problems.append('Permanent QEMU task identities/placement changed')
    if any(t['affinity']!=[63] for t in a['tasks'] if t['comm']=='worker'):
        problems.append('Auxiliary worker outside CPU63')
    def bindings(q):
        return [(f[0],f[1],next((v for v in f if v.startswith('kernelpagesize_kB=')),None))
                for line in q['numa_maps'].splitlines() if len(f:=line.split())>1 and f[1].startswith('bind:')]
    if not bindings(b) or bindings(a)!=bindings(b):problems.append('NUMA memory bindings changed')
    return problems


def monitor_start(name):
    # MM callers set RAW directly; its final component is the actual campaign.
    token=RAW.name+'-'+name
    if not re.fullmatch(r'[a-z0-9-]+',token):
        raise ValueError('Invalid campaign-qualified frequency token')
    script=(HERE/'frequency_monitor.py').read_bytes()
    command=[*SSH,'eric@10.176.26.71',shlex.join(['timeout','3570','sudo','-n','taskset','-c','63','python3','-',token])]
    receipt=RAW/(name+'-frequency-command.json')
    if receipt.exists():raise RuntimeError('Frequency attempt already exists: '+name)
    record=dict(argv=command,script_sha256=hashlib.sha256(script).hexdigest(),campaign=RAW.name,
        name=name,token=token,stop_path='/tmp/kdlock-linux70-'+token+'-stop',state='STARTING',
        startup_confirmed=False,completion_unconfirmed=True,returncode=None,
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(receipt,record)
    child=output=error=None
    try:
        output=(RAW/(name+'-frequency.jsonl')).open('xb')
        error=(RAW/(name+'-frequency.stderr')).open('xb')
        child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=output,stderr=error)
        record['local_pid']=child.pid
        save(receipt,record)  # Retain PID/script/token even if stdin or startup fails.
        child.stdin.write(script);child.stdin.close()
        deadline=time.monotonic()+15
        while True:
            if child.poll() is not None:
                raise RuntimeError('Frequency monitor exited before startup')
            if (RAW/(name+'-frequency.jsonl')).stat().st_size:
                record.update(state='RUNNING',startup_confirmed=True)
                save(receipt,record)
                return child,output,error,receipt
            if time.monotonic()>deadline:
                raise TimeoutError('Frequency startup unconfirmed; transport left running')
            time.sleep(.1)
    except BaseException as failure:
        rc=child.poll() if child is not None else None
        confirmed=child is None or rc is not None
        record.update(state=('LAUNCH_FAILED' if child is None else 'EXITED_BEFORE_READY') if confirmed
                      else 'STARTUP_UNCONFIRMED',returncode=rc,completion_unconfirmed=not confirmed,
                      error=repr(failure))
        if confirmed:
            record['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            if output is not None:output.close()
            if error is not None:error.close()
        else:
            # Preserve ownership of live local streams for explicit diagnosis.
            failure.monitor_state=(child,output,error,receipt)
        save(receipt,record)
        raise


def monitor_stop(name,state):
    child,output,error,receipt=state
    record=json.loads(receipt.read_text())
    try:
        if (receipt.parent!=RAW or record['name']!=name or record['local_pid']!=child.pid or
                record['token']!=record['campaign']+'-'+name or
                record['stop_path']!='/tmp/kdlock-linux70-'+record['token']+'-stop'):
            raise RuntimeError('Frequency stop does not match its original campaign/start receipt')
        if child.poll() is not None:raise RuntimeError('Frequency monitor exited unexpectedly')
        record['state']='STOP_REQUESTED';save(receipt,record)
        code="from pathlib import Path\nPath(%r).touch(exist_ok=False)\n" % record['stop_path']
        remote(name+'-frequency-stop',['timeout','15','sudo','-n','python3','-'],guest=False,code=code,seconds=25)
        rc=child.wait(timeout=20)
        record.update(state='EXITED',returncode=rc,completion_unconfirmed=False,
                      finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        output.close();error.close();save(receipt,record)
        events=[json.loads(line) for line in (receipt.parent/(name+'-frequency.jsonl')).read_text().splitlines()]
        if (rc or not events or events[-1]['event']!='complete' or not events[-1]['stop_requested'] or
                not all(e['policy_ok'] for e in events if e['event']=='sample')):
            raise RuntimeError('Frequency telemetry incomplete or policy drifted')
        record['telemetry_complete']=True;save(receipt,record)
    except BaseException as failure:
        rc=child.poll()
        record.update(state='STOP_FAILED' if rc is not None else 'STOP_UNCONFIRMED',returncode=rc,
                      completion_unconfirmed=rc is None,error=repr(failure))
        if rc is not None:
            record['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            output.close();error.close()
        else:
            failure.monitor_state=state
        save(receipt,record)
        raise


def preserve(name):
    remote(name+'-archive',['timeout','240','tar','-czf','-','-C',GUEST,name],seconds=260)
    path=RAW/(name+'-archive.stdout')
    files=0;links=[]
    with tarfile.open(path) as archive:
        for member in archive:
            relative=PurePosixPath(member.name)
            if relative.is_absolute() or '..' in relative.parts or relative.parts[0]!=name:
                raise RuntimeError('Unsafe archive path')
            if member.isfile():
                target=RAW/member.name;target.parent.mkdir(parents=True,exist_ok=True)
                data=archive.extractfile(member).read()
                if target.exists():raise RuntimeError('Evidence destination already exists')
                target.write_bytes(data);files+=1
            elif member.issym():
                if relative.parts[-2]!='workspace' or relative.name not in ('include','disassem') or member.linkname!=GUEST+'/'+name+'/source/'+relative.name:
                    raise RuntimeError('Unexpected evidence symlink')
                links.append(dict(path=member.name,target=member.linkname,materialized=False))
            elif not member.isdir():raise RuntimeError('Unexpected special evidence member')
    save(RAW/(name+'-preservation.json'),dict(archive=path.name,sha256=sha(path),bytes=path.stat().st_size,regular_files=files,links=links))
    manifest=json.loads((RAW/name/'source-sha256.json').read_text())
    for relative,expected in manifest.items():
        if sha(RAW/name/'source'/relative)!=expected:raise RuntimeError('Frozen source hash mismatch: '+relative)
    return files


def publish(progress):
    rows=['# Linux 7 single-round benchmark catalog','',
          'Kernel: `7.0.0-38-kdlock1`. Fixed host policy: 2.0 GHz. One timed round per coordinate.',
          'Workers: 1–8, then 12–60 by four. Auxiliary QEMU workers stay on CPU63; timing is exploratory, with no repetition variance estimate.','',
          'Source policy: trusted kernel/module source; semantic safety admission is bypassed. This campaign keeps its own frozen input identities.','',
          '| Workload | Valid/planned | State | Table and chart |','| --- | ---: | --- | --- |']
    for item in progress:
        name=item['workload']; ready=(PUBLIC/name/'README.md').exists()
        rows.append(f"| {name} | {item.get('measured',0)}/63 | {item['state']} | "+(f'[Results]({name}/README.md)' if ready else 'Pending')+' |')
    rows+=['','[Command plan](plan.json) · [Progress receipts](progress.json)','']
    (PUBLIC/'README.md').write_text('\n'.join(rows))
    save(PUBLIC/'progress.json',progress)


def completed_record(row):
    """Keep an explicit drained missing-body failure without accepting its rate."""
    if row.get('drained') is not True or row.get('cleanup_error'):
        return False
    if row.get('execution_status') == 'OK':
        return True
    measurement = row.get('measurement', {})
    return (row.get('execution_status') == 'NO_JIT' and row.get('arm') == 'kdlock'
            and row.get('jit_acceptance') == 'NO_JIT'
            and row.get('jit_bodies') == row.get('jit_completions') == 0
            and measurement.get('complete') is True and measurement.get('data_ok') is True)


def select_campaign(name):
    """Keep changed translation generations in separate immutable campaigns."""
    if not re.fullmatch(r'catalog-linux70-[a-z0-9][a-z0-9-]{0,64}', name):
        raise ValueError('Invalid Linux 7 campaign name')
    global CAMPAIGN, GUEST, RAW, PUBLIC
    CAMPAIGN = name
    GUEST = '/root/kdlock-evidence/10.176.26.71/bench/' + name
    RAW = ROOT/'bench/results/10.176.26.71/raw/bench'/name
    PUBLIC = ROOT/'bench/results/10.176.26.71/bench'/name


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only',nargs='+')
    parser.add_argument('--campaign',default=CAMPAIGN,
                        help='Separate evidence directory for this source generation')
    args=parser.parse_args()
    select_campaign(args.campaign)
    if not RAW.exists():RAW.mkdir(parents=True)
    PUBLIC.mkdir(parents=True,exist_ok=True)
    plan=[dict(workload=n,argv=a) for n,a in commands(GUEST)]
    if len(plan)!=52 or len({p['workload'] for p in plan})!=52:raise ValueError('Catalog coverage differs')
    selected=set(args.only or [p['workload'] for p in plan])
    if not selected<={p['workload'] for p in plan}:raise ValueError('Unknown workload')
    for path in (RAW/'plan.json',PUBLIC/'plan.json'):
        if path.exists() and json.loads(path.read_text())!=plan:raise ValueError('Frozen command plan differs')
        if not path.exists():save(path,plan)
    progress_path=RAW/'progress.json'
    progress=json.loads(progress_path.read_text()) if progress_path.exists() else []
    os.environ.setdefault('MPLCONFIGDIR','/tmp/kdlock-linux70-matplotlib')
    with (RAW/'owner.lock').open('a') as owner:
        fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        controls={str(path.relative_to(ROOT)):sha(path) for path in
                  (Path(__file__),HERE/'current_plan.py',HERE/'plan.py',
                   HERE/'report.py',HERE/'frequency_monitor.py')}
        control_dir=RAW/('orchestration-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        control_dir.mkdir()
        for name in controls:
            target=control_dir/Path(name).name
            target.write_bytes((ROOT/name).read_bytes())
            if sha(target)!=controls[name]:raise RuntimeError('Controller changed during capture')
        provenance=dict(files=controls,translation_policy='trusted-kernel-and-module-source',source_commit=subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            source_worktree_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
            scope='Controller bytes; each workload separately freezes and hashes its actual guest inputs')
        save(control_dir/'provenance.json',provenance)
        save(PUBLIC/'orchestration.json',provenance)
        if not (RAW/'initial-health.stdout').exists():health('initial-health')
        if not (RAW/'host-reference.stdout').exists():capture('host-reference')
        reference=json.loads((RAW/'host-reference.stdout').read_text())
        for item in plan:
            name=item['workload']
            if name not in selected:continue
            previous=next((r for r in progress if r['workload']==name),None)
            if previous:
                if previous['state'] not in ('COMPLETE','COMPLETE_WITH_FAILURES'):
                    raise RuntimeError('Prior attempt requires explicit diagnosis, no automatic retry')
                continue
            if (RAW/'STOP').exists():raise RuntimeError('STOP requested at drained workload boundary')
            row=dict(workload=name,state='PREFLIGHT',started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            row['orchestration']=str(control_dir.relative_to(RAW))
            progress.append(row);save(progress_path,progress);publish(progress)
            monitor=None
            try:
                health(name+'-before-health')
                before=capture(name+'-before-host')
                problems=compare(reference,before)
                if problems:raise RuntimeError('; '.join(problems))
                monitor=monitor_start(name)
                row['state']='RUNNING';save(progress_path,progress);publish(progress)
                print('START '+name,flush=True)
                argv=['/root/host_fs/kdlock/'+item['argv'][0],*item['argv'][1:]]
                # The runner first verifies the full permitted worker mask;
                # its client pins the collector and every worker explicitly.
                receipt=remote(name,[*ENV,PYTHON,*argv],seconds=3500,allowed=(0,1))
                health(name+'-after-health')
                after=capture(name+'-after-host')
                problems=compare(reference,after)
                if problems:raise RuntimeError('; '.join(problems))
                monitor_stop(name,monitor);monitor=None
                files=preserve(name)
                records=json.loads((RAW/name/'records.json').read_text())
                rows=render(RAW/name,PUBLIC/name,name,False,exploratory=True)
                row['measured']=sum(r['whole_mops_s'] is not None for r in rows)
                save(progress_path,progress);publish(progress)
                if len(records)!=63 or any(not completed_record(r) for r in records):
                    raise RuntimeError('Incomplete coordinates, unsafe failure or missing drain')
                measured=sum(r.get('execution_status')=='OK' for r in records)
                if receipt['returncode']:
                    failure=json.loads((RAW/name/'failure.json').read_text())
                    rejected={r['name'] for r in records if r['execution_status']=='NO_JIT'}
                    if (receipt['returncode']!=1 or not rejected or
                            failure.get('status')!='NO_JIT' or
                            set(failure.get('sessions',[]))!=rejected):
                        raise RuntimeError('Unexpected final runner failure; session rates do not override it')
                if sum(r['whole_mops_s'] is not None for r in rows)!=measured:
                    raise RuntimeError('Invalid rate/data receipt')
                save(PUBLIC/name/'preservation.json',json.loads((RAW/(name+'-preservation.json')).read_text()))
                row.update(state='COMPLETE' if measured==63 else 'COMPLETE_WITH_FAILURES',
                           measured=measured,failed_points=63-measured,files_preserved=files,
                           returncode=receipt['returncode'],strict_timing_qualified=False,
                           finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
                save(progress_path,progress);publish(progress)
                print('TABLE_READY '+name+' '+str(PUBLIC/name/'README.md'),flush=True)
            except BaseException as error:
                row.update(state='STOPPED',error=repr(error),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
                save(progress_path,progress);publish(progress)
                # Stopping telemetry does not assert guest workload completion.
                if monitor is not None and monitor[0].poll() is None:
                    try:monitor_stop(name,monitor)
                    except Exception as monitor_error:row['monitor_error']=repr(monitor_error);save(progress_path,progress)
                raise
        health('selected-final-health-'+str(len(progress)))
    print('ALL_SELECTED_WORKLOADS_COMPLETE',flush=True)


if __name__=='__main__':
    main()
