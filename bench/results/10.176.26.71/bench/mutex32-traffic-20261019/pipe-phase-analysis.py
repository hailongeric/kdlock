#!/usr/bin/env python3
"""Summarize this round's independently audited pipe evidence, without pooling phases."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(values):
    ordered = sorted(values)
    n = len(ordered)
    return dict(n=n, min=ordered[0] if n else None, max=ordered[-1] if n else None,
                median=(ordered[(n - 1) // 2] + ordered[n // 2]) / 2 if n else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = args.report.resolve()
    comparison = json.loads((report / 'comparison.json').read_bytes())
    audit = json.loads((report / 'statistics-review.json').read_bytes())
    profiles = json.loads((report / 'profile-analysis.json').read_bytes())
    if not audit['passed'] or audit['issues'] or not comparison['complete'] or not profiles['complete']:
        raise ValueError('require complete comparison, profiles and independent arithmetic audit')
    for filename, expected in audit['input_sha256'].items():
        if digest(report / filename) != expected:
            raise ValueError('audited report input changed: ' + filename)
    if comparison['arms'] != audit['arms']:
        raise ValueError('audit/source arm mismatch')
    grouped = defaultdict(list)
    for row in audit['pipe_phase_diagnostics']:
        if row['collection'] == 'pipe':
            grouped[row['arm'], row['threads']].append(row)
    rows, profile_rows = [], []
    for arm in comparison['arms']:
        for threads in (8, 60):
            plain = grouped[arm, threads]
            if len(plain) != 3 or {row['repeat'] for row in plain} != {0, 1, 2}:
                raise ValueError('incomplete or duplicate plain pipe cohort')
            matches = [row for row in comparison['groups'] if row['arm'] == arm and
                       row['collection'] == 'pipe' and row['threads'] == threads]
            if len(matches) != 1 or matches[0]['status'] != 'COMPLETE':
                raise ValueError('missing complete plain pipe group')
            group = matches[0]
            operations = sum(row['measured_operations'] for row in plain)
            returned = sum(row['jit_completions'] for row in comparison['sessions'] if
                           row['arm'] == arm and row['collection'] == 'pipe' and row['threads'] == threads)
            known_fast = [row['native_fast_whole_fraction'] for row in plain if row['native_fast_whole_fraction'] is not None]
            batches = stats([row['whole_bodies_per_combiner'] for row in plain])
            if batches != group['whole_session_bodies_per_combiner'] or returned / operations != group['measured_returned_jit_share']:
                raise ValueError('independent phase arithmetic differs from compact group')
            rows.append(dict(arm=arm, source_commit=group['source_commit'], threads=threads,
                measured_whole_mops=group['whole_mops'], measured_operations=operations,
                measured_returned_jit_bodies=returned, measured_returned_jit_share=returned / operations,
                whole_session_bodies_per_combiner=batches,
                whole_session_origin_acquires_per_1000_jit=stats([
                    row['whole_origin_acquires'] * 1000 / row['whole_jit_success'] for row in plain]),
                whole_session_native_fast=dict(complete=len(known_fast) == 3,
                    complete_cohort_statistics=stats(known_fast) if len(known_fast) == 3 else None,
                    known_rows_only_statistics=stats(known_fast),
                    missing=[dict(repeat=row['repeat'], cpus=row['missing_ratio_cpus']) for row in plain if row['missing_ratio_cpus']]),
                whole_session_admission_residual_by_repeat=[dict(repeat=row['repeat'],
                    after_2047_per_worker_and_busy=row['residual_after_2047_per_worker_and_busy'],
                    generation_race=(row['auxiliary_counts'] or {}).get('generation_race', 0),
                    after_2047_per_worker_busy_and_generation_race=None
                        if row['residual_after_2047_per_worker_and_busy'] is None else
                        row['residual_after_2047_per_worker_and_busy'] - (row['auxiliary_counts'] or {}).get('generation_race', 0))
                    for row in sorted(plain, key=lambda item: item['repeat'])],
                whole_session_auxiliary_counts=None if plain[0]['auxiliary_counts'] is None else {
                    key: stats([row['auxiliary_counts'][key] for row in plain])
                    for key in ('busy', 'generation_race', 'collision', 'exhausted', 'injected')},
                failure_counter_totals={key: sum(row['failure_counters'][key] for row in plain)
                                        for key in plain[0]['failure_counters']},
                session_paths=[row['session_path'] for row in sorted(plain, key=lambda item: item['repeat'])]))
            matching_profiles = [row for row in audit['profile_weight_receipts'] if row['arm'] == arm and row['threads'] == threads]
            if len(matching_profiles) != 1:
                raise ValueError('missing unique diagnostic profile')
            profile = matching_profiles[0]
            profile_rows.append(dict(arm=arm, threads=threads, profile_path=profile['profile_path'],
                parsed_samples=profile['parsed_samples'], sc_worker_samples=profile['sc_worker_samples'],
                sc_worker_period=profile['sc_worker_period'],
                measured_returned_jit_share=profile['measured_returned_jit_share'],
                plain_returned_jit_share=profile['plain_returned_jit_share'],
                profile_minus_plain_jit_percentage_points=profile['profile_minus_plain_jit_percentage_points'],
                sc_worker_focus={key: profile['focus'][key]['sc_worker'] for key in
                    ('aux_try_ref', 'aux_acquire', 'aux_put', 'aux_all', 'hint_retry_helpers', 'mutex_slowpath', 'mutex_execute_cs')}))
    lookup = {(row['arm'], row['threads']): row for row in rows}
    for row in rows:
        row['observed_median_rate_change_pct'] = {}
        for reference in ('baseline', 'old256'):
            if (reference, row['threads']) in lookup:
                denominator = lookup[reference, row['threads']]['measured_whole_mops']['median']
                row['observed_median_rate_change_pct'][reference] = 100 * (row['measured_whole_mops']['median'] / denominator - 1)
    output = dict(schema=1, arms=comparison['arms'], plain_pipe_groups=rows, diagnostic_profiles=profile_rows,
        input_sha256={filename: digest(report / filename) for filename in
                      ('comparison.json', 'statistics-review.json', 'profile-analysis.json')},
        script_sha256=digest(Path(__file__)),
        limits=['This is the fresh traffic round only; no prior-round measurements are pooled.',
                'Three sequential plain repeats provide observed medians/ranges, not confidence intervals or isolated hardware effects.',
                'Measured returned JIT shares pool only measured operations within one plain cohort; whole-session counters additionally contain warmup and checks.',
                'Bodies per combiner is an aggregate ratio, not a batch-size distribution. Native-fast counts use approximate admission diagnostics, not ownership records.',
                'Missing suppressed CPU ratio rows leave full-cohort native-fast and admission residuals unknown. Known-only rows are separately labelled.',
                'Profiles have one repeat per configuration and are unscored. Their execution mix can differ substantially from the corresponding plain cohort.',
                'Flat weighted samples cannot count CAS retries or memory coherence transactions. Inlining and code-scope changes affect symbol attribution.',
                'No claim of universal improvement or complete recovery of the old256 performance gap follows from this table.'])
    (report / 'pipe-phase-analysis.json').write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + '\n')
    text = ['Fresh traffic-round pipe evidence. Plain timing and measured return counters are separate from whole-session diagnostics and instrumented profiles.', '',
        '| Arm | Workers | Plain Mops/s median [min, max] | Change vs baseline | Change vs old256 | Measured returned JIT | Whole-session bodies/combiner median | Whole-session native-fast median |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in rows:
        rate = row['measured_whole_mops']
        fast = row['whole_session_native_fast']['complete_cohort_statistics']
        fast_text = f"{100 * fast['median']:.2f}%" if fast else 'unknown (missing CPU rows)'
        change = row['observed_median_rate_change_pct']
        text.append(f"| {row['arm']} | {row['threads']} | {rate['median']:.3f} [{rate['min']:.3f}, {rate['max']:.3f}] | "
                    f"{change['baseline']:+.2f}% | {change['old256']:+.2f}% | {100 * row['measured_returned_jit_share']:.2f}% | "
                    f"{row['whole_session_bodies_per_combiner']['median']:.2f} | {fast_text} |")
    text.extend(['', 'The profile fractions and symbol costs describe the instrumented sessions below; they do not replace the plain results.', '',
        '| Arm | Workers | Profile returned JIT | Plain returned JIT | Ref acquire % | Ref put % | Hint/retry family % | Worker samples |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for row in profile_rows:
        focus = row['sc_worker_focus']
        text.append(f"| {row['arm']} | {row['threads']} | {100 * row['measured_returned_jit_share']:.2f}% | "
                    f"{100 * row['plain_returned_jit_share']:.2f}% | {focus['aux_acquire']['percent_of_denominator']:.2f} | "
                    f"{focus['aux_put']['percent_of_denominator']:.2f} | {focus['hint_retry_helpers']['percent_of_denominator']:.2f} | {row['sc_worker_samples']} |")
    text.extend(['', 'Limits:', '', *('- ' + line for line in output['limits'])])
    (report / 'pipe-phase-analysis.md').write_text('\n'.join(text) + '\n')
    print(json.dumps(dict(plain_pipe_groups=len(rows), profiles=len(profile_rows), output=str(report / 'pipe-phase-analysis.json'))))


if __name__ == '__main__':
    main()
