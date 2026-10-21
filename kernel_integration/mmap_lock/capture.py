#!/usr/bin/env python3
"""Capture a separately built kernel without replacing the recovery baseline."""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--parent', type=Path,
                   default=Path('/root/kdlock-kernel-baselines/mutex-clobber2-20260919'))
    a = p.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.uname().release == '6.1.159-kdclobber2', 'recovery guest required')
    rt.idle()
    prepared = json.loads((a.prepared / 'prepare.json').read_text())
    tree = Path(prepared['source_tree'])
    rt.require(prepared['passed'] and not a.output.exists(), 'new completed build capture required')
    rt.require(rt.digest(tree / '.config') == prepared['config_sha256'], 'configuration changed')
    source_files = dict(prepared['outputs'])
    parent = json.loads((a.parent / 'manifest.json').read_text())
    # Preserve every inherited source identity that the integration did not
    # explicitly replace. Capturing a new hash cannot excuse an ancestor drift.
    for name, digest in parent['source_files'].items():
        source_files.setdefault(name, digest)
    for name, digest in source_files.items():
        rt.require(rt.digest(tree / name) == digest, 'prepared/inherited input changed: ' + name)
    a.output.mkdir(parents=True)
    copied = {'guest.config': tree / '.config', 'prepare.json': a.prepared / 'prepare.json',
              'parent-manifest.json': a.parent / 'manifest.json',
              'guest-kernel.patch': Path(__file__).with_name('guest-kernel.patch'),
              'capture.py': Path(__file__)}
    rt.require(rt.digest(copied['guest-kernel.patch']) == prepared['patch_sha256'], 'patch changed')
    bundle_files = {}
    for name, source in copied.items():
        shutil.copyfile(source, a.output / name)
        bundle_files[name] = rt.digest(a.output / name)
    notes = rt.command(['readelf', '-n', tree / 'vmlinux'], a.output / 'notes.txt', timeout=60)
    ids = re.findall(r'Build ID: ([0-9a-f]+)', notes)
    rt.require(len(ids) == 1, 'exactly one kernel Build ID required')
    version_line = (tree / 'include/generated/utsversion.h').read_text().strip()
    rt.require(version_line.startswith('#define UTS_VERSION '), 'UTS version definition differs')
    version = ast.literal_eval(version_line[len('#define UTS_VERSION '):])
    release = (tree / 'include/config/kernel.release').read_text().strip()
    rt.require(release == prepared['release'], 'release differs')
    build_files = {name: rt.digest(tree / name) for name in (
        'Module.symvers', 'vmlinux.symvers', 'System.map', 'arch/x86/boot/bzImage', 'vmlinux',
        'include/config/auto.conf', 'include/config/kernel.release', 'include/generated/autoconf.h',
        'include/generated/compile.h', 'include/generated/utsrelease.h', 'include/generated/utsversion.h')}
    result = dict(schema=1, source_files=source_files, build_files=build_files,
                  bundle_files=bundle_files, upstream=parent['upstream'],
                  running=dict(release=release, version=version, machine='x86_64', build_id=ids[0]),
                  installed=False, booted=False, parent_manifest_sha256=rt.digest(a.parent / 'manifest.json'))
    rt.write_json(a.output / 'manifest.json', result)
    spec = importlib.util.spec_from_file_location('verify', ROOT / 'kernel_baseline/verify.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    checked = verifier.verify(a.output, tree, build=True)
    rt.write_json(a.output / 'capture.json', dict(passed=True, verification=checked,
                  manifest_sha256=rt.digest(a.output / 'manifest.json'), kernel=result['running']))
    print(json.dumps(dict(passed=True, verification=checked, kernel=result['running'])))


if __name__ == '__main__':
    main()
