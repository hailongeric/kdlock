#!/usr/bin/env python3
"""Finish metadata/install/capture from the completed build; never recompile."""
import json
import lzma
import os
from pathlib import Path
import re
import runpy
import shutil
import sys

sys.dont_write_bytecode=True
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-zero-20261023')
D=runpy.run_path(str(BASE/'control/build.py'))
ROOT,OUT,TREE,RAM,LOWER,BUNDLE,PARENT=(D[k] for k in ('ROOT','OUT','TREE','RAM','LOWER','BUNDLE','PARENT'))
rt,command,verify=D['rt'],D['command'],D['verify']


def main():
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    D['idle']()
    old=json.loads((BASE/'build-1/result.json').read_text())
    assert not old['passed'] and not old['installed'] and 'install.log' in old['error']
    assert "modules-build-2.json" in (BASE/'build-1/install.log').read_text()
    assert not (BASE/'install').exists() and not Path('/boot/vmlinuz-6.1.159-kdmm17').exists()
    assert not Path('/lib/modules/6.1.159-kdmm17').exists()
    remaining_ram_budget=7_739_283_276-(old['space_before']['ram']-shutil.disk_usage('/dev/shm').free)
    assert shutil.disk_usage('/').free>260_000_000 and shutil.disk_usage('/dev/shm').free>remaining_ram_budget
    inputs=json.loads((BASE/'control/inputs.json').read_text())
    for name,digest in inputs['files'].items():assert rt.digest(ROOT/name)==digest,name
    expected=json.loads((BASE/'control/expected-guest.json').read_text())['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==sorted(expected+['overlay'])
    log=BASE/'finish-build-1';log.mkdir()
    state=dict(passed=False,installed=False,booted=False,source_commit=old['source_commit'],
               continued_from=str(BASE/'build-1/result.json'),recompiled=False,
               parent_manifest_sha256=old['parent_manifest_sha256'],space_before=old['space_before'],
               remaining_ram_budget=remaining_ram_budget,finish_space_before=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free))
    rt.write_json(log/'result.json',state)
    try:
        command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',TREE],log/'mount.log',30)
        assert verify(BUNDLE,TREE,build=True)['ok']
        modules=json.loads((OUT/'modules-build-1.json').read_text());assert modules['passed']
        for name,digest in modules['modules'].items():assert rt.digest(TREE/name)==digest
        # Correct only the installer's expected metadata pathname. Keep the
        # original receipt reachable; this alias allocates no duplicate payload.
        assert not (OUT/'modules-build-2.json').exists()
        os.link(OUT/'modules-build-1.json',OUT/'modules-build-2.json')
        state['root_free_before_install']=shutil.disk_usage('/').free
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/install.py','--prepared',OUT,
                 '--baseline',BUNDLE,'--recovery-record',BASE/'recovery','--output',BASE/'install',
                 '--strip-module-debug','--initramfs-tmpdir',RAM/'package'],log/'install.log',600)
        manifest=json.loads((BUNDLE/'manifest.json').read_text())
        prepared=json.loads((OUT/'prepare.json').read_text())
        snapshot=OUT/'identity';snapshot.mkdir()
        for name,digest in {**manifest['source_files'],**manifest['build_files'],'.config':prepared['config_sha256']}.items():
            if name=='vmlinux':continue
            dst=snapshot/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(TREE/name,dst)
            assert rt.digest(dst)==digest
        stored=OUT/'vmlinux.xz'
        assert not stored.exists() and shutil.disk_usage(OUT).free>142_582_604+26_000_000
        with (TREE/'vmlinux').open('rb') as source,lzma.open(stored,'wb',preset=1) as out:shutil.copyfileobj(source,out,1<<20)
        rt.write_json(OUT/'identity-store.json',dict(vmlinux_sha256=manifest['build_files']['vmlinux'],compressed_path=str(stored),compressed_sha256=rt.digest(stored),compressed_bytes=stored.stat().st_size))
        probes=BASE/'probes-1';binaries={}
        for family in ('unmap_body','zero_target','boundary_edge','boundary_empty','boundary_zero'):
            client=probes/family/'client';binaries[family]={str(client.relative_to(BASE)):rt.digest(client)}
        module=probes/'unmap_body/payload/kd_mm_unmap_test.ko'
        binaries['unmap_body'][str(module.relative_to(BASE))]=rt.digest(module)
        command(['umount',TREE],log/'unmount.log',30);TREE.rmdir()
        command(['rmmod','overlay'],log/'overlay-unload.log',30)
        runpy.run_path(str(BASE/'control/hydrate.py'))['hydrate']()
        assert verify(BUNDLE,TREE,build=True)['ok']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        D['idle']()
        parent=json.loads((PARENT/'manifest.json').read_text())
        state.update(passed=True,installed=True,binaries=binaries,probe_directory=str(probes),baseline=str(BUNDLE),
                     kernel_snapshot=str(TREE),persistent_identity=str(snapshot),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),
                     runtime_modules=len(modules['modules']),unchanged_clients_reused=4,module_debug_stripped=True,
                     changed_kernel_sources=[n for n,h in manifest['source_files'].items() if h!=parent['source_files'].get(n)],
                     incremental_compilations=sum(len(re.findall(r'^\s*CC\s',p.read_text(),re.M)) for p in (BASE/'build-1').glob('*.log')),
                     temporary_build_mount_removed=True,ram_intermediates_retained_until_boot=str(RAM),
                     space_after=dict(root=shutil.disk_usage('/').free,ram=shutil.disk_usage('/dev/shm').free))
    except BaseException as error:state['error']=repr(error);raise
    finally:rt.write_json(log/'result.json',state)
    print(json.dumps(dict(passed=True,recompiled=False)),flush=True)


if __name__=='__main__':main()
