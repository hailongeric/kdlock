#!/usr/bin/env python3
"""Independent inert-archive, source and arithmetic audit of the three-backend round.

Only Git object reads and inert tar/JSON/text reads are performed. Audit receipts
are written to --report. Collection, summarization and retained workload code
are never imported or executed. Source differences are reported without waivers.
"""
import argparse
import ast
from bisect import bisect_left
from fractions import Fraction
import math
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
                        self.members[name]['magic'] = content[:4].hex()
                        # Keep only inert metadata/source text needed below, never import it.
                        if (name.endswith(('.json', '.log', '.patch', '.c', '.h', '.inc', '.S', '.py', '.def', '.md', '.txt'))
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
                    self.check(self.members.get(member, {}).get('magic') == '7f454c46', 'binary_is_elf', member)
                    binary_rows.append((name, key, member, expected))
        return source_rows, binary_rows

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

    def expect(self, kind, condition, detail=None):
        return self.check(condition, kind, detail)

    def equal(self, kind, actual, expected, detail=None):
        return self.expect(kind, same(actual, expected), detail if same(actual, expected) else
                           dict(item=detail, actual=actual, expected=expected))

    def source_audit(self, rows):
        selected = self.revision(self.args.expect_source)
        runtime = self.revision(self.args.runtime_source)
        matrix = self.jread('current/matrix.json')
        self.equal('selected_source_commit', self.revision(matrix['source_commit']), selected)
        code_roots = ('include/', 'kernel_module/', 'daemon/', 'disassem/', 'tclock_backend/')
        source_code = lambda p: p.startswith(code_roots) and (Path(p).suffix in
                         ('.c', '.h', '.inc', '.S', '.def', '.py') or Path(p).name in ('Makefile', 'requirements.txt'))
        expected = {p for p in self.names(selected) if source_code(p)}
        retained, prepared_rows = [], []
        for row in rows:
            name = row['path']; folder = name.rsplit('/', 1)[0]
            self.expect('source_snapshot_scope', folder == 'checks' or folder.startswith('current/'), name)
            original_root = folder + '/source/'
            manifest = self.jread(name)
            if row['prepared']:
                prepared_rows.append((folder, original_root,
                                      {p: folder + '/build/provider/' + p for p in manifest}))
                continue
            overlay = 'bench/spin_cacheline/.build/provider/'
            original = {p: digest for p, digest in manifest.items() if not p.startswith(overlay)}
            actual = {p for p in original if source_code(p)}
            self.equal('production_and_comparator_path_set', sorted(actual), sorted(expected), name)
            for path, actual_hash in original.items():
                expected_hash = sha(self.git_bytes(selected, path)) if path in self.names(selected) else None
                self.equal('original_source_git_hash', actual_hash, expected_hash, [name, path])
            retained.append(dict(manifest=name, files=len(original), production_files=len(actual),
                                 private_inc_files=sum(p.endswith('.inc') for p in actual)))
            prepared = {p[len(overlay):]: original_root + p for p in manifest if p.startswith(overlay)}
            if prepared:
                prepared_rows.append((folder, original_root, prepared))
        reconstructed = []
        for folder, original_root, prepared in prepared_rows:
            patch_path = original_root + 'bench/spin_cacheline/provider/observation.patch'
            changes = self.reconstruct(original_root, self.contents[patch_path])
            classes = Counter()
            for path, member in prepared.items():
                if path == 'manifest.json':
                    generated = self.jread(member)
                    self.equal('prepared_manifest_complete', generated['complete'], True, folder)
                    for target, digest in generated['prepared'].items():
                        self.equal('prepared_manifest_bytes', self.files.get(prepared.get(target, '')), digest, [folder, target])
                    for target, digest in generated['production'].items():
                        self.equal('prepared_original_binding', self.files.get(original_root + target), digest, [folder, target])
                    for target, digest in generated['observation'].items():
                        self.equal('prepared_overlay_binding', self.files.get(original_root + 'bench/spin_cacheline/provider/' + target), digest, [folder, target])
                    classes['generated_manifest'] += 1
                    continue
                if path in ('include/kd_bench.h', 'kernel_module/kd_bench.c'):
                    expected_bytes = self.contents[original_root + 'bench/spin_cacheline/provider/' + Path(path).name]
                    category = 'benchmark_overlay'
                elif path in changes:
                    expected_bytes = changes[path]; category = 'observation_patch'
                else:
                    expected_bytes = self.contents[original_root + path]; category = 'unchanged_original'
                self.equal('prepared_reconstructed_hash', self.files[member], sha(expected_bytes), [folder, path, category])
                classes[category] += 1
            self.expect('prepared_patch_targets', set(changes) <= prepared.keys(), folder)
            reconstructed.append(dict(folder=folder, files=len(prepared), classification=dict(classes)))
        current_paths = {p for p in self.names(selected) if runtime_path(p)}
        self.equal('runtime_path_set', sorted(current_paths), sorted(p for p in self.names(runtime) if runtime_path(p)))
        for path in current_paths:
            selected_hash = sha(self.git_bytes(selected, path))
            self.equal('retained_runtime_unchanged', selected_hash, sha(self.git_bytes(runtime, path)), path)
            self.equal('current_runtime_git_hash', hashfile(self.repo / path), selected_hash, path)
        return dict(source_commit=selected, runtime_commit=runtime, manifests=retained,
                    prepared_snapshots=reconstructed, runtime_files=len(current_paths),
                    runtime_private_inc_files=sum(p.endswith('.inc') for p in current_paths))

    def jit_audit(self):
        rows = []
        for name in sorted(self.files):
            if not name.endswith('/jit.bin'):
                continue
            prefix = name[:-7]
            if '/publications/' in name:
                session = prefix.split('/publications/', 1)[0]
                self.expect('jit_publication_assembly', prefix + 'jit.S' in self.files, name)
                matches = [other for other in self.files if other.startswith(session + '/workspace/')
                           and other.endswith('/jit.bin') and self.files[other] == self.files[name]
                           and self.files.get(other[:-7] + 'jit.S') == self.files.get(prefix + 'jit.S')]
                self.expect('jit_publication_workspace_binding', bool(matches), name)
            else:
                self.expect('jit_workspace_triplet', all(prefix + suffix in self.files for suffix in ('jit.S', 'jit.o')), name)
            rows.append((name, self.files[name], self.files.get(prefix + 'jit.S'), self.files.get(prefix + 'jit.o')))
        self.equal('jit_inventory_exact', sorted(n for n in self.inventory if n.endswith(('/jit.S', '/jit.o', '/jit.bin'))),
                   sorted(n for n in self.files if n.endswith(('/jit.S', '/jit.o', '/jit.bin'))))
        return rows


    def peak(self, record, name):
        m = record['measurement']
        count, wall = m['completed'], m['wall_ns']
        self.expect('whole_positive', unsigned(count) and count > 0 and unsigned(wall) and wall > 0, name)
        self.equal('whole_wall', wall, m['finished_ns'] - m['started_ns'], name)
        for field, setting in (('duration_ns', 'duration_ms'), ('peak_window_ns', 'peak_window_ms'),
                               ('peak_settle_ns', 'peak_settle_ms'), ('sample_period_ns', 'sample_ms')):
            self.equal('measurement_setting', m[field], record[setting] * 1000000, [name, field])
        self.expect('window_settings', 0 < m['sample_period_ns'] <= m['peak_window_ns'] and
                   m['peak_settle_ns'] + m['peak_window_ns'] < m['duration_ns'], name)
        self.equal('measurement_deadline', m['deadline_ns'], m['started_ns'] + m['duration_ns'], name)
        self.equal('progress_batch', m['progress_batch'], 256, name)
        self.equal('collector_identity', [m['collector_cpu'], m['collector_observed_cpu'], m['collector_error'],
                                         m.get('collector_shared', False)],
                   [record['collector_cpu'], record['collector_cpu'], 0, record.get('collector_shared', False)], name)
        self.expect('collector_separate', record['collector_cpu'] not in record['cpus'] and
                   record.get('collector_shared', False) is False, name)
        workers, samples = m['workers'], m['samples']
        self.equal('worker_count', len(workers), record['threads'], name)
        self.equal('worker_cpu_order', [worker['cpu'] for worker in workers], record['cpus'], name)
        self.equal('worker_operation_sum', sum(worker['completed'] for worker in workers), count, name)
        for worker in workers:
            self.expect('worker_interval', all(unsigned(worker[key]) for key in
                       ('active_started_ns', 'kernel_finished_ns', 'finished_ns', 'completed')) and
                       m['started_ns'] <= worker['active_started_ns'] < m['deadline_ns'] <=
                       worker['kernel_finished_ns'] <= worker['finished_ns'] <= m['finished_ns'], [name, worker['cpu']])
            self.expect('worker_oracle', worker['completed'] > 0 and worker['error'] == 0 and
                       worker['observed_cpu'] == worker['cpu'], [name, worker['cpu']])
        active_start = max(worker['active_started_ns'] for worker in workers)
        active_end = min([m['deadline_ns']] + [worker['kernel_finished_ns'] for worker in workers])
        eligible_start = active_start + m['peak_settle_ns']
        self.expect('eligible_interval', active_end - eligible_start >= m['peak_window_ns'], name)
        self.expect('sample_count', isinstance(samples, list) and len(samples) >= 2, name)
        previous_end, previous, eligible = m['started_ns'], [0] * len(workers), []
        for index, sample in enumerate(samples):
            begin, end, counts = sample['started_ns'], sample['finished_ns'], sample['completed']
            self.expect('sample_time_order', unsigned(begin) and unsigned(end) and previous_end <= begin <= end,
                       [name, index])
            self.expect('sample_count_order', len(counts) == len(workers) and all(unsigned(value) and
                       old <= value <= worker['completed'] for value, old, worker in zip(counts, previous, workers)), [name, index])
            self.expect('sample_worker_lifetime', all((end >= worker['active_started_ns'] or value == 0) and
                       (begin < worker['kernel_finished_ns'] or value == worker['completed'])
                       for value, worker in zip(counts, workers)), [name, index])
            if begin >= eligible_start and end <= active_end:
                eligible.append(index)
            previous_end, previous = end, counts
        ends = [samples[index]['finished_ns'] for index in eligible]
        best, candidates = None, 0
        # Binary search independently implements the earliest endpoint rule.
        # Fraction comparison preserves exact ratios and first-observed ties.
        for position, first in enumerate(eligible):
            endpoint = bisect_left(ends, samples[first]['started_ns'] + m['peak_window_ns'], lo=position + 1)
            if endpoint == len(eligible):
                continue
            last = eligible[endpoint]
            deltas = [b - a for a, b in zip(samples[first]['completed'], samples[last]['completed'])]
            elapsed = samples[last]['finished_ns'] - samples[first]['started_ns']
            rate = Fraction(sum(deltas), elapsed)
            candidates += 1
            if all(value > 0 for value in deltas) and (best is None or rate > best[0]):
                best = (rate, first, last, deltas, elapsed)
        if not self.expect('positive_peak_exists', best is not None, name):
            raise ValueError('no positive full-cohort peak: ' + name)
        rate, first, last, deltas, elapsed = best
        start, end = samples[first], samples[last]
        reconstructed = dict(start_sample_index=first, end_sample_index=last,
            started_ns=start['started_ns'], finished_ns=end['finished_ns'],
            start_snapshot_span_ns=start['finished_ns'] - start['started_ns'],
            end_snapshot_span_ns=end['finished_ns'] - end['started_ns'],
            elapsed_ns=elapsed, completed=sum(deltas), worker_completed=deltas,
            throughput_ops_s=float(rate * 1000000000), amortized_ns_op=float(1 / rate),
            policy='observed_full_cohort_earliest_endpoint', requested_window_ns=m['peak_window_ns'],
            settle_ns=m['peak_settle_ns'], active_started_ns=active_start, active_finished_ns=active_end,
            eligible_started_ns=eligible_start, eligible_samples=len(eligible), candidate_windows=candidates,
            progress_batch=256, progress_count_error_bound=256 * len(workers),
            max_snapshot_span_ns=max(sample['finished_ns'] - sample['started_ns'] for sample in samples),
            sample_period_ns=m['sample_period_ns'], collector_cpu=m['collector_cpu'],
            collector_shared=record.get('collector_shared', False))
        self.equal('all_reconstructed_peak_fields', m['peak'], reconstructed, name)
        if 'peak_throughput_ops_s' in record:
            self.equal('record_peak_rate', record['peak_throughput_ops_s'], float(rate * 1000000000), name)
        whole = float(Fraction(count * 1000, wall))
        self.equal('record_whole_rate', record['whole_throughput_ops_s'],
                   whole * 1e6 if record['execution_status'] == 'OK' else None, name)
        self.windows.append(dict(session_path=name, whole_mops=whole, peak_mops=float(rate * 1000),
                                 start_sample_index=first, end_sample_index=last, candidate_windows=candidates))
        return whole, reconstructed

    def session(self, record, spec, collection):
        name = 'current/' + collection + '/' + record['name']
        synthetic = collection in ('c01', 'c08', 'rcuht')
        backend = record['arm']; m = record['measurement']; count = m['completed']
        saved = self.jread(name + '/session.json')
        self.equal('saved_session_fields', {k: record.get(k) for k in saved}, saved, name)
        self.equal('aggregate_only_fields', sorted(set(record) - set(saved)), sorted(DERIVED) if synthetic else [], name)
        self.equal('plan_session_fields', {k: record.get(k) for k in spec}, spec, name)
        rejected = record['execution_status'] == 'NO_JIT'
        self.expect('execution_status_allowed', record['execution_status'] == 'OK' or
                    (synthetic and backend == 'kdlock' and rejected and record.get('jit_acceptance') == 'NO_JIT'
                     and record.get('jit_bodies') == 0), name)
        self.expect('final_session_drain', record['drained'] is True and not record.get('cleanup_error'), name)
        self.expect('error_verdict_preserved', bool(record.get('error')) if rejected else not record.get('error'), name)
        self.expect('ordinary_instrumentation', not any(record.get(k, False) for k in ('diagnostic', 'pmu', 'perf_record'))
                    and record.get('mutex_lock_offset') is None, name)
        self.equal('worker_prefix', record['cpus'], list(range(record['threads'])), name)
        if synthetic:
            self.equal('worker_numa_nodes', record['cpu_nodes'], [int(c >= 32) for c in record['cpus']], name)
        else:
            for field, filename in (('kernel_identity', 'kernel-identity.json'), ('topology_identity', 'topology.txt')):
                self.equal('api_runtime_identity', record[field], self.files['current/' + collection + '/' + filename], [name, field])
        for key, value in dict(duration_ms=2000, peak_window_ms=300, peak_settle_ms=300,
                               sample_ms=10, collector_cpu=63, lock_kind='mutex').items():
            self.equal('common_measurement_identity', record.get(key), value, [name, key])
        self.equal('final_worker_finish', m['finished_ns'], max(w['finished_ns'] for w in m['workers']), name)
        self.expect('worker_cpu_time', all(unsigned(w['cpu_ns']) and w['cpu_ns'] > 0 for w in m['workers']), name)
        raw = self.jread(name + '/measure.json')
        self.expect('raw_measurement_binding', all(m.get(k) == v for k, v in raw.items()), name)
        if synthetic:
            self.expect('synthetic_oracle', m['complete'] is True and m['data_ok'] is True and m['schema'] == 2, name)
            self.equal('synthetic_workload', (m['workload'], m['cachelines'], m['threads'], m['iterations']),
                       ('rcuht' if collection == 'rcuht' else 'cacheline',
                        0 if collection == 'rcuht' else int(collection[1:]), record['threads'], 0), name)
            before, after = m['before'], m['after']
            self.expect('payload_shape', len(before) == len(after) == 16, name)
            if collection == 'rcuht':
                self.expect('hash_oracle', m['hash_integrity_ok'] is True and all(a >= b for a, b in zip(after, before))
                            and after[0] - before[0] == count and before[0] == sum(before[1:4])
                            and after[0] == sum(after[1:4]) and not any(before[4:] + after[4:]), name)
                for field, wanted in dict(buckets=1024, entries=4096, key_range=8192, resched=0).items():
                    self.equal('hash_layout', record['layout'].get(field), wanted, [name, field])
            else:
                self.equal('cacheline_oracle', [a - b for a, b in zip(after, before)],
                           [count if i < int(collection[1:]) else 0 for i in range(16)], name)
            self.equal('worker_cpu_sum', m['worker_cpu_ns'], sum(w['cpu_ns'] for w in m['workers']), name)
            warm = self.jread(name + '/warmup.json')
            self.expect('synthetic_warmup', warm['complete'] is True and warm['data_ok'] is True and
                        warm['completed'] == record['threads'] * 48000 and
                        all(w['completed'] == 48000 for w in warm['workers']), name)
            self.equal('synthetic_drain_active', self.jread(name + '/drain.counts.json')['active'], 0, name)
            self.expect('synthetic_lock_geometry', record['layout']['lock_bytes'] == (24 if backend == 'tclock' else 32)
                        and record['layout']['lock_addr'] > 0 and record['layout']['lock_addr'] % 64 == 0, name)
            if 'lock_align' in record['layout']:
                self.equal('native_type_alignment', record['layout']['lock_align'], 8, name)
        else:
            self.expect('api_oracle', m['ok'] is True and m['phase'] == 'measure' and
                        record['redirected_calls'] == count == record['jit_eligible_operations'], name)
            self.equal('api_workload', (record['kind'], record['query'], record['entries'], record['value_size']),
                       ('seek', collection[5:], 16, 64) if collection.startswith('seek-') else (collection, 'query', 16, 64), name)
            self.equal('api_file_descriptions', record['file_descriptions'],
                       'shared-query' if collection.startswith('seek-') else 'per-worker', name)
            self.equal('api_learning_waves', record.get('learning_waves', []), [], name)
            self.equal('api_completion_probe_identity', (record['jit_evidence_version'], record['jit_completion_probe'], record['entry_abi']),
                       (2, backend == 'kdlock', 2 if backend == 'kdlock' else 0), name)
            warm = self.jread(name + '/warmup.json')
            self.expect('api_warmup', warm['ok'] is True and len(warm['workers']) == record['threads'] and
                        warm['completed'] == sum(w['completed'] for w in warm['workers']) and
                        all(w['completed'] >= 48000 and w['finished_ns'] >= warm['started_ns'] + 1000000000
                            for w in warm['workers']), name)
            for endpoint in ('check-before', 'check-after'):
                self.equal('api_boundary_oracle', self.jread(name + '/' + endpoint + '.json')['check'], True, [name, endpoint])
            self.equal('api_control_unbound', self.jread(name + '/unbind.json')['unbound'], True, name)
        whole, peak = self.peak(record, name)
        if synthetic:
            self.equal('synthetic_derived_fields', {k: record[k] for k in DERIVED},
                       dict(whole_throughput_ops_s=None if rejected else whole * 1e6,
                            whole_amortized_ns_op=None if rejected else m['wall_ns'] / count,
                            throughput_ops_s=None if rejected else peak['throughput_ops_s'],
                            amortized_ns_op=None if rejected else peak['amortized_ns_op'], score_eligible=not rejected), name)
        entries = record.get('jit_bodies', 0)
        self.expect('jit_body_bounds', unsigned(entries) and entries <= count, name)
        if synthetic:
            if backend != 'tclock':
                verdict = 'PASS' if entries else 'NO_JIT_LOW_CONTENTION' if backend == 'kdlock' and record['threads'] == 2 else 'NO_JIT'
                self.equal('original_synthetic_jit_acceptance', record.get('jit_acceptance'), verdict, name)
            else:
                self.equal('tclock_no_kd_acceptance', record.get('jit_acceptance'), None, name)
            self.equal('original_synthetic_execution_verdict', record['execution_status'],
                       'NO_JIT' if backend == 'kdlock' and record['threads'] >= 4 and not entries else 'OK', name)
        completions = None if synthetic else record['jit_completions']
        if completions is not None:
            self.expect('jit_return_bounds', unsigned(completions) and completions <= entries, name)
            verdict = ('PASS' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT') if backend == 'kdlock' else 'NOT_APPLICABLE'
            self.equal('original_api_jit_verdict', record['jit_status'], verdict, name)
            self.equal('api_require_jit_setting', record['require_jit'], False, name)
        logs = self.contents[name + '/kernel.log'].decode(errors='replace')
        self.expect('kernel_log_clean', not FAULT.search(logs), name)
        delegated, batch = None, None
        if backend == 'kdlock':
            self.equal('source_retirement', record['retired'], dict(state=2, modules=0, frames=0, writers=0), name)
            before_pub, after_pub = record['published_before'], record['published_after']
            self.equal('immutable_publication', before_pub, after_pub, name)
            self.equal('open_drained_publication', before_pub['source'], dict(state=0, modules=1, frames=0, writers=0), name)
            self.expect('mutex_image_admitted', before_pub['entry']['status'] == 0 and before_pub['entry']['entry_abi'] == 2
                        and before_pub['entry']['lock_kind'] == 2, name)
            for filename, digest in before_pub['images'].items():
                matches = [p for p in self.files if p.startswith(name + '/workspace/') and Path(p).name == filename
                           and self.files[p] == digest]
                self.expect('published_image_hash', bool(matches), [name, filename])
            parsed = {}
            for label, marker in (('physical', 'kd_mutex stats:'), ('tasks', 'kd_mutex tasks:')):
                selected = [line for line in logs.splitlines() if marker in line]
                self.equal('unique_kd_diagnostic_row', len(selected), 1, [name, label])
                parsed[label] = fields(selected[0])
            physical, tasks = parsed['physical'], parsed['tasks']
            self.expect('kd_exact_final_drain', physical['active_waiters'] == physical['reserved_nodes'] ==
                        physical['frame_failure'] == tasks['active_tasks'] == 0, name)
            self.equal('kd_physical_balance', physical['origin_acquires'], physical['origin_releases'], name)
            self.expect('no_auxiliary_diagnostics', 'kd_mutex aux:' not in logs, name)
            batch = physical['jit_success'] / physical['combiner'] if physical['combiner'] else None
            if synthetic:
                self.equal('synthetic_measured_entry_delta', record['jit_after'] - record['jit_before'], entries, name)
                self.expect('synthetic_entry_only_probe', record['parameters']['bench_complete_probe'] in ('N', '0'), name)
            else:
                self.expect('api_return_probe_enabled', record['probe_parameters']['bench_complete_probe'] in ('Y', '1'), name)
            evidence = ('WITNESSED_JIT' if entries else 'NO_JIT') if synthetic else (
                'RETURNED_JIT' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT')
        else:
            self.equal('non_kd_entry_count', entries, 0, name)
            self.expect('non_kd_no_provider_statistics', 'kd_mutex stats:' not in logs, name)
            evidence = 'NOT_APPLICABLE'
            if backend == 'tclock':
                if synthetic:
                    expected_keys = {'target_lock', 'komb_batch_size', 'quiescent', 'delegated', 'batches', 'parks'}
                    for endpoint in ('tclock_before', 'tclock_after', 'tclock_drained'):
                        self.equal('tclock_parameter_shape', set(record[endpoint]), expected_keys, [name, endpoint])
                        self.equal('tclock_quiescent', record[endpoint]['quiescent'], 1, [name, endpoint])
                    delegated = record['tclock_after']['delegated'] - record['tclock_before']['delegated']
                    self.equal('tclock_return_delta', record['delegated_bodies'], delegated, name)
                    self.equal('tclock_original_delegation_verdict', record['delegation_status'],
                               'PASS' if delegated else 'NO_DELEGATION_UNCONTENDED', name)
                    self.equal('tclock_original_delegation_share', record['delegation_share'], delegated / count, name)
                    self.expect('tclock_contended_delegation', record['threads'] < 4 or delegated > 0, name)
                    self.equal('tclock_worker_drain', self.jread(name + '/tclock-drain.counts.json')['active'], 0, name)
                else:
                    delegated = record['tclock_delegation']
                    self.expect('tclock_checked_unload_receipt', name + '/unload-tc.log' in self.files, name)
                self.expect('tclock_return_bounds', unsigned(delegated) and delegated <= count, name)
        identity = {k: record.get(k, 'unrecorded') for k in IDENTITY}
        result = dict(session_path=name, collection=collection, backend=backend, workload=collection,
                      workers=record['threads'], repeat=record['repeat'], evidence_class=evidence,
                      execution_status=record['execution_status'], score_eligible=not rejected,
                      whole_mops=whole, peak_mops=peak['throughput_ops_s'] / 1e6,
                      count=count, entries=entries, completions=completions, delegated=delegated,
                      bodies_per_combiner=batch, identity=identity, session_sha256=self.files[name + '/session.json'])
        self.sessions[name] = result
        self.records[name] = record
        return result

    def collections(self):
        matrix = self.jread('current/matrix.json')
        self.expect('matrix_complete_drained', matrix['passed'] is True and matrix['final_idle'] is True, 'current')
        self.equal('matrix_scope', (matrix['plain_sessions'], matrix['profile_sessions'], matrix['workers'], matrix['backends'], matrix['repeats']),
                   (567, 0, list(WORKERS), list(BACKENDS), 3), 'current')
        self.equal('matrix_helper_binding', matrix['script_sha256'], self.files['run-matrix.py'], 'current')
        self.equal('matrix_bounded_scope', (matrix['full_suite'], matrix['collection_timeout_seconds'],
                                           matrix['total_timeout_seconds']), (False, 1800, 9000), 'current')
        source_commit = self.revision(matrix['source_commit'])
        self.equal('collection_inventory', [r['collection'] for r in matrix['commands']], list(COLLECTIONS), 'current')
        receipts, kernel_reference = [], None
        for collection in COLLECTIONS:
            folder = 'current/' + collection
            synthetic = collection in ('c01', 'c08', 'rcuht')
            identity = self.jread(folder + ('/baseline.json' if synthetic else '/kernel-identity.json'))
            self.expect('verified_running_kernel', identity['ok'] is True and identity['config'] is True and
                        isinstance(identity['running_build_id'], str) and bool(identity['running_build_id']), collection)
            if kernel_reference is None:
                kernel_reference = identity
            self.equal('all_collections_same_kernel', identity, kernel_reference, collection)
            if synthetic:
                environment = self.jread(folder + '/environment.json')
                self.equal('synthetic_kernel_receipt', {k: environment['kernel_identity'][k] for k in identity}, identity, collection)
                self.equal('synthetic_topology_cpus', environment['topology']['role_cpus'], list(range(60)), collection)
                self.equal('synthetic_topology_nodes', environment['topology']['role_nodes'], [int(c >= 32) for c in range(60)], collection)
                bundle = self.jread(folder + '/kernel-baseline/manifest.json')
                for path, digest in bundle['bundle_files'].items():
                    self.expect('kernel_bundle_safe_path', safe_relative(path), [collection, path])
                    self.equal('kernel_bundle_hash', self.files.get(folder + '/kernel-baseline/' + path), digest, [collection, path])
                self.equal('kernel_bundle_running_binding', bundle['running']['build_id'], identity['running_build_id'], collection)
            else:
                topology = self.contents[folder + '/topology.txt'].decode()
                rows = [line.split() for line in topology.splitlines() if line.split() and line.split()[0].isdigit()]
                self.equal('api_topology_cpu_nodes', [(int(r[0]), int(r[1])) for r in rows],
                           [(c, int(c >= 32)) for c in range(64)], collection)
            command = self.jread(folder + '-command.json')
            self.equal('command_matrix_binding', command, next(r for r in matrix['commands'] if r['collection'] == collection), collection)
            self.equal('command_source_binding', self.revision(command['source_commit']), source_commit, collection)
            python = command['argv'][0]
            self.expect('collector_python', Path(python).name.startswith('python'), collection)
            self.equal('collector_command_argv', command['argv'], collector_command(python, collection,
                       self.guest_base + 'current/' + collection), collection)
            self.equal('collector_command_context', (command['cwd'], command['timeout_seconds']),
                       ('/root/host_fs/kdlock', 1800), collection)
            self.expect('collector_command_duration', command['finished_unix'] >= command['started_unix'], collection)
            self.expect('command_complete_drained', command['expected_sessions'] == 81 and command['execution_inventory_complete'] is True
                        and command['all_drained'] is True and command['idle_after'] is True, collection)
            records, plan = self.jread(folder + '/records.json'), self.jread(folder + '/plan.json')
            expected = {(b, w, r) for b in BACKENDS for w in WORKERS for r in range(3)}
            self.equal('collection_plan_names', [r['name'] for r in records], [r['name'] for r in plan], collection)
            self.equal('collection_record_count', len(records), 81, collection)
            self.equal('collection_backend_worker_repeats', {(r['arm'], r['threads'], r['repeat']) for r in records}, expected, collection)
            rejected = [r['name'] for r in records if r['execution_status'] == 'NO_JIT']
            self.equal('retained_rejection_names', command['non_jit_rejections'], rejected, collection)
            self.equal('original_status_counts', command['original_execution_status_counts'], dict(Counter(r['execution_status'] for r in records)), collection)
            self.equal('command_original_exit', command['exit_code'], int(bool(rejected)), collection)
            if rejected:
                failure = self.jread(folder + '/failure.json')
                self.equal('retained_original_failure', (failure['status'], failure['sessions']), ('NO_JIT', rejected), collection)
            source_id = sha(json.dumps(self.jread(folder + '/source-sha256.json'), sort_keys=True).encode())
            for record, spec in zip(records, plan):
                try:
                    if not synthetic:
                        self.equal('api_source_identity', record['source_identity'], source_id, record['name'])
                    result = self.session(record, spec, collection)
                    result.update(source_identity=source_id, source_commit=source_commit)
                except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as error:
                    self.expect('session_data_exception', False, dict(collection=collection, name=record.get('name'), error=str(error)))
            receipts.append(dict(collection=collection, source_identity=source_id, sessions=len(records),
                                 rejections=rejected, records_sha256=self.files[folder + '/records.json'],
                                 source_manifest_sha256=self.files[folder + '/source-sha256.json'],
                                 command_sha256=self.files[folder + '-command.json']))
        self.equal('matrix_rejection_count', matrix['non_jit_rejections'], sum(len(r['rejections']) for r in receipts))
        self.equal('audited_session_count', len(self.sessions), 567)
        self.equal('reconstructed_window_count', len(self.windows), 567)
        return receipts

    def checks_and_health(self):
        check = self.jread('checks/result.json')
        commands = self.jread('checks/commands.json')
        self.expect('fresh_checks_complete', check['passed'] is True and check['final_idle'] is True and
                    check['source_unchanged'] is True and check['full_suite'] is False, 'checks')
        self.equal('fresh_checks_source', self.revision(check['source_revision']), self.revision(self.args.expect_source))
        self.equal('fresh_checks_scope', (check['unit_basic'], check['unit_drivers'], check['runner_tests']),
                   (2, [], ['bench/tclock_compare/test_direct.py', 'bench/spin_cacheline/test_peak.py',
                            'bench/real_api/test_plan.py', 'bench/real_api/test_report.py']))
        self.equal('fresh_checks_helper_binding', check['script_sha256'], self.files['run-checks.py'])
        self.equal('fresh_checks_command_copy', check['commands'], commands)
        self.equal('fresh_checks_commands', [r['name'] for r in commands],
                   ['dependencies', 'provider', 'daemon', 'unit', 'test_direct', 'test_peak', 'test_plan', 'test_report'])
        self.expect('fresh_checks_exits', all(r['exit_code'] == 0 for r in commands), 'checks')
        python = commands[0]['argv'][0]
        root, frozen = '/root/host_fs/kdlock', self.guest_base + 'checks/source'
        wanted = [
            ('dependencies', [python, '-m', 'pip', 'check'], root, 60),
            ('provider', ['make', '-C', 'kernel_module', 'KDIR=/root/linux-6.1.159-kdclobber2', 'W=1', 'UBSAN_SANITIZE=n'], frozen, 240),
            ('daemon', ['make', '-C', 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'], frozen, 60),
            ('unit', ['make', '-C', 'tests/unit', 'run', 'PY_TESTS='], frozen, 300)]
        wanted += [(Path(path).stem, [python, path], frozen, 180) for path in check['runner_tests']]
        self.expect('fresh_checks_python', Path(python).name.startswith('python'), 'checks')
        for command, expected in zip(commands, wanted):
            self.equal('fresh_checks_exact_command', tuple(command[k] for k in ('name', 'argv', 'cwd', 'timeout_seconds')), expected)
            self.expect('fresh_checks_duration', command['finished_unix'] >= command['started_unix'], command['name'])
        self.equal('basic_program_results', re.findall(r'Unit tests: (\d+) passed, (\d+) failed', self.contents['checks/unit.log'].decode()), [('2', '0')])
        runner_counts = {}
        for name in ('test_direct', 'test_peak', 'test_plan', 'test_report'):
            log = self.contents['checks/' + name + '.log'].decode()
            totals = re.findall(r'(?m)^Ran (\d+) tests? in ', log)
            source_path = next(p for p in check['runner_tests'] if Path(p).stem == name)
            tree = ast.parse(self.contents['checks/source/' + source_path].decode())
            declared = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(tree))
            self.expect('runner_test_result', totals == [str(declared)] and declared > 0 and
                        re.search(r'(?m)^OK$', log) is not None and 'skipped=' not in log and
                        not re.search(r'(?m)^FAILED|^ERROR:', log), name)
            runner_counts[name] = int(totals[0]) if len(totals) == 1 else None
        health = self.jread(self.archive['health_path'])
        self.expect('final_health_idle_boot', health['idle'] is True and health['boot_id'] == self.archive['boot_id'], 'health')
        logs = {name: digest for name, digest in self.files.items() if name.endswith('/kernel.log')}
        self.equal('health_kernel_log_inventory', health['kernel_logs'], logs)
        faults = []
        for name in logs:
            if FAULT.search(self.contents[name].decode(errors='replace')):
                faults.append(name)
        self.equal('all_kernel_logs_clean', faults, [])
        self.equal('current_session_log_count', len([n for n in logs if n.startswith('current/')]), 567)
        return dict(unit_basic=2, unit_drivers=0, runner_tests=runner_counts, kernel_logs=len(logs), kernel_faults=faults)

    def summary_audit(self, collections):
        comparison = self.jread('comparison.json')
        self.expect('summary_complete', comparison['complete'] is True and comparison['issues'] == [], 'comparison')
        self.equal('summary_analysis_helper', comparison['analysis_helper'], dict(file='summarize.py', sha256=self.files['summarize.py']))
        self.equal('summary_source', self.revision(comparison['source_commit']), self.revision(self.args.expect_source))
        self.equal('summary_backends_workers', (comparison['backends'], comparison['workers']), (list(BACKENDS), list(WORKERS)))
        self.equal('summary_session_inventory', [r['session_path'] for r in comparison['sessions']], list(self.sessions))
        self.equal('summary_collection_inventory', [r['collection'] for r in comparison['collections']], list(COLLECTIONS))
        for observed, actual in zip(comparison['collections'], collections):
            for key in ('collection', 'source_identity', 'sessions', 'records_sha256', 'source_manifest_sha256', 'command_sha256'):
                self.equal('summary_collection_binding', observed[key], actual[key], [actual['collection'], key])
            self.equal('summary_collection_issues', observed['issues'], [], actual['collection'])
        grouped = {}
        for row in comparison['sessions']:
            name = row['session_path']; actual = self.sessions[name]; record = self.records[name]
            mappings = {'collection':'collection', 'workload':'workload', 'backend':'backend', 'threads':'workers',
                        'repeat':'repeat', 'source_identity':'source_identity', 'execution_status':'execution_status',
                        'score_eligible':'score_eligible', 'jit_class':'evidence_class', 'completed':'count',
                        'jit_bodies':'entries', 'jit_completions':'completions', 'tclock_delegated':'delegated',
                        'observed_whole_mops':'whole_mops', 'measured_peak_mops':'peak_mops', 'session_sha256':'session_sha256'}
            for reported, derived in mappings.items():
                self.equal('summary_session_value', row[reported], actual[derived], [name, reported])
            self.equal('summary_session_source', self.revision(row['source_commit']), actual['source_commit'], name)
            self.equal('summary_session_integrity', (row['valid'], row['issues'], row['drained']), (True, [], True), name)
            self.equal('summary_rejected_verdict', row['retained_no_jit_rejection'], actual['execution_status'] == 'NO_JIT', name)
            self.equal('summary_original_jit_verdict', row['original_jit_verdict'], record.get(
                       'jit_acceptance' if row['collection'] in ('c01', 'c08', 'rcuht') else 'jit_status'), name)
            self.equal('summary_wall_ns', row['wall_ns'], record['measurement']['wall_ns'], name)
            self.equal('summary_identity_fields', row['identity'], {k: record.get(k) for k in row['identity']}, name)
            self.equal('summary_layout', row['layout'], record.get('layout'), name)
            kd = actual['backend'] == 'kdlock'; tc = actual['backend'] == 'tclock'; count = actual['count']
            self.equal('summary_body_share', row['measured_body_entry_share'], actual['entries'] / count if kd else None, name)
            self.equal('summary_return_share', row['measured_returned_jit_share'],
                       actual['completions'] / count if kd and actual['completions'] is not None else None, name)
            self.equal('summary_tclock_share', row['measured_tclock_delegation_share'], actual['delegated'] / count if tc else None, name)
            diag = row['whole_session_diagnostics']; text = self.contents[name + '/kernel.log'].decode(errors='replace')
            self.equal('summary_diagnostic_hash', diag['sha256'], self.files[name + '/kernel.log'], name)
            self.equal('summary_diagnostic_clean', (diag['present'], diag['fault_count'], diag['fault_examples'], diag['issues']),
                       (True, 0, [], []), name)
            for field, marker in (('mutex_stats', 'kd_mutex stats:'), ('mutex_tasks', 'kd_mutex tasks:')):
                lines = [line for line in text.splitlines() if marker in line]
                self.equal('summary_whole_session_counter', diag[field], fields(lines[0]) if len(lines) == 1 else None, [name, field])
            self.equal('summary_batch_ratio', diag['bodies_per_combiner'], actual['bodies_per_combiner'], name)
            key = (actual['collection'], actual['backend'], actual['workers'], actual['evidence_class'])
            grouped.setdefault(key, []).append(actual)
        exported = {(g['collection'], g['backend'], g['threads'], g['jit_class']):g for g in comparison['groups']}
        self.equal('group_inventory', sorted(exported), sorted(grouped))
        self.equal('unique_group_count', len(exported), len(comparison['groups']))
        reconstructed = []
        for key, values in sorted(grouped.items()):
            original = exported[key]
            identities = {canonical(v['identity']) for v in values}
            self.equal('group_identity_count', len(identities), 1, list(key))
            self.equal('group_source_count', len({v['source_identity'] for v in values}), 1, list(key))
            eligible = [v for v in values if v['score_eligible']] if len(identities) == 1 else []
            status = ('COMPLETE' if len(eligible) == 3 else 'REJECTED_NO_JIT' if all(not v['score_eligible'] for v in values)
                      else 'MIXED_IDENTITY' if len(identities) != 1 else 'INCOMPLETE_CLASS')
            self.equal('group_status_counts', (original['status'], original['planned'], original['collected'], original['valid'], original['repeats']),
                       (status, 3, len(values), len(eligible), [v['repeat'] for v in eligible]), list(key))
            self.equal('group_whole_statistics', original['whole_mops'], stats([v['whole_mops'] for v in eligible]), list(key))
            self.equal('group_peak_statistics', original['peak_mops'], stats([v['peak_mops'] for v in eligible]), list(key))
            self.equal('group_batch_statistics', original['whole_session_bodies_per_combiner'],
                       stats([v['bodies_per_combiner'] for v in eligible if v['bodies_per_combiner'] is not None]), list(key))
            total = sum(v['count'] for v in eligible)
            for field, selected in (('measured_body_entry_share', 'entries'), ('measured_returned_jit_share', 'completions'),
                                    ('measured_tclock_delegation_share', 'delegated')):
                wanted = (sum(v[selected] for v in eligible) / total if total and all(unsigned(v[selected]) for v in eligible)
                          and (key[1] == 'kdlock' if selected != 'delegated' else key[1] == 'tclock') else None)
                self.equal('group_measured_share', original[field], wanted, [list(key), field])
            reconstructed.append(dict(collection=key[0], backend=key[1], threads=key[2], jit_class=key[3],
                                      status=status, whole_mops=stats([v['whole_mops'] for v in eligible]),
                                      peak_mops=stats([v['peak_mops'] for v in eligible])))
        self.equal('summary_status_totals', comparison['execution_status_counts'], dict(Counter(v['execution_status'] for v in self.sessions.values())))
        self.equal('summary_class_totals', comparison['execution_class_counts'], dict(Counter(v['evidence_class'] for v in self.sessions.values())))
        self.equal('summary_score_count', comparison['score_eligible_sessions'], sum(v['score_eligible'] for v in self.sessions.values()))
        self.equal('summary_rejection_count', comparison['retained_no_jit_rejections'], sum(not v['score_eligible'] for v in self.sessions.values()))
        lines = ['| Workload | Backend | Workers | Class | Eligible repeats | Whole Mops/s median [min, max] | Status |',
                 '| --- | --- | ---: | --- | ---: | ---: | --- |']
        for row in reconstructed:
            values = row['whole_mops']
            formatted = '—' if not values['n'] else f"{values['median']:.3f} [{values['min']:.3f}, {values['max']:.3f}]"
            lines.append(f"| {row['collection']} | {row['backend']} | {row['threads']} | {row['jit_class']} | {values['n']} | {formatted} | {row['status']} |")
        self.equal('table_exact_arithmetic', self.contents['comparison-table.md'].decode(), '\n'.join(lines) + '\n')
        return reconstructed

    def finalization_bindings(self):
        validation, health = self.jread('validation.json'), self.jread('health.json')
        self.expect('validation_complete', validation['passed'] is True and validation['full_suite'] is False, 'validation')
        self.equal('validation_source', self.revision(validation['source_revision']), self.revision(self.args.expect_source))
        self.equal('validation_helper_binding', (validation['helper_file'], validation['helper_sha256']), ('finalize.py', self.files['finalize.py']))
        self.equal('validation_matrix_binding', validation['matrix_sha256'], self.files['current/matrix.json'])
        self.equal('validation_comparison_binding', validation['comparison_sha256'], self.files['comparison.json'])
        self.equal('health_validation_binding', health['validation_sha256'], self.files['validation.json'])
        self.equal('health_comparison_binding', health['comparison_sha256'], self.files['comparison.json'])
        for collection, receipt in validation['collection_manifests'].items():
            for field, path in (('source_manifest_sha256', 'current/' + collection + '/source-sha256.json'),
                                ('records_sha256', 'current/' + collection + '/records.json'),
                                ('command_sha256', 'current/' + collection + '-command.json')):
                self.equal('validated_collection_bytes', receipt[field], self.files[path], path)
        checked = validation['checks']
        for field, path in (('result_sha256', 'checks/result.json'), ('commands_sha256', 'checks/commands.json'),
                            ('source_manifest_sha256', 'checks/source-sha256.json')):
            self.equal('validated_check_bytes', checked[field], self.files[path], path)
        for name, digest in checked['logs_sha256'].items():
            self.equal('validated_check_log', digest, self.files['checks/' + name + '.log'], name)
        self.equal('validation_no_claimed_live_probes', checked['live_probes_rerun'], False)
        for name, digest in health['guest_receipts_sha256'].items():
            self.equal('guest_receipt_binding', digest, self.files[name], name)
            text = self.contents[name].decode()
            self.equal('guest_receipt_boot', re.findall(r'(?m)^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$', text),
                       [self.archive['boot_id']], name)
            self.expect('guest_kernel_identity', '6.1.159-kdclobber2' in text and 'nokaslr' in text and 'nopvspin' in text
                        and '(voluntary)' in text and re.search(r'(?m)^0-63$', text) is not None, name)
        self.equal('guest_receipt_actual_scope', set(health['guest_receipts_sha256']), {'guest-during.log', 'guest-after.log'})
        before, after = self.jread('host-before.json'), self.jread('host-after.json')
        self.expect('real_recovery_snapshot', before['snapshot_listed'] and after['snapshot_listed'] and
                    before['recovery_snapshot'] == after['recovery_snapshot'] == health['snapshot'], 'host')
        self.equal('host_frequency_stable', before['cpufreq'], after['cpufreq'])
        self.equal('host_numa_stable', before['numa'], after['numa'])
        self.expect('single_qemu', len(before['qemu']) == len(after['qemu']) == 1, 'host')
        left, right = before['qemu'][0], after['qemu'][0]
        self.equal('qemu_identity', (left['pid'], left['args']), (right['pid'], right['args']))
        bt, at = ({t['tid']: t for t in q['tasks']} for q in (left, right))
        self.equal('vcpu_pins_stable', {k:v for k,v in bt.items() if v['comm'].startswith('CPU ')},
                   {k:v for k,v in at.items() if v['comm'].startswith('CPU ')})
        self.expect('retained_qemu_tasks_stable', all(bt[k] == at[k] for k in bt.keys() & at.keys()), 'host')
        self.expect('service_threads_collector_only', all(t['affinity'] == [63] for t in [*bt.values(), *at.values()]
                    if not t['comm'].startswith('CPU ')), 'host')
        for label, path in (('before_sha256', 'host-before.json'), ('after_sha256', 'host-after.json')):
            self.equal('host_receipt_binding', health['topology'][label], self.files[path], path)
        plot_receipts = [n for n in self.files if PurePosixPath(n).name == 'mutex-comparison.json']
        self.equal('plot_receipt_count', len(plot_receipts), 1)
        for name in plot_receipts:
            plot = self.jread(name); folder = PurePosixPath(name).parent
            self.equal('plot_comparison_binding', plot['comparison_sha256'], self.files['comparison.json'], name)
            self.equal('plot_helper_binding', plot['script_sha256'], self.files['plot.py'], name)
            for output, digest in plot['outputs'].items():
                self.expect('plot_safe_basename', Path(output).name == output, output)
                self.equal('plot_output_bytes', digest, self.files.get(str(folder / output)), output)

    def run(self):
        self.windows, self.sessions, self.records = [], {}, {}
        results = {}
        steps = [('archives', self.load_archives), ('manifests', self.manifests)]
        for name, action in steps:
            try:
                results[name] = action()
            except Exception as error:
                self.expect('audit_phase_exception', False, dict(phase=name, error=repr(error)))
                return results
        for name, action in (
            ('source', lambda: self.source_audit(results['manifests'][0])),
            ('jit', self.jit_audit), ('collections', self.collections),
            ('checks', self.checks_and_health),
            ('summary_groups', lambda: self.summary_audit(results['collections'])),
            ('finalization', self.finalization_bindings),
        ):
            try:
                results[name] = action()
            except Exception as error:
                self.expect('audit_phase_exception', False, dict(phase=name, error=repr(error)))
        for path in self.report.rglob('*'):
            if path.is_file() and not path.is_symlink():
                name = str(path.relative_to(self.report))
                if name in self.files:
                    self.equal('compact_copy_binding', hashfile(path), self.files[name], name)
                elif name == 'archives.json':
                    self.equal('compact_archive_manifest', hashfile(path), hashfile(self.raw / 'archives.json'), name)
        return results


WORKERS = (1, 2, 4, 8, 16, 32, 36, 48, 60)
BACKENDS = ('native', 'tclock', 'kdlock')
COLLECTIONS = ('c01', 'c08', 'rcuht', 'seek-set', 'seek-end', 'pipebytes', 'pipecap')
DERIVED = {'whole_throughput_ops_s', 'whole_amortized_ns_op', 'throughput_ops_s', 'amortized_ns_op', 'score_eligible'}
IDENTITY = ('source_identity', 'kernel_identity', 'topology_identity', 'cpus', 'cpu_nodes', 'collector_cpu',
            'collector_shared', 'duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms', 'workload',
            'cachelines', 'kind', 'query', 'entries', 'value_size', 'file_descriptions', 'lock_kind',
            'caller_abi', 'caller_shell', 'cookie_storage', 'entry_abi', 'mutex_implementation',
            'cpu_heat_policy', 'spin_entry_ratio_limit', 'spin_prefetch', 'kd_provider_ubsan',
            'numa_policy', 'delegation_batch_limit', 'warmup_policy', 'warmup_iterations_per_worker',
            'warmup', 'warmup_ms', 'helper_waves', 'helper_cpus', 'jit_evidence_version',
            'jit_completion_probe', 'mutex_lock_offset', 'diagnostic', 'pmu', 'perf_record')
FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|unable to handle|'
                   r'general protection fault|Oops:|\[ERROR\]|invariant_failures=[1-9]|runtime error:|KASAN:|UBSAN:', re.I)


def collector_command(python, collection, output):
    common = ['--backends', *BACKENDS, '--threads', *map(str, WORKERS), '--repeats', '3',
              '--duration-ms', '2000', '--collector-cpu', '63']
    if collection in ('c01', 'c08', 'rcuht'):
        command = [python, 'bench/tclock_compare/run_mutex.py', '--cpus', '0-59',
            '--peak-window-ms', '300', '--peak-settle-ms', '300', '--sample-ms', '10',
            '--iterations', '100000', '--numa', 'on', '--kd-batch-size', '1024',
            '--kd-provider-ubsan', 'off', '--spin-prefetch', '2', '--spin-entry-ratio-limit', '2',
            '--spin-delegate', 'on', '--scenario', 'plain', '--keep-going-no-jit', *common]
        command += ['--workload', 'rcuht'] if collection == 'rcuht' else [
            '--workload', 'cacheline', '--cachelines', str(int(collection[1:]))]
    else:
        kind, query = ('seek', collection[5:]) if collection.startswith('seek-') else (collection, 'query')
        command = [python, 'bench/real_api/run.py', '--cpus', ','.join(map(str, range(60))),
            '--entries', '16', '--value-size', '64', '--warmup', '48000', '--warmup-ms', '1000',
            '--helper-waves', '4', '--helper-workers', '8', *common, '--kinds', kind, '--queries', query]
    return [*command, '--output', output]


def same(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(same(left[k], right[k]) for k in left)
    if isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right if type(left) is type(right) is int else (
            math.isfinite(left) and math.isfinite(right) and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-15))
    return type(left) is type(right) and left == right


def unsigned(value):
    return type(value) is int and value >= 0


def fields(line):
    return {key: int(value) for key, value in re.findall(r'(\w+)=(-?\d+)\b', line)}


def stats(values):
    ordered = sorted(values)
    n = len(ordered)
    return dict(n=n, min=ordered[0] if n else None, max=ordered[-1] if n else None,
                median=(ordered[(n - 1) // 2] + ordered[n // 2]) / 2 if n else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expect-source', required=True, help='exact committed collection source')
    parser.add_argument('--runtime-source', default='752fec1', help='retained production revision before report-only changes')
    parser.add_argument('--output', type=Path, help='new receipt path; an existing receipt is never overwritten')
    args = parser.parse_args()
    output = (args.output or args.report / 'offline-review.json').resolve()
    if output.exists() or output.is_relative_to(args.raw.resolve()) or not output.is_relative_to(args.report.resolve()):
        raise ValueError('audit output must be a new path inside --report, outside retained raw inputs')
    audit = Audit(args)
    result = audit.run()
    receipt = dict(schema=1, passed=not audit.issues, host=socket.gethostname(),
        scope='Independent inert-byte/Git-object/source/arithmetic audit; no retained code, binaries, modules, builds, tests or VM commands executed.',
        script_sha256=hashfile(Path(__file__)), archives_manifest_sha256=hashfile(args.raw / 'archives.json'),
        inventory_sha256=hashfile(args.raw / 'input-inventory.json'), checks=dict(audit.counts), issues=audit.issues,
        total_checks=sum(audit.counts.values()), inventory_members=len(audit.inventory), members=len(audit.members),
        regular_files=len(audit.files), regular_file_hash_map_sha256=canonical(audit.files),
        audited_sessions=len(audit.sessions), reconstructed_windows=len(audit.windows), windows=audit.windows,
        results=result,
        limits=['Synthetic KD counters witness entry, not returned execution; API return counters are measured-phase evidence.',
                'API TCLock final drain is retained through successful checked runner/unbind/unload receipts; no absent numeric parameter snapshot is invented.',
                'Peak windows are independently selected using exact fractions; whole-run shares do not describe selected peaks.',
                'Warmup/check-inclusive batch ratios are diagnostics, not batch-size distributions.',
                'No persisted initial guest preflight was available; guest-during and guest-after receipts retain their actual observation scope.',
                'Archive stat inventory preserves metadata; tar hashes bind content, with independent source/ELF/JIT/receipt hashes.',
                'Source, workload, backend and execution classes are not pooled; rejected NO_JIT timings remain unscored.'])
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str, allow_nan=False) + '\n')
    print(json.dumps(dict(passed=receipt['passed'], checks=receipt['total_checks'], issues=len(audit.issues),
                         members=len(audit.members), files=len(audit.files), sessions=len(audit.sessions),
                         windows=len(audit.windows), output=str(output))))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
