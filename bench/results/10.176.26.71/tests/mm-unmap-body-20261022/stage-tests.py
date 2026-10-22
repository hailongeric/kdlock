#!/usr/bin/env python3
"""Freeze and compile focused munmap probes, then install the preserved candidate."""
import argparse
import io
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASE = '/root/kdlock-evidence/10.176.26.71/tests/mm-unmap-body-20261022'
RAW_ROOT = ROOT / 'bench/results/10.176.26.71/raw/tests/mm-unmap-body-20261022'
TREE = '/root/kdlock-kernel-work/mm-unmap-body-20261022/candidate-1/linux'
BUNDLE = '/root/kdlock-kernel-baselines/mmap-kdmm4-20261022'
C = runpy.run_path(str(HERE.parent/'serial-continuation-20261022/campaign.py'))
SYNC = runpy.run_path(str(ROOT/'tools/vm/sync_source.py'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',type=int,required=True)
    parser.add_argument('--compile-only',action='store_true')
    a=parser.parse_args()
    assert a.attempt >= 1
    RAW=RAW_ROOT/('test-preparation-'+str(a.attempt))
    RAW.mkdir()
    prior = json.loads((HERE/'source-inputs.json').read_text())
    for name, digest in prior['files'].items():
        assert C['sha'](ROOT/name) == digest, 'frozen kernel/build input drift: ' + name
    names = set(prior['files'])
    names.update(str(p.relative_to(ROOT)) for p in (ROOT/'tests/kernel/mmap_lock/unmap_body').rglob('*') if p.is_file())
    files = {n:C['sha'](ROOT/n) for n in sorted(names)}
    inputs = dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(), files=files)
    C['save'](RAW/'source-inputs.json',inputs)
    C['save'](HERE/'test-inputs.json',inputs)
    ssh = ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','2222','root@10.176.26.71',
           'env PYTHONDONTWRITEBYTECODE=1 python3 -c '+shlex.quote(SYNC['REMOTE_CODE'])]
    C['command'](ssh,RAW/'sync-before.json',120,(json.dumps(dict(operation='inspect',manifest=files))+'\n').encode())
    before=json.loads((RAW/'sync-before.json').read_text())
    assert before['idle'] and before['fstype']=='ext4'
    changed=[n for n in files if before['hashes'][n]!=files[n]]
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w') as tar:
        for n in changed:tar.add(ROOT/n,arcname=n,recursive=False)
    (RAW/'changed-inputs.tar').write_bytes(archive.getvalue())
    assert SYNC['host_hashes'](ROOT,files)==files
    header=dict(operation='copy',manifest=files,changed=changed,previous={n:before['hashes'][n] for n in changed})
    C['command'](ssh,RAW/'sync-after.json',180,(json.dumps(header)+'\n').encode()+archive.getvalue())
    after=json.loads((RAW/'sync-after.json').read_text())
    assert after['idle'] and after['hashes']==files and after['copied']==len(changed)
    C['guest']('mkdir -p -- '+BASE+'/control',RAW/'mkdir.log',30)
    C['copy_in']([HERE/'transition.py',RAW/'source-inputs.json'],BASE+'/control/',RAW/'copy-control.log')
    # Read-only ELF inspection remains on the source host. Keep the complete
    # captured ELF, rather than inferring new offsets from an older image.
    elf=RAW_ROOT/'test-preparation-1/vmlinux'
    if a.attempt==1:
        C['command'](['scp','-o','BatchMode=yes','-o','ConnectTimeout=10','-P','2222',
                      'root@10.176.26.71:'+TREE+'/vmlinux',str(elf)],RAW/'copy-elf.log',300)
    C['fetch'](BUNDLE+'/manifest.json',RAW/'kernel-manifest.json')
    C['command'](['python3',str(HERE/'writer-sites.py'),'--elf',str(elf),
                  '--manifest',str(RAW/'kernel-manifest.json'),'--output',str(RAW/'writer-sites')],RAW/'writer-sites.log',120)
    C['copy_in']([RAW/'writer-sites/writer-sites.json'],BASE+'/control/',RAW/'copy-sites.log')
    script = '''import json,os,runpy,shutil,sys
from pathlib import Path
root=Path('/root/host_fs/kdlock');base=Path(BASE);tree=Path(TREE)
sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
assert os.uname().release in ('6.1.159-kdclobber2','6.1.159-kdmm4')
modules=sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())
expected=json.loads(Path('/root/kdlock-evidence/10.176.26.71/tests/mm-body-20261022/final-health.json').read_text())['modules']
assert modules==expected
rt.write_json(base/'control/expected-guest.json',dict(modules=modules,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
out=base/('test-build-'+str(ATTEMPT));out.mkdir()
inputs=json.loads((base/'control/source-inputs.json').read_text())
rt.write_json(out/'frozen-inputs.json',inputs)
for n,digest in inputs['files'].items():assert rt.digest(root/n)==digest,n
shutil.copytree(root/'tests/kernel/mmap_lock/unmap_body',out/'source')
command=runpy.run_path(str(base/'build-control-1/build.py'))['command']
command(['make','-C',out/'source/payload','KDIR='+str(tree),'W=1','UBSAN_SANITIZE=n'],out/'build-module.log',180)
command(['cc','-pthread','-O2','-Wall','-Wextra','-Werror','-o',out/'client',out/'source/client.c'],out/'build-client.log',120)
command([sys.executable,root/'tests/kernel/mmap_lock/unmap_body/test_receipts.py'],out/'receipts.log',60)
rt.write_json(out/'result.json',dict(passed=True,loaded=False,booted=False,source_inputs_sha256=rt.digest(base/'control/source-inputs.json')))
'''.replace('BASE',repr(BASE)).replace('TREE',repr(TREE)).replace('ATTEMPT',str(a.attempt))
    C['guest'](C['PY']+" - <<'PYG'\n"+script+'\nPYG',RAW/'test-build.log',600)
    C['fetch'](BASE+'/test-build-'+str(a.attempt)+'/result.json',RAW/'test-build-result.json')
    if a.compile_only:
        print(json.dumps(dict(passed=True,probes_compiled=True,installation_attempted=False)),flush=True)
        return
    host=C['capture'](RAW/'host-install.json')
    assert host['pins_verified'] and host['snapshot_listed']
    C['copy_in']([RAW/'host-install.json'],BASE+'/control/',RAW/'copy-host.log')
    C['guest'](C['remote'](['/root/host_fs/kdlock/kernel_integration/mmap_lock/install.py',
        '--prepared',str(Path(TREE).parent),'--baseline',BUNDLE,
        '--recovery-record',BASE+'/build-control-1/recovery','--output',BASE+'/install-1']),RAW/'install.log',900)
    result=C['fetch'](BASE+'/install-1/result.json',RAW/'install-result.json')
    assert result['passed'] and result['recovery_unchanged'] and not result['rebooted']
    print(json.dumps(dict(passed=True,probes_compiled=True,installed=True,booted=False)),flush=True)


if __name__=='__main__':main()
