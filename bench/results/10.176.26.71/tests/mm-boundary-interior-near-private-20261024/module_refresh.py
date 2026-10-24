#!/usr/bin/env python3
"""Freeze and transport the module-only correction from the source host."""
import io,json,runpy,shlex,subprocess,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mm-boundary-interior-near-private-20261024'
BASE='/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-near-private-20261024'
CONTROL=BASE+'/control-r3'
C=runpy.run_path(str(HERE.parent/'serial-continuation-20261022/campaign.py'))
SYNC=runpy.run_path(str(ROOT/'tools/vm/sync_source.py'))
def main():
    out=RAW/'module-refresh-1';assert (out/'capacity.json').is_file() and not (out/'inputs.json').exists()
    h=C['capture'](out/'host.json');assert h['pins_verified'] and h['snapshot_listed']
    names=set(C['load'](RAW/'revise-1/inputs.json')['files'])
    names.update(str(p.relative_to(ROOT)) for p in HERE.glob('*.py'))
    files={n:C['sha'](ROOT/n) for n in sorted(names)}
    inputs=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),files=files)
    C['save'](out/'inputs.json',inputs)
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','2222','root@10.176.26.71',
        'env PYTHONDONTWRITEBYTECODE=1 python3 -c '+shlex.quote(SYNC['REMOTE_CODE'])]
    C['command'](ssh,out/'sync-before.json',120,(json.dumps(dict(operation='inspect',manifest=files))+'\n').encode())
    before=C['load'](out/'sync-before.json');assert before['idle'] and before['fstype']=='ext4'
    changed=[n for n in files if before['hashes'][n]!=files[n]]
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w') as tar:
        for n in changed:tar.add(ROOT/n,arcname=n,recursive=False)
    header=dict(operation='copy',manifest=files,changed=changed,previous={n:before['hashes'][n] for n in changed})
    C['command'](ssh,out/'sync-after.json',180,(json.dumps(header)+'\n').encode()+archive.getvalue())
    after=C['load'](out/'sync-after.json');assert after['idle'] and after['hashes']==files
    C['guest']('mkdir -- '+CONTROL,out/'mkdir.log',30)
    C['copy_in']([out/'inputs.json',HERE/'refresh_modules.py',HERE/'focus.py',HERE/'transition.py',HERE/'hydrate.py'],CONTROL+'/',out/'copy.log')
    receipt=C['load'](RAW/'identity-r2/receipt.json');image=Path(receipt['host_path'])
    assert C['sha'](image)==receipt['compressed_sha256'] and image.stat().st_size==receipt['compressed_bytes']
    C['copy_in']([image],receipt['compressed_path'],out/'copy-ram-identity.log')
    C['guest']('unshare --mount --propagation private '+C['remote']([CONTROL+'/refresh_modules.py']),out/'refresh.log',1800)
    build=RAW/'build-3';build.mkdir()
    C['fetch'](BASE+'/build-3/result.json',build/'result.json')
    print(json.dumps(dict(passed=True,reused_kernel=True)))
if __name__=='__main__':main()
