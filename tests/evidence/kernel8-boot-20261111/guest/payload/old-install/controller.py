#!/usr/bin/env python3
"""One-off stage/check/install/arm controller. Never boots or loads a module.

Prepared and source-reviewed only. Execution belongs to the authorized guest
controller after the reviewed kernel8 built-image and NLS stage receipts and real recovery/idle review.
No phase automatically retries, removes partial state or overwrites old kernels.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import runpy
import stat
import subprocess
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
CORE_RECIPE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/full-build.py')
CORE_RECIPE_SHA = 'cf062063edb80334b09734db4461d4c4fcd66c486909c04a3ddac3afa115990e'
SOURCE, BUILD = BASE / 'source', BASE / 'build'
STAGE = BASE / 'install-stage-kdrebuild8-api-01'
RECEIPTS = BASE / 'receipts/install-kdrebuild8-api-01'
RELEASE = '7.0.0-38-kdrebuild8'
EXPECTED_CORE = '0d42063ead37dc8fc1631fa56c8348890ede9c5f'
FULL, LIMITED = None, STAGE / 'limited'
INITRD = STAGE / ('initrd.img-' + RELEASE)
MODULE_ROOT = Path('/lib/modules').resolve()
REQUIRED = ('virtio_pci', 'virtio_scsi', 'sd_mod', 'ext4', 'virtio_net',
            'efivarfs', 'vfat', 'nls_iso8859_1')
INITRD_REQUIRED = REQUIRED[:4]
ROOT_RESERVE = 1024 ** 3
ENTRY = 'kdlock-kdrebuild8-api-01'
GRUB_BEFORE_SHA = '4cb0e54c275387c4e725b1dc3d6c69393ec98207a5ea71d1c736c227b5eb93be'
CUSTOM_BEFORE_SHA = '10704ea47ac50dfef89b9a0f2a6870f668bbaf7bb4935254d14f4c2dea829255'
# Body/load flags are the actual normal entry, with only this candidate's
# title, ID and image/initrd release changed. Existing menus stay byte-exact.
MENU_APPEND = b"""
# BEGIN kdlock-kdrebuild8-api-01
menuentry 'KDLock Linux 7 native API (7.0.0-38-kdrebuild8)' --class ubuntu --class gnu-linux --class gnu --class os --id 'kdlock-kdrebuild8-api-01' {
    recordfail
    load_video
    set gfxpayload=$linux_gfx_mode
    insmod gzio
    if [ x$grub_platform = xxen ]; then insmod xzio; insmod lzopio; fi
    insmod part_gpt
    insmod ext2
    set root='hd0,gpt1'
    if [ x$feature_platform_search_hint = xy ]; then
      search --no-floppy --fs-uuid --set=root --hint-bios=hd0,gpt1 --hint-efi=hd0,gpt1 --hint-baremetal=ahci0,gpt1  aa0bde06-47f6-4049-aaaf-13d052e53961
    else
      search --no-floppy --fs-uuid --set=root aa0bde06-47f6-4049-aaaf-13d052e53961
    fi
    echo 'Loading Linux 7.0.0-38-kdrebuild8 ...'
    linux /boot/vmlinuz-7.0.0-38-kdrebuild8 root=UUID=aa0bde06-47f6-4049-aaaf-13d052e53961 ro nokaslr nopvspin console=tty1 console=ttyS0
    echo 'Loading initial ramdisk ...'
    initrd /boot/initrd.img-7.0.0-38-kdrebuild8
}
# END kdlock-kdrebuild8-api-01
"""
EVENTS = None
PHASE = None


def digest(path):
    result = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                return result.hexdigest()
            result.update(block)


def linked_recipe():
    if CORE_RECIPE.resolve(strict=True) != CORE_RECIPE or digest(CORE_RECIPE) != CORE_RECIPE_SHA:
        raise RuntimeError('reviewed kernel8 linked/protection recipe changed')
    return runpy.run_path(str(CORE_RECIPE))


def syncdir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(name, value):
    with open(RECEIPTS / name, 'x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    syncdir(RECEIPTS)


def event(kind, **values):
    data = dict(event=kind, phase=PHASE, unix_time=time.time(), **values)
    EVENTS.write(json.dumps(data, sort_keys=True) + '\n')
    EVENTS.flush()
    os.fsync(EVENTS.fileno())
    print(json.dumps(data, sort_keys=True), flush=True)


class CommandObserverExpired(RuntimeError):
    pass


def command(label, argv, seconds):
    log = RECEIPTS / (PHASE + '-' + label + '.log')
    started = time.monotonic()
    event('command_started', label=label, argv=list(map(str, argv)), timeout_seconds=seconds)
    with open(log, 'xb') as output:
        proc = subprocess.Popen(list(map(str, argv)), stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        event('command_dispatched', label=label, pid=proc.pid)
        try:
            code = proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            # The outstanding stage/install actor retains its output file.
            # A deadline is not physical completion or permission to retry.
            result = dict(argv=list(map(str, argv)), returncode=None, pid=proc.pid,
                          timed_out=True, status='INCOMPLETE_CHILD_RETAINED',
                          elapsed_seconds=time.monotonic()-started, log=str(log),
                          log_bytes_at_observer_stop=log.stat().st_size)
            save(PHASE + '-' + label + '-result.json', result)
            event('command_observer_stopped', label=label, **result)
            raise CommandObserverExpired('command outcome pending; child retained: ' + label + ' pid=' + str(proc.pid))
        output.flush()
        os.fsync(output.fileno())
    result = dict(argv=list(map(str, argv)), returncode=code, pid=proc.pid,
                  timed_out=False, elapsed_seconds=time.monotonic()-started,
                  log=str(log), log_sha256=digest(log))
    save(PHASE + '-' + label + '-result.json', result)
    event('command_finished', label=label, **result)
    if code:
        raise RuntimeError('command failed; preserve partial state: ' + label)
    return log.read_text(errors='replace')


def check(label, mode, extra=(), seconds=600):
    output = PHASE + '-' + label + '.json'
    command(label, ['python3', RECEIPTS / 'checks.py', mode,
                    '--output', RECEIPTS / output, *extra], seconds)
    return json.loads((RECEIPTS / output).read_text())


def ready(phase):
    data = json.loads((RECEIPTS / (phase + '-complete.json')).read_text())
    if data.get('status') != 'COMPLETE':
        raise RuntimeError('prior phase not complete: ' + phase)
    return data


def verify_records(rows):
    for row in rows:
        path = Path(row['path'])
        if 'symlink' in row:
            if not path.is_symlink() or os.readlink(path) != row['symlink']:
                raise RuntimeError('retained link changed: ' + str(path))
            continue
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('expected regular retained file: ' + str(path))
        if path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            raise RuntimeError('retained bytes changed: ' + str(path))
        if 'mode' in row and stat.S_IMODE(path.stat().st_mode) != row['mode']:
            raise RuntimeError('retained mode changed: ' + str(path))


def menu_metadata(value):
    return dict(device=value.st_dev, inode=value.st_ino, mode=stat.S_IMODE(value.st_mode),
                uid=value.st_uid, gid=value.st_gid, nlink=value.st_nlink)


def prepare_menu():
    grub, custom = Path('/boot/grub/grub.cfg'), Path('/boot/grub/custom.cfg')
    if grub.is_symlink() or custom.is_symlink() or not custom.is_file():
        raise RuntimeError('actual existing regular GRUB menu sources required')
    if grub.stat().st_size > 1024*1024 or custom.stat().st_size != 9216:
        raise RuntimeError('reviewed GRUB source extents differ')
    original, prefix = grub.read_bytes(), custom.read_bytes()
    loader = (b'if [ -f  ${config_directory}/custom.cfg ]; then\n'
              b'  source ${config_directory}/custom.cfg\n')
    if (hashlib.sha256(original).hexdigest() != GRUB_BEFORE_SHA or
        hashlib.sha256(prefix).hexdigest() != CUSTOM_BEFORE_SHA or
        digest(RECEIPTS/'grub.cfg-before') != GRUB_BEFORE_SHA or
        digest(grub) != GRUB_BEFORE_SHA or digest(custom) != CUSTOM_BEFORE_SHA or
        loader not in original or ENTRY.encode() in original + prefix or
        custom.stat().st_nlink != 1):
        raise RuntimeError('reviewed existing custom loader/menu prefix differs')
    for name, data in (('custom.cfg-before', prefix), ('candidate-entry.cfg', MENU_APPEND)):
        with (RECEIPTS/name).open('xb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    combined = STAGE/'custom.cfg-expected'
    with combined.open('xb') as output:
        output.write(prefix + MENU_APPEND)
        output.flush()
        os.fsync(output.fileno())
    command('candidate-menu-syntax', ['grub-script-check', combined], 30)
    command('existing-grub-syntax', ['grub-script-check', grub], 30)
    save('stage-grub-sources.json', dict(grub_cfg_sha256=GRUB_BEFORE_SHA,
         custom_cfg_before_sha256=CUSTOM_BEFORE_SHA, custom_cfg_before_size=len(prefix),
         custom_cfg_metadata=menu_metadata(custom.stat()), append_bytes=len(MENU_APPEND),
         append_sha256=hashlib.sha256(MENU_APPEND).hexdigest(),
         custom_cfg_after_sha256=hashlib.sha256(prefix + MENU_APPEND).hexdigest(),
         custom_cfg_after_size=len(prefix + MENU_APPEND), candidate_entry=ENTRY))


def append_candidate_menu():
    snapshot = json.loads((RECEIPTS/'stage-grub-sources.json').read_text())
    prefix = (RECEIPTS/'custom.cfg-before').read_bytes()
    expected = STAGE/'custom.cfg-expected'
    custom = Path('/boot/grub/custom.cfg')
    if (digest('/boot/grub/grub.cfg') != snapshot['grub_cfg_sha256'] or
        hashlib.sha256(prefix).hexdigest() != snapshot['custom_cfg_before_sha256'] or
        expected.read_bytes() != prefix + MENU_APPEND):
        raise RuntimeError('reviewed unchanged GRUB prefix or candidate append differs')
    command('candidate-menu-syntax', ['grub-script-check', expected], 30)
    fd = os.open(custom, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size != len(prefix) or
            menu_metadata(metadata) != snapshot['custom_cfg_metadata']):
            raise RuntimeError('existing custom menu identity/mode changed')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            if stream.read(len(prefix)+1) != prefix:
                raise RuntimeError('existing custom menu prefix changed before append')
        written = 0
        while written < len(MENU_APPEND):
            count = os.write(fd, MENU_APPEND[written:])
            if count <= 0:
                raise RuntimeError('candidate append stopped; preserve partial state')
            written += count
        os.fsync(fd)
        if menu_metadata(os.fstat(fd)) != snapshot['custom_cfg_metadata']:
            raise RuntimeError('custom menu file identity/mode changed during append')
    finally:
        os.close(fd)
    syncdir(custom.parent)
    if (custom.read_bytes() != prefix + MENU_APPEND or
        menu_metadata(custom.stat()) != snapshot['custom_cfg_metadata'] or
        digest('/boot/grub/grub.cfg') != snapshot['grub_cfg_sha256']):
        raise RuntimeError('GRUB old-prefix preservation or candidate suffix differs')
    save('install-grub-append.json', dict(**snapshot, old_prefix_preserved=True,
         grub_cfg_unchanged=True, custom_cfg_sha256=digest(custom)))


def module_table(data):
    root = Path(data['root'])
    return sorted((str(Path(row['path']).relative_to(root)), row['size'],
                   row['sha256'], row['mode']) for row in data['modules'])


def required_closure(root):
    rows = {}
    prefix = root / 'lib/modules' / RELEASE
    for name in REQUIRED:
        flags = ['-d', root] if root != Path('/') else []
        text = command('dependencies-' + name,
                       ['modprobe', *flags, '-S', RELEASE, '--show-depends', name], 20)
        paths = []
        builtin = False
        for line in text.splitlines():
            words = shlex.split(line)
            if not words:
                continue
            if words[0] == 'builtin' and len(words) == 2:
                builtin = True
                continue
            if words[0] != 'insmod' or len(words) != 2:
                raise RuntimeError('unrecognized dependency row: ' + line)
            path = Path(words[1])
            if not path.is_absolute() or path.is_symlink():
                raise RuntimeError('noncanonical dependency: ' + str(path))
            candidate = path.resolve(strict=True)
            relative = candidate.relative_to(prefix.resolve(strict=True))
            if not candidate.is_file() or not relative.name.endswith(('.ko', '.ko.zst')):
                raise RuntimeError('non-module dependency: ' + str(candidate))
            paths.append(str(relative))
        if not (builtin or paths):
            raise RuntimeError('no dependency result: ' + name)
        rows[name] = dict(builtin=builtin, modules=paths)
    return rows


def stage_limited():
    full = FULL / 'lib/modules' / RELEASE
    names = sorted({path for row in required_closure(FULL).values() for path in row['modules']})
    if names != ['kernel/fs/nls/nls_iso8859-1.ko']:
        raise RuntimeError('actual boot dependency closure differs from rebuilt NLS module')
    limited = LIMITED / 'lib/modules' / RELEASE
    limited.mkdir(parents=True, mode=0o755)
    for name in ('modules.builtin', 'modules.builtin.modinfo'):
        shutil.copy2(full / name, limited / name)
    order = (full / 'modules.order').read_text().splitlines()
    if not set(names) <= set(order):
        raise RuntimeError('closure paths absent from normal modules.order')
    (limited / 'modules.order').write_text(''.join(name + '\n' for name in order if name in names))
    for name in names:
        target = limited / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full / name, target)
    shutil.copy2(BUILD / '.config', limited / ('config-' + RELEASE))
    command('depmod-limited', ['depmod', '-a', '-b', LIMITED, '-e', '-F',
                              BUILD/'System.map', RELEASE], 120)
    conf, temp = STAGE / 'initramfs-config', STAGE / 'initramfs-temp'
    shutil.copytree('/etc/initramfs-tools', conf, symlinks=True)
    if (conf / 'modules').is_symlink() or (conf / 'conf.d').is_symlink():
        raise RuntimeError('private initramfs config override is a symlink')
    (conf / 'conf.d').mkdir(exist_ok=True)
    with (conf / 'conf.d/zz-kdlock-limited').open('x') as output:
        output.write('MODULES=list\n')
    with (conf / 'modules').open('a') as output:
        output.write('\n' + '\n'.join(INITRD_REQUIRED) + '\n')
    temp.mkdir(mode=0o700)
    script = ('set -eu; mount --bind "$1/lib/modules" /lib/modules; '
              'exec env TMPDIR="$2" modules=list mkinitramfs -d "$3" -o "$4" "$5"')
    command('initramfs-off-root', ['unshare', '--mount', '--propagation', 'private',
                                 '/bin/sh', '-c', script, 'kdrebuild8-initramfs',
                                 LIMITED, temp, conf, INITRD, RELEASE], 300)
    if not INITRD.is_file() or INITRD.is_symlink():
        raise RuntimeError('expected staged regular initramfs')
    save('stage-closure.json', dict(modules=names, namespace=str(limited)))


def verify_initrd(initrd, closure):
    listing = command('initrd-list', ['lsinitramfs', initrd], 120).splitlines()
    for name in ('init', 'scripts/local'):
        if name not in listing:
            raise RuntimeError('required local-root initramfs entry missing: ' + name)
    for name in INITRD_REQUIRED:
        for relative in closure[name]['modules']:
            base = 'lib/modules/' + RELEASE + '/' + relative
            if not any(line == base or line.endswith('/' + base) for line in listing):
                raise RuntimeError('required module absent from initramfs: ' + relative)
    foreign = [line for line in listing if 'lib/modules/' in line and
               line.split('lib/modules/', 1)[1].split('/', 1)[0] != RELEASE]
    if foreign:
        raise RuntimeError('initramfs contains a different module release')


def tree_table(root):
    rows = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('symlink in the limited namespace: ' + str(path))
        if path.is_file():
            statinfo = path.stat()
            rows.append(dict(name=str(path.relative_to(root)), size=statinfo.st_size,
                             mode=stat.S_IMODE(statinfo.st_mode), sha256=digest(path)))
        elif not path.is_dir():
            raise RuntimeError('nonregular namespace entry: ' + str(path))
    return rows


def budget(config):
    if not (os.stat('/').st_dev == os.stat('/boot').st_dev == os.stat(MODULE_ROOT).st_dev):
        raise RuntimeError('root/boot/modules filesystem layout changed')
    fs = os.statvfs('/')
    def blocks(size):
        return ((size + fs.f_frsize - 1) // fs.f_frsize) * fs.f_frsize
    limited = LIMITED / 'lib/modules' / RELEASE
    entries = [limited, *limited.rglob('*')]
    module_bytes = sum(blocks(p.stat().st_size) if p.is_file() else fs.f_frsize for p in entries)
    boot = sum(blocks((BUILD/name).stat().st_size) for name in
               ('arch/x86/boot/bzImage', 'System.map', '.config'))
    initrd = blocks(INITRD.stat().st_size)
    free = fs.f_bavail * fs.f_frsize
    needed = module_bytes + boot + initrd + ROOT_RESERVE + config['root_working_bytes']
    if free <= needed:
        raise RuntimeError('measured limited install cannot preserve reserve: ' + str((free, needed)))
    return dict(root_free=free, limited_namespace_bytes=module_bytes, boot_bytes=boot,
                initrd_bytes=initrd, root_reserve_bytes=ROOT_RESERVE,
                root_working_bytes=config['root_working_bytes'], needed=needed)


def verify_linked(config):
    build_path = Path(config['final_build_receipt'])
    final_path = Path(config['final_identity'])
    if digest(build_path) != config['final_build_receipt_sha256'] or digest(final_path) != config['final_identity_sha256']:
        raise RuntimeError('reviewed build/linked receipt changed')
    build = json.loads(build_path.read_text())
    final = json.loads(final_path.read_text())
    if (build.get('status') != 'BUILT_AND_LINKED_IDENTITY_VERIFIED' or
        build.get('core_git_head') != EXPECTED_CORE or build.get('kernelrelease') != RELEASE or
        build.get('source') != str(SOURCE) or build.get('build') != str(BUILD)):
        raise RuntimeError('reviewed native API core/build receipt differs')
    for name, expected in final['files'].items():
        file = BUILD/name
        if file.stat().st_size != expected['bytes'] or digest(file) != expected['sha256']:
            raise RuntimeError('linked kernel8 artifact differs: ' + name)
    focused_path = Path(build['focused_receipt'])
    if digest(focused_path) != build['focused_sha256']:
        raise RuntimeError('retained focused prerequisite changed')
    focused = json.loads(focused_path.read_text())
    if (focused['status'] != 'FOCUSED_COMPILE_COMPLETE' or
        focused['target_units'] != dict(core=33, native=8) or
        focused['core_git_head'] != EXPECTED_CORE or focused['kernelrelease'] != RELEASE):
        raise RuntimeError('actual 33+8 focused prerequisite differs')
    for root, rows in ((SOURCE/'kernel/kdlock', focused['package_after']),
                       (SOURCE, focused['integration_after']), (SOURCE, focused['body_after'])):
        for name, expected in rows.items():
            if digest(root/name) != expected:
                raise RuntimeError('linked kernel8 source differs: ' + str(root/name))
    functions = linked_recipe()
    if (functions['protected'](focused) != build['protected_after'] or
        functions['source_pins'](focused, SOURCE) != build['source_after']):
        raise RuntimeError('kernel8 and retained normal/kernel6/kernel7 source/output/provenance changed')
    verify_offroot(config)
    notes = command('exact-build-id', ['readelf', '-n', BUILD/'vmlinux'], 30)
    if [line.split()[-1] for line in notes.splitlines() if 'Build ID:' in line] != [final['build_id']]:
        raise RuntimeError('linked kernel8 ELF BuildID differs')


def verify_offroot(config):
    path = Path(config['offroot_receipt'])
    if digest(path) != config['offroot_receipt_sha256']:
        raise RuntimeError('reviewed off-root stage receipt changed')
    staged = json.loads(path.read_text())
    if (staged.get('status') != 'OFFROOT_MODULE_STAGE_COMPLETE' or
        staged.get('core_git_head') != EXPECTED_CORE or staged.get('kernelrelease') != RELEASE or
        staged.get('source') != str(SOURCE) or staged.get('build') != str(BUILD) or
        staged['stage']['build_receipt_sha256'] != config['final_build_receipt_sha256']):
        raise RuntimeError('successful exact NLS off-root stage required')
    root = Path(staged['stage']['root'])
    if (root != FULL or root.resolve(strict=True) != root or
        BASE/'receipts' not in root.parents or root.stat().st_dev == Path('/').stat().st_dev):
        raise RuntimeError('off-root stage is outside the reviewed candidate receipts')
    module = root/'lib/modules'/RELEASE/'kernel/fs/nls/nls_iso8859-1.ko'
    if (str(module) != staged['stage']['module'] or module.resolve(strict=True) != module or
        digest(module) != staged['stage']['sha256'] or module.stat().st_size != staged['stage']['bytes'] or
        list((root/'lib/modules'/RELEASE/'kernel').rglob('*.ko')) != [module] or
        (root/'lib/modules'/RELEASE/'modules.order').read_text().splitlines() !=
        ['kernel/fs/nls/nls_iso8859-1.ko']):
        raise RuntimeError('off-root NLS module bytes or exact limited order changed')


def stage(args):
    if STAGE.exists() or RECEIPTS.exists():
        raise RuntimeError('fresh stage and receipt required')
    if args.root_working_bytes <= 0:
        raise RuntimeError('explicit root GRUB/metadata working budget required')
    for name in ('final_build_receipt', 'offroot_receipt', 'recovery_receipt'):
        path = Path(getattr(args, name))
        expected = getattr(args, name + '_sha256')
        if len(expected) != 64 or digest(path) != expected:
            raise RuntimeError('controller receipt hash mismatch: ' + name)
    build = json.loads(Path(args.final_build_receipt).read_text())
    if (build['status'] != 'BUILT_AND_LINKED_IDENTITY_VERIFIED' or
        build['kernelrelease'] != RELEASE or build.get('core_git_head') != EXPECTED_CORE or
        any(row['returncode'] != 0 for row in build['commands']) or
        build.get('phase') != 'build' or len(build['commands']) != 7 or
        {row['label'] for row in build['commands']} != {'kernel', 'nls', 'module-vermagic',
            'module-dependencies', 'elf-notes', 'elf-symbols', 'gs-disassembly'}):
        raise RuntimeError('reviewed successful actual kernel/NLS metadata receipt required')
    final = Path(args.final_build_receipt).with_name('final-identity.json')
    if digest(final) != build['final_identity_sha256']:
        raise RuntimeError('linked identity receipt hash differs')
    identity = json.loads(final.read_text())
    if identity['module_count'] != 1 or identity['module_vermagic'].split()[0] != RELEASE:
        raise RuntimeError('expected linked kernel8 with exact single NLS module release')
    if BASE.stat().st_dev == Path('/').stat().st_dev:
        raise RuntimeError('staging is no longer off the root filesystem')
    fs = os.statvfs(BASE)
    if fs.f_bavail * fs.f_frsize < 4_000_000_000:
        raise RuntimeError('less than 4GB off-root stage headroom')
    STAGE.mkdir(mode=0o700)
    RECEIPTS.mkdir(mode=0o700)
    syncdir(STAGE.parent)
    syncdir(RECEIPTS.parent)
    return dict(root_reserve_bytes=ROOT_RESERVE, root_working_bytes=args.root_working_bytes,
                final_build_receipt=args.final_build_receipt,
                final_build_receipt_sha256=args.final_build_receipt_sha256,
                offroot_receipt=args.offroot_receipt,
                offroot_receipt_sha256=args.offroot_receipt_sha256,
                final_identity_sha256=build['final_identity_sha256'],
                final_identity=str(final), recovery_receipt=args.recovery_receipt,
                recovery_receipt_sha256=args.recovery_receipt_sha256,
                kernel_code_commit=build['core_git_head'],
                linked_recipe=str(CORE_RECIPE), linked_recipe_sha256=CORE_RECIPE_SHA)


def require_fresh_targets():
    paths = [Path('/lib/modules') / RELEASE]
    paths += [Path('/boot') / (prefix + RELEASE) for prefix in
              ('vmlinuz-', 'System.map-', 'config-', 'initrd.img-')]
    if any(os.path.lexists(path) for path in paths):
        raise RuntimeError('candidate installed namespace is not fresh')


def main():
    global EVENTS, PHASE, FULL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('stage', 'check', 'install', 'arm'))
    parser.add_argument('--controller-idle-recovery-confirmed', action='store_true')
    parser.add_argument('--final-build-success-reviewed', action='store_true')
    parser.add_argument('--final-build-receipt')
    parser.add_argument('--final-build-receipt-sha256')
    parser.add_argument('--offroot-receipt')
    parser.add_argument('--offroot-receipt-sha256')
    parser.add_argument('--recovery-receipt')
    parser.add_argument('--recovery-receipt-sha256')
    parser.add_argument('--root-working-bytes', type=int)
    parser.add_argument('--checks', default=str(Path(__file__).with_name('kdlock-kdrebuild8-checks.py')))
    args = parser.parse_args()
    PHASE = args.phase
    if os.geteuid() != 0 or not args.controller_idle_recovery_confirmed:
        parser.error('guest root and actual prior controller idle/recovery review required')
    if args.phase == 'stage':
        required = (args.final_build_success_reviewed, args.final_build_receipt,
                    args.final_build_receipt_sha256, args.offroot_receipt,
                    args.offroot_receipt_sha256, args.recovery_receipt,
                    args.recovery_receipt_sha256, args.root_working_bytes)
        if not all(required):
            parser.error('stage needs final-build/recovery receipts+hashes and explicit budgets')
        config = stage(args)
        shutil.copyfile(args.checks, RECEIPTS / 'checks.py')
        shutil.copyfile(__file__, RECEIPTS / 'controller.py')
        save('configuration.json', config)
        save('helper-hashes.json', {name: digest(RECEIPTS/name) for name in ('checks.py', 'controller.py')})
    else:
        config = json.loads((RECEIPTS / 'configuration.json').read_text())
        for name, expected in json.loads((RECEIPTS/'helper-hashes.json').read_text()).items():
            if digest(RECEIPTS/name) != expected:
                raise RuntimeError('retained helper changed')
        if digest(__file__) != digest(RECEIPTS/'controller.py'):
            raise RuntimeError('different controller from stage')
    offroot = Path(config['offroot_receipt'])
    if digest(offroot) != config['offroot_receipt_sha256']:
        raise RuntimeError('retained off-root receipt changed')
    FULL = Path(json.loads(offroot.read_text())['stage']['root'])
    EVENTS = open(RECEIPTS / (PHASE+'-journal.jsonl'), 'x', encoding='utf-8')
    syncdir(RECEIPTS)
    try:
        event('phase_started')
        check('idle', 'idle', seconds=30)
        verify_linked(config)
        if PHASE == 'stage':
            require_fresh_targets()
            check('protected-before', 'protect')
            identity = check('identity-before', 'identity', seconds=120)
            shutil.copyfile('/boot/grub/grub.cfg', RECEIPTS/'grub.cfg-before')
            prepare_menu()
            save('identity-pin.json', identity)
            verify_offroot(config)
            stage_limited()
            if digest(Path(config['final_identity'])) != config['final_identity_sha256']:
                raise RuntimeError('linked identity changed while staging')
        elif PHASE == 'check':
            ready('stage')
            current = check('identity-after-stage', 'identity', seconds=120)
            if current != json.loads((RECEIPTS/'identity-pin.json').read_text()):
                raise RuntimeError('build/source/tools changed during stage')
            modules = check('modules-stage', 'modules', ('--root', str(LIMITED)), seconds=120)
            closure = required_closure(LIMITED)
            names = sorted({path for row in closure.values() for path in row['modules']})
            limited = LIMITED/'lib/modules'/RELEASE
            if names != sorted(str(Path(row['path']).relative_to(limited)) for row in modules['modules']):
                raise RuntimeError('limited module inventory differs from exact dependency closure')
            verify_initrd(INITRD, closure)
            save('limited-stage.json', dict(closure=closure, namespace=tree_table(limited),
                 initrd=dict(size=INITRD.stat().st_size, sha256=digest(INITRD))))
            save('root-budget.json', budget(config))
        elif PHASE == 'install':
            ready('check')
            require_fresh_targets()
            identity = json.loads((RECEIPTS/'identity-pin.json').read_text())
            verify_records(identity['artifacts'])
            verify_records(identity['package_source'])
            staged = json.loads((RECEIPTS/'check-modules-stage.json').read_text())
            verify_records(staged['modules'])
            actual_stage = json.loads((RECEIPTS/'limited-stage.json').read_text())
            limited = LIMITED/'lib/modules'/RELEASE
            if tree_table(limited) != actual_stage['namespace'] or digest(INITRD) != actual_stage['initrd']['sha256']:
                raise RuntimeError('staged limited module tree or initramfs changed')
            save('root-budget-before-install.json', budget(config))
            shutil.copytree(limited, MODULE_ROOT/RELEASE, copy_function=shutil.copy2)
            syncdir(MODULE_ROOT)
            for path in sorted((MODULE_ROOT/RELEASE).rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if path.is_dir():
                    syncdir(path)
                else:
                    with path.open('rb') as stream:
                        os.fsync(stream.fileno())
            syncdir(MODULE_ROOT/RELEASE)
            if tree_table(MODULE_ROOT/RELEASE) != actual_stage['namespace']:
                raise RuntimeError('installed limited namespace differs from staged bytes')
            installed = check('modules-installed', 'modules', ('--root', '/'), seconds=120)
            if module_table(installed) != module_table(staged):
                raise RuntimeError('installed module copy differs')
            pins = {row['path']: row['sha256'] for row in identity['artifacts']}
            boot_sources = [(BUILD/name, prefix, pins[str(BUILD/name)])
                            for name, prefix in (('arch/x86/boot/bzImage', 'vmlinuz'),
                                                 ('System.map', 'System.map'), ('.config', 'config'))]
            boot_sources.append((INITRD, 'initrd.img', actual_stage['initrd']['sha256']))
            for source, prefix, expected in boot_sources:
                data = source.read_bytes()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise RuntimeError('boot input changed')
                target = Path('/boot') / (prefix+'-'+RELEASE)
                with open(target, 'xb') as output:
                    os.fchmod(output.fileno(), 0o644)
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                if digest(target) != expected:
                    raise RuntimeError('boot copy differs: '+str(target))
            syncdir('/boot')
            append_candidate_menu()
            dependencies = required_closure(Path('/'))
            if dependencies != actual_stage['closure']:
                raise RuntimeError('installed module closure differs')
            verify_initrd(Path('/boot')/('initrd.img-' + RELEASE), dependencies)
            check('protected-after', 'verify-protected', ('--snapshot', str(RECEIPTS/'stage-protected-before.json')))
            grub = check('grub-installed', 'grub', seconds=30)
            boot = [Path('/boot')/(prefix+RELEASE) for prefix in
                    ('vmlinuz-', 'System.map-', 'config-', 'initrd.img-')]
            fs = os.statvfs('/')
            if fs.f_bavail*fs.f_frsize < config['root_reserve_bytes']:
                raise RuntimeError('root reserve consumed')
            save('installed-boot.json', dict(files=[dict(path=str(path), size=path.stat().st_size,
                 sha256=digest(path)) for path in boot], dependencies=dependencies, grub=grub))
        else:
            ready('install')
            installed = json.loads((RECEIPTS/'installed-boot.json').read_text())
            verify_records(installed['files'])
            verify_records(json.loads((RECEIPTS/'install-modules-installed.json').read_text())['modules'])
            if tree_table(MODULE_ROOT/RELEASE) != json.loads((RECEIPTS/'limited-stage.json').read_text())['namespace']:
                raise RuntimeError('installed candidate namespace changed before arm')
            fs = os.statvfs('/')
            if fs.f_bavail*fs.f_frsize < config['root_reserve_bytes']:
                raise RuntimeError('root reserve consumed before arm')
            check('protected-before-arm', 'verify-protected', ('--snapshot', str(RECEIPTS/'stage-protected-before.json')))
            before = check('grub-before-arm', 'grub', seconds=30)
            if before['grub_cfg_sha256'] != installed['grub']['grub_cfg_sha256']:
                raise RuntimeError('GRUB configuration changed after install')
            command('one-shot', ['grub-reboot', ENTRY], 30)
            after = check('grub-after-arm', 'grub', ('--armed',), seconds=30)
            if (before['grub_cfg_sha256'] != after['grub_cfg_sha256'] or
                before['custom_cfg_sha256'] != after['custom_cfg_sha256'] or {
                k:v for k,v in before['environment'].items() if k != 'next_entry'
            } != {k:v for k,v in after['environment'].items() if k != 'next_entry'}):
                raise RuntimeError('one-shot changed other GRUB state')
            command('sync', ['sync'], 30)
        command('disk-usage', ['df', '-B1', '/', '/boot', BASE], 30)
        save(PHASE+'-complete.json', dict(status='COMPLETE', phase=PHASE,
             reboot_performed=False, module_load_performed=False, unix_time=time.time()))
        event('phase_complete')
    except BaseException as error:
        save(PHASE+'-failure.json', dict(status=('INCOMPLETE_CHILD_RETAINED' if isinstance(error, CommandObserverExpired)
             else 'FAILED_NO_AUTOMATIC_RETRY'),
             phase=PHASE, error=repr(error), preserve_partial_state=True,
             one_shot_may_be_set=(PHASE == 'arm'), reboot_performed=False))
        event('phase_failed', error=repr(error))
        raise
    finally:
        EVENTS.close()


if __name__ == '__main__':
    main()
