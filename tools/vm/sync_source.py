#!/usr/bin/env python3
"""Copy approved changed source files to an idle ext4 recovery guest.

Run on the physical benchmark host beside vm_ssh.sh. The JSON manifest is a
relative-path-to-SHA256 mapping; review and refresh it when host inputs change.
Neither an SSH connection nor a dry run writes guest project files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile


GUEST_ROOT = '/root/host_fs/kdlock'

# This program is sent as an SSH command; stdin carries JSON, then an optional
# tar stream. It uses only guest Python's standard library.
REMOTE_CODE = r'''
import errno, fcntl, hashlib, json, os, pathlib, re, stat, sys, tarfile, uuid

ROOT = pathlib.Path('/root/host_fs/kdlock')
MODULES = {'kdlock_km', 'spin_cacheline', 'mutex_cacheline', 'klock_module',
           'kd_depth_source', 'kd_dispatch_floor', 'rwlock_bench', 'rwlock_test',
           'tclock_backend_km', 'tclock_mutex_backend_km',
           'tclock_rwlock_backend_km', 'tc_allocator_guard'}
TASKS = {'sc_worker', 'rb_worker', 'klock_test', 'kd_test', 'daemon'}

def validate_manifest(mapping):
    if not isinstance(mapping, dict) or not mapping:
        raise RuntimeError('A nonempty source manifest is required')
    for relative, digest in mapping.items():
        if not isinstance(relative, str) or not relative or any(ord(c) < 32 for c in relative):
            raise RuntimeError('Invalid source path')
        path = pathlib.PurePosixPath(relative)
        if path.is_absolute() or str(path) != relative or '..' in path.parts:
            raise RuntimeError('Unsafe source path: ' + relative)
        if ((path.parts[:2] == ('bench', 'results') and 'raw' in path.parts[2:]) or
                (path.parts[0] == 'results' and 'raw' in path.parts[1:])):
            raise RuntimeError('Raw evidence is outside source synchronization: ' + relative)
        if any(p.startswith('.') for p in path.parts) and relative not in ('.gitattributes', '.gitignore'):
            raise RuntimeError('Private or Git metadata path forbidden: ' + relative)
        if '__pycache__' in path.parts or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise RuntimeError('Invalid source manifest entry: ' + relative)

def ensure_idle():
    for module in pathlib.Path('/sys/module').iterdir():
        if module.name in MODULES or module.name.startswith(('kd_', 'tclock_', 'tc_')):
            raise RuntimeError('Guest project module is still loaded: ' + module.name)
    for comm in pathlib.Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            name = comm.read_text().strip()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if name in TASKS:
            raise RuntimeError('Guest project task is still active: ' + str(comm) + ': ' + name)
    for cmdline in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = [a.decode(errors='replace') for a in cmdline.read_bytes().split(b'\0') if a]
        except (FileNotFoundError, ProcessLookupError):
            continue
        for arg in args:
            # Match actual file arguments, not Python -c program text.
            if '\n' in arg or len(arg) > 4096:
                continue
            if (arg.startswith(('bench/', str(ROOT) + '/bench/')) and
                    pathlib.PurePosixPath(arg).name in
                    {'run.py', 'run_mutex.py', 'owned_origin.py', 'client.py', 'bench_session.py', 'client'}):
                raise RuntimeError('Guest benchmark process is active: ' + str(cmdline))

def ensure_root():
    if os.geteuid() != 0:
        raise RuntimeError('Guest root execution is required')
    path = pathlib.Path('/')
    for part in ROOT.parts[1:]:
        path /= part
        mode = path.lstat().st_mode
        if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            raise RuntimeError('Guest source root or ancestor is not a real directory: ' + str(path))
    mounts = []
    def unescape(value):
        return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), value)
    for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ', 1)
        mountpoint = unescape(left.split()[4])
        if str(ROOT) == mountpoint or str(ROOT).startswith(mountpoint.rstrip('/') + '/'):
            mounts.append((len(mountpoint), right.split()[0]))
    if not mounts or max(mounts)[1] != 'ext4':
        raise RuntimeError('Guest source must reside on ext4')

def parent_fd(relative, create=False):
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = pathlib.PurePosixPath(relative).parts
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise

def sha256(relative):
    try:
        fd, name = parent_fd(relative)
    except FileNotFoundError:
        return None
    try:
        try:
            source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            return None
        with os.fdopen(source, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RuntimeError('Guest destination is not a regular file: ' + relative)
            return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hash_stream(stream)
    finally:
        os.close(fd)

def hash_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest()

def inspect(manifest):
    ensure_root()
    ensure_idle()
    return {'root': str(ROOT), 'fstype': 'ext4', 'idle': True,
            'hashes': {relative: sha256(relative) for relative in manifest}}

def copy(request):
    manifest = request['manifest']
    changed = request['changed']
    previous = request['previous']
    if not isinstance(changed, list) or not changed or len(changed) != len(set(changed)) or not set(changed) <= set(manifest):
        raise RuntimeError('Invalid changed-file selection')
    if not isinstance(previous, dict) or set(previous) != set(changed):
        raise RuntimeError('Previous hashes must cover exactly the changed files')
    ensure_root()
    ensure_idle()
    # Only this helper uses the temporary lock; keep source trees untouched.
    lock = os.open('/tmp/kdlock-source-sync.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    staged = []
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ensure_idle()
        for relative in changed:
            if sha256(relative) != previous[relative]:
                raise RuntimeError('Guest source changed after comparison: ' + relative)
        seen = set()
        with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as archive:
            for member in archive:
                relative = member.name
                if relative not in changed or relative in seen or not member.isreg():
                    raise RuntimeError('Archive must contain exactly the selected regular files')
                if member.size < 0 or member.size > 256 * 1024 * 1024:
                    raise RuntimeError('Source file exceeds the 256 MiB safety limit: ' + relative)
                seen.add(relative)
                ensure_idle()
                fd, name = parent_fd(relative, create=True)
                temporary = '.kdlock-sync-' + uuid.uuid4().hex
                staged.append((fd, temporary, name, relative))
                output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=fd)
                incoming = archive.extractfile(member)
                digest = hashlib.sha256()
                copied = 0
                with incoming, os.fdopen(output, 'wb') as stream:
                    for block in iter(lambda: incoming.read(1024 * 1024), b''):
                        stream.write(block)
                        digest.update(block)
                        copied += len(block)
                    stream.flush()
                    os.fchmod(stream.fileno(), member.mode & 0o777)
                    os.fsync(stream.fileno())
                if copied != member.size or digest.hexdigest() != manifest[relative]:
                    raise RuntimeError('Incoming source bytes do not match the approved hash: ' + relative)
        if seen != set(changed):
            raise RuntimeError('Archive omitted selected source files')
        for fd, temporary, name, relative in staged:
            ensure_idle()
            if sha256(relative) != previous[relative]:
                raise RuntimeError('Guest source changed before replacement: ' + relative)
            # Refuse a symlink/non-file even if it appeared after the hash check.
            try:
                mode = os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
                if not stat.S_ISREG(mode):
                    raise RuntimeError('Unsafe destination before replacement: ' + relative)
            except FileNotFoundError:
                pass
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        result = inspect(manifest)
        if result['hashes'] != manifest:
            raise RuntimeError('Final source hashes do not match the complete approved manifest')
        result['copied'] = len(changed)
        return result
    finally:
        for fd, temporary, name, relative in staged:
            try:
                os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError:
                pass
            os.close(fd)
        os.close(lock)

request = json.loads(sys.stdin.buffer.readline())
validate_manifest(request['manifest'])
if request['operation'] == 'inspect':
    result = inspect(request['manifest'])
elif request['operation'] == 'copy':
    result = copy(request)
else:
    raise RuntimeError('Unknown source synchronization operation')
print(json.dumps(result, sort_keys=True))
'''


def validate_manifest(mapping):
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError('Manifest must be a nonempty relative-path-to-SHA256 mapping')
    for relative, digest in mapping.items():
        if not isinstance(relative, str) or not relative or any(ord(c) < 32 for c in relative):
            raise ValueError('Invalid source path')
        path = PurePosixPath(relative)
        if path.is_absolute() or str(path) != relative or '..' in path.parts:
            raise ValueError('Unsafe source path: ' + relative)
        if ((path.parts[:2] == ('bench', 'results') and 'raw' in path.parts[2:]) or
                (path.parts[0] == 'results' and 'raw' in path.parts[1:])):
            raise ValueError('Raw evidence is outside source synchronization: ' + relative)
        if any(part.startswith('.') for part in path.parts) and relative not in ('.gitattributes', '.gitignore'):
            raise ValueError('Private or Git metadata path forbidden: ' + relative)
        if '__pycache__' in path.parts or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid manifest entry: ' + relative)


def checked_host_file(root, relative):
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError('Host source path contains a symlink: ' + relative)
    if not stat.S_ISREG(mode):
        raise ValueError('Host source is not a regular file: ' + relative)
    return current


def host_hashes(root, manifest):
    actual = {}
    for relative in manifest:
        path = checked_host_file(root, relative)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        actual[relative] = digest.hexdigest()
    mismatches = [relative for relative in manifest if actual[relative] != manifest[relative]]
    if mismatches:
        raise ValueError('Host files differ from the approved manifest; review and refresh it: ' + ', '.join(mismatches))
    return actual


def remote(ssh, request, timeout, archive=None):
    command = 'PYTHONDONTWRITEBYTECODE=1 python3 -c ' + shlex.quote(REMOTE_CODE)
    header = (json.dumps(request, sort_keys=True) + '\n').encode()
    if archive is None:
        result = subprocess.run([str(ssh), command], input=header, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    else:
        # Keep large source payloads out of SSH arguments and memory.
        with tempfile.TemporaryFile() as payload:
            payload.write(header)
            archive.seek(0)
            for block in iter(lambda: archive.read(1024 * 1024), b''):
                payload.write(block)
            payload.seek(0)
            result = subprocess.run([str(ssh), command], stdin=payload, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.stderr:
        sys.stderr.write(result.stderr.decode(errors='replace'))
    if result.returncode:
        raise RuntimeError(f'Guest synchronization command exited {result.returncode}; inspect any partial progress before running benchmarks')
    response = json.loads(result.stdout)
    if response.get('root') != GUEST_ROOT or response.get('fstype') != 'ext4' or response.get('idle') is not True:
        raise RuntimeError('Guest did not confirm the required root, filesystem and idle state')
    if set(response.get('hashes', {})) != set(request['manifest']):
        raise RuntimeError('Guest response omitted or added source paths')
    return response


def main():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=script_dir.parent / 'vm-shared/kdlock')
    parser.add_argument('--manifest', type=Path, default=script_dir / 'source-sha256.json')
    parser.add_argument('--ssh', type=Path, default=script_dir / 'vm_ssh.sh')
    parser.add_argument('--timeout', type=int, default=600, help='outer timeout for each SSH operation')
    parser.add_argument('--dry-run', action='store_true', help='compare host and guest without writing project files')
    args = parser.parse_args()
    if args.timeout <= 0:
        raise ValueError('Timeout must be positive')
    manifest = json.loads(args.manifest.read_text())
    validate_manifest(manifest)
    source = args.source.resolve(strict=True)
    ssh = args.ssh.resolve(strict=True)
    if not os.access(ssh, os.X_OK):
        raise ValueError('Companion SSH helper is not executable')
    host_hashes(source, manifest)
    before = remote(ssh, {'operation': 'inspect', 'manifest': manifest}, args.timeout)
    changed = sorted(relative for relative in manifest if before['hashes'][relative] != manifest[relative])
    print(json.dumps({'approved_files': len(manifest), 'changed_files': len(changed),
                      'dry_run': args.dry_run, 'changed': changed}, sort_keys=True), flush=True)
    if args.dry_run:
        return 0
    if not changed:
        print(f'All {len(manifest)} approved guest files already match; no writes performed.')
        return 0
    with tempfile.TemporaryFile() as archive:
        with tarfile.open(fileobj=archive, mode='w', format=tarfile.PAX_FORMAT) as tar:
            for relative in changed:
                path = checked_host_file(source, relative)
                with path.open('rb') as stream:
                    mode = os.fstat(stream.fileno()).st_mode
                    if not stat.S_ISREG(mode):
                        raise ValueError('Host source changed type: ' + relative)
                    info = tarfile.TarInfo(relative)
                    info.size = os.fstat(stream.fileno()).st_size
                    info.mode = mode & 0o777
                    tar.addfile(info, stream)
        # Detect edits while creating the archive; guest also hashes incoming bytes.
        host_hashes(source, manifest)
        after = remote(ssh, {'operation': 'copy', 'manifest': manifest,
                            'changed': changed,
                            'previous': {p: before['hashes'][p] for p in changed}},
                       args.timeout, archive)
    if after['hashes'] != manifest or after.get('copied') != len(changed):
        raise RuntimeError('Guest final verification failed')
    print(f'Copied {len(changed)} changed files; verified all {len(manifest)} approved hashes. No project files deleted.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'STOP: {error}', file=sys.stderr)
        raise SystemExit(1)
