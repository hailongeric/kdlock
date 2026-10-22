#!/usr/bin/env python3
"""Freeze only approved MM build inputs; use the maintained guarded VM copier."""
import hashlib
import io
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
RAW = ROOT / 'bench/results/10.176.26.71/raw/tests/mm-populated-unmap-20261022/build-1'
BASE = '/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022'
C = runpy.run_path(str(HERE.parent/'serial-continuation-20261022/campaign.py'))
SYNC = runpy.run_path(str(ROOT/'tools/vm/sync_source.py'))


def main():
    RAW.mkdir()
    previous = json.loads((HERE.parent/'mm-unmap-body-20261022/test-inputs.json').read_text())
    names = {n for n in previous['files'] if not n.endswith('.md')}
    names.update(['bench/archive_run.py',
        'kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/unmap.c',
        'kernel_integration/mmap_lock/overlay/mm/kd_mmap_unmap.inc'])
    manifest = {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    inputs = dict(commit=commit,files=manifest)
    C['save'](RAW/'source-inputs.json',inputs)
    C['save'](HERE/'source-inputs.json',inputs)
    (RAW/'git-status.txt').write_text(subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True))
    ssh = ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','2222','root@10.176.26.71',
           'env PYTHONDONTWRITEBYTECODE=1 python3 -c '+shlex.quote(SYNC['REMOTE_CODE'])]
    header = dict(operation='inspect',manifest=manifest)
    C['command'](ssh,RAW/'sync-before.json',120,(json.dumps(header)+'\n').encode())
    before = json.loads((RAW/'sync-before.json').read_text())
    assert before['idle'] and before['fstype']=='ext4'
    changed = [n for n in manifest if before['hashes'][n]!=manifest[n]]
    C['save'](RAW/'changed.json',changed)
    if changed:
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w') as tar:
            for n in changed:tar.add(ROOT/n,arcname=n,recursive=False)
        (RAW/'changed-inputs.tar').write_bytes(archive.getvalue())
        assert SYNC['host_hashes'](ROOT,manifest)==manifest
        header = dict(operation='copy',manifest=manifest,changed=changed,
                      previous={n:before['hashes'][n] for n in changed})
        C['command'](ssh,RAW/'sync-after.json',180,(json.dumps(header)+'\n').encode()+archive.getvalue())
        after=json.loads((RAW/'sync-after.json').read_text())
        assert after['hashes']==manifest and after['copied']==len(changed) and after['idle']
    host=C['capture'](RAW/'host.json')
    assert host['pins_verified'] and host['snapshot_listed'] and len(host['qemu'])==1
    C['guest']('mkdir -p '+BASE+' && mkdir '+BASE+'/build-control-1',RAW/'mkdir.log',30)
    C['copy_in']([HERE/'build.py',HERE/'module-targets.json',RAW/'source-inputs.json',RAW/'host.json'],
                 BASE+'/build-control-1/',RAW/'control-copy.log')
    C['guest'](C['PY']+' '+BASE+'/build-control-1/build.py',RAW/'build.log',7200)
    result=C['fetch'](BASE+'/build-control-1/build-result.json',RAW/'build-result.json')
    assert result['passed'] and result['state']=='COMPLETE' and not result['installed'] and not result['booted']
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
