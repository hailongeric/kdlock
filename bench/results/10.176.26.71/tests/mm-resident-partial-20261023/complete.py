#!/usr/bin/env python3
"""Finish the failed packaging stage without rebuilding or overwriting evidence."""
import json
import lzma
import os
from pathlib import Path
import re
import runpy
import shutil
import sys

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-resident-partial-20261023')
OUT=Path('/root/kdlock-kernel-work/mm-resident-partial-20261023')
TREE=Path('/dev/shm/kdmm8-identity');RAM=Path('/dev/shm/kdmm8-cow')
LOWER=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm8-20261023')
RELEASE='6.1.159-kdmm8'
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
load=lambda p:json.loads(p.read_text())
verify=runpy.run_path(str(ROOT/'kernel_baseline/verify.py'))['verify']


def main():
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
    expected=load(BASE/'control/expected-guest.json')['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==sorted(expected+['overlay'])
    assert not load(BASE/'build-1/result.json')['passed']
    failed=load(BASE/'install/result.json');assert failed['state']=='FAILED' and 'mkinitramfs' in failed['error']
    package=load(BASE/'package-2/result.json')
    assert package['passed'] and rt.digest(Path(package['file']))==package['sha256']
    inputs=load(BASE/'control/inputs.json')
    for n,h in inputs['files'].items():assert rt.digest(ROOT/n)==h,n
    boot=load(BASE/'recovery/boot-sha256.json');old_modules=load(BASE/'recovery/modules-sha256.json')
    for n,h in {**boot,**old_modules}.items():assert rt.digest(Path(n))==h,n
    log=BASE/'install-2';log.mkdir();buildlog=BASE/'build-2';buildlog.mkdir()
    state=dict(passed=False,state='COMPLETING',release=RELEASE,rebooted=False,
               prior_failure=str(BASE/'install/result.json'),package=str(BASE/'package-2/result.json'))
    rt.write_json(log/'result.json',state)
    rt.command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',TREE],log/'mount.log')
    try:
        assert verify(BUNDLE,TREE,build=True)['ok']
        manifest=load(BUNDLE/'manifest.json')
        for name,kind in [('arch/x86/boot/bzImage','vmlinuz'),('System.map','System.map')]:
            assert rt.digest(Path('/boot',kind+'-'+RELEASE))==manifest['build_files'][name]
        assert rt.digest(Path('/boot','config-'+RELEASE))==manifest['bundle_files']['guest.config']
        targets=load(OUT/'modules-build-2.json');assert targets['passed']
        for name in targets['modules']:
            installed=Path('/lib/modules')/RELEASE/'kernel'/name
            assert installed.is_file()
            assert rt.command(['modinfo','-F','signer',installed],log/(Path(name).stem+'-signer.log')).strip()
        assert not rt.command(['depmod','-e','-F',TREE/'System.map',RELEASE],log/'depmod.log',timeout=60).strip()

        # Retain only the new ELF, compressed on the existing data filesystem.
        # Everything used to rebuild is still in the immutable ancestor tree.
        snapshot=OUT/'identity';snapshot.mkdir()
        for n,h in {**manifest['source_files'],**manifest['build_files'],'.config':manifest['bundle_files']['guest.config']}.items():
            if n=='vmlinux':continue
            dest=snapshot/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(TREE/n,dest)
            assert rt.digest(dest)==h
        compressed=RAM/'vmlinux.xz'
        with (TREE/'vmlinux').open('rb') as source,lzma.open(compressed,'wb',preset=1) as output:
            shutil.copyfileobj(source,output,1<<20)
        data=Path('/mnt/kdlock-builds/mm-resident-partial-20261023');data.mkdir()
        assert compressed.stat().st_size<shutil.disk_usage(data).free-8_000_000
        stored=data/'vmlinux.xz';shutil.copyfile(compressed,stored)
        rt.write_json(OUT/'identity-store.json',dict(vmlinux_sha256=manifest['build_files']['vmlinux'],
            compressed_path=str(stored),compressed_sha256=rt.digest(stored),compressed_bytes=stored.stat().st_size))

        # The partial candidate has never been booted. Preserve it by rename,
        # then install only the verified replacement; no recovery file changes.
        initrd=Path('/boot','initrd.img-'+RELEASE)
        partial=dict(file=str(BASE/'install/failed-initrd.img'),bytes=initrd.stat().st_size,sha256=rt.digest(initrd))
        assert not Path(partial['file']).exists()
        initrd.rename(partial['file']);rt.write_json(BASE/'install/failed-initrd.json',partial)
        shutil.copyfile(package['file'],initrd);assert rt.digest(initrd)==package['sha256']
        entry_file=Path('/etc/grub.d/42_kd_mmap_kdmm8');assert not entry_file.exists()
        mount=rt.command(['findmnt','-n','-o','TARGET,UUID,FSTYPE','--target','/boot'],log/'boot-filesystem.log').split()
        assert len(mount)==3 and mount[0]=='/' and mount[2]=='ext4' and re.fullmatch('[0-9a-f-]+',mount[1])
        args=[s for s in Path('/proc/cmdline').read_text().split() if not s.startswith('BOOT_IMAGE=')]
        assert all(re.fullmatch('[A-Za-z0-9_=,./:-]+',s) for s in args) and {'nokaslr','nopvspin'}<=set(args)
        assert not any(s.startswith('kd_mmap=') for s in args)
        entries='#!/bin/sh\nexec tail -n +3 "$0"\n';ids={}
        for mode,option in [('native','off'),('kd','on')]:
            ident='kd-mmap-'+mode+'-kdmm8';ids[mode]=ident
            entries+=(f"menuentry 'KD mmap {mode} {RELEASE}' --id '{ident}' {{\n"
                '  insmod part_gpt\n  insmod part_msdos\n  insmod ext2\n'
                f'  search --no-floppy --fs-uuid --set=root {mount[1]}\n'
                f'  linux /boot/vmlinuz-{RELEASE} '+' '.join(args)+f' kd_mmap={option}\n'
                f'  initrd /boot/initrd.img-{RELEASE}\n}}\n')
        entry_file.write_text(entries);entry_file.chmod(0o755)
        rt.command(['update-grub'],log/'update-grub.log',timeout=120)
        default='gnulinux-advanced-'+mount[1]+'>gnulinux-6.1.159-kdclobber2-advanced-'+mount[1]
        cfg=Path('/boot/grub/grub.cfg').read_text()
        assert 'set default="'+default+'"' in cfg and all(s in cfg for s in ids.values())
        for n,h in {**boot,**old_modules}.items():
            if n!='/boot/grub/grub.cfg':assert rt.digest(Path(n))==h,n
        installed={str(p):rt.digest(p) for p in Path('/lib/modules',RELEASE).rglob('*') if p.is_file() and not p.is_symlink()}
        installed.update({str(p):rt.digest(p) for p in Path('/boot').glob('*-'+RELEASE) if p.is_file()})
        rt.write_json(log/'installed-sha256.json',installed)
        state.update(state='COMPLETE',passed=True,recovery_unchanged=True,recovery_default=default,
            boot_entries=ids,modules=len(targets['modules']),snapshot_tag='before-mutex-kdonly-20261017T140354Z',
            kernel_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),installed_manifest_sha256=rt.digest(log/'installed-sha256.json'))
        rt.command(['umount',TREE],log/'unmount.log');TREE.rmdir()
        rt.command(['rmmod','overlay'],log/'overlay-unload.log');shutil.rmtree(RAM)
        shutil.rmtree(Path(package['temporary_directory']))
        runpy.run_path(str(BASE/'control/hydrate.py'))['hydrate']()
        assert verify(BUNDLE,TREE,build=True)['ok']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected
        runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
        binaries={}
        for family,module in [('body','kd_mm_body_test'),('fault_body','kd_mm_fault_test'),
                ('unmap_body','kd_mm_unmap_test'),('populated_unmap','kd_mm_populated_test'),('partial_unmap',None),('resident_partial',None)]:
            paths=[BASE/'probes-1'/family/'client']
            if module:paths.append(BASE/'probes-1'/family/'payload'/(module+'.ko'))
            binaries[family]={str(p.relative_to(BASE)):rt.digest(p) for p in paths}
        rt.write_json(buildlog/'result.json',dict(passed=True,installed=True,booted=False,source_commit=inputs['commit'],
            reused_build=str(BASE/'build-1'),installation=str(log),binaries=binaries,probe_directory=str(BASE/'probes-1'),
            baseline=str(BUNDLE),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),
            parent_manifest_sha256=manifest['parent_manifest_sha256'],runtime_modules=73,unchanged_clients_reused=5,
            kernel_snapshot=str(TREE),persistent_identity=str(snapshot),temporary_build_mount_removed=True,
            incremental_compilations=sum(len(re.findall(r'^\s*CC\s',p.read_text(),re.M)) for p in (BASE/'build-1').glob('*.log'))))
    except BaseException as error:state.update(passed=False,error=repr(error));raise
    finally:rt.write_json(log/'result.json',state)
    print(json.dumps(dict(passed=True,build='build-2',reused_compiled_outputs=True)))


if __name__=='__main__':main()
