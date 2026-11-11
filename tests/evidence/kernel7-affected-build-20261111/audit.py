#!/usr/bin/env python3
"""Saved-file-only kernel7 affected-build receipt audit using the standard library.

This reads archives as data, never imports source, parses Python or executes a
project command. The report is separate from the immutable original receipts.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def safe(name):
    value = PurePosixPath(name)
    require(name == str(value) and not value.is_absolute() and '..' not in value.parts, 'unsafe relative name')
    return value


def document(path):
    return json.loads(path.read_text())


def facts(path):
    require(path.is_file() and not path.is_symlink(), 'regular retained file required: ' + str(path))
    return {'bytes': path.stat().st_size, 'sha256': sha(path)}


def tar_members(path, maximum=8 * 1024**2):
    files, directories = {}, set()
    with tarfile.open(path, 'r:') as archive:
        for member in archive:
            name = member.name.rstrip('/') if member.isdir() else member.name
            safe(name)
            require(name not in files and name not in directories, 'duplicate archive member')
            if member.isdir():
                directories.add(name)
                continue
            require(member.isfile() and 0 <= member.size <= maximum, 'nonregular/oversize archive member')
            with archive.extractfile(member) as stream:
                data = stream.read(member.size + 1)
            require(len(data) == member.size, 'archive member extent differs')
            files[name] = {'bytes': member.size, 'sha256': hashlib.sha256(data).hexdigest(), 'mode': member.mode}
    ancestors = {str(parent) for name in files for parent in PurePosixPath(name).parents if str(parent) != '.'}
    require(directories <= ancestors, 'archive directory is not an actual regular-member ancestor')
    return files, directories


def check_command_logs(root, receipt, expected):
    rows = receipt['commands']
    require([(row['label'], row['returncode']) for row in rows] == expected, 'actual command disposition differs')
    for row in rows:
        require(sha(root / (row['label'] + '.log')) == row['log_sha256'], 'saved command log differs')
    return [{'label': row['label'], 'returncode': row['returncode'], 'log_sha256': row['log_sha256'],
             'elapsed_seconds': row['elapsed_seconds']} for row in rows]


def audit(root):
    root = root.resolve(strict=True)
    regular = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'collection symlink refused')
        if path.is_dir():
            continue
        require(stat.S_ISREG(path.stat().st_mode), 'nonregular collection object refused')
        relative = str(path.relative_to(root))
        safe(relative)
        regular[relative] = facts(path)
    index, collection = document(root / 'copy-index.json'), document(root / 'collection.json')
    require(index['count'] == collection['files'] == len(index['files']) == 225 and
            index['bytes'] == collection['bytes'] == 11693491 and collection['status'] == 'COMPLETE',
            'closed225-file collection extent differs')
    before = document(root / '.collection/inventory-before.json')
    after = document(root / '.collection/inventory-after.json')
    require(before['count'] == after['count'] == 225 and before['bytes'] == after['bytes'] == 11693491 and
            before['files'] == after['files'] and before['directories'] == after['directories'],
            'before/after guest inventory differs')
    by_name = {}
    for row in index['files']:
        safe(row['name']); safe(row['path'])
        require(row['path'] == 'payload/' + row['name'] and row['name'] not in by_name,
                'copy index path/duplicate differs')
        require(regular[row['path']] == {key: row[key] for key in ('bytes', 'sha256')}, 'copied payload differs')
        inventory = before['files'][row['name']]
        require(inventory == {'bytes': row['bytes'], 'identity': row['identity'], 'path': row['guest_path'],
                              'sha256': row['sha256']} and stat.S_ISREG(row['identity'][2]),
                'copy index differs from original guest inode/hash inventory')
        by_name[row['name']] = row
    require({name.removeprefix('payload/') for name in regular if name.startswith('payload/')} == set(by_name),
            'payload membership differs')
    transport = root / '.collection/copy.tar'
    require(sha(transport) == collection['archive_sha256'], 'raw collection transport differs')
    transported, directories = tar_members(transport)
    require(not directories and set(transported) == set(by_name) and all(
            {key: transported[name][key] for key in ('bytes', 'sha256')} ==
            {key: row[key] for key in ('bytes', 'sha256')} for name, row in by_name.items()),
            'raw transport payload differs')
    payload = root / 'payload'
    refused = document(payload / 'failed-unpack/build-01/receipts/result.json')
    built = document(payload / 'attempt02/receipts/result.json')
    checked = document(payload / 'checks/result.json')
    require(refused['status'] == 'FAILED_OR_INCOMPLETE' and refused['commands'] == [] and
            refused['error'] == "RuntimeError('archive contains an unexpected/nonregular member')", 'unpack refusal differs')
    expected = [(label + suffix, 0) for label in ('native-api', 'mmap', 'killable', 'rwsem', 'mutex')
                for suffix in ('-build', '-sign', '-vermagic', '-signer', '-sig_key', '-sig_hashalgo', '-depends')]
    expected += [('client-build', 0), ('new-runner-syntax', 1)]
    build_logs = check_command_logs(payload / 'attempt02/receipts', built, expected)
    require(built['status'] == 'FAILED_OR_INCOMPLETE' and
            built['error'] == "RuntimeError('new-runner-syntax failed; original output retained')" and
            "SyntaxError: '(' was never closed" in (payload / 'attempt02/receipts/new-runner-syntax.log').read_text(),
            'original AST failure differs')
    checks_logs = check_command_logs(payload / 'checks', checked,
        [('corrected-runner-syntax', 0), ('source-boundary-four', 0), ('unselected-syscalls', 0)])
    require(checked['status'] == 'AFFECTED_MODULE_BUILDS_AND_BASIC_CHECKS_COMPLETE' and
            checked['prior_error'] == built['error'] and checked['prior_result_sha256'] == sha(payload / 'attempt02/receipts/result.json'),
            'basic-only continuation lost the original failure')
    require(built['kernel_core_git_head'] == checked['kernel_core_git_head'] == '0c97cd34cc6e3b75ac7ed0e233c813431264ef73' and
            built['source_git_head'] == checked['compiled_source_git_head'] == 'e01a89d95aec9e2efa0937d88f66a92b95b71e08' and
            checked['corrected_runner_git_head'] == 'e9365fdfffb625f47766aeef935cbcfb8f875eea' and
            built['kernelrelease'] == '7.0.0-38-kdrebuild7' and
            built['linked_build_id'] == '6195c94ad20aa3548344f27416b350cfde14ad6e' and built['running_candidate_proof'] is False,
            'version/build-only identity differs')
    require(checked['checks'] == {'new_runner_ast': 2, 'source_boundary_skips': 0, 'source_boundary_tests': 4,
            'unselected_iterations_per_thread': 8, 'unselected_threads': 2} and
            (payload / 'checks/corrected-runner-syntax.log').read_text().strip() == 'AST_COMPLETE 2' and
            (payload / 'checks/source-boundary-four.log').read_text().splitlines()[-1] == 'SOURCE_BOUNDARIES_COMPLETE 4' and
            'Ran 4 tests' in (payload / 'checks/source-boundary-four.log').read_text(), 'actual basic check counts differ')
    manifest = document(payload / 'attempt02/transport/source-sha256.json')
    state = document(payload / 'attempt02/transport/source-state.json')
    require(len(manifest) == state['files'] == 139 and state['git_status'] == '' and state['source_git_head'] == built['source_git_head'] and
            state['transfer_bytes'] == sum(row['bytes'] for row in manifest.values()) == 1495952,
            'frozen139 source export differs')
    original, dirs = tar_members(payload / 'failed-unpack/transport/source.tar')
    repacked, repacked_dirs = tar_members(payload / 'attempt02/transport/source.tar')
    require(len(dirs) == 20 and not repacked_dirs and original == repacked and set(original) == set(manifest),
            'regular-only repack changed regular source bytes/modes')
    for name, row in manifest.items():
        require({key: original[name][key] for key in ('bytes', 'sha256')} == row and
                facts(payload / 'attempt02/input' / name) == row, 'archived/extracted source differs')
    fixed = payload / 'checks-input/mmap-runner-fixed.py'
    require(sha(fixed) == checked['corrected_runner_sha256'] == 'c20114507195b4dbccdd2fbca504230400a8cc9be3c51182d76ea30eff3dfb31',
            'standalone corrected source differs')
    original_runner = payload / 'attempt02/input/tests/kernel/mmap_api/runner.py'
    diff = list(difflib.unified_diff(original_runner.read_text().splitlines(), fixed.read_text().splitlines(),
                                   fromfile='original-e01-runner', tofile='standalone-e936-runner', lineterm=''))
    changes = [line for line in diff if line.startswith(('+', '-')) and not line.startswith(('+++', '---'))]
    require(len(changes) == 4 and changes[0][1:].replace('\"ACQUIRE_CANCELLED\")', '\"ACQUIRE_CANCELLED\", \"QUERY_RESULT\")') == changes[1][1:] and
            changes[2][1:] + ')' == changes[3][1:], 'corrected runner differs from the exact name-append/parenthesis changes')
    require(set(built['modules']) == {'native-api', 'mmap', 'killable', 'rwsem', 'mutex'} and built['modules'] == checked['modules'],
            'passing module set differs')
    artifacts = {}
    for label, row in built['modules'].items():
        for kind in ('unsigned', 'signed'):
            file = payload / f'binaries/{label}-{kind}.ko'
            value = facts(file)
            require(value == {key: row[kind][key] for key in ('bytes', 'sha256')} and
                    checked['artifact_pins'][row[kind]['path']] == value['sha256'], 'retained module binary differs')
            artifacts[label + '-' + kind] = value
        for field, value in row['modinfo'].items():
            require((payload / f'attempt02/receipts/{label}-{field}.log').read_text().strip() == value, 'module metadata log differs')
        require(row['modinfo']['vermagic'].split()[0] == built['kernelrelease'] and row['modinfo']['sig_hashalgo'] == 'sha512' and
                row['modinfo']['signer'] and row['modinfo']['sig_key'] and not row['modinfo']['depends'], 'actual signature/release differs')
    artifacts['client'] = facts(payload / 'binaries/client')
    require(artifacts['client'] == {key: built['client'][key] for key in ('bytes', 'sha256')} and built['client'] == checked['client'] and
            checked['artifact_pins'][built['client']['path']] == artifacts['client']['sha256'], 'passed C client differs')
    require(len(built['core_pins_before']) == 16 and built['core_pins_before'] == checked['core_pins_before'] == checked['core_pins_after'],
            'linked16 before/after hashes differ')
    identities = [built['identity_before'], checked['identity_before'], checked['identity_after']]
    normal = {'boot': 'afb0c5cd-96b7-488b-bcb4-4a31cbb4e50e', 'release': '7.0.0-38-kdlock1', 'taint': '0'}
    names = None
    for identity in identities:
        require(all(str(identity[key]) == value for key, value in normal.items()) and not identity['busy'] and not identity['blocked'],
                'actual offline normal identity/idle differs')
        actual_names = sorted(line.split()[0] for line in identity['modules'].splitlines())
        require(len(actual_names) == 54 and (names is None or names == actual_names), 'normal54 module profile differs')
        names = actual_names
    baseline = checked['unselected_syscall_baseline']
    require(json.loads((payload / 'checks/unselected-syscalls.log').read_text()) == baseline and
            baseline['status'] == 'syscall_completion_pass' and baseline['overall_pass'] is True and
            baseline['kd_observations'] == 'not_collected' and baseline['selected_gate']['requested'] is False and
            baseline['threads'] == baseline['created_threads'] == 2 and baseline['iterations_per_thread'] == 8 and
            baseline['completed_iterations'] == 16 and baseline['worker_errors'] == baseline['arena_cleanup_errno'] == 0 and baseline['deadline_ms'] == 60000 and
            len(baseline['workers']) == 2 and
            baseline['arena_reservations'] == 1 and not baseline['deadline_exceeded'] and baseline['setup_error'] == 'none',
            'unselected actual syscall completion differs')
    totals = {}
    for worker in baseline['workers']:
        require(worker['completed'] == 8 and worker['mmap_attempts'] == worker['mmap_successes'] == 24 and
                worker['munmap_attempts'] == worker['munmap_successes'] == 16 and
                worker['mincore_attempts'] == worker['unmapped_page_checks'] == 32 and worker['reuse_successes'] == 8 and
                worker['fresh_zero_bytes'] == worker['written_bytes'] == worker['readback_bytes'] == 32 * baseline['page_bytes'] and
                worker['error'] == 'none' and worker['errno'] == 0 and not worker['deadline_reached'], 'worker effects differ')
        for key in ('mmap_successes', 'munmap_successes', 'unmapped_page_checks', 'reuse_successes',
                    'fresh_zero_bytes', 'written_bytes', 'readback_bytes'):
            totals[key] = totals.get(key, 0) + worker[key]
    warnings = []
    for label in built['modules']:
        path = payload / f'attempt02/receipts/{label}-build.log'
        for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
            if re.match(r'^.*:[0-9]+(?::[0-9]+)?: warning:', line):
                warnings.append({'module': label, 'log': str(path.relative_to(root)), 'line': number, 'text': line})
    require(len(warnings) == 4 and sorted(re.findall(r'frame size of ([0-9]+) bytes', '\n'.join(row['text'] for row in warnings))) ==
            ['1912', '2264', '4352'], 'retained compiler warning set differs')
    whitespace = []
    for name in regular:
        data = (root / name).read_bytes()
        if b'\0' in data:
            continue
        try:
            text = data.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            continue
        trailing = [number for number, line in enumerate(text.splitlines(), 1) if line.rstrip(' \t') != line]
        if trailing or text.endswith('\n\n'):
            whitespace.append({'path': name, 'trailing_space_lines': trailing, 'blank_line_at_eof': text.endswith('\n\n')})
    drivers = {}
    for name, expected_rc in [('failed-unpack/driver-01', 1), ('attempt02/driver', 1), ('checks-driver', 0)]:
        row = document(payload / name / 'result.json');require(row['returncode'] == expected_rc, 'outer controller disposition differs')
        drivers[name] = row
    return {'schema': 1, 'status': 'SAVED_RECEIPTS_CONSISTENT', 'collection': {'payload_files': 225, 'payload_bytes': 11693491,
            'regular_retained_collection_files': len(regular), 'regular_retained_collection_bytes': sum(row['bytes'] for row in regular.values()),
            'copy_index_sha256': sha(root / 'copy-index.json'), 'raw_transport_sha256': sha(transport), 'guest_before_after_equal': True},
            'normal_running_identity': normal, 'normal_module_names': names, 'linked_candidate_release': built['kernelrelease'],
            'linked_candidate_build_id': built['linked_build_id'], 'compiled_source_git_head': built['source_git_head'],
            'kernel_core_git_head': built['kernel_core_git_head'], 'corrected_runner_git_head': checked['corrected_runner_git_head'],
            'original_archive_directory_records': len(dirs), 'source_regular_members': 139, 'source_regular_bytes': 1495952,
            'regular_repack_preserves_names_modes_bytes': True, 'initial_unpack': {'status': refused['status'], 'error': refused['error'], 'project_commands': 0},
            'build_attempt': {'status': built['status'], 'successful_commands_before_ast': 36, 'failed_ast_returncode': 1, 'commands': build_logs},
            'basic_continuation': {'status': checked['status'], 'commands': checks_logs, 'checks': checked['checks'],
                'corrected_runner_diff': diff, 'core16_before_after_equal': True, 'module_client_bytes_unchanged': True},
            'actual_artifacts': artifacts, 'compiler_warnings': warnings, 'raw_whitespace': whitespace, 'unselected_syscalls': {'threads': 2, 'iterations_per_thread': 8,
                'completed_iterations': 16, 'worker_errors': 0, 'page_bytes': baseline['page_bytes'], 'worker_totals': totals,
                'separate_parent_arena_mmap': 1, 'separate_parent_arena_munmap': 1, 'selected_gate_requested': False},
            'outer_controller_results': drivers,
            'scope': 'Saved-file audit only. No project import/AST/test/build/VM. No selected kernel7, module load, generated-code or performance evidence.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    value = audit(args.collection)
    with args.report.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'status': value['status'], 'report': str(args.report), 'sha256': sha(args.report)}, sort_keys=True))
