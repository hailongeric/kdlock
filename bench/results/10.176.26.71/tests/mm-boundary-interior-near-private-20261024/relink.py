#!/usr/bin/env python3
"""Guest-only pre-boot correction: reuse completed objects, modules and initramfs."""
import json,lzma,os,re,runpy,shutil,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-near-private-20261024')
OUT=Path('/root/kdlock-kernel-work/mm-boundary-interior-near-private-20261024')
REV=OUT/'revision-2'
RAM=Path('/dev/shm/kdmm28-cow');TREE=Path('/dev/shm/kdmm28-relink')
LOWER=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
PARENT=Path('/root/kdlock-kernel-baselines/mmap-kdmm28-20261024')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm28-r2-20261024')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'));import bench_runtime as rt
command=runpy.run_path('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/build-control-1/build.py')['command']
def load(p):return json.loads(p.read_text())
def idle():runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
def preserved():
    for n,h in {**load(BASE/'recovery/boot-sha256.json'),**load(BASE/'recovery/modules-sha256.json')}.items():
        if n!='/boot/grub/grub.cfg':assert rt.digest(Path(n))==h,n

def main():
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    idle();preserved()
    old=load(BASE/'build-1/result.json');parent=load(PARENT/'manifest.json')
    inputs=load(BASE/'control-r2/inputs.json')
    assert old['passed'] and not (BASE/'kd-1').exists()
    for n,h in inputs['files'].items():assert rt.digest(ROOT/n)==h,n
    expected=load(BASE/'control/expected-guest.json')['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
    installed=load(BASE/'install/installed-sha256.json')
    for n,h in installed.items():assert rt.digest(Path(n))==h,n
    # Existing identity contains original bzImage/System.map: replacing the two
    # candidate boot files is reversible without deleting or recapturing them.
    for name,target in [('arch/x86/boot/bzImage','vmlinuz'),('System.map','System.map')]:
        assert rt.digest(OUT/'identity'/name)==installed['/boot/'+target+'-6.1.159-kdmm28']
    grub=rt.digest(Path('/boot/grub/grub.cfg'))
    # One new ELF identity plus link/transport space; derive the RAM allowance
    # from the completed ELF and compressed size, not a generic disk threshold.
    ram_need=3*Path('/dev/shm/kdmm28-identity/vmlinux').stat().st_size+load(OUT/'identity-store.json')['compressed_bytes']
    assert shutil.disk_usage('/').free>120_000_000 and shutil.disk_usage('/dev/shm').free>ram_need
    log=BASE/'build-2';log.mkdir();REV.mkdir();TREE.mkdir()
    state=dict(old,passed=False,installed=False,source_commit=inputs['commit'],parent_manifest_sha256=rt.digest(PARENT/'manifest.json'),
        initial_build=str(BASE/'build-1/result.json'),initial_compilations=old['incremental_compilations'],
        space_before=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free),ram_budget=ram_need)
    rt.write_json(log/'result.json',state)
    command(['modprobe','overlay'],log/'overlay-load.log',30)
    command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',TREE],log/'mount.log',30)
    try:
        for n,h in {**parent['source_files'],**parent['build_files']}.items():assert rt.digest(TREE/n)==h,n
        assert rt.digest(TREE/'.config')==parent['bundle_files']['guest.config']
        shutil.copyfile(ROOT/'kernel_integration/mmap_lock/overlay/mm/kd_mmap_unmap.inc',TREE/'mm/kd_mmap_unmap.inc')
        command(['make','-j16','bzImage'],log/'image.log',1800,cwd=TREE)
        # ABI/config/signing key unchanged: every already installed module and
        # the existing initramfs remain valid. Do not regenerate or recopy them.
        assert rt.digest(TREE/'vmlinux.symvers')==parent['build_files']['vmlinux.symvers']
        shutil.copyfile(OUT/'identity/Module.symvers',TREE/'Module.symvers')
        for n,h in load(OUT/'modules-build-2.json')['modules'].items():assert rt.digest(TREE/n)==h,n
        outputs=dict(parent['source_files']);outputs['mm/kd_mmap_unmap.inc']=rt.digest(TREE/'mm/kd_mmap_unmap.inc')
        prep=load(OUT/'prepare.json');prep.update(source_tree=str(TREE),outputs=outputs)
        rt.write_json(REV/'prepare.json',prep)
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/capture.py','--prepared',REV,'--output',BUNDLE,'--parent',PARENT],log/'capture.log',180)
        manifest=load(BUNDLE/'manifest.json');snap=REV/'identity';snap.mkdir()
        for n,h in {**manifest['source_files'],**manifest['build_files'],'.config':prep['config_sha256']}.items():
            if n=='vmlinux':continue
            dst=snap/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(TREE/n,dst);assert rt.digest(dst)==h
        stored=Path('/dev/shm/kdmm28-r2-vmlinux.xz');assert not stored.exists()
        with (TREE/'vmlinux').open('rb') as src,lzma.open(stored,'wb',preset=1) as dst:shutil.copyfileobj(src,dst,1<<20)
        rt.write_json(REV/'identity-store.json',dict(vmlinux_sha256=manifest['build_files']['vmlinux'],compressed_path=str(stored),compressed_sha256=rt.digest(stored),compressed_bytes=stored.stat().st_size))
        install=BASE/'install-r2';install.mkdir()
        state['root_free_before_install']=shutil.disk_usage('/').free;assert state['root_free_before_install']>120_000_000
        for source,target in [('arch/x86/boot/bzImage','vmlinuz'),('System.map','System.map')]:
            dst=Path('/boot')/(target+'-6.1.159-kdmm28');tmp=dst.with_name(dst.name+'.revision-2')
            assert not tmp.exists() and rt.digest(dst)==installed[str(dst)]
            shutil.copyfile(TREE/source,tmp);assert rt.digest(tmp)==manifest['build_files'][source]
            tmp.replace(dst);installed[str(dst)]=rt.digest(dst)
        for n,h in installed.items():assert rt.digest(Path(n))==h,n
        rt.write_json(install/'installed-sha256.json',installed)
        ir=load(BASE/'install/result.json');ir.update(kernel_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),
            installed_manifest_sha256=rt.digest(install/'installed-sha256.json'),revision=2,reused_modules_and_initramfs=True,
            prior_install=str(BASE/'install/result.json'),replaced_candidate_files=['/boot/vmlinuz-6.1.159-kdmm28','/boot/System.map-6.1.159-kdmm28'])
        rt.write_json(install/'result.json',ir)
        assert rt.digest(Path('/boot/grub/grub.cfg'))==grub;preserved()
        command(['umount',TREE],log/'unmount.log',30);TREE.rmdir();command(['rmmod','overlay'],log/'overlay-unload.log',30)
        runpy.run_path(str(BASE/'control-r2/hydrate.py'))['hydrate']()
        assert runpy.run_path(str(ROOT/'kernel_baseline/verify.py'))['verify'](BUNDLE,Path('/dev/shm/kdmm28-r2-identity'),build=True)['ok']
        idle();assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        state.update(passed=True,installed=True,baseline=str(BUNDLE),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),
            kernel_snapshot='/dev/shm/kdmm28-r2-identity',persistent_identity=str(snap),reused_probe_binaries=True,
            incremental_compilations=len(re.findall(r'^\s*CC\s',(log/'image.log').read_text(),re.M)),
            space_after=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free))
    except BaseException as error:state['error']=repr(error);raise
    finally:rt.write_json(log/'result.json',state)
    print(json.dumps(dict(passed=True,reused_modules_and_initramfs=True,incremental_compilations=state['incremental_compilations'])))
if __name__=='__main__':main()
