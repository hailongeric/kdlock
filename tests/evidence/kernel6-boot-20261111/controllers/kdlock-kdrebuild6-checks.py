#!/usr/bin/env python3
"""One-off receipt/check helper; no install, module load, trim or reboot calls.

Prepared on the source host; not executed or parsed during preparation.
Every command below is a later controller action in the guest after full build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04')
SOURCE, BUILD = BASE / 'source', BASE / 'build'
RELEASE = '7.0.0-38-kdrebuild6'
CORE = '532b68a65bdf96504e2cede6c23a5bc1476d94e9'
CONFIGURATION = BASE / 'receipts/install-kdrebuild6-api-01/configuration.json'
NORMAL = '7.0.0-38-kdlock1'
LEGACY = '6.1.159-kdclobber2'
PREVIOUS = tuple('7.0.0-38-kdrebuild' + str(number) for number in (1, 2, 3, 4, 5))
UUID = 'aa0bde06-47f6-4049-aaaf-13d052e53961'
SUBMENU = 'gnulinux-advanced-' + UUID
DEFAULT = SUBMENU + '>gnulinux-' + NORMAL + '-advanced-' + UUID
CANDIDATE = 'kdlock-kdrebuild6-api-01'
RECEIPTS = BASE / 'receipts/install-kdrebuild6-api-01'


def run(argv, seconds=30):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=seconds)
    if result.returncode:
        raise RuntimeError(str(argv) + ': ' + result.stderr)
    return result.stdout


def sha(path):
    before = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise RuntimeError('not a regular file: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        expected = (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
        if (opened.st_dev, opened.st_ino, opened.st_size,
                opened.st_mtime_ns, opened.st_ctime_ns) != expected:
            raise RuntimeError('open changed: ' + str(path))
        digest = hashlib.sha256()
        while True:
            data = os.read(fd, 1024 * 1024)
            if not data:
                break
            digest.update(data)
        after = os.fstat(fd)
        current = os.stat(path, follow_symlinks=False)
        for item in (after, current):
            if (item.st_dev, item.st_ino, item.st_size,
                    item.st_mtime_ns, item.st_ctime_ns) != expected:
                raise RuntimeError('read changed: ' + str(path))
    finally:
        os.close(fd)
    return digest.hexdigest()


def record(path):
    path = Path(path)
    st = path.lstat()
    result = {'path': str(path), 'mode': stat.S_IMODE(st.st_mode)}
    if path.is_symlink():
        result['symlink'] = os.readlink(path)
    elif stat.S_ISREG(st.st_mode):
        result.update(size=st.st_size, sha256=sha(path))
    else:
        raise RuntimeError('unexpected protected type: ' + str(path))
    return result


def files(root):
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in list(dirs):
            p = Path(directory) / name
            if p.is_symlink():
                yield p
                dirs.remove(name)
        dirs.sort()
        for name in sorted(names):
            yield Path(directory) / name


def write(path, data):
    with open(path, 'x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def idle():
    if os.uname().release != NORMAL or Path('/proc/sys/kernel/random/boot_id').read_text().strip() != '51b49fa4-4d99-457e-a73e-632b690eb95e':
        raise RuntimeError('not on the normal kernel')
    if Path('/proc/sys/kernel/tainted').read_text().strip() != '0':
        raise RuntimeError('unexpected pre-install taint')
    bad = []
    names = {'make', 'gmake', 'ninja', 'cc1', 'cc1plus', 'gcc', 'clang',
             'ld', 'ld.bfd', 'ld.lld', 'as', 'objcopy', 'insmod', 'rmmod',
             'modprobe', 'fio', 'perf'}
    runners = ('pytest', 'unittest', 'run_runtime_fixture.py', 'run_spin_fixture.py',
               'run_spin_runtime_fixture.py', 'run_rwsem_runtime_fixture.py',
               'run_rwlock_runtime_fixture.py', 'will-it-scale')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            comm = (proc / 'comm').read_text().strip()
            command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            if (comm in names or any(x in comm for x in ('gcc', 'clang', 'cc1')) or
                    any(x in command for x in runners)):
                bad.append({'pid': proc.name, 'comm': comm, 'command': command})
        except (FileNotFoundError, ProcessLookupError):
            continue
    modules = Path('/proc/modules').read_text()
    if any(any(x in line.split()[0].lower() for x in ('kdlock', 'kd_', 'komb', 'tclock'))
           for line in modules.splitlines()) or bad or list(Path('/dev').glob('kd*')):
        raise RuntimeError('build/test/module activity: ' + repr(bad))
    return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'release': os.uname().release, 'taint': 0,
            'modules': modules, 'checked_unix_time': time.time()}


def protected():
    paths = set()
    for pattern in ('vmlinuz*', 'initrd.img*', 'System.map*', 'config*'):
        paths.update(p for p in Path('/boot').glob(pattern) if RELEASE not in p.name)
    for name in ('/vmlinuz', '/vmlinuz.old', '/initrd.img', '/initrd.img.old', '/etc/default/grub', '/boot/grub/grub.cfg'):
        p = Path(name)
        if os.path.lexists(p):
            paths.add(p)
    paths.update(files('/etc/default/grub.d'))
    paths.update(files('/etc/grub.d'))
    module_roots = sorted(p for p in Path('/lib/modules').iterdir() if p.name != RELEASE)
    for root in module_roots:
        if root.is_symlink():
            paths.add(root)
        elif root.is_dir():
            paths.update(files(root))
    if not Path('/lib/modules/' + NORMAL).is_dir() or not Path('/lib/modules/' + LEGACY).is_dir():
        raise RuntimeError('normal or legacy modules missing')
    for release in PREVIOUS:
        if not Path('/lib/modules/' + release).is_dir() or any(
            not Path('/boot/' + prefix + release).is_file() for prefix in
            ('vmlinuz-', 'System.map-', 'config-', 'initrd.img-')):
            raise RuntimeError('prior candidate boot/module namespace missing: ' + release)
    return {'files': [record(path) for path in sorted(paths)],
            'module_roots': [str(path) for path in module_roots]}


def identity():
    config_record = json.loads(CONFIGURATION.read_text())
    build_path = Path(config_record['final_build_receipt'])
    final_path = Path(config_record['final_identity'])
    if (sha(build_path) != config_record['final_build_receipt_sha256'] or
        sha(final_path) != config_record['final_identity_sha256']):
        raise RuntimeError('reviewed build/identity receipt changed')
    built = json.loads(build_path.read_text())
    linked = json.loads(final_path.read_text())
    if (built.get('status') != 'BUILT_AND_LINKED_IDENTITY_VERIFIED' or
        built.get('core_git_head') != CORE or built.get('kernelrelease') != RELEASE or
        built.get('source') != str(SOURCE) or built.get('build') != str(BUILD) or
        built.get('final_identity_sha256') != config_record['final_identity_sha256'] or
        linked.get('source') != str(SOURCE) or linked.get('build') != str(BUILD) or
        linked.get('kernelrelease') != RELEASE or linked.get('module_count') != 1):
        raise RuntimeError('actual reviewed kernel6 linked identity differs')
    focused_path = Path(built['focused_receipt'])
    if sha(focused_path) != built['focused_sha256']:
        raise RuntimeError('actual focused prerequisite changed')
    focused = json.loads(focused_path.read_text())
    if (focused.get('status') != 'FOCUSED_COMPILE_COMPLETE' or
        focused.get('core_git_head') != CORE or focused.get('kernelrelease') != RELEASE or
        focused.get('target_units') != dict(core=33, native=8) or
        focused.get('source') != str(SOURCE) or focused.get('build') != str(BUILD) or
        focused['package_before'] != focused['package_after'] or
        len(focused['package_after']) != 77 or
        focused['source_after_before'] != focused['source_after_after']):
        raise RuntimeError('actual focused source/package pins differ')
    expected = (BUILD / 'include/config/kernel.release').read_text().strip()
    if expected != RELEASE:
        raise RuntimeError('candidate release mismatch: ' + expected)
    config = (BUILD / '.config').read_text()
    for value in ('CONFIG_KDLOCK_REBUILD=y', 'CONFIG_MODULE_SIG_ALL=y', 'CONFIG_MODULE_COMPRESS_ZSTD=y'):
        if value not in config.splitlines():
            raise RuntimeError('configuration missing: ' + value)
    if 'CONFIG_MODULE_COMPRESS_ALL=y' in config.splitlines():
        raise RuntimeError('compression policy changed from reviewed build')
    names = ('.config', 'arch/x86/boot/bzImage', 'vmlinux', 'System.map',
             'Module.symvers', 'modules.order', 'modules.builtin',
             'modules.builtin.modinfo', 'include/config/kernel.release',
             'include/generated/utsrelease.h', 'certs/signing_key.x509',
             'vmlinux.symvers', 'fs/nls/nls_iso8859-1.ko',
             'include/config/auto.conf', 'include/generated/autoconf.h',
             'include/generated/utsversion.h')
    if set(linked['files']) != set(names):
        raise RuntimeError('reviewed sixteen-artifact identity set differs')
    artifacts = []
    for name in names:
        row = record(BUILD / name)
        if row['size'] != linked['files'][name]['bytes'] or row['sha256'] != linked['files'][name]['sha256']:
            raise RuntimeError('linked artifact differs: ' + name)
        artifacts.append(row)
    paths = {SOURCE / name for name in ('Makefile', 'scripts/Makefile.modinst',
             'scripts/Makefile.modpost', 'scripts/Makefile.modfinal',
             'scripts/depmod.sh', 'debian/scripts/sign-module')}
    package = SOURCE / 'kernel/kdlock'
    actual_package = {str(path.relative_to(package)) for path in files(package)}
    if actual_package != set(focused['package_after']):
        raise RuntimeError('frozen package file membership differs')
    for root, rows in ((package, focused['package_after']),
                       (SOURCE, focused['source_after_after']),
                       (SOURCE, focused['body_after'])):
        for name, expected_sha in rows.items():
            path = root / name
            if sha(path) != expected_sha:
                raise RuntimeError('frozen source differs: ' + str(path))
            paths.add(path)
    sources = [record(path) for path in sorted(paths)]
    tools = {}
    for name in ('make', 'strip', 'readelf', 'depmod', 'modinfo', 'modprobe',
                 'mkinitramfs', 'unshare', 'mount', 'grub-reboot', 'grub-editenv',
                 'grub-script-check', 'lsinitramfs', 'cp', 'sync'):
        path = shutil.which(name)
        if not path:
            raise RuntimeError('missing tool: ' + name)
        tools[name] = record(Path(path).resolve())
    notes = run(['readelf', '-n', str(BUILD / 'vmlinux')])
    if re.findall(r'Build ID:\s*([0-9a-f]+)', notes) != [linked['build_id']]:
        raise RuntimeError('actual linked Build ID differs')
    return {'artifacts': artifacts, 'package_source': sources, 'tools': tools,
            'build_id_notes': notes,
            'make_version': run(['make', '--version']),
            'strip_version': run(['strip', '--version']),
            'readelf_version': run(['readelf', '--version']),
            'depmod_version': run(['depmod', '--version']),
            'focused_receipt_sha256': built['focused_sha256'],
            'linked_identity_sha256': config_record['final_identity_sha256'],
            'signing_private_key': 'retained build certs/signing_key.pem; contents not exported'}


def modules(root):
    module_root = Path(root) / 'lib/modules' / RELEASE
    wanted = (module_root / 'modules.order').read_text().splitlines()
    if len(set(wanted)) != len(wanted) or any(
        not name.startswith('kernel/') or not name.endswith('.ko') or
        name != str(Path(name)) or '..' in Path(name).parts for name in wanted):
        raise RuntimeError('unexpected limited modules.order')
    actual = sorted(str(p.relative_to(module_root)) for p in (module_root / 'kernel').rglob('*') if p.is_file())
    if sorted(wanted) != actual:
        raise RuntimeError('limited module set differs from its modules.order')
    records = []
    signed = unsigned = 0
    for relative in actual:
        path = module_root / relative
        info = run(['modinfo', str(path)])
        fields = {}
        for line in info.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                fields.setdefault(key, value.strip())
        if fields.get('vermagic', '').split()[0:1] != [RELEASE]:
            raise RuntimeError('wrong module vermagic: ' + str(path))
        sections = run(['readelf', '-SW', str(path)])
        if re.search(r'\]\s+\.(?:debug_|zdebug_)', sections):
            raise RuntimeError('DWARF remains after INSTALL_MOD_STRIP=1: ' + str(path))
        if fields.get('signer'):
            signed += 1
        else:
            unsigned += 1
        records.append({**record(path), 'vermagic': fields.get('vermagic'),
                        'signer': fields.get('signer'), 'sig_key': fields.get('sig_key'),
                        'sig_hashalgo': fields.get('sig_hashalgo')})
    return {'root': str(module_root), 'count': len(records), 'signed': signed,
            'unsigned': unsigned, 'modules': records,
            'signature_policy': 'record vendor result; unsigned alone is not a new rejection'}


def grub(armed):
    grub_path, custom_path = Path('/boot/grub/grub.cfg'), Path('/boot/grub/custom.cfg')
    snapshot = json.loads((RECEIPTS / 'stage-grub-sources.json').read_text())
    prefix = (RECEIPTS / 'custom.cfg-before').read_bytes()
    append = (RECEIPTS / 'candidate-entry.cfg').read_bytes()
    if (grub_path.is_symlink() or custom_path.is_symlink() or
        sha(grub_path) != snapshot['grub_cfg_sha256'] or
        snapshot['candidate_entry'] != CANDIDATE or
        len(prefix) != snapshot['custom_cfg_before_size'] or
        hashlib.sha256(prefix).hexdigest() != snapshot['custom_cfg_before_sha256'] or
        len(append) != snapshot['append_bytes'] or
        hashlib.sha256(append).hexdigest() != snapshot['append_sha256']):
        raise RuntimeError('reviewed GRUB source or exact candidate suffix changed')
    metadata = custom_path.lstat()
    current_metadata = dict(device=metadata.st_dev, inode=metadata.st_ino,
                            mode=stat.S_IMODE(metadata.st_mode), uid=metadata.st_uid,
                            gid=metadata.st_gid, nlink=metadata.st_nlink)
    custom = custom_path.read_bytes()
    if (not stat.S_ISREG(metadata.st_mode) or
        current_metadata != snapshot['custom_cfg_metadata'] or
        custom != prefix + append or len(custom) != snapshot['custom_cfg_after_size'] or
        hashlib.sha256(custom).hexdigest() != snapshot['custom_cfg_after_sha256']):
        raise RuntimeError('existing custom prefix or exact append differs')
    text = grub_path.read_text()
    loader = ('if [ -f  ${config_directory}/custom.cfg ]; then\n'
              '  source ${config_directory}/custom.cfg\n')
    if loader not in text:
        raise RuntimeError('actual custom menu loader changed')
    if 'set default="' + DEFAULT + '"' not in text:
        raise RuntimeError('normal default no longer pinned')
    for release in (NORMAL, LEGACY, *PREVIOUS):
        token = "'gnulinux-" + release + '-advanced-' + UUID + "'"
        if text.count(token) != 1:
            raise RuntimeError('missing/ambiguous advanced entry: ' + release)
    if CANDIDATE in text or custom.decode().count("--id '" + CANDIDATE + "'") != 1:
        raise RuntimeError('missing/ambiguous top-level candidate entry')
    run(['grub-script-check', str(grub_path)])
    run(['grub-script-check', str(custom_path)])
    environment = run(['grub-editenv', '/boot/grub/grubenv', 'list'])
    values = dict(line.split('=', 1) for line in environment.splitlines() if '=' in line)
    if values.get('prev_saved_entry'):
        raise RuntimeError('unresolved prior saved-entry state')
    if values.get('next_entry', '') != (CANDIDATE if armed else ''):
        raise RuntimeError('unexpected one-shot boot selection')
    return {'normal_default': DEFAULT, 'candidate_entry': CANDIDATE,
            'grub_cfg_sha256': sha(grub_path),
            'custom_cfg_sha256': hashlib.sha256(custom).hexdigest(),
            'custom_prefix_sha256': hashlib.sha256(prefix).hexdigest(),
            'environment': values}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('idle', 'protect', 'verify-protected', 'identity', 'modules', 'grub'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--snapshot')
    parser.add_argument('--root')
    parser.add_argument('--armed', action='store_true')
    args = parser.parse_args()
    if args.mode == 'idle':
        data = idle()
    elif args.mode == 'protect':
        data = protected()
    elif args.mode == 'verify-protected':
        if not args.snapshot:
            parser.error('--snapshot required')
        previous = json.loads(Path(args.snapshot).read_text())
        current = protected()
        if current != previous:
            raise RuntimeError('protected file/module namespace differs')
        data = {'unchanged': True, 'file_count': len(current['files'])}
    elif args.mode == 'identity':
        data = identity()
    elif args.mode == 'modules':
        if not args.root:
            parser.error('--root required')
        data = modules(args.root)
    else:
        data = grub(args.armed)
    write(args.output, data)


if __name__ == '__main__':
    main()
