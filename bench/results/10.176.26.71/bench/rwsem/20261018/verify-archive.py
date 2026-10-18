#!/usr/bin/env python3
"""Read-only hash verification of captured guest archives, without executing them."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('archive', type=Path)
p.add_argument('receipt', type=Path)
p.add_argument('--extract-grid', type=Path)
a = p.parse_args()
hashes, manifests, links, selected = {}, {}, {}, {}
archive_hash = hashlib.sha256()
with a.archive.open('rb') as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        archive_hash.update(chunk)
allowed = {'plan.json', 'records.json', 'summary.json', 'parity.json',
           'source-sha256.json', 'binary-sha256.json', 'environment.json'}
with tarfile.open(a.archive, 'r|gz') as archive:
    for member in archive:
        path = PurePosixPath(member.name)
        assert not path.is_absolute() and '..' not in path.parts, member.name
        name = str(path)
        if member.isdir():
            continue
        assert name not in hashes and name not in links, name
        if member.issym() or member.islnk():
            links[name] = dict(target=member.linkname, hard=member.islnk())
            continue
        assert member.isfile(), name
        is_manifest = path.name in ('source-sha256.json', 'source-manifest.json', 'binary-sha256.json')
        export = len(path.parts) == 2 and path.parts[0] == 'rwsem-delegation-grid-20261018' and path.name in allowed
        digest, saved = hashlib.sha256(), bytearray()
        stream = archive.extractfile(member)
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
            if is_manifest or export:
                saved.extend(chunk)
        hashes[name] = digest.hexdigest()
        if is_manifest:
            manifests[name] = json.loads(saved)
        if export:
            selected[path.name] = bytes(saved)

checks, source_instances, binary_instances = [], 0, 0
for name, manifest in manifests.items():
    assert isinstance(manifest, dict) and manifest, name
    parent = PurePosixPath(name).parent
    binary = PurePosixPath(name).name == 'binary-sha256.json'
    for relative, expected in manifest.items():
        assert isinstance(expected, str) and len(expected) == 64, (name, relative)
        if binary:
            prefix = '/mnt/kdlock-builds/'
            assert relative.startswith(prefix), (name, relative)
            target = relative[len(prefix):]
            binary_instances += 1
        else:
            assert not PurePosixPath(relative).is_absolute() and '..' not in PurePosixPath(relative).parts
            target = str(parent / 'source' / relative)
            source_instances += 1
        assert hashes.get(target) == expected, (name, target, hashes.get(target), expected)
    checks.append(dict(path=name, files=len(manifest), kind='binary' if binary else 'source'))

if a.extract_grid:
    assert selected.keys() == allowed, sorted(selected)
    a.extract_grid.mkdir(parents=True, exist_ok=False)
    for name, data in selected.items():
        (a.extract_grid / name).write_bytes(data)

receipt = dict(path=str(a.archive), sha256=archive_hash.hexdigest(),
    bytes=a.archive.stat().st_size, regular_files=len(hashes), links=len(links),
    manifests_verified=checks, source_file_instances_verified=source_instances,
    binary_file_instances_verified=binary_instances,
    scope='Read-only offline archive hashes and frozen source/binary manifests; no source-host tests')
a.receipt.parent.mkdir(parents=True, exist_ok=True)
assert not a.receipt.exists()
a.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
