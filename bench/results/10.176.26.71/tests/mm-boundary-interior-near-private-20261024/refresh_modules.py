#!/usr/bin/env python3
"""Refresh split-BTF modules against the captured image; never relink the kernel."""
import json,os,re,runpy,shutil,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-near-private-20261024')
OUT=Path('/root/kdlock-kernel-work/mm-boundary-interior-near-private-20261024')
REV=OUT/'revision-3'
RAM=Path('/dev/shm/kdmm28-modules-cow')
TREE=Path('/dev/shm/kdmm28-modules-tree')
IDENTITY=Path('/dev/shm/kdmm28-r2-identity')
LOWER=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm28-r2-20261024')
RELEASE='6.1.159-kdmm28'
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'));import bench_runtime as rt
command=runpy.run_path('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/build-control-1/build.py')['command']
verify=runpy.run_path(str(ROOT/'kernel_baseline/verify.py'))['verify']
def load(p):return json.loads(p.read_text())
def idle():runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
def preserved():
    for n,h in {**load(BASE/'recovery/boot-sha256.json'),**load(BASE/'recovery/modules-sha256.json')}.items():
        if n!='/boot/grub/grub.cfg':assert rt.digest(Path(n))==h,n

def main():
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    idle();preserved()
    inputs=load(BASE/'control-r3/inputs.json')
    for n,h in inputs['files'].items():assert rt.digest(ROOT/n)==h,n
    expected=load(BASE/'control/expected-guest.json')['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
    old=load(BASE/'build-2/result.json');installed=load(BASE/'install-r2/installed-sha256.json')
    for n,h in installed.items():assert rt.digest(Path(n))==h,n
    # Retain the rejected module set/initramfs by same-filesystem rename. New
    # installed modules plus initramfs measured 33.2 MB; 120 MB includes probe,
    # logs and boot growth. The previous complete RAM build fit within 8 GB.
    assert shutil.disk_usage('/').free>120_000_000
    assert shutil.disk_usage('/dev/shm').free>8_000_000_000
    log=BASE/'build-3';log.mkdir();REV.mkdir();RAM.mkdir();TREE.mkdir()
    for n in ('upper','work','package'):(RAM/n).mkdir()
    state=dict(old,passed=False,installed=False,source_commit=inputs['commit'],
        reused_kernel=True,reused_probe_clients=True,prior_build=str(BASE/'build-2/result.json'),
        root_budget=120_000_000,ram_budget=8_000_000_000,
        space_before=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free))
    rt.write_json(log/'result.json',state)
    runpy.run_path(str(BASE/'control-r3/hydrate.py'))['hydrate']()
    assert verify(BUNDLE,IDENTITY,build=True)['ok']
    assert verify(Path('/root/kdlock-kernel-baselines/mmap-kdmm5-20261022'),LOWER,build=True)['ok']
    manifest=load(BUNDLE/'manifest.json');grub=rt.digest(Path('/boot/grub/grub.cfg'))
    command(['modprobe','overlay'],log/'overlay-load.log',30)
    command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',TREE],log/'mount.log',30)
    try:
        for n,h in {**manifest['source_files'],**manifest['build_files'],'.config':manifest['bundle_files']['guest.config']}.items():
            dst=TREE/n;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(IDENTITY/n,dst);assert rt.digest(dst)==h,n
        # Explicit .ko targets leave the final vmlinux unchanged. Kbuild's BTF
        # pass must use precisely that ELF, not an image with matching CRCs.
        targets=load(ROOT/'bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/module-targets.json')
        serio='drivers/input/serio/serio_raw.ko'
        command(['make','-j16',*[n for n in targets if n!=serio]],log/'runtime-modules.log',900,cwd=TREE)
        shutil.copyfile(TREE/'Module.symvers',REV/'runtime-Module.symvers')
        command(['make','-j1','M=drivers/input/serio','serio_raw.ko'],log/'serio.log',180,cwd=TREE)
        symbols={}
        for path in (TREE/'vmlinux.symvers',REV/'runtime-Module.symvers',TREE/'drivers/input/serio/Module.symvers'):
            for line in path.read_text().splitlines():
                name=line.split()[1];assert name not in symbols or symbols[name]==line;symbols[name]=line
        (TREE/'Module.symvers').write_text('\n'.join(symbols[n] for n in sorted(symbols))+'\n')
        assert verify(BUNDLE,TREE,build=True)['ok']
        btf_log=(log/'runtime-modules.log').read_text()+(log/'serio.log').read_text()
        btf_targets=re.findall(r'^\s*BTF \[M\]\s+(\S+)',btf_log,re.M)
        assert sorted(btf_targets)==sorted(targets),(len(btf_targets),len(targets))
        rt.write_json(REV/'modules.json',dict(vmlinux_sha256=rt.digest(TREE/'vmlinux'),
            modules={n:rt.digest(TREE/n) for n in targets},btf_targets=btf_targets))
        probes=BASE/'probes-3';probes.mkdir();unmap=probes/'unmap_body';(unmap/'payload').mkdir(parents=True)
        for p in (BASE/'probes-1').iterdir():
            if p.name!='unmap_body':(probes/p.name).symlink_to(p,target_is_directory=True)
        for p in (BASE/'probes-1/unmap_body').rglob('*'):
            if p.is_file() and (p.suffix in ('.c','.h','.py','.inc') or p.name=='Makefile') and not p.name.endswith('.mod.c'):
                dst=unmap/p.relative_to(BASE/'probes-1/unmap_body');shutil.copyfile(p,dst)
        (unmap/'client').symlink_to(BASE/'probes-1/unmap_body/client')
        command(['make','-C',unmap/'payload','KDIR='+str(TREE),'W=1','UBSAN_SANITIZE=n'],log/'unmap_body-module.log',180)
        assert 'BTF [M]' in (log/'unmap_body-module.log').read_text()
        binaries=json.loads(json.dumps(old['binaries']))
        binaries['unmap_body']={str(p.relative_to(BASE)):rt.digest(p) for p in (unmap/'client',unmap/'payload/kd_mm_unmap_test.ko')}
        # Recoverable replacement affects only this candidate's dependent
        # outputs. Final image/config/System.map, GRUB and recovery stay exact.
        install=BASE/'install-r3';install.mkdir()
        ir=load(BASE/'install-r2/result.json');ir.update(passed=False,state='REFRESHING_MODULES',
            revision=3,reused_modules_and_initramfs=False,reused_kernel=True,
            prior_install=str(BASE/'install-r2/result.json'))
        rt.write_json(install/'result.json',ir)
        destination=Path('/lib/modules')/RELEASE;initrd=Path('/boot')/('initrd.img-'+RELEASE)
        destination.rename(REV/'installed-modules-before-refresh');initrd.rename(REV/'initrd-before-refresh')
        (TREE/'modules.order').write_text(''.join(n+'\n' for n in sorted(targets)))
        command(['make','modules_install','INSTALL_MOD_STRIP=1'],install/'modules-install.log',300,cwd=TREE)
        command(['depmod','-e','-F',TREE/'System.map',RELEASE],install/'depmod.log',60)
        assert not (install/'depmod.log').read_text().strip()
        for n in targets:
            command(['modinfo','-F','signer',destination/'kernel'/n],install/(Path(n).stem+'-signer.log'),30)
            assert (install/(Path(n).stem+'-signer.log')).read_text().strip()
        env=dict(os.environ,TMPDIR=str(RAM/'package'))
        rt.command(['mkinitramfs','-o',initrd,RELEASE],install/'initramfs.log',timeout=300,env=env)
        command(['lsinitramfs',initrd],install/'initramfs-files.log',90)
        listing=(install/'initramfs-files.log').read_text()
        assert 'kernel/drivers/scsi/virtio_scsi.ko' in listing and '6.1.159-kdclobber2' not in listing
        for n,h in installed.items():
            if n.startswith('/lib/modules/') or n==str(initrd):continue
            assert rt.digest(Path(n))==h,n
        assert rt.digest(Path('/boot/grub/grub.cfg'))==grub;preserved()
        hashes={str(p):rt.digest(p) for p in destination.rglob('*') if p.is_file() and not p.is_symlink()}
        hashes.update({str(p):rt.digest(p) for p in Path('/boot').glob('*-'+RELEASE) if p.is_file()})
        rt.write_json(install/'installed-sha256.json',hashes)
        ir.update(passed=True,state='COMPLETE',installed_manifest_sha256=rt.digest(install/'installed-sha256.json'),
            prior_module_backup=str(REV/'installed-modules-before-refresh'),prior_initramfs_backup=str(REV/'initrd-before-refresh'))
        rt.write_json(install/'result.json',ir)
        assert verify(BUNDLE,TREE,build=True)['ok']
        command(['umount',TREE],log/'unmount.log',30);TREE.rmdir()
        command(['rmmod','overlay'],log/'overlay-unload.log',30)
        idle();assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        state.update(passed=True,installed=True,binaries=binaries,probe_directory=str(probes),
            incremental_compilations=sum(len(re.findall(r'^\s*CC\s',p.read_text(),re.M)) for p in log.glob('*.log')),
            btf_runtime_modules=len(btf_targets),btf_probe_modules=1,
            ram_intermediates_retained_until_boot=str(RAM),
            space_after=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free))
    except BaseException as error:state['error']=repr(error);raise
    finally:rt.write_json(log/'result.json',state)
    print(json.dumps(dict(passed=True,reused_kernel=True,btf_modules=74)),flush=True)
if __name__=='__main__':main()
