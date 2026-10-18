#!/usr/bin/env python3
"""Replay the taskname/xattr comparison; never run benchmarks or build code.

Usage: report.py RUN_MAP.json NEW_OUTPUT_DIRECTORY [--plots] [--allow-partial]
The map has taskname and xattr keys, each naming one runner directory or tar.gz
archive. Relative paths resolve against the map. Plot generation is VM-only.
Raw validation reuses the maintained workload oracle and peak-window policy;
their exact source hashes are retained and checked against each run's snapshot.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import tarfile


GRID = [*range(1, 9), *range(12, 61, 4)]
ARMS = ('native', 'tclock', 'kdlock')
ROOT = Path(__file__).resolve().parents[5]
DEPENDENCIES = ('bench/spin_cacheline/peak.py', 'bench/rwlock_compare/oracle.py',
                'bench/real_api/report.py', 'bench/real_api/evidence.py')
COMMON_IDENTITY = ('cpus', 'cpu_nodes', 'collector_cpu', 'duration_ms',
                   'peak_window_ms', 'peak_settle_ms', 'sample_ms')
TASK_IDENTITY = COMMON_IDENTITY + (
    'lock_kind', 'write_percent', 'post_work_rounds', 'warmup_iterations_per_worker',
    'mix_policy', 'provider_ubsan', 'caller_abi', 'entry_abi', 'delegate',
    'helper_waves', 'helper_cpus', 'helper_cpu_nodes', 'helper_iterations_per_worker',
    'numa_policy', 'delegation_batch_limit', 'spin_entry_ratio_limit')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(left, right):
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-7)


def relative_name(name):
    path = Path(name)
    require(not path.is_absolute() and '..' not in path.parts and str(path) not in ('', '.'),
            'invalid evidence-relative path: ' + str(name))
    return str(path)


def number(value):
    return {'Y': 1, 'N': 0}[value] if value in ('Y', 'N') else int(value)


def verify_binaries(kind, inputs, manifest, plan):
    """Resolve archived bytes by recorded suffix, never by live absolute paths."""
    arms = {row['arm'] for row in plan}
    if kind == 'taskname':
        expected = {'build/guard/tc_allocator_guard.ko'}
        expected.update('build/' + row['variant'] + '/rwlock_bench.ko' for row in plan)
        if 'kdlock' in arms:
            expected.update(('build/provider/kernel_module/kdlock_km.ko', 'source/daemon/daemon'))
        if 'tclock' in arms:
            expected.add('build/tclock/tclock_backend_km.ko')
        rows = []
        for original, digest in manifest.items():
            matches = [relative for relative in expected if original.endswith('/' + relative)]
            require(len(matches) == 1, 'unexpected taskname binary: ' + original)
            rows.append((original, matches[0], digest))
        require({relative for _, relative, _ in rows} == expected and len(rows) == len(expected),
                'missing or duplicate taskname binary')
    else:
        require({'client', 'daemon', 'kdlock_km.ko', 'tc_allocator_guard.ko',
                 'tclock_backend_km.ko', *(arm + '-xattr/real_api.ko' for arm in ARMS)} <= manifest.keys(),
                'missing xattr binary')
        rows = [(item['path'], 'build/' + relative_name(name), item['sha256'])
                for name, item in manifest.items()]
        require(all(original.endswith('/' + relative) for original, relative, _ in rows),
                'xattr binary path differs from its manifest key')
    roots = {original[:-len(relative)] for original, relative, _ in rows}
    require(len(roots) == 1, 'binary manifest combines different original run roots')
    verified = {}
    for original, relative, digest in rows:
        require(sha(inputs.read(relative)) == digest, 'binary bytes differ: ' + relative)
        verified[original] = dict(path=relative, sha256=digest)
    return verified


def verify_runtime_policy(row, kind, inputs, binaries):
    if row['arm'] == 'native':
        return
    kd = row['arm'] == 'kdlock'
    log = ('load-kdlock' if kind == 'taskname' else 'load-kd') if kd else (
        'load-tclock' if kind == 'taskname' else 'load-tc')
    command = inputs.json(row['name'] + '/' + log + '.log.command.json')['argv']
    require(len(command) >= 2 and command[0] == 'insmod' and command[1] in binaries,
            'loaded provider is absent from verified binary manifest')
    expected = {'komb_batch_size': '1024'}
    module = 'tclock_backend_km.ko'
    if kd:
        module = 'kdlock_km.ko'
        expected = dict(bench_quiet='1', bench_complete_probe='1', jit_timing='0',
                        hotlock_stats='1', target_process='rb_worker' if kind == 'taskname' else 'sc_worker',
                        spin_entry_ratio_limit='2', spin_prefetch='2')
        if kind == 'taskname':
            expected['spin_delegate'] = '1'
    pairs = [argument.split('=', 1) for argument in command[2:]]
    require(Path(command[1]).name == module and all(len(pair) == 2 for pair in pairs) and
            len(pairs) == len(expected) and dict(pairs) == expected,
            'provider load parameters differ from the main comparison policy')
    inputs.read(row['name'] + '/' + log + '.log')
    if kd:
        probe = row['parameters'] if kind == 'taskname' else row['probe_parameters']
        gate = row['layout']['gate_addr'] if kind == 'taskname' else row['gate_addr']
        require(number(probe['bench_complete_probe']) == 1 and
                int(probe['bench_lock_addr'], 0) == gate, 'completion counter bound to another lock')
        if kind == 'taskname':
            require(all((probe[key] == value if key == 'target_process' else
                         number(probe[key]) == int(value)) for key, value in expected.items()),
                    'observed KD parameters differ from the recorded load')
        retired_log = 'unload-kdlock.log' if kind == 'taskname' else 'unload-kd.log'
    else:
        if kind == 'taskname':
            require(row['tclock_drained']['quiescent'] == 1 and
                    row['parameters']['komb_batch_size'] == 1024,
                    'TCLock final state or batch policy differs')
        retired_log = 'unload-tclock.log' if kind == 'taskname' else 'unload-tc.log'
    command = inputs.json(row['name'] + '/' + retired_log + '.command.json')['argv']
    require(command == ['rmmod', module[:-3]], 'wrong final provider unload command')
    inputs.read(row['name'] + '/' + retired_log)


def verify_publication(row, inputs):
    before, after = row['published_before'], row['published_after']
    require(before == after, 'publication or source leases changed')
    entry = before['entry']
    begin, end = row['entry_range']
    require(entry['status'] == entry['pid'] == 0 and entry['lock_kind'] == entry['entry_abi'] == 1
            and entry['code'] > 0 and begin <= entry['entry'] < end,
            'measured image is not the expected ready ABI1 spin entry')
    require(before['source']['state'] == 0 and
            before['source']['writers'] == before['source']['frames'] == 0,
            'measured source was not OPEN and drained')
    # The runner copies each publication before the translator can replace its
    # workspace. Check those regular archived files, not workspace symlinks.
    matches = [item for item in row['publications'] if
               item['entry'] == entry and item['images'] == before['images']]
    require(matches and set(before['images']) == {'jit.bin', 'jit.S', 'bin.txt'},
            'missing captured measurement image')
    for item in matches:
        directory = relative_name(item['path'])
        for name, digest in item['images'].items():
            require(sha(inputs.read(row['name'] + '/' + directory + '/' + name)) == digest,
                    'captured JIT image differs: ' + name)


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Evidence:
    """Read named files without extracting archives or following archive links."""
    def __init__(self, path):
        self.path, self.hashes, self.archive, self.members = path, {}, None, {}
        if path.is_dir():
            self.prefix = ''
            return
        self.archive = tarfile.open(path)
        files = [member for member in self.archive if member.isfile()]
        candidates = [member for member in files if Path(member.name).name == 'plan.json']
        require(candidates, 'archive has no plan.json: ' + str(path))
        depth = min(len(Path(member.name).parts) for member in candidates)
        roots = [Path(member.name).parent for member in candidates
                 if len(Path(member.name).parts) == depth]
        require(len(roots) == 1, 'ambiguous archive root: ' + str(path))
        self.prefix = roots[0]
        for member in files:
            name = Path(member.name)
            if name.is_relative_to(self.prefix):
                relative = str(name.relative_to(self.prefix))
                require(relative not in self.members, 'duplicate archive file: ' + relative)
                self.members[relative] = member

    def read(self, name, required=True):
        name = relative_name(name)
        if self.archive:
            member = self.members.get(name)
            blob = self.archive.extractfile(member).read() if member else None
        else:
            file = self.path / name
            blob = file.read_bytes() if file.is_file() else None
        require(blob is not None or not required, 'missing evidence: ' + str(self.path / name))
        if blob is not None:
            self.hashes[name] = sha(blob)
        return blob

    def json(self, name, required=True):
        blob = self.read(name, required)
        return json.loads(blob) if blob is not None else None

    def close(self):
        if self.archive:
            self.archive.close()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row)) or ['no_rows']
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({key: canonical(value) if isinstance(value, (dict, list)) else value
                         for key, value in row.items()} for row in rows)


def case(row, kind):
    return 'taskname' if kind == 'taskname' else 'xattr-tail-n' + str(row['entries']) + '-v64'


def configuration(row, kind):
    return case(row, kind), row['threads'], row['arm'], row['repeat']


def verify_plan(row, kind):
    require(Path(row['name']).name == relative_name(row['name']), 'invalid session name')
    require(row['arm'] in ARMS and row['threads'] in GRID and row['repeat'] in range(3),
            'unexpected backend, worker count or repetition')
    require(row['cpus'] == list(range(row['threads'])) and row['collector_cpu'] == 63 and
            row['duration_ms'] == 2000 and row['peak_window_ms'] == row['peak_settle_ms'] == 300 and
            row['sample_ms'] == 10, 'different placement or measurement timing')
    if kind == 'taskname':
        require(row['workload'] == 'taskname' and row['lock_kind'] == 'spin' and
                row['cachelines'] == row['write_percent'] == 0 and not row['functional'] and
                row['post_work_rounds'] == 4 and row['provider_ubsan'] == 'off',
                'different taskname payload or instrumentation')
        kd = row['arm'] == 'kdlock'
        require(row['warmup_iterations_per_worker'] == 48000 and
                row['helper_iterations_per_worker'] == 240000 and
                row['mix_policy'] == 'evenly_spaced_worker_phase17' and
                row['helper_waves'] == (8 if kd else 0) and
                row['helper_cpus'] == (list(range(16)) if kd else []) and
                row['delegate'] is kd and row['spin_entry_ratio_limit'] == (2 if kd else None) and
                row['entry_abi'] == 1 and row['caller_abi'] == ('clobber' if kd else 'c') and
                row['numa_policy'] == ('not_applicable' if row['arm'] == 'native' else 'on') and
                row['delegation_batch_limit'] == (None if row['arm'] == 'native' else 1024),
                'different taskname preparation, call interface or delegation policy')
    else:
        require(row['kind'] == 'xattr' and row['query'] == 'tail' and row['entries'] in (16, 128) and
                row['value_size'] == 64 and row['jit_evidence_version'] == 2 and
                row['jit_completion_probe'] == (row['arm'] == 'kdlock'),
                'different xattr payload or instrumentation')
        require(row['helper_waves'] == 8 and row['helper_cpus'] == list(range(16)) and
                row['warmup'] == 48000 and row['warmup_ms'] == 1000 and
                row['lock_kind'] == 'spin' and row['syscalls_per_op'] == 1 and
                row['file_descriptions'] == 'shared-query' and
                row['entry_abi'] == (1 if row['arm'] == 'kdlock' else 0) and
                row['caller_abi'] == ('clobber' if row['arm'] == 'kdlock' else 'c'),
                'different xattr preparation or call interface')


def replay_session(row, spec, kind, inputs, oracle, peak, api_evidence, binaries):
    require(all(row.get(key) == value for key, value in spec.items()), 'record differs from plan')
    require(not any(row.get(key) for key in ('functional', 'diagnostic', 'pmu', 'perf_record')) and
            row.get('score_eligible') is not False, 'diagnostic or functional session is not a timing result')
    require(row['execution_status'] == 'OK' and row['drained'] is True, 'failed or undrained session')
    measured = row['measurement']
    raw = inputs.json(row['name'] + '/measure.json')
    require(raw == {key: value for key, value in measured.items() if key != 'peak'},
            'session measurement differs from raw client output')
    verify_runtime_policy(row, kind, inputs, binaries)
    load = inputs.json(row['name'] + '/load-source.log.command.json')['argv']
    expected_source = ('build/' + row['variant'] + '/rwlock_bench.ko' if kind == 'taskname'
                       else 'build/' + row['arm'] + '-xattr/real_api.ko')
    require(len(load) >= 2 and load[0] == 'insmod' and load[1] in binaries and
            binaries[load[1]]['path'] == expected_source,
            'loaded workload does not match the verified backend binary')
    inputs.read(row['name'] + '/kernel.log')
    inputs.read(row['name'] + '/unload-source.log')
    source_unload = inputs.json(row['name'] + '/unload-source.log.command.json')['argv']
    require(source_unload == ['rmmod', 'rwlock_bench' if kind == 'taskname' else 'real_api'],
            'wrong final workload unload command')
    require(measured['wall_ns'] == measured['finished_ns'] - measured['started_ns'] > 0,
            'invalid whole-run interval')
    if kind == 'taskname':
        require(measured['data_ok'] is True, 'taskname data oracle failed')
        derived_peak = oracle.validate(measured, spec)
        evidence = oracle.jit_evidence(row['jit_before'], row['jit_after'], measured['reads'],
            backend=row['arm'], delegate=row['delegate'], operation='snapshot',
            completed=row['jit_complete_after'] - row['jit_complete_before'])
    else:
        require(measured['ok'] is True and measured['completed'] == sum(
            worker['completed'] for worker in measured['workers']) and all(
            worker['error'] == 0 and worker['cpu'] == worker['observed_cpu'] and
            worker['cpu_ns'] > 0 and worker['completed'] > 0 for worker in measured['workers']),
            'xattr result, progress or affinity failed')
        require(row['redirected_calls'] == measured['completed'], 'incomplete xattr substitution')
        require(inputs.json(row['name'] + '/check-after.json')['check'] is True,
                'xattr post-measurement oracle failed')
        derived_peak = peak.analyze_peak(measured, spec)
        evidence = api_evidence.jit_evidence(row['jit_bodies'], row['jit_completions'],
            measured['completed'], enabled=row['arm'] == 'kdlock')
    require(derived_peak == measured['peak'], 'stored peak differs from raw progress replay')
    require(all(row.get(key) == value for key, value in evidence.items()),
            'JIT counts, shares or execution status differ')
    delegation = row['tclock_delegation_status'] if kind == 'taskname' else row['tclock_delegation']
    require(delegation == ('UNMEASURED' if row['arm'] == 'tclock' else 'NOT_APPLICABLE'),
            'unexpected TCLock delegation evidence for spin workloads')
    guards = row.get('address_guard_exits')
    if row['arm'] == 'kdlock':
        require(row.get('retired') == dict(state=2, modules=0, frames=0, writers=0),
                'missing successful KD source retirement')
        verify_publication(row, inputs)
        require(type(guards) is int and guards >= 0 and
                guards == row['address_guards_after'] - row['address_guards_before'],
                'address-guard exits were not measured')
        probe = row['parameters'] if kind == 'taskname' else row['probe_parameters']
        require(str(probe['bench_complete_probe']) in ('1', 'Y'), 'returned-body probe disabled')
    whole = measured['completed'] * 1e9 / measured['wall_ns']
    peak_rate = derived_peak['throughput_ops_s']
    require(all(math.isfinite(value) and value > 0 for value in (whole, peak_rate)), 'invalid throughput')
    for field, value in (('whole_ops_s' if kind == 'taskname' else 'whole_throughput_ops_s', whole),
                         ('peak_ops_s' if kind == 'taskname' else 'peak_throughput_ops_s', peak_rate)):
        require(field not in row or close(row[field], value), 'stored rate differs from replay')
    return dict(whole_ops_s=whole, peak_ops_s=peak_rate, completed=measured['completed'],
        min_worker_completed=min(worker['completed'] for worker in measured['workers']),
        worker_cpu_ns_per_op=sum(worker['cpu_ns'] for worker in measured['workers']) / measured['completed'],
        jit_entries=row['jit_bodies'], jit_completions=row['jit_completions'],
        jit_complete_share=row['jit_complete_share'], jit_status=row['jit_status'],
        address_guard_exits=guards,
        tclock_delegation=delegation)


def read_run(kind, path, modules, dependency_hashes):
    oracle, peak, api_report, api_evidence = modules
    inputs = Evidence(path)
    try:
        plan, records = inputs.json('plan.json'), inputs.json('records.json')
        source, environment = inputs.json('source-sha256.json'), inputs.json('environment.json')
        binaries = inputs.json('binary-sha256.json' if kind == 'taskname' else 'binaries.json')
        verified_binaries = verify_binaries(kind, inputs, binaries, plan)
        for name, expected_hash in source.items():
            require(sha(inputs.read('source/' + name)) == expected_hash,
                    kind + ': frozen source bytes differ: ' + name)
        dependencies = DEPENDENCIES[:2] if kind == 'taskname' else (DEPENDENCIES[0], *DEPENDENCIES[2:])
        require(all(source.get(name) == dependency_hashes[name] for name in dependencies),
                kind + ': analysis helper differs from the frozen runner source')
        saved = {row['name']: row for row in records}
        require(len(saved) == len(records) and len({row['name'] for row in plan}) == len(plan),
                kind + ': duplicate session name')
        require(saved.keys() <= {row['name'] for row in plan}, kind + ': unplanned recorded session')
        expected_cases = ['taskname'] if kind == 'taskname' else ['xattr-tail-n16-v64', 'xattr-tail-n128-v64']
        expected = {(name, count, arm, repeat) for name in expected_cases for count in GRID
                    for arm in ARMS for repeat in range(3)}
        actual = {configuration(row, kind) for row in plan}
        require(len(actual) == len(plan) and actual <= expected, kind + ': duplicate or unexpected configuration')
        source_id = sha(canonical(source).encode())
        sessions, groups, accepted = [], defaultdict(list), []
        for spec in plan:
            verify_plan(spec, kind)
            row = saved.get(spec['name'], dict(spec, execution_status='NOT_RUN', drained=False))
            receipt = dict(run=kind, name=spec['name'], case=case(spec, kind), threads=spec['threads'],
                arm=spec['arm'], repeat=spec['repeat'], execution_status=row['execution_status'],
                drained=row.get('drained', False), valid=False, source_id=source_id)
            sessions.append(receipt)
            try:
                stored_session = inputs.json(spec['name'] + '/session.json', required=False)
                require(stored_session is not None and all(row.get(key) == value
                    for key, value in stored_session.items()), 'missing or inconsistent per-session receipt')
                receipt.update(replay_session(row, spec, kind, inputs, oracle, peak, api_evidence, verified_binaries), valid=True)
                identity = ({key: row.get(key) for key in TASK_IDENTITY} if kind == 'taskname'
                            else api_report.comparison_identity(row))
                if kind == 'taskname':
                    identity['probe'] = {key: row.get('parameters', {}).get(key)
                        for key in ('bench_complete_probe', 'bench_quiet', 'hotlock_stats', 'jit_timing')}
                else:
                    require(row['source_identity'] == sha(json.dumps(source, sort_keys=True).encode()),
                            'source identity differs from frozen source hashes')
                    require(row['kernel_identity'] == sha(inputs.read('kernel-identity.json')) and
                            row['topology_identity'] == sha(inputs.read('topology.txt')),
                            'kernel or topology identity differs')
                receipt['identity'] = identity
                key = receipt['case'], receipt['threads'], receipt['arm'], receipt['jit_status'], canonical(identity)
                groups[key].append(receipt)
                accepted.append(row)
            except (ValueError, KeyError, TypeError) as error:
                receipt.update(valid=False, error=str(error))
        summaries = []
        for key, cohort in sorted(groups.items()):
            group = dict(run=kind, case=key[0], threads=key[1], arm=key[2], jit_status=key[3],
                identity=json.loads(key[4]), source_id=source_id, valid_rounds=len(cohort),
                complete=len(cohort) == 3, samples=[row['name'] for row in cohort])
            for metric in ('whole_ops_s', 'peak_ops_s', 'worker_cpu_ns_per_op', 'jit_complete_share'):
                values = [row[metric] for row in cohort]
                group.update({metric + '_min': min(values), metric + '_median': statistics.median(values),
                              metric + '_max': max(values)})
            for metric in ('jit_entries', 'jit_completions', 'address_guard_exits'):
                values = [row[metric] for row in cohort]
                group[metric + '_total'] = sum(values) if all(value is not None for value in values) else None
            summaries.append(group)
        # Reuse the syscall reporter's independent grouping policy as a check;
        # it must agree with the groups admitted by raw validation above.
        if kind == 'xattr':
            reused = api_report.summarize(accepted)
            require(len(reused) == len(summaries), 'syscall grouping differs from replay')
            for group in summaries:
                candidates = [row for row in reused if row['entries'] == int(group['case'].split('-n')[1].split('-')[0])
                    and row['threads'] == group['threads'] and row['arm'] == group['arm'] and
                    row['execution_group'] == group['jit_status'] and row['identity'] == group['identity']]
                require(len(candidates) == 1 and candidates[0]['accepted'] == group['valid_rounds'] and
                        close(candidates[0]['whole_median'], group['whole_ops_s_median']) and
                        close(candidates[0]['peak_median'], group['peak_ops_s_median']),
                        'syscall summary differs from raw replay')
        complete = len(plan) == len(expected) and all(row['valid'] for row in sessions)
        return dict(path=str(path), complete=complete, expected_sessions=len(expected),
            planned_sessions=len(plan), valid_sessions=sum(row['valid'] for row in sessions),
            missing_configurations=sorted(expected - actual), source_id=source_id, source_sha256=source,
            environment=environment, binaries=binaries, verified_binaries=verified_binaries, input_sha256=inputs.hashes,
            all_sessions_drained=all(row['drained'] for row in sessions), sessions=sessions, groups=summaries,
            kd_status_counts=dict(Counter(row['jit_status'] for row in sessions
                if row['valid'] and row['arm'] == 'kdlock')))
    finally:
        inputs.close()


def comparisons(runs):
    points = []
    for kind, run in runs.items():
        cases = ['taskname'] if kind == 'taskname' else ['xattr-tail-n16-v64', 'xattr-tail-n128-v64']
        for name in cases:
            for count in GRID:
                point, selected = dict(case=name, threads=count), {}
                for arm in ARMS:
                    groups = [row for row in run['groups'] if
                              (row['case'], row['threads'], row['arm']) == (name, count, arm)]
                    group = groups[0] if len(groups) == 1 and groups[0]['complete'] else None
                    selected[arm] = group
                    point[arm + '_groups'] = [dict(jit_status=row['jit_status'], valid_rounds=row['valid_rounds'])
                                              for row in groups]
                    for field in ('whole_ops_s_median', 'peak_ops_s_median', 'jit_complete_share_median',
                                  'address_guard_exits_total'):
                        point[arm + '_' + field] = group[field] if group else None
                for other in ('native', 'tclock'):
                    kd, control = selected['kdlock'], selected[other]
                    fields = COMMON_IDENTITY + (('post_work_rounds', 'warmup_iterations_per_worker', 'mix_policy')
                        if kind == 'taskname' else ('warmup', 'warmup_ms', 'helper_waves', 'helper_cpus', 'file_descriptions'))
                    matched = kd and control and all(kd['identity'].get(key) == control['identity'].get(key)
                                                     for key in fields)
                    for metric in ('whole', 'peak'):
                        field = metric + '_ops_s_median'
                        point['kd_' + other + '_' + metric + '_ratio'] = kd[field] / control[field] if matched else None
                points.append(point)
    return points


def plots(out, groups):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for name in sorted({row['case'] for row in groups}):
        figure, axes = plt.subplots(1, 2, figsize=(12, 4))
        for arm, color in zip(ARMS, ('#2762ad', '#de9220', '#b62837')):
            for status in sorted({row['jit_status'] for row in groups if row['case'] == name and row['arm'] == arm}):
                selected = sorted((row for row in groups if
                    (row['case'], row['arm'], row['jit_status']) == (name, arm, status)), key=lambda row: row['threads'])
                # Separate incomplete/status groups; no three-run median is
                # manufactured by pooling observations across execution paths.
                for complete in (True, False):
                    rows = [row for row in selected if row['complete'] == complete]
                    if not rows:
                        continue
                    label = arm + (' ' + status if arm == 'kdlock' else '') + ('' if complete else ' (<3 rounds)')
                    style = 'o-' if complete and status in ('PASS', 'NATIVE', 'NOT_APPLICABLE') else 'x--'
                    for ax, metric in zip(axes, ('whole', 'peak')):
                        ax.plot([row['threads'] for row in rows],
                                [row[metric + '_ops_s_median'] / 1e6 for row in rows], style, color=color, label=label)
                        ax.set(xlabel='Pinned workers', ylabel='Million operations/second',
                               title='Whole-run median' if metric == 'whole' else '300 ms peak median')
                        ax.grid(alpha=.2)
        axes[0].legend(fontsize=8)
        figure.suptitle(name)
        figure.tight_layout()
        figure.savefig(out / (name + '.png'), dpi=180)
        figure.savefig(out / (name + '.svg'))
        plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_map', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--plots', action='store_true')
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    require(not args.output.exists(), 'use a new report output directory')
    mapping = json.loads(args.run_map.read_text())
    require(set(mapping) <= {'taskname', 'xattr'} and mapping, 'unknown or empty run map')
    hashes = {name: sha((ROOT / name).read_bytes()) for name in DEPENDENCIES}
    modules = (load_module('taskname_oracle', DEPENDENCIES[1]), load_module('comparison_peak', DEPENDENCIES[0]),
               load_module('xattr_report', DEPENDENCIES[2]), load_module('xattr_evidence', DEPENDENCIES[3]))
    runs = {kind: read_run(kind, (args.run_map.resolve().parent / path).resolve(), modules, hashes)
            for kind, path in mapping.items()}
    if set(runs) == {'taskname', 'xattr'}:
        left, right = runs['taskname']['source_sha256'], runs['xattr']['source_sha256']
        require(all(left[name] == right[name] for name in left.keys() & right.keys()),
                'taskname and xattr runs use different shared implementation sources')
    passed = set(runs) == {'taskname', 'xattr'} and all(run['complete'] for run in runs.values())
    output = dict(schema=1, complete=passed, runs=runs, points=comparisons(runs),
        script_sha256=sha(Path(__file__).read_bytes()), dependency_sha256=hashes,
        run_map_sha256=sha(args.run_map.read_bytes()),
        limits=['Taskname is an extracted snapshot, not a complete procfs or ps benchmark.',
                'Xattr includes one validated fgetxattr syscall per operation.',
                'TCLock spin delegation is unmeasured; KD counters do not classify TCLock execution.',
                'Whole and peak ratios both use medians of three homogeneous repetitions.',
                'Groups with fewer than three homogeneous repetitions remain visible without comparison ratios; NO_JIT and PARTIAL_JIT labels remain explicit.',
                'Read-only replay validates recorded evidence; it is not a fresh correctness test.'])
    args.output.mkdir(parents=True)
    write_json(args.output / 'replay.json', output)
    groups = [group for run in runs.values() for group in run['groups']]
    write_csv(args.output / 'sessions.csv', [row for run in runs.values() for row in run['sessions']])
    write_csv(args.output / 'groups.csv', groups)
    write_csv(args.output / 'comparison.csv', output['points'])
    if args.plots:
        plots(args.output, groups)
    print(json.dumps(dict(complete=passed, runs={kind: {key: run[key] for key in
        ('expected_sessions', 'valid_sessions', 'all_sessions_drained', 'kd_status_counts')}
        for kind, run in runs.items()}), indent=2))
    return 0 if passed or args.allow_partial else 1


if __name__ == '__main__':
    raise SystemExit(main())
