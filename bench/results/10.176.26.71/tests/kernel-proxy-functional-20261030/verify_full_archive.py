#!/usr/bin/env python3
"""Offline hash/inventory audit; never executes or imports archived code."""
import argparse
import collections
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--raw', type=Path, required=True,
                    help='Main-checkout raw/tests/kernel-proxy-functional-20261030')
parser.add_argument('--output', type=Path, default=HERE / 'full-archive-verification.json')
args = parser.parse_args()

def require(value, message):
    if not value:
        raise ValueError(message)

def sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
    return digest.hexdigest()

def load(path):
    return json.loads(path.read_text())

archive_path = args.raw / 'full-evidence.tar.gz'
receipt_path = args.raw / 'full-result.json'
inventory_path = args.raw / 'full-input-inventory.json'
inputs = [archive_path, receipt_path, inventory_path]
initial = {str(p): p.stat() for p in inputs}
receipt, inventory = load(receipt_path), load(inventory_path)
require(receipt['completed'] and receipt['idle'], 'capture did not complete idle')
require(receipt['boot_id'] == '677b7afa-5358-4ece-a650-5f4a4adecd55' and
        receipt['release'] == '7.0.0-38-kdlock1', 'capture platform differs')
require(sha_file(archive_path) == receipt['archive_sha256'], 'archive SHA256')
require(archive_path.stat().st_size == receipt['archive_bytes'], 'archive byte count')
require(sha_file(inventory_path) == receipt['input_inventory_sha256'], 'inventory SHA256')
require(set(receipt['roots']) == set(inventory), 'inventory roots')
files, objects, kinds, seen, roots = {}, {}, collections.Counter(), set(), set()
data_cache = {}
with tarfile.open(archive_path, 'r|gz') as archive:
    for member in archive:
        name = member.name.rstrip('/')
        parts = PurePosixPath(name)
        require(not parts.is_absolute() and '..' not in parts.parts and name not in seen,
                'unsafe/duplicate member ' + name)
        seen.add(name)
        root, separator, relative = name.partition('/')
        require(root in inventory, 'unlisted root ' + root)
        if not separator:
            require(member.isdir(), 'root is not a directory')
            roots.add(root)
            continue
        row = inventory[root].get(relative)
        require(row is not None, 'unlisted path ' + name)
        require(stat.S_IMODE(row['mode']) == member.mode and row['uid'] == member.uid and
                row['gid'] == member.gid, 'mode/owner mismatch ' + name)
        # Python tarfile preserves the source stat's floating-point mtime in PAX.
        # Full integer ns, inode, device and ctime are inventory-only provenance.
        require(float(row['mtime_ns'] / 1_000_000_000) == member.mtime,
                'archive-representable mtime mismatch ' + name)
        if member.isfile():
            require(stat.S_ISREG(row['mode']) and row['bytes'] == member.size,
                    'file type/size mismatch ' + name)
            data = archive.extractfile(member).read()
            if (name.endswith('/native-call-observation.patch') or
                    ('native-call' in root and name.endswith(('/build/provider/kernel_module/execution/wrapper_entry.inc',
                                                             '/build/provider/kernel_module/kd_exec.c')))):
                data_cache[name] = data
            files[name] = dict(kind='file', bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            if name.endswith('.json') and len(data) < 2_500_000:
                try:
                    objects[name] = json.loads(data)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            if (root == 'kernel-proxy-profiles-r2-unit-20261030' and
                    relative in {'unit.log', 'nano-runner.log', 'basic-runner.log'}):
                objects[name] = data.decode()
        elif member.isdir():
            require(stat.S_ISDIR(row['mode']), 'directory type ' + name)
            files[name] = dict(kind='directory')
        elif member.issym():
            require(stat.S_ISLNK(row['mode']) and member.linkname == row['link'], 'symlink ' + name)
            files[name] = dict(kind='symlink', link=member.linkname)
        elif member.islnk():
            require(stat.S_ISREG(row['mode']), 'hardlink type ' + name)
            files[name] = dict(kind='hardlink', link=member.linkname)
        else:
            raise ValueError('unsupported member type ' + name)
        kinds[files[name]['kind']] += 1
require(roots == set(inventory), 'missing root headers')
require(set(files) == {root + '/' + relative for root, rows in inventory.items() for relative in rows},
        'archive path set differs from exact inventory')
for name, row in files.items():
    if row['kind'] == 'hardlink':
        target = files.get(row['link'], {})
        require(target.get('kind') == 'file', 'unresolved hardlink ' + name)
        row.update(sha256=target['sha256'], bytes=target['bytes'])
        root, relative = name.split('/', 1)
        require(row['bytes'] == inventory[root][relative]['bytes'], 'hardlink size ' + name)

# Preserve the earlier receipt-only milestone and prove byte continuity.
old_fetch = load(HERE / 'fetch-verification.json')
for row in old_fetch['sha256']:
    current = files.get(row['path'], {})
    require(current.get('sha256') == row['sha256'] and current.get('bytes') == row['bytes'],
            'earlier receipt differs ' + row['path'])

checks = []
def check(kind, manifest, reference, path, expected):
    require(files.get(path, {}).get('sha256') == expected,
            'missing/hash mismatch ' + kind + ' ' + path)
    checks.append(dict(kind=kind, manifest=manifest, reference=reference,
                       archived_path=path, sha256=expected))

for path, value in objects.items():
    parent = path.rsplit('/', 1)[0]
    if path.endswith('/source-sha256.json'):
        for name, digest in value.items():
            check('source', path, name, parent + '/source/' + name, digest)
    elif path.endswith('/prepared-source-sha256.json'):
        for name, digest in value.items():
            check('prepared_source', path, name, parent + '/build/provider/' + name, digest)
    elif path.endswith('/binary-sha256.json'):
        for name, digest in value.items():
            prefix = receipt['source_base'] + '/'
            if name.startswith(prefix):
                target = name[len(prefix):]
            elif name.startswith('/root/host_fs/kdlock/'):
                # Maintained spin/mutex basic runner retains these exact binaries.
                target = parent + '/binaries/' + name.rsplit('/', 1)[1]
            else:
                raise ValueError('unrecognized binary reference ' + name)
            check('binary', path, name, target, digest)
    elif path.endswith('/session.json'):
        for field in ['publication', 'published_before', 'published_after']:
            publication = value.get(field)
            if not isinstance(publication, dict) or 'entry' not in publication:
                continue
            entry = publication['entry']
            directory = parent + '/workspace/daemon/0x%x/%d/asm/' % (entry['entry'], entry['tgid'])
            for name, digest in publication['images'].items():
                check('image', path, field + '.' + name, directory + name, digest)

# The Native CALL probe adds a recorded observation patch after the maintained
# provider-preparation manifest. Reconstruct that earlier layer as data only.
def reverse_observation(patch, current_files):
    lines = patch.decode().splitlines(keepends=True)
    result = {}; index = 0
    while index < len(lines):
        require(lines[index].startswith('--- a/'), 'unexpected patch header')
        name = lines[index][6:].strip(); index += 1
        require(lines[index] == '+++ b/' + name + '\n', 'patch pathname mismatch'); index += 1
        current = current_files[name].decode().splitlines(keepends=True)
        output = []; cursor = 0
        while index < len(lines) and lines[index].startswith('@@ '):
            match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n', lines[index])
            require(match is not None, 'patch hunk header')
            old_count, start, new_count = int(match[2] or 1), int(match[3])-1, int(match[4] or 1)
            index += 1; old = []; new = []
            while index < len(lines) and not lines[index].startswith(('@@ ', '--- a/')):
                line = lines[index]; require(line[:1] in {' ', '+', '-'}, 'patch hunk line')
                if line[0] in ' -': old.append(line[1:])
                if line[0] in ' +': new.append(line[1:])
                index += 1
            require(len(old) == old_count and len(new) == new_count and start >= cursor,
                    'patch hunk counts/order')
            require(current[start:start+new_count] == new, 'observation patch differs from archived output')
            output.extend(current[cursor:start]); output.extend(old); cursor = start+new_count
        output.extend(current[cursor:]); result[name] = ''.join(output).encode()
    require(set(result) == set(current_files), 'observation patch file set')
    return result

provider_manifests = []; reconstructed = []
for path, value in objects.items():
    if not isinstance(value, dict) or value.get('kind') != 'spin_cacheline private provider':
        continue
    parent = path.rsplit('/', 1)[0]
    changed = [name for name, digest in value['prepared'].items()
               if files.get(parent+'/'+name, {}).get('sha256') != digest]
    originals = {}
    patch_path = None
    if changed:
        require(parent.endswith('/build/provider'),
                'unexpected provider preparation layout')
        require('kernel-proxy-native-call-live' in parent and set(changed) == {
            'kernel_module/execution/wrapper_entry.inc', 'kernel_module/kd_exec.c'},
            'unexplained prepared-provider mismatch')
        patch_path = parent[:-len('/build/provider')] + '/native-call-observation.patch'
        originals = reverse_observation(data_cache[patch_path],
            {name: data_cache[parent+'/'+name] for name in changed})
    for name, expected in value['prepared'].items():
        if name in originals:
            require(hashlib.sha256(originals[name]).hexdigest() == expected,
                    'reconstructed provider base differs '+path+':'+name)
            reconstructed.append(dict(manifest=path, reference=name,
                base_sha256=expected, final_sha256=files[parent+'/'+name]['sha256'],
                observation_patch=patch_path, patch_sha256=files[patch_path]['sha256']))
        else:
            check('provider_prepared_manifest', path, name, parent+'/'+name, expected)
    provider_manifests.append(dict(path=path, references=len(value['prepared']),
                                   direct_matches=len(value['prepared'])-len(changed),
                                   exact_reconstructed_base_matches=len(changed)))

profile_root = 'kernel-proxy-profiles-r2-unit-20261030/'
owner = objects[profile_root + 'owner.json']
require(owner['completed'] and owner['source_commit'] == '8446f4ecb08816380a4c233197a8ce5e4d333aac' and
        owner['boot_id'] == receipt['boot_id'] and all(b['returncode'] == 0 for b in owner['blocks']),
        'profiles-r2 owner evidence')
require(re.findall(r'Unit tests: (\d+) passed, (\d+) failed', objects[profile_root + 'unit.log']) == [('4', '0')],
        'profiles-r2 driver totals')
for name, count in [('basic-runner.log', 9), ('nano-runner.log', 12)]:
    require(re.findall(r'Ran (\d+) tests', objects[profile_root + name]) == [str(count)] and
            objects[profile_root + name].rstrip().endswith('OK'), 'runner count/status ' + name)

for path in inputs:
    before, after = initial[str(path)], path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino) ==
            (after.st_size, after.st_mtime_ns, after.st_ino), 'input changed during audit ' + str(path))
summary = {}
for kind in sorted({r['kind'] for r in checks}):
    selected = [r for r in checks if r['kind'] == kind]
    summary[kind] = dict(references=len(selected), manifests=len({r['manifest'] for r in selected}),
                         unique_archived_files=len({r['archived_path'] for r in selected}))
manifest_rows = []
for path in sorted({r['manifest'] for r in checks}):
    selected = [r for r in checks if r['manifest'] == path]
    manifest_rows.append(dict(path=path, sha256=files[path]['sha256'], references=len(selected),
                              kinds=sorted({r['kind'] for r in selected}), missing=0, mismatched=0))
result = dict(completed=True, scope='Offline full-archive byte/metadata verification; no archived code executed',
              capture=receipt, raw_path=str(args.raw), result_sha256=sha_file(receipt_path),
              controller_sha256=sha_file(args.raw / 'full-controller.py'),
              inventoried_paths=len(files), extra_root_directory_headers=len(roots), types=dict(kinds),
              regular_file_bytes=sum(v.get('bytes', 0) for v in files.values()),
              metadata_verified=['exact relative path set', 'type', 'permission mode', 'uid', 'gid',
                                 'regular-file size', 'floating-point/PAX mtime', 'symlink target'],
              inventory_only_metadata=['device', 'inode', 'ctime_ns', 'link count', 'sub-float mtime nanoseconds'],
              earlier_receipts_identical=len(old_fetch['sha256']), manifest_summary=summary,
              manifests=manifest_rows, binary_and_image_checks=[r for r in checks if r['kind'] in {'binary', 'image'}],
              provider_preparation_manifests=provider_manifests,
              historical_prepared_layers=reconstructed,
              profiles_r2=dict(source_commit=owner['source_commit'], unit_drivers_passed=4,
                               unit_drivers_failed=0, basic_runner_cases=9, nano_runner_cases=12,
                               blocks=owner['blocks'], performance_claim=False),
              limits=['No new functional execution, kernel boot, syscall/MM validation or performance evidence.',
                      'Recorded source manifests are now authenticated against archive bytes, including historical leaves; this does not make those leaves compiler dependencies.',
                      'The earlier Git authentication and functional arithmetic remain separate in verification.json.',
                      'Binary/image equality authenticates retained bytes, not every runtime instruction or mitigation path.'])
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({key: result[key] for key in ['completed', 'inventoried_paths', 'types', 'earlier_receipts_identical', 'manifest_summary']}))
