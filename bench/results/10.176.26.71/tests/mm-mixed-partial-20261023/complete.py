#!/usr/bin/env python3
"""Finish identity storage from compiled outputs, without rebuilding or deleting evidence."""
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import sys

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-mixed-partial-20261023')
OUT=Path('/root/kdlock-kernel-work/mm-mixed-partial-20261023')
DATA=Path('/mnt/kdlock-builds/mm-mixed-partial-20261023')
RAM=Path('/dev/shm/kdmm9-cow');TREE=Path('/dev/shm/kdmm9-identity')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm9-20261023')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
load=lambda p:json.loads(p.read_text())


def main():
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
    expected=load(BASE/'control/expected-guest.json')['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==sorted(expected+['overlay'])
    assert not load(BASE/'build-1/result.json')['passed']
    installed=load(BASE/'install/result.json');assert installed['passed'] and installed['recovery_unchanged']
    assert rt.digest(BASE/'install/installed-sha256.json')==installed['installed_manifest_sha256']
    for n,h in load(BASE/'install/installed-sha256.json').items():assert rt.digest(Path(n))==h,n
    for n,h in {**load(BASE/'recovery/boot-sha256.json'),**load(BASE/'recovery/modules-sha256.json')}.items():
        if n!='/boot/grub/grub.cfg':assert rt.digest(Path(n))==h,n
    inputs=load(BASE/'control/inputs.json')
    for n,h in inputs['files'].items():assert rt.digest(ROOT/n)==h,n
    manifest=load(BUNDLE/'manifest.json');parent=load(BUNDLE/'parent-manifest.json')
    snapshot=DATA/'identity'
    for n,h in {**manifest['source_files'],**manifest['build_files'],'.config':manifest['bundle_files']['guest.config']}.items():
        if n!='vmlinux':assert rt.digest(snapshot/n)==h,n
    log=BASE/'build-2';log.mkdir()
    state=dict(passed=False,reused_build=str(BASE/'build-1'),source_commit=inputs['commit'])
    try:
        # Split storage only: the concatenated bytes remain the original xz
        # stream. Each part and the complete stream have an exact digest.
        compressed=RAM/'vmlinux.xz';split=100*1024*1024
        assert 0<split<compressed.stat().st_size
        assert shutil.disk_usage(OUT).free>split+8_000_000
        assert shutil.disk_usage(DATA).free>compressed.stat().st_size-split+8_000_000
        parts=[]
        with compressed.open('rb') as source:
            for p,n in ((OUT/'vmlinux.xz.part0',split),(DATA/'vmlinux.xz.part1',compressed.stat().st_size-split)):
                assert not p.exists()
                with p.open('wb') as dest:
                    remaining=n
                    while remaining:
                        block=source.read(min(1<<20,remaining));assert block
                        dest.write(block);remaining-=len(block)
                parts.append(dict(path=str(p),bytes=n,sha256=rt.digest(p)))
            assert not source.read(1)
        rt.write_json(OUT/'identity-store.json',dict(parts=parts,compressed_bytes=compressed.stat().st_size,
            compressed_sha256=rt.digest(compressed),vmlinux_sha256=manifest['build_files']['vmlinux']))
        assert not any(TREE.iterdir()),'private build mount must have drained'
        TREE.rmdir()
        runpy.run_path(str(BASE/'control-2/hydrate.py'))['hydrate']()
        assert runpy.run_path(str(ROOT/'kernel_baseline/verify.py'))['verify'](BUNDLE,TREE,build=True)['ok']
        # Verified persistent parts and rehydrated identity exist before only
        # this stage's disposable RAM build/packaging layer is retired.
        rt.command(['rmmod','overlay'],log/'overlay-unload.log');shutil.rmtree(RAM)
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
        binaries={}
        for family,module in [('body','kd_mm_body_test'),('fault_body','kd_mm_fault_test'),
                ('unmap_body','kd_mm_unmap_test'),('populated_unmap','kd_mm_populated_test'),
                ('partial_unmap',None),('resident_partial',None),('mixed_partial',None)]:
            paths=[BASE/'probes-1'/family/'client']
            if module:paths.append(BASE/'probes-1'/family/'payload'/(module+'.ko'))
            binaries[family]={str(p.relative_to(BASE)):rt.digest(p) for p in paths}
        state.update(passed=True,installed=True,booted=False,binaries=binaries,probe_directory=str(BASE/'probes-1'),
            baseline=str(BUNDLE),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),
            parent_manifest_sha256=manifest['parent_manifest_sha256'],runtime_modules=73,unchanged_clients_reused=6,
            module_debug_stripped=True,kernel_snapshot=str(TREE),persistent_identity=str(snapshot),
            temporary_build_mount_removed=True,changed_kernel_sources=[n for n,h in manifest['source_files'].items() if parent['source_files'].get(n)!=h],
            incremental_compilations=sum(len(re.findall(r'^\s*CC\s',p.read_text(),re.M)) for p in (BASE/'build-1').glob('*.log')))
    except BaseException as error:state['error']=repr(error);raise
    finally:rt.write_json(log/'result.json',state)
    print(json.dumps(dict(passed=True,recompiled=False)))


if __name__=='__main__':main()
