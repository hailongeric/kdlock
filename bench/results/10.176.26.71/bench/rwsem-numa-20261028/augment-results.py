"""Add reproducible comparisons and a read-only Git binding to extracted JSON."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

COMMIT = 'acc4dbc2e28394522992469250a31da536c39fa7'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repo', type=Path,
                        default=Path('/home/eric/vm/vm-shared/kdlock'))
    args = parser.parse_args()
    result = json.loads(args.input.read_text())
    profile = result['profile_cohort']
    assert profile['result']['source_commit'] is None
    manifest = profile['source_identity']['files']
    requests = ''.join(COMMIT + ':' + name + '\n' for name in manifest).encode()
    raw = subprocess.check_output(['git', 'cat-file', '--batch'],
                                  input=requests, cwd=args.repo, timeout=30)
    position = 0
    mismatches = []
    for name, expected in manifest.items():
        end = raw.index(b'\n', position)
        header = raw[position:end].decode().split()
        position = end + 1
        assert len(header) == 3 and header[1] == 'blob', (name, header)
        size = int(header[2])
        actual = hashlib.sha256(raw[position:position + size]).hexdigest()
        position += size + 1
        if actual != expected:
            mismatches.append(dict(path=name, expected=expected, git_sha256=actual))
    assert position == len(raw) and not mismatches, mismatches
    profile['source_host_commit_binding'] = dict(
        commit=COMMIT,
        method='Read-only git cat-file --batch over every frozen source manifest path; '
               'SHA256 equals the profile and cohort/compact manifests.',
        matched_files=len(manifest), mismatches=mismatches,
        original_result_source_commit_preserved=None)

    phases = {phase['phase']: phase for phase in result['phases']}

    def grid(phase, variant):
        return {(row['cachelines'], row['write_percent'], row['threads'], row['backend']): row
                for block in phases[phase]['variants'] if block['name'] == variant
                for row in block['points']}

    comparisons = []
    for variant in ('compact', 'split32'):
        baseline, cohort = grid('baseline', variant), grid('cohort', variant)
        for key, row in cohort.items():
            if key[-1] != 'kdlock':
                continue
            old = baseline[key]
            tc = cohort[(*key[:-1], 'tclock')]
            old_tc = baseline[(*key[:-1], 'tclock')]
            comparisons.append(dict(
                variant=variant, cachelines=key[0], write_percent=key[1], threads=key[2],
                baseline_kd_mops_s=old['mops_s'], cohort_kd_mops_s=row['mops_s'],
                kd_change_percent=100 * (row['mops_s'] / old['mops_s'] - 1),
                baseline_tclock_mops_s=old_tc['mops_s'], cohort_tclock_mops_s=tc['mops_s'],
                tclock_drift_percent=100 * (tc['mops_s'] / old_tc['mops_s'] - 1),
                cohort_kd_vs_tclock_percent=100 * (row['mops_s'] / tc['mops_s'] - 1),
                baseline_execution=old['execution_class'], cohort_execution=row['execution_class'],
                baseline_returned_share=old['returned_body_share_of_writes'],
                cohort_returned_share=row['returned_body_share_of_writes']))
    result['cohort_vs_baseline'] = comparisons

    def metrics(row):
        settled = row['profile']['settled_rb_worker']

        def percent(symbol):
            return sum(f['period_percent'] for f in settled['functions'] if f['symbol'] == symbol)

        return dict(
            settled_samples=settled['samples'], osq_percent=percent('kd_mutex_osq_lock'),
            vcpu_preempt_query_percent=percent('__raw_callee_save___kvm_vcpu_is_preempted'),
            read_entry_percent=percent('kd_down_read'),
            writer_phase_enter_percent=percent('kd_rwsem_delegate_enter'),
            mutex_lock_slowpath_percent=percent('__kd_mutex_lock_slowpath'),
            writer_phase_exit_percent=percent('kd_rwsem_delegate_exit'),
            named_combiner_percent=percent('kd_mutex_run_combiner'),
            named_execute_percent=percent('kd_mutex_execute_cs'),
            unresolved_percent=percent('[unknown]'), instrumented_mops_s=row['mops_s'],
            returned_writer_share=row['returned_body_share_of_writes'])

    result['kd_profile_comparison'] = []
    for workers in (32, 60):
        selected = [next(row for row in result[name]['points']
                         if row['backend'] == 'kdlock' and row['threads'] == workers)
                    for name in ('profile_baseline', 'profile_cohort')]
        result['kd_profile_comparison'].append(dict(
            workers=workers, baseline=metrics(selected[0]), cohort=metrics(selected[1])))
    caveat = ('Named combiner/execute symbol shares are not total JIT overhead. '
              'Unresolved samples are retained separately and are not assumed to be generated bodies.')
    if caveat not in result['caveats']:
        result['caveats'].append(caveat)
    if result.get('causal_notes'):
        result['causal_notes'][0] = (
            'The same 32 workers and payload run changes placement from CPUs 0–31 to '
            '0–15 plus 32–47. This isolates worker placement from worker count, but remains '
            'one observation per placement and preserves any JIT-class difference.')
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
