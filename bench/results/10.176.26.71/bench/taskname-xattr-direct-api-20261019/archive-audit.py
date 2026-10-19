#!/usr/bin/env python3
"""Host-only independent audit of recorded direct-string image evidence.

Reads copied run files or archives; never extracts, imports or executes their
code. Git is read only at an explicitly selected commit. Requires independently
captured round kallsyms bytes and identity, not addresses chosen by an image
receipt. Old req4/8 evidence belongs to its original auditor and is unchanged.
"""
import argparse
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import tarfile


FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|'
                   r'hard LOCKUP|unable to handle|general protection fault|'
                   r'Oops:|\[ERROR\]|\[KD_JIT\]\[ERROR\]|invariant_failures=[1-9]', re.I)
SERVICES = {4: ('strcmp', 4), 5: ('strscpy_pad', 8)}
GRID = [*range(1, 9), *range(12, 61, 4)]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) in ('', '.'):
        raise ValueError('unsafe relative evidence path: ' + str(value))
    return str(path)


def wanted(path):
    return path.endswith(('.json', '.log', '/jit.S', '/jit.bin')) or \
        ('/loaded-images/' in path and path.endswith('.bin'))


class Evidence:
    def __init__(self, base, check):
        self.base, self.check = base, check
        self.hashes, self.sizes, self.data = {}, {}, {}
        self.archive_receipt = None
        self.archive_rows = []
        if (base / 'archives.json').exists():
            self.archives()
        else:
            self.directory()

    def consume(self, name, stream):
        sha, chunks, size = hashlib.sha256(), [], 0
        keep = wanted(name)
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
            size += len(chunk)
            if keep:
                chunks.append(chunk)
        self.hashes[name], self.sizes[name] = sha.hexdigest(), size
        if keep:
            self.data[name] = b''.join(chunks)

    def directory(self):
        # Never follow mutable workspace symlinks to a different source tree.
        for folder, directories, files in os.walk(self.base, followlinks=False):
            directories[:] = [name for name in directories if not (Path(folder) / name).is_symlink()]
            for name in files:
                path = Path(folder) / name
                if path.is_symlink() or not path.is_file():
                    continue
                relative = str(path.relative_to(self.base))
                with path.open('rb') as stream:
                    self.consume(relative, stream)

    def archives(self):
        receipt_bytes = (self.base / 'archives.json').read_bytes()
        receipt = json.loads(receipt_bytes)
        inventory_bytes = (self.base / 'input-inventory.json').read_bytes()
        inventory = json.loads(inventory_bytes)
        self.archive_receipt = receipt
        self.check(receipt.get('completed') is True and receipt.get('guest_idle') is True,
                   'archive receipt incomplete/undrained')
        self.check(digest(inventory_bytes) == receipt['input_inventory_sha256'], 'inventory hash mismatch')
        self.check(digest((self.base / 'archive_run.py').read_bytes()) == receipt['script_sha256'],
                   'archiver capture hash mismatch')
        prefix, seen = receipt['archive_prefix'] + '/', set()
        for group in receipt['groups']:
            path = self.base / safe_relative(group['file'])
            compressed_sha, compressed_size = hashlib.sha256(), 0
            with path.open('rb') as stream:
                while chunk := stream.read(1024 * 1024):
                    compressed_sha.update(chunk)
                    compressed_size += len(chunk)
            self.check(compressed_sha.hexdigest() == group['sha256'] and compressed_size == group['bytes'],
                       'compressed archive differs: ' + group['file'])
            self.archive_rows.append(dict(file=group['file'], sha256=compressed_sha.hexdigest(),
                                          bytes=compressed_size))
            with tarfile.open(path, 'r|gz') as archive:
                for member in archive:
                    self.check(member.name.startswith(prefix), 'unexpected archive prefix: ' + member.name)
                    name = safe_relative(member.name.removeprefix(prefix))
                    self.check(name not in seen, 'duplicate archive member: ' + name)
                    seen.add(name)
                    self.check(any(member.name == root or member.name.startswith(root + '/')
                                   for root in group['roots']), 'member outside group: ' + name)
                    item = inventory.get(name)
                    self.check(item is not None, 'member absent from inventory: ' + name)
                    if item is None:
                        continue
                    mode = stat.S_IFDIR if member.isdir() else stat.S_IFLNK if member.issym() else \
                        stat.S_IFREG if member.isfile() or member.islnk() else 0
                    self.check(mode == stat.S_IFMT(item['mode']) and member.mode == stat.S_IMODE(item['mode'])
                               and (member.uid, member.gid) == (item['uid'], item['gid']),
                               'archive type/mode/owner differs: ' + name)
                    self.check(abs(round(member.mtime * 1e9) - item['mtime_ns']) <= 256,
                               'archive mtime differs beyond tar precision: ' + name)
                    if member.isfile():
                        self.consume(name, archive.extractfile(member))
                        self.check(self.sizes[name] == item['bytes'] == member.size,
                                   'archive file length differs: ' + name)
                    elif member.issym():
                        self.check(member.linkname == item['link'], 'archive symlink differs: ' + name)
                    elif member.islnk():
                        target = safe_relative(member.linkname.removeprefix(prefix))
                        self.check(target in self.hashes, 'unsupported forward hardlink: ' + name)
                        if target in self.hashes:
                            self.hashes[name], self.sizes[name] = self.hashes[target], self.sizes[target]
                            self.check(self.sizes[name] == item['bytes'], 'hardlink size differs: ' + name)
                            if wanted(name):
                                self.check(target in self.data, 'hardlink evidence content unavailable: ' + name)
                                if target in self.data:
                                    self.data[name] = self.data[target]
        self.check(seen == set(inventory), 'archive/inventory membership differs')

    def read(self, path):
        return self.data[safe_relative(path)]

    def json(self, path):
        return json.loads(self.read(path))


def git_source_hashes(repo, commit, paths):
    tree = subprocess.run(['git', 'ls-tree', '-rz', commit], cwd=repo,
                          check=True, capture_output=True).stdout
    objects = {}
    for line in tree.split(b'\0'):
        if line:
            header, name = line.split(b'\t', 1)
            _, kind, oid = header.split()
            if kind == b'blob' and name.decode() in paths:
                objects[name.decode()] = oid.decode()
    needed = sorted(set(objects.values()))
    raw = subprocess.run(['git', 'cat-file', '--batch'], cwd=repo, check=True, capture_output=True,
                         input=('\n'.join(needed) + '\n').encode()).stdout if needed else b''
    content, position = {}, 0
    while position < len(raw):
        end = raw.index(b'\n', position)
        oid, kind, size = raw[position:end].split()
        if kind != b'blob':
            raise ValueError('unexpected Git object type')
        position = end + 1
        content[oid.decode()] = digest(raw[position:position + int(size)])
        position += int(size) + 1
    return {path: content[oid] for path, oid in objects.items()}


def parse_symbols(path, expected_hash, check):
    raw = path.read_bytes()
    check(digest(raw) == expected_hash, 'round symbol receipt differs from independently supplied SHA-256')
    receipt = json.loads(raw)
    check(receipt['schema'] == 1 and receipt['kernel_release'] == '6.1.159-kdclobber2'
          and receipt['boot_id'] and receipt['running_build_id'], 'incomplete round symbol/kernel identity')
    text = (path.parent / safe_relative(receipt['kallsyms_path'])).read_bytes()
    check(digest(text) == receipt['kallsyms_sha256'], 'round kallsyms subset hash differs')
    symbols = {}
    for line in text.decode().splitlines():
        fields = line.split()
        check(len(fields) == 3 and fields[2] in ('strcmp', 'strscpy_pad'),
              'unexpected round kallsyms line: ' + line)
        if len(fields) != 3 or fields[2] not in ('strcmp', 'strscpy_pad'):
            continue
        check(fields[2] not in symbols and fields[1].lower() == 't', 'ambiguous/non-text core API symbol')
        symbols[fields[2]] = int(fields[0], 16)
    check(set(symbols) == {'strcmp', 'strscpy_pad'} and all(symbols.values()), 'missing round API symbols')
    check(symbols == receipt['symbols'], 'parsed kallsyms symbols differ from round receipt')
    return receipt, symbols


def validate_image(upload, loaded, receipt, entry, requirement, symbols, check, name):
    check(64 <= len(upload) <= 640 * 1024 and upload[9:16] == b'KDWB002'
          and upload[25:32] == b'KDWC002'
          and upload[41:48] == b'KDAB\x01\x02' + bytes([requirement]),
          'wrong image ABI/publication/requirements: ' + name)
    check(b'KDAG0001' not in upload and upload.count(b'KDNC0001') == 1,
          'unexpected or duplicate image directory: ' + name)
    magic, start, count = struct.unpack_from('<8sII', upload, len(upload) - 16)
    if not (magic == b'KDNC0001' and 1 <= count <= 64 and start >= 48 and
            start + 16 * count == len(upload) - 16):
        raise ValueError('invalid direct-call footer: ' + name)
    base = receipt['base']
    check(0xffffffff80000000 < base < (1 << 64) - len(upload), 'invalid generated-code base: ' + name)
    check(entry['code'] == base and entry['entry_abi'] == 1 and entry['requirements'] == requirement
          and entry['pid'] == 0 and entry['lock_kind'] == 1
          and entry['entry'] == receipt['entry'] and entry['generation'] == receipt['generation'] > 0
          and entry['status'] == 0, 'registry/loaded-image identity differs: ' + name)
    check(receipt['requirements'] == requirement and receipt['bytes'] == len(upload) == len(loaded)
          and receipt['uploaded_sha256'] == digest(upload) and receipt['loaded_sha256'] == digest(loaded)
          and receipt['byte_for_byte_match'] is True, 'loaded-image receipt hashes differ: ' + name)
    expected, rows, occupied, seen = bytearray(upload), [], set(), 0
    for index in range(count):
        offset, service, continuation = struct.unpack_from('<IIQ', upload, start + index * 16)
        if service not in SERVICES:
            raise ValueError('unknown relocated service: ' + name)
        symbol, bit = SERVICES[service]
        check(requirement & bit and continuation != 0, 'invalid service/continuation: ' + name)
        check(48 <= offset <= start - 5 and upload[offset:offset + 5] == b'\xe8\0\0\0\0',
              'generated E8 slot invalid before relocation: ' + name)
        span = set(range(offset, offset + 5))
        check(not occupied & span, 'overlapping generated E8 slots: ' + name)
        occupied.update(span)
        displacement = symbols[symbol] - (base + offset + 5)
        if not -(1 << 31) <= displacement < (1 << 31):
            raise ValueError('relocation target outside rel32: ' + name)
        struct.pack_into('<i', expected, offset + 1, displacement)
        rows.append(dict(offset=offset, service=service, symbol=symbol, target=symbols[symbol],
                         continuation=continuation, displacement=displacement))
        seen |= bit
    check(seen == requirement & 12, 'missing or extra declared service effect: ' + name)
    check(loaded == bytes(expected), 'loaded bytes differ beyond exact independently reconstructed E8 operands: ' + name)
    check(receipt['relocations'] == rows, 'producer relocation receipt differs from independent decoding: ' + name)
    return dict(uploaded_sha256=digest(upload), loaded_sha256=digest(loaded), requirements=requirement,
                base=base, entry=entry['entry'], generation=entry['generation'], relocations=rows)


def verify_binaries(group, evidence, check):
    """Check required binary coverage and bytes, never resolve guest live paths."""
    plan = evidence.json(group + '/plan.json')
    arms = {row['arm'] for row in plan}
    rows = []
    if group == 'taskname':
        expected = {'build/guard/tc_allocator_guard.ko'}
        expected.update('build/' + safe_relative(row['variant']) + '/rwlock_bench.ko' for row in plan)
        if 'kdlock' in arms:
            expected.update(('build/provider/kernel_module/kdlock_km.ko', 'source/daemon/daemon'))
        if 'tclock' in arms:
            expected.add('build/tclock/tclock_backend_km.ko')
        manifest = evidence.json(group + '/binary-sha256.json')
        for original, sha in manifest.items():
            matches = [relative for relative in expected if original.endswith('/' + relative)]
            check(len(matches) == 1, 'unexpected/ambiguous taskname binary: ' + original)
            if len(matches) == 1:
                rows.append((original, matches[0], sha))
        check({relative for _, relative, _ in rows} == expected and len(rows) == len(expected),
              'taskname binary manifest is missing/duplicating required binaries')
    else:
        manifest = evidence.json(group + '/binaries.json')
        expected = {'client', 'daemon', 'kdlock_km.ko', 'tc_allocator_guard.ko',
                    'tclock_backend_km.ko',
                    *(arm + '-xattr/real_api.ko' for arm in ('native', 'tclock', 'kdlock'))}
        check(expected <= set(manifest), 'xattr binary manifest is missing required binaries')
        for name, item in manifest.items():
            relative = 'build/' + safe_relative(name)
            check(item['path'].endswith('/' + relative), 'binary original path differs from its key: ' + name)
            rows.append((item['path'], relative, item['sha256']))
    roots = {original[:-len(relative)] for original, relative, _ in rows}
    check(len(roots) == 1, 'binary manifest combines different or empty run roots: ' + group)
    for _, relative, sha in rows:
        check(evidence.hashes.get(group + '/' + relative) == sha,
              'binary bytes differ: ' + group + '/' + relative)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repo', type=Path, default=Path('/home/eric/vm/vm-shared/kdlock'))
    parser.add_argument('--commit', required=True, help='independently chosen exact 40-hex implementation commit')
    parser.add_argument('--round-symbols', type=Path, required=True)
    parser.add_argument('--symbols-sha256', required=True)
    parser.add_argument('--allowed-guest-only', type=Path,
                        help='explicit JSON map of permitted extra source paths to exact SHA-256')
    parser.add_argument('--replay-relative', default='replay-final/replay.json')
    parser.add_argument('--replay-script', help='Git-relative replay script whose captured SHA-256 must match')
    parser.add_argument('--full-grid', action='store_true', help='require all567 uninstrumented main sessions and replay')
    args = parser.parse_args()
    base, out = args.base.resolve(), args.output.resolve()
    if out.exists() or out == base or base in out.parents:
        parser.error('use a new output file outside original evidence')
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit) or not re.fullmatch(r'[0-9a-f]{64}', args.symbols_sha256):
        parser.error('explicit full commit and symbol SHA-256 are required')
    if args.full_grid and not args.replay_script:
        parser.error('--full-grid requires --replay-script to bind the replay implementation')
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    evidence = Evidence(base, check)
    symbol_receipt, symbols = parse_symbols(args.round_symbols.resolve(), args.symbols_sha256, check)
    manifests, all_sources = {}, {}
    for path in sorted(evidence.hashes):
        if not path.endswith('/source-sha256.json'):
            continue
        group = path.removesuffix('/source-sha256.json')
        # A main run has top-level taskname/xattr build roots; ignore any
        # historical helper inputs archived inside its source/results tree.
        if '/' in group or group not in ('taskname', 'xattr'):
            continue
        manifests[group] = evidence.json(path)
        for source, sha in manifests[group].items():
            source = safe_relative(source)
            check(evidence.hashes.get(group + '/source/' + source) == sha, 'frozen source bytes differ: ' + group + '/' + source)
            check(source not in all_sources or all_sources[source] == sha, 'source differs between workload groups: ' + source)
            all_sources[source] = sha
    check(bool(manifests), 'no supported source manifests')
    replay_path = safe_relative(args.replay_relative)
    replay = evidence.json(replay_path) if replay_path in evidence.hashes else None
    reference_paths = set(all_sources) | (set(replay.get('dependency_sha256', {})) if replay else set())
    if args.replay_script:
        reference_paths.add(safe_relative(args.replay_script))
    reference = git_source_hashes(args.repo, args.commit, reference_paths)
    allowed = json.loads(args.allowed_guest_only.read_text()) if args.allowed_guest_only else {}
    for path, sha in all_sources.items():
        check(reference.get(path, allowed.get(path)) == sha, 'source differs from selected Git/exact-extra policy: ' + path)
    binary_count = sum(verify_binaries(group, evidence, check) for group in manifests)
    if args.full_grid:
        check(replay is not None and replay.get('complete') is True, 'missing/incomplete main replay')
    if replay:
        check(replay.get('schema') == 2 and replay['round_symbols']['sha256'] == args.symbols_sha256
              and replay['round_symbols']['receipt'] == symbol_receipt
              and replay['round_symbols']['symbols'] == symbols
              and replay['round_symbols']['kallsyms_sha256'] == symbol_receipt['kallsyms_sha256']
              and replay['round_symbols']['kallsyms_path'] == symbol_receipt['kallsyms_path'],
              'replay symbol capture/schema differs from independent round evidence')
        if args.replay_script:
            check(reference.get(args.replay_script) == replay['script_sha256'], 'replay script differs from selected Git')
        for dependency, sha in replay.get('dependency_sha256', {}).items():
            check(reference.get(dependency) == sha and all_sources.get(dependency) == sha,
                  'replay dependency differs from Git/frozen source: ' + dependency)
        for group, run in replay['runs'].items():
            check(run['source_sha256'] == manifests.get(group), 'replay source manifest differs: ' + group)
            check(run['source_id'] == digest(json.dumps(run['source_sha256'], sort_keys=True,
                                                        separators=(',', ':')).encode()),
                  'replay source identity differs from its manifest: ' + group)
            for path, sha in run['input_sha256'].items():
                check(evidence.hashes.get(group + '/' + safe_relative(path)) == sha, 'replay input differs: ' + group + '/' + path)
    if 'health.json' in evidence.hashes:
        health = evidence.json('health.json')
        check(health['idle'] is True and health['boot_id'] == symbol_receipt['boot_id']
              and health['kernel_release'] == symbol_receipt['kernel_release'], 'health and round symbol identity differ')
        check(not health.get('per_session_kernel_faults'), 'health reports a session kernel fault')
        if replay:
            check(health['replay_sha256'] == evidence.hashes[replay_path], 'health/replay hash differs')
        if args.full_grid:
            check(health['completed_sessions'] == health['per_session_kernel_logs'] == 567,
                  'health full-matrix session counts differ')
    elif args.full_grid:
        check(False, 'main health receipt absent')
    if evidence.archive_receipt:
        check(evidence.archive_receipt['boot_id'] == symbol_receipt['boot_id'], 'archive/symbol boot ID differs')
        check(evidence.archive_receipt['health_sha256'] == evidence.hashes.get('health.json'),
              'archive/health hash differs')
    for group in manifests:
        identity_path = group + ('/baseline.json' if group == 'taskname' else '/kernel-identity.json')
        check(evidence.json(identity_path).get('running_build_id') == symbol_receipt['running_build_id'],
              'kernel Build ID and round symbols differ: ' + group)

    sessions, image_rows, identities = [], [], set()
    referenced_loaded, referenced_publications = set(), set()
    for group in manifests:
        plan, records = evidence.json(group + '/plan.json'), evidence.json(group + '/records.json')
        plan_map, record_map = {row['name']: row for row in plan}, {row['name']: row for row in records}
        check(len(plan_map) == len(plan) == len(records) == len(record_map) and set(plan_map) == set(record_map),
              'plan/records membership differs: ' + group)
        replay_map = {row['name']: row for row in replay['runs'][group]['sessions']} if replay else {}
        if replay:
            check(set(replay_map) == set(plan_map), 'replay session membership differs: ' + group)
        for name, planned in plan_map.items():
            stem = group + '/' + safe_relative(name) + '/'
            row = evidence.json(stem + 'session.json')
            check(all(record_map[name].get(key) == value for key, value in row.items()) and
                  all(row.get(key) == value for key, value in planned.items()), 'session/plan/record differs: ' + stem)
            check(row['execution_status'] == 'OK' and row['drained'] is True, 'session failed/undrained: ' + stem)
            check(not any(row.get(key) for key in ('diagnostic', 'pmu', 'perf_record'))
                  and row.get('score_eligible') is not False, 'instrumented session cannot enter this audit: ' + stem)
            if args.full_grid:
                check(not row.get('functional') and row['duration_ms'] == 2000 and row['collector_cpu'] == 63
                      and row['cpus'] == list(range(row['threads'])), 'main duration/placement differs: ' + stem)
                if group == 'taskname':
                    check(row['write_percent'] == 0 and row['post_work_rounds'] == 4,
                          'main taskname payload differs: ' + stem)
                if group == 'xattr' or row['arm'] == 'kdlock':
                    check(row['helper_waves'] == 8 and row['helper_cpus'] == list(range(16)),
                          'main helper preparation differs: ' + stem)
            measurement = row['measurement']
            check(measurement['completed'] == sum(worker['completed'] for worker in measurement['workers']) > 0
                  and all(worker['completed'] > 0 for worker in measurement['workers']), 'invalid worker progress: ' + stem)
            check(measurement.get('ok', True) and measurement.get('data_ok', True) and measurement.get('complete', True),
                  'failed business/measurement oracle: ' + stem)
            check(evidence.json(stem + 'measure.json') == {key: value for key, value in measurement.items() if key != 'peak'},
                  'raw measurement differs: ' + stem)
            log = evidence.read(stem + 'kernel.log').decode(errors='replace')
            check(not FAULT.search(log), 'kernel fault marker: ' + stem)
            case = 'taskname' if group == 'taskname' else f"xattr-{row['query']}-n{row['entries']}-v{row['value_size']}"
            identity = (case, row['arm'], row['threads'], row['repeat'])
            check(identity not in identities, 'duplicate experiment identity: ' + repr(identity))
            identities.add(identity)
            if replay:
                recorded = replay_map[name]
                check(recorded['valid'] is True and recorded['completed'] == measurement['completed'] and
                      recorded['jit_entries'] == row['jit_bodies'] and recorded['jit_completions'] == row['jit_completions']
                      and recorded['jit_status'] == row['jit_status'] and
                      recorded['source_id'] == replay['runs'][group]['source_id'], 'replay outcome differs: ' + stem)
            sessions.append(dict(path=stem + 'session.json', case=case, arm=row['arm'], threads=row['threads'],
                                 repeat=row['repeat'], completed=measurement['completed'], jit_status=row['jit_status'],
                                 jit_entries=row['jit_bodies'], jit_completions=row['jit_completions']))
            if row['arm'] != 'kdlock':
                check(row['jit_bodies'] == row['jit_completions'] == 0, 'non-KD arm reports JIT: ' + stem)
                continue
            entries, completions = row['jit_bodies'], row['jit_completions']
            check(0 <= completions <= entries <= measurement['completed'], 'invalid JIT witnesses: ' + stem)
            check(row['jit_status'] == ('PASS' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT'),
                  'JIT status differs from returned-body counts: ' + stem)
            check(row.get('address_guard_exits') == 0 and row.get('retired') ==
                  dict(frames=0, modules=0, state=2, writers=0), 'KD guard/drain evidence differs: ' + stem)
            before, after = row['published_before'], row['published_after']
            check(before == after, 'measured publication/readback changed: ' + stem)
            measured_captured = False
            for publication in row['publications']:
                begin, end = row['entry_range']
                check(begin < end and begin <= publication['entry']['entry'] < end,
                      'publication belongs to another original critical section: ' + stem)
                folder = safe_relative(publication['path'])
                for filename, sha in publication['images'].items():
                    path = stem + folder + '/' + safe_relative(filename)
                    check(evidence.hashes.get(path) == sha, 'saved publication hash differs: ' + path)
                image_path, assembly_path = stem + folder + '/jit.bin', stem + folder + '/jit.S'
                referenced_publications.add(image_path)
                assembly = evidence.read(assembly_path)
                check(b'kd_address_guard_failed_' not in assembly and b'kd_entry_guard' not in assembly,
                      'unexpected pointer/stack guard in direct API image: ' + image_path)
                loaded = publication['loaded_image']
                loaded_path = stem + safe_relative(loaded['path'])
                loaded_receipt = loaded_path.removesuffix('.bin') + '.json'
                referenced_loaded.add(loaded_path)
                check(evidence.json(loaded_receipt) == loaded, 'inline/disk loaded-image receipt differs: ' + loaded_path)
                result = validate_image(evidence.read(image_path), evidence.read(loaded_path), loaded,
                    publication['entry'], 24 if group == 'taskname' else 20, symbols, check, image_path)
                measured = (publication['entry'] == before['entry'] and publication['images'] == before['images'])
                if measured:
                    measured_captured = True
                    check(loaded == before['loaded_image'], 'measured readback not bound to saved publication: ' + stem)
                    if replay:
                        covered = replay['runs'][group]['input_sha256']
                        for path in (image_path, assembly_path, loaded_path, loaded_receipt):
                            check(covered.get(path.removeprefix(group + '/')) == evidence.hashes[path],
                                  'measured generated/loaded evidence absent from replay: ' + path)
                image_rows.append(dict(path=image_path, loaded_path=loaded_path, measured=measured, **result))
            check(measured_captured, 'no saved measured direct image: ' + stem)
            daemon = evidence.read(stem + 'daemon.log')
            check(b'ADDRESS_GUARDED_ADMISSION' not in daemon and b'ENTRY_GUARDED_ADMISSION' not in daemon,
                  'unexpected guarded admission: ' + stem)
    actual_loaded = {path for path in evidence.hashes if '/loaded-images/' in path and path.endswith('.bin')}
    check(actual_loaded == referenced_loaded, 'loaded-image evidence membership differs')
    actual_publications = {path for path in evidence.hashes if '/publications/' in path and path.endswith('/jit.bin')}
    check(actual_publications == referenced_publications, 'publication evidence membership differs')
    if args.full_grid:
        expected = {(case, arm, workers, repeat) for case in
                    ('taskname', 'xattr-tail-n16-v64', 'xattr-tail-n128-v64')
                    for arm in ('native', 'tclock', 'kdlock') for workers in GRID for repeat in range(3)}
        check(identities == expected and len(sessions) == 567, 'standard full matrix membership differs')
        check(sum(path.endswith('/kernel.log') for path in evidence.hashes) == 567,
              'main kernel-log membership differs')
    result = dict(schema=1, complete=not errors, discrepancies=errors,
        audited_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), base=str(base),
        implementation_commit=args.commit, round_symbols_sha256=args.symbols_sha256,
        symbol_identity={key: symbol_receipt[key] for key in ('boot_id', 'kernel_release', 'running_build_id')},
        archives=evidence.archive_rows, source_files=len(all_sources),
        git_source_files=sum(path in reference for path in all_sources),
        binary_files=binary_count, sessions=sessions, images=image_rows,
        unique_loaded_images=len(referenced_loaded), full_grid_required=args.full_grid,
        replay_verified=replay is not None, audit_script_sha256=digest(Path(__file__).read_bytes()),
        limits=['Offline integrity/recorded-evidence audit, not fresh execution or a proof of source ownership.',
                'Only generated E8 operands are relocated; original helper code/arguments are never inspected.',
                'Round symbols are independently supplied captured evidence, bound to explicit hash and kernel identity.',
                'Returned-body counters are checked separately from publication; NO_JIT is not delegation acceptance.',
                'Partial/failing diagnostic experiments and old req4/8 images require their separate audit scope.',
                'Archive extraction and archived code imports/execution are forbidden; forward hardlinks fail closed.',
                'This does not rerun the replay estimator, compare performance cohorts, or prove whole-kernel compatibility.'])
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(output=str(out), complete=result['complete'], errors=len(errors),
                          sessions=len(sessions), images=len(image_rows), loaded_images=len(referenced_loaded))))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
