#!/usr/bin/env python3
"""Audit and plot the completed October 28 nano run; execute only in the idle guest."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
COMMIT = 'edf1cc06d68d476b8d4382a9f24258471a76f8d3'
THREADS = [*range(1, 9), *range(12, 61, 4)]
ARMS = ('native', 'tclock', 'kdlock')
PROFILES = [
    ('mutex-throughput', 'mutex', 1, 100),
    ('mutex-locality', 'mutex', 16, 100),
    ('rwsem-throughput-read', 'rwsem', 1, 1),
    ('rwsem-throughput-mixed', 'rwsem', 1, 20),
    ('rwsem-locality-read', 'rwsem', 16, 1),
    ('rwsem-locality-mixed', 'rwsem', 16, 20),
    ('rwlock-throughput-read', 'rwlock', 1, 1),
    ('rwlock-throughput-mixed', 'rwlock', 1, 20),
    ('rwlock-locality-read', 'rwlock', 16, 1),
    ('rwlock-locality-mixed', 'rwlock', 16, 20),
]
POLICY = dict(total_cap=1024, numa_boundary=1024, deferred_handoff=8, scan_budget=64)


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path(
        '/root/kdlock-evidence/10.176.26.71/bench/nano-cohort-20261028'))
    parser.add_argument('--audit-only', action='store_true',
                        help='Audit in the guest; retain plot inputs for later offline source-host rendering')
    args = parser.parse_args()
    base = args.base.resolve(strict=True)
    out = base.with_name(base.name + '-report')
    require(os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdlock1'
            and ROOT.is_dir(), 'Run only in the designated Linux 7 guest')
    require(not base.is_relative_to(ROOT) and not out.exists(),
            'Inputs must be external and report output must be new')
    sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
    import bench_runtime
    archive = load('nano_report_archive', ROOT / 'bench/archive_run.py')
    archive.idle(base, bench_runtime.idle)
    out.mkdir()
    (out / 'report-helper.py').write_bytes(Path(__file__).read_bytes())
    catalog = load('nano_catalog_report', ROOT / 'bench/catalog_single/report.py')
    summary = dict(schema=1, passed=False, source_commit=COMMIT,
        kernel_release=os.uname().release,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        input=str(base), repetitions_per_point=1, duration_ms=2000,
        post_work_rounds=256, workers=THREADS, backends=list(ARMS),
        provider_mutex_policy=POLICY, strict_timing_qualified=False,
        timing='exploratory; n=1; no repeat variability estimate',
        reader_execution='Every rwsem/rwlock read executes on its acquiring task',
        real_world_api_executed=False, expected_profiles=10,
        expected_measurements=630, expected_warmups=630,
        graphical_rendering=('pending_source_host' if args.audit_only else 'requested_in_guest'),
        audit_scope=('Retained receipt and frozen-oracle replay, exact JIT entry/return deltas, '
                     'all frozen source hashes, data, placement, mix, post-work, and drain. '
                     'No new workload, build or test execution.'),
        warmup_jit_scope='Warmup payload/progress/drain replay; no separate warmup JIT delta is recorded',
        helper_sha256=sha(Path(__file__)), catalog_report_sha256=sha(
            ROOT / 'bench/catalog_single/report.py'), profiles=[], errors=[])
    combined = []

    def failure(scope, error):
        summary['errors'].append(dict(scope=scope, error=str(error)))
        save(out / 'audit.json', summary)

    try:
        owner = read(base / 'owner.json')
        require(owner['boot_id'] == summary['boot_id'], 'Campaign boot differs from current guest')
        require(owner['provider_mutex_policy'] == POLICY, 'Campaign mutex policy differs')
        blocks = owner['blocks']
        require([b['profile'] for b in blocks] == [p[0] for p in PROFILES],
                'Campaign does not contain exactly the ten expected profiles')
        require(all(b.get('returncode') == 0 and b.get('completion_unconfirmed') is False
                    for b in blocks), 'Campaign has incomplete or failed blocks')
        source_manifest = read(base / 'source-sha256.json')
        summary['campaign_source_manifest_sha256'] = sha(base / 'source-sha256.json')
        summary['owner_sha256'] = sha(base / 'owner.json')
    except Exception as error:
        failure('campaign', error)
        source_manifest = None

    for original, family, lines, percent in PROFILES:
        source = base / original
        concrete = f'{family}-c{lines:02d}-w{percent:03d}'
        title = f'{family.capitalize()} c{lines:02d}, {percent}% writes, post256'
        audit = dict(workload=concrete, source_directory=original,
                     lock=family, cachelines=lines, write_percent=percent,
                     planned=0, valid_measurements=0, valid_warmups=0,
                     source_files_verified=0, session_findings=[])
        summary['profiles'].append(audit)
        try:
            manifest = read(source / 'source-sha256.json')
            require(manifest == source_manifest, 'Profile source manifest differs from campaign')
            for relative, expected_hash in manifest.items():
                require(sha(source / 'source' / relative) == expected_hash,
                        'Frozen source hash differs: ' + relative)
                audit['source_files_verified'] += 1
            plan, records = read(source / 'plan.json'), read(source / 'records.json')
            audit['planned'] = len(plan)
            require(len(plan) == len(records) == 63, 'Expected 63 plan and record rows')
            require(len({p['name'] for p in plan}) == 63
                    and len({r['name'] for r in records}) == 63, 'Duplicate session names')
            require({(p['threads'], p['arm'], p['repeat']) for p in plan}
                    == {(n, arm, 0) for n in THREADS for arm in ARMS},
                    'Grid is not exactly one round of the expected 63 unique points')
            by_name = {r['name']: r for r in records}
            require(set(by_name) == {p['name'] for p in plan}, 'Record/plan names differ')
            # All ten frozen sources have identical hashes, including oracle and peak.
            sys.path.insert(0, str(source / 'source/bench/spin_cacheline'))
            oracle = load('nano_frozen_oracle_' + concrete.replace('-', '_'),
                          source / 'source/bench/rwlock_compare/oracle.py')
            rows = catalog.receipt_rows(source, False)
            rendered = {r['session']: r for r in rows}
            for spec in plan:
                name = spec['name']
                item = dict(session=name, valid=False, warmup_valid=False)
                audit['session_findings'].append(item)
                try:
                    require((spec['lock_kind'], spec['cachelines'], spec['write_percent'],
                             spec['workload'], spec['post_work_rounds'], spec['duration_ms'],
                             spec['functional'], spec['call_shell']) ==
                            (family, lines, percent, 'cacheline', 256, 2000, False, 'bulk_ioctl'),
                            'Workload geometry differs')
                    require(spec['cpus'] == list(range(spec['threads']))
                            and spec['collector_cpu'] == 63, 'CPU placement differs')
                    if spec['arm'] == 'kdlock':
                        require(spec['provider_mutex_policy'] == POLICY and spec['delegate'] is True,
                                'KD policy/delegation selection differs')
                    record = by_name[name]
                    session = read(source / name / 'session.json')
                    require(all(record[k] == v for k, v in session.items()),
                            'Aggregated record differs from retained session')
                    require(all(record[k] == v for k, v in spec.items()),
                            'Session changed a planned parameter')
                    require(record['execution_status'] == 'OK' and record['drained'] is True
                            and not record.get('cleanup_error'), 'Session failed or did not drain')
                    m = record['measurement']
                    raw_measurement = read(source / name / 'measure.json')
                    require(set(m) == set(raw_measurement) | {'peak'} and
                            all(m[k] == v for k, v in raw_measurement.items()),
                            'Session measurement differs from raw client receipt')
                    require(m['data_ok'] is True and m['complete'] is True, 'Measurement data failed')
                    peak = oracle.validate(m, spec)
                    require(peak == m['peak'], 'Frozen peak replay differs')
                    entries, completions = record['jit_bodies'], record['jit_completions']
                    require(type(entries) is int and type(completions) is int
                            and 0 <= entries == completions <= m['writes'],
                            'JIT entries and returned bodies do not match exactly')
                    require(entries == record['jit_after'] - record['jit_before']
                            and completions == record['jit_complete_after'] - record['jit_complete_before'],
                            'JIT counter deltas differ from retained witnesses')
                    require(spec['arm'] == 'kdlock' or entries == 0, 'Control executed KD JIT')
                    selected = rendered[name]
                    require(selected['whole_mops_s'] is not None and math.isclose(
                        selected['whole_mops_s'], m['completed'] * 1e3 / m['wall_ns'],
                        rel_tol=1e-14), 'Published rate is missing or differs')
                    item.update(valid=True, execution_class=selected['jit_status'],
                                jit_entries=entries, jit_completions=completions)
                    audit['valid_measurements'] += 1
                    combined.append(dict(workload=concrete, lock=family, cachelines=lines,
                                         write_percent=percent, post_work_rounds=256, **selected))
                    warm_spec = read(source / name / 'warmup.spec.json')
                    require(warm_spec['iterations'] == 48000 and warm_spec['duration_ms'] == 0
                            and all(warm_spec[k] == v for k, v in spec.items()
                                    if k not in ('iterations', 'duration_ms')),
                            'Warmup parameters differ')
                    warmup = read(source / name / 'warmup.json')
                    require(warmup['data_ok'] is True and warmup['complete'] is True,
                            'Warmup data failed')
                    oracle.validate(warmup, warm_spec)
                    warm_counts = read(source / name / 'warmup.counts.json')
                    oracle.check_snapshot(warm_counts, warm_spec)
                    require(warm_counts == warmup['after'], 'Warmup final snapshot differs')
                    item['warmup_valid'] = True
                    audit['valid_warmups'] += 1
                except Exception as error:
                    item['error'] = str(error)
                    failure(concrete + '/' + name, error)
            audit['statuses'] = dict(Counter(r.get('execution_status', 'MISSING') for r in records))
            audit['kd_execution_classes'] = dict(Counter(
                r['jit_status'] for r in rows if r['backend'] == 'kdlock'))
            audit['plan_sha256'] = sha(source / 'plan.json')
            audit['records_sha256'] = sha(source / 'records.json')
            require(audit['valid_measurements'] == audit['valid_warmups'] == 63,
                    'Profile lacks 63 valid measurements and 63 valid warmups')
            if args.audit_only:
                plot_input = out / 'plot-input' / original
                plot_input.mkdir(parents=True)
                for name in ('plan.json', 'records.json'):
                    (plot_input / name).write_bytes((source / name).read_bytes())
                require(sha(plot_input / 'plan.json') == audit['plan_sha256'] and
                        sha(plot_input / 'records.json') == audit['records_sha256'],
                        'Copied plot inputs differ from the audited receipts')
                audit['plot_input'] = str(plot_input.relative_to(out))
            else:
                catalog.render(source, out / concrete, title, False, exploratory=True)
        except Exception as error:
            failure(concrete, error)
        save(out / 'audit.json', summary)

    summary['planned'] = sum(p['planned'] for p in summary['profiles'])
    summary['valid_measurements'] = sum(p['valid_measurements'] for p in summary['profiles'])
    summary['valid_warmups'] = sum(p['valid_warmups'] for p in summary['profiles'])
    summary['statuses'] = dict(sum((Counter(p.get('statuses', {})) for p in summary['profiles']), Counter()))
    summary['kd_execution_classes'] = dict(sum((Counter(p.get('kd_execution_classes', {}))
                                               for p in summary['profiles']), Counter()))
    if combined:
        with (out / 'combined.csv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(combined[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(combined)
    if not (summary['planned'] == summary['valid_measurements'] == summary['valid_warmups'] == 630):
        failure('totals', 'Expected exactly 630 planned, valid measurements, and valid warmups')
    try:
        archive.idle(base, bench_runtime.idle)
        summary['guest_idle_after_report'] = True
    except Exception as error:
        summary['guest_idle_after_report'] = False
        failure('final-idle', error)
    summary['passed'] = not summary['errors']
    if summary['passed'] and not args.audit_only:
        summary['graphical_rendering'] = 'completed_in_guest'
    save(out / 'audit.json', summary)
    if summary['errors']:
        (out / 'README.md').write_text('# Nano comparison: incomplete audit\n\n'
            'Audit did not pass; retained findings are in [audit.json](audit.json). '
            'Partial outputs do not qualify the complete comparison.\n')
        raise RuntimeError(f"Nano report audit failed with {len(summary['errors'])} findings; see {out}/audit.json")

    lookup = {(r['workload'], r['workers'], r['backend']): r for r in combined}
    def rates(workload, count):
        return [lookup[workload, count, arm]['whole_mops_s'] for arm in ARMS]
    def line(workload, count, label):
        native, tclock, kd = rates(workload, count)
        evidence = lookup[workload, count, 'kdlock']['jit_status']
        return (f'| {label} | {native:.3f} | {tclock:.3f} | {kd:.3f} | '
                f'{kd/native:.3f}× | {kd/tclock:.3f}× | {evidence} |')
    text = ['# Nano comparison after rwsem reader-cohort optimization: October 28, 2026', '',
        '630/630 measurements and 630/630 warmups passed the retained data, progress, '
        'placement, frozen-oracle and drain audit. Each point has exactly one two-second '
        'measurement; no real-world API cases were run.', '',
        f'Source `{COMMIT}` on Linux `7.0.0-38-kdlock1`. '
        'All bodies use c01 or c16 and post256. KD mutex uses total cap 1024 and NUMA '
        'boundary 1024. This source includes the rwsem queued-reader preference from acc4dbc2. '
        'Rwsem/rwlock reads always execute locally; only writes may delegate.', '',
        'Workers: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`, '
        'on CPU prefixes 0..N-1 with collector CPU63. Counts above 32 cross NUMA nodes. '
        'Rates include post-lock work and compare complete implementations.', '',
        '**Exploratory timing, n=1.** Strict timing qualification remains failed; '
        'there is no repeat variability estimate or significance claim. '
        'Returned-JIT and NO_JIT observations retain their execution classes. '
        'NO_JIT results cannot establish delegation gains.', '',
        'Whole-run throughput at **60 workers**, Mops/s:', '',
        '| Workload | Native | TCLock | KD | KD / Native | KD / TCLock | KD execution |',
        '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for _, family, lines, percent in PROFILES:
        concrete = f'{family}-c{lines:02d}-w{percent:03d}'
        label = f'[{family} c{lines:02d}, {percent}% writes]({concrete}/README.md)'
        text.append(line(concrete, 60, label))
    text += ['', 'Current rwsem c01, 20% writes, post256:', '',
        '| Workers | Native | TCLock | KD | KD / Native | KD / TCLock | KD execution |',
        '| ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    text.extend(line('rwsem-c01-w020', n, str(n)) for n in (8, 16, 32, 60))
    text += ['', '[All 630 measurements](combined.csv) · '
        '[Audit and execution classes](audit.json)', '',
        ('Chart rendering is pending on the source host. After rendering, each workload link '
         'provides its complete worker grid and PNG/SVG chart; the separate plot-receipt.json '
         'records rendering completion and exact input/output hashes. '
         if args.audit_only else
         'Each workload link provides its complete worker grid and PNG/SVG chart. ') +
        'The campaign source manifests and original session data remain in the separate '
        'raw evidence tree; this report does not modify them. Archive and host endpoint '
        'receipts are separate evidence and are not fabricated by this report.', '']
    (out / 'README.md').write_text('\n'.join(text))
    print(json.dumps(dict(output=str(out), passed=True, planned=630,
                          valid_measurements=630, valid_warmups=630,
                          kd_execution_classes=summary['kd_execution_classes']), sort_keys=True))


if __name__ == '__main__':
    main()
