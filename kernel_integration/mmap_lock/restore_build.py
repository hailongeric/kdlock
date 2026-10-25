#!/usr/bin/env python3
"""Restore the retained kdmm31 build privately; never compile or install a kernel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tarfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt

BASE = Path('/root/kdlock-kernel-work/mmap-20261021/candidate-1/linux')
CANDIDATE = Path('/root/kdlock-kernel-work/mmap-irq-20261025/candidate-1')
INVENTORY_SHA = '9687419fcbc6165a929c6652e65321abab3a93a87e72386c329df64c72fb7aca'
DELTA_SHA = 'cde7ad43033ea25812ec608482200e754b56ccb271a88b48665c89918630cf16'
POST_SHA = '0d5bbb6d8ed27ef5b521efb02ab0e70de7aa60d2abe40f95f3458d3e686a5b4a'
ORDER_SHA = 'd5b2d3095ecbb958ca410deb0ae1e020f19d935b26fc1603e44a2d69fc9b630d'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def verify_tree(root, records):
    """Check every name, type, mode, regular-file byte and symlink target.

    Mtime/ownership/xattrs remain preserved inputs, not reconstruction acceptance
    predicates. Moving the two obsolete dependencies changes directory mtimes.
    """
    seen = set()
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(parent) / name
            rel = str(path.relative_to(root))
            seen.add(rel)
            row = records.get(rel)
            rt.require(row is not None, 'unexpected reconstructed entry: ' + rel)
            info = path.lstat()
            rt.require(info.st_mode == row['mode'], 'mode/type differs: ' + rel)
            if stat.S_ISREG(info.st_mode):
                rt.require(info.st_size == row['size'] and digest(path) == row['sha256'],
                           'file differs: ' + rel)
            elif stat.S_ISLNK(info.st_mode):
                rt.require(os.readlink(path) == row['link'], 'link differs: ' + rel)
            else:
                rt.require(stat.S_ISDIR(info.st_mode), 'unsupported entry: ' + rel)
    rt.require(seen == set(records), 'tree inventory differs')
    return len(seen)


def archive_names(path, expected):
    with tarfile.open(path) as archive:
        names = []
        for member in archive:
            name = Path(member.name)
            rt.require(not name.is_absolute() and '..' not in name.parts,
                       'unsafe archive path')
            names.append(member.name)
    rt.require(len(names) == len(set(names)) and set(names) == set(expected),
               'archive inventory differs')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--delta', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rt.require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
               and str(ROOT) == '/root/host_fs/kdlock', 'idle recovery guest required')
    rt.idle()
    # Reuse the comprehensive project process/module/open-writer inspection.
    import runpy
    runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
    out = a.output.resolve()
    rt.require(not out.exists() and out.is_relative_to(Path('/dev/shm')),
               'new private tmpfs output required')
    inventory = CANDIDATE / 'new-volatile.json'
    post = CANDIDATE / 'resume-20261025/post-install-tree-changes.tar.gz'
    rt.require(digest(inventory) == INVENTORY_SHA and digest(a.delta) == DELTA_SHA
               and digest(post) == POST_SHA, 'preserved reconstruction input differs')
    records = json.loads(inventory.read_text())
    rt.require(records['passed'] and records['base_root'] == str(BASE), 'base differs')
    needed = sum(row.get('size', 0) for row in records['files'].values()) + 512 * 1024**2
    rt.require(shutil.disk_usage(out.parent).free > needed, 'insufficient temporary space')
    out.mkdir()
    result = dict(passed=False, kernel_built=False, installed=False, booted=False,
                  base=str(BASE), tree=str(out / 'linux'), inventory_sha256=INVENTORY_SHA,
                  delta_sha256=DELTA_SHA, post_install_sha256=POST_SHA,
                  verification='All names/types/modes, regular bytes and symlink targets')
    try:
        print('VERIFY_BASE', flush=True)
        result['base_entries'] = verify_tree(BASE, records['base_files'])
        archive_names(a.delta, records['selected'])
        archive_names(post, ['modules.order'])
        print('COPY_AND_RESTORE', flush=True)
        tree = out / 'linux'
        rt.command(['cp', '-a', '--reflink=never', BASE, tree], out / 'copy.log', timeout=300)
        for name in records['removed']:
            target = out / 'displaced' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(tree / name, target)
        rt.command(['tar', '--acls', '--xattrs', '-xzf', a.delta, '-C', tree],
                   out / 'delta.log', timeout=300)
        print('VERIFY_CANDIDATE', flush=True)
        result['candidate_entries'] = verify_tree(tree, records['files'])
        rt.command(['tar', '--acls', '--xattrs', '-xzf', post, '-C', tree],
                   out / 'post-install.log', timeout=30)
        rt.require(digest(tree / 'modules.order') == ORDER_SHA, 'post-install index differs')
        verify = runpy.run_path(str(ROOT / 'kernel_baseline/verify.py'))['verify']
        result['identity'] = verify(
            Path('/root/kdlock-kernel-baselines/mmap-kdmm31-irq-20261025'),
            tree, build=True)
        rt.write_json(out / 'identity.json', result['identity'])
        result.update(passed=True, modules_order_sha256=ORDER_SHA,
                      remaining_tmp_bytes=shutil.disk_usage(tree).free)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out / 'result.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
