#!/usr/bin/env python3
"""Compile only changed correctness probes against the exact installed kdmm29 ELF."""
import argparse,json,os,re,runpy,shutil,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-interior-near-create-20261024')
PRIOR=BASE.parent/'mm-boundary-interior-zero-near-private-20261024'
IDENTITY=Path('/dev/shm/kdmm29-identity')
RAM=Path('/dev/shm/kdmm29-near-create-cow')
TREE=RAM/'tree'
LOWER=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm29-20261024')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'));import bench_runtime as rt
command=runpy.run_path('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/build-control-1/build.py')['command']
verify=runpy.run_path(str(ROOT/'kernel_baseline/verify.py'))['verify']
load=lambda p:json.loads(p.read_text())
def idle():runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)

def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=int,default=1);a=p.parse_args()
    assert a.attempt==1 and os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    idle();inputs=load(BASE/'control/inputs.json')
    for n,h in inputs['files'].items():assert rt.digest(ROOT/n)==h,n
    expected=load(PRIOR/'control/expected-guest.json')['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
    preserved=runpy.run_path(str(PRIOR/'control/transition.py'))['preserved'];preserved()
    # Prior .ko=818240, each client=96920, plus object/debug/source/log copies.
    # 40 MB also retains >8.6 MB observed two-boot growth and room for failures.
    # RAM: two 780204992-byte ELFs + 142634648 compressed transport + headers,
    # helper tools and margin. No kernel packaging/install outputs are needed.
    assert shutil.disk_usage('/').free>40_000_000
    assert shutil.disk_usage('/dev/shm').free>2_000_000_000
    log=BASE/'build-1';log.mkdir()
    state=dict(passed=False,source_commit=inputs['commit'],reused_kernel=True,reused_runtime_modules=True,
        reused_initramfs=True,prior_build=str(PRIOR/'build-1/result.json'),root_budget=40_000_000,ram_budget=2_000_000_000,
        space_before=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free))
    rt.write_json(log/'result.json',state)
    runpy.run_path(str(PRIOR/'control/hydrate.py'))['hydrate']()
    assert verify(BUNDLE,IDENTITY,build=True)['ok']
    manifest=load(BUNDLE/'manifest.json')
    assert verify(Path('/root/kdlock-kernel-baselines/mmap-kdmm5-20261022'),LOWER,build=True)['ok']
    RAM.mkdir();TREE.mkdir();(RAM/'upper').mkdir();(RAM/'work').mkdir()
    command(['modprobe','overlay'],log/'overlay-load.log',30)
    command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',TREE],log/'mount.log',30)
    try:
        for n,h in {**manifest['source_files'],**manifest['build_files'],'.config':manifest['bundle_files']['guest.config']}.items():
            dst=TREE/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(IDENTITY/n,dst);assert rt.digest(dst)==h,n
        probes=BASE/'probes-1';probes.mkdir();sources={};binaries={}
        for name,h in inputs['files'].items():
            prefix='tests/kernel/mmap_lock/'
            if not name.startswith(prefix):continue
            dest=probes/name[len(prefix):];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
            assert rt.digest(dest)==h;sources[str(dest.relative_to(probes))]=h
        command([sys.executable,'-c','import ast,sys;from pathlib import Path;[ast.parse(Path(p).read_text(),p) for p in sys.argv[1:]]',*[ROOT/n for n in inputs['files'] if n.endswith('.py')]],log/'syntax.log',30)
        command(['make','-C',ROOT/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],log/'basic.log',180)
        for target in ('empty','zero'):
            dst=probes/'interior_near_create'/('client-'+target)
            command(['cc','-pthread','-O2','-Wall','-Wextra','-Werror','-o',dst,dst.with_suffix('.c')],log/('client-'+target+'.log'),120)
            binaries[target]={str(dst.relative_to(BASE)):rt.digest(dst)}
        for family in ('boundary_interior_near_private','boundary_interior_zero_near_private','boundary_interior_near_empty','boundary_interior_zero'):
            dst=probes/family/'client';dst.symlink_to(PRIOR/'probes-1'/family/'client')
            binaries[family]={str(dst.relative_to(BASE)):rt.digest(dst)}
        payload=probes/'unmap_body/payload'
        command(['make','-C',payload,'KDIR='+str(TREE),'W=1','UBSAN_SANITIZE=n'],log/'unmap_body-module.log',180)
        assert 'BTF [M]' in (log/'unmap_body-module.log').read_text()
        assert verify(BUNDLE,TREE,build=True)['ok']
        module=payload/'kd_mm_unmap_test.ko';binaries['module']={str(module.relative_to(BASE)):rt.digest(module)}
        command(['umount',TREE],log/'unmount.log',30);TREE.rmdir()
        command(['rmmod','overlay'],log/'overlay-unload.log',30)
        preserved();idle()
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        state.update(passed=True,binaries=binaries,sources=sources,probe_directory=str(probes),
            module_btf_vmlinux_sha256=manifest['build_files']['vmlinux'],baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),
            btf_probe_modules=1,new_clients=2,reused_clients=4,new_runtime_modules=0,kernel_relinks=0,
            temporary_build_mount_removed=True,ram_intermediates_retained_until_boot=str(RAM),
            space_after=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free))
    except BaseException as error:state['error']=repr(error);raise
    finally:rt.write_json(log/'result.json',state)
    print(json.dumps(dict(passed=True,new_clients=2,new_test_modules=1,kernel_relinks=0)),flush=True)
if __name__=='__main__':main()
