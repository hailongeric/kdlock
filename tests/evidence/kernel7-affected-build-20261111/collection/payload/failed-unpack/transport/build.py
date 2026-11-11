#!/usr/bin/env python3
"""VM-only kernel7 affected fixture builds and basic checks, never load or boot.

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

RELEASE = '7.0.0-38-kdrebuild7'
CORE = '0c97cd34cc6e3b75ac7ed0e233c813431264ef73'
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


def protected(focused):
    normal = canonical(focused['normal_source'])
    old = canonical(focused['kernel6_preserved'])
    return {'normal': pins(normal, focused['normal_after']),
            'kernel6': pins(old / 'build', focused['kernel6_after']),
            'kernel6_core': pins(old / 'source/kernel/kdlock', focused['kernel6_core_after'])}


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
    base = source.parent
    inp = Path('/mnt/kdlock-builds2/kdlock-main-kernel7-input-0c97cd34-01')
    integrated = dict(focused['applied_after'])
    require('Makefile' not in integrated, 'top-level Makefile unexpectedly applied')
    integrated['Makefile'] = focused['normal_after']['Makefile']
    result = {'package': pins(source / 'kernel/kdlock', focused['package_after']),
              'bodies': pins(source, focused['body_after']),
              'integration': pins(source, integrated),
              'immutable_input': pins(canonical(inp / 'package'), focused['package_after'])}
    provenance = ((inp / 'package.json',
                   '40122a5d8bad32dcca1e6bb9b706a85a807f8fa33dac2ce282ee31d55b7a8b07'),
                  (base / 'receipts/integration-application/manifest.json',
                   focused['application_manifest_sha256']),
                  (base / 'receipts/focused-01/integration-inspect.log',
                   '9d6e8bb28335b50833376c7f1d6190e2d884f4a08e523993f81caf328ca802ba'),
                  (Path(focused['resumed_from']), focused['original_failure_sha256']))
    for path, expected in provenance:
        canonical(path)
        require(sha(path) == expected, 'focused provenance changed: ' + str(path))
        result[str(path)] = expected
    manifest = json.loads(provenance[0][0].read_text())
    application = json.loads(provenance[1][0].read_text())
    require(manifest['files'] == focused['package_after'] and
            manifest['core_git_head'] == manifest['source_snapshot_git_head'] == CORE and
            manifest['intended_kernelrelease'] == RELEASE,
            'immutable package source/core/release differs')
    require(application['format'] == 'kdlock.exact-target-integration.v2' and
            application['after'] == focused['applied_after'] and
            application['tree'] == str(source) and application['build'] == str(base / 'build'),
            'exact seven-file committed application differs')
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


def dispatch(label, argv, deadline, limit, root, bounds, cwd=None, python_path=None):
    require(time.monotonic() < deadline, 'controller deadline expired before dispatch')
    stop = min(deadline, time.monotonic() + limit)
    row = {'label': label, 'argv': list(argv), 'cwd': str(cwd) if cwd else None, 'started_unix': time.time()}
    record['commands'].append(row)
    atomic_json('result.json', record)
    log = out / (label + '.log')
    env = dict(os.environ, LC_ALL='C', PATH='/usr/bin:/bin', PYTHONDONTWRITEBYTECODE='1')
    if python_path is not None:
        env['PYTHONPATH'] = str(python_path)
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


def baseline_result(path):
    value = json.loads(path.read_text())
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


def main():
    global out, record
    parser = argparse.ArgumentParser(description='VM-only kernel7 five affected modules/client/basic checks; no module load.')
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
            built['core_git_head'] == CORE and built['kernelrelease'] == RELEASE, 'actual successful linked kernel7 required')
    identity_path, identity = checked_json(build_path.parent / 'final-identity.json', built['final_identity_sha256'])
    require(set(identity['files']) == set(FILE_NAMES) and identity['module_count'] == 1 and
            identity['kernelrelease'] == RELEASE and re.fullmatch('[0-9a-f]{40}', identity['build_id']) is not None,
            'exact16 linked kernel7 outputs and fresh Build ID required')
    focus_path, focused = checked_json(built['focused_receipt'], built['focused_sha256'])
    require(focused['status'] == 'FOCUSED_COMPILE_COMPLETE' and focused['core_git_head'] == CORE and
            focused['kernelrelease'] == RELEASE and focused['target_units'] == {'core': 33, 'native': 8} and
            focused['package_before'] == focused['package_after'] and len(focused['package_after']) == 77 and
            len(focused['applied_after']) == 7, 'exact successful focused provenance required')
    source, build = canonical(built['source']), canonical(built['build'])
    require(source == Path(focused['source']) and build == Path(focused['build']) and
            source.parent == build.parent == Path('/mnt/kdlock-builds2/kdlock-main-kernel7-0c97cd34-01') and
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
            type(state['files']) is int and state['files'] == len(files) and type(state['transfer_bytes']) is int and
            state['transfer_bytes'] == sum(row['bytes'] for row in files.values()),
            'actual clean source export membership/commit/byte count differs')
    required = set(RUNNERS) | {'tests/test_source_boundaries.py', 'tests/kernel/mmap_api/userspace.c',
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
              'scope': 'Five external fixture modules/client and basic affected checks. No module load, selected gate, generated-code execution, boot or performance result.'}
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
    dispatch('client-build', [str(tools['gcc']), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                             str(inp / 'tests/kernel/mmap_api/userspace.c'), '-o', str(client)],
             deadline, bounds['client_seconds'], root, bounds)
    record['client'] = facts(client)
    syntax = 'import ast,pathlib,sys; files=sys.argv[1:]; assert len(files)==2; ' \
             '[ast.parse(pathlib.Path(p).read_bytes(),filename=p) for p in files]; print("AST_COMPLETE 2")'
    syntax_log = dispatch('new-runner-syntax', [str(tools['python']), '-c', syntax] + [str(inp / name) for name in RUNNERS],
                          deadline, bounds['check_seconds'], root, bounds, cwd=inp)
    require(syntax_log.read_text().strip() == 'AST_COMPLETE 2', 'both VM-only runner syntax checks must complete')
    tests = 'import pathlib,sys,unittest; root=pathlib.Path(sys.argv[1]); ' \
            'suite=unittest.defaultTestLoader.discover(str(root/"tests"),pattern="test_source_boundaries.py"); ' \
            'assert suite.countTestCases()==4; result=unittest.TextTestRunner(verbosity=2).run(suite); ' \
            'assert result.testsRun==4 and not result.skipped and result.wasSuccessful(); print("SOURCE_BOUNDARIES_COMPLETE 4")'
    tests_log = dispatch('source-boundary-four', [str(tools['python']), '-c', tests, str(inp)],
                         deadline, bounds['check_seconds'], root, bounds, cwd=inp, python_path=inp)
    require(tests_log.read_text().splitlines()[-1] == 'SOURCE_BOUNDARIES_COMPLETE 4',
            'all four affected boundary checks required, no skips')
    baseline = dispatch('unselected-syscalls', [str(client), '--threads', '2', '--iterations', '8', '--deadline-ms', '60000'],
                        deadline, bounds['check_seconds'], root, bounds, cwd=root)
    record['unselected_syscall_baseline'] = baseline_result(baseline)
    record['checks'] = {'new_runner_ast': 2, 'source_boundary_tests': 4, 'source_boundary_skips': 0,
                        'unselected_threads': 2, 'unselected_iterations_per_thread': 8}
    source_files(inp, files)
    require(sha(config_path) == args.config_sha and sha(build_path) == config['build_receipt_sha256'] and
            sha(identity_path) == built['final_identity_sha256'] and sha(focus_path) == built['focused_sha256'] and
            sha(manifest_path) == config['manifest_sha256'] and sha(state_path) == config['state_sha256'] and
            sha(archive) == config['archive_sha256'] and sha(sign_tool) == config['sign_file_sha256'] and
            sha(client) == record['client']['sha256'] and
            all(tools[name].resolve(strict=True) == resolved_tools[name] and
                sha(resolved_tools[name]) == config['tools'][name]['sha256'] for name in TOOLS), 'retained prerequisite changed')
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
