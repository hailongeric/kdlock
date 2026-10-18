#!/usr/bin/env python3
"""Host-only, streaming archive verification without executing captured source.

Usage: verify-archive.py ARCHIVE RECEIPT --archives-json archives.json
       [--extract-receipts NEW_DIRECTORY]
Without archives.json, supply --guest-base and --archive-prefix explicitly.
Only seven runner JSON receipts and selected profile JSON receipts are exported.
No tar extraction primitive, links, binaries or source files are executed/exported.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


RUN_RECEIPTS = {'plan.json', 'records.json', 'summary.json', 'parity.json',
                'source-sha256.json', 'binary-sha256.json', 'environment.json'}
MANIFESTS = {'source-sha256.json', 'source-manifest.json', 'binary-sha256.json'}
PROFILE_RECEIPTS = {'function-count-summary.json', 'function-observations.json',
                    'diagnostic.json', 'result.json', 'commands.json', 'exception.json', 'controls-final.json'}
MAX_SAVED_MEMBER = 128 << 20
MAX_SAVED_TOTAL = 768 << 20


def require(value, message):
    if not value:
        raise ValueError(message)


def safe_path(name, absolute=False):
    require(isinstance(name, str) and '\x00' not in name and '\\' not in name, 'invalid path: ' + repr(name))
    path = PurePosixPath(name)
    require(path.is_absolute() == absolute and '..' not in path.parts and
            all(part not in ('.', '..') for part in name.rstrip('/').split('/') if part),
            'unsafe path: ' + name)
    require(str(path) not in ('', '.', '/'), 'empty archive/base path')
    return path


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            value.update(chunk)
    return value.hexdigest()


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')


def verify(args):
    require(args.archive.is_file(), 'archive not found')
    require(not args.receipt.exists(), 'verification receipt already exists')
    if args.extract_receipts:
        require(not args.extract_receipts.exists(), 'receipt export directory already exists')
    archive_stat = args.archive.stat()
    compressed_hash = sha256(args.archive)
    expected = None
    if args.archives_json:
        capture = json.loads(args.archives_json.read_text())
        require(capture.get('completed') is True and capture.get('guest_idle') is True,
                'guest archive capture did not finish with an idle confirmation')
        matches = [row for row in capture['groups'] if row['file'] == args.archive.name]
        require(len(matches) == 1, 'archive has no unique capture receipt')
        expected = matches[0]
        require(expected['sha256'] == compressed_hash and expected['bytes'] == archive_stat.st_size,
                'transferred archive differs from its guest hash/size')
        guest_base = args.guest_base or capture['guest_base']
        archive_prefix = args.archive_prefix or capture['archive_prefix']
        require(not args.guest_base or args.guest_base == capture['guest_base'], 'guest-base override differs from receipt')
        require(not args.archive_prefix or args.archive_prefix == capture['archive_prefix'], 'archive-prefix override differs from receipt')
    else:
        require(args.guest_base and args.archive_prefix, 'supply capture receipt or both explicit path mappings')
        guest_base, archive_prefix = args.guest_base, args.archive_prefix
    guest_base, archive_prefix = safe_path(guest_base, True), safe_path(archive_prefix)
    hashes, links, manifests, buffers, seen = {}, {}, {}, {}, set()
    saved_total = regular_bytes = 0
    with tarfile.open(args.archive, 'r|gz') as archive:
        for member in archive:
            path = safe_path(member.name)
            ancestor = member.isdir() and archive_prefix.is_relative_to(path)
            # Earlier single-run captures placed their log/command beside the
            # run directory. They are hashed, retained and never exported.
            sidecar = member.isfile() and str(path) in (
                str(archive_prefix) + '.log', str(archive_prefix) + '.command.json')
            require(path.is_relative_to(archive_prefix) or ancestor or sidecar,
                    'member outside recorded archive prefix: ' + member.name)
            name = str(path)
            require(name not in seen, 'duplicate archive member: ' + name)
            seen.add(name)
            if member.isdir():
                continue
            if member.issym() or member.islnk():
                # Link payloads are retained as metadata only. Symlinks are
                # never followed; only in-archive hard links may supply hashes.
                links[name] = dict(target=member.linkname, hard=member.islnk())
                if member.islnk():
                    target = safe_path(member.linkname)
                    require(target.is_relative_to(archive_prefix), 'hard link leaves archive prefix')
                continue
            require(member.isfile(), 'special file in archive: ' + name)
            capture_bytes = path.name in MANIFESTS | RUN_RECEIPTS | PROFILE_RECEIPTS
            if capture_bytes:
                require(member.size <= MAX_SAVED_MEMBER and saved_total + member.size <= MAX_SAVED_TOTAL,
                        'JSON receipt memory bound exceeded: ' + name)
                saved_total += member.size
            value, saved = hashlib.sha256(), bytearray()
            stream = archive.extractfile(member)
            read_bytes = 0
            for chunk in iter(lambda: stream.read(1 << 20), b''):
                value.update(chunk)
                read_bytes += len(chunk)
                if capture_bytes:
                    saved.extend(chunk)
            require(read_bytes == member.size, 'short archive member: ' + name)
            hashes[name] = value.hexdigest()
            regular_bytes += read_bytes
            if capture_bytes:
                buffers[name] = bytes(saved)
            if path.name in MANIFESTS:
                manifests[name] = json.loads(saved)

    def member_hash(name, trail=()):
        require(name not in trail, 'cyclic archive hard link: ' + name)
        if name in hashes:
            return hashes[name]
        link = links.get(name)
        require(link and link['hard'], 'manifest target is absent or a symlink: ' + name)
        return member_hash(str(safe_path(link['target'])), (*trail, name))

    checks = []
    source_instances = binary_instances = 0
    for name, manifest in sorted(manifests.items()):
        require(isinstance(manifest, dict) and manifest, 'empty/non-dictionary manifest: ' + name)
        parent = PurePosixPath(name).parent
        binary = PurePosixPath(name).name == 'binary-sha256.json'
        for relative, expected_hash in manifest.items():
            require(isinstance(expected_hash, str) and re.fullmatch('[0-9a-f]{64}', expected_hash),
                    'invalid SHA256 in ' + name)
            if binary:
                absolute = safe_path(relative, True)
                require(absolute.is_relative_to(guest_base), 'binary target outside captured guest base: ' + relative)
                target = archive_prefix / absolute.relative_to(guest_base)
                binary_instances += 1
            else:
                target = parent / 'source' / safe_path(relative)
                source_instances += 1
            require(member_hash(str(target)) == expected_hash, 'manifest digest mismatch: ' + str(target))
        checks.append(dict(path=name, files=len(manifest), kind='binary' if binary else 'source'))

    # Export only top-level receipts of actual runner/profile roots. This avoids
    # confusing similarly named fixture JSON in a captured source tree.
    runner_roots = {PurePosixPath(name).parent for name in manifests
                    if PurePosixPath(name).name == 'source-sha256.json'}
    runner_roots.update(PurePosixPath(name).parent for name in buffers if PurePosixPath(name).name == 'plan.json'
                        and str(PurePosixPath(name).parent / 'records.json') in buffers)
    profile_roots = set()
    for name, data in buffers.items():
        if PurePosixPath(name).name == 'diagnostic.json':
            row = json.loads(data)
            if isinstance(row, dict) and row.get('diagnostic') is True:
                profile_roots.add(PurePosixPath(name).parent)
    selected, exports = {}, []
    for name, data in sorted(buffers.items()):
        path = PurePosixPath(name)
        if ((path.parent in runner_roots and path.name in RUN_RECEIPTS) or
                (path.parent in profile_roots and path.name in PROFILE_RECEIPTS)):
            # Parse every exported receipt before writing, while retaining its
            # original bytes and corresponding archive digest.
            json.loads(data)
            relative = path.relative_to(archive_prefix)
            selected[str(relative)] = data
            exports.append(dict(path=str(relative), bytes=len(data), sha256=hashes[name]))
    require(args.archive.stat().st_size == archive_stat.st_size and
            args.archive.stat().st_mtime_ns == archive_stat.st_mtime_ns and
            sha256(args.archive) == compressed_hash, 'archive changed during verification')
    if args.extract_receipts:
        args.extract_receipts.mkdir(parents=True)
        for relative, data in selected.items():
            target = args.extract_receipts / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
    receipt = dict(schema=1, status='PASS', path=str(args.archive.resolve()),
        sha256=compressed_hash, bytes=archive_stat.st_size, archive_prefix=str(archive_prefix),
        guest_base=str(guest_base), guest_capture_hash_checked=expected is not None,
        capture_receipt_sha256=sha256(args.archives_json) if args.archives_json else None,
        regular_files=len(hashes), regular_bytes=regular_bytes, links=len(links),
        manifests_verified=checks, source_file_instances_verified=source_instances,
        binary_file_instances_verified=binary_instances, exported_receipts=exports,
        export_directory=str(args.extract_receipts.resolve()) if args.extract_receipts else None,
        scope='Read-only streaming archive hashes and complete frozen source/binary manifests; no source execution or tests')
    save_new(args.receipt, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--archives-json', type=Path)
    parser.add_argument('--guest-base')
    parser.add_argument('--archive-prefix')
    parser.add_argument('--extract-receipts', type=Path)
    args = parser.parse_args()
    try:
        verify(args)
    except Exception as error:
        if not args.receipt.exists():
            save_new(args.receipt, dict(schema=1, status='FAIL', path=str(args.archive), error=repr(error),
                                      scope='Read-only archive verification; failure is not a pass'))
        raise


if __name__ == '__main__':
    main()
