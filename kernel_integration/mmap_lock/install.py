#!/usr/bin/env python3
"""Install a distinct approved guest experiment; retain the recovery default."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--recovery-record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.uname().release == '6.1.159-kdclobber2' and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed recovery guest required')
    rt.idle()
    prepared = json.loads((a.prepared / 'prepare.json').read_text())
    built = json.loads((a.prepared / 'modules-build-2.json').read_text())
    manifest = json.loads((a.baseline / 'manifest.json').read_text())
    tree, release = Path(prepared['source_tree']), prepared['release']
    rt.require(prepared['passed'] and built['passed'] and re.fullmatch(r'6\.1\.159-kdmm[0-9]+', release),
               'completed distinct experimental build required')
    for name, h in {**manifest['source_files'], **manifest['build_files']}.items():
        rt.require(rt.digest(tree / name) == h, 'captured kernel changed: ' + name)
    rt.require(rt.digest(tree / '.config') == manifest['bundle_files']['guest.config'], 'config changed')
    preserved = json.loads((a.recovery_record / 'boot-sha256.json').read_text())
    old_modules = json.loads((a.recovery_record / 'modules-sha256.json').read_text())
    for name, h in {**preserved, **old_modules}.items():
        rt.require(rt.digest(Path(name)) == h, 'recovery changed: ' + name)
    for name, h in built['modules'].items():
        rt.require(rt.digest(tree / name) == h, 'new module changed: ' + name)
    destination = Path('/lib/modules') / release
    entry_file = Path('/etc/grub.d') / ('42_kd_mmap_' + release.split('-')[1])
    rt.require(not destination.exists() and not entry_file.exists() and not a.output.exists(),
               'installation destination already exists; inspect before resuming')
    for kind in ('vmlinuz', 'initrd.img', 'System.map', 'config'):
        rt.require(not Path('/boot', kind + '-' + release).exists(), 'boot artifact already exists')
    a.output.mkdir(parents=True)
    result = dict(state='INSTALLING', passed=False, release=release, rebooted=False,
                  kernel_manifest_sha256=rt.digest(a.baseline / 'manifest.json'),
                  snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], modules=len(built['modules']))
    rt.write_json(a.output / 'result.json', result)
    try:
        # Kbuild signs each fresh module with this image's generated key.
        # The new release directory was required absent; recovery paths are
        # neither installation destinations nor rollback targets.
        (tree / 'modules.order').write_text(''.join(n + '\n' for n in sorted(built['modules'])))
        rt.command(['make', 'modules_install'], a.output / 'modules-install.log', timeout=300, cwd=tree)
        depmod = rt.command(['depmod', '-e', '-F', tree / 'System.map', release],
                            a.output / 'depmod.log', timeout=60)
        rt.require(not depmod.strip(), 'module dependency diagnostics require review')
        for name in built['modules']:
            module = destination / 'kernel' / name
            signer = rt.command(['modinfo', '-F', 'signer', module],
                                a.output / (Path(name).stem + '-signer.log'))
            rt.require(signer.strip(), 'new module is unsigned: ' + name)
        for name, target in (('arch/x86/boot/bzImage', 'vmlinuz'), ('System.map', 'System.map'),
                             ('.config', 'config')):
            shutil.copyfile(tree / name, Path('/boot', target + '-' + release))
        rt.command(['mkinitramfs', '-o', '/boot/initrd.img-' + release, release],
                   a.output / 'initramfs.log', timeout=300)
        listing = rt.command(['lsinitramfs', '/boot/initrd.img-' + release],
                             a.output / 'initramfs-files.txt', timeout=90)
        rt.require('kernel/drivers/scsi/virtio_scsi.ko' in listing and
                   '6.1.159-kdclobber2' not in listing, 'initramfs boot module/release differs')
        mount = rt.command(['findmnt', '-n', '-o', 'TARGET,UUID,FSTYPE', '--target', '/boot'],
                           a.output / 'boot-filesystem.txt').split()
        rt.require(len(mount) == 3 and mount[0] == '/' and mount[2] == 'ext4' and
                   re.fullmatch('[0-9a-f-]+', mount[1]), 'unreviewed boot filesystem layout')
        args = [s for s in Path('/proc/cmdline').read_text().split() if not s.startswith('BOOT_IMAGE=')]
        rt.require(all(re.fullmatch('[A-Za-z0-9_=,./:-]+', s) for s in args) and
                   all(s in args for s in ('nokaslr', 'nopvspin')) and
                   not any(s.startswith('kd_mmap=') for s in args), 'unexpected recovery command line')
        entries = '#!/bin/sh\nexec tail -n +3 "$0"\n'
        ids = {}
        for mode, option in (('native', 'off'), ('kd', 'on')):
            entry = 'kd-mmap-' + mode + '-' + release.split('-')[1]
            ids[mode] = entry
            entries += (f"menuentry 'KD mmap {mode} {release}' --id '{entry}' {{\n"
                        '  insmod part_gpt\n  insmod part_msdos\n  insmod ext2\n'
                        f'  search --no-floppy --fs-uuid --set=root {mount[1]}\n'
                        f'  linux /boot/vmlinuz-{release} ' + ' '.join(args) + f' kd_mmap={option}\n'
                        f'  initrd /boot/initrd.img-{release}\n}}\n')
        entry_file.write_text(entries)
        entry_file.chmod(0o755)
        rt.command(['update-grub'], a.output / 'update-grub.log', timeout=120)
        cfg = Path('/boot/grub/grub.cfg').read_text()
        default = ('gnulinux-advanced-' + mount[1] + '>gnulinux-6.1.159-kdclobber2-advanced-' + mount[1])
        rt.require('set default="' + default + '"' in cfg and all(s in cfg for s in ids.values()),
                   'recovery default or experiment entries differ')
        for name, h in {**preserved, **old_modules}.items():
            if name == '/boot/grub/grub.cfg':
                continue  # New entries were added; its previous bytes are preserved.
            rt.require(rt.digest(Path(name)) == h, 'recovery changed during installation: ' + name)
        installed = {str(p): rt.digest(p) for p in destination.rglob('*') if p.is_file() and not p.is_symlink()}
        installed.update({str(p): rt.digest(p) for p in Path('/boot').glob('*-' + release) if p.is_file()})
        rt.write_json(a.output / 'installed-sha256.json', installed)
        result.update(state='COMPLETE', passed=True, recovery_unchanged=True, recovery_default=default,
                      boot_entries=ids, installed_manifest_sha256=rt.digest(a.output / 'installed-sha256.json'))
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        rt.write_json(a.output / 'result.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
