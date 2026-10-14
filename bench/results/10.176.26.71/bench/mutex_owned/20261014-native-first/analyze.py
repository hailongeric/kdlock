#!/usr/bin/env python3
"""Audit owned native-first c01/post64 stages; never run a workload.

Declare finite/refill baselines separately. Candidate groups are screens unless
--confirmations SCREEN BLOCK1 BLOCK2 explicitly identifies two fresh blocks.
No legacy KD, TClock or qspinlock measurements enter this study.
"""
import argparse
import csv
import gzip
import importlib.util
import io
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
HELPER = HERE/'evidence.py'
module_spec = importlib.util.spec_from_file_location('owned_evidence_audit', HELPER)
audit = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(audit)
study, require = audit.study, audit.require

QUEUE = {'finite': 'finite_fifo', 'refill': 'bounded_fifo_refill'}
TABLES = ('statistics', 'samples', 'workers', 'progress', 'batches', 'pmu',
          'flat-profiles', 'lock-profiles', 'batch-histograms', 'owned-preflight-profiles',
          'owned-native-first-profiles')
VARYING_PLAN_FIELDS = {'name', 'threads', 'repeat', 'cpus', 'cpu_nodes'}
PREFLIGHT_COUNTERS = ('gate_self', 'gate_capture', 'optimistic_acquired',
                      'optimistic_busy', 'optimistic_self', 'optimistic_other', 'missed')


def baseline_identity(rows):
    """Fresh d8d14a1 references retain the default ABI2 capture-first policy."""
    for row in rows:
        if row['arm'] != 'kdlock':
            continue
        require(row['entry_abi'] == 2 and row['owned_mutex_entry_ratio_limit'] == 256 and
                row.get('owned_preflight_policy') == 'capture_first' and
                row.get('owned_mutex_preflight') is False and
                row.get('owned_mutex_preflight_spins') == 0 and
                row.get('owned_mutex_preflight_queue') is False and
                not row.get('owned_mutex_cabi', False) and
                not row.get('owned_mutex_native_first', False) and
                not row.get('owned_mutex_early_release', False),
                'baseline is not the default d8d14a1 owned acquisition/release policy')


def write_progress(path, rows):
    """Preserve the CSV bytes with a reproducible gzip header and no filename."""
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)


def policy_identity(folder):
    """Include all planned controls, including newly added candidate switches."""
    plans = audit.read(folder/'plan.json')
    policies = {json.dumps({k: v for k, v in spec.items() if k not in VARYING_PLAN_FIELDS},
                           sort_keys=True) for spec in plans if spec['arm'] == 'kdlock'}
    require(len(policies) <= 1, 'mixed owned policies in ' + str(folder))
    return json.loads(next(iter(policies))) if policies else None


def audit_owned_preflight(folder, rows):
    """Audit the independent opt-in receipt without changing lock_profile."""
    audited = 0
    prefix = 'kd_mutex_profile ownedpreflight:'
    for record in rows:
        enabled = record.get('profile_owned_preflight', False)
        require(type(enabled) is bool, 'preflight profiling flag is not boolean')
        log = (folder/record['name']/'kernel.log').read_text()
        if not enabled:
            require('owned_preflight_profile' not in record and prefix not in log,
                    'undeclared preflight profile receipt: ' + record['name'])
            continue
        require(record['diagnostic'] is True and record.get('profile_lock') is True and
                record['arm'] == 'kdlock' and record.get('mutex_implementation') == 'owned-v1' and
                record.get('owned_preflight_policy') == 'c_abi_v1',
                'preflight counters require an owned C-ABI diagnostic lock profile')
        receipts = re.findall(re.escape(prefix) + r'([^\n]*)', log)
        require(len(receipts) == 1, 'missing/duplicate owned preflight receipt')
        tokens = receipts[0].split()
        pairs = [re.fullmatch(r'(\w+)=(\d+)', token) for token in tokens]
        require(tokens and all(pairs), 'malformed owned preflight counter')
        counts = {pair[1]: int(pair[2]) for pair in pairs}
        require(len(counts) == len(pairs), 'duplicate owned preflight counter')
        saved = record.get('owned_preflight_profile')
        require(set(counts) == set(PREFLIGHT_COUNTERS) and isinstance(saved, dict) and
                all(type(value) is int and value >= 0 for value in saved.values()) and saved == counts,
                'preflight counter fields or saved/raw receipt differ')
        require(counts['missed'] == counts['optimistic_other'] == 0,
                'preflight profiler missed calls or observed an unknown result')
        acquired, busy, self = (counts['optimistic_' + name] for name in ('acquired', 'busy', 'self'))
        require(acquired + self <= counts['gate_self'] and counts['gate_capture'] <= busy and
                acquired + busy + self <= counts['gate_self'] + counts['gate_capture'],
                'preflight helper/gate outcome counts are inconsistent')
        # The ordinary shared profile audit separately requires zero original
        # Linux target lock/slow-lock/unlock calls and zero missed probes.
        record['_owned_preflight'] = counts
        audited += 1
    return audited


def audit_native_first(folder, rows):
    from experiment_policy import parse_owned_native_first_profile
    count = 0
    for record in rows:
        log = (folder/record['name']/'kernel.log').read_text()
        observed = parse_owned_native_first_profile(log, record)
        if observed is None:
            require('owned_native_first_profile' not in record,
                    'undeclared native-first profile dictionary')
            continue
        saved = record.get('owned_native_first_profile')
        require(isinstance(saved, dict) and saved == observed and
                all(type(value) is int and value >= 0 for value in saved.values()),
                'native-first raw/recorded counters differ')
        record['_owned_native_first'] = observed
        count += 1
    return count


def require_owned(rows, diagnostic):
    require({r['arm'] for r in rows} <= {'native', 'kdlock'} and
            all(r['lock_kind'] == 'mutex' for r in rows),
            'this report accepts only Native and owned KD mutex evidence')
    geometries = set()
    for record in rows:
        layout = record['layout']
        require(layout['lock_bytes'] == 32 and layout['line_bytes'] == 64 and
                layout['lock_addr'] % 64 == layout['data_addr'] % 64 == 0,
                'Native/owned object size or cacheline alignment differs')
        geometries.add((layout['lock_addr']-layout['data_addr'], layout['slots'],
                        tuple(address-layout['data_addr'] for address in layout['slot_addr'])))
        require(record.get('post_work_rounds') == 64,
                'fresh evidence must explicitly record post64')
        if record['arm'] == 'kdlock':
            require(record.get('mutex_implementation') == 'owned-v1' and
                    record.get('owned_queue_policy') in QUEUE.values(),
                    'owned-v1 and an explicit finite/refill queue identity are required')
            study.require_owned_identity(record)
            require(record.get('mutex_routing') in (('adaptive', 'self') if diagnostic else ('adaptive',)),
                    'Linux native routing is not an owned execution mode')
            if not diagnostic:
                require(record['mutex_acceptance'] == 'adaptive-performance',
                        'scored owned runs require adaptive-performance acceptance')
    require(len(geometries) == 1, 'Native/owned workload cacheline geometry differs within the run')
    if not diagnostic:
        require({r['arm'] for r in rows} == {'native', 'kdlock'},
                'each scored group needs owned KD and paired Native controls')
        require({r['threads'] for r in rows} <= set(study.GRID),
                'scored cohort is outside the declared study grid')
        require_alternating_rounds(rows)


def require_alternating_rounds(rows):
    """The audited record order is the frozen plan order and actual run order."""
    for threads in {r['threads'] for r in rows}:
        cohort = [r for r in rows if r['threads'] == threads]
        require(len(cohort) == 6 and {r['repeat'] for r in cohort} == {0, 1, 2},
                'each scored cohort needs all six Native/owned samples')
        orders = [[r['arm'] for r in cohort if r['repeat'] == repeat] for repeat in range(3)]
        require(set(orders[0]) == {'native', 'kdlock'} and
                orders[1] == orders[0][::-1] and orders[2] == orders[0],
                'three rounds must alternate backend order')
        require([r['repeat'] for r in cohort] == [0, 0, 1, 1, 2, 2],
                'planned rounds were reordered')
    require(all(left['measurement']['finished_ns'] < right['measurement']['started_ns']
                for left, right in zip(rows, rows[1:])),
            'actual sample order differs from the frozen sequential plan')


def baseline_key(rows):
    policies = {r['owned_queue_policy'] for r in rows if r['arm'] == 'kdlock'}
    require(len(policies) == 1, 'one owned queue policy is required per scored group')
    return next(key for key, policy in QUEUE.items() if policy in policies)


def coverage(rows):
    counts = sorted({r['threads'] for r in rows if r['arm'] == 'kdlock'})
    return dict(worker_counts=counts,
                missing_primary=sorted(set(study.PRIMARY)-set(counts)),
                missing_regression=sorted(set(study.REGRESSION)-set(counts)),
                regression_complete=set(study.REGRESSION) <= set(counts),
                full_grid=set(counts) == set(study.GRID))


def evaluate(label, candidate, baselines):
    key = baseline_key(candidate)
    baseline = baselines.get(key, [])
    reference_counts = {r['threads'] for r in baseline if r['arm'] == 'kdlock'}
    candidate_counts = {r['threads'] for r in candidate if r['arm'] == 'kdlock'}
    checks, missing_references = [], []
    for threads in sorted(candidate_counts):
        kd = study.metrics([r for r in candidate if r['arm'] == 'kdlock' and r['threads'] == threads])
        primary = threads in study.PRIMARY
        if not primary and threads not in reference_counts:
            missing_references.append(threads)
            continue
        reference_rows = candidate if primary else baseline
        arm = 'native' if primary else 'kdlock'
        control = study.metrics([r for r in reference_rows if r['arm'] == arm and r['threads'] == threads])
        ratios = {name: kd[name]/control[name] for name in ('median_whole', 'best_peak')}
        jit_ok = primary or all(value > 0 for value in kd['jit_bodies'])
        checks.append(dict(threads=threads,
            reference_group=label if primary else key,
            reference='paired_native' if primary else 'same_policy_owned_baseline',
            ratios=ratios, minimum_ratio=.97, jit_ok=jit_ok,
            passed=all(value >= .97 for value in ratios.values()) and jit_ok,
            candidate=kd, control=control))
    covered = coverage(candidate)
    reference_coverage = coverage(baseline)
    complete = covered['full_grid'] and reference_coverage['regression_complete'] and not missing_references
    verdict = ('REJECTED' if any(not check['passed'] for check in checks) else
               'PASS' if complete else 'INCOMPLETE')
    return dict(gate_verdict=verdict, establishes_final_acceptance=False,
                baseline=key, queue_policy=QUEUE[key], **covered,
                baseline_coverage=reference_coverage,
                missing_measured_regression_references=missing_references,
                checks=checks)


def acceptance(runs, baselines, folders, policies, confirmations):
    result = dict(schema=1, target_reached=False, performance_target_reached=False,
        selected_candidate=None, selected_default=None,
        primary=list(study.PRIMARY), regression=list(study.REGRESSION),
        acceptance='Each block: median whole-run and best valid warmed peak independently >=97% of paired Native at primary counts; both >=97% of the fresh same-queue owned baseline at regression counts, with returned JIT bodies in every regression sample.',
        baselines={key: dict(queue_policy=QUEUE[key], **coverage(rows)) for key, rows in baselines.items()},
        trials={label: evaluate(label, rows, baselines) for label, rows in runs.items()},
        confirmation_declaration=list(confirmations), missing_gates=[],
        correctness_validation='Separate unit/live/recovery evidence remains required; this file establishes performance gates only.')
    for trial in result['trials'].values():
        trial['role'] = 'screen'
    for key in QUEUE:
        if key not in baselines:
            result['missing_gates'].append('No fresh ' + key + ' owned baseline declared')
        elif not coverage(baselines[key])['regression_complete']:
            result['missing_gates'].append(key + ' baseline is missing regression counts')
    if not runs:
        result['missing_gates'].append('No candidate screens declared')
    if not confirmations:
        result['missing_gates'].append('No selected screen and two fresh confirmation blocks declared')
        return result
    screen, first, second = confirmations
    require(len(set(confirmations)) == 3 and all(label in runs for label in confirmations),
            'confirmations must name a screen and two distinct declared scored groups')
    for label in (first, second):
        result['trials'][label]['role'] = 'confirmation'
        require(policies[label] == policies[screen],
                'confirmation planned controls differ from selected screen: ' + label)
        require(audit.read(folders[label]/'source-sha256.json') ==
                audit.read(folders[screen]/'source-sha256.json'),
                'confirmation frozen source differs from selected screen: ' + label)
    result['selected_screen'] = screen
    # All group sample identities have already been checked for reuse. Merely
    # naming a screen or a short passing rung never makes a final acceptance.
    passed = all(result['trials'][label]['gate_verdict'] == 'PASS' for label in confirmations)
    if not passed:
        result['missing_gates'].append('Selected screen and both independent confirmation blocks must each pass the complete grid')
    if result['missing_gates']:
        return result
    result.update(target_reached=True, performance_target_reached=True,
                  selected_candidate=screen, selected_policy=policies[screen])
    for label in (first, second):
        result['trials'][label]['establishes_final_acceptance'] = True
    return result


def progress_rows(label, rows):
    """Retain sampled per-worker progress; no interpolation or resampling."""
    for record in rows:
        ident, measurement = audit.identity(label, record), record['measurement']
        peak = measurement['peak']
        previous = [0] * record['threads']
        for index, snapshot in enumerate(measurement['samples']):
            deltas = [after-before for after, before in zip(snapshot['completed'], previous)]
            yield dict(**ident, sample_index=index,
                snapshot_started_ns=snapshot['started_ns'], snapshot_finished_ns=snapshot['finished_ns'],
                elapsed_ns=snapshot['finished_ns']-measurement['started_ns'],
                cpus_json=json.dumps(record['cpus'], separators=(',', ':')),
                sampled_completed_json=json.dumps(snapshot['completed'], separators=(',', ':')),
                delta_since_previous_json=json.dumps(deltas, separators=(',', ':')) if index else None,
                peak_start=index == peak['start_sample_index'], peak_end=index == peak['end_sample_index'])
            previous = snapshot['completed']


def compare_stages(pairs, audited, policies, receipts):
    """Explicit changes and paired Native drift accompany each owned ratio."""
    result = []
    for child, parent in pairs.items():
        require(child != parent and child in audited and parent in audited and
                not receipts[child]['diagnostic'] and not receipts[parent]['diagnostic'],
                'stage comparisons require two distinct scored groups')
        require(baseline_key(audited[child]) == baseline_key(audited[parent]),
                'stage comparisons must keep the same queue policy')
        changes = {key: [policies[parent].get(key, 'unrecorded'),
                         policies[child].get(key, 'unrecorded')]
                   for key in set(policies[parent]) | set(policies[child])
                   if policies[parent].get(key, 'unrecorded') != policies[child].get(key, 'unrecorded')}
        shared = set(coverage(audited[child])['worker_counts']) & set(coverage(audited[parent])['worker_counts'])
        for threads in sorted(shared):
            row = dict(group=child, reference_group=parent, threads=threads,
                queue_policy=QUEUE[baseline_key(audited[child])],
                same_source_manifest=receipts[child]['source_manifest_sha256'] == receipts[parent]['source_manifest_sha256'],
                candidate_source_manifest_sha256=receipts[child]['source_manifest_sha256'],
                reference_source_manifest_sha256=receipts[parent]['source_manifest_sha256'],
                changed_planned_fields_json=json.dumps(changes, sort_keys=True, separators=(',', ':')))
            for arm in ('kdlock', 'native'):
                def metrics(label):
                    return study.metrics([r for r in audited[label] if r['threads'] == threads and r['arm'] == arm])
                current, previous = metrics(child), metrics(parent)
                for measure in ('median_whole', 'best_peak'):
                    row[arm+'_'+measure+'_ratio'] = current[measure]/previous[measure]
            result.append(row)
    return result


def enrich_tables(label, rows, tables, role, policy):
    offsets = {name: len(values) for name, values in tables.items()}
    audit.summarize(label, rows, tables)
    tables['progress'].extend(progress_rows(label, rows))
    for record in rows:
        if '_owned_native_first' in record:
            counts = record['_owned_native_first']
            calls = sum(counts[key] for key in ('acquired', 'promote', 'self'))
            tables['owned-native-first-profiles'].append(dict(**audit.identity(label, record),
                **counts, helper_calls=calls, scope='after_warmup_until_profile_drain',
                owned_mutex_native_first_spins=record['owned_mutex_native_first_spins'],
                acquired_fraction=counts['acquired']/calls if calls else None,
                promote_fraction=counts['promote']/calls if calls else None,
                self_fraction=counts['self']/calls if calls else None))
        if '_owned_preflight' not in record:
            continue
        counts = record['_owned_preflight']
        gates = counts['gate_self'] + counts['gate_capture']
        optimistic = sum(counts['optimistic_' + key] for key in ('acquired', 'busy', 'self'))
        tables['owned-preflight-profiles'].append(dict(**audit.identity(label, record), **counts,
            scope='after_warmup_until_profile_drain',
            owned_preflight_policy=record['owned_preflight_policy'],
            owned_mutex_preflight_spins=record.get('owned_mutex_preflight_spins'),
            owned_mutex_preflight_queue=record.get('owned_mutex_preflight_queue', 'unrecorded'),
            gate_calls=gates, optimistic_calls=optimistic,
            gate_self_fraction=counts['gate_self']/gates if gates else None,
            gate_capture_fraction=counts['gate_capture']/gates if gates else None,
            optimistic_acquired_fraction=counts['optimistic_acquired']/optimistic if optimistic else None))
    policy_json = json.dumps(policy, sort_keys=True, separators=(',', ':')) if policy else '{}'
    for name in TABLES:
        for row in tables[name][offsets[name]:]:
            row['role'] = role
            if name in ('samples', 'statistics'):
                row['planned_owned_policy_json'] = policy_json
                for key, value in (policy or {}).items():
                    if key.startswith(('owned_', 'mutex_')) and key not in row:
                        row[key] = value if row['arm'] == 'kdlock' else None
                if row['arm'] == 'kdlock':
                    # The capture-first runner predates these explicit flags.
                    # Preserve its original plan above; only label the display.
                    row.setdefault('owned_preflight_policy', 'capture_first')
                    row.setdefault('owned_mutex_preflight_spins', None)
                    row['owned_preflight_policy_recorded'] = 'owned_preflight_policy' in (policy or {})
    samples = {r['name']: r for r in rows}
    for row in tables['samples'][offsets['samples']:]:
        record = samples[row['sample']]
        measurement, peak = record['measurement'], record['measurement']['peak']
        row.update(started_ns=measurement['started_ns'], finished_ns=measurement['finished_ns'],
            every_worker_progress=all(w['completed'] > 0 for w in measurement['workers']),
            peak_every_worker_progress=all(n > 0 for n in peak['worker_completed']),
            peak_elapsed_ns=peak['elapsed_ns'], peak_start_sample_index=peak['start_sample_index'],
            peak_end_sample_index=peak['end_sample_index'],
            peak_count_error_bound=peak['progress_count_error_bound'],
            frozen_source_and_raw_verified=True, final_drain_active=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=HERE)
    parser.add_argument('--baselines', nargs='+', default=[], metavar='finite=PATH|refill=PATH')
    parser.add_argument('--controls', nargs='+', default=[], metavar='LABEL=PATH',
                        help='paired owned/Native stage controls, excluded from candidate acceptance')
    parser.add_argument('--runs', nargs='+', default=[], metavar='LABEL=PATH')
    parser.add_argument('--diagnostics', nargs='+', default=[], metavar='LABEL=PATH')
    parser.add_argument('--compare', nargs='+', default=[], metavar='CHILD=PARENT',
                        help='explicit stage contrasts; defaults to each candidate against its same-queue baseline')
    parser.add_argument('--confirmations', nargs=3, default=[], metavar=('SCREEN', 'BLOCK1', 'BLOCK2'))
    parser.add_argument('--baseline-source-manifest-sha256',
                        help='optional exact expected SHA256 of both fresh baseline source manifests')
    args = parser.parse_args()
    raw = args.raw.resolve()
    baselines = audit.declared(raw, args.baselines)
    controls = audit.declared(raw, args.controls)
    runs, diagnostics = audit.declared(raw, args.runs), audit.declared(raw, args.diagnostics)
    require(set(baselines) <= set(QUEUE), 'baseline labels must be finite and/or refill')
    declared_labels = [*baselines, *controls, *runs, *diagnostics]
    require(len(set(declared_labels)) == len(declared_labels),
            'duplicate labels across baseline, screen and diagnostic groups')
    folders = {**baselines, **controls, **runs, **diagnostics}
    require(folders and len(set(folders.values())) == len(folders), 'empty declaration or reused run folder')
    require(not args.confirmations or all(label in runs for label in args.confirmations),
            'confirmation labels must be declared with --runs')
    tables = {name: [] for name in TABLES}
    receipts, audited, policies, seen = {}, {}, {}, set()
    for label, folder in folders.items():
        diagnostic = label in diagnostics
        rows, receipt = audit.audit_group(label, folder, diagnostic)
        receipt['owned_preflight_profiles_verified'] = audit_owned_preflight(folder, rows)
        receipt['owned_native_first_profiles_verified'] = audit_native_first(folder, rows)
        require_owned(rows, diagnostic)
        if label in baselines:
            require(baseline_key(rows) == label, 'baseline label does not match its owned queue policy')
            baseline_identity(rows)
            if args.baseline_source_manifest_sha256:
                require(receipt['source_manifest_sha256'] == args.baseline_source_manifest_sha256,
                        'fresh baseline frozen source manifest differs from declared reference')
        study.require_fresh(rows, seen)
        policy = policy_identity(folder)
        role = ('baseline' if label in baselines else 'control' if label in controls else 'diagnostic' if diagnostic else
                'confirmation' if label in args.confirmations[1:] else 'screen')
        receipt.update(path=str(folder.relative_to(raw)), role=role, planned_owned_policy=policy,
                       alternating_three_rounds_verified=not diagnostic)
        receipts[label], audited[label], policies[label] = receipt, rows, policy
        enrich_tables(label, rows, tables, role, policy)
    if len(baselines) == 2:
        require(audit.read(baselines['finite']/'source-sha256.json') ==
                audit.read(baselines['refill']/'source-sha256.json'),
                'finite and refill baselines must freeze the same source checkout')
    decision = acceptance({label: audited[label] for label in runs},
                          {label: audited[label] for label in baselines}, folders, policies, args.confirmations)
    comparisons = {label: baseline_key(audited[label]) for label in runs
                   if baseline_key(audited[label]) in baselines}
    for declaration in args.compare:
        child, separator, parent = declaration.partition('=')
        require(separator and child in runs and parent in folders,
                'stage comparison must name a candidate and a declared reference')
        comparisons[child] = parent
    contrasts = compare_stages(comparisons, audited, policies, receipts)
    undeclared = []
    for plan in sorted(raw.rglob('plan.json')):
        if plan.parent.resolve() in folders.values() or 'source' in plan.relative_to(raw).parts:
            continue
        specs = audit.read(plan)
        if not isinstance(specs, list) or not all(isinstance(spec, dict) and 'name' in spec for spec in specs):
            continue  # A non-runner test plan is separate validation evidence.
        undeclared.append(dict(path=str(plan.parent.relative_to(raw)), planned=len(specs),
            existing_sessions=sum((plan.parent/spec['name']/'session.json').exists() for spec in specs),
            audited=False))
    report = dict(schema=1, passed=True, post_work_rounds=64, runs=receipts,
        study='owned-native-first-20261014', baseline_reference_commit='d8d14a1',
        baseline_source_manifest_expected=args.baseline_source_manifest_sha256,
        stage_comparisons=comparisons,
        baseline_commit_provenance='The recorded commit is the study declaration; frozen manifests are independently byte-audited. Explicit expected-manifest matching is recorded when supplied.',
        baseline_sessions=sum(len(audited[label]) for label in baselines),
        control_sessions=sum(len(audited[label]) for label in controls),
        candidate_sessions=sum(len(audited[label]) for label in runs),
        diagnostic_sessions=sum(len(audited[label]) for label in diagnostics),
        undeclared_runs=undeclared, command=sys.argv,
        analyzer_sha256=audit.digest(Path(__file__)), shared_auditor_sha256=audit.digest(HELPER),
        policy_auditor_sha256=audit.digest(HERE/'experiment_policy.py'),
        study_auditor_sha256=audit.digest(HERE/'study_audit.py'),
        generic_validator_sha256={name: audit.digest(ROOT/'bench/spin_cacheline'/name)
                                  for name in ('bench_runtime.py', 'summarize.py', 'peak.py')},
        progress_export=dict(path='progress.csv.gz', format='csv', compression='gzip',
                             gzip_mtime=0, gzip_original_filename='', rows=len(tables['progress'])),
        limits=['All declared samples are required; an audit failure stops publication, never drops a round.',
                'Distinct source/policy groups and confirmation blocks are never pooled.',
                'Freshness means distinct declared folders and non-reused raw sample identities; archive hashes establish internal consistency, not independent execution authentication.',
                'Screen PASS means complete measured gates passed once; it is never final acceptance.',
                'Diagnostics, including SELF routing, remain unscored.',
                'The peak is the maximum valid observed full-cohort warmed window, not an interpolated or instantaneous rate.',
                'Progress counts have 256-operation checkpoints; zero sampled deltas are not a bound on scheduling or starvation.',
                'Worker CPU cost excludes collector and other VM/host overhead.',
                'Sampled ownership transitions and generic cache misses do not measure exact ownership streaks or cacheline transfers.',
                'Recovery, host placement/governor and unit/live correctness receipts must be reviewed separately.'])
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        if name == 'progress':
            write_progress(args.out/'progress.csv.gz', rows)
        else:
            audit.csv_write(args.out/(name+'.csv'), rows)
    audit.write_json(args.out/'coverage.json', report)
    audit.write_json(args.out/'acceptance.json', decision)
    audit.csv_write(args.out/'comparisons.csv', contrasts)
    print(json.dumps(dict(passed=True, baseline_sessions=report['baseline_sessions'],
        control_sessions=report['control_sessions'],
        candidate_sessions=report['candidate_sessions'], diagnostic_sessions=report['diagnostic_sessions'],
        target_reached=decision['target_reached'], output=str(args.out))))


if __name__ == '__main__':
    main()
