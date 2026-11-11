#!/usr/bin/env python3
"""One-off stage/check/install/arm controller. Never boots or loads a module.

Prepared and source-reviewed only. Execution belongs to the authorized guest
controller after the final reviewed kernel4 spin build and real recovery/idle review.
No phase automatically retries, removes partial state or overwrites old kernels.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import stat
import subprocess
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f')
SOURCE, BUILD = BASE / 'source', BASE / 'build'
STAGE = BASE / 'install-stage-kdrebuild4-spin-01'
RECEIPTS = BASE / 'receipts/install-kdrebuild4-spin-01'
RELEASE = '7.0.0-38-kdrebuild4'
FULL, LIMITED = STAGE / 'full', STAGE / 'limited'
INITRD = STAGE / ('initrd.img-' + RELEASE)
MODULE_ROOT = Path('/lib/modules').resolve()
REQUIRED = ('virtio_pci', 'virtio_scsi', 'sd_mod', 'ext4', 'virtio_net',
            'efivarfs', 'vfat', 'nls_iso8859_1')
INITRD_REQUIRED = REQUIRED[:4]
ROOT_RESERVE = 1024 ** 3
ENTRY = 'gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>gnulinux-7.0.0-38-kdrebuild4-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961'
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


def command(label, argv, seconds):
    log = RECEIPTS / (PHASE + '-' + label + '.log')
    started = time.monotonic()
    event('command_started', label=label, argv=list(map(str, argv)), timeout_seconds=seconds)
    with open(log, 'xb') as output:
        proc = subprocess.Popen(list(map(str, argv)), stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            code = proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                code = proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                code = proc.wait(timeout=15)
        output.flush()
        os.fsync(output.fileno())
    result = dict(argv=list(map(str, argv)), returncode=code,
                  timed_out=timed_out, elapsed_seconds=time.monotonic()-started,
                  log=str(log), log_sha256=digest(log))
    save(PHASE + '-' + label + '-result.json', result)
    event('command_finished', label=label, **result)
    if timed_out or code:
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
                                 '/bin/sh', '-c', script, 'kdrebuild4-initramfs',
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
    for name, expected in final['files'].items():
        file = BUILD/name
        if file.stat().st_size != expected['bytes'] or digest(file) != expected['sha256']:
            raise RuntimeError('linked kernel4 artifact differs: ' + name)
    manifest_path = build_path.with_name('build-inputs.json')
    if digest(manifest_path) != build['manifest_sha256']:
        raise RuntimeError('retained kernel4 package manifest changed')
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest['files'].items():
        if digest(SOURCE/'kernel/kdlock'/name) != expected:
            raise RuntimeError('linked kernel4 source differs: ' + name)
    notes = command('exact-build-id', ['readelf', '-n', BUILD/'vmlinux'], 30)
    if [line.split()[-1] for line in notes.splitlines() if 'Build ID:' in line] != [final['build_id']]:
        raise RuntimeError('linked kernel4 ELF BuildID differs')


def stage(args):
    if STAGE.exists() or RECEIPTS.exists():
        raise RuntimeError('fresh stage and receipt required')
    if args.root_working_bytes <= 0:
        raise RuntimeError('explicit root GRUB/metadata working budget required')
    for name in ('final_build_receipt', 'recovery_receipt'):
        path = Path(getattr(args, name))
        expected = getattr(args, name + '_sha256')
        if len(expected) != 64 or digest(path) != expected:
            raise RuntimeError('controller receipt hash mismatch: ' + name)
    build = json.loads(Path(args.final_build_receipt).read_text())
    if (build['phase'] != 'BUILT_AND_LINKED_IDENTITY_VERIFIED' or
        build['kernelrelease'] != RELEASE or any(row['returncode'] != 0 for row in build['commands']) or
        {row['label'] for row in build['commands']} != {'core', 'kernel'}):
        raise RuntimeError('reviewed successful kernel4 build required')
    final = Path(args.final_build_receipt).with_name('final-identity.json')
    if digest(final) != build['final_identity_sha256']:
        raise RuntimeError('linked identity receipt hash differs')
    identity = json.loads(final.read_text())
    if identity['module_count'] != 6901 or identity['module_vermagic'].split()[0] != RELEASE:
        raise RuntimeError('expected full linked kernel4 output with exact module release')
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
                final_identity_sha256=build['final_identity_sha256'],
                final_identity=str(final), recovery_receipt=args.recovery_receipt,
                recovery_receipt_sha256=args.recovery_receipt_sha256,
                kernel_code_commit=build['core_git_head'])


def require_fresh_targets():
    paths = [Path('/lib/modules') / RELEASE]
    paths += [Path('/boot') / (prefix + RELEASE) for prefix in
              ('vmlinuz-', 'System.map-', 'config-', 'initrd.img-')]
    if any(os.path.lexists(path) for path in paths):
        raise RuntimeError('candidate installed namespace is not fresh')


def main():
    global EVENTS, PHASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('stage', 'check', 'install', 'arm'))
    parser.add_argument('--controller-idle-recovery-confirmed', action='store_true')
    parser.add_argument('--final-build-success-reviewed', action='store_true')
    parser.add_argument('--final-build-receipt')
    parser.add_argument('--final-build-receipt-sha256')
    parser.add_argument('--recovery-receipt')
    parser.add_argument('--recovery-receipt-sha256')
    parser.add_argument('--root-working-bytes', type=int)
    parser.add_argument('--checks', default=str(Path(__file__).with_name('kdlock-kdrebuild4-checks.py')))
    args = parser.parse_args()
    PHASE = args.phase
    if os.geteuid() != 0 or not args.controller_idle_recovery_confirmed:
        parser.error('guest root and actual prior controller idle/recovery review required')
    if args.phase == 'stage':
        required = (args.final_build_success_reviewed, args.final_build_receipt,
                    args.final_build_receipt_sha256, args.recovery_receipt,
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
            save('identity-pin.json', identity)
            command('modules-install', ['make', '-C', SOURCE, 'O='+str(BUILD),
                    'KERNELRELEASE='+RELEASE, 'INSTALL_MOD_PATH='+str(FULL),
                    'INSTALL_MOD_STRIP=1', 'modules_install'], 900)
            if len(list((FULL/'lib/modules'/RELEASE/'kernel').rglob('*.ko'))) != 6901:
                raise RuntimeError('normal off-root module stage count differs')
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
            command('update-grub', ['update-grub'], 120)
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
            if before['grub_cfg_sha256'] != after['grub_cfg_sha256'] or {
                k:v for k,v in before['environment'].items() if k != 'next_entry'
            } != {k:v for k,v in after['environment'].items() if k != 'next_entry'}:
                raise RuntimeError('one-shot changed other GRUB state')
            command('sync', ['sync'], 30)
        command('disk-usage', ['df', '-B1', '/', '/boot', BASE], 30)
        save(PHASE+'-complete.json', dict(status='COMPLETE', phase=PHASE,
             reboot_performed=False, module_load_performed=False, unix_time=time.time()))
        event('phase_complete')
    except BaseException as error:
        save(PHASE+'-failure.json', dict(status='FAILED_NO_AUTOMATIC_RETRY',
             phase=PHASE, error=repr(error), preserve_partial_state=True,
             one_shot_may_be_set=(PHASE == 'arm'), reboot_performed=False))
        event('phase_failed', error=repr(error))
        raise
    finally:
        EVENTS.close()


if __name__ == '__main__':
    main()
