#!/usr/bin/env python3
"""Only the new test module/clients; installed kdmm22 and recovery stay intact."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-neighbor-replace-20261024')
PRIOR=BASE.parent/'mm-boundary-shared-missing-20261024'
RAM=Path('/dev/shm/kdmm22-neighbor-build')
IDENTITY=Path('/dev/shm/kdmm22-identity')
LOWER=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm22-20261024')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
command=runpy.run_path(str(BASE.parent/'mm-populated-unmap-20261022/build-control-1/build.py'))['command']


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=int,default=1);a=p.parse_args()
    assert a.attempt==1 and os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
    inputs=json.loads((BASE/'control/inputs.json').read_text())
    for name,digest in inputs['files'].items():assert rt.digest(ROOT/name)==digest,name
    expected=json.loads((PRIOR/'control/expected-guest.json').read_text())['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
    previous=json.loads((PRIOR/'build-1/result.json').read_text());assert previous['passed']
    manifest=json.loads((BUNDLE/'manifest.json').read_text())
    assert rt.digest(BUNDLE/'manifest.json')==previous['baseline_manifest_sha256']
    source_bytes=sum((ROOT/n).stat().st_size for n in inputs['files'])
    module_bytes=(PRIOR/'probes-1/unmap_body/payload/kd_mm_unmap_test.ko').stat().st_size
    client_bytes=max(p.stat().st_size for p in (PRIOR/'probes-1').glob('*/client'))
    logs_bytes=sum(p.stat().st_size for p in (PRIOR/'focused-1').rglob('*') if p.is_file())
    root_budget=2*(source_bytes+module_bytes+4*client_bytes+logs_bytes)+15_000_000
    # Actual captured ELF size comes from the retained original ELF (same
    # configuration). Allow two such sizes for hydration/build and 128 MiB
    # for copied headers, this small module and compressed RAM transport.
    ram_budget=2*(LOWER/'vmlinux').stat().st_size+142_624_436+128*1024*1024
    assert shutil.disk_usage('/').free>root_budget and shutil.disk_usage('/dev/shm').free>ram_budget
    out=BASE/'build-1';out.mkdir()
    state=dict(passed=False,source_commit=inputs['commit'],kernel_rebuilt=False,kernel_installed=False,
        root_budget=root_budget,ram_budget=ram_budget,measured_inputs=dict(source_bytes=source_bytes,module_bytes=module_bytes,client_bytes=client_bytes,prior_logs_bytes=logs_bytes),
        space_before=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'))
    rt.write_json(out/'result.json',state)
    try:
        runpy.run_path(str(PRIOR/'control/hydrate.py'))['hydrate']()
        RAM.mkdir();tree=RAM/'tree';tree.mkdir();(RAM/'upper').mkdir();(RAM/'work').mkdir()
        command(['modprobe','overlay'],out/'overlay-load.log',30)
        command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',tree],out/'mount.log',30)
        captured={**manifest['source_files'],**manifest['build_files']}
        for name,digest in captured.items():
            assert rt.digest(IDENTITY/name)==digest,name
            if name=='vmlinux':
                # Replacing only the overlay name never changes lower's ELF.
                (tree/name).unlink();(tree/name).symlink_to(IDENTITY/name)
            else:
                (tree/name).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(IDENTITY/name,tree/name)
        shutil.copyfile(IDENTITY/'.config',tree/'.config')
        probes=BASE/'probes-1';probes.mkdir();binaries={}
        for name in inputs['files']:
            if not name.startswith('tests/kernel/mmap_lock/'):continue
            dest=probes/name[len('tests/kernel/mmap_lock/'):];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for family in ('boundary_shared_missing','boundary_shared_empty','boundary_shared_zero','boundary_shared'):
            dst=probes/family/'client';dst.symlink_to(PRIOR/'probes-1'/family/'client')
            binaries[family]={str(dst.relative_to(BASE)):rt.digest(dst)}
        command(['make','-C',probes/'neighbor_replace'],out/'clients.log',180)
        binaries['neighbor_replace']={str(p.relative_to(BASE)):rt.digest(p) for p in (probes/'neighbor_replace').glob('client-*')}
        module=RAM/'module';shutil.copytree(probes/'unmap_body/payload',module)
        command(['make','-C',module,'KDIR='+str(tree),'W=1','UBSAN_SANITIZE=n'],out/'module.log',180)
        binary=probes/'unmap_body/payload/kd_mm_unmap_test.ko';shutil.copyfile(module/binary.name,binary)
        binaries['unmap_body']={str(binary.relative_to(BASE)):rt.digest(binary)}
        command([sys.executable,'-c',"import ast,sys;from pathlib import Path;[ast.parse(Path(p).read_text(),p) for p in sys.argv[1:]]",*[ROOT/n for n in inputs['files'] if n.endswith('.py')]],out/'syntax.log',30)
        command(['make','-C',ROOT/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],out/'basic.log',180)
        # Module builds must not silently regenerate a different configuration
        # or captured kernel input. No release change or kernel target is used.
        for name,digest in captured.items():assert rt.digest(tree/name)==digest,name
        assert rt.digest(tree/'.config')==rt.digest(IDENTITY/'.config')
        command(['umount',tree],out/'unmount.log',30)
        command(['rmmod','overlay'],out/'overlay-unload.log',30)
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        rt.write_json(BASE/'control/expected-guest.json',dict(modules=expected))
        state.update(passed=True,probe_directory=str(probes),binaries=binaries,unchanged_clients_reused=4,new_clients=4,
                     space_after=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free),temporary_mount_removed=True)
    except BaseException as error:state['error']=repr(error);raise
    finally:rt.write_json(out/'result.json',state)
    print(json.dumps(state),flush=True)

if __name__=='__main__':main()
