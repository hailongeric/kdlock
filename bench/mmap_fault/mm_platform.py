"""Linux 7 identity and host gates for the private backing-lock MM suites.

These gates do not qualify a completed measurement: its immediate host endpoint
and the existing callback/data/drain oracles remain separate obligations.
"""
import datetime
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
RELEASE = '7.0.0-38-kdlock1'
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
PACKAGES = dict(miasm='0.1.5', future='1.0.0', pyparsing='2.4.7', pyelftools='0.27')
CANONICAL_ROOT = Path('/root/host_fs/kdlock')
PRIVATE_ROOTS = Path('/root/kdlock-inputs')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


host_capture = load_module('mm_host_capture', ROOT/'bench/basic/capture_host.py')


def arguments(parser):
    parser.add_argument('--boot-id', required=True, help='exact verified Linux 7 boot UUID')
    parser.add_argument('--host-reference', type=Path, required=True,
                        help='recorded Linux 7 fixed-frequency host reference')
    parser.add_argument('--host-reference-sha256', required=True)


def _regular_file(path, *, contents=False):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= 256 * 1024 * 1024,
            'regular bounded source file required: '+str(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    digest, total, data = hashlib.sha256(), 0, bytearray()
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            total += len(block)
            if contents:
                data.extend(block)
        after = os.fstat(stream.fileno())
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    require(stat.S_ISREG(opened.st_mode) and total == before.st_size and
            all(getattr(before, key) == getattr(opened, key) == getattr(after, key)
                for key in fields), 'source changed while reading: '+str(path))
    return digest.hexdigest(), total, bytes(data)


def _source_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate source receipt key')
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique)
    require(isinstance(value, dict), 'source receipt object required')
    return value


def _private_filesystem(root, mountinfo):
    covering = []
    for line in mountinfo.splitlines():
        fields = line.split()
        separator = fields.index('-')
        mount = Path(re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), fields[4]))
        require(mount != root and root not in mount.parents,
                'private source leaf or nested mount refused')
        if mount in root.parents:
            covering.append((len(mount.parts), mount, fields[separator + 1]))
    require(bool(covering), 'private source filesystem not observed')
    _, mount, filesystem = max(covering, key=lambda row: row[0])
    require(filesystem == 'ext4' and root.stat().st_dev == mount.stat().st_dev,
            'private source requires local ext4 storage')
    return filesystem


def source_identity(root=None, *, state_sha256=None, manifest_sha256=None):
    """Admit one externally bound committed copy without aliasing kernel inputs."""
    root = ROOT if root is None else Path(root)
    if root == CANONICAL_ROOT:
        return dict(root=str(root), route='canonical')
    require(root.parent == PRIVATE_ROOTS and
            bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', root.name)),
            'canonical source or one private source directory required')
    for component in reversed((root, *root.parents)):
        require(stat.S_ISDIR(component.lstat().st_mode),
                'private source directory component differs: '+str(component))
    require(root.resolve() == root, 'literal private source directory required')
    filesystem = _private_filesystem(root, Path('/proc/self/mountinfo').read_text())
    expected_state = state_sha256 or os.environ.get('KDLOCK_PRIVATE_SOURCE_STATE_SHA256', '')
    expected_manifest = manifest_sha256 or os.environ.get('KDLOCK_PRIVATE_SOURCE_MANIFEST_SHA256', '')
    require(all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                for value in (expected_state, expected_manifest)),
            'explicit frozen source receipt SHA256 values required')
    state_path, manifest_path = root/'source-state.json', root/'source-sha256.json'
    state_hash, _, state_data = _regular_file(state_path, contents=True)
    manifest_hash, _, manifest_data = _regular_file(manifest_path, contents=True)
    require(state_hash == expected_state and manifest_hash == expected_manifest,
            'frozen source receipt SHA256 differs')
    state, manifest = _source_json(state_data), _source_json(manifest_data)
    require(isinstance(state.get('git_head'), str) and
            bool(re.fullmatch(r'[0-9a-f]{40}', state['git_head'])) and
            state.get('git_status') == '' and state.get('omitted_missing_tracked_paths') == [],
            'clean committed source state required')
    require(type(state.get('files')) is int and state['files'] > 0 and
            type(state.get('transfer_bytes')) is int and state['transfer_bytes'] >= 0 and
            bool(manifest) and len(manifest) == state['files'],
            'source manifest file count differs')
    receipts = {'source-state.json', 'source-sha256.json'}
    for name, wanted in manifest.items():
        require(isinstance(name, str) and name not in receipts and '\0' not in name and
                not Path(name).is_absolute() and str(Path(name)) == name and
                '..' not in Path(name).parts and isinstance(wanted, str) and
                bool(re.fullmatch(r'[0-9a-f]{64}', wanted)), 'source manifest row differs')
    seen, total, pending = set(), 0, [root]
    device = root.stat().st_dev
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            entry = path.lstat()
            require(entry.st_dev == device, 'private source filesystem boundary differs')
            if stat.S_ISDIR(entry.st_mode):
                pending.append(path)
                continue
            require(stat.S_ISREG(entry.st_mode), 'private source entry is not a regular file')
            name = str(path.relative_to(root))
            if name in receipts:
                continue
            require(name in manifest, 'unlisted private source file: '+name)
            actual, size, _ = _regular_file(path)
            require(actual == manifest[name], 'private source file SHA256 differs: '+name)
            seen.add(name)
            total += size
    require(seen == set(manifest) and total == state['transfer_bytes'],
            'private source file set or byte count differs')
    require(_regular_file(state_path)[0] == state_hash and
            _regular_file(manifest_path)[0] == manifest_hash, 'source receipts changed while reading')
    return dict(root=str(root), route='private-frozen', git_head=state['git_head'],
                files=len(seen), transfer_bytes=total, filesystem=filesystem,
                source_state_sha256=state_hash, source_manifest_sha256=manifest_hash)


def guest(boot_id=None, *, release=RELEASE):
    actual = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(os.geteuid() == 0 and
            release in (RELEASE, '7.0.0-38-kdmm1', '7.0.0-38-kdscope1', '7.0.0-38-kdscope3',
                        '7.0.0-38-kdscope4', '7.0.0-38-kdscope5') and
            os.uname().release == release and
            (boot_id is None or actual == boot_id),
            'verified Linux 7 development guest and selected boot required')
    tag = os.environ.get('KDLOCK_SNAPSHOT_TAG', '')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', tag)),
            'explicit confirmed recovery snapshot required')
    require(sys.executable == PYTHON and shutil.which('python3') == PYTHON,
            'pinned Linux 7 translation Python required')
    source_identity()
    return actual


def dependency_identity():
    packages = {name: importlib.metadata.version(name) for name in PACKAGES}
    require(packages == PACKAGES, 'translation dependency versions differ')
    patch = load_module('mm_miasm_patch', ROOT/'disassem/miasm_python314.py').verify_runtime()
    return dict(packages=packages, python=sys.executable, semantic_builder=patch,
                source_provenance=source_identity())


def kernel_binding(identity, build, baseline, *, private_backing_locks=True):
    require(identity.get('ok') is True and identity.get('schema') == 2 and
            identity.get('runtime_policy_verified') is True and
            bool(identity.get('running_build_id')), 'verified live schema-2 identity required')
    config = (build/'.config').read_bytes()
    require(b'CONFIG_KDLOCK_MMAP=y' not in config.splitlines(),
            'private-backing suite requires native kernel mmap locking')
    require(b'# CONFIG_KDLOCK_MMAP is not set' in config.splitlines(),
            'explicit disabled MM adapter configuration required')
    return dict(release=RELEASE, build_id=identity['running_build_id'],
                configuration_sha256=hashlib.sha256(config).hexdigest(),
                manifest_sha256=hashlib.sha256((baseline/'manifest.json').read_bytes()).hexdigest(),
                runtime_policy=identity['runtime_policy'], kernel_mmap_backend='native',
                private_backing_locks=private_backing_locks)


def compare_host(reference, current, now, snapshot, strict):
    """Only pinned worker lifetimes may vary under explicit exploration."""
    for host in (reference, current):
        host_capture.validate(host)
        require(host['pins_verified'] and host['frequency_verified'], 'unverified host capture')
    stamp = datetime.datetime.fromisoformat(current['captured_utc'])
    require(datetime.datetime.fromisoformat(reference['captured_utc']) <= stamp and
            0 <= (now-stamp).total_seconds() <= 300, 'stale host capture')
    require(current['recovery_snapshot'] == snapshot, 'selected recovery snapshot differs')
    for key in ('host_boot_id', 'cpufreq', 'no_turbo', 'numa', 'monitor_path', 'recovery_snapshot'):
        require(reference[key] == current[key], 'host reference differs: '+key)
    old, new = reference['qemu'][0], current['qemu'][0]
    require(all(old[key] == new[key] for key in ('pid', 'start_ticks', 'args')),
            'QEMU process/configuration differs')
    require(host_capture.memory_bindings(old) == host_capture.memory_bindings(new),
            'host memory bindings differ')
    before = {row['tid']: row for row in old['tasks']}
    after = {row['tid']: row for row in new['tasks']}
    permanent = lambda tasks:{tid:row for tid,row in tasks.items() if row['comm'] != 'worker'}
    require(permanent(before) == permanent(after),
            'permanent QEMU task identity/placement differs')
    extra = [row for tid,row in after.items() if before.get(tid) != row]
    retired = [row for tid,row in before.items() if after.get(tid) != row]
    require(all(row['comm'] == 'worker' and row['affinity'] == [63] for row in extra+retired),
            'only pinned worker lifetimes may differ')
    require(not strict or before == after, 'strict QEMU task set differs')
    return dict(strict_host_gate='PASS' if strict else 'FAILED',
                exploratory=not strict, task_set_unchanged=before == after,
                additional_workers=extra, retired_workers=retired,
                original_threads=len(before), observed_threads=len(after),
                fixed_frequency_khz=2000000, performance_accepted=False,
                host_endpoint='PENDING')


def host_reference(path, expected):
    require(bool(re.fullmatch('[0-9a-f]{64}', expected or '')),
            'explicit host-reference SHA256 required')
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected, 'host reference SHA256 differs')
    return data, json.loads(data)
