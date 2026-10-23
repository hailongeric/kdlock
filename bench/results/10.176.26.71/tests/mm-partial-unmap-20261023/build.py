#!/usr/bin/env python3
"""Incremental guest-only build; freeze one candidate and reuse unchanged clients."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import sys

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-partial-unmap-20261023')
PRIOR=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-range-unmap-20261023')
STAGE=ROOT/'bench/results/10.176.26.71/tests/mm-partial-unmap-20261023'
OUT=Path('/root/kdlock-kernel-work/mm-partial-unmap-20261023')
TREE=Path('/dev/shm/kdmm7-identity')
RAM=Path('/dev/shm/kdmm7-cow')
LOWER=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
PARENT=Path('/root/kdlock-kernel-baselines/mmap-kdmm6-20261023')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm7-20261023')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
command=runpy.run_path('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/build-control-1/build.py')['command']
verify=runpy.run_path(str(ROOT/'kernel_baseline/verify.py'))['verify']

def idle():runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
def save(path,row):rt.write_json(path,row)

def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=int,default=1);a=p.parse_args()
    assert a.attempt==1 and os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    idle();inputs=json.loads((BASE/'control/inputs.json').read_text())
    for name,digest in inputs['files'].items():assert rt.digest(ROOT/name)==digest,name
    expected=json.loads((PRIOR/'final-health.json').read_text())['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
    assert verify(Path('/root/kdlock-kernel-baselines/mmap-kdmm5-20261022'),LOWER,build=True)['ok']
    parent=json.loads((PARENT/'manifest.json').read_text())
    assert shutil.disk_usage('/').free>800_000_000
    log=BASE/'build-1';log.mkdir();OUT.mkdir();TREE.mkdir();RAM.mkdir();(RAM/'upper').mkdir();(RAM/'work').mkdir()
    state=dict(passed=False,installed=False,booted=False,source_commit=inputs['commit'],parent_manifest_sha256=rt.digest(PARENT/'manifest.json'))
    save(log/'result.json',state)
    recovery=BASE/'recovery';recovery.mkdir()
    names=[p for p in Path('/boot').glob('*-6.1.159-*') if p.is_file()]
    names += [Path('/boot/grub/grub.cfg'),Path('/etc/default/grub')]
    names += [p for d in ('/etc/default/grub.d','/etc/grub.d') for p in Path(d).glob('*') if p.is_file()]
    save(recovery/'boot-sha256.json',{str(p):rt.digest(p) for p in names})
    shutil.copyfile(PRIOR/'recovery/modules-sha256.json',recovery/'modules-sha256.json')
    shutil.copyfile('/boot/grub/grub.cfg',recovery/'grub-before.cfg')
    save(BASE/'control/expected-guest.json',dict(modules=expected))
    command(['modprobe','overlay'],log/'overlay-load.log',30)
    command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',TREE],log/'mount.log',30)
    try:
        changed=['mm/mmap.c','lib/maple_tree.c','mm/kd_mmap_unmap.inc']
        command(['patch','--batch','--fuzz=0','-p1','-i',STAGE/'incremental.patch'],log/'patch.log',30,cwd=TREE)
        shutil.copyfile(ROOT/'kernel_integration/mmap_lock/overlay/mm/kd_mmap_unmap.inc',TREE/changed[2])
        config=(LOWER/'.config').read_text().replace('CONFIG_LOCALVERSION="-kdmm5"','CONFIG_LOCALVERSION="-kdmm7"')
        (TREE/'.config').write_text(config)
        command(['make','olddefconfig'],log/'config.log',120,cwd=TREE);assert (TREE/'.config').read_text()==config
        command(['make','-j16','bzImage'],log/'image.log',1800,cwd=TREE)
        targets=json.loads((ROOT/'bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/module-targets.json').read_text())
        serio='drivers/input/serio/serio_raw.ko'
        command(['make','-j16',*[n for n in targets if n!=serio]],log/'runtime-modules.log',600,cwd=TREE)
        shutil.copyfile(TREE/'Module.symvers',OUT/'runtime-Module.symvers')
        command(['make','-j1','M=drivers/input/serio','serio_raw.ko'],log/'serio.log',180,cwd=TREE)
        symbols={}
        for path in (TREE/'vmlinux.symvers',OUT/'runtime-Module.symvers',TREE/'drivers/input/serio/Module.symvers'):
            for line in path.read_text().splitlines():
                name=line.split()[1];assert name not in symbols or symbols[name]==line;symbols[name]=line
        (TREE/'Module.symvers').write_text('\n'.join(symbols[n] for n in sorted(symbols))+'\n')
        assert (TREE/'vmlinux.symvers').read_bytes()==(LOWER/'vmlinux.symvers').read_bytes()
        save(OUT/'modules-build-2.json',dict(passed=True,modules={n:rt.digest(TREE/n) for n in targets}))
        probes=BASE/'probes-1';probes.mkdir();binaries={}
        for family,module in [('populated_unmap','kd_mm_populated_test'),('body','kd_mm_body_test'),('fault_body','kd_mm_fault_test'),('unmap_body','kd_mm_unmap_test')]:
            dest=probes/family;(dest/'payload').mkdir(parents=True)
            for source in (PRIOR/'probes-1'/family).rglob('*'):
                if source.is_file() and (source.suffix in ('.c','.h','.py','.inc') or source.name=='Makefile') and not source.name.endswith('.mod.c'):
                    rel=source.relative_to(PRIOR/'probes-1'/family);dst=dest/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                    if family=='unmap_body' and rel.as_posix() in ('payload/module.c','payload/api.h'):
                        shutil.copyfile(ROOT/'tests/kernel/mmap_lock'/family/rel,dst)
                    else:dst.symlink_to(source)
            command(['make','-C',dest/'payload','KDIR='+str(TREE),'W=1','UBSAN_SANITIZE=n'],log/(family+'-module.log'),180)
            (dest/'client').symlink_to(PRIOR/'probes-1'/family/'client')
            binaries[family]={str(f.relative_to(BASE)):rt.digest(f) for f in (dest/'client',dest/'payload'/(module+'.ko'))}
        partial=probes/'partial_unmap';shutil.copytree(ROOT/'tests/kernel/mmap_lock/partial_unmap',partial,ignore=shutil.ignore_patterns('__pycache__'))
        command(['cc','-pthread','-O2','-Wall','-Wextra','-Werror','-o',partial/'client',partial/'client.c'],log/'partial-client.log',120)
        binaries['partial_unmap']={str((partial/'client').relative_to(BASE)):rt.digest(partial/'client')}
        command([sys.executable,partial/'test_receipts.py'],log/'receipts.log',60)
        command(['make','-C',ROOT/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],log/'basic.log',180)
        outputs=dict(parent['source_files'])
        for name in changed:outputs[name]=rt.digest(TREE/name)
        prepared=dict(passed=True,source_tree=str(TREE),release='6.1.159-kdmm7',outputs=outputs,config_sha256=rt.digest(TREE/'.config'),patch_sha256=rt.digest(ROOT/'kernel_integration/mmap_lock/guest-kernel.patch'))
        save(OUT/'prepare.json',prepared)
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/capture.py','--prepared',OUT,'--output',BUNDLE,'--parent',PARENT],log/'capture.log',180)
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/install.py','--prepared',OUT,'--baseline',BUNDLE,'--recovery-record',recovery,'--output',BASE/'install'],log/'install.log',600)
        manifest=json.loads((BUNDLE/'manifest.json').read_text());snapshot=OUT/'identity';snapshot.mkdir()
        for name,digest in {**manifest['source_files'],**manifest['build_files'],'.config':prepared['config_sha256']}.items():
            if name=='vmlinux':continue
            dst=snapshot/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(TREE/name,dst);assert rt.digest(dst)==digest
        with (TREE/'vmlinux').open('rb') as source,gzip.open(snapshot/'vmlinux.gz','wb',compresslevel=1) as out:shutil.copyfileobj(source,out,1<<20)
        save(OUT/'identity-store.json',dict(vmlinux_sha256=manifest['build_files']['vmlinux'],compressed_sha256=rt.digest(snapshot/'vmlinux.gz'),compressed_bytes=(snapshot/'vmlinux.gz').stat().st_size))
        command(['umount',TREE],log/'unmount.log',30);TREE.rmdir()
        command(['rmmod','overlay'],log/'overlay-unload.log',30);shutil.rmtree(RAM)
        runpy.run_path(str(BASE/'control/hydrate.py'))['hydrate']()
        assert verify(BUNDLE,TREE,build=True)['ok']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        idle();state.update(passed=True,installed=True,binaries=binaries,probe_directory=str(probes),baseline=str(BUNDLE),kernel_snapshot=str(TREE),persistent_identity=str(snapshot),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),runtime_modules=len(targets),unchanged_clients_reused=4,temporary_build_mount_removed=True,incremental_compilations=sum(len(re.findall(r'^\s*CC\s',p.read_text(),re.M)) for p in log.glob('*.log')))
    except BaseException as error:state['error']=repr(error);raise
    finally:save(log/'result.json',state)
    print(json.dumps(state),flush=True)

if __name__=='__main__':main()
