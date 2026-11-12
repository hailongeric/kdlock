#!/usr/bin/env python3
"""Preserve closed AUX source/object evidence with standard-library byte audits."""
from pathlib import Path, PurePosixPath
import gzip
import hashlib
import io
import json
import stat
import tarfile

DRAFT = Path('/tmp/kdlock-kernel8-aux-context-review-draft-20261111-01')
MANIFEST = Path('/tmp/kdlock-kernel8-aux-audit-input-manifest-20261111-01.json')
ADMISSION = Path('/tmp/kdlock-kernel8-mm-prefix-0798c1ab-02/admission.json')
sha = lambda b: hashlib.sha256(b).hexdigest()
load = lambda p: json.loads(p.read_bytes())
trees = {
    '/tmp/kdlock-kernel8-aux-context-controls-20261111-01': 'source-host/native-source-01',
    '/tmp/kdlock-kernel8-aux-context-controls-20261111-02': 'source-host/frame-source-02',
    '/tmp/kdlock-kernel8-aux-context-source-20261111-01': 'native-source/collection',
    '/tmp/kdlock-kernel8-aux-context-source-20261111-02': 'frame-source/collection',
    '/tmp/kdlock-kernel8-aux-object-capture-controls-20261111-01': 'source-host/object-capture-failed-01',
    '/tmp/kdlock-kernel8-aux-object-capture-controls-20261111-02': 'source-host/object-capture-02',
    '/tmp/kdlock-kernel8-aux-object-discovery-20261111-02': 'scheduler-discovery',
    '/tmp/kdlock-kernel8-aux-object-capture-collection-20261111-02': 'object-capture/collection',
    '/tmp/kdlock-kernel8-runtime-metadata-20261111-01': 'source-host/runtime-metadata',
}
standalone = {
    '/tmp/kdlock-kernel8-stack-weights-20261111.py': 'analysis/stack-weights.py',
    '/tmp/kdlock-kernel8-narrow-aux-source-0798c1ab-01.md': 'analysis/narrow-source-graph.md',
}
for number in ('01', '02'):
    standalone[f'/tmp/kdlock-kernel8-aux-object-capture-plan-20261111-{number}.json'] = f'analysis/object-plan-{number}.json'
for number in ('02', '03', '04'):
    standalone[f'/tmp/kdlock-kernel8-aux-stack-weights-20261111-{number}.json'] = f'analysis/weights-{number}.json'
for number in ('01', '02', '03', '04'):
    standalone[f'/tmp/kdlock-kernel8-narrow-aux-stack-budget-20261111-{number}.json'] = f'analysis/conditional-budget-{number}.json'
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
    result = []
    for path in sorted(root.rglob('*')):
        mode = path.lstat().st_mode
        assert not stat.S_ISLNK(mode), str(path)
        if stat.S_ISREG(mode):
            result.append(path)
        else:
            assert stat.S_ISDIR(mode), str(path)
    return result


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
            'exact_regular_unique_members': True, 'zero_trailing_padding': True}


def collection_audit(root, count, byte_count):
    index = load(root / 'copy-index.json')
    receipt = load(root / 'collection.json')
    assert index['count'] == len(index['files']) == receipt['files'] == count
    assert index['bytes'] == sum(row['bytes'] for row in index['files']) == receipt['bytes'] == byte_count
    assert receipt['status'] == 'COMPLETE'
    expected = {}
    for row in index['files']:
        assert row['path'] == 'payload/' + row['name'] and row['name'] not in expected
        data = read(root / row['path'])
        assert (len(data), sha(data)) == (row['bytes'], row['sha256'])
        expected[row['name']] = {'bytes': len(data), 'sha256': sha(data)}
    assert {str(p.relative_to(root / 'payload')) for p in regular_files(root / 'payload')} == set(expected)
    transport = tar_audit(root / '.collection/copy.tar', expected)
    assert transport['sha256'] == receipt['archive_sha256']
    return {'source': str(root), 'payload_files': count, 'payload_bytes': byte_count,
            'index_sha256': sha(read(root / 'copy-index.json')), 'transport': transport}


def relative(path):
    if str(path) in standalone:
        return standalone[str(path)]
    found = [(root, target) for root, target in trees.items() if path.is_relative_to(root)]
    assert len(found) == 1, str(path)
    root, target = found[0]
    return target + '/' + str(path.relative_to(root))


def copy(path, name):
    data = read(path)
    encoded = data
    encoding = 'identity'
    if len(data) >= 65536 and path.suffix not in ('.o', '.elf', '.ko'):
        encoded = gzip.compress(data, compresslevel=9, mtime=0)
        assert gzip.decompress(encoded) == data
        name += '.gz'
        encoding = 'gzip'
    target = DRAFT / name
    assert not target.exists(), str(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    copied.append({'source': str(path), 'source_identity': origins[str(path)][0],
                   'raw_bytes': len(data), 'raw_sha256': sha(data), 'path': name,
                   'encoding': encoding, 'stored_bytes': len(encoded), 'stored_sha256': sha(encoded)})


assert not DRAFT.exists()
manifest_bytes = read(MANIFEST)
assert sha(manifest_bytes) == '549ca59b3b3178623fc4d784168f17fd2bf3d5ab917cdbbc6ff1d6f5150b6997'
manifest = json.loads(manifest_bytes)
assert manifest['count'] == len(manifest['files']) == 450
assert manifest['bytes'] == sum(row['bytes'] for row in manifest['files']) == 32949760
assert manifest['final_conditional_native_premise_accepted'] is False
assert {row['path'] for row in manifest['directories']} == set(trees)
assert set(manifest['standalone_files']) == set(standalone)
paths = {row['path']: row for row in manifest['files']}
assert len(paths) == 450
for root, target in trees.items():
    actual = regular_files(Path(root))
    assert {str(p) for p in actual} == {name for name in paths if Path(name).is_relative_to(root)}
for path, row in paths.items():
    data = read(Path(path))
    assert (len(data), sha(data), identity(Path(path))) == (row['bytes'], row['sha256'], row['identity']), path
audit = {'format': 'kdlock.aux-archive-byte-audit.v1',
         'scope': 'Standard-library sourcehost byte, hash, tar and exact metadata inspection only. No project imports, builds, behavioral tests, provider activation or VM workload.',
         'raw_manifest_sha256': sha(manifest_bytes), 'raw_manifest_files': 450, 'raw_manifest_bytes': 32949760}
audit['collections'] = [collection_audit(Path('/tmp/kdlock-kernel8-aux-context-source-20261111-01'), 11, 693911),
                        collection_audit(Path('/tmp/kdlock-kernel8-aux-context-source-20261111-02'), 3, 61753),
                        collection_audit(Path('/tmp/kdlock-kernel8-aux-object-capture-collection-20261111-02'), 292, 9569064)]
capture_root = Path('/tmp/kdlock-kernel8-aux-object-capture-collection-20261111-02/payload/capture')
capture_bytes = read(capture_root / 'result.json')
assert sha(capture_bytes) == '5a49b6efa7f3c21201508cdbd724fa9da1d22aa03439e2d856dddb54406873f7'
capture = json.loads(capture_bytes)
assert capture['status'] == 'READ_ONLY_OBJECT_CAPTURE_COMPLETE' and capture['command_count'] == len(capture['commands']) == 144
for row in capture['commands']:
    assert row['returncode'] == 0 and row['output_capacity_exceeded'] is False
    for kind in ('stdout', 'stderr'):
        data = read(capture_root / row[kind])
        assert (len(data), sha(data)) == (row[kind + '_bytes'], row[kind + '_sha256'])
conditional_path = Path('/tmp/kdlock-kernel8-narrow-aux-stack-budget-20261111-04.json')
conditional_bytes = read(conditional_path)
assert sha(conditional_bytes) == 'bdcab02965bc43fb2134e5ef13087a0ecec92ee9fbfaef98ae62b657a8bf35b2'
conditional = json.loads(conditional_bytes)
assert conditional['native_budget_premise_accepted'] is False and conditional['conditional_budget']['aux_flag_set'] is False
assert conditional['conditional_budget']['bytes'] == 44024
assert 27 * (392 + 16) + 32 + 48 + 16 + 144 + 2 * 16384 == 44024
assert conditional['conditional_budget']['proposed_required_control_bytes'] == 65536
assert conditional['conditional_budget']['proposed_auxiliary_bytes'] == 131072
assert conditional['conditional_budget']['margin_within_declared_control_bytes'] == 21512
assert conditional['cancellation_witness_compiled_overcount_bytes'] == 3064
assert conditional['cancellation_witness_including_alternatives_overcount_bytes'] == 3304
assert sum(row['conservative_bytes'] for row in conditional['cancellation_witness']) == 3064
assert all(row['measured'] is False for row in conditional['explicit_external_premises'])
weights_path = Path('/tmp/kdlock-kernel8-aux-stack-weights-20261111-04.json')
weights = load(weights_path)
assert weights['parser_sha256'] == sha(read(Path('/tmp/kdlock-kernel8-stack-weights-20261111.py'))) == '0e5f7f7fc0d0c6debbd19885b0cc9bbffaedaf0a91cd4e1c5136da00d969fba9'
assert sha(read(weights_path)) == 'd1c66e94efed9670ecd2a4a541f8437fa7547064434e703eca7a687bde0a1078'
admission_bytes = read(ADMISSION)
assert sha(admission_bytes) == 'db233cd8ac3164d3170c071ecc7081c9e58141f93cbf0b147f700dab761f5a1b'
admission = json.loads(admission_bytes)
assert admission['status'] == 'USER_SELECTED_EXPERIMENTAL_NATIVE_PREMISE'
assert admission['native_segments_measured'] is False and admission['full_auxiliary_stack_requirement_proved'] is False
assert admission['full_native_callback_tree_measured'] is False
assert admission['independent_reviews']['conditional_budget_sha256'] == sha(conditional_bytes)
assert (admission['conditional_total_bytes'], admission['required_control_bytes'], admission['auxiliary_bytes']) == (44024, 65536, 131072)
audit['object_inspection'] = {'receipt_sha256': sha(capture_bytes), 'commands': 144, 'all_returned_zero': True,
                              'inspection_outputs_hash_matched': 288, 'stack_bound_established_by_capture': capture['stack_bound_established']}
audit['conditional_analysis'] = {'sha256': sha(conditional_bytes), 'bytes': 44024, 'control_bytes': 65536,
                                'auxiliary_bytes': 131072, 'margin_bytes': 21512, 'false_flags_preserved': True,
                                'native_segments_measured': False}
audit['experimental_admission'] = {'sha256': sha(admission_bytes), 'status': admission['status'],
                                  'scope': 'Separate user-selected experimental premise. No actual MM dispatch input receipt, activation or execution is established here.',
                                  'full_auxiliary_requirement_proved': False, 'native_callback_tree_measured': False}
DRAFT.mkdir()
for path in sorted(paths):
    copy(Path(path), relative(Path(path)))
copy(MANIFEST, 'input-manifest.json')
copy(ADMISSION, 'experimental-admission/user-premise.json')
copy(Path(__file__), 'archive-copy.py')
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
                         'gzip_files': sum(row['encoding'] == 'gzip' for row in copied), 'complete_transports_omitted': 0}
audit['object_binary_paths'] = [row['path'] for row in copied if row['path'].endswith(('.o', '.ko'))]
for name, value in (('copy-index.json', {'format': 'kdlock.lossless-file-copy.v1', 'files': copied}), ('audit.json', audit)):
    (DRAFT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
print(json.dumps({'draft': str(DRAFT), 'copy_summary': audit['copy_summary'], 'object_binary_paths': audit['object_binary_paths'],
                  'audit_sha256': sha((DRAFT / 'audit.json').read_bytes()),
                  'copy_index_sha256': sha((DRAFT / 'copy-index.json').read_bytes())}, sort_keys=True))
