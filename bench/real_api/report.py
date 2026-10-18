#!/usr/bin/env python3
"""Export all raw syscall results, including failures and NO_JIT outcomes."""
import argparse
import csv
import json
from pathlib import Path
import statistics

PARAMETER_UNITS = {'xattr': 'attributes', 'ofd': 'ranges', 'setfd': 'FD stride',
                   'pipebytes': 'pipe buffers', 'pipecap': 'pipe capacity in pages',
                   'seek': 'file size in pages', 'utsname': 'write percent'}
IDENTITY_FIELDS = ('source_identity', 'kernel_identity', 'topology_identity',
                   'cpus', 'cpu_nodes', 'collector_cpu', 'duration_ms',
                   'peak_window_ms', 'peak_settle_ms', 'sample_ms',
                   'warmup', 'warmup_ms', 'helper_waves', 'helper_cpus', 'file_descriptions',
                   'jit_evidence_version', 'jit_completion_probe',
                   'entry_abi', 'caller_abi', 'mutex_implementation',
                   'mutex_wait_mode', 'mutex_spin_limit', 'owned_mutex_reuse_spins',
                   'owned_mutex_adaptive', 'owned_mutex_object_bytes',
                   'owned_mutex_origin_spin', 'owned_mutex_numa',
                   'diagnostic', 'pmu', 'perf_record')


def comparison_identity(record):
    # Missing historical identities stay unknown; never infer the current
    # protocol for an old record, even when its workload name is unchanged.
    return {field: record.get(field, 'unrecorded') for field in IDENTITY_FIELDS}


def execution_group(record):
    if record['arm'] != 'kdlock':
        return 'NOT_APPLICABLE'
    if record.get('jit_evidence_version', 1) < 2:
        return 'LEGACY_ENTRY_ONLY'
    if 'jit_completions' not in record:
        return 'UNMEASURED'
    entries, completed = record['jit_bodies'], record['jit_completions']
    if not 0 <= completed <= entries:
        raise ValueError('invalid JIT entry/completion evidence')
    return 'PASS' if completed else 'PARTIAL_JIT' if entries else 'NO_JIT'


def summarize(records):
    groups = {}
    for r in records:
        key = tuple(r[k] for k in ('kind', 'query', 'entries', 'value_size', 'threads', 'arm')) + (
            json.dumps(comparison_identity(r), sort_keys=True), execution_group(r))
        groups.setdefault(key, []).append(r)
    rows = []
    for key, runs in sorted(groups.items()):
        good = [r for r in runs if r['execution_status'] == 'OK' and r.get('drained') and
                not any(r.get(field, False) for field in ('diagnostic', 'pmu', 'perf_record'))]
        row = dict(zip(('kind', 'query', 'entries', 'value_size', 'threads', 'arm'), key[:6]))
        row['identity'] = json.loads(key[6])
        row['execution_group'] = key[7]
        row.update(planned=len(runs), accepted=len(good),
                   diagnostics=sum(any(r.get(field, False) for field in
                                       ('diagnostic', 'pmu', 'perf_record')) for r in runs),
                   failed=sum(r['execution_status'] != 'NOT_RUN' and
                              (r['execution_status'] != 'OK' or not r.get('drained')) for r in runs),
                   not_run=sum(r['execution_status'] == 'NOT_RUN' for r in runs),
                   jit_positive=sum(r.get('jit_bodies', 0) > 0 for r in good),
                   jit_bodies=sum(r.get('jit_bodies', 0) for r in good))
        complete_known = bool(good) and all('jit_completions' in r for r in good)
        row['jit_complete_positive'] = (sum(r['jit_completions'] > 0 for r in good)
                                        if complete_known else None)
        row['jit_completions'] = (sum(r['jit_completions'] for r in good)
                                  if complete_known else None)
        row['parameter_unit'] = PARAMETER_UNITS[row['kind']]
        row['jit_eligible_operations'] = sum(
            r['measurement'].get('writes', 0) if r['kind'] == 'utsname' else r['measurement']['completed']
            for r in good)
        row['jit_share'] = (row['jit_bodies']/row['jit_eligible_operations']
                            if row['jit_eligible_operations'] else 0)
        row['jit_complete_share'] = (row['jit_completions']/row['jit_eligible_operations']
                                    if complete_known and row['jit_eligible_operations']
                                    else 0 if complete_known else None)
        delegated = [r['tclock_delegation'] for r in good if isinstance(r.get('tclock_delegation'), int)]
        row['tclock_delegated'] = sum(delegated) if len(delegated) == len(good) and good else None
        for metric in ('whole', 'peak'):
            values = [r[f'{metric}_throughput_ops_s'] for r in good]
            row[f'{metric}_min'] = min(values) if values else None
            row[f'{metric}_median'] = statistics.median(values) if values else None
            row[f'{metric}_max'] = max(values) if values else None
            row[f'{metric}_spread_pct'] = (100*(max(values)-min(values))/statistics.median(values)) if values else None
        row['worker_min_share'] = min((min(w['completed'] for w in r['measurement']['workers']) /
                                      r['measurement']['completed'] for r in good), default=None)
        row['worker_max_share'] = max((max(w['completed'] for w in r['measurement']['workers']) /
                                      r['measurement']['completed'] for r in good), default=None)
        row['cpu_ns_per_op_median'] = statistics.median([
            sum(w['cpu_ns'] for w in r['measurement']['workers'])/r['measurement']['completed']
            for r in good]) if good else None
        rows.append(row)
    return rows


def write_report(out, records):
    rows = summarize(records)
    # The compact comparison table has one column per backend. Fail before
    # writing it if that column would hide a source/protocol/placement change.
    seen = {}
    for row in rows:
        key = tuple(row[k] for k in ('kind', 'query', 'entries', 'value_size', 'threads', 'arm'))
        if key in seen and seen[key] != row['identity']:
            raise ValueError('cannot compare distinct source/protocol/placement identities in one report')
        seen[key] = row['identity']
    for field in ('source_identity', 'kernel_identity', 'topology_identity'):
        if len({json.dumps(row['identity'][field], sort_keys=True) for row in rows}) > 1:
            raise ValueError('cannot compare distinct ' + field + ' values in one report')
    protocols = {}
    for row in rows:
        key = (row['kind'], row['arm'])
        protocol = tuple(json.dumps(row['identity'][field], sort_keys=True) for field in
                         ('entry_abi', 'caller_abi', 'mutex_implementation',
                          'mutex_wait_mode', 'mutex_spin_limit', 'owned_mutex_reuse_spins',
                          'owned_mutex_adaptive', 'owned_mutex_object_bytes',
                          'owned_mutex_origin_spin', 'owned_mutex_numa',
                          'jit_evidence_version', 'jit_completion_probe',
                          'diagnostic', 'pmu', 'perf_record'))
        if key in protocols and protocols[key] != protocol:
            raise ValueError('cannot compare distinct protocol/instrumentation identities across cohorts')
        protocols[key] = protocol
    matched = {}
    for row in rows:
        key = tuple(row[k] for k in ('kind', 'query', 'entries', 'value_size', 'threads'))
        identity = row['identity']
        geometry = tuple(json.dumps(identity[field], sort_keys=True) for field in
                         ('cpus', 'cpu_nodes', 'collector_cpu', 'duration_ms',
                          'peak_window_ms', 'peak_settle_ms', 'sample_ms',
                          'warmup', 'warmup_ms', 'helper_waves', 'helper_cpus'))
        if key in matched and matched[key] != geometry:
            raise ValueError('cannot compare different worker/timing identities across backends')
        matched[key] = geometry
    out.mkdir(parents=True, exist_ok=True)
    (out/'summary.json').write_text(json.dumps(rows, indent=2)+'\n')
    if rows:
        with (out/'summary.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
    configs = {}
    for row in rows:
        key = tuple(row[k] for k in ('kind', 'query', 'entries', 'value_size', 'threads'))
        configs.setdefault(key, {}).setdefault(row['arm'], []).append(row)
    text = ['# Real syscall lock comparison', '',
            'Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. '
            'Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. '
            'Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; '
            'setfd changes preallocated flags, seek changes the shared file position, and UTS mixes '
            'uname reads with fixed-length name updates in a private namespace. '
            'These are API microbenchmarks, not whole-application measurements.', '',
            f'Accepted and drained: {sum(r["accepted"] for r in rows)}/{len(records)} sessions. '
            f'Failed: {sum(r["failed"] for r in rows)}; not run: {sum(r["not_run"] for r in rows)}; '
            f'unscored diagnostics: {sum(r["diagnostics"] for r in rows)}.', '',
            'Whole-run columns are medians across rounds, in million operations/second. '
            'Peak ratios use the best valid 300 ms window from each backend. '
            'A speedup above 1 favors KD. Raw exports retain min/median/max/spread. '
            'KD execution groups remain separate: PASS has returned bodies, PARTIAL_JIT has entries '
            'but no returned body, NO_JIT has no entries, and UNMEASURED has no measured completion evidence. '
            'LEGACY_ENTRY_ONLY retains historical entry-count records without inferring returned bodies. '
            'An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. '
            'Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. '
            'Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers '
            'for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. '
            'Matched UTS arms use private locks: a Linux rwsem for Native, reader/writer spinlocks for KD/TCLock. '
            'They move proc notification after unlock; stock keeps the global rwsem and original placement.', '',
            '| API/query | Entries/stride/write % | Threads | KD execution | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD returned-body runs |',
            '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for key, groups in sorted(configs.items()):
        kind, query, count, size, n = key
        for kd in groups.get('kdlock', [{}]):
            arms = {arm: values[0] for arm, values in groups.items() if arm != 'kdlock'}
            arms['kdlock'] = kd
            def val(arm, metric):
                return arms.get(arm, {}).get(metric)
            def rate(arm):
                v = val(arm, 'whole_median')
                return f'{v/1e6:.3f}' if v else '—'
            def ratio(arm, metric):
                kd_value, other = val('kdlock', metric), val(arm, metric)
                return f'{kd_value/other:.2f}×' if kd_value and other else '—'
            complete = kd.get('jit_complete_positive')
            evidence = f'{complete}/{kd["accepted"]}' if complete is not None else 'unrecorded'
            text.append(f'| {kind}/{query} | {count} | {n} | {kd.get("execution_group", "—")} | '
                        f'{rate("stock")} | {rate("native")} | {rate("tclock")} | {rate("kdlock")} | '
                        f'{ratio("native", "whole_median")} | {ratio("tclock", "whole_median")} | '
                        f'{ratio("native", "peak_max")} | {ratio("tclock", "peak_max")} | {evidence} |')
    text += ['', 'TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. '
             'Entry counts and returned-body counts cover the measured phase; UTS shares use writes as the denominator. '
             'Historical records lacking the completion probe keep returned-body counts unrecorded. '
             'A published translation alone is not a JIT execution. Throughput is not acquisition latency. '
             'The CPU-time export helps distinguish throughput gains from processor cost.', '']
    (out/'README.md').write_text('\n'.join(text))
    return rows


def plot(out, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    groups = sorted({(r['kind'], r['query'], r['entries'], r['value_size']) for r in rows})
    for kind, query, count, size in groups:
        fig, ax = plt.subplots(figsize=(7, 4.3))
        for arm, color in (('stock', '#888888'), ('native', '#2762ad'), ('tclock', '#e49524'), ('kdlock', '#b62837')):
            matched = [r for r in rows if (r['kind'], r['query'], r['entries'], r['value_size'], r['arm']) ==
                       (kind, query, count, size, arm) and r['accepted']]
            for group in sorted({r['execution_group'] for r in matched}):
                rs = sorted((r for r in matched if r['execution_group'] == group), key=lambda r: r['threads'])
                xs = [r['threads'] for r in rs]
                label = f'{arm} ({group})' if arm == 'kdlock' else arm
                style = 'o-' if group in ('PASS', 'NOT_APPLICABLE', 'LEGACY_ENTRY_ONLY') else 'x--'
                ax.plot(xs, [r['whole_median']/1e6 for r in rs], style, label=label, color=color)
                ax.fill_between(xs, [r['whole_min']/1e6 for r in rs], [r['whole_max']/1e6 for r in rs], color=color, alpha=.15)
        unit = PARAMETER_UNITS[kind]
        ax.set(xlabel='Pinned worker threads', ylabel='Million operations/second',
               title=f'{kind} {query}: {count} {unit}, median and round range')
        ax.grid(alpha=.2)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out/f'{kind}-{query}-{count}-{size}.png', dpi=180)
        svg = out/f'{kind}-{query}-{count}-{size}.svg'
        fig.savefig(svg)
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
        plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plots', action='store_true')
    args = parser.parse_args()
    records = json.loads((args.run/'records.json').read_text())
    output = args.output or args.run/'report'
    rows = write_report(output, records)
    if args.plots:
        plot(output, rows)
