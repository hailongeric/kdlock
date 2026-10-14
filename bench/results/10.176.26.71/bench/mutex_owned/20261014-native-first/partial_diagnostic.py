#!/usr/bin/env python3
"""Audit the retained C8 profiler preparation failure; never run a workload."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import evidence as audit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
RELATIVE_RUN = 'bench/mutex-native-first-c8-profile-lock64-20261014'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=ROOT/'bench/results/10.176.26.71/raw/bench/mutex-native-first-20261014')
    parser.add_argument('--out', type=Path, default=HERE/'partial-profile.json')
    args = parser.parse_args()
    folder = args.raw/'extracted'/RELATIVE_RUN
    plan, records = audit.read(folder/'plan.json'), audit.read(folder/'records.json')
    audit.require(len(plan) == len(records) == 36 and
                  len({row['name'] for row in plan}) == 36, 'partial plan size/identity differs')
    audit.require([row['name'] for row in plan] == [row['name'] for row in records],
                  'partial records are not in declared order')
    audit.require(Counter(row['execution_status'] for row in records) ==
                  {'OK': 1, 'PREPARATION_FAILED': 1, 'NOT_RUN': 34}, 'partial status counts differ')
    for spec, record in zip(plan, records):
        audit.require(all(record.get(key) == value for key, value in spec.items()),
                      'partial record differs from plan')
        audit.require(record['diagnostic'] and record['score_eligible'] is False and
                      record['profile_lock'] and not record['pmu'] and not record['perf_record'],
                      'partial run is not an unscored lock profile')
    frozen = audit.frozen(folder)
    audit.environment(folder)
    completed, failed = records[:2]
    audit.require(completed['arm'] == 'native' and failed['arm'] == 'kdlock' and
                  completed['threads'] == failed['threads'] == 2 and
                  completed['repeat'] == failed['repeat'] == 0, 'first pair differs')
    paths = {row['name']: folder/row['name'] for row in records[:2]}
    hashes = {}
    for row in records[:2]:
        path = paths[row['name']]
        session = audit.read(path/'session.json')
        audit.require(all(row.get(key) == value for key, value in session.items()),
                      'session/aggregate differs')
        hashes[row['name']] = {str(item.relative_to(path)): audit.digest(item)
                              for item in sorted(path.iterdir()) if item.is_file()}
    native_path = paths[completed['name']]
    audit.require(audit.valid(completed), 'completed Native sample is invalid')
    raw = audit.read(native_path/'measure.json')
    peak = audit.validate_measurement(raw, completed, completed['iterations'])
    audit.require(dict(raw, peak=peak) == completed['measurement'], 'Native raw measurement differs')
    native_log = (native_path/'kernel.log').read_text()
    audit.require(not audit.FAULT.search(native_log), 'completed Native sample contains kernel fault')
    audit.audit_backend(folder, completed, native_log, True)
    counts = audit.parse_profile(native_log, completed)
    audit.require(audit.read(native_path/'profile-drain.counts.json')['active'] == 0,
                  'Native profile workers did not drain')
    failure_path = paths[failed['name']]
    failure_log = (failure_path/'kernel.log').read_text()
    load_log = (failure_path/'load-profile.log').read_text()
    command = audit.read(failure_path/'load-profile.log.command.json')
    audit.require('command exited 1:' in failed['error'] and
                  'Cannot allocate memory' in load_log and
                  'percpu: allocation failed, size=264 align=32' in failure_log and
                  'alloc from reserved chunk failed' in failure_log and
                  'kd_mutex_profile: Could not allocate 264 bytes percpu data' in failure_log,
                  'retained failure is not the expected profiler reserved-percpu allocation')
    audit.require(command['argv'][0:4] == ['taskset', '-c', '63', 'insmod'] and
                  'kd_mutex_profile.ko' in command['argv'][4] and
                  {'kd=1', 'owned=1', 'native_first=1'} <= set(command['argv']),
                  'failed command identity differs')
    audit.require(not (failure_path/'measure.json').exists() and 'measurement' not in failed and
                  'lock_profile' not in failed and 'owned_native_first_profile' not in failed,
                  'failed preparation unexpectedly contains a timed/profile result')
    audit.require(failed['drained'] and not failed.get('cleanup_error') and
                  audit.read(failure_path/'drain.counts.json')['active'] == 0 and
                  failed['retired'] == {'state': 2, 'modules': 0, 'frames': 0, 'writers': 0} and
                  'kd_source retire: result=0 state=2 modules=0 frames=0 writers=0' in failure_log,
                  'failed preparation did not drain/retire')
    owned = audit.log_counts(failure_log, 'kd_owned_mutex:')
    audit.require(owned == failed['owned_observations'], 'warmup owned counters differ')
    for row in records[2:]:
        audit.require(row['execution_status'] == 'NOT_RUN' and 'measurement' not in row and
                      not (folder/row['name']).exists(), 'unattempted sample has execution artifacts')
    result = dict(schema=1, passed=True, diagnostic_complete=False, score_eligible=False,
        method='Offline partial-run audit; no workload, build, guest action or fixture execution',
        command=[str(Path(__file__).relative_to(ROOT)), '--raw', str(args.raw), '--out', str(args.out)],
        run=RELATIVE_RUN, planned_sessions=36, completed_native_sessions=1,
        preparation_failed_owned_sessions=1, not_run_sessions=34,
        frozen=frozen, source_script_sha256=audit.digest(Path(__file__)),
        input_sha256={name: audit.digest(folder/name) for name in ('plan.json', 'records.json', 'summary.json')},
        archive_sha256=audit.digest(args.raw/'candidate8-diagnostics-validation.tar.gz'),
        completed_native=dict(name=completed['name'], profile=counts,
                              raw_measurement_and_progress_verified=True, drained=True),
        failed_owned=dict(name=failed['name'], stage='profile module load after warmup, before timed measurement',
                          error=failed['error'], command=command, retained_kernel_allocation_warning=True,
                          timed_measurement=False, profile_outcomes_available=False,
                          warmup_and_lifetime_observations=owned, drained=True, retired=failed['retired']),
        not_run=[row['name'] for row in records[2:]], artifacts_sha256=hashes,
        limits=['No owned native-first profile was collected in this attempt.',
                'Warmup/lifetime bodies are not measured returned-JIT evidence.',
                'Allocation warning is preserved; this is not a clean completed diagnostic group.',
                'A later fixed profiler/source must be audited as a separate group.'])
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({key: result[key] for key in ('passed', 'diagnostic_complete', 'completed_native_sessions',
                                                'preparation_failed_owned_sessions', 'not_run_sessions')}))


if __name__ == '__main__':
    main()
