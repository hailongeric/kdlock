#!/usr/bin/env python3
"""Source-host transport and serial transitions; no tests execute on this host."""
import argparse
import io
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mm-boundary-resident-20261023'
BASE='/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-resident-20261023'
C=runpy.run_path(str(HERE.parent/'serial-continuation-20261022/campaign.py'))
SYNC=runpy.run_path(str(ROOT/'tools/vm/sync_source.py'))
CONTROL=BASE+'/control'
C['boot'].__globals__['PRIOR']=CONTROL


def boot(mode,block,output):
    # The candidate identity is durable on the source host, not guest root.
    # Restore only its RAM transport after a changed boot and before verification.
    receipt=C['load'](RAW/'identity/receipt.json')
    image=Path(receipt['host_path'])
    assert receipt['passed'] and image.stat().st_size==receipt['compressed_bytes'] and C['sha'](image)==receipt['compressed_sha256']
    original_guest=C['boot'].__globals__['guest']
    def guest_with_identity(command,log,timeout=900,allow_failure=False):
        if mode!='recovery' and CONTROL+'/transition.py verify ' in command:
            C['copy_in']([image],receipt['compressed_path'],output/'copy-ram-identity.log')
        return original_guest(command,log,timeout,allow_failure)
    C['boot'].__globals__['guest']=guest_with_identity
    try:return C['boot'](mode,block,output)
    finally:C['boot'].__globals__['guest']=original_guest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','build','kd','run','recovery','collect'))
    p.add_argument('--attempt',type=int,default=1)
    a=p.parse_args()
    local=RAW/(a.action+'-'+str(a.attempt));local.mkdir(parents=True)
    if a.action=='prepare':
        assert a.attempt==1
        C['capture'](local/'availability-host.json')
        names={'kernel_integration/mmap_lock/guest-kernel.patch','kernel_integration/mmap_lock/install.py',
               'bench/results/10.176.26.71/tests/mm-resident-partial-20261023/incremental.patch'}
        names.update('kernel_integration/mmap_lock/overlay/'+n for n in ('mm/kd_mmap_unmap.inc','include/linux/kd_mmap_lock.h','include/linux/kd_mmap_lock_types.h','kernel/locking/kd_mmap/unmap.c'))
        for folder in [HERE,*[ROOT/'tests/kernel/mmap_lock'/s for s in ('boundary_resident','resident_partial','boundary_zero','boundary_empty','boundary_edge','zero_target','unmap_body')]]:
            names.update(str(path.relative_to(ROOT)) for path in folder.rglob('*')
                         if path.is_file() and (path.suffix in ('.py','.c','.h','.inc','.patch') or path.name=='Makefile'))
        files={n:C['sha'](ROOT/n) for n in sorted(names)}
        inputs=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),files=files)
        C['save'](local/'inputs.json',inputs)
        ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','2222','root@10.176.26.71',
             'env PYTHONDONTWRITEBYTECODE=1 python3 -c '+shlex.quote(SYNC['REMOTE_CODE'])]
        C['command'](ssh,local/'sync-before.json',120,(json.dumps(dict(operation='inspect',manifest=files))+'\n').encode())
        before=json.loads((local/'sync-before.json').read_text());assert before['idle'] and before['fstype']=='ext4'
        changed=[n for n in files if before['hashes'][n]!=files[n]]
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w') as tar:
            for n in changed:tar.add(ROOT/n,arcname=n,recursive=False)
        header=dict(operation='copy',manifest=files,changed=changed,previous={n:before['hashes'][n] for n in changed})
        C['command'](ssh,local/'sync-after.json',180,(json.dumps(header)+'\n').encode()+archive.getvalue())
        after=json.loads((local/'sync-after.json').read_text());assert after['idle'] and after['hashes']==files
        C['guest']('mkdir -p -- '+CONTROL,local/'mkdir.log',30)
        C['copy_in']([local/'inputs.json',HERE/'build.py',HERE/'focus.py',HERE/'transition.py',HERE/'hydrate.py'],CONTROL+'/',local/'copy.log')
        host=C['capture'](local/'host.json');assert host['pins_verified'] and host['snapshot_listed']
        C['copy_in']([local/'host.json'],CONTROL+'/',local/'copy-host.log')
    elif a.action=='build':
        C['guest']('unshare --mount --propagation private '+C['remote']([CONTROL+'/build.py','--attempt',str(a.attempt)]),local/'build.log',2400)
        C['fetch'](BASE+'/build-'+str(a.attempt)+'/result.json',local/'result.json')
        receipt=C['fetch']('/root/kdlock-kernel-work/mm-boundary-resident-20261023/identity-store.json',local/'identity-store.json')
        identity=RAW/'identity';identity.mkdir()
        C['guest']('cat -- '+shlex.quote(receipt['compressed_path']),identity/'vmlinux.xz',180)
        assert (identity/'vmlinux.xz').stat().st_size==receipt['compressed_bytes'] and C['sha'](identity/'vmlinux.xz')==receipt['compressed_sha256']
        C['save'](identity/'receipt.json',dict(passed=True,**receipt,host_path=str(identity/'vmlinux.xz')))

    elif a.action=='run':
        host=C['capture'](local/'host.json');assert host['pins_verified'] and host['snapshot_listed']
        C['guest'](C['remote']([CONTROL+'/focus.py','--run','focused-'+str(a.attempt)]),local/'focused.log',1200)
        C['fetch'](BASE+'/focused-'+str(a.attempt)+'/result.json',local/'result.json')
    elif a.action in ('kd','recovery'):
        guest=BASE+'/'+a.action+'-'+str(a.attempt)
        C['guest']('mkdir -- '+guest,local/'mkdir.log',30)
        transition=boot(a.action,guest,local)
        if a.action=='kd':
            C['guest'](C['remote']([CONTROL+'/focus.py','--build-attempt','1','--run','focused-'+str(a.attempt)]),local/'focused.log',1200)
            C['fetch'](BASE+'/focused-'+str(a.attempt)+'/result.json',local/'result.json')
        else:C['save'](local/'result.json',transition)
    else:
        # One small transport of new logs/receipts/sources, never old archives
        # or duplicate kernel ELFs. The guest retains original probe binaries.
        script="""import json,tarfile,sys
from pathlib import Path
base=Path(BASE)
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for p in sorted(base.rglob('*')):
  if p.is_file() and not p.is_symlink() and (p.suffix in ('.json','.log','.c','.h','.py','.inc') or p.name=='Makefile'):
   tar.add(p,arcname=str(p.relative_to(base)),recursive=False)
""".replace('BASE',repr(BASE))
        C['guest'](C['PY']+" - <<'PYG'\n"+script+'\nPYG',local/'essential.tar.gz',180)
        C['save'](local/'receipt.json',dict(file='essential.tar.gz',bytes=(local/'essential.tar.gz').stat().st_size,sha256=C['sha'](local/'essential.tar.gz')))
    print(json.dumps(dict(action=a.action,passed=True)),flush=True)


if __name__=='__main__':main()
