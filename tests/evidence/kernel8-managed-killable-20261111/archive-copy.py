#!/usr/bin/env python3
"""Preserve closed K04 evidence and inspect raw bytes with the standard library."""
from pathlib import Path, PurePosixPath
from collections import Counter
import gzip
import hashlib
import io
import json
import stat
import struct
import tarfile

DRAFT = Path('/tmp/kdlock-kernel8-managed-killable-pass-draft-20261111-01')
COLLECTION = Path('/tmp/kdlock-kernel8-managed-killable-collection-20261111-04')
CONTROLS = Path('/tmp/kdlock-kernel8-managed-killable-20261111-04')
SOURCE = Path('/tmp/kdlock-kernel8-fixture-source-5c14b483-01')
AST = Path('/tmp/kdlock-kernel8-frontier-claim-ast-collection-20261111-01/payload/receipts')
CLEANUP = Path('/tmp/kdlock-kernel8-killable-final-recovery-collection-20261111-01/payload/runtime/result.json')
PACKAGE = Path('/tmp/kdlock-kernel8-build-collection-20261111-01/payload/input/package.json')
PEER = Path('/tmp/kdlock-k04-independent-audit-20261111.json')
PEER_SCRIPT = Path('/tmp/kdlock-k04-independent-audit-20261111.py')
sha = lambda data: hashlib.sha256(data).hexdigest()
load = lambda path: json.loads(path.read_bytes())
origins = {}
copied = []


def identity(path):
    s = path.lstat()
    assert stat.S_ISREG(s.st_mode), str(path)
    return [s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def read(path):
    before = identity(path)
    data = path.read_bytes()
    assert identity(path) == before and len(data) == before[4], str(path)
    origins[str(path)] = (before, sha(data))
    return data


def regular_files(root):
    files = []
    for path in sorted(root.rglob('*')):
        mode = path.lstat().st_mode
        assert not stat.S_ISLNK(mode), str(path)
        if stat.S_ISREG(mode):
            files.append(path)
        else:
            assert stat.S_ISDIR(mode), str(path)
    return files


def copy(path, relative):
    data = read(path)
    encoded = data
    encoding = 'identity'
    if len(data) >= 65536 and path.suffix not in ('.o', '.elf', '.ko'):
        encoded = gzip.compress(data, compresslevel=9, mtime=0)
        assert gzip.decompress(encoded) == data
        relative += '.gz'
        encoding = 'gzip'
    target = DRAFT / relative
    assert not target.exists(), str(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    copied.append({'source': str(path), 'source_identity': origins[str(path)][0],
                   'raw_bytes': len(data), 'raw_sha256': sha(data), 'path': relative,
                   'encoding': encoding, 'stored_bytes': len(encoded), 'stored_sha256': sha(encoded)})


def copy_tree(root, relative):
    files = regular_files(root)
    for path in files:
        copy(path, relative + '/' + str(path.relative_to(root)))
    return {'source': str(root), 'files': len(files), 'bytes': sum(identity(p)[4] for p in files)}


def tar_audit(path, expected):
    data = read(path)
    seen = {}
    end = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts
            assert '\\' not in member.name and member.name not in seen
            content = tar.extractfile(member).read()
            assert len(content) == member.size
            seen[member.name] = {'bytes': len(content), 'sha256': sha(content)}
            end = max(end, member.offset_data + ((member.size + 511) // 512) * 512)
    assert seen == expected and len(data) >= end + 1024 and not any(data[end:])
    return {'bytes': len(data), 'sha256': sha(data), 'members': len(seen),
            'regular_unique_exact_members': True, 'zero_trailing_padding': True}


def frame(data, operation, fixed_words, row_words, blob_count=0):
    abi, op, total, count = struct.unpack_from('<4Q', data)
    assert (abi, op, total) == (1, operation, len(data))
    offset = 32
    fixed = struct.unpack_from('<' + str(fixed_words) + 'Q', data, offset)
    offset += fixed_words * 8
    rows = []
    for _ in range(count):
        rows.append(struct.unpack_from('<' + str(row_words) + 'Q', data, offset))
        offset += row_words * 8
    blobs = []
    for _ in range(blob_count):
        length, = struct.unpack_from('<Q', data, offset)
        offset += 8
        assert offset + length <= len(data)
        blobs.append(data[offset:offset + length])
        offset += length
    assert offset == len(data)
    return fixed, rows, blobs


assert not DRAFT.exists()
index_bytes = read(COLLECTION / 'copy-index.json')
assert sha(index_bytes) == '6fd35fdc4e43acd5ce12fe2c01a1ae2ccacbc300539aa639cbbbb1bc7a1e5a01'
index = json.loads(index_bytes)
collection = load(COLLECTION / 'collection.json')
assert index['count'] == len(index['files']) == collection['files'] == 179
assert index['bytes'] == sum(row['bytes'] for row in index['files']) == collection['bytes'] == 2093451
assert collection['status'] == 'COMPLETE'
expected = {}
for row in index['files']:
    assert row['path'] == 'payload/' + row['name']
    data = read(COLLECTION / row['path'])
    assert (len(data), sha(data)) == (row['bytes'], row['sha256'])
    assert row['name'] not in expected
    expected[row['name']] = {'bytes': len(data), 'sha256': sha(data)}
assert {str(p.relative_to(COLLECTION / 'payload')) for p in regular_files(COLLECTION / 'payload')} == set(expected)
transport = tar_audit(COLLECTION / '.collection/copy.tar', expected)
assert transport['sha256'] == collection['archive_sha256']
runtime = COLLECTION / 'payload/runtime'
inner_bytes = read(runtime / 'result.json')
outer_bytes = read(COLLECTION / 'payload/receipts/result.json')
assert sha(inner_bytes) == 'd50378c6e084a41eca1da70e23f9d76b7df80048175e85f6fba6ce57cb7bb062'
assert sha(outer_bytes) == 'd7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488'
inner = json.loads(inner_bytes)
outer = json.loads(outer_bytes)
assert inner['status'] == 'managed_killable_mechanism_pass' and outer['status'] == 'MANAGED_KILLABLE_COMPLETE'
assert outer['runner_result_sha256'] == sha(inner_bytes)
assert outer['source_git_head'] == '5c14b483ca16b3bba8f3dd40a00f16a6efefc12c'
assert outer['compiled_module_source_git_head'] == '140aecc4f83a6b6ae6f20245234e8a63504f9210'
assert outer['kernel_core_git_head'] == '0d42063ead37dc8fc1631fa56c8348890ede9c5f'
assert inner['module_sha256'] == outer['module_sha256'] == '74bec2fad7f75b1e5ea4d5ffbd4a4d699d99f3ca2413145ef4801479498e36b8'
names = [row['name'] for row in inner['cases']]
assert names == ['ready-before-fatal-cancel', 'reader-drain-cancel', 'queued-exit-before-holder-release',
                 'learning-0', 'learning-1', 'origin-signal-wakes-foreign-c', 'candidate-cancel-drains-current-w']
assert len(inner['children']) == len(inner['waitpid']) == len(inner['exit_acknowledgments']) == 19
assert {r['pid'] for r in inner['children']} == {r['pid'] for r in inner['waitpid']} == {r['pid'] for r in inner['exit_acknowledgments']}
assert all(row['returned'] and row['reaped'] for row in inner['exit_acknowledgments'])
assert Counter(row['wait_status'] for row in inner['waitpid']) == {0: 13, 9: 6}
for case in inner['cases']:
    status = case['status']
    assert all(status[k] == 0 for k in ('overflow', 'owner', 'tail', 'readers', 'writer', 'writer_pending', 'native_scopes', 'cleanup_error'))
    assert status['pool_idle'] == 1
event_bytes = read(runtime / 'observations-final.bin')
header = struct.unpack_from('<5Q', event_bytes)
assert header == (1, 20, 131072, 241, 0) and len(event_bytes) == 40 + 241 * 160
fields = 'kind task state origin node acquisition parent owner owner_task object image ip cursor related phase result flags source_user return_user notifier'.split()
events = [dict(zip(fields, struct.unpack_from('<20Q', event_bytes, 40 + i * 160)), index=i) for i in range(241)]
observations = load(runtime / 'observations-final.json')
assert observations['fields'] == fields and observations['records'] == events
matches = [0]
def visit(value):
    if isinstance(value, dict):
        if set(fields + ['index']) <= set(value):
            assert all((value[k] & ((1 << 64) - 1)) == events[value['index']][k] for k in fields)
            matches[0] += 1
        for item in value.values():
            visit(item)
    elif isinstance(value, list):
        for item in value:
            visit(item)
visit(inner)
for retired in inner['retirement']:
    order = [retired[name]['index'] for name in ('grant', 'owner_stop', 'physical_begin', 'physical_end',
                                                'source_drop', 'release_retire', 'owner_retire', 'node_ready', 'slot_free')]
    assert order == sorted(set(order))
cancellation = []
for case in inner['cases']:
    if 'cancelled' in case:
        cancelled, ready, freed = [case[k] for k in ('cancelled', 'retire_ready', 'slot_free')]
        assert cancelled['kind'] == 43 and cancelled['result'] == (1 << 64) - 4 and cancelled['phase'] == 5
        assert ready['kind'] == 9 and freed['kind'] == 2 and cancelled['index'] < ready['index'] < freed['index']
        assert all(len({row[k] for row in (cancelled, ready, freed)}) == 1 for k in ('state', 'origin', 'node', 'acquisition'))
        cancellation.append({'name': case['name'], 'cancelled': cancelled['index'], 'retire_ready': ready['index'],
                             'slot_free': freed['index'], 'actual_waitpid': case.get('actual_exit')})
assert len(inner['cycles']) == 4 and [row['published'] for row in inner['cycles']] == [True, True, False, False]
assert [row['acknowledged'] for row in inner['cycles']] == [0, 1, 0, 0]
assert inner['fixed_claim_no_new_facts'] is False and inner['fixed_claim_no_new_ordinary_learning'] is True
assert inner['fixed_claim_only_expected_native_frontiers'] is True and inner['fixed_image_unchanged'] is True
assert inner['fixed_snapshot_unchanged'] is True and inner['fixed_claim_published'] is False
key = lambda row: (row['epoch'], row['record'], row['incarnation'])
keys = [key(row) for row in inner['fixed_pending_keys']]
baseline = [key(row) for row in inner['fixed_pending_baseline']]
assert len(keys) == len(set(keys)) == 2 and len(baseline) == 1 and set(baseline) < set(keys)
assert set(keys) == {key(row) for row in inner['native_frontier_archive_keys']} == {key(row['fact']) for row in inner['native_frontiers']}
frontiers = []
for row in inner['native_frontiers']:
    assert row['exit']['ip'] == row['exit']['cursor'] == row['forward']['ip'] == row['call']['site']
    assert row['exit']['related'] == row['forward']['related'] and row['fact']['incarnation'] == 1
    assert row['exit']['result'] == 3 and row['exit']['flags'] == 10 and row['exit']['phase'] == 1
    frontiers.append({'name': row['name'], 'key': list(key(row['fact'])),
                      'reserve_frame_grant_enter_exit_forward': [row[k]['index'] for k in ('reserve', 'frame', 'grant', 'enter', 'exit', 'forward')],
                      'call_site': row['call']['site'], 'target': row['forward']['related'], 'slot_free': row['slot_free']['index']})
wire = []
for number in range(1, 23):
    base = runtime / 'wire' / f'attempt-{number:08d}'
    request, reply, envelope = [read(base / name) for name in ('request.bin', 'reply.bin', 'returned-envelope.bin')]
    words = struct.unpack('<9Q', envelope)
    metadata = load(base / 'result.json')
    assert words[0] == 1 and words[4] == len(request) and words[7] == len(reply) and words[8] == 0
    assert metadata['completed_response'] is True and metadata['status'] == 0
    assert (metadata['operation'], metadata['sequence'], metadata['request_bytes'], metadata['reply_bytes']) == (words[1], words[2], len(request), len(reply))
    wire.append({'attempt': number, 'operation': words[1], 'sequence': words[2], 'status': words[8]})
assert inner['wire']['attempts'] == 22 and [row['sequence'] for row in wire] == list(range(22))
assert [(row['operation'], row['sequence']) for row in wire[-4:]] == [(9, 18), (10, 19), (11, 20), (6, 21)]
archive_bytes = read(runtime / 'shutdown-archive.json')
archive = json.loads(archive_bytes)
assert sha(archive_bytes) == inner['archive_sha256'] == outer['archive_sha256'] == 'fc2220a597868184cb5731251f8a33b7869f6c541bbb6c7f0802846440782d1e'
archive_key = lambda row: (row['fields']['epoch_identity']['bytes_hex'], row['fields']['record_identity']['bytes_hex'], row['fields']['incarnation'])
assert archive['learning_closed'] and len(archive['facts']) == 2
assert {archive_key(row) for row in archive['claim']['keys']} == {archive_key(row['key']) for row in archive['facts']} == set(keys)
assert all(row['acknowledgment_identities'] == [] for row in archive['facts'])
claim_bytes = bytes.fromhex(archive['raw_claim']['bytes_hex'])
assert claim_bytes == read(runtime / 'wire/attempt-00000020/reply.bin')
claim = frame(claim_bytes, 10, 3, 12, 1)
pairs = {(int.from_bytes(bytes.fromhex(record), 'little'), incarnation) for epoch, record, incarnation in keys}
assert {row[:2] for row in claim[1]} == pairs and len(claim[1]) == 2
assert claim[1][0][2:] == claim[1][1][2:]
assert claim[0][2] == int.from_bytes(bytes.fromhex(keys[0][0]), 'little')
assert claim[1][0][2:] == (0xff1100010c13b000, 0xff1100010c13b138, 3, 10,
                          0xffffffffc000b4e6, 0xffffffffc000b300, 0xffffffffc000b4e6, 1, 0, 0)
source_bytes = read(runtime / 'source-export.bin')
abi, operation, total, source_count = struct.unpack_from('<4Q', source_bytes)
assert (abi, operation, total, source_count) == (1, 8, len(source_bytes), 5)
source_fixed = struct.unpack_from('<7Q', source_bytes, 32)
offset = 88
regions = []
for _ in range(source_count):
    start, length = struct.unpack_from('<2Q', source_bytes, offset)
    offset += 16
    code = source_bytes[offset:offset + length]
    assert len(code) == length
    offset += length
    regions.append((start, code))
offset += source_fixed[4] * 16
length, = struct.unpack_from('<Q', source_bytes, offset)
offset += 8
assert source_bytes[offset:offset + length] == claim[2][0] and offset + length == len(source_bytes)
site, target = 0xffffffffc000b4e6, 0xffffffffc000b300
assert [code[site-start:site-start+5] for start, code in regions if start <= site < start + len(code)] == [bytes.fromhex('2e2e2effd0')]
assert not any(start <= target < start + len(code) for start, code in regions)
settle_request = frame(read(runtime / 'wire/attempt-00000021/request.bin'), 11, 2, 2, 1)
settle_reply_bytes = read(runtime / 'wire/attempt-00000021/reply.bin')
settle_reply = frame(settle_reply_bytes, 11, 3, 2)
assert settle_request[0] == settle_reply[0][1:] == claim[0][:2]
assert len(settle_request[1]) == len(settle_reply[1]) == 2 and set(settle_request[1]) == set(settle_reply[1]) == pairs
assert settle_request[2] == [hashlib.sha256(archive_bytes).digest()] and settle_reply[0][0] != 0
assert frame(read(runtime / 'wire/attempt-00000022/request.bin'), 6, 2, 0) == frame(read(runtime / 'wire/attempt-00000022/reply.bin'), 6, 2, 0) == (claim[0][:2], [], [])
for cycle, attempt in ((1, 5), (2, 11)):
    _, _, blobs = frame(read(runtime / f'wire/attempt-{attempt:08d}/request.bin'), 3, 1, 0, 5)
    for blob, relative in zip(blobs[:4], ('image.S', 'metadata.c', 'manifest.json', 'build/image.bin')):
        assert blob == read(runtime / f'cycle-{cycle}' / relative)
    elf = read(runtime / f'cycle-{cycle}/build/image.elf')
    assert elf[:6] == b'\x7fELF\x02\x01'
    offset, = struct.unpack_from('<Q', elf, 40)
    size, count, string_index = struct.unpack_from('<3H', elf, 58)
    sections = [struct.unpack_from('<IIQQQQIIQQ', elf, offset + i * size) for i in range(count)]
    strings = sections[string_index]
    namestring = elf[strings[4]:strings[4] + strings[5]]
    assert [elf[s[4]:s[4] + s[5]] for s in sections if namestring[s[0]:].split(b'\0', 1)[0] == b'.text'] == [blobs[3]]
final = inner['final']
assert final['retired'] == final['pool_idle'] == 1
assert all(final[k] == 0 for k in ('binding_live', 'runtime_live', 'source_live', 'trace_live', 'self_held', 'native_scopes', 'owner', 'tail', 'writer', 'writer_pending', 'readers', 'overflow', 'setup_error', 'cleanup_error'))
assert all(all(v == (-1 if k in ('admission', 'selection') else 0) for k, v in role.items()) for role in final['roles'])
assert outer['identity_before'] == outer['identity_after'] == {'activity': [], 'identity': {'boot': 'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0', 'release': '7.0.0-38-kdrebuild8', 'taint': 4096}, 'modules': 'nls_iso8859_1 12288 1 - Live 0xffffffffc000a000\n'}
assert sha(read(CONTROLS / 'postread.json')) == '44e7d6cdd01e54c791c3426368eef3758e26b514d7a1849ed47b76de110ccf59'
manifest = load(SOURCE / 'source-sha256.json')
source_state = load(SOURCE / 'source-state.json')
source_transport = tar_audit(SOURCE / 'source.tar', manifest)
assert len(manifest) == source_state['files'] == 143 and source_state['transfer_bytes'] == 1612508
assert sum(row['bytes'] for row in manifest.values()) == 1612508 and source_state['git_status'] == ''
assert source_state['source_git_head'] == outer['source_git_head']
assert source_transport['sha256'] == '35e9d05d6a4b88a3d3bffe95ad1f6674388486ff6e06d4be210aece753512989'
package = load(PACKAGE)
assert len(package['files']) == 78 and package['core_git_head'] == outer['kernel_core_git_head']
assert all(manifest[name]['sha256'] == digest for name, digest in package['files'].items())
assert sha(read(AST / 'result.json')) == outer['host_checks_sha256'] == '3fc26667154f5232125e0e02ea40e11084a39fd475e5a44367d30514bc7d2de0'
assert sha(read(CLEANUP)) == outer['cleanup_sha256'] == '40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0'
assert sha(read(PEER)) == 'bbb8c131b373d5d23360c585b6246157a701dbbf4c958806360e21e279fd0208'
assert sha(read(PEER_SCRIPT)) == '2749c42c923c0ee596e4f308711fcba2c01fe38670fa405d2cba1df4e1cdf2ef'
audit = {'format': 'kdlock.k04-closed-byte-audit.v1',
         'scope': 'Standard-library sourcehost byte/archive inspection only. No project imports, tests, builds or VM operations.',
         'collection': {'payload_files': 179, 'payload_bytes': 2093451, 'copy_index_sha256': sha(index_bytes), 'transport': transport},
         'runtime_sha256': sha(inner_bytes), 'outer_sha256': sha(outer_bytes), 'source_git_head': outer['source_git_head'],
         'module_sha256': inner['module_sha256'], 'kernel_core_git_head': outer['kernel_core_git_head'],
         'cases': names, 'children': {'count': 19, 'normal_wait_status_zero': 13, 'sigkill_wait_status_nine': 6, 'all_exit_ack_returned_reaped': True},
         'events': {'header': list(header), 'sha256': sha(event_bytes), 'embedded_event_dictionary_matches': matches[0]},
         'cancellation_ordering': cancellation, 'native_frontiers': frontiers, 'cycles': inner['cycles'], 'wire': wire,
         'retirement_ordered_acquisitions': len(inner['retirement']),
         'reached_call_bytes': '2e2e2effd0', 'native_target_outside_exported_regions': True,
         'fixed_claim_no_new_facts': False, 'fixed_claim_no_new_ordinary_learning': True,
         'archive': {'bytes': len(archive_bytes), 'sha256': sha(archive_bytes), 'exact_keys': [list(row) for row in keys],
                     'settled_keys': [list(row) for row in keys], 'settle_reply_sha256': sha(settle_reply_bytes), 'unacknowledged': True},
         'stage_and_elf_text_matches': 2, 'normal_retirement_and_unload': True, 'identity_after': outer['identity_after'],
         'source': {'state': source_state, 'transport': source_transport, 'core_files': 78},
         'ast_receipt_sha256': outer['host_checks_sha256'], 'cleanup_predecessor_sha256': outer['cleanup_sha256'],
         'independent_peer_audit_sha256': sha(read(PEER))}
DRAFT.mkdir()
audit['copied_trees'] = [copy_tree(COLLECTION, 'collection'), copy_tree(CONTROLS, 'source-host'), copy_tree(SOURCE, 'source-export')]
for path, relative in ((PACKAGE, 'source-export/kernel-package-0d42063e.json'),
                       (AST / 'result.json', 'prerequisites/runner-ast-result.json'),
                       (AST / 'frontier-reservation-killable-runner-ast.log', 'prerequisites/runner-ast.log'),
                       (CLEANUP, 'prerequisites/k03-cleanup-result.json'),
                       (PEER, 'independent-peer/audit.json'), (PEER_SCRIPT, 'independent-peer/audit.py'),
                       (Path(__file__), 'archive-copy.py')):
    copy(path, relative)
for name, (before, digest) in origins.items():
    path = Path(name)
    assert identity(path) == before and sha(path.read_bytes()) == digest, name
for row in copied:
    data = (DRAFT / row['path']).read_bytes()
    assert (len(data), sha(data)) == (row['stored_bytes'], row['stored_sha256'])
    decoded = gzip.decompress(data) if row['encoding'] == 'gzip' else data
    assert (len(decoded), sha(decoded)) == (row['raw_bytes'], row['raw_sha256'])
audit['copy_summary'] = {'files': len(copied), 'raw_bytes': sum(row['raw_bytes'] for row in copied),
                         'stored_bytes': sum(row['stored_bytes'] for row in copied),
                         'gzip_files': sum(row['encoding'] == 'gzip' for row in copied), 'duplicate_transport_tars_omitted': 0}
audit['object_paths'] = [row['path'] for row in copied if row['path'].endswith(('.o', '.ko'))]
for name, value in (('copy-index.json', {'format': 'kdlock.lossless-file-copy.v1', 'files': copied}), ('audit.json', audit)):
    (DRAFT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
print(json.dumps({'draft': str(DRAFT), 'copy_summary': audit['copy_summary'], 'object_paths': audit['object_paths'],
                  'audit_sha256': sha((DRAFT / 'audit.json').read_bytes()),
                  'copy_index_sha256': sha((DRAFT / 'copy-index.json').read_bytes())}, sort_keys=True))
