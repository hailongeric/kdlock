#!/usr/bin/env python3
"""Capture current mmap/fault source for offline review in an idle guest.

This performs identity checks and copies text. It does not build, load a module,
run a workload, modify the kernel, or change an admission/ownership contract.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time
from types import SimpleNamespace


ROOT = Path('/root/host_fs/kdlock')
HISTORICAL = ROOT/'bench/results/10.176.26.71/tests/proc-mmap-audit-20261015/audit.json'
ADDITIONAL = (
    'mm/filemap.c', 'mm/userfaultfd.c', 'fs/userfaultfd.c', 'mm/shmem.c',
    'mm/huge_memory.c', 'mm/hugetlb.c', 'mm/internal.h',
    'fs/ext4/file.c', 'fs/ext4/inode.c', 'fs/buffer.c', 'fs/iomap/buffered-io.c',
    'include/linux/pagemap.h', 'include/linux/userfaultfd_k.h', 'include/linux/mm.h',
    'include/linux/fs.h', 'include/linux/maple_tree.h', 'include/linux/rwsem.h',
    'include/linux/huge_mm.h', 'include/linux/hugetlb.h',
    'lib/maple_tree.c', 'kernel/locking/rwsem.c',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-manifest', type=Path, required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert Path.cwd() == ROOT
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    import kernel_identity
    out = args.output.resolve()
    assert not out.exists() and not out.is_relative_to(ROOT)
    archiver = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    archiver['idle'](out, rt.idle)
    manifest = json.loads(args.source_manifest.read_text())
    for path, digest in manifest['files'].items():
        assert sha(ROOT/path) == digest, path
    out.mkdir(parents=True)
    shutil.copyfile(Path(__file__), out/'capture.py')
    shutil.copyfile(args.source_manifest, out/'committed-source.json')
    shutil.copyfile(HISTORICAL, out/'historical-audit.json')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    result = dict(passed=False, source_commit=manifest['commit'], boot_id=boot,
                  capture_script_sha256=sha(Path(__file__)), started_unix=time.time(),
                  scope='Read-only kernel identity and source capture; no KD mmap execution.',
                  kernel_modified=False, builds=0, tests=0, measured_sessions=0)
    try:
        options = SimpleNamespace(
            kernel_source=Path('/root/linux-6.1.159-kdclobber2'),
            kernel_baseline=Path('/root/kdlock-kernel-baselines/mutex-clobber2-20260919'))
        identity = kernel_identity.capture(options, out, rt.command)
        assert identity['ok'] and identity['running_build_id'] == \
            '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
        rt.write_json(out/'kernel-identity.json', identity)
        historical = json.loads(HISTORICAL.read_text())['kernel_source_sha256']
        paths = sorted(set(historical) | set(ADDITIONAL))
        frozen = {}
        for relative in paths:
            source = options.kernel_source/relative
            assert source.is_file(), relative
            digest = sha(source)
            if relative in historical:
                assert historical[relative] == digest, relative
            target = out/'kernel'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            assert sha(target) == digest, relative
            frozen[relative] = digest
        rt.write_json(out/'kernel-source-sha256.json', frozen)
        for relative, digest in frozen.items():
            assert sha(options.kernel_source/relative) == digest, relative
        for path, digest in manifest['files'].items():
            assert sha(ROOT/path) == digest, path
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
        archiver['idle'](out, rt.idle)
        result.update(passed=True, idle=True, kernel_identity=identity,
                      historical_source_files=len(historical), captured_source_files=len(frozen),
                      additional_source_files=len(set(frozen)-set(historical)),
                      kernel_source_manifest_sha256=sha(out/'kernel-source-sha256.json'),
                      source_unchanged=True, completed_unix=time.time())
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out/'result.json', result)
    # This receipt only establishes idle capture, not lock correctness.
    rt.write_json(out/'health.json', dict(
        idle=True, boot_id=boot, checked_unix=time.time(),
        per_session_kernel_faults=[], scope=result['scope'],
        result_sha256=sha(out/'result.json'), capture_script_sha256=sha(Path(__file__))))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
