#!/usr/bin/env python3
"""Reviewed VM-only kernel3 overlay/build; never install, boot or load code."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import struct
import subprocess
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f')
SOURCE, BUILD = BASE / 'source', BASE / 'build'
PACKAGE = SOURCE / 'kernel/kdlock'
CORE = '1b50e37382d2c739b16953027c47d7e2388562f0'
HEAD = '69ba6b030c1eb7e5f1c3f9461b70f5fef6791309'
OLD = '81feb2d749ebbca468c0ab2eb895dcdd82fe519e'
RELEASE = '7.0.0-38-kdrebuild3'
CONFIG_SHA = '31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483'
CHANGED = {'Kbuild', 'kernel/episode.c', 'kernel/mutex.c', 'kernel/mutex_release.c',
           'kernel/owner_progress.c', 'kernel/request_pool.c',
           'kernel/observation.c', 'kernel/observation.h'}
ADDED = {'kernel/observation.c', 'kernel/observation.h'}
OLD_FINAL = {
    '.config': CONFIG_SHA,
    'vmlinux': '7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809',
    'System.map': '47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f',
    'Module.symvers': '2533c2a4becc4f99f8dacc38e9480608c9032e4c0f3d06a9b4a2fe51fda6752b',
    'arch/x86/boot/bzImage': 'a5fc091793ac0b4dbe9ccb59a390743967d89aa61192eb29e497ac066f356439',
    'include/config/kernel.release': 'e3e48a568c9af5f2fd62c4b0648b92df9579804e41b0148656a13febd1d3684e',
    'include/generated/utsrelease.h': '46e934d076d324d0f049ce41484a4c37cdc91608e12adffcb4aeb55cad52497d',
}
HOOKS = {
    'Makefile': '7b16bd89f6768317eed05f31b8e9ebea901751fea90a731223fd4f990d0dcc32',
    'include/linux/sched.h': 'c0ddfcc8be427faebb47d9807a891a650081e3bcd26e139253da9c8b67f264e8',
    'init/Kconfig': '4a715d514aadc22c22bacd33964596336ace7b0e18bc4ea55dcca6b53d29d872',
    'kernel/Makefile': '81d7f2489749b47d6cc57735885c9a749dfe82ad120b73e8f9f5a298cdb8d6fb',
    'kernel/exit.c': '1bb762d02021af4d2d61945bc3deb01372d9468a7762acc6612e8ad43561e6cb',
    'kernel/fork.c': '330c947b46444b7eb4543febb26b16f80ce6e632de88af540c4f462844f05bb1',
}
UNITS = (
    'kernel/mutex.o', 'kernel/mutex_release.o', 'kernel/state.o', 'kernel/task_state.o',
    'kernel/request_pool.o', 'kernel/owner_progress.o', 'kernel/source_epoch.o',
    'kernel/source_provider.o', 'kernel/feedback.o', 'kernel/feedback_publish.o',
    'kernel/control.o', 'kernel/channel.o', 'kernel/compiled_image.o', 'kernel/runtime.o',
    'kernel/exports.o', 'kernel/image.o', 'kernel/image_owner.o', 'kernel/jit.o',
    'kernel/native_entry.o', 'kernel/observation.o', 'kernel/episode.o', 'kernel/mutex_api.o',
    'kernel/task_progress.o', 'kernel/task_setup.o', 'kernel/task_storage.o',
    'kernel/lifecycle.o', 'kernel/source_stack.o', 'include/mutex_api.o',
    'include/mutex_entry.o', 'include/native_resume.o',
)
FINAL_NAMES = tuple(OLD_FINAL) + ('include/config/auto.conf', 'include/generated/autoconf.h',
    'include/generated/utsversion.h', 'modules.order', 'modules.builtin',
    'modules.builtin.modinfo', 'certs/signing_key.x509')
BUSY = {'make', 'gmake', 'ninja', 'cc1', 'cc1plus', 'gcc', 'g++', 'clang', 'clang++',
        'ld', 'ld.bfd', 'ld.lld', 'as', 'ar', 'objcopy', 'strip', 'fstrim', 'depmod',
        'modprobe', 'insmod', 'rmmod'}
ENV_INPUTS = ('KCFLAGS', 'KCPPFLAGS', 'KAFLAGS', 'CFLAGS_KERNEL', 'CFLAGS_MODULE',
    'AFLAGS_KERNEL', 'AFLAGS_MODULE', 'LLVM', 'LLVM_IAS', 'CC', 'HOSTCC', 'LD',
    'CROSS_COMPILE', 'KBUILD_OUTPUT', 'KBUILD_EXTMOD', 'KCONFIG_CONFIG', 'ARCH')
MIN_FREE, SECONDS = 4_000_000_000, 900
record = None
out = None


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def file_record(path):
    path = Path(path)
    require(path.resolve(strict=True) == path and path.is_file(), 'noncanonical regular file: ' + str(path))
    before = path.stat()
    value = {'bytes': before.st_size, 'sha256': digest(path)}
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            'file changed while hashing: ' + str(path))
    return value


def save(name, value):
    temporary = out / ('.' + name + '.new')
    data = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, out / name)
    descriptor = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def free_bytes():
    value = os.statvfs(BUILD)
    return value.f_bavail * value.f_frsize


def idle(boot):
    actual = {'release': os.uname().release,
        'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'taint': int(Path('/proc/sys/kernel/tainted').read_text()), 'busy': [],
        'devices': sorted(str(p) for p in Path('/dev').glob('kd*'))}
    require((actual['release'], actual['boot'], actual['taint']) ==
            ('7.0.0-38-kdlock1', boot, 0), 'normal boot identity differs')
    require(not Path('/sys/module/kd_runtime_fixture').exists() and not actual['devices'],
            'fixture/module controls remain')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal() or int(proc.name) == os.getpid():
            continue
        try:
            comm = (proc / 'comm').read_text().strip()
            if comm in BUSY or comm.startswith(('kd-fixture', 'kd-scene/', 'kd-runtime')):
                actual['busy'].append({'pid': int(proc.name), 'comm': comm,
                    'command': (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')})
        except (FileNotFoundError, ProcessLookupError):
            continue
    require(not actual['busy'], 'active build/trim/fixture: ' + repr(actual['busy']))
    require(free_bytes() >= MIN_FREE, 'build filesystem has less than 4GB available')
    return actual


def verify_files(root, files):
    actual = {name: digest(root / name) for name in files}
    require(actual == files, 'exact input hashes differ under ' + str(root))
    return actual


def ordinary_boot_files():
    # Hash installed images/maps/configs and GRUB state; no installation writes.
    paths = set(Path('/boot').glob('vmlinuz-*')) | set(Path('/boot').glob('System.map-*'))
    paths |= set(Path('/boot').glob('config-*'))
    paths |= set(Path('/boot').glob('initrd.img-*'))
    paths |= {p for p in (Path('/boot/grub/grub.cfg'), Path('/boot/grub/grubenv')) if p.exists()}
    return {str(p): file_record(p) for p in sorted(paths)}


def execute(label, argv, deadline):
    entry = {'label': label, 'argv': argv, 'start_utc': utc()}
    record['commands'].append(entry)
    save('result.json', record)
    require(time.monotonic() < deadline and free_bytes() >= MIN_FREE, 'build budget unavailable before ' + label)
    with (out / (label + '.log')).open('xb') as log:
        child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C', 'LANGUAGE': 'C'}, start_new_session=True)
        entry['pid'] = child.pid
        save('result.json', record)
        while child.poll() is None:
            entry['elapsed_seconds'] = time.monotonic() - record['build_monotonic_start']
            entry['available_bytes'] = free_bytes()
            if time.monotonic() >= deadline or entry['available_bytes'] < MIN_FREE:
                entry['stop_reason'] = 'aggregate900s_or_build_space_below4GB'
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
                break
            save('result.json', record)
            time.sleep(2)
        entry['returncode'] = child.wait()
    entry['end_utc'] = utc()
    entry['log'] = file_record(out / (label + '.log'))
    save('result.json', record)
    require(entry['returncode'] == 0 and 'stop_reason' not in entry, label + ' failed/stopped; preserve partial build')


def metadata(label, argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    (out / (label + '.stdout')).write_bytes(result.stdout)
    (out / (label + '.stderr')).write_bytes(result.stderr)
    require(result.returncode == 0, 'metadata command failed: ' + label)
    return result.stdout


def elf_bytes(path, address, length):
    with path.open('rb') as stream:
        header = stream.read(64)
        require(header[:6] == b'\x7fELF\x02\x01', 'expected little-endian ELF64')
        fields = struct.unpack('<16sHHIQQQIHHHHHH', header)
        require(fields[2] == 62, 'expected x86_64 ELF')
        phoff, phentsize, phnum = fields[5], fields[9], fields[10]
        require(phentsize == 56 and 0 < phnum <= 256, 'unexpected program header layout')
        matches = []
        for index in range(phnum):
            stream.seek(phoff + index * phentsize)
            kind, flags, offset, va, pa, filesz, memsz, align = struct.unpack('<IIQQQQQQ', stream.read(56))
            if kind == 1 and va <= address and address + length <= va + filesz:
                matches.append(offset + address - va)
        require(len(matches) == 1, 'instruction has no unique file-backed LOAD mapping')
        stream.seek(matches[0])
        data = stream.read(length)
        require(len(data) == length, 'short instruction read')
        return data


def linked_identity():
    names = FINAL_NAMES
    identities = {name: file_record(BUILD / name) for name in names}
    require(identities['.config']['sha256'] == CONFIG_SHA, 'configuration changed')
    require((BUILD / 'include/config/kernel.release').read_text().strip() == RELEASE,
            'linked release is not kernel3')
    notes = metadata('elf-notes', ['readelf', '-n', str(BUILD / 'vmlinux')]).decode()
    build_ids = re.findall(r'Build ID:\s*([0-9a-f]+)', notes)
    require(len(build_ids) == 1, 'unique linked BuildID unavailable')
    metadata('elf-sections', ['readelf', '-W', '-S', str(BUILD / 'vmlinux')])
    symbols = {}
    lines = []
    for line in (BUILD / 'System.map').read_text().splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in ('current_task', 'const_current_task', '__per_cpu_start'):
            require(fields[2] not in symbols, 'duplicate GS symbol')
            symbols[fields[2]] = int(fields[0], 16)
            lines.append(line)
    require(set(symbols) == {'current_task', 'const_current_task', '__per_cpu_start'} and
            symbols['current_task'] == symbols['const_current_task'] and
            symbols['current_task'] >= 1 << 63, 'linked full current_task alias unavailable')
    (out / 'gs-symbols.txt').write_text('\n'.join(lines) + '\n')
    witness = None
    for function in ('kd_mutex_release_request', 'kd_episode_unlock_native', 'kd_jit_mutex_acquire',
                     'kd_task_root_context_current', 'schedule'):
        raw = metadata('gs-disassembly-' + function,
            ['objdump', '-d', '-Mintel', '--insn-width=15', '--disassemble=' + function, str(BUILD / 'vmlinux')])
        for line in raw.decode().splitlines():
            match = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)$', line)
            if not match:
                continue
            data = bytes.fromhex(match[2])
            if len(data) != 8 or data[0] != 0x65 or data[1] & 0xf8 != 0x48 or data[2] != 0x8b or data[3] & 0xc7 != 5:
                continue
            site = int(match[1], 16)
            effective = (site + len(data) + int.from_bytes(data[4:], 'little', signed=True)) & ((1 << 64) - 1)
            if effective != symbols['current_task']:
                continue
            require(elf_bytes(BUILD / 'vmlinux', site, len(data)) == data,
                    'disassembled witness disagrees with actual ELF bytes')
            witness = {'function': function, 'line': line, 'site': hex(site), 'instruction_hex': data.hex(),
                'current_task': hex(effective), 'source_next_ip': hex(site + len(data)),
                'signed_displacement': int.from_bytes(data[4:], 'little', signed=True)}
            break
        if witness:
            break
    require(witness is not None, 'no actual linked GS:RIP MOV current_task witness; do not reuse kernel2 proof')
    witness.update(vmlinux=str(BUILD / 'vmlinux'), vmlinux_sha256=identities['vmlinux']['sha256'],
        system_map=str(BUILD / 'System.map'), system_map_sha256=identities['System.map']['sha256'],
        kernel_config=str(BUILD / '.config'), kernel_config_sha256=CONFIG_SHA,
        per_cpu_start=hex(symbols['__per_cpu_start']), scope='Fresh linked ELF metadata; no boot or generated execution.')
    save('gs-config.json', witness)
    modules = sorted(BUILD.rglob('*.ko'))
    require(len(modules) == 6901, 'actual module count differs; preserve outputs')
    vermagic = metadata('module-vermagic', ['modinfo', '-F', 'vermagic', str(modules[0])]).decode().strip()
    require(vermagic.split()[0] == RELEASE, 'module release differs')
    return {'files': identities, 'build_id': build_ids[0], 'gs_symbols': symbols,
            'gs_witness': witness, 'module_count': len(modules),
            'module_vermagic_path': str(modules[0]), 'module_vermagic': vermagic}


def main():
    global out, record
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--retention-manifest', type=Path, required=True)
    parser.add_argument('--retention-sha256', required=True)
    parser.add_argument('--expected-boot', required=True)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0, 'root required inside VM')
    require(args.input.resolve(strict=True) == args.input and
            args.input.is_relative_to(Path('/mnt/kdlock-builds/kdlock-main-work')),
            'frozen input must be an exact candidate work input')
    require(args.receipt_dir.parent == BASE / 'receipts' and
            args.receipt_dir.name.startswith('overlay-1b50e373-') and
            not args.receipt_dir.exists(), 'fresh exact receipt namespace required')
    require(all(not os.environ.get(name) for name in ENV_INPUTS), 'unreviewed build environment overrides')
    require(digest(args.manifest) == args.manifest_sha256, 'external source manifest hash differs')
    manifest = json.loads(args.manifest.read_text())
    require((manifest['source_git_head'], manifest['core_git_head'], manifest['base_git_head']) ==
            (HEAD, CORE, OLD), 'source/core/base commit mismatch')
    require(manifest['build_input_count'] == len(manifest['files']) == 66 and
            len(manifest['base_files']) == 64 and set(manifest['changed']) == CHANGED and
            set(manifest['added']) == ADDED, 'unexpected core overlay scope')
    require(set(manifest['files']) == set(manifest['base_files']) | ADDED and
            {name for name, value in manifest['files'].items() if value != manifest['base_files'].get(name)} == CHANGED,
            'manifest does not describe exactly six changed and two added paths')
    require(digest(args.retention_manifest) == args.retention_sha256, 'retention manifest hash differs')
    retained = json.loads(args.retention_manifest.read_text())
    require(retained['phase'] == 'KERNEL2_WITNESS_RETAINED' and retained['kernel_code_commit'] == OLD,
            'kernel2 retention incomplete')
    require({name: row['sha256'] for name, row in retained['package_files'].items()} ==
            manifest['base_files'], 'retained kernel2 package differs')
    for name in FINAL_NAMES:
        row = retained['build_files'][name]
        require(digest(BUILD / name) == row['sha256'] == digest(args.retention_manifest.parent / 'build' / name),
                'retained/live kernel2 output differs: ' + name)
    verify_files(BUILD, OLD_FINAL)
    verify_files(SOURCE, HOOKS)
    verify_files(PACKAGE, manifest['base_files'])
    require(all(not (PACKAGE / name).exists() for name in ADDED), 'added core file already exists')
    verify_files(args.input, manifest['files'])
    before_idle = idle(args.expected_boot)
    before_boot = ordinary_boot_files()
    args.receipt_dir.mkdir(mode=0o700)
    out = args.receipt_dir
    record = {'phase': 'PREFLIGHT_VERIFIED', 'start_utc': utc(), 'source_git_head': HEAD,
        'core_git_head': CORE, 'base_git_head': OLD, 'kernelrelease': RELEASE,
        'input': str(args.input), 'manifest': str(args.manifest), 'manifest_sha256': args.manifest_sha256,
        'retention_manifest': str(args.retention_manifest), 'retention_sha256': args.retention_sha256,
        'before_idle': before_idle, 'build_inputs': 66, 'changed_paths': sorted(CHANGED),
        'target_units': {'C': 27, 'assembly': 3, 'objects': UNITS}, 'commands': [],
        'aggregate_build_seconds': SECONDS, 'minimum_build_available_bytes': MIN_FREE,
        'environment_overrides': {'LC_ALL': 'C', 'LANG': 'C', 'LANGUAGE': 'C'},
        'scope': 'Source overlay, targeted core build and ordinary kernel build only; no install, module load or boot.'}
    save('result.json', record)
    save('boot-before.json', before_boot)
    shutil.copy2(args.manifest, out / 'build-inputs.json')
    shutil.copy2(args.retention_manifest, out / 'retention-manifest.json')
    for name in sorted(CHANGED - ADDED):
        target = out / 'core-before' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PACKAGE / name, target)
    for name in sorted(CHANGED):
        target = PACKAGE / name
        temporary = target.with_name('.' + target.name + '-kernel3-overlay')
        with temporary.open('xb') as stream:
            stream.write((args.input / name).read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    verify_files(PACKAGE, manifest['files'])
    record['phase'] = 'OVERLAY_VERIFIED'
    save('result.json', record)
    record['build_monotonic_start'] = time.monotonic()
    deadline = record['build_monotonic_start'] + SECONDS
    common = ['make', '-C', str(SOURCE), 'O=' + str(BUILD), 'KERNELRELEASE=' + RELEASE]
    record['phase'] = 'BUILDING'
    execute('core', common + ['-j8', 'V=1'] + ['kernel/kdlock/' + unit for unit in UNITS], deadline)
    for unit in UNITS:
        command = BUILD / 'kernel/kdlock' / str(Path(unit).parent) / ('.' + Path(unit).name + '.cmd')
        target = out / 'normal-command-files' / unit
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(command, target.with_suffix('.cmd'))
    execute('kernel', common + ['-j32', 'bzImage', 'modules'], deadline)
    record['phase'] = 'BUILD_RETURNED_ZERO'
    save('result.json', record)
    verify_files(PACKAGE, manifest['files'])
    verify_files(args.input, manifest['files'])
    verify_files(SOURCE, HOOKS)
    require(ordinary_boot_files() == before_boot, 'installed boot/default artifacts changed')
    identity = linked_identity()
    save('final-identity.json', identity)
    record.update(phase='BUILT_AND_LINKED_IDENTITY_VERIFIED', end_utc=utc(),
        elapsed_build_seconds=time.monotonic() - record['build_monotonic_start'],
        after_idle=idle(args.expected_boot), final_identity_sha256=digest(out / 'final-identity.json'),
        installed_boot_unchanged=True, input_files_verified_after=66)
    save('result.json', record)
    print(json.dumps(record, indent=2, sort_keys=True), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if record is not None and out is not None:
            record.update(phase='FAILED_RETAIN_PARTIAL', error_type=type(error).__name__, error=str(error), end_utc=utc())
            save('result.json', record)
        raise
