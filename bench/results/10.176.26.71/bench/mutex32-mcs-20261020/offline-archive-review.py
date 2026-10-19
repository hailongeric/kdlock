#!/usr/bin/env python3
"""Read-only offline archive/source audit; never extract or execute archive code.

Only Git object reads and inert tar/JSON/text reads are performed. Audit receipts
are written to --report. Explicit --allow-ancillary paths permit documented
runner/test/prose differences; production, daemon and translator differences
can never use that exception. Every exception retains both hashes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import subprocess
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hashfile(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def canonical(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def runtime_path(path):
    return path.startswith(('include/', 'kernel_module/')) and (
        Path(path).suffix in ('.c', '.h', '.inc', '.S', '.def') or Path(path).name == 'Makefile')


def safe_relative(path):
    value = PurePosixPath(path)
    return bool(path) and not value.is_absolute() and '..' not in value.parts


class Audit:
    def __init__(self, args):
        self.args = args
        self.repo, self.raw, self.report = (path.resolve() for path in (args.repo, args.raw, args.report))
        self.issues, self.counts = [], Counter()
        self.files, self.contents, self.members = {}, {}, {}
        self.git_cache, self.git_paths, self.resolved = {}, {}, {}
        self.archive = json.loads((self.raw / 'archives.json').read_text())
        self.inventory = json.loads((self.raw / 'input-inventory.json').read_text())
        self.prefix = self.archive['archive_prefix'] + '/'
        self.guest_base = self.archive['guest_base'].rstrip('/') + '/'

    def check(self, value, label, detail=None):
        self.counts[label] += 1
        if not value:
            self.issues.append(dict(check=label, detail=detail))
        return value

    def jread(self, name):
        return json.loads(self.contents[name])

    def git(self, *argv):
        return subprocess.check_output(['git', *argv], cwd=self.repo, timeout=30)

    def revision(self, value):
        if not re.fullmatch(r'[0-9a-f]{7,40}', value):
            raise ValueError('invalid retained Git revision: ' + repr(value))
        if value not in self.resolved:
            self.resolved[value] = self.git('rev-parse', value + '^{commit}').decode().strip()
        return self.resolved[value]

    def names(self, revision):
        if revision not in self.git_paths:
            self.git_paths[revision] = set(self.git('ls-tree', '-r', '--name-only', revision).decode().splitlines())
        return self.git_paths[revision]

    def git_bytes(self, revision, path):
        key = revision, path
        if key not in self.git_cache:
            self.git_cache[key] = self.git('show', revision + ':' + path)
        return self.git_cache[key]

    def load_archives(self):
        ar, inv = self.archive, self.inventory
        self.check(ar.get('completed') is True and ar.get('guest_idle') is True, 'archive_completed_idle')
        self.check(hashfile(self.raw / 'input-inventory.json') == ar['input_inventory_sha256'], 'inventory_hash')
        self.check(hashfile(self.raw / 'archive_run.py') == ar['script_sha256'], 'archiver_hash')
        groups, links = [], []
        for group in ar['groups']:
            if not safe_relative(group['file']) or Path(group['file']).name != group['file']:
                raise ValueError('unsafe archive filename')
            path = self.raw / group['file']
            self.check(path.stat().st_size == group['bytes'], 'archive_bytes', group['file'])
            self.check(hashfile(path) == group['sha256'], 'archive_hash', group['file'])
            kinds = Counter()
            with tarfile.open(path, 'r:gz') as archive:
                for member in archive:
                    if not self.check(member.name.startswith(self.prefix), 'member_prefix', member.name):
                        continue
                    name = member.name[len(self.prefix):]
                    if not self.check(safe_relative(name), 'member_safe_path', name):
                        continue
                    if not self.check(name not in self.members, 'member_unique', name):
                        continue
                    self.check(any(member.name == root or member.name.startswith(root + '/') for root in group['roots']),
                               'member_assigned_group', name)
                    kind = ('file' if member.isfile() else 'dir' if member.isdir() else
                            'symlink' if member.issym() else 'unsupported')
                    kinds[kind] += 1
                    self.members[name] = dict(kind=kind, bytes=member.size, archive=group['file'])
                    expected = inv.get(name)
                    if not self.check(expected is not None, 'member_in_inventory', name):
                        continue
                    expected_kind = ('file' if stat.S_ISREG(expected['mode']) else 'dir' if stat.S_ISDIR(expected['mode'])
                                     else 'symlink' if stat.S_ISLNK(expected['mode']) else 'unsupported')
                    self.check(kind == expected_kind and kind != 'unsupported', 'member_type', name)
                    self.check(member.mode == stat.S_IMODE(expected['mode']), 'member_mode', name)
                    self.check((member.uid, member.gid) == (expected['uid'], expected['gid']), 'member_owner', name)
                    seconds, nanos = divmod(expected['mtime_ns'], 1_000_000_000)
                    self.check(member.mtime == seconds + nanos * 1e-9, 'member_mtime_tar_projection', name)
                    if kind == 'file':
                        self.check(member.size == expected['bytes'], 'member_bytes', name)
                        content = archive.extractfile(member).read()
                        self.check(len(content) == member.size, 'member_read_bytes', name)
                        self.files[name] = sha(content)
                        # Keep only inert metadata/source text needed below, never import it.
                        if member.size < 5_000_000 and (name.endswith(('.json', '.log', '.patch', '.c', '.h', '.inc', '.S', '.py', '.def'))
                                or '/source/' in name or '/.build/provider/' in name or '/build/provider/' in name):
                            if b'\x00' not in content:
                                self.contents[name] = content
                    elif kind == 'symlink':
                        self.check(member.linkname == expected['link'] and len(member.linkname.encode()) == expected['bytes'],
                                   'symlink_target', name)
                        self.check(member.size == 0, 'symlink_empty_payload', name)
                        target = member.linkname[len(self.guest_base):] if member.linkname.startswith(self.guest_base) else None
                        self.check(target in inv, 'symlink_target_retained', dict(path=name, target=member.linkname))
                        links.append((name, member.linkname))
                    elif kind == 'dir':
                        self.check(member.size == 0, 'directory_empty_payload', name)
            groups.append(dict(file=group['file'], sha256=group['sha256'], bytes=group['bytes'],
                               members=sum(kinds.values()), types=dict(kinds)))
        self.check(set(self.members) == set(inv), 'inventory_exact_set',
                   dict(missing=sorted(set(inv) - set(self.members)), extra=sorted(set(self.members) - set(inv))))
        self.check(self.files.get(ar['health_path']) == ar['health_sha256'], 'archived_health_hash')
        return groups, links

    def normalized_binary(self, value, folder):
        if value.startswith(self.guest_base):
            return value[len(self.guest_base):]
        if value.startswith('/root/host_fs/kdlock/') or value.endswith('/tools/perf'):
            return folder + '/binaries/' + value.rsplit('/', 1)[1]
        return folder + '/' + value

    def manifests(self):
        source_rows, binary_rows = [], []
        for name in sorted(self.files):
            folder = name.rsplit('/', 1)[0] if '/' in name else ''
            if name.endswith(('/source-sha256.json', '/prepared-source-sha256.json')):
                prepared = name.endswith('/prepared-source-sha256.json')
                prefix = folder + ('/build/provider/' if prepared else '/source/')
                manifest = self.jread(name)
                for path, expected in manifest.items():
                    self.check(safe_relative(path) and self.files.get(prefix + path) == expected,
                               'prepared_source_manifest_hash' if prepared else 'source_manifest_hash',
                               dict(manifest=name, path=path))
                source_rows.append(dict(path=name, entries=len(manifest), sha256=self.files[name], prepared=prepared))
            elif name.endswith(('/binary-sha256.json', '/binaries.json')):
                for key, value in self.jread(name).items():
                    path, expected = (value['path'], value['sha256']) if isinstance(value, dict) else (key, value)
                    member = self.normalized_binary(path, folder)
                    self.check(self.files.get(member) == expected, 'binary_manifest_hash',
                               dict(manifest=name, path=path, member=member))
                    binary_rows.append((name, key, member, expected))
        return source_rows, binary_rows

    def ancillary_allowed(self, path):
        permitted_kind = path.startswith(('bench/', 'tests/', 'docs/')) or Path(path).suffix == '.md'
        protected = path.startswith(('include/', 'kernel_module/', 'daemon/', 'disassem/'))
        return permitted_kind and not protected and any(
            path == allowed or allowed.endswith('/') and path.startswith(allowed)
            for allowed in self.args.allow_ancillary)

    def reconstruct(self, original_root, patch):
        """Apply exact unique unified-diff hunks in memory; no patch subprocess."""
        output, lines, index = {}, patch.decode().splitlines(keepends=True), 0
        while index < len(lines):
            if not lines[index].startswith('diff --git '):
                index += 1
                continue
            path = lines[index].split(' b/', 1)[1].strip()
            if not safe_relative(path):
                raise ValueError('unsafe patch target')
            original = self.contents[original_root + path].decode().splitlines(keepends=True)
            result, cursor = [], 0
            index += 1
            while index < len(lines) and not lines[index].startswith('diff --git '):
                if not lines[index].startswith('@@ '):
                    index += 1
                    continue
                header = lines[index]
                old, new = [], []
                index += 1
                while index < len(lines) and not lines[index].startswith(('@@ ', 'diff --git ')):
                    line = lines[index]
                    if line.startswith(' '):
                        old.append(line[1:]); new.append(line[1:])
                    elif line.startswith('-'):
                        old.append(line[1:])
                    elif line.startswith('+'):
                        new.append(line[1:])
                    else:
                        raise ValueError('unsupported patch body: ' + repr(line))
                    index += 1
                positions = [at for at in range(cursor, len(original) - len(old) + 1)
                             if original[at:at + len(old)] == old]
                if len(positions) != 1:
                    raise ValueError('nonunique patch hunk: ' + path + ':' + header)
                at = positions[0]
                result.extend(original[cursor:at]); result.extend(new)
                cursor = at + len(old)
            result.extend(original[cursor:])
            output[path] = ''.join(result).encode()
        return output

    def source_audit(self, source_rows, comparison, validation):
        commits = {arm: self.jread(arm + '/matrix.json')['source_commit'] for arm in comparison['arms']}
        mapped = dict(commits)
        for arm, row in validation['checks_by_arm'].items():
            self.check(row['source_commit'] == commits[arm], 'validation_candidate_commit', arm)
            mapped[row['directory']] = commits[arm]
        for value in self.args.extra_source:
            folder, separator, revision = value.partition('=')
            if not separator or folder in mapped or '/' in folder:
                raise ValueError('invalid --extra-source mapping: ' + value)
            mapped[folder] = revision
        for value in self.args.expect:
            arm, separator, expected = value.partition('=')
            if not separator or arm not in commits:
                raise ValueError('invalid --expect mapping: ' + value)
            self.check(self.revision(commits[arm]) == self.revision(expected), 'selected_source_commit', arm)
        for revision in mapped.values():
            self.revision(revision)
        original_rows, prepared_rows, exceptions = [], [], []
        for row in source_rows:
            name = row['path']; folder = name.rsplit('/', 1)[0]; top = folder.split('/')[0]
            if not self.check(top in mapped, 'source_snapshot_mapped', name):
                continue
            commit = mapped[top]
            manifest = self.jread(name)
            original_root = folder + '/source/'
            if row['prepared']:
                prepared_rows.append((folder, commit, original_root,
                                      {path: folder + '/build/provider/' + path for path in manifest}))
                continue
            overlay = 'bench/spin_cacheline/.build/provider/'
            original = {path: value for path, value in manifest.items() if not path.startswith(overlay)}
            expected_runtime = {path for path in self.names(commit) if runtime_path(path)}
            actual_runtime = {path for path in original if runtime_path(path)}
            self.check(actual_runtime == expected_runtime, 'production_path_set_exact',
                       dict(manifest=name, missing=sorted(expected_runtime - actual_runtime),
                            extra=sorted(actual_runtime - expected_runtime)))
            mismatches, allowed = [], []
            for path, actual in original.items():
                expected = sha(self.git_bytes(commit, path)) if path in self.names(commit) else None
                if actual == expected:
                    self.check(True, 'original_source_git_hash')
                elif self.ancillary_allowed(path):
                    value = dict(manifest=name, commit=commit, path=path, actual_sha256=actual,
                                 git_sha256=expected, reason='explicit --allow-ancillary runner/test/prose exception')
                    exceptions.append(value); allowed.append(path)
                else:
                    self.check(False, 'original_source_git_hash', dict(manifest=name, commit=commit,
                               path=path, actual=actual, expected=expected))
                    mismatches.append(path)
            original_rows.append(dict(manifest=name, commit=commit, files=len(original),
                                      production_files=len(actual_runtime),
                                      private_inc_files=sum(path.endswith('.inc') for path in actual_runtime),
                                      allowed_ancillary=allowed, mismatches=mismatches))
            prepared = {path[len(overlay):]: original_root + path for path in manifest if path.startswith(overlay)}
            if prepared:
                prepared_rows.append((folder, commit, original_root, prepared))
        reconstructed = []
        for folder, commit, original_root, prepared in prepared_rows:
            patch_path = original_root + 'bench/spin_cacheline/provider/observation.patch'
            changes = self.reconstruct(original_root, self.contents[patch_path])
            classes = Counter()
            for path, member in prepared.items():
                if path == 'manifest.json':
                    generated = self.jread(member)
                    self.check(generated.get('complete') is True, 'prepared_manifest_complete', folder)
                    for target, expected in generated['prepared'].items():
                        self.check(self.files.get(prepared.get(target, '')) == expected,
                                   'prepared_manifest_bytes', dict(folder=folder, path=target))
                    for target, expected in generated['production'].items():
                        self.check(self.files.get(original_root + target) == expected,
                                   'prepared_original_source_binding', dict(folder=folder, path=target))
                    for target, expected in generated['observation'].items():
                        self.check(self.files.get(original_root + 'bench/spin_cacheline/provider/' + target) == expected,
                                   'prepared_observation_binding', dict(folder=folder, path=target))
                    classes['generated_manifest'] += 1
                    continue
                if path == 'include/kd_bench.h':
                    expected = self.contents[original_root + 'bench/spin_cacheline/provider/kd_bench.h']; kind = 'benchmark_overlay'
                elif path == 'kernel_module/kd_bench.c':
                    expected = self.contents[original_root + 'bench/spin_cacheline/provider/kd_bench.c']; kind = 'benchmark_overlay'
                elif path in changes:
                    expected = changes[path]; kind = 'observation_patch'
                else:
                    expected = self.contents[original_root + path]; kind = 'unchanged_original'
                self.check(self.files[member] == sha(expected), 'prepared_reconstructed_hash',
                           dict(folder=folder, path=path, category=kind))
                classes[kind] += 1
            self.check(set(changes) <= prepared.keys(), 'prepared_patch_targets_retained', folder)
            reconstructed.append(dict(folder=folder, commit=commit, files=len(prepared),
                                      classification=dict(classes), patch_sha256=self.files[patch_path]))
        current_arm = validation['current_arm']; current = commits[current_arm]
        self.check(validation['source_revision'] == current, 'current_revision_binding')
        current_paths = {path for path in self.names(current) if runtime_path(path)}
        for path in current_paths:
            self.check((self.repo / path).is_file() and hashfile(self.repo / path) == sha(self.git_bytes(current, path)),
                       'current_production_git_hash', path)
        return dict(commits={arm: dict(recorded=value, resolved=self.revision(value)) for arm, value in commits.items()},
                    original_manifests=original_rows, prepared_snapshots=reconstructed,
                    ancillary_exceptions=exceptions, current_production=dict(arm=current_arm, commit=current,
                    files=len(current_paths), private_inc_files=sum(p.endswith('.inc') for p in current_paths)))

    def evidence_bindings(self, comparison, validation, health):
        arms = comparison['arms']
        commits = {arm: self.jread(arm + '/matrix.json')['source_commit'] for arm in arms}
        self.check(comparison.get('complete') is True and not comparison.get('issues'), 'comparison_complete')
        self.check(len(comparison['sessions']) == 18 * len(arms)
                   and sum(r['score_eligible'] for r in comparison['sessions']) == 18 * len(arms)
                   and all(r['valid'] for r in comparison['sessions']), 'comparison_session_scope')
        self.check(validation.get('passed') is True and validation.get('full_suite') is False, 'validation_passed_affected_only')
        self.check(health.get('idle') is True and health.get('boot_id') == self.archive['boot_id']
                   and not health.get('per_session_kernel_faults'), 'health_idle_same_boot')
        for receipt, fields in ((validation, {'comparison_sha256': 'comparison.json'}),
                                (health, {'comparison_sha256': 'comparison.json', 'validation_sha256': 'validation.json',
                                          'guest_before_sha256': 'guest-before.log'})):
            for key, name in fields.items():
                self.check(receipt.get(key) == self.files.get(name), 'finalization_receipt_hash', key)
        for name, expected in health['kernel_logs'].items():
            self.check(self.files.get(name) == expected, 'health_kernel_log_hash', name)
        self.check(set(health['kernel_logs']) == {name for name in self.files if name.endswith('/kernel.log')},
                   'health_kernel_log_inventory_exact')
        self.check(set(health['expected_kernel_logs']) <= health['kernel_logs'].keys(), 'expected_kernel_logs_retained')
        self.check(validation.get('helper_sha256') == self.files.get('finalize.py'), 'finalization_helper_binding')
        for key, name in (('before_sha256', 'host-before.json'), ('after_sha256', 'host-after.json')):
            self.check(health.get('topology', {}).get(key) == self.files.get(name), 'topology_receipt_binding', name)
        for arm, row in validation['matrices'].items():
            self.check(arm in commits and row['source_commit'] == commits[arm]
                       and row['matrix_sha256'] == self.files.get(arm + '/matrix.json'),
                       'matrix_validation_binding', arm)
            matrix = self.jread(arm + '/matrix.json')
            self.check(matrix.get('passed') is True and matrix.get('final_idle') is True
                       and matrix.get('plain_sessions') == 18 and matrix.get('profile_sessions') == 0
                       and matrix.get('comparison_arm') is True
                       and matrix.get('script_sha256') == self.files.get('run-matrix.py'),
                       'matrix_complete_scope', arm)
            for name, proof in row['collections'].items():
                folder = arm + '/' + name + ('/pipe' if name == 'profile' else '')
                for field, path in (('sha256', folder + '/source-sha256.json'),
                                    ('records_sha256', folder + '/records.json'),
                                    ('command_sha256', arm + '/' + name + '-command.json')):
                    self.check(proof[field] == self.files.get(path), 'validated_collection_binding', path)
        for row in comparison['collections']:
            folder = row['arm'] + '/' + row['collection'] + ('/pipe' if row['collection'] == 'profile' else '')
            self.check(row['source_commit'] == commits[row['arm']], 'summary_collection_revision', folder)
            for key, path in (('source_manifest_sha256', folder + '/source-sha256.json'),
                              ('records_sha256', folder + '/records.json'),
                              ('command_sha256', row['arm'] + '/' + row['collection'] + '-command.json')):
                self.check(row[key] == self.files.get(path), 'summary_collection_binding', path)
            source_id = sha(json.dumps(self.jread(folder + '/source-sha256.json'), sort_keys=True).encode())
            self.check(row['source_identity'] == source_id, 'summary_collection_source_identity', folder)
        for row in comparison['sessions']:
            path = row['session_path'] + '/session.json'
            self.check(self.files.get(path) == row['session_sha256'], 'summary_session_hash', path)
            self.check(row['source_commit'] == commits[row['arm']], 'summary_session_revision', path)
            session = self.jread(path)
            self.check(session.get('execution_status') == 'OK' and session.get('drained') is True,
                       'raw_session_passed_drained', path)
        for arm, row in validation['checks_by_arm'].items():
            folder = row['directory']; result = self.jread(folder + '/result.json')
            self.check(self.files.get(folder + '/result.json') == row['result_sha256']
                       and self.files.get(folder + '/commands.json') == row['commands_sha256'], 'check_receipt_hashes', folder)
            self.check(result.get('passed') is True and result.get('final_idle') is True
                       and result.get('source_unchanged') is True and result.get('full_suite') is False
                       and result.get('unit_basic') == 2 and len(result.get('unit_drivers', [])) == 15
                       and 'mutex/test_mutex_osq.py' in result.get('unit_drivers', []),
                       'checks_basic_affected_scope', folder)
            commands = self.jread(folder + '/commands.json')
            self.check(commands == result['commands'] and all(command.get('exit_code') == 0 for command in commands)
                       and [command['name'] for command in commands] ==
                       ['dependencies', 'provider', 'daemon', 'unit', 'runner-plan', 'runner-report', 'local', 'rwsem', 'instruction-exit'],
                       'checks_command_scope_and_exits', folder)
            text = self.contents[folder + '/unit.log'].decode()
            self.check(re.findall(r'Unit tests: (\d+) passed, (\d+) failed', text) == [('17', '0')], 'unit_totals', folder)
            for name, proof in row.get('runner_tests', {}).items():
                log = self.contents[folder + '/' + name + '.log'].decode()
                self.check(proof.get('passed') is True and proof['log_sha256'] ==
                           self.files.get(folder + '/' + name + '.log') and
                           re.findall(r'(?m)^Ran (\d+) tests? in ', log) == [str(proof['tests'])] and
                           re.search(r'(?m)^OK$', log) and 'skipped=' not in log,
                           'runner_test_evidence', [folder, name])
            for controls in row['negative_controls'].values():
                self.check(all('mutation detected: ' + name in text for name in controls), 'negative_control_log', folder)
            for probe, proof in row['live'].items():
                path = folder + '/' + probe + '/result.json'; actual = self.jread(path)
                self.check(actual.get('passed') is True and actual.get('drained') is True
                           and self.files.get(path) == proof['result_sha256'], 'live_probe_passed_drained', path)

    def run(self):
        groups, links = self.load_archives()
        source_rows, binary_rows = self.manifests()
        comparison, validation, health = (self.jread(name) for name in
            ('comparison.json', 'validation.json', 'health.json'))
        self.evidence_bindings(comparison, validation, health)
        source = self.source_audit(source_rows, comparison, validation)
        compact = []
        for path in sorted(self.report.rglob('*')):
            if path.is_file() and not path.is_symlink():
                name = str(path.relative_to(self.report))
                if name in self.files:
                    self.check(hashfile(path) == self.files[name], 'compact_receipt_hash', name)
                    compact.append((name, self.files[name]))
                elif name == 'archives.json':
                    self.check(hashfile(path) == hashfile(self.raw / 'archives.json'), 'copied_archives_receipt_hash')
        jit = []
        for name in sorted(self.files):
            if not name.endswith('/jit.bin'):
                continue
            prefix = name[:-len('jit.bin')]
            if '/publications/' in prefix:
                session = prefix.split('/publications/', 1)[0]
                self.check(prefix + 'jit.S' in self.files, 'jit_publication_pair', prefix)
                matches = [other for other in self.files if other.startswith(session + '/workspace/')
                           and other.endswith('/jit.bin') and self.files[other] == self.files[name]
                           and self.files.get(other[:-7] + 'jit.S') == self.files.get(prefix + 'jit.S')]
                self.check(bool(matches), 'jit_publication_workspace_match', prefix)
            else:
                self.check(all(prefix + suffix in self.files for suffix in ('jit.S', 'jit.o', 'jit.bin')),
                           'jit_workspace_triplet', prefix)
            jit.append((name, self.files[name], self.files.get(prefix + 'jit.S'), self.files.get(prefix + 'jit.o')))
        self.check({n for n in self.inventory if n.endswith(('/jit.S', '/jit.o', '/jit.bin'))} ==
                   {n for n in self.files if n.endswith(('/jit.S', '/jit.o', '/jit.bin'))}, 'jit_inventory_exact')
        common = dict(schema=1, passed=not self.issues, audit_script_sha256=hashfile(Path(__file__)),
                      issues=self.issues, scope='Offline inert-byte/Git-object audit; no archive extraction, execution, build, test or VM command')
        archive_report = dict(common, host=socket.gethostname(), archive_receipt_sha256=hashfile(self.raw / 'archives.json'),
                              inventory_sha256=hashfile(self.raw / 'input-inventory.json'), archived_groups=groups,
                              inventory_members=len(self.inventory), members=len(self.members), regular_files=len(self.files),
                              regular_file_hash_map_sha256=canonical(self.files), symlinks=len(links), symlink_map_sha256=canonical(links),
                              compact_copies=len(compact), compact_copy_map_sha256=canonical(compact),
                              jit_binaries=len(jit), jit_map_sha256=canonical(jit), source_manifests=len(source_rows),
                              binary_manifest_entries=len(binary_rows), binary_binding_map_sha256=canonical(binary_rows),
                              metadata_limits='Tar preserves reviewed path/type/mode/uid/gid, file length, symlink target and mtime projection. '
                              'Original inode/device/ctime/directory size/link counts remain only in the hashed inventory. '
                              'Inventory is stat metadata; archive hashes bind all bytes, with separate source/binary/receipt hash checks.',
                              checks=dict(self.counts))
        source_report = dict(common, **source, source_manifests=len(source_rows), binary_manifest_entries=len(binary_rows),
                             prepared_limit='Only retained expanded provider snapshots are reconstructed. API collections retain original source, '
                             'preparation recipes and built binaries, but may omit expanded private provider trees.',
                             numeric_limit='This audit binds reported statistics and profiles to raw inputs; it does not independently reparse '
                             'sample periods or recompute throughput/peak statistics.')
        for name, value in (('archive-review.json', archive_report), ('source-review.json', source_report)):
            (self.report / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
        print(json.dumps(dict(passed=not self.issues, members=len(self.members), regular_files=len(self.files),
                              source_manifests=len(source_rows), binary_manifest_entries=len(binary_rows),
                              jit_binaries=len(jit), ancillary_exceptions=len(source['ancillary_exceptions']),
                              issues=self.issues), indent=2))
        return 1 if self.issues else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--expect', action='append', default=[], metavar='ARM=COMMIT')
    parser.add_argument('--extra-source', action='append', default=[], metavar='TOP_LEVEL_DIRECTORY=COMMIT',
                        help='explicit mapping for preserved diagnostic/failed source snapshots outside comparison arms')
    parser.add_argument('--allow-ancillary', action='append', default=[], metavar='PATH',
                        help='exact runner/test/prose path or directory ending /; differences remain reported, never production exceptions')
    args = parser.parse_args()
    for path in args.allow_ancillary:
        if not safe_relative(path):
            raise ValueError('unsafe ancillary exception path')
    return Audit(args).run()


if __name__ == '__main__':
    raise SystemExit(main())
