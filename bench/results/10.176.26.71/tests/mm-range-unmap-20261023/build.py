#!/usr/bin/env python3
"""Guest-only incremental build in a private mount namespace; preserve the lower tree."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/mm-range-unmap-20261023')
OUT = Path('/mnt/kdlock-builds/mm-range-unmap-20261023')
TREE = OUT / 'linux'
RAM = Path('/dev/shm/kd-mm-range-20261023')
LOWER = Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux')
PARENT = Path('/root/kdlock-kernel-baselines/mmap-kdmm5-20261022')
BUNDLE = Path('/root/kdlock-kernel-baselines/mmap-kdmm6-20261023')
sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
command = runpy.run_path('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/build-control-1/build.py')['command']
verify = runpy.run_path(str(ROOT/'kernel_baseline/verify.py'))['verify']


def save(path, value):
    rt.write_json(path, value)


def idle():
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, default=1)
    a = parser.parse_args()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert os.readlink('/proc/self/ns/mnt') != os.readlink('/proc/1/ns/mnt'), 'private mount namespace required'
    idle()
    assert os.environ['KDLOCK_SNAPSHOT_TAG'] == 'before-mutex-kdonly-20261017T140354Z'
    inputs = json.loads((BASE/'control/inputs.json').read_text())
    os.environ['PYTHONPATH'] = str(ROOT/'bench/spin_cacheline')
    for name, digest in inputs['files'].items():
        assert rt.digest(ROOT/name) == digest, name
    host = json.loads((BASE/'control/host.json').read_text())
    assert host['pins_verified'] and host['snapshot_listed'] and len(host['qemu']) == 1
    assert host['qemu'][0]['pid'] == 257489
    expected = json.loads(Path('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/final-health.json').read_text())['modules']
    assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines()) == expected
    assert verify(PARENT, LOWER, build=True)['ok']
    parent = json.loads((PARENT/'manifest.json').read_text())
    log = BASE/('build-'+str(a.attempt)); log.mkdir()
    state = dict(passed=False, installed=False, booted=False, attempt=a.attempt,
                 source_commit=inputs['commit'], parent_manifest_sha256=rt.digest(PARENT/'manifest.json'))
    save(log/'result.json', state)
    if not OUT.exists():
        assert shutil.disk_usage('/mnt/kdlock-builds').free > 900_000_000
        assert shutil.disk_usage('/').free > 500_000_000
        OUT.mkdir(); TREE.mkdir(); RAM.mkdir()
        (RAM/'upper').mkdir(); (RAM/'work').mkdir()
        recovery = BASE/'recovery'; recovery.mkdir()
        names = [p for p in Path('/boot').glob('*-6.1.159-*') if p.is_file()]
        names += [Path('/boot/grub/grub.cfg'), Path('/etc/default/grub')]
        names += [p for d in ('/etc/default/grub.d','/etc/grub.d') for p in Path(d).glob('*') if p.is_file()]
        save(recovery/'boot-sha256.json', {str(p):rt.digest(p) for p in names})
        # Existing recovery files stay in place; retain only the small manifest
        # and the GRUB bytes that adding a new boot entry will change.
        shutil.copyfile('/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/build-control-1/recovery/modules-sha256.json', recovery/'modules-sha256.json')
        shutil.copyfile('/boot/grub/grub.cfg', recovery/'grub-before.cfg')
        save(BASE/'control/expected-guest.json', dict(modules=expected, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
    command(['modprobe','overlay'], log/'overlay-load.log', 30)
    command(['mount','-t','overlay','overlay','-o',f'lowerdir={LOWER},upperdir={RAM}/upper,workdir={RAM}/work',TREE], log/'mount.log', 30)
    try:
        changed = 'mm/kd_mmap_unmap.inc'
        source = ROOT/'kernel_integration/mmap_lock/overlay'/changed
        if not (OUT/'kernel-built.json').exists():
            shutil.copyfile(source, TREE/changed)
            config = (LOWER/'.config').read_text().replace('CONFIG_LOCALVERSION="-kdmm5"','CONFIG_LOCALVERSION="-kdmm6"')
            assert config != (LOWER/'.config').read_text()
            (TREE/'.config').write_text(config)
            command(['make','olddefconfig'], log/'config.log', 120, cwd=TREE)
            assert (TREE/'.config').read_text() == config
            command(['make','-j16','bzImage'], log/'image.log', 1800, cwd=TREE)
            save(OUT/'kernel-built.json', dict(passed=True,source_sha256=rt.digest(source), image_sha256=rt.digest(TREE/'arch/x86/boot/bzImage')))
        else:
            assert json.loads((OUT/'kernel-built.json').read_text())['source_sha256'] == rt.digest(source)
        targets = json.loads((ROOT/'bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/module-targets.json').read_text())
        if not (OUT/'modules-build-2.json').exists():
            serio = 'drivers/input/serio/serio_raw.ko'
            command(['make','-j16',*[n for n in targets if n != serio]],log/'runtime-modules.log',600,cwd=TREE)
            shutil.copyfile(TREE/'Module.symvers',OUT/'runtime-Module.symvers')
            command(['make','-j1','M=drivers/input/serio','serio_raw.ko'],log/'serio.log',180,cwd=TREE)
            symbols = {}
            for path in (TREE/'vmlinux.symvers',OUT/'runtime-Module.symvers',TREE/'drivers/input/serio/Module.symvers'):
                for line in path.read_text().splitlines():
                    name = line.split()[1]
                    assert name not in symbols or symbols[name] == line
                    symbols[name] = line
            (TREE/'Module.symvers').write_text('\n'.join(symbols[n] for n in sorted(symbols))+'\n')
            # The implementation is internal: no exported symbol CRC changed.
            assert (TREE/'vmlinux.symvers').read_bytes() == (LOWER/'vmlinux.symvers').read_bytes()
            save(OUT/'modules-build-2.json',dict(passed=True,modules={n:rt.digest(TREE/n) for n in targets}))
        probes = BASE/('probes-'+str(a.attempt)); probes.mkdir()
        binaries = {}
        for name,module in [('populated_unmap','kd_mm_populated_test'),('body','kd_mm_body_test'),
                            ('fault_body','kd_mm_fault_test'),('unmap_body','kd_mm_unmap_test')]:
            dest = probes/name
            shutil.copytree(ROOT/'tests/kernel/mmap_lock'/name,dest,
                            ignore=shutil.ignore_patterns('__pycache__','*.o','*.ko','*.cmd','Module.symvers','modules.order','client'))
            command(['make','-C',dest/'payload','KDIR='+str(TREE),'W=1','UBSAN_SANITIZE=n'],log/(name+'-module.log'),180)
            command(['cc','-pthread','-O2','-Wall','-Wextra','-Werror','-o',dest/'client',dest/'client.c'],log/(name+'-client.log'),120)
            binaries[name] = {str(p.relative_to(BASE)):rt.digest(p) for p in (dest/'client',dest/'payload'/(module+'.ko'))}
        command([sys.executable,probes/'populated_unmap/test_receipts.py'],log/'receipts.log',60)
        command(['make','-C',ROOT/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],log/'basic.log',180)
        outputs = dict(parent['source_files']); outputs[changed] = rt.digest(TREE/changed)
        prepared = dict(passed=True,source_tree=str(TREE),release='6.1.159-kdmm6',outputs=outputs,
                        config_sha256=rt.digest(TREE/'.config'),patch_sha256=rt.digest(ROOT/'kernel_integration/mmap_lock/guest-kernel.patch'),
                        incremental_parent=str(LOWER),parent_manifest_sha256=rt.digest(PARENT/'manifest.json'))
        save(OUT/'prepare.json',prepared)
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/capture.py','--prepared',OUT,'--output',BUNDLE,'--parent',PARENT],log/'capture.log',180)
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/install.py','--prepared',OUT,'--baseline',BUNDLE,
                 '--recovery-record',BASE/'recovery','--output',BASE/'install'],log/'install.log',600)
        # Preserve exact verification inputs, not a duplicate full build tree.
        # Live tests use the four already-built probes; this is an identity
        # snapshot, not a fresh external-module build directory.
        manifest = json.loads((BUNDLE/'manifest.json').read_text())
        snapshot = OUT/'snapshot'; snapshot.mkdir()
        for name,digest in {**manifest['source_files'],**manifest['build_files'],'.config':prepared['config_sha256']}.items():
            dst=snapshot/name;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(TREE/name,dst);assert rt.digest(dst)==digest
        save(log/'changed-build-paths.json',sorted(str(p.relative_to(RAM/'upper')) for p in (RAM/'upper').rglob('*') if p.is_file()))
        command(['umount',TREE],log/'unmount.log',30)
        TREE.rmdir();snapshot.rename(TREE)
        command(['rmmod','overlay'],log/'overlay-unload.log',30)
        shutil.rmtree(RAM)  # Only this new disposable RAM build workspace.
        assert verify(PARENT,LOWER,build=True)['ok']
        assert verify(BUNDLE,TREE,build=True)['ok']
        assert sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines()) == expected
        idle()
        state.update(passed=True,installed=True,binaries=binaries,probe_directory=str(probes),baseline=str(BUNDLE),
                     kernel_snapshot=str(TREE),baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),
                     runtime_modules=len(targets),parent_build_unchanged=True,temporary_mounts_removed=True,
                     incremental_compilations=sum(len(re.findall(r'^\s*CC\s',p.read_text(),re.M)) for p in log.glob('*.log')))
    except BaseException as error:
        state.update(error=repr(error))
        raise
    finally:
        save(log/'result.json',state)
    print(json.dumps(state),flush=True)


if __name__ == '__main__':main()
