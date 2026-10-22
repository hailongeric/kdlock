#!/usr/bin/env python3
"""Relocate selected completed evidence only after independent archival.

Both trees are compared byte-for-byte by SHA-256 before the reviewed original
inventory is removed. A symlink preserves every recorded absolute input path.
No measurement or historical campaign is changed.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

SOURCE=Path('/root/host_fs/kdlock')
BASE=Path('/mnt/kdlock-builds/nano-20261022')
DEST_ROOT=Path('/root/kdlock-evidence/10.176.26.71/bench/nano-20261022-relocated')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def inventory(base):
    paths=[base]
    def error(exc):raise exc
    for parent,dirs,files in os.walk(base,followlinks=False,onerror=error):
        paths.extend(Path(parent)/name for name in dirs+files)
    result={}
    for path in paths:
        info=path.lstat()
        row=dict(mode=info.st_mode,uid=info.st_uid,gid=info.st_gid,mtime_ns=info.st_mtime_ns)
        if stat.S_ISREG(info.st_mode):row.update(bytes=info.st_size,sha256=sha(path))
        elif stat.S_ISLNK(info.st_mode):row['link']=os.readlink(path)
        else:assert stat.S_ISDIR(info.st_mode),str(path)
        result[str(path.relative_to(base))]=row
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verification',type=Path,required=True)
    p.add_argument('--block',choices=('rwlock','mutex-cacheline'),required=True)
    a=p.parse_args();dest=DEST_ROOT/a.block
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(SOURCE/'bench'),str(SOURCE/'bench/spin_cacheline')]
    from bench_runtime import idle as common_idle
    from archive_run import idle
    with open('/run/lock/kdlock-nano.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        idle(BASE,common_idle)
        assert (BASE/'continuation/owner-finished.json').is_file()
        assert json.loads((BASE/'continuation/storage-stop.json').read_text())['block']=='rwsem'
        prior=json.loads((BASE/'continuation/status.json').read_text())
        assert next(r for r in prior if r['block']==a.block)['returncode']==0
        archives=BASE.with_name(BASE.name+'-archives-checkpoint')
        receipt=json.loads((archives/'archives.json').read_text())
        verification=json.loads(a.verification.read_text())
        assert receipt['completed'] and verification['completed']
        group=next(r for r in receipt['groups'] if r['group']==a.block)
        independent=next(r for r in verification['verified_archives'] if r['file']==group['file'])
        assert independent['sha256']==group['sha256']==sha(archives/group['file'])
        old=BASE/a.block
        record_path=BASE/('relocation-'+a.block+'.json')
        assert old.is_dir() and not old.is_symlink() and not dest.exists() and not dest.is_symlink()
        assert not DEST_ROOT.is_symlink() and not record_path.exists()
        before=inventory(old)
        manifest=BASE/('relocation-inventory-'+a.block+'.json')
        manifest.write_text(json.dumps(before,sort_keys=True)+'\n')
        record=dict(started=time.time(),original=str(old),destination=str(dest),
            independent_verification=str(a.verification),verification_sha256=sha(a.verification),
            archive_sha256=group['sha256'],inventory_sha256=sha(manifest),paths=len(before),
            completed=False,scope='Completed evidence moved across existing guest filesystems; recorded absolute paths preserved by symlink.')
        def save(): record_path.write_text(json.dumps(record,indent=2)+'\n')
        save();DEST_ROOT.mkdir(parents=True,exist_ok=True)
        subprocess.run(['cp','-a','--',str(old),str(DEST_ROOT)],check=True,timeout=300)
        assert inventory(dest)==before,'destination copy differs; originals retained'
        assert inventory(old)==before,'original changed; both copies retained'
        idle(BASE,common_idle)
        record['copy_verified']=True;save()
        # Delete only this immutable inventory, after archive and copy checks.
        for name in sorted((n for n in before if n!='.'),key=lambda n:(len(Path(n).parts),n),reverse=True):
            path=old/name
            if stat.S_ISDIR(before[name]['mode']):path.rmdir()
            else:path.unlink()
        old.rmdir();old.symlink_to(dest,target_is_directory=True)
        assert old.resolve()==dest and inventory(old.resolve())==before
        idle(BASE,common_idle)
        record.update(completed=True,finished=time.time(),link_target=os.readlink(old));save()
        print(json.dumps(record))

if __name__=='__main__':main()
