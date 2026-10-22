#!/usr/bin/env python3
"""Read-only archive verification on the source host; no extraction or execution."""
import argparse
import collections
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads((args.archives / 'archives.json').read_text())
    assert receipt['completed'] and receipt['guest_idle']
    assert digest(args.archives / 'archive_run.py') == receipt['script_sha256']
    inventory_file = args.archives / 'input-inventory.json'
    assert digest(inventory_file) == receipt['input_inventory_sha256']
    inventory = json.loads(inventory_file.read_text())
    prefix = receipt['archive_prefix']
    health_path = receipt['health_path']
    seen, hashes, metadata, hardlinks = {}, {}, {}, {}
    statuses = collections.Counter()
    checked_sessions = 0
    archives = []
    for group in receipt['groups']:
        path = args.archives / group['file']
        assert path.stat().st_size == group['bytes'] and digest(path) == group['sha256']
        archives.append(dict(file=path.name, bytes=path.stat().st_size, sha256=group['sha256']))
        with tarfile.open(path, 'r|gz') as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                assert not name.is_absolute() and '..' not in name.parts and name.parts[0] == prefix
                relative = str(name.relative_to(prefix))
                assert relative != '.' and relative not in seen and relative in inventory, relative
                expected = inventory[relative]
                assert stat.S_IMODE(expected['mode']) == member.mode
                assert expected['uid'] == member.uid and expected['gid'] == member.gid
                assert abs(member.mtime * 1e9 - expected['mtime_ns']) <= 1024, relative
                if member.isdir():
                    assert stat.S_ISDIR(expected['mode'])
                elif member.issym():
                    assert stat.S_ISLNK(expected['mode']) and member.linkname == expected['link']
                elif member.islnk():
                    assert stat.S_ISREG(expected['mode'])
                    target = PurePosixPath(member.linkname)
                    assert target.parts[0] == prefix and '..' not in target.parts
                    hardlinks[relative] = str(target.relative_to(prefix))
                else:
                    assert member.isfile() and stat.S_ISREG(expected['mode']) and member.size == expected['bytes']
                    stream = archive.extractfile(member)
                    result = hashlib.sha256()
                    capture = (relative in ('source-sha256.json', 'source-state.json', health_path, 'matrix-status.json',
                                            'report/collection.json', 'report/provider-reconstruction.json')
                               or re.fullmatch(r'matrix/[^/]+/(source-sha256|binary-sha256)\.json', relative)
                               or re.fullmatch(r'matrix/[^/]+/source/bench/spin_cacheline/\.build/provider/manifest\.json', relative)
                               or re.fullmatch(r'matrix/[^/]+/[^/]+/session\.json', relative))
                    blocks = []
                    for block in iter(lambda: stream.read(1 << 20), b''):
                        result.update(block)
                        if capture:
                            blocks.append(block)
                    hashes[relative] = result.hexdigest()
                    if capture:
                        value = json.loads(b''.join(blocks))
                        if relative.endswith('/session.json'):
                            assert value['drained'] is True and not value.get('cleanup_error'), relative
                            assert value['measurement']['complete'] is True and value['measurement']['data_ok'] is True
                            assert value['execution_status'] in ('OK', 'NO_JIT')
                            statuses[(value['lock_kind'], value['arm'], value['execution_status'])] += 1
                            checked_sessions += 1
                        else:
                            metadata[relative] = value
                seen[relative] = True
    while hardlinks:
        resolved = {name: target for name, target in hardlinks.items() if target in hashes}
        assert resolved, 'unresolved archived hard links'
        for name, target in resolved.items():
            assert inventory[name]['bytes'] == inventory[target]['bytes']
            hashes[name] = hashes[target]
            del hardlinks[name]
    assert set(seen) == set(inventory)
    health = metadata[health_path]
    assert health['idle'] and health['boot_id'] == receipt['boot_id']
    assert health['sessions'] == health['drained'] == health['kernel_logs'] == 3600
    assert not health['per_session_kernel_faults'] and not health['new_faults_in_retained_dmesg']
    assert hashes[health_path] == receipt['health_sha256']
    assert hashes['capture-health.py'] == health['script_sha256']
    assert hashes['report.py'] == metadata['report/collection.json']['report_script_sha256']
    assert metadata['report/collection.json']['recorded_sessions'] == 3600
    assert metadata['matrix-status.json']['state'] == 'COLLECTED'
    assert checked_sessions == 3600
    frozen = metadata['source-sha256.json']
    assert hashes['frozen-source.tar'] == metadata['source-state.json']['archive_sha256']
    assert len(frozen) == metadata['source-state.json']['file_count'] == 664
    provider = metadata['report/provider-reconstruction.json']
    assert provider['complete'] and provider['kind'] == 'spin_cacheline private provider'
    for name, expected in provider['production'].items():
        assert frozen[name] == expected, name
    for name, expected in provider['observation'].items():
        assert frozen['bench/spin_cacheline/provider/' + name] == expected, name
    checked_sources = checked_binaries = source_manifests = binary_manifests = generated_sources = 0
    for name, values in metadata.items():
        match = re.fullmatch(r'matrix/([^/]+)/source-sha256\.json', name)
        if match:
            source_manifests += 1
            folder = 'matrix/' + match[1]
            for source, expected in values.items():
                archived = folder + '/source/' + source
                assert expected == hashes[archived], source
                prefix = 'bench/spin_cacheline/.build/provider/'
                if source.startswith(prefix):
                    prepared = source[len(prefix):]
                    if prepared == 'manifest.json':
                        assert metadata[archived] == provider, source
                    else:
                        assert provider['prepared'][prepared] == expected, source
                    generated_sources += 1
                else:
                    assert frozen[source] == expected, source
                checked_sources += 1
        match = re.fullmatch(r'matrix/([^/]+)/binary-sha256\.json', name)
        if match:
            binary_manifests += 1
            folder = 'matrix/' + match[1]
            absolute = receipt['guest_base'] + '/' + folder + '/'
            for binary, expected in values.items():
                if binary.startswith(absolute):
                    archived = folder + '/' + binary[len(absolute):]
                else:
                    archived = folder + '/binaries/' + PurePosixPath(binary).name
                assert hashes[archived] == expected, archived
                checked_binaries += 1
    assert source_manifests == binary_manifests == 16
    result = dict(passed=True, scope='Read-only archive inventory, content, source/binary manifests and session receipts',
                  frozen_source_revision=metadata['source-state.json']['git_head'],
                  frozen_source_archive_sha256=hashes['frozen-source.tar'],
                  archive_receipt_sha256=digest(args.archives / 'archives.json'),
                  archives=archives, paths=len(seen), hashed_files=len(hashes),
                  checked_source_files=checked_sources, checked_binaries=checked_binaries,
                  generated_source_files=generated_sources,
                  checked_sessions=checked_sessions,
                  session_statuses=[dict(lock=k[0], backend=k[1], status=k[2], count=v)
                                    for k, v in sorted(statuses.items())])
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
