#!/usr/bin/env python3
"""Incremental guest-only build; freeze one candidate and reuse unchanged clients."""
import argparse
import lzma
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import sys

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-zero-partial-20261023')
PRIOR=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-resident-partial-20261023')
STAGE=ROOT/'bench/results/10.176.26.71/tests/mm-zero-partial-20261023'
OUT=Path('/root/kdlock-kernel-work/mm-zero-partial-20261023')
TREE=Path('/dev/shm/kdmm10-identity')
RAM=Path('/dev/shm/kdmm10-cow')
LOWER=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
PARENT=Path('/root/kdlock-kernel-baselines/mmap-kdmm9-20261023')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm10-20261023')
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
    expected=json.loads((PRIOR/'control/expected-guest.json').read_text())['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
    assert verify(Path('/root/kdlock-kernel-baselines/mmap-kdmm5-20261022'),LOWER,build=True)['ok']
    parent=json.loads((PARENT/'manifest.json').read_text())
    # Measured prior artifacts: 225,280,844 persistent bytes + 8,908,800
    # observed boot-cycle growth. RAM budget is the conservative artifact
    # model (7,739,283,276 bytes); no new files are placed on the data disk.
    assert shutil.disk_usage('/').free > 234_189_644
    assert shutil.disk_usage('/dev/shm').free > 7_739_283_276
    assert not Path('/boot/vmlinuz-6.1.159-kdmm10').exists()
    assert not Path('/lib/modules/6.1.159-kdmm10').exists()
    log=BASE/'build-1';log.mkdir();OUT.mkdir();TREE.mkdir();RAM.mkdir();(RAM/'upper').mkdir();(RAM/'work').mkdir()
    state=dict(space_before=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free),passed=False,installed=False,booted=False,source_commit=inputs['commit'],parent_manifest_sha256=rt.digest(PARENT/'manifest.json'))
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
        probes=BASE/'probes-1';probes.mkdir();binaries={}
        for family,module in [('populated_unmap','kd_mm_populated_test'),('body','kd_mm_body_test'),('fault_body','kd_mm_fault_test'),('unmap_body','kd_mm_unmap_test')]:
            dest=probes/family;(dest/'payload').mkdir(parents=True)
            for source in (PRIOR/'probes-1'/family).rglob('*'):
                if source.is_file() and (source.suffix in ('.c','.h','.py','.inc') or source.name=='Makefile') and not source.name.endswith('.mod.c'):
                    rel=source.relative_to(PRIOR/'probes-1'/family);dst=dest/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                    if family=='unmap_body' and rel.as_posix() in ('payload/module.c','payload/api.h','payload/resident.inc'):
                        shutil.copyfile(ROOT/'tests/kernel/mmap_lock'/family/rel,dst)
                    else:dst.symlink_to(source)
            (dest/'client').symlink_to(PRIOR/'probes-1'/family/'client')
            binaries[family]={str((dest/'client').relative_to(BASE)):rt.digest(dest/'client')}
        partial=probes/'partial_unmap';partial.mkdir()
        for name in ('client','client.c','receipts.py','test_receipts.py'):(partial/name).symlink_to(PRIOR/'probes-1/partial_unmap'/name)
        binaries['partial_unmap']={str((partial/'client').relative_to(BASE)):rt.digest(partial/'client')}
        resident=probes/'resident_partial';resident.mkdir()
        for name in ('client','client.c','receipts.py','controls.py'):(resident/name).symlink_to(PRIOR/'probes-1/resident_partial'/name)
        binaries['resident_partial']={str((resident/'client').relative_to(BASE)):rt.digest(resident/'client')}
        mixed=probes/'mixed_partial';mixed.mkdir()
        previous=Path('/mnt/kdlock-builds/mm-mixed-matrix-20261023/probes-1/mixed_partial')
        for name in ('client','client.c','receipts.py','controls.py'):(mixed/name).symlink_to(previous/name)
        binaries['mixed_partial']={str((mixed/'client').relative_to(BASE)):rt.digest(mixed/'client')}
        partial=probes/'zero_partial';shutil.copytree(ROOT/'tests/kernel/mmap_lock/zero_partial',partial,ignore=shutil.ignore_patterns('__pycache__'))
        command(['cc','-pthread','-O2','-Wall','-Wextra','-Werror','-o',partial/'client',partial/'client.c'],log/'zero-client.log',120)
        binaries['zero_partial']={str((partial/'client').relative_to(BASE)):rt.digest(partial/'client')}
        command(['make','-C',ROOT/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],log/'basic.log',180)
        changed=['mm/mmap.c','mm/rmap.c','mm/kd_mmap_unmap.inc','include/linux/kd_mmap_lock.h','include/linux/kd_mmap_lock_types.h','kernel/locking/kd_mmap/unmap.c']
        command(['patch','--batch','--fuzz=0','-p1','-i',ROOT/'bench/results/10.176.26.71/tests/mm-resident-partial-20261023/incremental.patch'],log/'patch.log',30,cwd=TREE)
        for name in changed[2:]:shutil.copyfile(ROOT/'kernel_integration/mmap_lock/overlay'/name,TREE/name)
        config=(LOWER/'.config').read_text().replace('CONFIG_LOCALVERSION="-kdmm5"','CONFIG_LOCALVERSION="-kdmm10"')
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
        old_symbols={s.split()[1] for s in (LOWER/'vmlinux.symvers').read_text().splitlines()}
        new_symbols={s.split()[1] for s in (TREE/'vmlinux.symvers').read_text().splitlines()}
        assert new_symbols-old_symbols=={'kd_mmap_unmap_resident_partial_enable'} and not old_symbols-new_symbols
        save(OUT/'modules-build-2.json',dict(passed=True,modules={n:rt.digest(TREE/n) for n in targets}))
        for family,module in [('populated_unmap','kd_mm_populated_test'),('body','kd_mm_body_test'),('fault_body','kd_mm_fault_test'),('unmap_body','kd_mm_unmap_test')]:
            dest=probes/family
            command(['make','-C',dest/'payload','KDIR='+str(TREE),'W=1','UBSAN_SANITIZE=n'],log/(family+'-module.log'),180)
            binary=dest/'payload'/(module+'.ko');binaries[family][str(binary.relative_to(BASE))]=rt.digest(binary)
        outputs=dict(parent['source_files'])
        for name in changed:outputs[name]=rt.digest(TREE/name)
        prepared=dict(passed=True,source_tree=str(TREE),release='6.1.159-kdmm10',outputs=outputs,config_sha256=rt.digest(TREE/'.config'),patch_sha256=rt.digest(ROOT/'kernel_integration/mmap_lock/guest-kernel.patch'))
        save(OUT/'prepare.json',prepared)
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/capture.py','--prepared',OUT,'--output',BUNDLE,'--parent',PARENT],log/'capture.log',180)
        (RAM/'package').mkdir()
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/install.py','--prepared',OUT,'--baseline',BUNDLE,'--recovery-record',recovery,'--output',BASE/'install','--strip-module-debug','--initramfs-tmpdir',RAM/'package'],log/'install.log',600)
        manifest=json.loads((BUNDLE/'manifest.json').read_text());snapshot=OUT/'identity';snapshot.mkdir(parents=True)
        for name,digest in {**manifest['source_files'],**manifest['build_files'],'.config':prepared['config_sha256']}.items():
            if name=='vmlinux':continue
            dst=snapshot/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(TREE/name,dst);assert rt.digest(dst)==digest
        # Compress straight to its final root-filesystem path; no duplicate
        # disk copy or split archive. Retain every previous identity intact.
        stored=OUT/'vmlinux.xz'
        assert shutil.disk_usage(OUT).free > 142_582_604 + 8_908_800
        with (TREE/'vmlinux').open('rb') as source,lzma.open(stored,'wb',preset=1) as out:shutil.copyfileobj(source,out,1<<20)
        save(OUT/'identity-store.json',dict(vmlinux_sha256=manifest['build_files']['vmlinux'],compressed_path=str(stored),compressed_sha256=rt.digest(stored),compressed_bytes=stored.stat().st_size))
        command(['umount',TREE],log/'unmount.log',30);TREE.rmdir()
        command(['rmmod','overlay'],log/'overlay-unload.log',30);shutil.rmtree(RAM)
        runpy.run_path(str(BASE/'control/hydrate.py'))['hydrate']()
        assert verify(BUNDLE,TREE,build=True)['ok']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        idle();state.update(space_after=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free),passed=True,installed=True,binaries=binaries,probe_directory=str(probes),baseline=str(BUNDLE),kernel_snapshot=str(TREE),persistent_identity=str(snapshot),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),runtime_modules=len(targets),unchanged_clients_reused=7,module_debug_stripped=True,changed_kernel_sources=[n for n,h in outputs.items() if h!=parent['source_files'].get(n)],temporary_build_mount_removed=True,incremental_compilations=sum(len(re.findall(r'^\s*CC\s',p.read_text(),re.M)) for p in log.glob('*.log')))
    except BaseException as error:state['error']=repr(error);raise
    finally:save(log/'result.json',state)
    print(json.dumps(state),flush=True)

if __name__=='__main__':main()
