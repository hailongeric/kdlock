#!/usr/bin/env python3
"""Inert boundary-diagnostic archive, prerequisite and causal-record integrity review."""
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import sys
import tarfile
from types import SimpleNamespace

ROOT = Path('/home/eric/vm/vm-shared/kdlock')
HERE = Path(__file__).resolve().parent
RAW = HERE.parents[1]/'raw/bench'
CONTROL = RAW/HERE.name
OLD = RAW/'pipecap-unlock-20261021/archives-1'
NEW = CONTROL/'archives-1'
HASH = 'c01910453dd0183e30e6e167fb5f7359df200a655958a6174658e55fb5184812'


def main():
    sys.dont_write_bytecode = True
    path = ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
    spec = importlib.util.spec_from_file_location('worker_inert_reader', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    roots = {}
    for folder, digest in ((RAW/'mutex-public-20261020-r2', '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'),
                           (OLD, 'c665228f06d3c5cd6ba85fb62c4e7609d4f1cc4a4d8ac58d26c439d333317c10'), (NEW, HASH)):
        assert helper.hashfile(folder/'archives.json') == digest
        manifest = json.loads((folder/'archives.json').read_text())
        assert helper.hashfile(folder/'input-inventory.json') == manifest['input_inventory_sha256']
        roots[manifest['guest_base']] = json.loads((folder/'input-inventory.json').read_text())
        if folder == OLD:
            for group in manifest['groups']:
                assert helper.hashfile(folder/group['file']) == group['sha256']

    class Audit(helper.Audit):
        def retained(self, target):
            seen = set()
            for _ in range(32):
                target = posixpath.normpath(target)
                if target in seen:
                    return False
                seen.add(target)
                root = next((r for r in roots if target == r or target.startswith(r+'/')), None)
                if root is None:
                    return False
                parts = target[len(root):].lstrip('/').split('/')
                if parts == ['']:
                    return True
                for n in range(1, len(parts)+1):
                    name = '/'.join(parts[:n])
                    item = roots[root].get(name)
                    if item is None:
                        return False
                    if item.get('link') is not None:
                        link = item['link']
                        target = link if link.startswith('/') else posixpath.join(root, posixpath.dirname(name), link)
                        if n < len(parts):
                            target = posixpath.join(target, *parts[n:])
                        break
                else:
                    return True
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.retained(detail['target'])
            return super().check(value, label, detail)

    a = Audit(SimpleNamespace(repo=ROOT, raw=NEW, report=HERE))
    groups, _ = a.load_archives()
    check, read = a.check, a.jread
    result, health = read('probe-1/result.json'), read('final-health.json')
    check(result['diagnostic_completed'] and result['final_idle'] and
          result['planned'] == result['completed'] == 1 and result['passed'] and
          not result['accepted'] and health['idle'], 'completed_drained_boundary_pass')
    for path in ('runner.py', 'boundary_protocol.py'):
        original = 'unlock_run.py' if path == 'runner.py' else path
        check(a.files['probe-1/'+path] == helper.sha(a.git_bytes(result['source_commit'],
              'bench/mutex_api_compare/'+original)), 'guest_driver_git_binding', path)
    for retained, group, original in [('inputs', 'inputs', 'inputs-1/inputs.json'),
                                     ('correctness', 'live', 'correctness-1/result.json'),
                                     ('unit-checks', 'checks', 'checks-1/result.json'),
                                     ('task-check', 'live', 'task-2/result.json'),
                                     ('elf-checks', 'metadata', 'elf-checks-2.json')]:
        with tarfile.open(OLD/(group+'.tar.gz')) as archive:
            data = archive.extractfile('pipecap-unlock-20261021/'+original).read()
        check(a.files['probe-1/'+retained+'.json'] == helper.sha(data), 'exact_prerequisite_binding', retained)
    unit = read('checks-1/result.json')
    check(unit['passed'] and unit['final_idle'] and unit['source_unchanged'] and
          [(r['name'], r['exit_code']) for r in unit['commands']] ==
          [('basic', 0), ('boundary-trigger', 0), ('boundary-protocol', 0), ('recovery-gate', 0)], 'serial_basic_affected_pass')
    for relative, digest in read('checks-1/sources.json').items():
        check(a.files['checks-1/source/'+relative] == digest ==
              helper.sha(a.git_bytes(unit['source_revision'], relative)), 'tested_source_git_binding', relative)
    for name, expected in [('basic', b'Unit tests: 2 passed, 0 failed'),
                           ('boundary-trigger', b'Ran 9 tests'), ('boundary-protocol', b'Ran 4 tests'), ('recovery-gate', b'Ran 6 tests')]:
        check(expected in a.contents['checks-1/'+name+'.log'], 'actual_test_log', name)
    row, = result['records']
    prefix = 'probe-1/outer/'+row['name']+'/'
    check(read(prefix+'session.json') == row, 'session_binding')
    check(row['execution_status'] == 'OK' and row['drained'] and
          row['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'exact_retirement')
    kernel_lines = a.contents[prefix+'kernel.log'].decode().splitlines()
    owner_line, = [line for line in kernel_lines if 'kd_mutex stats:' in line]
    task_line, = [line for line in kernel_lines if 'kd_mutex tasks:' in line]
    check(all(value in owner_line for value in ('origin_acquires=57525', 'origin_releases=57525',
          'active_waiters=0', 'reserved_nodes=0')) and 'active_tasks=0' in task_line, 'exact_origin_balance_and_resource_drain')
    warm = row['boundary_warmup']
    check(warm == read(prefix+'warmup.json') and warm['ok'] and len(warm['workers']) == 5 and
          warm['completed'] == sum(w['completed'] for w in warm['workers']) == 8375936 and
          all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] >= 48000
              and w['finished_ns'] >= warm['started_ns']+1000000000 for w in warm['workers']), 'joined_original_warmup')
    check(warm['collector_cpu'] == warm['collector_observed_cpu'] == 63 and warm['collector_error'] == 0
          and [w['cpu'] for w in warm['workers']] == list(range(5)), 'worker_collector_placement')
    check(row['duration_ms'] == 2000 and row['warmup'] == 48000 and row['warmup_ms'] == 1000 and
          row['peak_settle_ms'] == row['peak_window_ms'] == 300 and row['sample_ms'] == 10 and
          row['collector_cpu'] == 63 and row['cpus'] == list(range(5)) and row['entries'] == 16 and
          row['actual_lock_cacheline_offset'] == row['lock_addr'] % 64 == 32, 'original_settings')
    check(row['measurement_skipped'] and not any(k in row for k in
          ('measurement', 'whole_throughput_ops_s', 'peak_throughput_ops_s')) and
          prefix+'measure.json' not in a.files, 'no_measurement_or_rates')
    check(read(prefix+'check-before.json')['check'] and read(prefix+'check-after-boundary.json')['check'], 'business_oracles')
    boundary = row['boundary']
    check(boundary['before'] == boundary['after'] and boundary['before']['physical_idle'] and
          boundary['before']['publication'] == row['published_before'] and
          boundary['before']['publication']['source'] == dict(state=0, modules=1, frames=0, writers=0), 'held_state_identical')
    check(boundary['before']['counters'] == dict(address_guard_count=0, bench_jit_bodies=7903,
          bench_jit_completions=7903), 'exact_cumulative_drained_counters')
    check(boundary['gate']['passed'] and boundary['gate']['comparison']['configuration_matches']
          and health['boundary_gate_passed'] and not health['measurement_sent'] and
          not health['per_session_kernel_faults'] and health['original_inputs_unchanged'], 'combined_gate_and_final_health')
    state = json.loads((CONTROL/'probe-1/supervisor.json').read_text())
    check(state['complete'] and not state['accepted'] and not state['score_eligible'] and not state['timing_sent']
          and len(state['streams']) == 2 and all(s['exit_code'] == 0 for s in state['streams']), 'supervisor_completed_no_timing')
    for run in ('probe-1',):
        supervisor = json.loads((CONTROL/run/'supervisor.json').read_text())
        for filename, digest in supervisor['sources'].items():
            relative = str(Path(filename).relative_to(ROOT))
            check(helper.hashfile(CONTROL/run/Path(filename).name) == digest ==
                  helper.sha(a.git_bytes(supervisor['source_commit'], relative)), 'supervisor_source_git_binding', [run, relative])
    phases = state['phases']
    check([p['guest_event']['remote']['sequence'] for p in phases] == list(range(1, len(phases)+1)), 'complete_phase_sequence')
    stack = []
    for phase in phases:
        event = phase['guest_event']['remote']
        check(event['label'] != 'client-measure', 'no_measure_command_phase')
        check(phase['guest_event']['received']['mono_ns'] <= phase['host_ack']['sent']['mono_ns'] <=
              phase['host_ack']['ack']['received']['mono_ns'] <= phase['guest_ack_sent']['mono_ns'], 'phase_causal_order')
        if event['edge'] == 'begin':
            stack.append(event['label'])
        else:
            check(bool(stack) and stack.pop() == event['label'], 'phase_pair')
    check(not stack, 'all_phase_pairs_closed')
    request = state['boundary']['request']['remote']
    observations = state['boundary']['observations']
    check(observations == boundary['observations'] and len(observations) == 1, 'guest_host_observation_binding')
    captures = {r['value']: r for r in state['requests'] if r['key'] == 'capture'}
    counts = []
    for index, observation in enumerate(observations):
        name = 'boundary-'+request['boundary_token']+'-'+str(index)
        reply = captures[name]
        remote = reply['ack']['remote']
        host = remote['host']
        counts.append(len(host['qemu'][0]['tasks']))
        check(name == observation['capture'] and observation['host_sha256'] ==
              helper.sha(json.dumps(host, sort_keys=True).encode()) and host == json.loads((CONTROL/'probe-1'/(name+'.json')).read_text()),
              'capture_nonce_hash_binding')
        check(state['boundary']['request']['received']['mono_ns'] <= reply['sent']['mono_ns'] <=
              reply['ack']['received']['mono_ns'] <= state['boundary']['reply_sent']['mono_ns'] and
              observation['boundary_marker_ns'] <= remote['capture_began']['mono_ns'] <= remote['capture_finished']['mono_ns'],
              'capture_causal_order')
    check(counts == [67] and boundary['host'] == remote['host'], 'selected_full_gate_pass')
    check(state['captures'][-1]['label'] == 'endpoint' and not state['captures'][-1]['host_gate']['passed'], 'immediate_endpoint_refused')
    trace = [json.loads(line)['remote'] for line in (CONTROL/'probe-1/observer.jsonl').read_text().splitlines()]
    samples = [r for r in trace if r['event'] == 'sample']
    marker = next(r for r in trace if r['event'] == 'marker' and r['marker'].startswith('held-boundary'))
    idle_samples = [r for r in samples if r['phase'].startswith('held-boundary') and len(r['tasks']) == 67]
    trigger = observations[0]['trigger']
    chosen, = [sample for sample in samples if sample['sequence'] == trigger['sequence']]
    check(trigger['kind'] == 'sample' and trigger['candidate'] and trigger['reason'] is None and
          trigger['sample_sha256'] == helper.sha(json.dumps(chosen, sort_keys=True).encode()), 'exact_trigger_sample_binding')
    anchor = state['trigger_anchor']
    anchored, = [sample for sample in samples if sample['sequence'] == anchor['sample_sequence']]
    original = json.loads((CONTROL/'probe-1/original-host-state.json').read_text())
    original_tasks = sorted(original['qemu'][0]['tasks'], key=lambda t: t['tid'])
    check(anchor['sample_sha256'] == helper.sha(json.dumps(anchored, sort_keys=True).encode()) and
          anchor['tasks'] == original_tasks and len(anchor['identities']) == 67, 'original_lifetime_anchor')
    check(all(t['complete'] and t['identity_matches'] and t['identity_before'] == t['identity_after'] for t in chosen['tasks']) and
          sorted(t['identity_before'] for t in chosen['tasks']) == anchor['identities'] and
          sorted((dict(tid=t['tid'], comm=t['comm'], affinity=t['affinity']) for t in chosen['tasks']), key=lambda t: t['tid']) == original_tasks,
          'complete_exact_trigger_task_set')
    freshness = observations[0]['trigger_freshness']
    check(chosen['scan_began']['mono_ns'] >= marker['mono_ns'] and
          0 <= trigger['decision_ns']-trigger['received_ns'] <= 2000000000 and
          trigger['decision_ns'] <= observations[0]['request_sent_ns'] and
          observations[0]['capture_began_ns']-chosen['scan_began']['mono_ns'] == freshness['sample_to_capture_ns'] == 25431021 and
          freshness['qualified'] and freshness['dispatch_before_cutoff'] and observations[0]['offset_s'] < 95, 'prompt_causal_capture')
    decisions = state['boundary']['sample_decisions']
    check(len(decisions) == 17 and [d['sequence'] for d in decisions] == list(range(5, 22)) and
          all(not d['candidate'] and d['reason'] == 'original exact task set, placement or lifetime differs' for d in decisions[:-1]) and
          decisions[-1]['candidate'] and decisions[-1]['sequence'] == chosen['sequence'] and not state['boundary']['dispatch_skips'],
          'all_candidate_refusals_retained')
    for decision in decisions:
        sample, = [sample for sample in samples if sample['sequence'] == decision['sequence']]
        check(decision['sample_sha256'] == helper.sha(json.dumps(sample, sort_keys=True).encode()), 'decision_sample_hash')
    check(len(json.loads((CONTROL/'probe-1/preflight-0.json').read_text())['qemu'][0]['tasks']) == 69 and
          len(json.loads((CONTROL/'probe-1/preflight-1.json').read_text())['qemu'][0]['tasks']) == 67 and
          not state['captures'][0]['host_gate']['passed'] and state['captures'][1]['host_gate']['passed'], 'preflight_refusal_then_full_pass')
    check(len(samples[-1]['tasks']) == 67 and len(json.loads((CONTROL/'probe-1/endpoint.json').read_text())['qemu'][0]['tasks']) == 70,
          'accounting_and_full_endpoint_distinct')
    observer = json.loads((CONTROL/'observer-review-3.json').read_text())[0]
    check(observer['complete'] and observer['original_67_unchanged'] and not observer['incomplete_rows'], 'observer_accounting_integrity')
    raw_hashes = {str(p.relative_to(CONTROL)): helper.hashfile(p) for p in sorted(CONTROL.rglob('*')) if p.is_file()}
    review = dict(integrity_passed=not a.issues, accepted=False, checks=sum(a.counts.values()), issues=a.issues,
        check_counts=dict(a.counts), archive_manifest_sha256=HASH, archives=groups, raw_sha256=raw_hashes,
        phase_events=len(phases), trigger_freshness=freshness, sample_decisions=len(decisions), warmup_operations=warm['completed'], cumulative_pre_hold_counters=boundary['before']['counters'],
        hold_ns=boundary['finished_ns']-boundary['began_ns'], full_capture_tasks=counts,
        sample_67_window_seconds=[(idle_samples[0]['scan_began']['mono_ns']-marker['mono_ns'])/1e9,
                                  (idle_samples[-1]['scan_finished']['mono_ns']-marker['mono_ns'])/1e9],
        observer=observer['observer'], held_worker_observed_deltas=observer['phases'][marker['marker']]['observed_worker_deltas'],
        source_sha256=helper.hashfile(Path(__file__)), regressions=health['regressions'],
        scope='No timing; one full gate passed at retained prepared boundary. No continuous quiescence or original preparation equivalence established.')
    (HERE/'review.json').write_text(json.dumps(review, indent=2, sort_keys=True)+'\n')
    assert not a.issues, a.issues[:10]
    print(json.dumps(dict(passed=True, checks=review['checks'], warmup_operations=warm['completed'], full_capture_tasks=counts, accepted=False)))


if __name__ == '__main__':
    main()
