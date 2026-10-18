#!/usr/bin/env python3
"""Capture kdclobber1 against a verified static2 parent; preserve both bundles."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    with path.open('rb') as source:
        digest = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, parent, out = args.source.resolve(), args.parent.resolve(), args.output.resolve()
    if ROOT != Path('/root/host_fs/kdlock') or source != Path('/root/linux-6.1.159-kdclobber1') or out.exists() or out.is_relative_to(ROOT):
        raise RuntimeError('requires the independent kdclobber1 tree and a new external bundle')
    previous = json.loads((parent/'manifest.json').read_text())
    if previous['running']['release'] != '6.1.159-kdstatic2':
        raise RuntimeError('expected the preserved kdstatic2 parent')
    release = (source/'include/config/kernel.release').read_text().strip()
    if release != '6.1.159-kdclobber1':
        raise RuntimeError('unexpected release')
    version = ast.literal_eval(re.search(r'^#define UTS_VERSION (".*")$', (source/'include/generated/utsversion.h').read_text(), re.M)[1])
    build_id, = re.findall(r'Build ID: ([a-f0-9]+)', subprocess.check_output(['readelf','-n',str(source/'vmlinux')],text=True))
    old_config = (parent/'guest.config').read_text().splitlines()
    config = (source/'.config').read_text().splitlines()
    # The only permitted configuration difference is the independent release.
    keep = lambda lines: [s for s in lines if s and not s.startswith(('#', 'CONFIG_LOCALVERSION='))]
    if keep(config) != keep(old_config):
        raise RuntimeError('kernel configuration changed beyond LOCALVERSION')
    out.mkdir(parents=True)
    shutil.copyfile(source/'.config',out/'guest.config')
    shutil.copyfile(parent/'manifest.json',out/'parent-manifest.json')
    for name, expected in previous['bundle_files'].items():
        if sha(parent/name) != expected:
            raise RuntimeError(f'parent bundle changed: {name}')
        if name != 'guest.config':
            shutil.copyfile(parent/name,out/name)
    shutil.copyfile(HERE/'guest-kernel.patch',out/'spin-clobber.patch')
    named = sorted(set(previous['source_files']) | {'include/linux/spinlock.h','include/linux/kd_spin_hooks.h','kernel/locking/spinlock.c'})
    manifest = dict(schema=1,experiment='spin_clobber_v1',captured_at=datetime.now(timezone.utc).isoformat(),
        parent_manifest_sha256=sha(parent/'manifest.json'),upstream=previous['upstream'],
        bundle_files={p.name:sha(p) for p in out.iterdir()},source_files={name:sha(source/name) for name in named},
        build_files={name:sha(source/name) for name in previous['build_files']},
        running=dict(release=release,version=version,machine='x86_64',build_id=build_id),
        installed_files={str(p):sha(p) for p in (Path('/boot')/(prefix+release) for prefix in ('vmlinuz-','config-','initrd.img-')) if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps(manifest['running']))


if __name__=='__main__':
    main()
