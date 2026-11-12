#!/usr/bin/env python3
"""VM-only built-in kernel/one-module build, or separately reviewed off-root stage.

The build phase requires a hash-pinned successful 33+8 focused receipt. The stage
phase requires its successful build receipt and a fresh off-root destination.
Neither phase installs into /boot or /lib/modules, loads code, or reboots. A
deadline/space failure retains a live child and all receipts; it proves no drain.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time

RELEASE = '7.0.0-38-kdrebuild8'
CORE = '0d42063ead37dc8fc1631fa56c8348890ede9c5f'
NLS = 'fs/nls/nls_iso8859-1.ko'
ORDER = b'fs/nls/nls_iso8859-1.o\n'

# Offline build/stage runs on the preserved NORMAL kernel. The future candidate
# still builds and installs only its declared NLS closure; its loaded-module
# check belongs to actual candidate postboot, not this normal-kernel preflight.
NORMAL_MODULE_WITNESS_SHA256 = 'e21b41772bc494af225070c4a817af70e54c2f377605ef307340f55b07e4ce6a'
NORMAL_MODULE_NAMES = frozenset(('aesni_intel', 'async_memcpy', 'async_pq', 'async_raid6_recov', 'async_tx', 'async_xor', 'autofs4', 'binfmt_misc', 'bochs', 'btrfs', 'cfg80211', 'dm_multipath', 'dmi_sysfs', 'efi_pstore', 'floppy', 'ghash_clmulni_intel', 'i2c_piix4', 'i2c_smbus', 'input_leds', 'intel_rapl_common', 'intel_rapl_msr', 'intel_uncore_frequency_common', 'irqbypass', 'joydev', 'kvm', 'kvm_intel', 'libblake2b', 'linear', 'mac_hid', 'nfit', 'nfnetlink', 'nls_iso8859_1', 'parport', 'parport_pc', 'pata_acpi', 'ppdev', 'psmouse', 'qemu_fw_cfg', 'raid0', 'raid1', 'raid10', 'raid456', 'raid6_pq', 'rapl', 'sch_fq_codel', 'serio_raw', 'skx_edac_common', 'vga16fb', 'vgastate', 'virtiofs', 'vmw_vsock_virtio_transport', 'vmw_vsock_virtio_transport_common', 'vsock', 'xor'))
ENV_KEYS = {'KCFLAGS', 'KAFLAGS', 'KCPPFLAGS', 'CFLAGS_KERNEL', 'CFLAGS_MODULE',
            'AFLAGS_KERNEL', 'AFLAGS_MODULE', 'LLVM', 'LLVM_IAS', 'CC', 'LD',
            'HOSTCC', 'HOSTCXX', 'CROSS_COMPILE', 'KBUILD_OUTPUT', 'KBUILD_EXTMOD',
            'KCONFIG_CONFIG', 'ARCH', 'MAKEFLAGS', 'MFLAGS', 'INSTALL_MOD_PATH',
            'INSTALL_MOD_STRIP', 'KBUILD_MODPOST_WARN', 'KBUILD_MODPOST_NOFINAL'}
FILE_NAMES = ('.config', 'Module.symvers', 'System.map', 'arch/x86/boot/bzImage',
              'certs/signing_key.x509', 'include/config/auto.conf',
              'include/config/kernel.release', 'include/generated/autoconf.h',
              'include/generated/utsrelease.h', 'include/generated/utsversion.h',
              'modules.builtin', 'modules.builtin.modinfo', 'modules.order', 'vmlinux',
              'vmlinux.symvers', NLS)
record = None
out = None


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(path):
    value = Path(path)
    require(value.is_absolute() and value.resolve(strict=True) == value,
            'canonical existing absolute path required: ' + str(value))
    return value


def checked_json(path, expected):
    value = canonical(path)
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None and sha(value) == expected,
            'receipt SHA mismatch: ' + str(value))
    return value, json.loads(value.read_text())


def atomic_json(name, value):
    target = out / name
    temporary = target.with_name('.' + target.name + '.new')
    with temporary.open('xb') as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    descriptor = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def pins(root, expected):
    require(isinstance(expected, dict) and expected, 'empty file-pin set')
    result = {}
    for name, digest in expected.items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts,
                'invalid pinned relative path')
        path = root / relative
        require(path.resolve(strict=True) == path and path.is_file(),
                'nonregular or aliased pinned file: ' + str(path))
        before = path.stat()
        actual = sha(path)
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                 before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size,
                                        after.st_mtime_ns, after.st_ctime_ns),
                'pinned file changed while reading: ' + str(path))
        require(actual == digest, 'pinned bytes differ: ' + str(path))
        result[name] = actual
    return result


def available(path):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def environment():
    bad = sorted(key for key in os.environ if key in ENV_KEYS or
                 key.startswith(('CFLAGS', 'AFLAGS', 'KBUILD_', 'INSTALL_MOD_')))
    require(not bad, 'unreviewed build environment overrides: ' + ','.join(bad))


def idle_sample(expected, names):
    value = {'unix': time.time(), 'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'release': os.uname().release, 'taint': Path('/proc/sys/kernel/tainted').read_text().strip(),
             'modules': Path('/proc/modules').read_text(), 'busy': [], 'dthreads': []}
    require(all(str(value[key]) == str(expected[key]) for key in ('boot', 'release', 'taint')) and
            value['release'] == '7.0.0-38-kdlock1' and value['taint'] == '0', 'normal identity differs')
    require({line.split()[0] for line in value['modules'].splitlines()} == set(names), 'actual normal54 modules differ')
    require(not any('fixture' in path.name or path.name in ('kd_mmap_api', 'kd_mmap_api_events', 'kd_rwsem_api')
                    for path in Path('/dev').iterdir()), 'fixture/API device remains')
    commands = {'make', 'gmake', 'cc1', 'cc1plus', 'gcc', 'gcc-15', 'clang', 'ld', 'ld.bfd',
                'as', 'objtool', 'fstrim', 'depmod', 'insmod', 'rmmod', 'mmap-userspace'}
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            comm = (process / 'comm').read_text().strip()
            argv = [word.decode('utf-8', errors='replace') for word in (process / 'cmdline').read_bytes().split(b'\0') if word]
            project_check = any('/tests/kernel/' in word or 'test_source_boundaries.py' in word for word in argv)
            if (comm in commands or project_check or
                    comm.startswith(('kd-fixture/', 'kd-scene/', 'kd-reader/', 'kd-killable/'))):
                value['busy'].append({'pid': int(process.name), 'comm': comm, 'argv': argv})
            for task in (process / 'task').iterdir():
                if '\nState:\tD ' in '\n' + (task / 'status').read_text():
                    value['dthreads'].append({'pid': int(process.name), 'tid': int(task.name),
                                             'comm': (task / 'comm').read_text().strip(),
                                             'wchan': (task / 'wchan').read_text().strip()})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return value


def final_idle(expected, names):
    deadline = time.monotonic() + 60
    clear_at = None
    samples = []
    while True:
        sample = idle_sample(expected, names)
        samples.append(sample)
        record['final_idle_samples'] = samples
        atomic_json('result.json', record)
        if sample['busy'] or sample['dthreads']:
            clear_at = None
        elif clear_at is None:
            clear_at = time.monotonic()
        elif time.monotonic() - clear_at >= 10:
            return sample
        require(time.monotonic() < deadline, 'final strict idle not established within60s; all samples retained')
        time.sleep(min(10, max(0, deadline - time.monotonic())))


def idle(expected):
    sample = idle_sample(expected, NORMAL_MODULE_NAMES)
    require(not sample['busy'] and not sample['dthreads'], 'strict idle refused: ' + json.dumps(sample, sort_keys=True))
    sample['normal_module_names'] = sorted(NORMAL_MODULE_NAMES)
    sample['normal_module_witness_sha256'] = NORMAL_MODULE_WITNESS_SHA256
    return sample



def recovery(path, digest, policy):
    unused, value = checked_json(path, digest)
    require(set(policy) == {'host_boot_id', 'qemu_pid', 'qemu_start_ticks', 'monitor_path', 'tag',
                            'maximum_age_seconds', 'headroom_path', 'host_floor_bytes'} and
            type(policy['qemu_pid']) is int and policy['qemu_pid'] > 0 and
            type(policy['qemu_start_ticks']) is int and policy['qemu_start_ticks'] > 0 and
            1 <= policy['maximum_age_seconds'] <= 900 and policy['host_floor_bytes'] >= 48 * 1024**3 and
            policy['tag'], 'explicit retained capture/headroom policy required')
    # Keep the actual reviewed capture+headroom schema. The all-disks monitor
    # list is the recovery observation; process arguments alone are not one.
    capture, space = value['capture'], value['headroom']
    captured = datetime.datetime.fromisoformat(capture['captured_utc'])
    spaced = datetime.datetime.fromisoformat(space['utc'])
    require(captured.tzinfo is not None and spaced.tzinfo is not None and
            0 <= time.time() - captured.timestamp() <= policy['maximum_age_seconds'] and
            0 <= time.time() - spaced.timestamp() <= policy['maximum_age_seconds'], 'stale recovery/headroom')
    require(capture['pins_verified'] is True and capture['frequency_verified'] is True and
            capture['snapshot_listed'] is True and capture['recovery_snapshot'] == policy['tag'] and
            capture['host_boot_id'] == policy['host_boot_id'] and capture['monitor_path'] == policy['monitor_path'],
            'real recovery/pin/frequency/host gates differ')
    require(len(capture['qemu']) == 1 and capture['qemu'][0]['pid'] == policy['qemu_pid'] and
            capture['qemu'][0]['start_ticks'] == policy['qemu_start_ticks'], 'actual QEMU identity differs')
    require(space['path'] == space['realpath'] == policy['headroom_path'] and
            space['host_free_bytes'] >= policy['host_floor_bytes'], 'actual host headroom differs')
    marker = 'List of snapshots present on all disks:'
    listing = capture['snapshots']
    require(marker in listing and any(policy['tag'] in line.split() for line in
            listing.split(marker, 1)[1].split('List of partial', 1)[0].splitlines()), 'complete actual recovery tag absent')
    return {'sha256': digest, 'capture_unix': captured.timestamp(), 'headroom_unix': spaced.timestamp(),
            'host_available': space['host_free_bytes'], 'raw': value}



def preserved_inputs(focused):
    unused, value = checked_json(focused['preserved_inputs'], focused['preserved_inputs_sha256'])
    require(value['format'] == 'kdlock.kernel8.preserved-inputs.v1' and value['core_git_head'] == CORE and
            value['kernelrelease'] == RELEASE, 'preserved input identity differs')
    counts = {group['name']: len(group['files']) for group in value['preserved_groups']}
    require(counts == {'normal_source': 8, 'kernel6_output': 16, 'kernel6_package': 77, 'kernel7_output': 16,
                       'kernel7_package': 77, 'kernel7_integration': 8, 'kernel7_mm_bodies': 11, 'kernel7_input': 77},
            'complete retained normal/kernel6/kernel7 groups required')
    return value


def protected(focused):
    value = preserved_inputs(focused)
    result = {group['name']: pins(canonical(group['root']), group['files']) for group in value['preserved_groups']}
    result['provenance_files'] = {}
    for name, digest in value['provenance_files'].items():
        require(sha(canonical(name)) == digest, 'preserved provenance changed: ' + name)
        result['provenance_files'][name] = digest
    require(sha(canonical(value['normal_manifest'])) == value['normal_manifest_sha256'], 'normal bundle changed')
    result['normal_manifest_sha256'] = value['normal_manifest_sha256']
    return result


def boot_files():
    result = {}
    for root in (Path('/boot'), Path('/etc/grub.d')):
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                result[str(path)] = {'symlink': os.readlink(path)}
            elif path.is_file():
                result[str(path)] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    for path in (Path('/etc/default/grub'), Path('/boot/grub/grubenv')):
        if path.is_file():
            result[str(path)] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    result['/lib/modules namespaces'] = sorted(item.name for item in Path('/lib/modules').iterdir())
    return result


def source_pins(focused, source):
    package_input = canonical(focused['package_input'])
    integrated = dict(focused['applied_after'])
    require('Makefile' not in integrated, 'top-level Makefile unexpectedly applied')
    integrated['Makefile'] = focused['normal_after']['Makefile']
    result = {'package': pins(source / 'kernel/kdlock', focused['package_after']),
              'bodies': pins(source, focused['body_after']), 'integration': pins(source, integrated),
              'immutable_input': pins(package_input, focused['package_after'])}
    provenance = ((Path(focused['package_manifest']), focused['package_manifest_sha256']),
                  (Path(focused['application_manifest']), focused['application_manifest_sha256']),
                  (Path(focused['inspect_receipt']), focused['inspect_sha256']),
                  (Path(focused['preserved_inputs']), focused['preserved_inputs_sha256']),
                  (Path(focused['config']), focused['config_sha256_input']))
    for path, expected in provenance:
        require(sha(canonical(path)) == expected, 'focused provenance changed: ' + str(path))
        result[str(path)] = expected
    manifest = json.loads(provenance[0][0].read_text())
    application = json.loads(provenance[1][0].read_text())
    require(manifest['files'] == focused['package_after'] and manifest['code_file_count'] == 78 and
            manifest['core_git_head'] == manifest['source_snapshot_git_head'] == CORE and
            manifest['intended_kernelrelease'] == RELEASE and
            manifest['installer_format'] == 'kdlock.exact-target-integration.v3' and
            'include/kd_linux_rwsem_query.h' in manifest['files'], 'exact78 v3 package identity differs')
    require(application['format'] == 'kdlock.exact-target-integration.v3' and
            application['after'] == focused['applied_after'] and application['tree'] == str(source) and
            application['build'] == str(source.parent / 'build'), 'exact v3 application differs')
    return result


def diagnostic_rows(path):
    # Recognize diagnostic records, not echoed GCC recipes whose flags include
    # -Wmissing-declarations after an unrelated vmlinux.export.o argument.
    prefix = re.compile(r'^(?:(?:ERROR|WARNING|error|warning|fatal error):|'
                        r'(?:ld|ld\.bfd|modpost):|'
                        r'[^\n]+:[0-9]+(?::[0-9]+)?:\s*(?:fatal error|error|warning|note):)')
    rows = []
    for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
        if prefix.match(line.strip()):
            rows.append({'line': number, 'text': line})
    return rows


def run(label, argv, deadline, build, args):
    require(time.monotonic() < deadline, 'deadline expired before dispatch')
    row = {'label': label, 'argv': list(argv), 'started_unix': time.time()}
    record['commands'].append(row)
    atomic_json('result.json', record)
    log = out / (label + '.log')
    with log.open('xb') as output:
        child = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, LC_ALL='C', PYTHONDONTWRITEBYTECODE='1'))
        row['pid'] = child.pid
        atomic_json('result.json', record)
        while child.poll() is None:
            if time.monotonic() >= deadline or available('/') < args.root_floor or \
                    available(build) < args.output_floor:
                row.update(status='CHILD_RETAINED', elapsed_seconds=time.time() - row['started_unix'])
                record['status'] = 'INCOMPLETE_CHILD_RETAINED'
                atomic_json('result.json', record)
                raise RuntimeError('deadline/space observer stopped; child retained, no drain proof')
            time.sleep(0.25)
        row.update(returncode=child.returncode, elapsed_seconds=time.time() - row['started_unix'])
    row['log_sha256'] = sha(log)
    atomic_json('result.json', record)
    require(child.returncode == 0, label + ' failed; output retained')
    return log


def export_rows(path):
    rows = []
    for line in path.read_text().splitlines():
        fields = line.split()
        require(len(fields) >= 4, 'invalid native symbol-version row')
        if fields[2] == 'vmlinux':
            rows.append(line)
    require(rows, 'fresh vmlinux export rows absent')
    return sorted(rows)


def elf_bytes(path, address, length):
    with path.open('rb') as stream:
        header = stream.read(64)
        require(header[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', header, 18)[0] == 62,
                'actual ELF64 x86-64 required')
        offset = struct.unpack_from('<Q', header, 32)[0]
        size, count = struct.unpack_from('<HH', header, 54)
        require(size == 56 and 0 < count < 1024, 'ELF program-header bounds')
        matches = []
        for index in range(count):
            stream.seek(offset + index * size)
            kind, flags, file_offset, va, unused, file_size, unused2, unused3 = \
                struct.unpack('<IIQQQQQQ', stream.read(size))
            if kind == 1 and flags & 1 and va <= address and address + length <= va + file_size:
                matches.append(file_offset + address - va)
        require(len(matches) == 1, 'symbol does not map to one executable file-backed ELF segment')
        stream.seek(matches[0])
        data = stream.read(length)
        require(len(data) == length, 'short ELF symbol data')
        return data


def linked_identity(source, build, deadline, args):
    notes = run('elf-notes', ['readelf', '-nW', str(build / 'vmlinux')], deadline, build, args)
    identifiers = re.findall(r'Build ID:\s*([0-9a-f]+)', notes.read_text())
    require(len(identifiers) == 1, 'one actual linked GNU Build ID required')
    nm = run('elf-symbols', ['nm', '-S', '-n', '--defined-only', str(build / 'vmlinux')],
             deadline, build, args)
    wanted = {'current_task', 'const_current_task', '__per_cpu_start',
              'its_return_thunk', '__x86_return_thunk'}
    symbols = {}
    for line in nm.read_text().splitlines():
        fields = line.split()
        if len(fields) in (3, 4) and fields[-1] in wanted:
            require(fields[-1] not in symbols, 'duplicate linked symbol')
            symbols[fields[-1]] = {'address': int(fields[0], 16),
                                   'bytes': int(fields[1], 16) if len(fields) == 4 else 0}
    require(set(symbols) == wanted, 'required actual linked GS/return symbols absent')
    gs = {key: symbols[key]['address'] for key in ('current_task', 'const_current_task', '__per_cpu_start')}
    require(gs['current_task'] == gs['const_current_task'] and gs['current_task'] >= 1 << 63,
            'current_task must be the full linked alias, without a second subtraction')
    mapped = {}
    for line in (build / 'System.map').read_text().splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in wanted:
            require(fields[2] not in mapped, 'duplicate System.map symbol')
            mapped[fields[2]] = int(fields[0], 16)
    require(mapped == {key: row['address'] for key, row in symbols.items()},
            'System.map and linked ELF symbols differ')
    disassembly = run('gs-disassembly', ['objdump', '-dw', '-M', 'intel',
                       '--disassemble=kd_mutex_release_request', str(build / 'vmlinux')],
                      deadline, build, args)
    witnesses = []
    for line in disassembly.read_text().splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s*((?:[0-9a-f]{2}\s+)+)', line)
        if match is None:
            continue
        raw = bytes.fromhex(match[2])
        if len(raw) == 8 and raw[:1] == b'\x65' and raw[1] in (0x48, 0x4c) and \
                raw[2] == 0x8b and raw[3] & 0xc7 == 5:
            site = int(match[1], 16)
            target = (site + 8 + int.from_bytes(raw[4:], 'little', signed=True)) & ((1 << 64) - 1)
            if target == gs['current_task']:
                require(elf_bytes(build / 'vmlinux', site, len(raw)) == raw, 'GS witness bytes differ')
                witnesses.append({'function': 'kd_mutex_release_request', 'site': hex(site),
                                  'source_next_ip': hex(site + 8), 'instruction_hex': raw.hex(),
                                  'current_task': hex(target), 'line': line})
    require(witnesses, 'fresh linked full-VMA GS:RIP witness absent')
    thunks = {}
    for name in ('its_return_thunk', '__x86_return_thunk'):
        row = symbols[name]
        require(1 <= row['bytes'] <= 4096, 'bounded actual return-symbol size required')
        data = elf_bytes(build / 'vmlinux', row['address'], row['bytes'])
        (out / (name + '.bin')).write_bytes(data)
        thunks[name] = dict(row, hex=data.hex(), sha256=hashlib.sha256(data).hexdigest())
    files = {name: {'bytes': (build / name).stat().st_size, 'sha256': sha(build / name)}
             for name in FILE_NAMES}
    result = {'build_id': identifiers[0], 'files': files, 'gs_symbols': gs,
              'gs_witness': witnesses[0], 'return_symbols': thunks,
              'module_count': 1, 'module_scope': 'Only the declared NLS boot closure was built.',
              'source': str(source), 'build': str(build), 'kernelrelease': RELEASE,
              'scope': 'Linked-image and selected-module evidence; no boot, API runtime or performance result.'}
    atomic_json('final-identity.json', result)
    atomic_json('gs-config.json', {'kernel_elf': str(build / 'vmlinux'),
                'kernel_elf_sha256': files['vmlinux']['sha256'],
                'system_map': str(build / 'System.map'),
                'system_map_sha256': files['System.map']['sha256'],
                'kernel_config': str(build / '.config'),
                'kernel_config_sha256': files['.config']['sha256'],
                'current_task_gs_offset': gs['current_task'],
                'percpu_section_va': gs['__per_cpu_start'], 'build_id': identifiers[0],
                'verified_for_running_kernel': False,
                'scope': 'Fresh linked ELF metadata only. A later actual postboot proof is required.'})
    return result


def main():
    global out, record
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('build', 'stage'), required=True)
    for key in ('focused-receipt', 'focused-sha', 'receipt-dir', 'recovery', 'recovery-sha'):
        parser.add_argument('--' + key, required=True)
    for key in ('seconds', 'jobs', 'root-floor', 'output-floor', 'host-floor'):
        parser.add_argument('--' + key, type=int, required=True)
    parser.add_argument('--build-receipt')
    parser.add_argument('--build-sha')
    parser.add_argument('--raw-stage')
    args = parser.parse_args()
    require(os.geteuid() == 0, 'guest root required')
    require(args.jobs in (8, 16) and 1 <= args.seconds <= 3600, 'explicit 8/16 jobs and bounded deadline required')
    require(args.root_floor >= 1024 ** 3 and args.output_floor >= 8 * 1024 ** 3 and
            args.host_floor >= 8 * 1024 ** 3, 'explicit space floors below reviewed minima')
    environment()
    focus_path, focused = checked_json(args.focused_receipt, args.focused_sha)
    require(focused['status'] == 'FOCUSED_COMPILE_COMPLETE' and
            focused['core_git_head'] == CORE and focused['kernelrelease'] == RELEASE and
            focused['target_units'] == {'core': 33, 'native': 8}, 'successful exact 33+8 focused receipt required')
    require(focused['package_before'] == focused['package_after'] and len(focused['package_after']) == 78,
            'focused immutable package pin set differs')
    require(len(focused['applied_after']) == 7, 'focused seven-file integrated source pins differ')
    require(focused['normal_before'] == focused['normal_after'] and
            focused['protected_before'] == focused['protected_after'] and
            focused['installer_format'] == 'kdlock.exact-target-integration.v3',
            'focused v3/protected inputs changed')
    source, build = canonical(focused['source']), canonical(focused['build'])
    require(source.name == 'source' and build.name == 'build' and source.parent == build.parent and
            source.parent == Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01') and
            source.parent.parent == Path('/mnt/kdlock-builds2'), 'unexpected independent source/O namespace')
    saved = preserved_inputs(focused)
    for kept in (canonical(group['root']) for group in saved['preserved_groups']):
        require(not (source == kept or source in kept.parents or kept in source.parents or
                     build == kept or build in kept.parents or kept in build.parents),
                'candidate source/O overlaps protected input')
    require(len(focused['compiled_objects']) == 82, 'all41 focused object/command pairs required')
    if args.phase == 'build':
        pins(build, {name: row['sha256'] for name, row in focused['compiled_objects'].items()})
    require(sha(build / '.config') == focused['config_sha256'], 'reviewed focused config changed')
    config = (build / '.config').read_text().splitlines()
    for item in ('CONFIG_NLS_ISO8859_1=m', 'CONFIG_MODULE_SIG_ALL=y', 'CONFIG_MODVERSIONS=y',
                 'CONFIG_KDLOCK_REBUILD=y', 'CONFIG_VIRTIO_PCI=y', 'CONFIG_SCSI_VIRTIO=y',
                 'CONFIG_BLK_DEV_SD=y', 'CONFIG_EXT4_FS=y', 'CONFIG_VIRTIO_NET=y',
                 'CONFIG_EFIVAR_FS=y', 'CONFIG_VFAT_FS=y'):
        require(item in config, 'reviewed limited boot configuration differs: ' + item)
    require('CONFIG_TRIM_UNUSED_KSYMS=y' not in config, 'TRIM would build unselected modules')
    require('CONFIG_MODULE_COMPRESS_ALL=y' not in config,
            'reviewed uncompressed limited-module namespace required')
    require((build / 'include/config/kernel.release').read_text().strip() == RELEASE,
            'actual focused output release differs')
    state = idle(focused['identity_after'])
    require(focused['recovery_policy']['host_floor_bytes'] >= args.host_floor, 'recovery floor is below explicit request')
    rec = recovery(args.recovery, args.recovery_sha, focused['recovery_policy'])
    require(available('/') >= args.root_floor and available(build) >= args.output_floor,
            'guest headroom below explicit floors')
    if args.phase == 'build':
        require(available(build) >= 48 * 1024 ** 3 and rec['host_available'] >= 48 * 1024 ** 3,
                'initial guest output and host headroom each require 48GiB')
    out = Path(args.receipt_dir)
    require(out.is_absolute() and not os.path.lexists(out) and
            out.parent.resolve(strict=True) == source.parent / 'receipts' and
            out == out.parent.resolve(strict=True) / out.name,
            'fresh direct-child candidate receipt directory required')
    protected_before, source_before, boot_before = protected(focused), source_pins(focused, source), boot_files()
    out.mkdir(mode=0o700)
    record = {'status': 'PREPARED', 'phase': args.phase, 'core_git_head': CORE,
              'source_snapshot_git_head': focused['source_snapshot_git_head'],
              'focused_receipt': str(focus_path), 'focused_sha256': args.focused_sha,
              'source': str(source), 'build': str(build), 'kernelrelease': RELEASE,
              'arguments': vars(args).copy(), 'commands': [], 'identity_before': state,
              'recovery': rec, 'protected_before': protected_before, 'source_before': source_before,
              'boot_before': boot_before, 'started_unix': time.time(),
              'scope': 'Fresh kernel8 v3 built-in kernel and one NLS module, or separate off-root stage. Normal/kernel6/kernel7 retained. No installed namespace, load or boot.'}
    atomic_json('result.json', record)
    deadline = time.monotonic() + args.seconds
    make = ['make', '-C', str(source), 'O=' + str(build), 'KERNELRELEASE=' + RELEASE, 'V=1']
    if args.phase == 'build':
        require(not any((args.build_receipt, args.build_sha, args.raw_stage)), 'stage inputs on build phase')
        require(not (build / 'vmlinux').exists() and not (build / NLS).exists() and
                not (build / 'Module.symvers').exists() and not (build / 'vmlinux.symvers').exists(),
                'first full build required; partial/old linked outputs retained for separate review')
        run('kernel', make + ['-j' + str(args.jobs), 'bzImage'], deadline, build, args)
        require((build / 'vmlinux.symvers').is_file(), 'built-in modpost did not create fresh exports')
        run('nls', make + ['-j' + str(args.jobs), NLS], deadline, build, args)
        require(export_rows(build / 'Module.symvers') == export_rows(build / 'vmlinux.symvers'),
                'fresh selected-module and vmlinux export rows disagree')
        require(not os.path.lexists(build / 'modules.order'), 'single-module temporary order was not removed')
        with (build / 'modules.order').open('xb') as stream:
            stream.write(ORDER)
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open(build, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        record['diagnostics'] = {name: diagnostic_rows(out / (name + '.log'))
                                 for name in ('kernel', 'nls')}
        missing = re.compile(r'(undefined!|undefined (?:symbol|reference)|unresolved symbol|'
                             r'Symbol version dump.*missing|vmlinux(?:\.symvers|\.o)?.*missing)', re.I)
        failures = {name: [row for row in rows if missing.search(row['text'])]
                    for name, rows in record['diagnostics'].items()}
        record['missing_export_diagnostics'] = failures
        atomic_json('result.json', record)
        require(not any(failures.values()), 'actual unresolved/missing-export diagnostic retained')
        vermagic = run('module-vermagic', ['modinfo', '-F', 'vermagic', str(build / NLS)], deadline, build, args)
        require(vermagic.read_text().strip().split()[0] == RELEASE, 'new NLS vermagic differs')
        depends = run('module-dependencies', ['modinfo', '-F', 'depends', str(build / NLS)], deadline, build, args)
        require(not depends.read_text().strip(), 'NLS module has an undeclared dependency')
        linked = linked_identity(source, build, deadline, args)
        linked['module_vermagic'] = vermagic.read_text().strip()
        atomic_json('final-identity.json', linked)
        record['final_identity_sha256'] = sha(out / 'final-identity.json')
        record['status'] = 'BUILT_AND_LINKED_IDENTITY_VERIFIED'
    else:
        require(args.build_receipt and args.build_sha and args.raw_stage, 'stage requires exact build receipt and fresh raw destination')
        previous_path, previous = checked_json(args.build_receipt, args.build_sha)
        require(previous['status'] == 'BUILT_AND_LINKED_IDENTITY_VERIFIED' and
                previous['focused_sha256'] == args.focused_sha and previous['core_git_head'] == CORE and
                previous['source'] == str(source) and previous['build'] == str(build),
                'exact successful build receipt required')
        unused, identity = checked_json(previous_path.parent / 'final-identity.json', previous['final_identity_sha256'])
        pins(build, {key: row['sha256'] for key, row in identity['files'].items()})
        require((build / 'modules.order').read_bytes() == ORDER, 'limited native install order changed')
        raw = Path(args.raw_stage)
        require(raw.is_absolute() and not os.path.lexists(raw) and
                raw.parent.resolve(strict=True) == out and raw == out / raw.name,
                'fresh raw stage must be an immediate child of this receipt directory')
        raw.mkdir(mode=0o700)
        run('modules-install', make + ['INSTALL_MOD_PATH=' + str(raw), 'INSTALL_MOD_STRIP=1',
                                     'modules_install'], deadline, build, args)
        destination = raw / 'lib/modules' / RELEASE
        require(destination.resolve(strict=True) == destination and
                list(destination.rglob('*.ko')) == [destination / 'kernel' / NLS],
                'off-root installed module closure differs')
        module = destination / 'kernel' / NLS
        fields = {}
        for field in ('vermagic', 'signer', 'sig_key', 'sig_hashalgo', 'depends'):
            log = run('installed-' + field, ['modinfo', '-F', field, str(module)], deadline, build, args)
            fields[field] = log.read_text().strip()
        expected_hash = [line.split('=', 1)[1].strip('"') for line in config
                         if line.startswith('CONFIG_MODULE_SIG_HASH=')]
        require(len(expected_hash) == 1 and fields['vermagic'].split()[0] == RELEASE and
                fields['signer'] and fields['sig_key'] and fields['sig_hashalgo'] == expected_hash[0] and
                not fields['depends'], 'off-root signature/vermagic/dependencies differ')
        require((destination / 'modules.order').read_text().splitlines() == ['kernel/' + NLS],
                'native installed order differs')
        pins(build, {key: row['sha256'] for key, row in identity['files'].items()})
        record['stage'] = {'root': str(raw), 'module': str(module), 'bytes': module.stat().st_size,
                           'sha256': sha(module), 'modinfo': fields,
                           'build_receipt_sha256': args.build_sha,
                           'scope': 'Native strip/sign off-root closure only; no real installation or initramfs.'}
        record['status'] = 'OFFROOT_MODULE_STAGE_COMPLETE'
    require(sha(build / '.config') == focused['config_sha256'], 'build/stage changed reviewed configuration')
    record['protected_after'] = protected(focused)
    record['source_after'] = source_pins(focused, source)
    record['boot_after'] = boot_files()
    require(record['protected_after'] == protected_before and record['source_after'] == source_before and
            record['boot_after'] == boot_before, 'protected source/installed files changed')
    record['identity_after'] = final_idle(focused['identity_after'], NORMAL_MODULE_NAMES)
    record['headroom_after'] = {'root': available('/'), 'output': available(build)}
    record['elapsed_seconds'] = time.time() - record['started_unix']
    atomic_json('result.json', record)
    print(json.dumps({'status': record['status'], 'receipt': str(out / 'result.json')}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if record is not None:
            record['error'] = str(error)
            if record.get('status') != 'INCOMPLETE_CHILD_RETAINED':
                record['status'] = 'FAILED_OR_INCOMPLETE'
            atomic_json('result.json', record)
        raise
