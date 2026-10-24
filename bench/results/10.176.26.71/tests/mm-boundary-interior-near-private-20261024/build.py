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
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-near-private-20261024')
PRIOR=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024')
STAGE=ROOT/'bench/results/10.176.26.71/tests/mm-boundary-interior-near-private-20261024'
OUT=Path('/root/kdlock-kernel-work/mm-boundary-interior-near-private-20261024')
TREE=Path('/dev/shm/kdmm28-identity')
RAM=Path('/dev/shm/kdmm28-cow')
LOWER=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
PARENT=Path('/root/kdlock-kernel-baselines/mmap-kdmm27-20261024')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm28-20261024')
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
    idle();inputs=json.loads((Path(__file__).parent/'inputs.json').read_text())
    for name,digest in inputs['files'].items():assert rt.digest(ROOT/name)==digest,name
    expected=json.loads((PRIOR/'control/expected-guest.json').read_text())['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
    assert verify(Path('/root/kdlock-kernel-baselines/mmap-kdmm5-20261022'),LOWER,build=True)['ok']
    parent=json.loads((PARENT/'manifest.json').read_text())
    # The prior cycle used 220,442,624 root bytes, including a 142,582,604
    # byte compressed ELF. Retain the new compressed identity on the source
    # host, using guest RAM for transport/hydration. 120 MB covers the measured
    # remaining 77,860,020 bytes, 4,304,896 boot growth and 37,835,084 margin.
    assert shutil.disk_usage('/').free > 120_000_000
    assert shutil.disk_usage('/dev/shm').free > 8_000_000_000
    assert not Path('/boot/vmlinuz-6.1.159-kdmm28').exists()
    assert not Path('/lib/modules/6.1.159-kdmm28').exists()
    log=BASE/f'build-{a.attempt}';log.mkdir();OUT.mkdir();TREE.mkdir()
    RAM.mkdir();(RAM/'upper').mkdir();(RAM/'work').mkdir()
    state=dict(space_before=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free),passed=False,installed=False,booted=False,source_commit=inputs['commit'],parent_manifest_sha256=rt.digest(PARENT/'manifest.json'))
    save(log/'result.json',state)
    recovery=BASE/'recovery';recovery.mkdir()
    names=[p for p in Path('/boot').glob('*-6.1.159-*') if p.is_file()]
    names += [Path('/boot/grub/grub.cfg'),Path('/etc/default/grub')]
    names += [p for d in ('/etc/default/grub.d','/etc/grub.d') for p in Path(d).glob('*') if p.is_file()]
    boot_hashes={str(p):rt.digest(p) for p in names}
    save(recovery/'boot-sha256.json',boot_hashes)
    shutil.copyfile(PRIOR/'recovery/modules-sha256.json',recovery/'modules-sha256.json')
    shutil.copyfile('/boot/grub/grub.cfg',recovery/'grub-before.cfg')
    save(BASE/'control/expected-guest.json',dict(modules=expected))
    command(['modprobe','overlay'],log/'overlay-load.log',30)
    command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',TREE],log/'mount.log',30)
    try:
        probes=BASE/f'probes-{a.attempt}';probes.mkdir();binaries={}
        unmap=probes/'unmap_body';(unmap/'payload').mkdir(parents=True)
        for source in (ROOT/'tests/kernel/mmap_lock/unmap_body').rglob('*'):
            if source.is_file() and (source.suffix in ('.c','.h','.py','.inc') or source.name=='Makefile') and not source.name.endswith('.mod.c'):
                dest=unmap/source.relative_to(ROOT/'tests/kernel/mmap_lock/unmap_body');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        (unmap/'client').symlink_to(PRIOR/'probes-1/unmap_body/client')
        binaries['unmap_body']={str((unmap/'client').relative_to(BASE)):rt.digest(unmap/'client')}
        for family in ('zero_target','boundary_edge','boundary_empty','boundary_zero','resident_partial','boundary_resident','boundary_shared','boundary_shared_zero','boundary_shared_empty','boundary_shared_missing','boundary_interior_missing','boundary_interior_empty','boundary_interior_zero','boundary_interior_near_zero','boundary_interior_near_empty','boundary_interior_near_private','neighbor_replace'):
            dest=probes/family;dest.mkdir()
            for source in (ROOT/'tests/kernel/mmap_lock'/family).iterdir():
                if source.suffix in ('.c','.py','.inc','.h'):shutil.copyfile(source,dest/source.name)
            if family=='neighbor_replace':
                prior=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-neighbor-replace-20261024/probes-1/neighbor_replace/client-missing')
                (dest/'client-missing').symlink_to(prior)
                binaries[family]={str((dest/'client-missing').relative_to(BASE)):rt.digest(dest/'client-missing')}
            elif family!='boundary_interior_near_private':
                (dest/'client').symlink_to(PRIOR/'probes-1'/family/'client')
                binaries[family]={str((dest/'client').relative_to(BASE)):rt.digest(dest/'client')}
        new=probes/'boundary_interior_near_private'
        command(['cc','-pthread','-O2','-Wall','-Wextra','-Werror','-o',new/'client',new/'client.c'],log/'interior-client.log',120)
        binaries['boundary_interior_near_private']={str((new/'client').relative_to(BASE)):rt.digest(new/'client')}
        command([sys.executable,'-c',"import ast,sys;from pathlib import Path;[ast.parse(Path(p).read_text(),p) for p in sys.argv[1:]]",*[ROOT/n for n in inputs['files'] if n.endswith('.py')]],log/'syntax.log',30)
        command(['make','-C',ROOT/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],log/'basic.log',180)
        changed=['mm/mmap.c','mm/rmap.c','mm/kd_mmap_unmap.inc','include/linux/kd_mmap_lock.h','include/linux/kd_mmap_lock_types.h','kernel/locking/kd_mmap/unmap.c']
        command(['patch','--batch','--fuzz=0','-p1','-i',ROOT/'bench/results/10.176.26.71/tests/mm-resident-partial-20261023/incremental.patch'],log/'patch.log',30,cwd=TREE)
        for name in changed[2:]:shutil.copyfile(ROOT/'kernel_integration/mmap_lock/overlay'/name,TREE/name)
        config=(LOWER/'.config').read_text().replace('CONFIG_LOCALVERSION="-kdmm5"','CONFIG_LOCALVERSION="-kdmm28"')
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
        # install.py's historical input filename is independent of this run's attempt.
        save(OUT/'modules-build-2.json',dict(passed=True,modules={n:rt.digest(TREE/n) for n in targets}))
        for family,module in [('unmap_body','kd_mm_unmap_test')]:
            dest=probes/family
            command(['make','-C',dest/'payload','KDIR='+str(TREE),'W=1','UBSAN_SANITIZE=n'],log/(family+'-module.log'),180)
            binary=dest/'payload'/(module+'.ko');binaries[family][str(binary.relative_to(BASE))]=rt.digest(binary)
        outputs=dict(parent['source_files'])
        for name in changed:outputs[name]=rt.digest(TREE/name)
        prepared=dict(passed=True,source_tree=str(TREE),release='6.1.159-kdmm28',outputs=outputs,config_sha256=rt.digest(TREE/'.config'),patch_sha256=rt.digest(ROOT/'kernel_integration/mmap_lock/guest-kernel.patch'))
        save(OUT/'prepare.json',prepared)
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/capture.py','--prepared',OUT,'--output',BUNDLE,'--parent',PARENT],log/'capture.log',180)
        (RAM/'package').mkdir()
        state['root_free_before_install']=shutil.disk_usage('/').free
        assert state['root_free_before_install'] > 120_000_000
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/install.py','--prepared',OUT,'--baseline',BUNDLE,'--recovery-record',recovery,'--output',BASE/'install','--strip-module-debug','--initramfs-tmpdir',RAM/'package'],log/'install.log',600)
        manifest=json.loads((BUNDLE/'manifest.json').read_text());snapshot=OUT/'identity';snapshot.mkdir(parents=True)
        for name,digest in {**manifest['source_files'],**manifest['build_files'],'.config':prepared['config_sha256']}.items():
            if name=='vmlinux':continue
            dst=snapshot/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(TREE/name,dst);assert rt.digest(dst)==digest
        # Source-host workflow must hash-verify the durable copy before boot.
        # No new compressed ELF is accumulated on the nearly full guest root.
        stored=Path('/dev/shm/kdmm28-vmlinux.xz')
        assert not stored.exists() and shutil.disk_usage('/dev/shm').free > 160_000_000
        with (TREE/'vmlinux').open('rb') as source,lzma.open(stored,'wb',preset=1) as out:shutil.copyfileobj(source,out,1<<20)
        save(OUT/'identity-store.json',dict(vmlinux_sha256=manifest['build_files']['vmlinux'],compressed_path=str(stored),compressed_sha256=rt.digest(stored),compressed_bytes=stored.stat().st_size))
        command(['umount',TREE],log/'unmount.log',30);TREE.rmdir()
        command(['rmmod','overlay'],log/'overlay-unload.log',30)
        # Retain this operation's volatile intermediates until the approved
        # boot clears tmpfs. No historical files or permanent intermediates
        # are deleted. The captured image/identity is already durable.
        state['ram_intermediates_retained_until_boot']=str(RAM)
        runpy.run_path(str(BASE/'control/hydrate.py'))['hydrate']()
        assert verify(BUNDLE,TREE,build=True)['ok']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        idle();state.update(space_after=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free),passed=True,installed=True,binaries=binaries,probe_directory=str(probes),baseline=str(BUNDLE),kernel_snapshot=str(TREE),persistent_identity=str(snapshot),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),runtime_modules=len(targets),unchanged_clients_reused=17,module_debug_stripped=True,changed_kernel_sources=[n for n,h in outputs.items() if h!=parent['source_files'].get(n)],temporary_build_mount_removed=True,incremental_compilations=sum(len(re.findall(r'^\s*CC\s',p.read_text(),re.M)) for p in log.glob('*.log')))
    except BaseException as error:state['error']=repr(error);raise
    finally:save(log/'result.json',state)
    print(json.dumps(state),flush=True)

if __name__=='__main__':main()
