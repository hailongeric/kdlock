#!/usr/bin/env python3
"""Wait locally, capture one endpoint, archive once, fetch and verify bytes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode=True
COMMIT='f7a84065e84474380faa37eeadfdf534abd72a68'
BOOT='2e0ea0fa-ff34-4416-9175-b4b0ede3f63b'
NAME='kdscope1-api-f7a84065-20261030'
REMOTE='/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests'
MEASURE=Path('/tmp/kdlock-scope-f7-native-a-api-measure-20261030')
OUT=Path('/tmp/kdlock-scope-f7-api-preserve-20261030')
RAW=Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests')/NAME
MANIFEST=Path('/tmp/kdlock-scope-f7-native-a-argv-r2-20261030.json')
MANIFEST_SHA='1e549b91ba64c9b86a28d7bc383ab858d204d09a8efd3386ae9c8f8318d0fe40'
GUEST_HELPER=Path('/tmp/kdlock-scope-f7-api-archive-20261030.py')
GUEST_HELPER_SHA='46134b0aaf87b6e928ad475dfd7c071719b9d28404e5844d2f26a9040399eae3'
CORE=Path('/tmp/kdlock-nano-f7a84065-analysis-prep-20261030/nano_core.py')
CORE_SHA='1bbd6e010c27c42f5293a3df09660342e453d49663d9452e3c1d02269116c3a7'
HOST_VERIFY='/tmp/kdlock-qemu-pool64-native-a-api-endpoint-20261030'
HOST_AFTER='/tmp/kdlock-scope-f7-api-host-after-20261030.json'
ENDPOINT_RESULT='/tmp/kdlock-scope-f7-api-endpoint-policy-20261030.json'

def require(v,m):
    if not v:raise RuntimeError(m)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def load(p):return json.loads(Path(p).read_text())

def save(p,v):
    t=p.with_name('.'+p.name+'.tmp')
    with t.open('w') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n');f.flush()
    t.replace(p)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wait-seconds',type=int,default=18000)
    a=p.parse_args();require(1<=a.wait_seconds<=21600,'bounded local wait required')
    require(sha(MANIFEST)==MANIFEST_SHA and sha(GUEST_HELPER)==GUEST_HELPER_SHA and sha(CORE)==CORE_SHA,'prepared source changed')
    require(not OUT.exists() and not RAW.exists(),'fresh source-host evidence/raw output required')
    OUT.mkdir();m=load(MANIFEST);shutil.copyfile(__file__,OUT/'controller.py')
    owner=dict(schema=1,completed=False,state='WAITING_LOCAL_MEASURE',source_commit=COMMIT,boot_id=BOOT,
               script_sha256=sha(Path(__file__)),manifest_sha256=MANIFEST_SHA,started=time.time(),
               remote_started=False,guest_archive_started=False,drain_unknown=False,performance_accepted=False,calls=[])
    child=None
    def persist():save(OUT/'owner.json',owner)
    def interrupted(signum,frame):raise InterruptedError('preservation interrupted; child untouched')
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
    persist()
    def call(label,argv,seconds=90,input_path=None,output=None):
        nonlocal child
        output=output or OUT/(label+'.stdout');error=OUT/(label+'.stderr')
        row=dict(label=label,argv=argv,started=time.time());owner['calls'].append(row);persist()
        incoming=input_path.open('rb') if input_path else None
        try:
            with output.open('xb') as out,error.open('xb') as err:
                child=subprocess.Popen(argv,stdin=incoming or subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
                row['pid']=child.pid;persist();code=child.wait(timeout=seconds)
            row.update(returncode=code,finished=time.time(),stdout_sha256=sha(output),stderr_sha256=sha(error));persist()
            require(code==0,label+' failed; preserve all evidence');child=None;return output
        finally:
            if incoming:incoming.close()
    ssh=m['transport']['physical_qemu_host_ssh_prefix'];wrapper=m['transport']['physical_qemu_host_vm_wrapper']
    def host(label,argv,**kw):return call(label,[*ssh,shlex.join(argv)],**kw)
    def guest(label,argv,**kw):return host(label,[wrapper,shlex.join(argv)],**kw)
    def upload(label,src,dest,identical=False):
        code=('import pathlib,hashlib,sys;p=pathlib.Path(sys.argv[1]);b=sys.stdin.buffer.read();'
              'assert hashlib.sha256(b).hexdigest()==sys.argv[2];assert not p.is_symlink();'
              'same=p.exists();assert not same or (sys.argv[3]=="1" and p.read_bytes()==b);'
              'f=None if same else p.open("xb");None if same else f.write(b);None if same else f.close();'
              'assert p.read_bytes()==b')
        guest(label,['python3','-c',code,str(dest),sha(src),'1' if identical else '0'],input_path=src)
    try:
        deadline=time.monotonic()+a.wait_seconds
        while True:
            if (MEASURE/'owner.json').is_file():
                local=load(MEASURE/'owner.json')
                require(local.get('state')!='FAILED','local measure transport FAILED')
                if local.get('state')=='COMPLETE' and local.get('completed') is True:break
            require(time.monotonic()<deadline,'local measurement wait expired; no remote action started')
            time.sleep(min(10,max(.01,deadline-time.monotonic())))
        require(local.get('action')=='native-a-api-measure' and local.get('source_commit')==COMMIT and
                local.get('guest_drain_unknown') is False and local.get('observed_boot_id')==BOOT,'local measure completion differs')
        actual=MEASURE/'guest-result.json';require(sha(actual)==local['guest_result_sha256'],'retained actual measure receipt changed')
        measure=load(actual)
        require(measure.get('state')=='COMPLETE' and measure.get('completed') is True and
                measure.get('final_idle') is True and measure.get('completion_checks_passed') is True and
                measure.get('drain_unknown') is False and measure.get('child_returncode')==0 and
                measure.get('source_commit')==COMMIT and measure.get('boot_id')==BOOT and
                measure.get('planned_points')==126 and measure.get('rounds_per_point')==1,'actual measure incomplete')
        shutil.copyfile(MEASURE/'owner.json',OUT/'measure-transport-owner.json');shutil.copyfile(actual,OUT/'measure-owner.json')
        owner.update(state='ENDPOINT',remote_started=True,measure_owner_sha256=sha(actual));persist()
        fetched=guest('actual-measure-owner',['cat',REMOTE+'/'+NAME+'/measure-control/owner.json'])
        require(sha(fetched)==sha(actual),'guest actual measure receipt differs')
        fresh=m['fresh_host_for_every_action']
        argv=[x.replace('${SELECTED_ACTION_QEMU_HOST_VERIFY_OUTPUT}',HOST_VERIFY) for x in fresh['host_verify_argv']]
        host('endpoint-verify',argv,seconds=fresh['transport_wait_seconds'])
        policy_path=host('endpoint-policy',['cat',HOST_VERIFY+'/result.json']);policy=load(policy_path)
        require(all(policy.get(k)==v for k,v in fresh['expected'].items()),'endpoint pool verification failed')
        require(policy.get('controller_sha256')=='cf8176070d7717febbf987df0accfda2bb6f1b88a53f3a03233f8ea06fc6c8ea' and
                policy.get('capture_helper_sha256')=='e9417457c4d33eea2a84f70af0ed2839ce5b07abbd4dd70bb84ea66fdaf9bb74','endpoint tool identity differs')
        for label in ('before','after'):
            row=policy['captures'][label]
            require(row['path']==HOST_VERIFY+'/'+label+'.host.json','endpoint capture path differs')
            captured=host('endpoint-'+label,['cat',row['path']]);require(sha(captured)==row['sha256'],'endpoint capture differs')
        ref=host('host-reference',['cat',fresh['reference']['qemu_host_path']])
        require(sha(ref)==fresh['reference']['sha256'],'fixed131-task reference differs')
        upload('upload-archive-helper',GUEST_HELPER,GUEST_HELPER,True)
        upload('upload-endpoint',OUT/'endpoint-after.stdout',HOST_AFTER)
        upload('upload-policy',policy_path,ENDPOINT_RESULT)
        upload('verify-reference',ref,fresh['reference']['guest_path'],True)
        owner.update(state='ARCHIVING',guest_archive_started=True,drain_unknown=True,
                     endpoint_policy_sha256=sha(policy_path),host_after_sha256=sha(OUT/'endpoint-after.stdout'));persist()
        argv=['env','PYTHONDONTWRITEBYTECODE=1',
              '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3',str(GUEST_HELPER),
              '--measure-owner-sha256',sha(actual),'--host-after',HOST_AFTER,
              '--host-after-sha256',owner['host_after_sha256'],'--endpoint-result',ENDPOINT_RESULT,
              '--endpoint-result-sha256',owner['endpoint_policy_sha256']]
        guest('archive',argv,seconds=3900)
        receipt_path=guest('archive-owner',['cat',REMOTE+'/'+NAME+'-archive-control/owner.json']);receipt=load(receipt_path)
        archive_path=guest('archives',['cat',REMOTE+'/'+NAME+'-archives/archives.json']);archives=load(archive_path)
        require(receipt.get('completed') is True and receipt.get('state')=='COMPLETE' and receipt.get('idle') is True and
                receipt.get('drain_unknown') is False and receipt.get('returncode')==0 and
                receipt.get('source_commit')==COMMIT and receipt.get('boot_id')==BOOT and
                receipt.get('script_sha256')==GUEST_HELPER_SHA and receipt.get('archives_sha256')==sha(archive_path) and
                receipt.get('measure_owner_sha256')==sha(actual),'guest archive not completed/drained')
        require(archives.get('completed') is True and archives.get('guest_idle') is True and archives.get('boot_id')==BOOT,'maintained archives incomplete')
        owner.update(state='FETCHING',drain_unknown=False,archive_owner_sha256=sha(receipt_path),archives_sha256=sha(archive_path));persist()
        require(shutil.disk_usage(RAW.parent).free>2*sum(r['bytes'] for r in archives['groups'])+1024**3,'insufficient source-host raw space')
        RAW.mkdir()
        fetch='''import hashlib,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);name=sys.argv[2];expected=sys.argv[3:]
paths=[root/(name+'-archive-control')/'owner.json',root/(name+'-archives')/'archives.json']
def check():
 assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in zip(paths,expected))
check();rc=subprocess.call(['tar','-C',str(root),'-cf','-',name+'-archives',name+'-archive-control']);assert rc==0;check()
'''
        transport=guest('fetch',['python3','-c',fetch,REMOTE,NAME,sha(receipt_path),sha(archive_path)],seconds=1800,output=RAW/'transport.tar')
        allowed={NAME+'-archives',NAME+'-archive-control'}
        with tarfile.open(transport,'r:') as tar:
            for row in tar:
                path=PurePosixPath(row.name.rstrip('/'))
                require(not path.is_absolute() and '..' not in path.parts and path.parts[0] in allowed,'unexpected transport member')
                dest=RAW/path
                if row.isdir():dest.mkdir(parents=True,exist_ok=True);continue
                require(row.isfile() and not dest.exists(),'unexpected/duplicate transport type')
                dest.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(row) as src,dest.open('xb') as dst:shutil.copyfileobj(src,dst)
                require(dest.stat().st_size==row.size,'truncated transport file')
        require(sha(RAW/(NAME+'-archive-control')/'owner.json')==sha(receipt_path) and
                sha(RAW/(NAME+'-archives')/'archives.json')==sha(archive_path),'fetched receipt differs')
        require(sha(CORE)==CORE_SHA,'offline reader changed')
        spec=importlib.util.spec_from_file_location('reviewed_archive_bytes',CORE);core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
        cache=RAW/'receipt-cache';cache.mkdir();parsed=core.Archive(RAW/(NAME+'-archives'),cache)
        require(parsed.meta['guest_base']==REMOTE+'/'+NAME and
                parsed.hashes['measure-control/owner.json']==sha(actual) and
                parsed.hashes['host-after.json']==owner['host_after_sha256'],'archived campaign/owner/endpoint differs')
        save(RAW/'member-sha256.json',parsed.hashes);save(RAW/'archive-provenance.json',parsed.provenance)
        transfer=dict(completed=True,source_commit=COMMIT,boot_id=BOOT,transport_sha256=sha(transport),
            archives_sha256=sha(archive_path),archive_owner_sha256=sha(receipt_path),
            regular_members=len(parsed.hashes),member_sha256_manifest=sha(RAW/'member-sha256.json'),
            offline_reader_sha256=CORE_SHA,performance_accepted=False,analysis_pending=True)
        save(RAW/'transfer.json',transfer)
        owner.update(completed=True,state='COMPLETE',drain_unknown=False,finished=time.time(),
                     raw=str(RAW),transfer_sha256=sha(RAW/'transfer.json'),analysis_pending=True)
    except BaseException as error:
        owner.update(state='FAILED',error=repr(error),finished=time.time())
        if child is not None:owner.update(last_child_returncode=child.poll(),transport_completion_unknown=child.poll() is None)
        if owner['guest_archive_started'] and owner['state']!='COMPLETE':owner['drain_unknown']=True
        raise
    finally:persist()
    print(json.dumps(owner,sort_keys=True))

if __name__=='__main__':main()
