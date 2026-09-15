#!/usr/bin/env python3
"""Capture a separately built spin-static kernel; never alter the old bundle.

Run in the recovery guest after build/install and before boot. The expected
running identity comes from this vmlinux and its generated headers, then the
ordinary verifier must match that identity after the experimental boot.
"""
import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as data:
        for chunk in iter(lambda: data.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    original = ROOT / 'kernel_baseline'
    if (ROOT != Path('/root/host_fs/kdlock') or source == Path('/root/linux-6.1.159') or
            out.exists() or out.is_relative_to(ROOT)):
        raise RuntimeError('requires a distinct guest experiment source and new external bundle')
    parent = json.loads((original / 'manifest.json').read_text())
    release = (source / 'include/config/kernel.release').read_text().strip()
    if not release.startswith('6.1.159-kdstatic'):
        raise RuntimeError('experimental release suffix missing')
    version_header = (source / 'include/generated/utsversion.h').read_text()
    version = ast.literal_eval(re.search(r'^#define UTS_VERSION (".*")$', version_header, re.M)[1])
    notes = subprocess.check_output(['readelf', '-n', str(source / 'vmlinux')], text=True)
    build_id, = re.findall(r'Build ID: ([a-f0-9]+)', notes)
    out.mkdir(parents=True)
    shutil.copyfile(source / '.config', out / 'guest.config')
    shutil.copyfile(original / 'linux-6.1.159-guest.patch', out / 'linux-6.1.159-guest.patch')
    shutil.copyfile(HERE / 'guest-kernel.patch', out / 'spin-static.patch')
    named_sources = list(parent['source_files']) + ['include/linux/kd_spin_hooks.h']
    manifest = dict(schema=1, captured_at=datetime.now(timezone.utc).isoformat(),
        experiment='spin_static', parent_manifest_sha256=sha(original / 'manifest.json'),
        upstream=parent['upstream'],
        bundle_files={p.name: sha(p) for p in sorted(out.iterdir())},
        source_files={p: sha(source / p) for p in named_sources},
        build_files={p: sha(source / p) for p in parent['build_files']},
        running=dict(release=release, version=version, machine='x86_64', build_id=build_id),
        installed_files={str(p): sha(p) for p in (
            Path('/boot') / (prefix + release) for prefix in ('vmlinuz-', 'config-', 'initrd.img-'))
                         if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(bundle=str(out), expected_running=manifest['running'],
                          source_files=len(named_sources)), indent=2))


if __name__ == '__main__':
    main()
