"""Offline association of captured compiler/upload bytes with one ABI2 row.

This module never opens a provider, queries a registry, waits, or retries. The
caller supplies the result of its already scheduled observation. Generation
association follows the immutable ABI2 publication contract in the frozen source;
it is neither a kernel byte digest nor a returned-body witness.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct


MAX_RECORDS = 64
MAX_FILE = 8 * 1024 * 1024
MAX_IMAGE = 4 * 1024 * 1024
U64_MAX = (1 << 64) - 1
KEY = ('pid', 'tgid', 'entry', 'lock_kind', 'entry_abi')


def require(condition, message):
    if not condition:
        raise ValueError('provenance: ' + message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(root, relative, files, limit=MAX_FILE):
    """Read bounded regular evidence, retaining exact bytes for later copying."""
    require(type(relative) is str, 'non-text evidence path')
    path = Path(relative)
    require(not path.is_absolute() and str(path) == relative and path.parts and
            all(part not in ('.', '..') for part in path.parts), 'invalid evidence path')
    target = root
    for part in path.parts:
        target = target / part
        require(not target.is_symlink(), 'evidence path is a symbolic link')
    require(target.is_file() and target.stat().st_size <= limit, 'missing or oversized ' + relative)
    with target.open('rb') as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, 'evidence grew beyond its bound')
    require(relative not in files or files[relative] == data, 'evidence changed while reading')
    files[relative] = data
    return data


def record(root, relative, files):
    def distinct(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON field')
            result[key] = value
        return result
    value = json.loads(read(root, relative, files), object_pairs_hook=distinct)
    require(type(value) is dict and value.get('schema') == 1, 'unsupported record schema')
    return value


def artifact(root, directory, value, files, limit=MAX_FILE):
    require(type(value) is dict and type(value.get('bytes')) is int,
            'missing artifact identity')
    data = read(root, str(Path(directory) / value['path']), files, limit)
    require(len(data) == value['bytes'] and digest(data) == value.get('sha256'),
            'artifact bytes differ')
    return data


def associate(root, observation, expected, required):
    """Return a verified chain and its captured files; perform no live reads."""
    root, files = Path(root), {}
    require(root.is_dir() and not root.is_symlink(), 'evidence root unavailable')
    session = record(root, 'session.json', files)
    require(observation.get('schema') == 1 and observation.get('clock') == 'CLOCK_MONOTONIC',
            'observation clock/schema differs')
    start, end = observation.get('read_start_ns'), observation.get('read_end_ns')
    require(type(start) is int and type(end) is int and 0 < start <= end,
            'invalid observation interval')
    require(session.get('boot_id') == observation.get('boot_id') == expected['boot_id'] and
            session.get('entry') == required['entry'], 'boot or selected entry differs')
    require(observation.get('observer') == expected['preparer'], 'observation process differs')
    daemon, writer = expected['daemon'], expected['daemon']['device_writer']
    observed_daemon = session['daemon']
    require(all(observed_daemon.get(key) == writer[key] for key in
                ('pid', 'start_ticks', 'fd', 'device', 'inode', 'rdev', 'flags')) and
            observed_daemon['pid'] == daemon['pid'] and
            observed_daemon['start_ticks'] == daemon['start_ticks'],
            'retained daemon descriptor differs')
    rows = observation['registry']
    require(rows == expected['registry'], 'observation differs from fixed receipt')
    targets = [row for row in rows if row['entry'] == required['entry']]
    require(len(targets) == 1, 'selected registry row is ambiguous')
    row = targets[0]
    require(row['lock_kind'] == row['entry_abi'] == 2 and row['status'] == 0 and
            type(row['generation']) is int and 0 < row['generation'] <= U64_MAX and row['code'] > 0,
            'selected image is not ready immutable ABI2')

    directories = sorted(root.glob('upload-*'))
    require(0 < len(directories) <= MAX_RECORDS, 'upload inventory is empty or exceeds bound')
    candidates = []
    for directory in directories:
        require(directory.is_dir() and not directory.is_symlink() and
                re.fullmatch(r'upload-[1-9][0-9]*', directory.name), 'invalid upload directory')
        upload = record(root, directory.name + '/receipt.json', files)
        require(upload['session_id'] == session['session_id'] and
                directory.name == 'upload-' + str(upload['upload_id']), 'upload session/id differs')
        if (upload.get('upload_complete') is True and
                upload.get('base_generation') == row['generation'] - 1 and
                upload.get('entry', {}).get('entry') == row['entry']):
            candidates.append((directory.name, upload))
    require(len(candidates) == 1, 'matching completed upload is missing or ambiguous')
    upload_dir, upload = candidates[0]
    require(upload.get('evidence_complete') is True and
            all(upload['entry'].get(key) == row[key] for key in KEY) and
            upload['requirements'] == row['requirements'], 'upload identity/evidence differs')
    base = upload['base_generation']
    require(type(base) is int and 0 <= base < U64_MAX and base + 1 == row['generation'],
            'immutable generation association differs')
    completed = upload.get('final_write_end_ns')
    require(type(completed) is int and 0 < completed <= start, 'upload overlaps or follows observation')
    require(type(upload['image_length']) is int and
            64 <= upload['image_length'] <= MAX_IMAGE and
            upload['accepted_length'] == upload['image_length'], 'incomplete payload coverage')
    require(upload['payload'] == upload_dir + '/payload.bin', 'unexpected payload location')
    payload = read(root, upload['payload'], files, MAX_IMAGE)
    require(len(payload) == upload['image_length'], 'payload mirror length differs')

    attempt = upload.get('compile_attempt_id')
    require(type(attempt) is int and 0 < attempt <= MAX_RECORDS, 'compiler attempt unavailable')
    compile_dir = 'compile-' + str(attempt)
    manifest_path = compile_dir + '/manifest.json'
    manifest = record(root, manifest_path, files)
    manifest_digest = digest(files[manifest_path])
    sidecar = read(root, compile_dir + '/manifest.sha256', files, 65).decode('ascii').strip()
    require(manifest_digest == upload.get('manifest_sha256') == sidecar,
            'cached compiler manifest differs')
    context = record(root, compile_dir + '/context.json', files)
    require(manifest['context'] == context and context['session_id'] == session['session_id'] and
            context['compile_attempt_id'] == attempt and
            all(context['entry'].get(key) == row[key] for key in KEY) and
            context['entry']['base_generation'] == base and
            manifest.get('complete') is True and manifest.get('evidence_complete') is True,
            'compiler attempt or completeness differs')
    require(manifest.get('context_validated') is True and
            manifest.get('context_sha256') == digest(files[compile_dir + '/context.json']) and
            manifest.get('errors') == [] and not manifest.get('errors_truncated'),
            'compiler context or recording failed')
    translation = manifest['translation']
    require(translation['pid'] == row['pid'] and translation['entry'] == row['entry'] and
            translation['lock_kind'] == 'mutex' and translation['entry_abi'] == 2 and
            translation['trusted_source'] is True, 'translation arguments differ')
    require(manifest['binary']['bytes'] == len(payload) and
            manifest['binary']['sha256'] == digest(payload), 'compiler output differs from sent bytes')
    require(payload[9:16] == b'KDWB002' and payload[25:32] == b'KDWC002' and
            payload[41:45] == b'KDAB' and payload[45] == 2 and payload[46] == 3 and
            upload['protocol'] == 3 and payload[47] == (row['requirements'] & 255) and
            struct.unpack_from('<I', payload, 48)[0] == row['requirements'] and
            row['requirements'] & (1 << 14), 'payload contract differs')
    require(bytes.fromhex(manifest['binary']['header_hex']) == payload[:64],
            'captured compiler header differs')
    caps = manifest['capabilities']
    raw = bytes.fromhex(caps['raw_hex'])
    require(caps.get('validated') is True and caps.get('result') == 0 and len(raw) == 16,
            'compiler capability response unvalidated')
    version, features, stack, percpu = struct.unpack('<IIII', raw)
    require((version, features, stack, percpu) ==
            tuple(caps[key] for key in ('version', 'features', 'mutex_stack_bytes', 'percpu_module_bytes')) and
            version == 21 and features & 262144 and
            caps['parsed'].get('source_frontier_direction') is True,
            'compiler direction capability differs')
    descriptor = manifest['descriptor']
    require(descriptor.get('validated') is True and descriptor.get('inherited') is True and
            descriptor.get('relationship') == 'inherited_description_then_dup' and
            descriptor.get('inherited_fd') == writer['fd'] and
            descriptor['access_flags'] & os.O_ACCMODE == os.O_RDWR and
            descriptor['source_info']['state'] == 0 and caps['fd'] == descriptor['fd'],
            'compiler descriptor lineage differs')
    for name in ('opened', 'named', 'inherited_stat'):
        metadata = descriptor[name]
        require(stat.S_ISCHR(metadata['st_mode']) and
                (metadata['st_dev'], metadata['st_ino'], metadata['st_rdev']) ==
                (writer['device'], writer['inode'], writer['rdev']),
                'compiler device identity differs')
    compiler = manifest['compiler']
    require(compiler['ppid'] == daemon['pid'] and compiler['pid'] != daemon['pid'] and
            type(compiler['start_ticks']) is int and compiler['start_ticks'] > 0 and
            compiler['parent_start_ticks'] == daemon['start_ticks'] and
            compiler['interpreter']['sha256'] == expected['preparer']['executable_sha256'] and
            compiler['interpreter']['proc_exe'] == expected['preparer']['executable'],
            'compiler process lineage differs')
    assembly = artifact(root, compile_dir, manifest['assembly'], files)
    require(manifest['assembly'].get('unchanged_after_build') is True,
            'assembly changed during build')
    histories = manifest['histories']
    history = artifact(root, compile_dir, histories['callee_table.txt'], files)
    ij_history = artifact(root, compile_dir, histories['ij_table.txt'], files)
    require(all(histories[key].get('state') == 'read' for key in
                ('callee_table.txt', 'ij_table.txt')), 'compiler histories unavailable')
    for name, raw_history in (('callee_table.txt', history), ('ij_table.txt', ij_history)):
        normalized = raw_history.decode('ascii').replace('\r\n', '\n').replace('\r', '\n')
        require(histories[name]['parser_sha256'] == digest(normalized.encode('ascii')),
                'history parser input differs')
    table = manifest['service_table']
    require(table.get('mode') == 'paged' and table.get('validated') is True and
            table.get('state_before_hex') == table.get('state_after_hex') and
            type(table.get('generation')) is int and
            type(table.get('pages')) is list and len(table['pages']) == 8,
            'compiler service snapshot unavailable')
    table_state = bytes.fromhex(table['state_before_hex']).decode('ascii').split()
    require(len(table_state) == 3 and all(word.isdecimal() for word in table_state) and
            tuple(map(int, table_state)) == (table['generation'], table['slots'], table['active']) and
            0 <= table['generation'] <= 256 and 0 <= table['active'] <= table['slots'] <= 128,
            'compiler service state differs')
    pages = b''.join(artifact(root, compile_dir, page, files) for page in table['pages'])
    require(artifact(root, compile_dir, table['snapshot'], files) == pages,
            'compiler service snapshot differs')
    controls = manifest['controls']
    require(controls.get('mode') == 'read', 'compiler controls unavailable')
    artifact(root, compile_dir, controls['snapshot'], files)
    chain = dict(schema=1, claim='source-derived immutable ABI2 upload association',
        kernel_digest_reported=False, execution_proved=False,
        session_id=session['session_id'], compile_attempt_id=attempt,
        manifest_sha256=manifest_digest, upload_id=upload['upload_id'],
        payload_sha256=digest(payload), payload_bytes=len(payload),
        base_generation=base, observed_generation=row['generation'], registry=row,
        final_write_end_ns=completed, read_start_ns=start, read_end_ns=end)
    return chain, files, assembly, history


def capture(root, destination, observation, expected, required):
    """Freeze the verified selected records before creating the fixed receipt."""
    chain, files, _, _ = associate(root, observation, expected, required)
    destination = Path(destination)
    destination.mkdir()
    bound = {}
    for relative, data in files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        bound[str(target)] = digest(data)
    for name, value in (('observation.json', observation), ('association.json', chain)):
        data = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
        target = destination / name
        target.write_bytes(data)
        bound[str(target)] = digest(data)
    return bound
