#!/usr/bin/env python3
"""Read captured validation/profile archives without executing project code.

Usage: validation-report.py ARCHIVES_JSON RAW_FOLDER NEW_OUTPUT_DIRECTORY
Reads the tests, metadata and profiles archive groups. Missing final evidence is
reported as MISSING, never converted into a pass. This offline report does not
run tests, modules, guest commands or captured source, and does not score profiles.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


GROUPS = ('tests', 'metadata', 'profiles')
JSON_NAMES = {'plan.json', 'records.json', 'summary.json', 'parity.json', 'result.json', 'environment.json',
    'source-sha256.json', 'source-manifest.json', 'binary-sha256.json', 'baseline.json', 'health.json',
    'diagnostic.json', 'commands.json', 'function-count-summary.json', 'controls-final.json',
    'controls-before.json', 'restore.json', 'aggregate.json', 'raw-profile-sha256.json'}
MANIFESTS = {'source-sha256.json', 'source-manifest.json', 'binary-sha256.json'}
PROBE_12 = dict(errors=0, api_checks=8, readers_slept=2, writer_slept=1, late_reader_slept=1,
    cancellation_checks=10, colocated=1, idle=1, outer_readers_slept=2, outer_writer_slept=1,
    downgrade_checks=1, publication_checks=3)
FINAL_NAMES = ('xlong-probe', 'final-basic', 'final-functional', 'final-local', 'final-jit')
FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|'
                   r'Oops:|general protection fault|unable to handle|\[ERROR\]|\[KD_JIT\]\[ERROR\]|'
                   r'invariant_failures=[1-9]|KASAN:|UBSAN:|blocked for more than', re.I)


def sha_file(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            value.update(chunk)
    return value.hexdigest()


def safe_path(value, absolute=False):
    path = PurePosixPath(value)
    if path.is_absolute() != absolute or '..' in path.parts or '\x00' in value or str(path) in ('.', '/'):
        raise ValueError('unsafe path: ' + value)
    return path


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


class Audit:
    def __init__(self):
        self.counts = Counter()
        self.failures = []
        self.missing = []

    def check(self, value, label, context):
        self.counts[label] += 1
        if not value:
            self.failures.append(dict(check=label, context=context))
        return bool(value)


class Evidence:
    def __init__(self, capture, folder, audit):
        self.capture, self.audit = capture, audit
        self.prefix = safe_path(capture['archive_prefix'])
        self.guest_base = safe_path(capture['guest_base'], True)
        self.hashes, self.links, self.objects, self.logs, self.archives = {}, {}, {}, {}, []
        self.kernel_logs = []
        saved_bytes = 0
        audit.check(capture.get('completed') is True and capture.get('guest_idle') is True,
                    'completed idle archive capture', 'archives.json')
        for group in GROUPS:
            entries = [row for row in capture.get('groups', []) if row['group'] == group]
            if len(entries) != 1:
                audit.missing.append(dict(context=group, files=['unique archive capture receipt']))
                continue
            receipt = entries[0]
            filename = safe_path(receipt['file'])
            if len(filename.parts) != 1:
                raise ValueError('archive filename must be a basename')
            path = folder / str(filename)
            if not path.is_file():
                audit.missing.append(dict(context=group, files=[str(path)]))
                continue
            before = path.stat()
            actual_hash = sha_file(path)
            okay = audit.check(actual_hash == receipt['sha256'] and before.st_size == receipt['bytes'],
                               'compressed archive guest hash', group)
            self.archives.append(dict(group=group, path=str(path.resolve()), sha256=actual_hash,
                                      bytes=before.st_size, guest_hash_matches=okay))
            if not okay:
                continue
            seen = set()
            with tarfile.open(path, 'r|gz') as archive:
                for member in archive:
                    name = safe_path(member.name)
                    if not name.is_relative_to(self.prefix):
                        raise ValueError('member outside capture prefix: ' + member.name)
                    relative = str(name.relative_to(self.prefix))
                    if relative in seen:
                        raise ValueError('duplicate archive member: ' + member.name)
                    seen.add(relative)
                    if member.isdir():
                        continue
                    if relative in self.hashes or relative in self.links:
                        raise ValueError('duplicate path across archive groups: ' + relative)
                    if member.issym() or member.islnk():
                        self.links[relative] = dict(target=member.linkname, hard=member.islnk())
                        continue
                    if not member.isfile():
                        raise ValueError('special file in archive: ' + member.name)
                    is_json = name.name in JSON_NAMES or name.name.endswith('.command.json')
                    is_log = name.name in ('basic.log', 'kernel.log')
                    keep = is_json or is_log
                    if keep:
                        if member.size > 128 << 20 or saved_bytes + member.size > 768 << 20:
                            raise ValueError('receipt memory bound exceeded: ' + relative)
                        saved_bytes += member.size
                    value, content = hashlib.sha256(), bytearray()
                    stream = archive.extractfile(member)
                    read = 0
                    for chunk in iter(lambda: stream.read(1 << 20), b''):
                        value.update(chunk)
                        read += len(chunk)
                        if keep:
                            content.extend(chunk)
                    if read != member.size:
                        raise ValueError('truncated member: ' + member.name)
                    self.hashes[relative] = value.hexdigest()
                    if is_json:
                        self.objects[relative] = json.loads(content)
                    if is_log:
                        self.logs[relative] = content.decode(errors='replace')
                        if name.name == 'kernel.log':
                            faults = [line for line in self.logs[relative].splitlines() if FAULT.search(line)]
                            self.kernel_logs.append(dict(path=relative, sha256=value.hexdigest(), faults=faults))
                            audit.check(not faults, 'retained per-session kernel log has no fault', relative)
            audit.check(path.stat().st_size == before.st_size and path.stat().st_mtime_ns == before.st_mtime_ns
                        and sha_file(path) == actual_hash, 'archive remained unchanged', group)
        self.manifests = []
        for path, manifest in self.objects.items():
            name = PurePosixPath(path)
            if name.name not in MANIFESTS:
                continue
            okay = audit.check(isinstance(manifest, dict) and bool(manifest), 'nonempty source/binary manifest', path)
            if not okay:
                continue
            binary = name.name == 'binary-sha256.json'
            failures = len(audit.failures)
            for source, expected in manifest.items():
                audit.check(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'SHA256 manifest value', path)
                if binary:
                    absolute = safe_path(source, True)
                    if not absolute.is_relative_to(self.guest_base):
                        audit.check(False, 'binary within captured guest base', source)
                        continue
                    target = str(absolute.relative_to(self.guest_base))
                else:
                    target = str(name.parent / 'source' / safe_path(source))
                audit.check(self.member_hash(target) == expected, 'captured source/binary hash', target)
            self.manifests.append(dict(path=path, files=len(manifest), kind='binary' if binary else 'source',
                raw_manifest_sha256=self.hashes[path], passed=len(audit.failures) == failures))

    def member_hash(self, path, seen=()):
        if path in seen:
            raise ValueError('cyclic archive hard link: ' + path)
        if path in self.hashes:
            return self.hashes[path]
        link = self.links.get(path)
        if not link or not link['hard']:
            return None
        target = safe_path(link['target'])
        if not target.is_relative_to(self.prefix):
            raise ValueError('hard link outside archive prefix')
        return self.member_hash(str(target.relative_to(self.prefix)), (*seen, path))

    def needed(self, root, names):
        missing = [name for name in names if str(PurePosixPath(root) / name) not in self.objects and
                   str(PurePosixPath(root) / name) not in self.logs]
        if missing:
            self.audit.missing.append(dict(context=root, files=missing))
        return not missing

    def provenance(self, root):
        source = self.objects.get(root + '/source-sha256.json')
        binary = self.objects.get(root + '/binary-sha256.json')
        environment = self.objects.get(root + '/environment.json', {})
        return dict(source_manifest_sha256=self.hashes.get(root + '/source-sha256.json'),
            source_content_id=hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                if source else None, source_files=len(source) if source else 0,
            binary_manifest_sha256=self.hashes.get(root + '/binary-sha256.json'), binary_files=len(binary) if binary else 0,
            kernel_identity=environment.get('kernel_identity', self.objects.get(root + '/baseline.json')),
            topology=environment.get('topology'), cmdline=environment.get('cmdline'),
            snapshot_tag=environment.get('snapshot_tag'))


def command_receipt(evidence, name):
    path = name + '.command.json'
    if path not in evidence.objects:
        evidence.audit.missing.append(dict(context=name, files=[path]))
        return None
    receipt = evidence.objects[path]
    evidence.audit.check(receipt.get('returncode') == 0, 'command returned zero', name)
    return dict(**receipt, receipt_sha256=evidence.hashes[path])


def probe_result(evidence, name, selected=False):
    start = len(evidence.audit.failures)
    command = command_receipt(evidence, name)
    if not evidence.needed(name, ('result.json', 'local/result.json', 'source-sha256.json', 'binary-sha256.json')):
        return dict(name=name, selected=selected, status='MISSING', command=command)
    expected = dict(PROBE_12)
    if name == 'grant-probe':
        expected.update(publication_checks=4, reader_grant_checks=1)
    result = evidence.objects[name + '/result.json']
    payload = evidence.objects[name + '/local/result.json']
    evidence.audit.check(payload == expected, 'exact probe payload', name)
    evidence.audit.check(result.get('passed') is True and result.get('drained') is True and result.get('jit_bodies') == 0,
                         'probe passed and drained without JIT claim', name)
    evidence.audit.check(result.get('results') == [dict(execution='local', **expected)], 'probe aggregate matches payload', name)
    evidence.audit.check(result.get('kernel_identity', {}).get('ok') is True, 'captured probe kernel identity', name)
    return dict(name=name, selected=selected, status='PASS' if len(evidence.audit.failures) == start and command else 'FAIL',
        fields=len(payload), payload=payload, command=command, kernel_identity=result.get('kernel_identity'),
        snapshot_tag=result.get('snapshot_tag'), provenance=evidence.provenance(name))


def basic_result(evidence):
    name, start = 'final-basic', len(evidence.audit.failures)
    if not evidence.needed(name, ('result.json', 'basic.log', 'source-sha256.json')):
        return dict(name=name, status='MISSING')
    receipt, log = evidence.objects[name + '/result.json'], evidence.logs[name + '/basic.log']
    evidence.audit.check(receipt.get('returncode') == 0 and receipt.get('command') == ['make', '-C', 'tests/unit', 'run'],
                         'two-basic-C command', name)
    evidence.audit.check('Unit tests: 2 passed, 0 failed' in log and '[PASS] test_control_call' in log and
                         '[PASS] test_daemon_policy' in log and not re.search(r'\[FAIL\]|\bSKIP(?:PED)?\b', log),
                         'two basic C programs passed without skips', name)
    return dict(name=name, status='PASS' if len(evidence.audit.failures) == start else 'FAIL',
        command=receipt, programs=['basic/test_control_call', 'basic/test_daemon_policy'],
        log_sha256=evidence.hashes[name + '/basic.log'], provenance=evidence.provenance(name),
        limit='The basic wrapper captured a source manifest and command/log; no basic executable manifest was captured.')


def expected_plan(name):
    if name == 'final-functional':
        cases, mixes, threads, arms, iterations = [('cacheline', 1), ('cacheline', 8), ('rcuht', 0)], [0, 1, 20], [1, 8], ['native', 'kdlock'], 100000
    elif name == 'final-local':
        cases, mixes, threads, arms, iterations = [('cacheline', 8)], [0, 20], [1, 8], ['kdlock'], 100000
    else:
        cases, mixes, threads, arms, iterations = [('cacheline', 8), ('rcuht', 0)], [80, 100], [16], ['kdlock'], 200000
    return {(workload, lines, mix, count, arm, 0) for workload, lines in cases for mix in mixes for count in threads for arm in arms}, iterations


def functional_result(evidence, name):
    start = len(evidence.audit.failures)
    command = command_receipt(evidence, name)
    required = ('plan.json', 'records.json', 'summary.json', 'source-sha256.json', 'binary-sha256.json', 'environment.json')
    if not evidence.needed(name, required):
        return dict(name=name, status='MISSING', command=command)
    plan, records = (evidence.objects[name + '/' + filename] for filename in ('plan.json', 'records.json'))
    expected, iterations = expected_plan(name)
    actual = {(row['workload'], row['cachelines'], row['write_percent'], row['threads'], row['arm'], row['repeat']) for row in plan}
    evidence.audit.check(actual == expected and len(plan) == len(expected), 'exact final fixed-iteration matrix', name)
    recorded = {row['name']: row for row in records}
    evidence.audit.check(len(recorded) == len(records) == len(plan) and set(recorded) == {row['name'] for row in plan},
                         'all planned functional sessions recorded once', name)
    evidence.audit.check(evidence.objects[name + '/summary.json'] == [], 'functional sessions have no scored summary', name)
    sessions = []
    for spec in plan:
        row = recorded.get(spec['name'], {})
        context = name + '/' + spec['name']
        failures = len(evidence.audit.failures)
        direct = spec['arm'] == 'kdlock' and name != 'final-local'
        eligible = direct and spec['write_percent'] > 0
        evidence.audit.check(all(row.get(key) == value for key, value in spec.items()), 'record matches plan', context)
        evidence.audit.check(spec['functional'] is True and spec['duration_ms'] == 0 and spec['iterations'] == iterations and
            spec['lock_kind'] == 'rwsem' and spec['cpus'] == list(range(spec['threads'])) and spec['collector_cpu'] == 63 and
            spec['post_work_rounds'] == 4 and spec['caller_abi'] == ('clobber' if direct else 'c') and
            spec['entry_abi'] == (2 if direct else None) and spec['delegate'] == direct and
            spec['rwsem_writer_shell'] == ('delegated-epoch-abi2' if direct else 'ordinary-local') and
            spec['require_jit'] == (name == 'final-jit'), 'functional caller/iteration identity', context)
        measured = row.get('measurement', {})
        valid = row.get('execution_status') == 'OK' and row.get('drained') is True and measured.get('data_ok') is True and measured.get('complete') is True
        evidence.audit.check(valid, 'functional success and drain', context)
        receipt = {key: row.get(key) for key in ('name', 'arm', 'variant', 'workload', 'cachelines', 'write_percent',
            'threads', 'caller_abi', 'entry_abi', 'delegate', 'rwsem_writer_shell', 'execution_status', 'drained',
            'jit_status', 'jit_bodies', 'jit_completions', 'jit_complete_share')}
        if valid:
            workers = measured['workers']
            evidence.audit.check(len(workers) == row['threads'], 'functional worker count', context)
            for index, worker in enumerate(workers):
                evidence.audit.check(worker['completed'] == iterations and worker['completed'] == worker['reads'] + worker['writes'] and
                    worker['writes'] == ((17 * index) % 100 + iterations * row['write_percent']) // 100 and
                    worker['read_errors'] == 0 and not worker.get('error') and worker['cpu_ns'] > 0 and
                    worker['cpu'] == worker['observed_cpu'] == row['cpus'][index], 'fixed worker progress/mix/affinity', context)
            for field in ('completed', 'reads', 'writes'):
                evidence.audit.check(measured[field] == sum(worker[field] for worker in workers), 'functional totals ' + field, context)
            before, after = measured['before'], measured['after']
            evidence.audit.check(all(state[field] == 0 for state in (before, after) for field in ('active', 'cnts', 'gate')),
                                 'functional payload quiescence', context)
            delta = [last - first for first, last in zip(before['values'], after['values'])]
            effects = delta == [measured['writes']] * row['cachelines'] + [0] * (16 - row['cachelines']) if row['workload'] == 'cacheline' else (
                delta[0] == measured['writes'] == sum(delta[1:4]) and all(value >= 0 for value in delta[:4]) and
                before['values'][4:] == after['values'][4:] == [0] * 12)
            evidence.audit.check(effects, 'functional protected effects', context)
            entries, complete = row['jit_bodies'], row['jit_completions']
            evidence.audit.check(entries == row['jit_after'] - row['jit_before'] and complete == row['jit_complete_after'] - row['jit_complete_before']
                                 and 0 <= complete <= entries <= measured['writes'], 'functional JIT counter deltas/bounds', context)
            disposition = ('PASS' if complete else 'PARTIAL_JIT' if entries else 'NO_JIT') if eligible else 'NATIVE'
            evidence.audit.check(row['jit_status'] == disposition and (eligible or entries == complete == 0),
                                 'functional returned-body disposition', context)
            evidence.audit.check(name != 'final-jit' or complete > 0, 'strict JIT requires returned body', context)
            if eligible:
                publication = row.get('published_before')
                evidence.audit.check(publication is not None and publication == row.get('published_after') and
                    publication['entry']['entry_abi'] == 2 and publication['entry']['lock_kind'] == 2 and
                    publication['source']['writers'] == publication['source']['frames'] == publication['source']['state'] == 0,
                    'functional stable ABI2 publication', context)
            receipt.update(completed=measured['completed'], reads=measured['reads'], writes=measured['writes'],
                           min_worker_completed=min(worker['completed'] for worker in workers))
        receipt['replay_passed'] = len(evidence.audit.failures) == failures
        sessions.append(receipt)
    environment = evidence.objects[name + '/environment.json']
    evidence.audit.check(environment.get('kernel_identity', {}).get('ok') is True, 'functional captured kernel identity', name)
    return dict(name=name, status='PASS' if len(evidence.audit.failures) == start and command else 'FAIL',
        expected_sessions=len(expected), recorded_sessions=len(records),
        valid_sessions=sum(row['replay_passed'] for row in sessions),
        jit_session_counts=dict(Counter(row['jit_status'] for row in sessions)),
        jit_entries=sum(row.get('jit_bodies') or 0 for row in sessions),
        jit_completions=sum(row.get('jit_completions') or 0 for row in sessions),
        sessions=sessions, command=command, provenance=evidence.provenance(name))


def profile_result(evidence, name):
    start = len(evidence.audit.failures)
    root = name + '/rwsem'
    required = ('result.json', 'diagnostic.json', 'function-count-summary.json', 'controls-final.json')
    if not evidence.needed(name, required) or not evidence.needed(root, ('plan.json', 'records.json', 'summary.json',
            'source-sha256.json', 'binary-sha256.json', 'environment.json')):
        return dict(name=name, status='MISSING', diagnostic=True, score_eligible=False)
    result, diagnostic = evidence.objects[name + '/result.json'], evidence.objects[name + '/diagnostic.json']
    evidence.audit.check(result.get('completed') is True and result.get('tracing_restored') is True and result.get('guest_idle') is True
                         and bool(result.get('commands')) and all(command.get('returncode') == 0 for command in result.get('commands', [])),
                         'profile completed with restored tracing and idle', name)
    evidence.audit.check(diagnostic.get('diagnostic') is True and diagnostic.get('score_eligible') is False and
                         evidence.objects[root + '/summary.json'] == [], 'profile excluded from throughput scoring', name)
    plan, records = evidence.objects[root + '/plan.json'], evidence.objects[root + '/records.json']
    evidence.audit.check(evidence.objects[root + '/environment.json'].get('kernel_identity', {}).get('ok') is True,
                         'profile captured kernel identity', name)
    evidence.audit.check(len(plan) == len(records) and {row['name'] for row in plan} == {row['name'] for row in records},
                         'all profile sessions retained', name)
    planned = {row['name']: row for row in plan}
    arms = {row['arm'] for row in plan}
    evidence.audit.check('kdlock' in arms and arms <= {'native', 'kdlock'} and
        {(row['arm'], row['repeat']) for row in plan} == {(arm, repeat) for arm in arms for repeat in range(3)} and
        len(plan) == 3 * len(arms) and all(row.get('diagnostic') is True and row.get('score_eligible') is False and
            row['lock_kind'] == 'rwsem' and row['workload'] == 'cacheline' and row['cachelines'] == 1 and
            row['threads'] == 60 and row['write_percent'] == 20 and row['duration_ms'] == 2000 and not row['functional']
            for row in plan), 'profile diagnostic cohort identity', name)
    sessions = []
    for row in records:
        path = root + '/' + row['name'] + '/function-profile'
        if not evidence.needed(path, ('restore.json', 'controls-before.json', 'aggregate.json', 'raw-profile-sha256.json')):
            sessions.append(dict(name=row['name'], status='MISSING'))
            continue
        restore = evidence.objects[path + '/restore.json']
        before = evidence.objects[path + '/controls-before.json']
        raw = evidence.objects[path + '/raw-profile-sha256.json']
        aggregate = evidence.objects[path + '/aggregate.json']
        evidence.audit.check(all(row.get(key) == value for key, value in planned.get(row['name'], {}).items()),
                             'profile record matches plan', path)
        okay = evidence.audit.check(row.get('execution_status') == 'OK' and row.get('drained') is True and
            row.get('diagnostic') is True and row.get('score_eligible') is False and
            row.get('measurement', {}).get('data_ok') is True and row.get('measurement', {}).get('complete') is True and
            restore.get('restored') is True and not restore.get('errors') and restore.get('controls_after') == before and
            not aggregate.get('unexpected_rows') and bool(raw), 'profile session valid with exact tracing restoration', path)
        for filename, expected in raw.items():
            evidence.audit.check(len(safe_path(filename).parts) == 1 and evidence.member_hash(path + '/raw-profile/' + filename) == expected,
                                 'raw per-CPU profile hash', path + '/' + filename)
        sessions.append(dict(name=row['name'], arm=row['arm'], jit_status=row.get('jit_status'),
            jit_completions=row.get('jit_completions'), status='PASS' if okay else 'FAIL', raw_cpu_profiles=len(raw)))
        sessions[-1]['caller_identity'] = {key: row.get(key) for key in ('lock_kind', 'caller_abi', 'entry_abi',
            'delegate', 'rwsem_writer_shell', 'workload', 'cachelines', 'threads', 'write_percent',
            'duration_ms', 'cpus', 'collector_cpu')}
    final = evidence.objects[name + '/controls-final.json']
    evidence.audit.check(final.get('current_tracer', '').strip() == 'nop' and
                         final.get('function_profile_enabled', '').strip() == '0' and
                         not final.get('enabled_functions', '').strip(), 'profile final tracer idle', name)
    return dict(name=name, status='PASS' if len(evidence.audit.failures) == start and all(row['status'] == 'PASS' for row in sessions) else 'FAIL',
        diagnostic=True, score_eligible=False, recorded_sessions=len(records), sessions=sessions,
        command_receipts=result.get('commands'), provenance=evidence.provenance(root),
        function_counts=evidence.objects[name + '/function-count-summary.json'])


def health_result(evidence):
    path = evidence.capture.get('health_path', 'health.json')
    if path not in evidence.objects:
        evidence.audit.missing.append(dict(context='final-health', files=[path]))
        return dict(status='MISSING')
    start = len(evidence.audit.failures)
    health = evidence.objects[path]
    evidence.audit.check(evidence.hashes[path] == evidence.capture['health_sha256'], 'retained health receipt hash', path)
    evidence.audit.check(health.get('idle') is True and health.get('boot_id') == evidence.capture.get('boot_id') and
        health.get('no_linux_mutex_imports') is True and not health.get('per_session_kernel_faults') and
        not health.get('new_faults_in_retained_dmesg', []) and health.get('per_session_kernel_logs', 0) > 0,
        'final health idle/boot/imports/fault receipt', path)
    tracing = health.get('tracing', {})
    evidence.audit.check(tracing.get('current_tracer', '').strip() == 'nop' and
        tracing.get('function_profile_enabled', '').strip() == '0' and not tracing.get('enabled_functions', '').strip(),
        'final health tracing idle', path)
    required = {'xlong-probe', 'final-basic', 'final-functional', 'final-local', 'final-jit',
                'final-grid', 'final-reference', 'final-profile/rwsem'}
    checks = health.get('source_and_binary_checks', [])
    evidence.audit.check(required <= {row['name'] for row in checks}, 'final health covers all selected runs', path)
    for row in checks:
        source = row['name'] + '/source-sha256.json'
        if source in evidence.hashes:
            evidence.audit.check(row['source_manifest_sha256'] == evidence.hashes[source], 'health source manifest identity', row['name'])
    return dict(status='PASS' if len(evidence.audit.failures) == start else 'FAIL', receipt=health,
                receipt_sha256=evidence.hashes[path],
                scope='Health statements are captured guest evidence; this offline reader verifies their retained hash and matching available manifests.')


def markdown(result):
    lines = ['# KD rwsem optimization validation evidence', '',
        'Draft generated from captured archive bytes. Overall status: **' + result['status'] + '**. '
        'No project source was executed and no new guest tests were run by this report.', '',
        '| Selected check | Status | Detail |', '|---|---|---|']
    for row in result['final_checks']:
        detail = ('Probe payload fields: ' + str(row.get('fields'))) if row['name'].endswith('probe') else \
            ('Two basic C programs' if row['name'] == 'final-basic' else
             f"{row.get('valid_sessions', 0)}/{row.get('expected_sessions', '?')} sessions; "
             f"{row.get('jit_completions', 0)} returned JIT bodies")
        lines.append(f"| {row['name']} | {row['status']} | {detail} |")
    lines += ['', 'Functional/control configurations stay separate: `final-functional` expects 36 sessions '
        '(c01/c08/RCUHT, 0%/1%/20% writes, 1/8 workers, Native/KD); `final-local` expects four c08 KD '
        'ordinary-shell sessions (0%/20%, 1/8 workers); `final-jit` expects four ABI2 sessions '
        '(c08/RCUHT, 80%/100%, 16 workers, 200,000 iterations per worker) and requires at least one '
        'returned delegated writer body in every session. Actual returned-body totals are read from '
        'counter deltas, never inferred from publication.', '', '## Earlier experimental probes', '',
        'These probes are retained separately from selected-version validation. A passing probe does '
        'not endorse that candidate’s performance or protocol selection.', '',
        '| Probe | Status | Payload fields |', '|---|---|---|']
    for row in result['experimental_probes']:
        lines.append(f"| {row['name']} | {row['status']} | {row.get('fields', 'missing')} |")
    lines += ['', '## Profiles and final health', '', '| Capture | Status | Sessions |', '|---|---|---|']
    for row in result['profiles']:
        lines.append(f"| {row['name']} | {row['status']} | {row.get('recorded_sessions', 'missing')} |")
    lines += ['', 'Profiles are diagnostic and excluded from throughput scores. Per-session restoration '
        'receipts and raw per-CPU profile hashes are checked. Final health status: **' + result['health']['status'] + '**.', '',
        '## Provenance and limits', '',
        '`validation.json` retains command return codes, raw manifest hashes, source content IDs, '
        'kernel identity, available topology/snapshot identity, final boot identity, session shells, '
        'JIT counters, archive hashes and every failed/missing check. Source content IDs hash canonical '
        'manifest content; raw JSON hashes remain separately labeled. Source and binary manifests '
        'in the three captured groups are verified against archived file bytes. Performance matrices '
        'and their manifests are reported separately by the performance analysis.', '',
        'The basic C wrapper captured source hashes and its command/log, but no executable manifest. '
        'Recorded success and payload effects are evidence from the completed guest run; this offline '
        'replay is not a new concurrency proof or whole-kernel integration test.', '']
    if result['missing']:
        lines += ['Missing evidence:', '', *('- ' + row['context'] + ': ' + ', '.join(row['files']) for row in result['missing']), '']
    if result['failures']:
        lines += ['Failed checks:', '', *('- ' + row['check'] + ': ' + row['context'] for row in result['failures']), '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives_json', type=Path)
    parser.add_argument('raw_folder', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use a new output directory')
    capture = json.loads(args.archives_json.read_text())
    audit = Audit()
    evidence = Evidence(capture, args.raw_folder, audit)
    final = [probe_result(evidence, 'xlong-probe', selected=True), basic_result(evidence)]
    final += [functional_result(evidence, name) for name in ('final-functional', 'final-local', 'final-jit')]
    probes = [probe_result(evidence, name) for name in ('poll-probe', 'split-probe', 'long-probe', 'grant-probe')]
    profiles = [profile_result(evidence, name) for name in ('baseline-profile', 'final-profile')]
    health = health_result(evidence)
    status = 'FAIL' if audit.failures else 'MISSING' if audit.missing else 'PASS'
    result = dict(schema=1, status=status, archives_json_sha256=sha_file(args.archives_json),
        report_script_sha256=sha_file(Path(__file__)), archives=evidence.archives, final_checks=final,
        experimental_probes=probes, profiles=profiles, health=health, manifests_verified=evidence.manifests,
        kernel_log_scope='All retained kernel.log files within tests/metadata/profiles groups; other groups covered by captured final health and separate archive verification',
        kernel_logs=evidence.kernel_logs, checks=dict(audit.counts), failures=audit.failures, missing=audit.missing,
        no_captured_source_executed=True, no_guest_actions=True)
    args.output.mkdir(parents=True)
    save(args.output / 'validation.json', result)
    (args.output / 'README.md').write_text(markdown(result))
    print(json.dumps(dict(status=status, final={row['name']: row['status'] for row in final},
                          failures=len(audit.failures), missing=len(audit.missing)), indent=2))
    return 0 if status == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
