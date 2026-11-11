#!/usr/bin/env python3
"""VM-only kernel8 affected fixture builds and basic checks, never load or boot.

Consumes exact successful linked/focused receipts and a frozen source export.
Private signing-key data is never copied, hashed or printed by this helper.
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
import tarfile
import shutil
from pathlib import PurePosixPath

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


def idle(expected):
    current = {'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               'release': os.uname().release,
               'taint': Path('/proc/sys/kernel/tainted').read_text().strip(),
               'modules': Path('/proc/modules').read_text(), 'busy': [], 'blocked': []}
    require((current['boot'], current['release'], current['taint']) ==
            (expected['boot'], expected['release'], str(expected['taint'])),
            'running identity differs from focused normal boot')
    require(current['release'] == '7.0.0-38-kdlock1' and current['taint'] == '0',
            'untainted normal kernel required for offline build')
    loaded = {line.split()[0] for line in current['modules'].splitlines()}
    require(loaded == NORMAL_MODULE_NAMES, 'normal loaded-module names differ: ' + repr(sorted(loaded)))
    current['normal_module_names'] = sorted(loaded)
    current['normal_module_witness_sha256'] = NORMAL_MODULE_WITNESS_SHA256
    require(not any('fixture' in item.name or item.name in ('kd_mmap_api', 'kd_mmap_api_events', 'kd_rwsem_api')
                    for item in Path('/dev').iterdir()), 'fixture/API control remains')
    commands = {'make', 'gmake', 'cc1', 'cc1plus', 'gcc', 'gcc-15', 'clang',
                'ld', 'ld.bfd', 'as', 'objtool', 'fstrim', 'depmod', 'insmod', 'rmmod'}
    for item in Path('/proc').iterdir():
        if not item.name.isdigit() or int(item.name) == os.getpid():
            continue
        try:
            command = (item / 'comm').read_text().strip()
            if command in commands or command.startswith(('kd-fixture/', 'kd-scene/', 'kd-reader/')):
                current['busy'].append({'pid': int(item.name), 'comm': command})
            for task in (item / 'task').iterdir():
                if '\nState:\tD ' in '\n' + (task / 'status').read_text():
                    current['blocked'].append({'pid': int(item.name), 'tid': int(task.name)})
        except (FileNotFoundError, ProcessLookupError):
            pass
    require(not current['busy'] and not current['blocked'], 'build/workload or blocked task remains: ' + json.dumps(current, sort_keys=True))
    return current


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
                        r'[^\n]+:(?:[0-9]+(?::[0-9]+)?:)?\s*(?:fatal error|error|warning|note):)')
    rows = []
    for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
        if prefix.match(line.strip()):
            rows.append({'line': number, 'text': line})
    return rows


MODULES = (
    ('native-api', 'tests/kernel/rwsem_api/payload', 'kd_rwsem_api_fixture.ko'),
    ('mmap', 'tests/kernel/mmap_api/payload', 'kd_mmap_api_provider.ko'),
    ('killable', 'tests/kernel/rwsem_killable/payload', 'kd_rwsem_killable_fixture.ko'),
    ('rwsem', 'tests/kernel/rwsem/payload', 'kd_rwsem_runtime_fixture.ko'),
    ('mutex', 'tests/kernel/payload', 'kd_runtime_fixture.ko'),
)
RUNNERS = ('tests/kernel/mmap_api/runner.py', 'tests/kernel/rwsem_killable/runner.py')
TOOLS = ('make', 'gcc', 'modinfo', 'python')
retained_children = []


def facts(path):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def source_files(root, files):
    entries = list(root.rglob('*'))
    require(not any(path.is_symlink() for path in entries), 'snapshot contains a symlink')
    require({str(path.relative_to(root)) for path in entries if path.is_file()} == set(files),
            'source snapshot membership changed')
    for name, row in files.items():
        path = root / name
        require(path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'source snapshot bytes differ: ' + name)


def unpack(archive, files, destination, maximum):
    require(type(maximum) is int and 0 < maximum <= 16 * 1024**2, 'explicit finite source-byte limit required')
    total = 0
    for name, row in files.items():
        relative = PurePosixPath(name)
        require(name == str(relative) and not relative.is_absolute() and '..' not in relative.parts and
                set(row) == {'bytes', 'sha256'} and type(row['bytes']) is int and row['bytes'] >= 0 and
                re.fullmatch('[0-9a-f]{64}', row['sha256']) is not None, 'invalid source manifest member')
        total += row['bytes']
    require(files and total <= maximum, 'source manifest exceeds caller byte bound')
    seen = set()
    destination.mkdir(mode=0o700)
    with tarfile.open(archive, 'r:') as stream:
        for member in stream:
            require(member.isfile() and member.name in files and member.name not in seen,
                    'archive contains an unexpected/nonregular member')
            row = files[member.name]
            require(member.size == row['bytes'], 'archive member extent differs')
            with stream.extractfile(member) as source:
                data = source.read(member.size + 1)
            require(len(data) == member.size and hashlib.sha256(data).hexdigest() == row['sha256'],
                    'archive member bytes differ')
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            seen.add(member.name)
    require(seen == set(files), 'archive is missing source members')
    source_files(destination, files)


def fresh_recovery(path, expected, policy):
    unused, value = checked_json(path, expected)
    require(set(policy) == {'hostname', 'pid', 'exe', 'image_paths', 'tag', 'maximum_age_seconds', 'host_floor_bytes'},
            'explicit actual recovery identity and age policy required')
    require(type(policy['pid']) is int and policy['pid'] > 0 and
            type(policy['maximum_age_seconds']) is int and 1 <= policy['maximum_age_seconds'] <= 900 and
            type(policy['host_floor_bytes']) is int and policy['host_floor_bytes'] >= 8 * 1024**3 and
            len(policy['image_paths']) == 3 and len(set(policy['image_paths'])) == 3 and policy['tag'],
            'bounded three-image recovery policy required')
    require(all(value[name] == policy[name] for name in ('hostname', 'pid', 'exe')), 'actual host/QEMU differs')
    captured = datetime.datetime.fromisoformat(value['utc'])
    require(captured.tzinfo is not None and 0 <= time.time() - captured.timestamp() <= policy['maximum_age_seconds'],
            'fresh actual timezone-bearing recovery receipt required')
    images = value['images']
    require(len(images) == 3 and {row['path'] for row in images} == set(policy['image_paths']) and
            all(row['path'] == row['realpath'] and row['open_fds'] and
                row['host_available'] >= policy['host_floor_bytes'] for row in images),
            'all three attached image identities/headroom must match')
    monitor = value['hmp']
    texts = {row['command']: row['output'] for row in monitor}
    require(len(texts) == len(monitor) and 'VM status: running' in texts.get('info status', ''), 'VM status differs')
    marker = 'List of snapshots present on all disks:'
    listing = texts.get('info snapshots', '')
    require(marker in listing, 'complete all-disk recovery list missing')
    common = listing.split(marker, 1)[1].split('List of partial', 1)[0]
    require(any(policy['tag'] in line.split() for line in common.splitlines()), 'exact complete recovery tag absent')
    return {'sha256': expected, 'captured_unix': captured.timestamp(), 'tag': policy['tag'], 'images': images}


def dispatch(label, argv, deadline, limit, root, bounds, cwd=None, python_path=None,
             gs_config=None):
    require(time.monotonic() < deadline, 'controller deadline expired before dispatch')
    stop = min(deadline, time.monotonic() + limit)
    row = {'label': label, 'argv': list(argv), 'cwd': str(cwd) if cwd else None, 'started_unix': time.time()}
    record['commands'].append(row)
    atomic_json('result.json', record)
    log = out / (label + '.log')
    env = dict(os.environ, LC_ALL='C', PATH='/usr/bin:/bin', PYTHONDONTWRITEBYTECODE='1')
    if python_path is not None:
        env['PYTHONPATH'] = str(python_path)
    if gs_config is not None:
        env['KDLOCK_KERNEL_GS_TEST_CONFIG'] = str(gs_config)
    with log.open('xb') as output:
        child = subprocess.Popen(argv, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, env=env)
        retained_children.append(child)
        row['pid'] = child.pid
        atomic_json('result.json', record)
        while child.poll() is None:
            if (time.monotonic() >= stop or available('/') < bounds['root_floor_bytes'] or
                    available(root) < bounds['output_floor_bytes'] or
                    sum(path.stat().st_size for path in out.glob('*.log')) > bounds['log_bytes']):
                row.update(status='CHILD_RETAINED', elapsed_seconds=time.time() - row['started_unix'])
                record['status'] = 'INCOMPLETE_CHILD_RETAINED'
                atomic_json('result.json', record)
                raise RuntimeError('deadline/space/log observer stopped; child retained, no drain proof')
            time.sleep(0.25)
        row.update(returncode=child.returncode, elapsed_seconds=time.time() - row['started_unix'])
    row['log_sha256'] = sha(log)
    atomic_json('result.json', record)
    require(child.returncode == 0, label + ' failed; original output retained')
    return log


def baseline_value(value):
    require(value['status'] == 'syscall_completion_pass' and value['overall_pass'] is True and
            value['kd_observations'] == 'not_collected' and value['selected_gate']['requested'] is False and
            value['threads'] == value['created_threads'] == 2 and value['iterations_per_thread'] == 8 and
            value['deadline_ms'] == 60000 and value['completed_iterations'] == 16 and
            value['worker_errors'] == value['arena_cleanup_errno'] == value['setup_errno'] == 0 and
            not value['deadline_exceeded'] and value['setup_error'] == 'none' and
            value['arena_reservations'] == 1 and value['mapping_pages'] == 2,
            'unselected syscall baseline failed or was selected')
    page = os.sysconf('SC_PAGE_SIZE')
    require(value['page_bytes'] == page and len(value['workers']) == 2, 'baseline page/worker count differs')
    for index, worker in enumerate(value['workers']):
        require(worker['id'] == index and worker['tid'] > 0 and worker['completed'] == 8 and
                worker['mmap_attempts'] == worker['mmap_successes'] == 24 and
                worker['munmap_attempts'] == worker['munmap_successes'] == 16 and
                worker['mincore_attempts'] == worker['unmapped_page_checks'] == 32 and
                worker['reuse_successes'] == 8 and worker['fresh_zero_bytes'] == worker['written_bytes'] ==
                worker['readback_bytes'] == 32 * page and not worker['deadline_reached'] and
                worker['error'] == 'none' and worker['errno'] == 0,
                'actual unselected worker effects differ')
    return value


CLIENT_FILES = ('tests/kernel/mmap_api/userspace.c',
                'tests/kernel/mmap_api/userspace_jit.inc', 'tests/kernel/mmap_api/abi.h')


def client_reuse(config, inp, files, normal_identity):
    require(set(config) == {'compile_receipt', 'compile_receipt_sha256', 'basic_receipt', 'basic_receipt_sha256'},
            'exact prior client/build and baseline receipt pins required')
    old_path, old = checked_json(config['compile_receipt'], config['compile_receipt_sha256'])
    basic_path, basic = checked_json(config['basic_receipt'], config['basic_receipt_sha256'])
    require(old['source_git_head'] == 'e01a89d95aec9e2efa0937d88f66a92b95b71e08' and
            basic['status'] == 'AFFECTED_MODULE_BUILDS_AND_BASIC_CHECKS_COMPLETE' and
            basic['prior_result'] == str(old_path) and basic['prior_result_sha256'] == config['compile_receipt_sha256'] and
            basic['client'] == old['client'], 'exact prior client provenance differs')
    client = canonical(old['client']['path'])
    require(os.access(client, os.X_OK) and facts(client) == old['client'] and old['client']['sha256'] ==
            'bae90760f57f3930e1ff48443140eb096ea316c1fed00ae1840127f6985a4cd2',
            'prior proven client bytes differ')
    commands = [row for row in old['commands'] if row['label'] == 'client-build']
    require(len(commands) == 1 and commands[0]['returncode'] == 0 and
            commands[0]['argv'][-1] == str(client) and
            sha(old_path.parent / 'client-build.log') == commands[0]['log_sha256'],
            'actual prior strict C compile is not retained')
    require(commands[0]['argv'][1:8] == ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
            str(Path(old['source_input']) / CLIENT_FILES[0])], 'prior ordinary C build flags/source differ')
    source = canonical(old['source_input'])
    prior_manifest_path, prior_files = checked_json(old['arguments']['manifest'], old['arguments']['manifest_sha256'])
    before = {name: facts(canonical(source / name)) for name in CLIENT_FILES}
    require(all(before[name]['sha256'] == prior_files[name]['sha256'] and
                before[name]['bytes'] == prior_files[name]['bytes'] for name in CLIENT_FILES),
            'prior client source changed from its actual compiled snapshot')
    # Only a reviewed source-byte change selects a new compile. Broken prior
    # receipts/artifacts stop above rather than silently becoming a rebuild.
    same = all(before[name]['sha256'] == files[name]['sha256'] and before[name]['bytes'] == files[name]['bytes']
               for name in CLIENT_FILES)
    if not same:
        return None
    for sample in (basic['identity_before'], basic['identity_after']):
        require(all(str(sample[name]) == str(normal_identity[name]) for name in ('boot', 'release', 'taint')) and
                not sample['busy'] and not sample['blocked'], 'prior baseline normal identity differs')
    baseline = baseline_value(basic['unselected_syscall_baseline'])
    return {'compile_receipt': str(old_path), 'compile_receipt_sha256': config['compile_receipt_sha256'],
            'basic_receipt': str(basic_path), 'basic_receipt_sha256': config['basic_receipt_sha256'],
            'compiled_source_git_head': old['source_git_head'], 'client': facts(client),
            'source_manifest': str(prior_manifest_path),
            'source_manifest_sha256': old['arguments']['manifest_sha256'],
            'source_files': before, 'baseline': baseline,
            'scope': 'Exact prior userspace binary and prior same-normal baseline only; no candidate8 runtime result.'}


def gs_target(receipt_dir, identity, build):
    path = receipt_dir / 'gs-config.json'
    config = json.loads(canonical(path).read_text())
    witness = identity['gs_witness']
    require(config['build_id'] == identity['build_id'] and config['verified_for_running_kernel'] is False and
            config['current_task_gs_offset'] == identity['gs_symbols']['current_task'] ==
            identity['gs_symbols']['const_current_task'] and
            int(witness['current_task'], 0) == config['current_task_gs_offset'] and
            config['percpu_section_va'] == identity['gs_symbols']['__per_cpu_start'],
            'fresh linked GS witness/config disagree')
    result = {'site': witness['site'], 'instruction_hex': witness['instruction_hex'],
              'current_task': witness['current_task']}
    for key, relative in (('vmlinux', 'vmlinux'), ('system_map', 'System.map'), ('kernel_config', '.config')):
        source_key = 'kernel_elf' if key == 'vmlinux' else key
        require(config[source_key] == str(build / relative) and
                config[source_key + '_sha256'] == identity['files'][relative]['sha256'],
                'actual linked GS target-file provenance differs: ' + key)
        result[key] = config[source_key]
        result[key + '_sha256'] = config[source_key + '_sha256']
    return result


def main():
    global out, record
    parser = argparse.ArgumentParser(description='VM-only kernel8 five affected modules/client/basic checks; no module load.')
    parser.add_argument('--config', required=True)
    parser.add_argument('--config-sha', required=True)
    args = parser.parse_args()
    config_path, config = checked_json(args.config, args.config_sha)
    require(os.geteuid() == 0, 'VM root required for protected receipts, not module load')
    environment()
    require(not any(name in os.environ for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONOPTIMIZE', 'GCC_EXEC_PREFIX',
                                                   'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH')),
            'unreviewed compiler/Python environment override')
    require(config['kernel_core_git_head'] == CORE and config['kernelrelease'] == RELEASE and
            re.fullmatch('[0-9a-f]{40}', config['source_git_head']) is not None,
            'exact reviewed kernel/source commit identities required')
    bounds = config['bounds']
    require(set(bounds) == {'jobs', 'total_seconds', 'module_seconds', 'client_seconds', 'check_seconds',
                           'root_floor_bytes', 'output_floor_bytes', 'log_bytes', 'source_bytes'} and
            all(type(value) is int and value > 0 for value in bounds.values()) and bounds['jobs'] == 8 and
            bounds['total_seconds'] <= 1200 and bounds['module_seconds'] <= 180 and
            bounds['client_seconds'] <= 60 and bounds['check_seconds'] <= 60 and
            bounds['root_floor_bytes'] >= 1024**3 and bounds['output_floor_bytes'] >= 4 * 1024**3 and
            bounds['log_bytes'] <= 512 * 1024**2, 'explicit reviewed finite build/check bounds required')
    build_path, built = checked_json(config['build_receipt'], config['build_receipt_sha256'])
    require(built['status'] == 'BUILT_AND_LINKED_IDENTITY_VERIFIED' and built['phase'] == 'build' and
            built['core_git_head'] == CORE and built['kernelrelease'] == RELEASE, 'actual successful linked kernel8 required')
    identity_path, identity = checked_json(build_path.parent / 'final-identity.json', built['final_identity_sha256'])
    require(set(identity['files']) == set(FILE_NAMES) and identity['module_count'] == 1 and
            identity['kernelrelease'] == RELEASE and re.fullmatch('[0-9a-f]{40}', identity['build_id']) is not None,
            'exact16 linked kernel8 outputs and fresh Build ID required')
    focus_path, focused = checked_json(built['focused_receipt'], built['focused_sha256'])
    require(focused['status'] == 'FOCUSED_COMPILE_COMPLETE' and focused['core_git_head'] == CORE and
            focused['kernelrelease'] == RELEASE and focused['target_units'] == {'core': 33, 'native': 8} and
            focused['package_before'] == focused['package_after'] and len(focused['package_after']) == 78 and
            len(focused['applied_after']) == 7, 'exact successful focused provenance required')
    source, build = canonical(built['source']), canonical(built['build'])
    require(source == Path(focused['source']) and build == Path(focused['build']) and
            source.parent == build.parent == Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01') and
            identity['source'] == str(source) and identity['build'] == str(build), 'actual immutable kernel source/O differs')
    output_pins = {name: row['sha256'] for name, row in identity['files'].items()}
    pins(build, output_pins)
    require(sha(build / '.config') == focused['config_sha256'] and
            (build / 'include/config/kernel.release').read_text().strip() == RELEASE,
            'actual output config/release differs')
    signing_config = (build / '.config').read_text().splitlines()
    require('CONFIG_MODULE_SIG_KEY="certs/signing_key.pem"' in signing_config and
            'CONFIG_MODULE_SIG_HASH="sha512"' in signing_config, 'actual normal signing configuration differs')
    sign_tool = canonical(build / 'scripts/sign-file')
    key = canonical(build / 'certs/signing_key.pem')
    certificate = canonical(build / 'certs/signing_key.x509')
    require(sha(sign_tool) == config['sign_file_sha256'] and not key.is_symlink() and key.is_file(),
            'actual signing tool/key required; private key data is not read for receipts')
    tools, resolved_tools = {}, {}
    require(set(config['tools']) == set(TOOLS), 'four exact build/check tool pins required')
    for name, row in config['tools'].items():
        require(set(row) == {'path', 'resolved_path', 'sha256'}, 'exact tool invocation/resolved-byte pins required')
        tools[name] = Path(row['path'])
        resolved_tools[name] = canonical(row['resolved_path'])
        require(tools[name].is_absolute() and tools[name].resolve(strict=True) == resolved_tools[name] and
                sha(resolved_tools[name]) == row['sha256'], 'tool alias/resolved bytes differ: ' + name)
    require(tools['modinfo'].name == 'modinfo', 'retain the actual kmod modinfo invocation name')
    archive = canonical(config['archive'])
    require(archive.stat().st_size == config['archive_bytes'] and sha(archive) == config['archive_sha256'],
            'outer source archive extent/SHA differs')
    manifest_path, files = checked_json(config['manifest'], config['manifest_sha256'])
    state_path, state = checked_json(config['state'], config['state_sha256'])
    require(set(state) == {'source_git_head', 'git_status', 'files', 'transfer_bytes'} and
            state['source_git_head'] == config['source_git_head'] and state['git_status'] == '' and
            type(state['files']) is int and state['files'] == config['source_file_count'] == len(files) and type(state['transfer_bytes']) is int and
            state['transfer_bytes'] == sum(row['bytes'] for row in files.values()),
            'actual clean source export membership/commit/byte count differs')
    required = set(RUNNERS) | {'tests/test_source_boundaries.py', 'tests/test_kernel_gs_rip.py', 'include/asm_head.h',
                            'tests/kernel/mmap_api/userspace.c',
                            'tests/kernel/mmap_api/userspace_jit.inc', 'tests/kernel/mmap_api/abi.h',
                            'tests/kernel/mmap_api/payload/mmap_jit_profile.inc',
                            'tests/kernel/payload/runtime_fixture_observe.inc', 'tests/kernel/run_runtime_fixture.py'}
    required.update(relative + '/Kbuild' for unused, relative, unused_name in MODULES)
    require(required <= set(files), 'required runner/client/private include/build membership missing')
    for name, expected in focused['package_after'].items():
        require(files[name]['sha256'] == expected, 'snapshot kernel package differs from linked input: ' + name)
    identity_before = idle(focused['identity_after'])
    rec = fresh_recovery(config['recovery'], config['recovery_sha256'], config['recovery_policy'])
    root = Path(config['output'])
    require(root.is_absolute() and not root.exists() and root.parent.resolve(strict=True) / root.name == root and
            not root.is_relative_to(source) and not root.is_relative_to(build), 'fresh separate output namespace required')
    require(available('/') >= bounds['root_floor_bytes'] and available(root.parent) >= bounds['output_floor_bytes'],
            'actual root/output headroom below explicit floor')
    protected_before, source_before, boot_before = protected(focused), source_pins(focused, source), boot_files()
    require(protected_before == built['protected_after'] and source_before == built['source_after'] and
            boot_before == built['boot_after'], 'actual linked-build protections changed before fixture builds')
    root.mkdir(mode=0o700)
    out = root / 'receipts'
    out.mkdir(mode=0o700)
    inp, signed = root / 'input', root / 'signed'
    signed.mkdir(mode=0o700)
    record = {'status': 'PREPARED', 'config': str(config_path), 'config_sha256': args.config_sha,
              'kernel_core_git_head': CORE, 'source_git_head': config['source_git_head'], 'kernelrelease': RELEASE,
              'build_receipt': str(build_path), 'build_receipt_sha256': config['build_receipt_sha256'],
              'final_identity_sha256': built['final_identity_sha256'], 'linked_build_id': identity['build_id'],
              'linked_gs_symbols': identity['gs_symbols'], 'running_candidate_proof': False,
              'source_input': str(inp), 'arguments': config, 'commands': [], 'modules': {},
              'core_pins_before': pins(build, output_pins), 'protected_before': protected_before,
              'kernel_source_before': source_before, 'boot_before': boot_before, 'identity_before': identity_before,
              'recovery': rec, 'signing': {'public_certificate_sha256': output_pins['certs/signing_key.x509'],
                                         'private_key_data_recorded': False},
              'scope': 'Five external fixture modules, exact prior client reuse or fresh changed-source build, and basic affected checks. No module load, selected gate, generated-code execution, boot or performance result.'}
    atomic_json('result.json', record)
    unpack(archive, files, inp, bounds['source_bytes'])
    deadline = time.monotonic() + bounds['total_seconds']
    for label, relative, name in MODULES:
        module_out = root / (label + '-build')
        module_out.mkdir(mode=0o700)
        log = dispatch(label + '-build', [str(tools['make']), '-C', str(source), 'O=' + str(build),
                       'M=' + str(inp / relative), 'MO=' + str(module_out), 'KERNELRELEASE=' + RELEASE,
                       '-j8', 'V=1', 'modules'], deadline, bounds['module_seconds'], root, bounds)
        module = canonical(module_out / name)
        require(sorted(module_out.glob('*.ko')) == [module], 'exact named module output required')
        unsigned = facts(module)
        target = signed / name
        with module.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        dispatch(label + '-sign', [str(sign_tool), 'sha512', str(key), str(certificate), str(target)],
                 deadline, bounds['check_seconds'], root, bounds)
        require(sha(module) == unsigned['sha256'], 'signing changed the unsigned build output')
        fields = {}
        for field in ('vermagic', 'signer', 'sig_key', 'sig_hashalgo', 'depends'):
            metadata = dispatch(label + '-' + field, [str(tools['modinfo']), '-F', field, str(target)],
                                deadline, bounds['check_seconds'], root, bounds)
            fields[field] = metadata.read_text().strip()
        require(fields['vermagic'].split()[0] == RELEASE and fields['signer'] and fields['sig_key'] and
                fields['sig_hashalgo'] == 'sha512' and fields['depends'] == '',
                'actual signed module identity/dependencies differ')
        if record['modules']:
            previous = next(iter(record['modules'].values()))['modinfo']
            require(all(fields[field] == previous[field] for field in ('signer', 'sig_key', 'sig_hashalgo', 'vermagic')),
                    'signed fixture metadata differs across modules')
        record['modules'][label] = {'unsigned': unsigned, 'signed': facts(target), 'modinfo': fields,
                                    'diagnostics': diagnostic_rows(log)}
        source_files(inp, files)
        pins(build, output_pins)
        atomic_json('result.json', record)
    client = root / 'mmap-userspace'
    reuse = client_reuse(config['client_reuse'], inp, files, focused['identity_after'])
    if reuse is None:
        dispatch('client-build', [str(tools['gcc']), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                                 str(inp / 'tests/kernel/mmap_api/userspace.c'), '-o', str(client)],
                 deadline, bounds['client_seconds'], root, bounds)
        record['client_mode'] = 'fresh_compile_source_changed'
    else:
        previous = canonical(reuse['client']['path'])
        with previous.open('rb') as src, client.open('xb') as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        os.chmod(client, previous.stat().st_mode & 0o777)
        require(facts(previous) == reuse['client'] and sha(client) == reuse['client']['sha256'],
                'reused client source/output changed during copy')
        record['client_mode'] = 'exact_prior_binary_reuse'
        record['client_reuse'] = reuse
    record['client'] = facts(client)
    syntax = 'import ast,pathlib,sys; files=sys.argv[1:]; assert len(files)==2; ' \
             '[ast.parse(pathlib.Path(p).read_bytes(),filename=p) for p in files]; print("AST_COMPLETE 2")'
    syntax_log = dispatch('new-runner-syntax', [str(tools['python']), '-c', syntax] + [str(inp / name) for name in RUNNERS],
                          deadline, bounds['check_seconds'], root, bounds, cwd=inp)
    require(syntax_log.read_text().strip() == 'AST_COMPLETE 2', 'both VM-only runner syntax checks must complete')
    tests = 'import pathlib,sys,unittest; root=pathlib.Path(sys.argv[1]); ' \
            'loader=unittest.TestLoader(); suite=loader.discover(str(root/"tests"),pattern="test_source_boundaries.py"); ' \
            'assert suite.countTestCases()==8, (suite.countTestCases(),loader.errors); result=unittest.TextTestRunner(verbosity=2).run(suite); ' \
            'assert result.testsRun==8 and not result.skipped and result.wasSuccessful(); print("SOURCE_BOUNDARIES_COMPLETE 8")'
    tests_log = dispatch('source-boundary-eight', [str(tools['python']), '-c', tests, str(inp)],
                         deadline, bounds['check_seconds'], root, bounds, cwd=inp, python_path=inp)
    require(tests_log.read_text().splitlines()[-1] == 'SOURCE_BOUNDARIES_COMPLETE 8',
            'all eight affected boundary checks required, no skips')
    gs_config = out / 'gs-target.json'
    linked_gs_path = canonical(identity_path.parent / 'gs-config.json')
    linked_gs_sha = sha(linked_gs_path)
    gs_value = gs_target(identity_path.parent, identity, build)
    atomic_json('gs-target.json', gs_value)
    gs_sha = sha(gs_config)
    gs_tests = 'import pathlib,sys,unittest; root=pathlib.Path(sys.argv[1]); ' \
               'loader=unittest.TestLoader(); suite=loader.discover(str(root/"tests"),pattern="test_kernel_gs_rip.py"); ' \
               'assert suite.countTestCases()==5, (suite.countTestCases(),loader.errors); result=unittest.TextTestRunner(verbosity=2).run(suite); ' \
               'assert result.testsRun==5 and not result.skipped and result.wasSuccessful(); print("KERNEL_GS_COMPLETE 5")'
    gs_log = dispatch('linked-gs-five', [str(tools['python']), '-c', gs_tests, str(inp)],
                      deadline, bounds['check_seconds'], root, bounds, cwd=inp, python_path=inp,
                      gs_config=gs_config)
    require(gs_log.read_text().splitlines()[-1] == 'KERNEL_GS_COMPLETE 5' and sha(gs_config) == gs_sha,
            'all five actual linked-byte GS checks required, no skips')
    record['gs_checks'] = {'config': str(gs_config), 'sha256': gs_sha, 'tests': 5, 'skips': 0,
                           'linked_config': str(linked_gs_path), 'linked_config_sha256': linked_gs_sha,
                           'scope': 'Offline actual kernel8 linked-byte decoder/lowering checks; no running-candidate proof.'}
    if reuse is None:
        baseline = dispatch('unselected-syscalls', [str(client), '--threads', '2', '--iterations', '8', '--deadline-ms', '60000'],
                            deadline, bounds['check_seconds'], root, bounds, cwd=root)
        record['unselected_syscall_baseline'] = baseline_value(json.loads(baseline.read_text()))
        record['unselected_baseline_mode'] = 'fresh_client_normal_kernel'
    else:
        record['unselected_syscall_baseline'] = reuse['baseline']
        record['unselected_baseline_mode'] = 'prior_same_source_client_and_normal_identity'
    record['checks'] = {'new_runner_ast': 2, 'source_boundary_tests': 8, 'source_boundary_skips': 0,
                        'linked_gs_tests': 5, 'linked_gs_skips': 0,
                        'unselected_threads': 2, 'unselected_iterations_per_thread': 8,
                        'unselected_baseline_reexecuted': reuse is None}
    source_files(inp, files)
    require(sha(config_path) == args.config_sha and sha(build_path) == config['build_receipt_sha256'] and
            sha(identity_path) == built['final_identity_sha256'] and sha(focus_path) == built['focused_sha256'] and
            sha(manifest_path) == config['manifest_sha256'] and sha(state_path) == config['state_sha256'] and
            sha(archive) == config['archive_sha256'] and sha(sign_tool) == config['sign_file_sha256'] and
            sha(client) == record['client']['sha256'] and
            all(tools[name].resolve(strict=True) == resolved_tools[name] and
                sha(resolved_tools[name]) == config['tools'][name]['sha256'] for name in TOOLS), 'retained prerequisite changed')
    if reuse is not None:
        require(client_reuse(config['client_reuse'], inp, files, focused['identity_after']) == reuse,
                'prior client/baseline provenance changed')
    require(sha(gs_config) == gs_sha and sha(linked_gs_path) == linked_gs_sha,
            'actual linked GS test config changed')
    record['core_pins_after'] = pins(build, output_pins)
    record['protected_after'], record['kernel_source_after'], record['boot_after'] = protected(focused), source_pins(focused, source), boot_files()
    require(record['protected_after'] == protected_before and record['kernel_source_after'] == source_before and
            record['boot_after'] == boot_before, 'protected kernel/source/boot state changed')
    record['identity_after'] = idle(focused['identity_after'])
    record['headroom_after'] = {'root': available('/'), 'output': available(root)}
    record['status'] = 'AFFECTED_MODULES_CLIENT_AND_BASIC_CHECKS_COMPLETE'
    atomic_json('result.json', record)
    print(json.dumps({'status': record['status'], 'receipt': str(out / 'result.json')}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if record is not None:
            if record.get('status') != 'INCOMPLETE_CHILD_RETAINED':
                record['status'] = 'FAILED_OR_INCOMPLETE'
            record['error'] = repr(error)
            atomic_json('result.json', record)
        raise
