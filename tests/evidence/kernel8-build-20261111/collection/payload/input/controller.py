#!/usr/bin/env python3
"""VM-only fresh kernel8 v3 integration and exact 33+8 object compilation.

No network, load, boot, test or retry. Every refusal retains its original output.
A command observer never kills a child or treats timeout as source drain.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import time

CORE = '0d42063ead37dc8fc1631fa56c8348890ede9c5f'
RELEASE = '7.0.0-38-kdrebuild8'
BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
FORMAT = 'kdlock.exact-target-integration.v3'
CONFIG_SHA = '31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483'
ENV_KEYS = {'KCFLAGS', 'KAFLAGS', 'KCPPFLAGS', 'CFLAGS_KERNEL', 'CFLAGS_MODULE', 'AFLAGS_KERNEL',
            'AFLAGS_MODULE', 'LLVM', 'LLVM_IAS', 'CC', 'LD', 'HOSTCC', 'HOSTCXX', 'CROSS_COMPILE',
            'KCONFIG_CONFIG', 'ARCH', 'MAKEFLAGS', 'MFLAGS', 'PYTHONPATH', 'PYTHONHOME',
            'PYTHONOPTIMIZE', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH'}
record = None
out = None
children = []


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def canonical(path):
    value = Path(path)
    require(value.is_absolute() and value.resolve(strict=True) == value, 'canonical existing path required: ' + str(value))
    return value


def checked_json(path, expected):
    value = canonical(path)
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None and sha(value) == expected,
            'JSON pin mismatch: ' + str(value))
    return value, json.loads(value.read_text())


def put(name, value):
    path = out / name
    temporary = path.with_name('.' + path.name + '.new')
    with temporary.open('xb') as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def hashes(root, expected):
    root = canonical(root)
    require(expected and isinstance(expected, dict), 'nonempty exact file pins required')
    result = {}
    for name, digest in expected.items():
        relative = PurePosixPath(name)
        require(name == str(relative) and not relative.is_absolute() and '..' not in relative.parts,
                'invalid pinned member')
        path = canonical(root / name)
        require(path.is_file(), 'pinned regular file required')
        before = path.stat()
        actual = sha(path)
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                'file changed while reading: ' + str(path))
        require(actual == digest, 'pinned bytes differ: ' + str(path))
        result[name] = actual
    return result


def available(path):
    value = os.statvfs(path)
    return value.f_bavail * value.f_frsize


def protected(pins):
    result = {}
    for group in pins['preserved_groups']:
        require(group['name'] not in result, 'duplicate preserved group')
        result[group['name']] = hashes(Path(group['root']), group['files'])
    result['provenance_files'] = {}
    for name, digest in pins['provenance_files'].items():
        path = canonical(name)
        require(sha(path) == digest, 'preserved receipt changed: ' + name)
        result['provenance_files'][name] = digest
    manifest = canonical(pins['normal_manifest'])
    require(sha(manifest) == pins['normal_manifest_sha256'], 'normal authenticated bundle changed')
    result['normal_manifest_sha256'] = pins['normal_manifest_sha256']
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
    result['/lib/modules namespaces'] = sorted(path.name for path in Path('/lib/modules').iterdir())
    return result


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
        put('result.json', record)
        if sample['busy'] or sample['dthreads']:
            clear_at = None
        elif clear_at is None:
            clear_at = time.monotonic()
        elif time.monotonic() - clear_at >= 10:
            return sample
        require(time.monotonic() < deadline, 'final strict idle not established within60s; all samples retained')
        time.sleep(min(10, max(0, deadline - time.monotonic())))


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


def execute(label, argv, deadline, bounds, cwd=None):
    require(time.monotonic() < deadline, 'deadline expired before command dispatch')
    row = {'label': label, 'argv': list(argv), 'cwd': str(cwd) if cwd else None, 'started_unix': time.time()}
    record['commands'].append(row)
    put('result.json', record)
    log = out / (label + '.log')
    with log.open('xb') as stream:
        child = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, PATH='/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1'))
        children.append(child)
        row['pid'] = child.pid
        put('result.json', record)
        while child.poll() is None:
            if (time.monotonic() >= deadline or available('/') < bounds['root_floor_bytes'] or
                    available(BASE.parent) < bounds['output_floor_bytes'] or
                    sum(path.stat().st_size for path in out.glob('*.log')) > bounds['log_bytes']):
                row['status'] = 'CHILD_RETAINED'
                record['status'] = 'INCOMPLETE_CHILD_RETAINED'
                put('result.json', record)
                raise RuntimeError('deadline/space/log observer stopped; child retained, no drain proof')
            time.sleep(.25)
        row['returncode'] = child.returncode
        row['elapsed_seconds'] = time.time() - row['started_unix']
    row['log_sha256'] = sha(log)
    put('result.json', record)
    require(child.returncode == 0, label + ' failed; exact output retained')
    return log


def unpack(archive, files, root):
    seen = set()
    total = 0
    root.mkdir(parents=True, mode=0o700)
    with tarfile.open(archive, 'r:') as stream:
        for member in stream:
            name = PurePosixPath(member.name)
            require(member.name == str(name) and not name.is_absolute() and '..' not in name.parts and
                    member.isfile() and member.name in files and member.name not in seen and
                    0 <= member.size <= 4 * 1024**2, 'unexpected archive member')
            total += member.size
            require(total <= 4 * 1024**2, 'kernel package source bound exceeded')
            with stream.extractfile(member) as source:
                data = source.read(member.size + 1)
            require(len(data) == member.size and hashlib.sha256(data).hexdigest() == files[member.name],
                    'archive source bytes differ')
            path = root / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as target:
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            seen.add(member.name)
    require(seen == set(files), 'archive membership differs')
    return hashes(root, files)


def main():
    global record, out
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--config-sha', required=True)
    args = parser.parse_args()
    config_path, config = checked_json(args.config, args.config_sha)
    require(os.geteuid() == 0, 'VM root required')
    require(not any(name in os.environ for name in ENV_KEYS) and
            not any(name.startswith(('CFLAGS', 'AFLAGS', 'KBUILD_', 'INSTALL_MOD_')) for name in os.environ),
            'unreviewed build environment override')
    bounds = config['bounds']
    require(set(bounds) == {'jobs', 'total_seconds', 'root_floor_bytes', 'output_floor_bytes', 'log_bytes'} and
            all(type(value) is int and value > 0 for value in bounds.values()) and bounds['jobs'] == 8 and
            bounds['total_seconds'] <= 900 and bounds['root_floor_bytes'] >= 1024**3 and
            bounds['output_floor_bytes'] >= 48 * 1024**3 and bounds['log_bytes'] <= 4 * 1024**3,
            'explicit finite reviewed focus bounds required')
    pins_path, pins = checked_json(config['preserved_inputs'], config['preserved_inputs_sha256'])
    require(pins['format'] == 'kdlock.kernel8.preserved-inputs.v1' and pins['core_git_head'] == CORE and
            pins['kernelrelease'] == RELEASE and pins['config_sha256'] == CONFIG_SHA and
            len(pins['normal_files']) == 8 and 'Makefile' in pins['normal_files'] and len(pins['body_files']) == 11 and
            len(pins['core_units']) == 33 and len(pins['native_units']) == 8 and len(pins['normal_module_names']) == 54,
            'exact preserved source/normal/config/33+8 contract differs')
    counts = {group['name']: len(group['files']) for group in pins['preserved_groups']}
    require(counts == {'normal_source': 8, 'kernel6_output': 16, 'kernel6_package': 77, 'kernel7_output': 16,
                       'kernel7_package': 77, 'kernel7_integration': 8, 'kernel7_mm_bodies': 11, 'kernel7_input': 77},
            'all preserved normal/kernel6/kernel7 pin groups required')
    manifest_path, manifest = checked_json(config['package_manifest'], config['package_manifest_sha256'])
    require(manifest['core_git_head'] == manifest['source_snapshot_git_head'] == CORE and
            manifest['intended_kernelrelease'] == RELEASE and manifest['installer_format'] == FORMAT and
            manifest['code_file_count'] == len(manifest['files']) == 78 and
            manifest['installer'] == 'kernel/integration/apply_target.py' and
            'include/kd_linux_rwsem_query.h' in manifest['files'], 'exact78 v3 kernel package required')
    archive = canonical(config['package_archive'])
    require(archive.stat().st_size == config['package_archive_bytes'] and sha(archive) == config['package_archive_sha256'],
            'package transport pin differs')
    tools = {}
    require(set(config['tools']) == {'python', 'make', 'cp'}, 'explicit tool identities required')
    for name, row in config['tools'].items():
        tool = Path(row['path'])
        resolved = canonical(row['resolved_path'])
        require(tool.is_absolute() and tool.resolve(strict=True) == resolved and sha(resolved) == row['sha256'],
                'actual tool alias/bytes differ: ' + name)
        tools[name] = str(tool)
    require(not BASE.exists() and BASE.parent.resolve(strict=True) == BASE.parent, 'fresh independent candidate namespace required')
    source, build = BASE / 'source', BASE / 'build'
    require(all(not BASE.is_relative_to(Path(group['root'])) and not Path(group['root']).is_relative_to(BASE)
                for group in pins['preserved_groups']), 'candidate overlaps preserved source/output')
    require(available('/') >= bounds['root_floor_bytes'] and available(BASE.parent) >= bounds['output_floor_bytes'],
            'root/data headroom below reviewed floors')
    out = BASE / 'receipts/focused-01'
    out.mkdir(parents=True, mode=0o700)
    record = {'status': 'PREPARED', 'core_git_head': CORE, 'source_snapshot_git_head': CORE, 'kernelrelease': RELEASE,
              'source': str(source), 'build': str(build), 'normal_source': pins['normal_source'],
              'normal_manifest_sha256': pins['normal_manifest_sha256'], 'preserved_inputs': str(pins_path),
              'preserved_inputs_sha256': config['preserved_inputs_sha256'], 'config': str(config_path),
              'config_sha256_input': args.config_sha, 'package_manifest': str(manifest_path),
              'package_manifest_sha256': config['package_manifest_sha256'], 'package_archive_sha256': config['package_archive_sha256'],
              'installer_format': FORMAT, 'recovery_policy': config['recovery_policy'], 'commands': [], 'scope': 'Fresh v3 integration and exact33+8 compilation only. No full kernel, module load, boot or runtime result.'}
    put('result.json', record)
    state = idle_sample(config['normal_identity'], pins['normal_module_names'])
    record['identity_before'] = state
    put('result.json', record)
    require(not state['busy'] and not state['dthreads'], 'strict preflight idle refused; actual sample retained')
    record['recovery'] = recovery(config['recovery'], config['recovery_sha256'], config['recovery_policy'])
    record['protected_before'], record['boot_before'] = protected(pins), boot_files()
    record['normal_before'] = hashes(Path(pins['normal_source']), pins['normal_files'])
    record['headroom_before'] = {'root': available('/'), 'output': available(BASE.parent)}
    inp = BASE / 'input/package'
    record['package_input'] = str(inp)
    record['package_before'] = unpack(archive, manifest['files'], inp)
    put('result.json', record)
    deadline = time.monotonic() + bounds['total_seconds']
    execute('copy-normal-source', [tools['cp'], '-a', '--reflink=auto', '--', pins['normal_source'], str(source)], deadline, bounds)
    hashes(source, pins['normal_files'])
    hashes(source, pins['body_files'])
    build.mkdir(mode=0o700)
    shutil.copyfile(canonical(pins['config_source']), build / '.config')
    require(sha(build / '.config') == CONFIG_SHA, 'independent config seed differs')
    package = source / 'kernel/kdlock'
    require(not package.exists(), 'fresh normal source unexpectedly contains package')
    package.mkdir()
    for name in manifest['files']:
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(inp / name, target)
    hashes(package, manifest['files'])
    installer = package / manifest['installer']
    common = ['--tree', str(source), '--build', str(build), '--package', str(package), '--source-identity',
              'Ubuntu linux=7.0.0-38.38 with protected kdlock1 source changes', '--package-identity', CORE]
    inspection = execute('integration-inspect', [tools['python'], '-B', str(installer), 'inspect'] + common, deadline, bounds)
    inspected = json.loads(inspection.read_text())
    require(inspected['source_files'] == pins['normal_files'] and
            inspected['package_files'] == {name: value for name, value in manifest['files'].items() if name != manifest['installer']} and
            inspected['config_sha256'] == CONFIG_SHA, 'inspection differs from external original8/package77/config pins')
    bound = []
    for name in ('source-fingerprint', 'config-sha256', 'package-fingerprint'):
        bound += ['--' + name, inspected[name.replace('-', '_')]]
    record['inspect_sha256'] = sha(inspection)
    record['inspect_receipt'] = str(inspection)
    execute('integration-plan', [tools['python'], '-B', str(installer), 'plan'] + common + bound, deadline, bounds)
    protections = []
    for root in sorted({group['root'] for group in pins['preserved_groups']} | {str(inp)}):
        protections += ['--protected-tree', root]
    application = BASE / 'receipts/integration-application'
    execute('integration-apply', [tools['python'], '-B', str(installer), 'apply'] + common + bound + protections +
            ['--idle-confirmed', '--receipt-dir', str(application)], deadline, bounds)
    # Verify is deliberately supplied the SAME three inspect-bound pins. No
    # continuation may guess or omit them after a committed application.
    execute('integration-verify', [tools['python'], '-B', str(installer), 'verify'] + common + bound +
            ['--receipt-dir', str(application)], deadline, bounds)
    applied = json.loads((application / 'manifest.json').read_text())
    require(applied['format'] == FORMAT and len(applied['after']) == 7 and 'Makefile' not in applied['after'],
            'exact v3 seven-file application required')
    integration = dict(applied['after'], Makefile=pins['normal_files']['Makefile'])
    record['application_manifest'] = str(application / 'manifest.json')
    record['application_manifest_sha256'] = sha(application / 'manifest.json')
    record['applied_after'] = hashes(source, applied['after'])
    record['integration_after'] = hashes(source, integration)
    hashes(source, pins['body_files'])
    make = [tools['make'], '-C', str(source), 'O=' + str(build), 'KERNELRELEASE=' + RELEASE]
    execute('olddefconfig', make + ['olddefconfig'], deadline, bounds)
    require(sha(build / '.config') == CONFIG_SHA, 'olddefconfig changed reviewed config31d')
    targets = ['kernel/kdlock/' + name for name in pins['core_units']] + pins['native_units']
    execute('focused-objects', make + ['-j8', 'V=1'] + targets, deadline, bounds)
    require((build / 'include/config/kernel.release').read_text().strip() == RELEASE, 'fresh output release differs')
    objects = {}
    for name in targets:
        path = build / name
        command = path.with_name('.' + path.name + '.cmd')
        for artifact in (path, command):
            artifact = canonical(artifact)
            objects[str(artifact.relative_to(build))] = {'bytes': artifact.stat().st_size, 'sha256': sha(artifact)}
    require(len(objects) == 82, 'all41 object and native command records required')
    record['compiled_objects'] = objects
    record['normal_after'] = hashes(Path(pins['normal_source']), pins['normal_files'])
    record['package_after'] = hashes(inp, manifest['files'])
    require(hashes(package, manifest['files']) == record['package_before'], 'compiled package source changed')
    record['body_after'] = hashes(source, pins['body_files'])
    record['applied_after'] = hashes(source, applied['after'])
    record['integration_after'] = hashes(source, integration)
    record['protected_after'], record['boot_after'] = protected(pins), boot_files()
    require(record['protected_after'] == record['protected_before'] and record['boot_after'] == record['boot_before'] and
            record['normal_before'] == record['normal_after'] and record['package_before'] == record['package_after'],
            'protected source/kernel6/kernel7/boot inputs changed')
    require(sha(config_path) == args.config_sha and sha(pins_path) == config['preserved_inputs_sha256'] and
            sha(manifest_path) == config['package_manifest_sha256'] and sha(archive) == config['package_archive_sha256'],
            'immutable input/recipe changed')
    record['config_sha256'] = sha(build / '.config')
    record['target_units'] = {'core': 33, 'native': 8}
    record['identity_after'] = final_idle(config['normal_identity'], pins['normal_module_names'])
    record['headroom_after'] = {'root': available('/'), 'output': available(BASE.parent)}
    record['status'] = 'FOCUSED_COMPILE_COMPLETE'
    put('result.json', record)
    print(json.dumps({'status': record['status'], 'receipt': str(out / 'result.json')}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if record is not None:
            if record.get('status') != 'INCOMPLETE_CHILD_RETAINED':
                record['status'] = 'FAILED_OR_INCOMPLETE'
            record['error'] = repr(error)
            put('result.json', record)
        raise
