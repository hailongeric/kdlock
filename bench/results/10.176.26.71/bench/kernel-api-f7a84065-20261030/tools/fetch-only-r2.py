#!/usr/bin/env python3
"""Fetch and verify an already completed API archive; never recapture it."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
COMMIT = 'f7a84065e84474380faa37eeadfdf534abd72a68'
BOOT = '2e0ea0fa-ff34-4416-9175-b4b0ede3f63b'
NAME = 'kdscope1-api-f7a84065-20261030'
REMOTE = '/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests'
PRIOR = Path('/tmp/kdlock-scope-f7-api-preserve-20261030')
PRIOR_SHA = 'c08c0e9bf1c0ac8d252995b7739e01daf670d8ee482b92b34995f653f8181d8d'
OUT = Path('/tmp/kdlock-scope-f7-api-fetch-only-r2-20261030')
RAW = Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests') / NAME
MANIFEST = Path('/tmp/kdlock-scope-f7-native-a-argv-r2-20261030.json')
MANIFEST_SHA = '1e549b91ba64c9b86a28d7bc383ab858d204d09a8efd3386ae9c8f8318d0fe40'
CORE = Path('/tmp/kdlock-nano-f7a84065-analysis-prep-20261030/nano_core.py')
CORE_SHA = '1bbd6e010c27c42f5293a3df09660342e453d49663d9452e3c1d02269116c3a7'
ARCHIVE_OWNER_SHA = 'faadffedd8a15b776d392c1549b272148f512977b32f0a07daf96284d98c0c2a'
ARCHIVES_SHA = '6d4323fadc413522020631d937d1e259800591ededc46aa186259065ee0a4c4c'
INVENTORY_SHA = 'c7f14cbabf6d17e3a082ed740f9c41d31767c8733e42df33eae3cca8ff365104'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


# All remote operations are reads. The completed receipts are rechecked around
# the transfer; no current-boot/endpoint operation replaces historical evidence.
REMOTE_READ = r'''import hashlib,json,pathlib,stat,subprocess,sys
root=pathlib.Path(sys.argv[1]);name=sys.argv[2];mode=sys.argv[3]
expected=sys.argv[4:7]
paths=[root/(name+'-archive-control')/'owner.json',root/(name+'-archives')/'archives.json',root/(name+'-archives')/'input-inventory.json']
def check():
 assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in zip(paths,expected))
def inventory():
 rows=[]
 for top in (name+'-archives',name+'-archive-control'):
  parent=root/top
  for p in [parent,*sorted(parent.rglob('*'))]:
   s=p.lstat();rel=p.relative_to(root).as_posix()
   assert stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)
   assert len((rel+('/' if stat.S_ISDIR(s.st_mode) else '')).encode())<=100
   rows.append(dict(path=rel,bytes=s.st_size if stat.S_ISREG(s.st_mode) else 0,directory=stat.S_ISDIR(s.st_mode),mtime_ns=s.st_mtime_ns,mode=s.st_mode))
 return rows
check()
if mode=='input':
 sys.stdout.buffer.write(paths[2].read_bytes());check()
elif mode=='plan':
 print(json.dumps(inventory(),sort_keys=True));check()
elif mode=='fetch':
 rows=inventory();actual=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest();assert actual==sys.argv[7]
 rc=subprocess.call(['tar','--format=ustar','--blocking-factor=1','--hard-dereference','-C',str(root),'-cf','-',name+'-archives',name+'-archive-control']);assert rc==0
 check();assert inventory()==rows
else:raise AssertionError(mode)
'''


def main():
    require(sha(MANIFEST) == MANIFEST_SHA and sha(CORE) == CORE_SHA, 'prepared source changed')
    require(sha(PRIOR/'owner.json') == PRIOR_SHA, 'original failed owner changed')
    prior = load(PRIOR/'owner.json')
    require(prior.get('state') == 'FAILED' and prior.get('completed') is False and
            prior.get('error') == "RuntimeError('insufficient source-host raw space')" and
            prior.get('script_sha256') == '4bd53fd947ddca246b3dae7a5507fec223de554617744e252e31e183b5e2927a',
            'not the retained space-only failure')
    require(sha(PRIOR/'archive-owner.stdout') == ARCHIVE_OWNER_SHA and
            sha(PRIOR/'archives.stdout') == ARCHIVES_SHA, 'retained archive receipts changed')
    receipt = load(PRIOR/'archive-owner.stdout'); archives = load(PRIOR/'archives.stdout')
    require(receipt.get('completed') is True and receipt.get('state') == 'COMPLETE' and
            receipt.get('idle') is True and receipt.get('drain_unknown') is False and receipt.get('returncode') == 0 and
            receipt.get('source_commit') == COMMIT and receipt.get('boot_id') == BOOT and
            receipt.get('archives_sha256') == ARCHIVES_SHA and receipt.get('measure_owner_sha256') == prior['measure_owner_sha256'],
            'archive is not completed/drained for this measurement')
    require(archives.get('completed') is True and archives.get('guest_idle') is True and archives.get('boot_id') == BOOT and
            archives.get('input_inventory_sha256') == INVENTORY_SHA and
            sum(row['bytes'] for row in archives['groups']) == 40616996, 'archive identity differs')
    require(not OUT.exists() and not RAW.exists(), 'fresh evidence/raw outputs required')
    OUT.mkdir(); shutil.copyfile(__file__, OUT/'controller.py')
    for source, target in [('owner.json','prior-failed-owner.json'), ('archive-owner.stdout','archive-owner.json'), ('archives.stdout','archives.json')]:
        shutil.copyfile(PRIOR/source, OUT/target)
    owner = dict(schema=1, state='FETCH_PREPARATION', completed=False, source_commit=COMMIT, boot_id=BOOT,
                 script_sha256=sha(Path(__file__)), prior_failed_owner_sha256=PRIOR_SHA,
                 archive_owner_sha256=ARCHIVE_OWNER_SHA, archives_sha256=ARCHIVES_SHA,
                 guest_archive_completed=True, guest_archive_drained=True, remote_work='read-only byte transfer',
                 performance_accepted=False, calls=[], started=time.time())
    child = None
    def persist(): save(OUT/'owner.json', owner)
    def interrupted(signum, frame): raise InterruptedError('fetch interrupted; child untouched')
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP): signal.signal(number, interrupted)
    persist(); manifest = load(MANIFEST)
    ssh = manifest['transport']['physical_qemu_host_ssh_prefix']; wrapper = manifest['transport']['physical_qemu_host_vm_wrapper']
    def guest(label, mode, seconds=90, output=None, extra=()):
        nonlocal child
        output = output or OUT/(label+'.stdout'); error = OUT/(label+'.stderr')
        remote = ['python3','-c',REMOTE_READ,REMOTE,NAME,mode,ARCHIVE_OWNER_SHA,ARCHIVES_SHA,INVENTORY_SHA,*extra]
        argv = [*ssh, shlex.join([wrapper, shlex.join(remote)])]
        row = dict(label=label, argv=argv, started=time.time()); owner['calls'].append(row); persist()
        with output.open('xb') as out, error.open('xb') as err:
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            row['pid'] = child.pid; persist(); code = child.wait(timeout=seconds)
        row.update(returncode=code, finished=time.time(), stdout_sha256=sha(output), stderr_sha256=sha(error)); persist()
        require(code == 0, label+' failed; retain partials and original archive')
        child = None
        return output
    try:
        incoming = guest('input-inventory','input')
        require(sha(incoming) == INVENTORY_SHA, 'input inventory changed')
        inventory = load(incoming)
        plan_path = guest('transport-plan','plan'); plan = load(plan_path)
        plan_sha = hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
        block = os.statvfs(RAW.parent).f_frsize
        require(block > 0 and plan, 'filesystem allocation/transport plan unavailable')
        def rounded(size, unit): return ((size+unit-1)//unit)*unit
        keep = {name:row for name,row in inventory.items() if stat.S_ISREG(row['mode']) and
                '/source/' not in '/'+name and (name.endswith('.json') or name.endswith('/kernel.log') or name.endswith('.cmd'))}
        cache_bytes = sum(row['bytes'] for row in keep.values())
        cache_bound = sum(rounded(row['bytes'],block)+block for row in keep.values()) + block
        transport_bytes = 1024 + sum(512 + (0 if row['directory'] else rounded(row['bytes'],512)) for row in plan)
        required = 2*transport_bytes + cache_bound + 256*1024*1024
        free = shutil.disk_usage(RAW.parent).free
        owner['space_budget'] = dict(free_bytes=free, required_bytes=required, transport_bytes=transport_bytes,
            transport_copies=2, cache_files=len(keep), cache_bytes=cache_bytes, cache_allocation_bound=cache_bound,
            allocation_unit=block, headroom_bytes=256*1024*1024, input_inventory_sha256=INVENTORY_SHA, transport_plan_sha256=plan_sha)
        persist(); require(free >= required, 'insufficient calculated source-host fetch/cache space')
        RAW.mkdir(); owner['state'] = 'FETCHING'; persist()
        transport = guest('fetch','fetch',seconds=1800,output=RAW/'transport.tar',extra=(plan_sha,))
        require(transport.stat().st_size == transport_bytes, 'transport size differs from calculated USTAR plan')
        allowed = {NAME+'-archives',NAME+'-archive-control'}
        with tarfile.open(transport,'r:') as tar:
            for row in tar:
                path = PurePosixPath(row.name.rstrip('/'))
                require(not path.is_absolute() and '..' not in path.parts and path.parts[0] in allowed, 'unexpected transport member')
                dest = RAW/path
                if row.isdir(): dest.mkdir(parents=True,exist_ok=True); continue
                require(row.isfile() and not dest.exists(), 'unexpected/duplicate transport type')
                dest.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(row) as src, dest.open('xb') as dst: shutil.copyfileobj(src,dst)
                require(dest.stat().st_size == row.size, 'truncated transport file')
        require(sha(RAW/(NAME+'-archive-control')/'owner.json') == ARCHIVE_OWNER_SHA and
                sha(RAW/(NAME+'-archives')/'archives.json') == ARCHIVES_SHA and
                sha(RAW/(NAME+'-archives')/'input-inventory.json') == INVENTORY_SHA, 'fetched receipt differs')
        require(sha(CORE) == CORE_SHA, 'offline reader changed')
        spec = importlib.util.spec_from_file_location('reviewed_archive_bytes',CORE)
        core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
        cache = RAW/'receipt-cache'; cache.mkdir(); parsed = core.Archive(RAW/(NAME+'-archives'),cache)
        require(parsed.meta['guest_base'] == REMOTE+'/'+NAME and
                parsed.hashes['measure-control/owner.json'] == prior['measure_owner_sha256'] and
                parsed.hashes['host-after.json'] == prior['host_after_sha256'], 'archived campaign/owner/endpoint differs')
        save(RAW/'member-sha256.json',parsed.hashes); save(RAW/'archive-provenance.json',parsed.provenance)
        transfer = dict(completed=True, source_commit=COMMIT, boot_id=BOOT, transport_sha256=sha(transport),
            archives_sha256=ARCHIVES_SHA, archive_owner_sha256=ARCHIVE_OWNER_SHA, input_inventory_sha256=INVENTORY_SHA,
            regular_members=len(parsed.hashes), member_sha256_manifest=sha(RAW/'member-sha256.json'),
            offline_reader_sha256=CORE_SHA, prior_failed_owner_sha256=PRIOR_SHA,
            performance_accepted=False, analysis_pending=True)
        save(RAW/'transfer.json',transfer)
        owner.update(completed=True,state='COMPLETE',finished=time.time(),raw=str(RAW),
                     transfer_sha256=sha(RAW/'transfer.json'),analysis_pending=True)
    except BaseException as error:
        owner.update(state='FAILED',error=repr(error),finished=time.time())
        if child is not None:
            owner.update(last_child_returncode=child.poll(),transport_completion_unknown=child.poll() is None)
        raise
    finally: persist()
    print(json.dumps(owner,sort_keys=True))


if __name__ == '__main__': main()
