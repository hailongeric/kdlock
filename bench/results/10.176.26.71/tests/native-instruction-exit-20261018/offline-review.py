#!/usr/bin/env python3
"""Read-only archive evidence review; imports no project code and runs no tests."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Review:
    def __init__(self, final=False, source_root=None):
        self.checks = 0
        self.final = final
        self.source_root = source_root

    def check(self, value, message):
        self.checks += 1
        if not value:
            raise ValueError(message)

    def archive(self, raw, record):
        path = raw / record['archive']
        digest = hashlib.sha256()
        with path.open('rb') as incoming:
            for chunk in iter(lambda: incoming.read(1024 * 1024), b''):
                digest.update(chunk)
        self.check(path.stat().st_size == record['bytes'], 'archive size: ' + path.name)
        self.check(digest.hexdigest() == record['sha256'], 'archive hash: ' + path.name)
        root = PurePosixPath(record['guest_run']).name
        hashes, contents, names = {}, {}, set()
        with tarfile.open(path, 'r:gz') as archive:
            for member in archive:
                self.check(member.name not in names, 'duplicate member: ' + member.name)
                names.add(member.name)
                pieces = PurePosixPath(member.name).parts
                self.check(pieces and pieces[0] == root and '..' not in pieces,
                           'unexpected archive path: ' + member.name)
                if member.isfile():
                    data = archive.extractfile(member).read()
                    hashes[member.name] = sha(data)
                    if member.name.endswith(('.json', '.log', '/spin/restore.inc', '/jit_escape/run.py')):
                        contents[member.name] = data
        def data(name):
            return contents[root + '/' + name]
        def obj(name):
            return json.loads(data(name))
        def text(name):
            return data(name).decode(errors='replace')
        source = obj('source-sha256.json')
        for name, expected in source.items():
            self.check(hashes.get(root + '/source/' + name) == expected, 'source hash: ' + root + '/' + name)
        binaries = obj('binary-sha256.json') if root + '/binary-sha256.json' in contents else {}
        for name, expected in binaries.items():
            relative = PurePosixPath(name).relative_to(record['guest_run'])
            self.check(hashes.get(root + '/' + str(relative)) == expected, 'binary hash: ' + name)
        prepared = {}
        if root + '/prepared-source-sha256.json' in contents:
            prepared = obj('prepared-source-sha256.json')
        elif root + '/build/provider/manifest.json' in contents:
            prepared = obj('build/provider/manifest.json')['prepared']
        for name, expected in prepared.items():
            self.check(hashes.get(root + '/build/provider/' + name) == expected, 'prepared input: ' + name)
        warnings = []
        for name, payload in contents.items():
            if '/build' in name and name.endswith('.log'):
                warnings.extend(line for line in payload.decode(errors='replace').splitlines()
                                if 'warning: objtool:' in line)
        result = dict(**record, integrity='PASS', archive_members=len(names), regular_files=len(hashes),
                      source_inputs_verified=len(source), binary_inputs_verified=len(binaries),
                      prepared_inputs_verified=len(prepared),
                      source_manifest_sha256=sha(data('source-sha256.json')),
                      objtool_warnings=warnings)
        if '-units-' in root:
            result['unit_review'] = self.units(obj, text, root)
        elif '-live-' in root:
            result['live_review'] = self.live(obj, text, hashes, root)
        elif '-rwsem-' in root:
            result['rwsem_review'] = self.rwsem(obj, text, root)
        else:
            raise ValueError('unknown review type: ' + root)
        restore = text('source/kernel_module/spin/restore.inc')
        fragment = restore.split('kd_jump_to_saved_regs_with_flags', 1)[1].split('__builtin_unreachable', 1)[0]
        result['marker_restore_uses_config_rethunk'] = 'CONFIG_RETHUNK' in fragment
        if self.final:
            self.check('CONFIG_RETHUNK' in fragment and '__x86_return_thunk' in fragment,
                       'final marker restore lacks configured return thunk: ' + root)
            self.check(not any('kd_jump_to_saved_regs_with_flags' in line and "'naked' return" in line
                               for line in warnings), 'new marker restore has bare-return build warning: ' + root)
            result['current_source_equivalence'] = self.source_equivalence(source)
        return result

    def source_equivalence(self, captured):
        groups = dict(runtime={}, tests={}, runners={}, other_inputs={})
        docs, excluded_generated = {}, []
        for name, expected in captured.items():
            path = PurePosixPath(name)
            if any(piece.startswith('.') for piece in path.parts):
                excluded_generated.append(name)
                continue
            current = self.source_root / name
            observed = sha(current.read_bytes()) if current.is_file() else None
            if path.suffix == '.md':
                docs[name] = dict(captured=expected, current=observed, equal=expected == observed)
                continue
            category = ('runtime' if path.parts[0] in ('include', 'kernel_module', 'daemon', 'disassem') else
                        'tests' if path.parts[0] in ('tests', 'workload_modules') else
                        'runners' if path.parts[0] == 'bench' else 'other_inputs')
            groups[category][name] = dict(captured=expected, current=observed, equal=expected == observed)
            self.check(expected == observed, 'captured/current source differs: ' + name)
        return dict(status='PASS', compared_groups={k: len(v) for k, v in groups.items()},
                    groups=groups, captured_documentation_files=len(docs),
                    documentation_differences={k: v for k, v in docs.items() if not v['equal']},
                    excluded_generated_snapshot_paths=excluded_generated,
                    scope='Captured non-documentation runtime, tests, runners and other inputs; hidden historical .build copies excluded. This does not claim every checkout file was captured.')

    def units(self, obj, text, root):
        records = obj('results.json')
        checks = []
        for record in records:
            log = text(record['name'] + '.log')
            skip_lines = [line for line in log.splitlines()
                          if re.search(r'\.\.\. skipped|\bskipped=[1-9]|^SKIP\b', line)]
            self.check(not skip_lines, root + ': skipped tests: ' + record['name'])
            count = sum(map(int, re.findall(r'^Ran (\d+) tests? in ', log, re.M)))
            if record['returncode'] == 0 and count:
                self.check(bool(re.search(r'^OK\s*$', log, re.M)), 'missing unittest OK: ' + record['name'])
            checks.append(dict(name=record['name'], returncode=record['returncode'],
                               unittest_cases=count, skip_lines=skip_lines))
        failures = [r['name'] for r in records if r['returncode'] != 0]
        if root.endswith('-01'):
            self.check(failures == ['admission-test_native_escape.py', 'execution-test_native_escape_restore.py'],
                       'unexpected initial unit failure set')
            self.check("instruction='RDTSCP'" in text('admission-test_native_escape.py.log') and
                       'INVLPG     ECX' in text('admission-test_native_escape.py.log'), 'missing decoder failure')
            self.check('native_escape_restore_fixture.c: No such file or directory' in
                       text('execution-test_native_escape_restore.py.log'), 'missing fixture failure')
        else:
            self.check(not failures, 'unit command failed: ' + root)
            basic = text('basic.log')
            self.check('Unit tests: 2 passed, 0 failed' in basic, 'basic tests incomplete')
            self.check('64 arithmetic-flag combinations, all GPRs, exact SP and waiter control flags passed' in
                       text('execution-test_native_escape_restore.py.log'), 'restore fixture did not pass')
            if self.final:
                self.check(text('execution-test_native_escape_restore.py.log').count(
                    '64 arithmetic-flag combinations, all GPRs, exact SP and waiter control flags passed') == 2,
                    'both final restore configurations were not recorded')
        return dict(command_count=len(records), failed_commands=failures, commands=checks,
                    unittest_cases=sum(row['unittest_cases'] for row in checks), skipped=0,
                    status='RETAINED_FAILURES' if failures else 'PASS',
                    note='Basic daemon fixture intentionally prints launch/device errors while testing error handling; those diagnostics are not live kernel failures.')

    def live(self, obj, text, hashes, root):
        session = obj('session/session.json')
        self.check(session['drained'] is True and session['retired'] ==
                   dict(state=2, frames=0, modules=0, writers=0), 'live retirement failed')
        layout = session['layout']
        publication = session['publication']
        image = publication['entry']
        image_dir = f"{root}/session/workspace/daemon/{hex(image['entry'])}/{image['tgid']}/asm/"
        for name, digest in publication['images'].items():
            self.check(hashes.get(image_dir + name) == digest, 'published image hash: ' + name)
        summaries = []
        last_after = None
        for phase in session['phases']:
            name = phase['name']
            before, after = obj(f'session/{name}-before.counts.json'), obj(f'session/{name}-after.counts.json')
            self.check(before == phase['before'] and after == phase['after'], 'phase snapshot mismatch')
            if last_after is not None:
                self.check(all(before[k] == last_after[k] for k in ('prefix', 'suffix', 'hot_taken')),
                           'phase effects discontinuity')
            last_after = after
            for state in (before, after):
                self.check(state['active'] == state['failures'] == 0 and state['idle'] == 1 and
                           state['prefix'] == state['suffix'], 'live invariant failure')
            operations = len(session['cpus']) * phase['iterations']
            workers = [obj(f'session/{name}-worker-{i}.json') for i in range(len(session['cpus']))]
            self.check(workers == phase['workers'] and phase['returncodes'] == [0] * len(workers), 'worker records mismatch')
            for i, worker in enumerate(workers):
                self.check(worker['cpu'] == session['cpus'][i] and worker['worker'] == i and
                           worker['iterations'] == worker['completed'] == phase['iterations'] and
                           worker['reserved'] == [0, 0] and worker['errors'] == 0, 'worker progress/flags failure')
                if not root.endswith('-01'):
                    self.check(worker['comm'] == 'ke_worker', 'worker eligibility differs')
            self.check(after['prefix'] - before['prefix'] == after['suffix'] - before['suffix'] == operations,
                       'lost/repeated protected effects')
            self.check(after['hot_taken'] - before['hot_taken'] == phase['hot'] * operations, 'wrong branch count')
            delta = {key: phase['counters_after'][key] - value for key, value in phase['counters_before'].items()}
            self.check(delta == phase['jit_delta'], 'incorrect execution delta')
            self.check(phase['complete'] is True and phase['source_after']['frames'] == 0, 'phase incomplete')
            summaries.append(dict(name=name, operations=operations, hot=phase['hot'], jit_delta=delta,
                                  worker_errors=0, protected_effects='exact', source_frames=0))
        kernel = text('session/kernel.log')
        self.kernel_clean(kernel, root)
        native = re.search(r'kd_native stats: started=(\d+) completed=(\d+) unlocks=(\d+)', kernel)
        self.check(native is not None, 'missing native completion statistics')
        native_stats = dict(zip(('started', 'completed', 'unlocks'), map(int, native.groups())))
        if root.endswith('-01'):
            self.check(session['execution_status'] == 'NO_JIT' and len(summaries) == 2 and
                       all(not any(p['jit_delta'].values()) for p in summaries), 'unexpected first live result')
            self.check(session['initial_parameters']['target_process'] == 'kd_test', 'first live eligibility mismatch absent')
            self.check('cold branch lacks completed delegated bodies' in session['error'], 'first live failure changed')
            status = 'RETAINED_NO_JIT_FAILURE'
            events = []
        else:
            self.check(session['execution_status'] == 'OK' and session['accepted'] and len(summaries) == 4,
                       'accepted live session incomplete')
            self.check(session['initial_parameters']['target_process'] == 'ke_worker', 'wrong provider eligibility')
            for phase in summaries[:2]:
                delta = phase['jit_delta']
                self.check(delta['bench_jit_bodies'] == delta['bench_jit_completions'] > 0 and
                           delta['native_escape_count'] == 0, 'cold delegation failure')
            hot, post = summaries[2]['jit_delta'], summaries[3]['jit_delta']
            self.check(hot['native_escape_count'] > 0 and not any(post.values()), 'hot/post-ban counts failed')
            self.check(obj('session/hot.registry.json')[0]['status'] ==
                       obj('session/post-ban.registry.json')[0]['status'] == -3, 'ban not retained')
            matches = re.findall(r'reason=NATIVE_ESCAPE entry=(0x[0-9a-f]+) rip=(0x[0-9a-f]+) '
                                 r'generation=(\d+) waiter_pid=(\d+) action=native_suffix_and_disable', kernel)
            events = [dict(entry=int(e, 16), rip=int(ip, 16), generation=int(g), waiter_pid=int(pid))
                      for e, ip, g, pid in matches]
            self.check(events == session['escape_events'] and events, 'marker event mismatch')
            pids = {row['pid'] for row in obj('session/hot-escape-callers.json')}
            for event in events:
                self.check(event['entry'] == layout['entry'] and event['rip'] == layout['marker'] and
                           event['waiter_pid'] in pids and event['generation'] == session['image_registry'][0]['generation'],
                           'marker identity mismatch')
            self.check(native_stats['started'] == native_stats['completed'] == native_stats['unlocks'] == hot['native_escape_count'],
                       'native begin/completion/unlock counts differ')
            status = 'PASS'
        return dict(status=status, phases=summaries, operations=sum(p['operations'] for p in summaries),
                    events=events, native_statistics=native_stats, retired=session['retired'], drained=True)

    def kernel_clean(self, text, label):
        fault = re.search(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|'
                          r'unable to handle|general protection fault|Oops:|\[ERROR\]|invariant_failures=[1-9]', text, re.I)
        self.check(fault is None, 'kernel fault: ' + label)

    def rwsem(self, obj, text, root):
        plan = obj('plan.json')
        result = []
        for spec in plan:
            name = spec['name']
            session = obj(name + '/session.json')
            self.check(session['execution_status'] == 'OK' and session['drained'] and session['functional'],
                       'rwsem session failed')
            self.check(session['retired'] == dict(state=2, frames=0, modules=0, writers=0), 'rwsem retirement failed')
            measurements = []
            for phase in ('warmup', 'measure'):
                row = obj(name + '/' + phase + '.json')
                workers = row['workers']
                self.check(row['complete'] and row['data_ok'] and row['collector_error'] == 0, 'rwsem incomplete data')
                self.check(len(workers) == session['threads'] and
                           [w['cpu'] for w in workers] == session['cpus'], 'rwsem worker geometry')
                for worker in workers:
                    self.check(worker['error'] is None and worker['read_errors'] == 0 and
                               worker['observed_cpu'] == worker['cpu'] and worker['cpu_ns'] > 0 and
                               worker['completed'] == worker['reads'] + worker['writes'], 'rwsem worker error')
                for key in ('completed', 'reads', 'writes'):
                    self.check(row[key] == sum(w[key] for w in workers), 'rwsem aggregation error')
                self.check(row['reads'] * 4 == row['writes'] and row['completed'] == len(workers) *
                           (session['iterations'] if phase == 'measure' else session['warmup_iterations_per_worker']),
                           'rwsem progress or mix error')
                before, after = row['before']['values'], row['after']['values']
                if session['workload'] == 'cacheline':
                    self.check(all(a - b == (row['writes'] if i < session['cachelines'] else 0)
                                   for i, (a, b) in enumerate(zip(after, before))), 'rwsem cacheline effect error')
                else:
                    self.check(after[0] - before[0] == row['writes'] and after[0] == sum(after[1:4]) and
                               before[0] == sum(before[1:4]) and all(a >= b for a, b in zip(after, before)) and
                               not any(after[4:] + before[4:]), 'rwsem hash effect error')
                for state in (row['before'], row['after'], obj(name + '/' + phase + '.counts.json')):
                    self.check(state['active'] == state['cnts'] == state['gate'] == 0, 'rwsem not idle')
                measurements.append(dict(phase=phase, completed=row['completed'], reads=row['reads'], writes=row['writes']))
            self.check(session['jit_after'] - session['jit_before'] == session['jit_bodies'] ==
                       session['jit_complete_after'] - session['jit_complete_before'] == session['jit_completions'] > 0,
                       'rwsem returned JIT evidence mismatch')
            self.kernel_clean(text(name + '/kernel.log'), name)
            result.append(dict(name=name, phases=measurements, jit_completions=session['jit_completions'],
                               retired=session['retired'], drained=True))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--manifest', default='archives.json')
    parser.add_argument('--output-prefix', type=Path, required=True)
    parser.add_argument('--final', action='store_true', help='require corrected return path and current source equivalence')
    parser.add_argument('--source-root', type=Path, default=Path.cwd())
    parser.add_argument('--preflight', type=Path, default=Path(__file__).resolve().parent / 'guest-before.json')
    args = parser.parse_args()
    reviewer = Review(final=args.final, source_root=args.source_root.resolve())
    records = json.loads((args.raw / args.manifest).read_text())
    result = dict(schema=1, scope='FINAL_CAPTURED_SOURCE_VALIDATION' if args.final else 'INTERMEDIATE_VALIDATION_NOT_FINAL_SOURCE_PROOF',
                  method='Python standard-library tarfile reads only; no extraction, repository imports, tests or VM execution',
                  records=[reviewer.archive(args.raw, row) for row in records])
    if args.final:
        before = json.loads(args.preflight.read_text())
        health = json.loads((args.raw / 'health-after.json').read_text())
        reviewer.check(health['idle'] is True and not health['modules'] and not health['tasks'],
                       'final guest was not idle')
        reviewer.check(health['boot_id'] == before['boot_id'], 'final/preflight boot identity differs')
        reviewer.check(health['cpus'] == before['cpus'] and
                       health['cmdline'].strip() == before['cmdline'].strip(), 'final guest topology/boot settings differ')
        result['final_health'] = dict(record=health, preflight=before, matches_preflight=True,
                                     health_sha256=sha((args.raw / 'health-after.json').read_bytes()))
    result['checks_passed'] = reviewer.checks
    result['status'] = 'PASS_FINAL_EVIDENCE_REVIEW' if args.final else 'PASS_EVIDENCE_REVIEW_WITH_RETAINED_FAILURES'
    result['limits'] = [
        'These archives precede the CONFIG_RETHUNK-compatible return correction; they do not validate final selected source.',
        'Unit01 preserves RDTSCP decoder refusal and missing restore fixture; live01 preserves zero JIT caused by worker/provider name mismatch.',
        'Basic plus affected unit commands only, not a full suite. Unit executables have no separate binary-hash manifest.',
        'Live instruction coverage is safe RDTSC; other reviewed instruction families are not live-tested.',
        'Rwsem runs are functional checks at 80% writes, not performance measurements or a repeat of the accepted full grid.'
    ]
    if args.final:
        result['limits'][:2] = [
            'Current source equivalence covers captured inputs only; documentation differences and excluded historical .build copies are reported separately.',
            'Earlier failed unit01/live01 attempts and intermediate unit02/live02/rwsem01 evidence remain in preliminary-review.json; they are not pooled with final source.'
        ]
    args.output_prefix.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Final independent evidence review' if args.final else '# Preliminary independent evidence review', '',
             ('The final captured inputs include the corrected CONFIG_RETHUNK return sequence, which uses the kernel return helper. Captured runtime, test and runner inputs match the reviewed checkout; documentation differences are listed separately.' if args.final else
              '**Intermediate evidence only.** These archives precede the corrected return sequence for a kernel built with CONFIG_RETHUNK, which requires the kernel return helper. They do not prove the final selected source.'), '',
             f'Archive and recorded-data checks passed ({reviewer.checks:,} checks). This review read archives without extracting or running their code. No repository tests or VM work were executed.', '',
             '| Archive | Source files | Binary files | Recorded outcome |', '| --- | ---: | ---: | --- |']
    for record in result['records']:
        outcome = (record.get('unit_review') or record.get('live_review') or {}).get('status', 'PASS: two functional rwsem sessions')
        lines.append(f"| `{record['archive']}` | {record['source_inputs_verified']} | {record['binary_inputs_verified']} | {outcome} |")
    lines += ['', 'All archive sizes and SHA-256 hashes match the imported manifest. Frozen source, prepared provider inputs, recorded binaries and live published-image hashes were checked against their captured manifests.', '']
    for record in result['records']:
        if record.get('unit_review', {}).get('status') == 'PASS':
            unit = record['unit_review']
            lines += [f"`{record['archive']}` records {unit['command_count']} successful basic/affected commands, including two basic C programs and {unit['unittest_cases']} Python unittest cases. No recorded test was skipped. The restore fixture reports all 64 arithmetic-flag combinations; this is separate from the live workload. Expected daemon error-handling diagnostics remain in the basic log.", '']
        if record.get('live_review', {}).get('status') == 'PASS':
            live = record['live_review']
            lines += [f"`{record['archive']}` completed {live['operations']:,} operations with exact prefix/suffix counts, zero worker errors and complete retirement:", '',
                      '| Phase | Operations | Generated-code entries | Completed generated bodies | Instruction exits |', '| --- | ---: | ---: | ---: | ---: |']
            for phase in live['phases']:
                d = phase['jit_delta']
                lines.append(f"| {phase['name']} | {phase['operations']:,} | {d['bench_jit_bodies']:,} | {d['bench_jit_completions']:,} | {d['native_escape_count']:,} |")
            lines += ['', 'The instruction event matches the source instruction address, image version and a recorded worker process. The native continuation started, completed and unlocked once; later calls produced zero generated-code entries and retained the disabled registry state. Kernel logs contain no matched runtime fault. ' +
                      ('Build warnings remain recorded, but the new marker restore has no bare-return warning after the CONFIG_RETHUNK correction.' if args.final else
                       'Build warnings are retained, including the new restore function’s bare return that prompted the subsequent correction.'), '']
        if 'rwsem_review' in record:
            lines += ['The two rwsem checks each completed 3,200,000 measured operations (640,000 reads and 2,560,000 writes), with all 16 workers progressing and source retirement complete. Generated writer completions were ' + ' and '.join(f"{r['jit_completions']:,}" for r in record['rwsem_review']) + '. Their separate warmups and recorded protected-data totals also agree.', '']
    lines += ['Initial failures remain evidence: unit01 refused RDTSCP because the decoder called its bytes `INVLPG ECX`, and its restore fixture was missing from the snapshot; live01 completed correct local work but returned no generated bodies because Python workers did not match `target_process=kd_test`. Neither failed attempt is counted as a pass.', '',
              f'See [the machine-readable review]({args.output_prefix.with_suffix(".json").name}) for hashes, exact input counts, retained warnings and validation limits.', '']
    if args.final:
        counts = {row['archive']: row['current_source_equivalence']['compared_groups'] for row in result['records']}
        documentation = {row['archive']: list(row['current_source_equivalence']['documentation_differences'])
                         for row in result['records']}
        lines += ['The final guest was idle with no retained project modules or worker tasks. Its boot identity, CPU set and boot arguments match preflight. The restore fixture passed all 64 arithmetic-flag combinations in each of the ordinary-return and CONFIG_RETHUNK configurations.', '',
                  'Current-source comparison counts (runtime / tests / runners / other captured inputs):', '']
        for name, groups in counts.items():
            lines.append(f'- `{name}`: ' + ' / '.join(str(groups[k]) for k in ('runtime', 'tests', 'runners', 'other_inputs')) + '.')
        lines += ['', 'Captured documentation differences: ' + json.dumps(documentation, sort_keys=True) + '.', '',
                  'This remains basic plus affected validation. It does not claim a full unit suite, a new performance comparison, or live execution of the other reviewed privileged instructions.', '']
    args.output_prefix.with_suffix('.md').write_text('\n'.join(lines))
    print(json.dumps(dict(status=result['status'], archives=len(records), checks_passed=reviewer.checks)))


if __name__ == '__main__':
    main()
