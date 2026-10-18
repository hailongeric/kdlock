#!/usr/bin/env python3
"""Guest-only archive capture after health and live idle checks; no deletion.

Every top-level path under the completed base is archived exactly once. Archives
are written to a new sibling directory. Logs, command receipts, rejected runs,
source snapshots, private .inc files, modules and profile rows are retained.
Root coordinates execution; do not run while a benchmark or probe is active.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import stat
import tarfile
import time


DEFAULT_BASE = Path('/mnt/kdlock-builds/rwsem-opt-20261018')
PROBE = Path('/root/host_fs/kdlock/tests/kernel/rwsem/run.py')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            value.update(chunk)
    return value.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def inventory(base):
    rows = {}
    for directory, dirs, files in os.walk(base, followlinks=False):
        for name in sorted([*dirs, *files]):
            path = Path(directory) / name
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode),
                    'unsupported live/special evidence path: ' + str(path))
            rows[str(path.relative_to(base))] = dict(mode=info.st_mode, bytes=info.st_size,
                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns, inode=info.st_ino,
                device=info.st_dev, link=os.readlink(path) if path.is_symlink() else None)
    return rows


def group_for(path):
    name = path.name
    for suffix in ('.command.json', '.log'):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    if name.endswith('-screen'):
        return 'screens'
    if name.endswith('-profile'):
        return 'profiles'
    if name.endswith(('-probe', '-basic', '-functional', '-local', '-jit', '-checks')):
        return 'tests'
    if name.endswith('-grid'):
        return 'main'
    if name.endswith('-reference'):
        return 'reference'
    return 'metadata'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--health', type=Path, help='existing health.json inside the evidence base')
    parser.add_argument('--timeout-seconds', type=int, default=2400)
    args = parser.parse_args()
    base = args.base.resolve()
    out = args.output.resolve() if args.output else base.with_name(base.name + '-archives')
    health_path = args.health.resolve() if args.health else base / 'health.json'
    require(os.geteuid() == 0 and PROBE.is_file() and os.uname().release == '6.1.159-kdclobber2',
            'run only in the intended guest')
    require(base.is_dir() and out.parent == base.parent and out != base and not out.exists(),
            'use an existing evidence base and a new sibling archive directory')
    require(health_path.is_relative_to(base) and health_path.is_file(), 'retain health.json inside the base first')
    require(60 <= args.timeout_seconds <= 7200, 'archive timeout must be 60..7200 seconds')
    health = json.loads(health_path.read_text())
    require(health.get('idle') is True, 'health receipt does not confirm idle')
    require(not health.get('new_faults_in_retained_dmesg', []), 'health receipt contains new kernel faults')
    require(not health.get('per_session_kernel_faults', []), 'health receipt contains per-session kernel faults')
    if 'no_linux_mutex_imports' in health:
        require(health['no_linux_mutex_imports'] is True, 'health receipt reports native mutex imports')
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if 'boot_id' in health:
        require(health['boot_id'] == boot_id, 'health receipt belongs to another guest boot')
    for command in base.glob('*.command.json'):
        require(command.stat().st_mtime_ns <= health_path.stat().st_mtime_ns,
                'a runner command completed after the health receipt: ' + command.name)
    # Use only the checked-out guest idle predicate. Captured archive source is
    # never imported, and this helper does not load/unload anything.
    probe = runpy.run_path(str(PROBE), run_name='archive_idle_preflight')
    probe['idle']()
    before = inventory(base)
    require(before, 'empty evidence base')
    health_hash = sha256(health_path)
    groups = {name: [] for name in ('screens', 'profiles', 'tests', 'main', 'reference', 'metadata')}
    for path in sorted(base.iterdir()):
        groups[group_for(path)].append(path)
    out.mkdir()
    save(out / 'input-inventory.json', before)
    (out / 'archive-guest.py').write_bytes(Path(__file__).read_bytes())
    receipt = dict(schema=1, completed=False, guest_base=str(base), archive_prefix=base.name,
        boot_id=boot_id, health_path=str(health_path.relative_to(base)), health_sha256=health_hash,
        script_sha256=sha256(Path(__file__)), started_ns=time.time_ns(), groups=[],
        scope='Complete evidence preservation after idle/health checks; no benchmark or test execution')
    save(out / 'archives.json', receipt)

    def interrupted(signum, frame):
        raise TimeoutError('archive interrupted by signal ' + str(signum))

    old = {number: signal.signal(number, interrupted) for number in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM)}
    signal.alarm(args.timeout_seconds)
    try:
        for name, paths in groups.items():
            if not paths:
                continue
            probe['idle']()
            target = out / (name + '.tar.gz')
            print('ARCHIVE ' + name, flush=True)
            with tarfile.open(target, 'w:gz', compresslevel=6, dereference=False) as archive:
                for path in paths:
                    archive.add(path, arcname=str(Path(base.name) / path.name), recursive=True)
            row = dict(group=name, file=target.name, path=str(target), bytes=target.stat().st_size,
                       sha256=sha256(target), roots=[str(Path(base.name) / path.name) for path in paths])
            receipt['groups'].append(row)
            save(out / 'archives.json', receipt)
            print(json.dumps(row, sort_keys=True), flush=True)
        require(inventory(base) == before, 'evidence paths/metadata changed while archiving; retain partial capture')
        require(sha256(health_path) == health_hash, 'health receipt changed during archiving')
        probe['idle']()
        receipt.update(completed=True, guest_idle=True, finished_ns=time.time_ns(),
                       input_inventory_sha256=sha256(out / 'input-inventory.json'))
        save(out / 'archives.json', receipt)
    except BaseException as error:
        receipt.update(completed=False, error=repr(error), finished_ns=time.time_ns())
        save(out / 'archives.json', receipt)
        raise
    finally:
        signal.alarm(0)
        for number, handler in old.items():
            signal.signal(number, handler)
    print('Archived every top-level path; unchanged inputs and guest idle confirmed', flush=True)


if __name__ == '__main__':
    main()
