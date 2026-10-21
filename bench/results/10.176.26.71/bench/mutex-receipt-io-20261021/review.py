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
NEW = CONTROL/'archives-2'
HASH = 'a46ee1fac2d8c217dc8c1b59f4a41638bc5d9bb9c7992fcc5ec7b9916def0545'


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
    check(a.files['capture-health.py'] == helper.hashfile(HERE/'capture-health.py'), 'health_checker_source_binding')
    check(a.files['checks-1/run-checks.py'] == helper.sha(a.git_bytes(read('checks-1/result.json')['source_revision'],
          'bench/results/10.176.26.71/bench/mutex-receipt-io-20261021/run-checks.py')), 'check_runner_source_binding')
    check(result['diagnostic_completed'] and result['final_idle'] and result['passed'] and
          result['planned'] == result['completed'] == 1 and not result['accepted'] and health['idle'], 'drained_diagnostic')
    for path in ('runner.py', 'boundary_protocol.py', 'prewarmup_control.py'):
        original = 'unlock_run.py' if path == 'runner.py' else path
        check(a.files['probe-1/'+path] == helper.sha(a.git_bytes(result['source_commit'],
              'bench/mutex_api_compare/'+original)), 'guest_source_binding', path)
    for retained, group, original in [('inputs', 'inputs', 'inputs-1/inputs.json'),
                                     ('correctness', 'live', 'correctness-1/result.json'),
                                     ('unit-checks', 'checks', 'checks-1/result.json'),
                                     ('task-check', 'live', 'task-2/result.json'),
                                     ('elf-checks', 'metadata', 'elf-checks-2.json')]:
        with tarfile.open(OLD/(group+'.tar.gz')) as archive:
            data = archive.extractfile('pipecap-unlock-20261021/'+original).read()
        check(a.files['probe-1/'+retained+'.json'] == helper.sha(data), 'exact_prerequisite_binding', retained)
    unit = read('checks-1/result.json')
    expected_tests = [('basic', b'Unit tests: 2 passed, 0 failed'), ('receipt-trace', b'Ran 11 tests'), ('phase-accounting', b'Ran 5 tests'), ('boundary-trigger', b'Ran 9 tests'),
        ('boundary-protocol', b'Ran 4 tests'), ('prewarmup-control', b'Ran 12 tests'), ('recovery-gate', b'Ran 6 tests')]
    check(unit['passed'] and unit['final_idle'] and unit['source_unchanged'] and
          [(r['name'], r['exit_code']) for r in unit['commands']] == [(name, 0) for name, _ in expected_tests], 'serial_basic_affected_pass')
    for name, expected in expected_tests:
        check(expected in a.contents['checks-1/'+name+'.log'], 'actual_test_log', name)
    for relative, digest in read('checks-1/sources.json').items():
        check(a.files['checks-1/source/'+relative] == digest ==
              helper.sha(a.git_bytes(unit['source_revision'], relative)), 'tested_source_git_binding', relative)
    row, = result['records']
    prefix = 'probe-1/outer/'+row['name']+'/'
    check(read(prefix+'session.json') == row and row['execution_status'] == 'OK' and row['drained'], 'session_binding')
    check(row['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'exact_retirement')
    lines = a.contents[prefix+'kernel.log'].decode().splitlines()
    owner, = [line for line in lines if 'kd_mutex stats:' in line]
    tasks, = [line for line in lines if 'kd_mutex tasks:' in line]
    check(all(s in owner for s in ('origin_acquires=75164', 'origin_releases=75164', 'active_waiters=0', 'reserved_nodes=0'))
          and 'active_tasks=0' in tasks, 'exact_owner_balance_and_resources')
    check(row['measurement_skipped'] and not any(k in row for k in
          ('measurement', 'whole_throughput_ops_s', 'peak_throughput_ops_s')) and prefix+'measure.json' not in a.files, 'no_timing')
    check(row['duration_ms'] == 2000 and row['warmup'] == 48000 and row['warmup_ms'] == 1000 and
          row['peak_settle_ms'] == row['peak_window_ms'] == 300 and row['sample_ms'] == 10 and
          row['collector_cpu'] == 63 and row['cpus'] == list(range(5)) and row['entries'] == 16 and
          row['actual_lock_cacheline_offset'] == row['lock_addr'] % 64 == 32, 'original_settings')
    work, control = row['boundary_warmup'], row['prewarmup_control']
    check(work == read(prefix+'warmup.json') and work['ok'] and len(work['workers']) == 5 and
          work['completed'] == sum(w['completed'] for w in work['workers']) == 9331584 and
          all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] >= 48000 and
              w['finished_ns'] >= work['started_ns']+1000000000 for w in work['workers']), 'single_joined_warmup')
    check(work['collector_cpu'] == work['collector_observed_cpu'] == 63 and work['collector_error'] == 0 and
          [w['cpu'] for w in work['workers']] == list(range(5)), 'actual_placement')
    check(control['warmup_commands'] == 1 and control['measurement_commands'] == 0 and not control['warmup_skipped'], 'commands')
    check(read(prefix+'check-before.json')['check'] and read(prefix+'check-after-boundary.json')['check'], 'business_oracles')
    pre, post = row['boundaries']
    check([b['stage'] for b in row['boundaries']] == ['before-warmup', 'after-warmup-immediate'], 'ordered_stages')
    for b in (pre, post):
        check(b['before'] == b['after'] and b['before']['physical_idle'] and b['gate']['passed'] and
              b['gate']['comparison']['configuration_matches'] and
              b['before']['publication']['source'] == dict(state=0, modules=1, frames=0, writers=0), 'unchanged_stage_and_full_gate', b['stage'])
    check(pre['after']['publication'] == post['before']['publication'] and pre['after']['client_pid'] == post['before']['client_pid'], 'retained_identity')
    check(post['before']['calls']-pre['after']['calls'] == work['completed'] and row['warmup_counter_delta'] ==
          dict(address_guard_count=0, bench_jit_bodies=5881, bench_jit_completions=5881), 'exact_warmup_delta')
    check(health['boundary_gates'] == [True, True] and health['original_inputs_unchanged'] and
          not health['per_session_kernel_faults'] and not health['measurement_sent'], 'health')
    supervisor = json.loads((CONTROL/'probe-1/supervisor.json').read_text())
    check(supervisor['complete'] and not supervisor['accepted'] and not supervisor['timing_sent'] and
          supervisor['wait_before_warmup'], 'supervisor_contract')
    for path, digest in supervisor['sources'].items():
        relative = str(Path(path).relative_to(ROOT))
        check(helper.hashfile(CONTROL/'probe-1'/Path(path).name) == digest ==
              helper.sha(a.git_bytes(supervisor['source_commit'], relative)), 'supervisor_source_binding', relative)
    before, after = supervisor['boundaries']
    check(before['policy'] == 'wait' and after['policy'] == 'immediate' and not after['sample_decisions'] and
          not after['dispatch_skips'] and len(after['observations']) == 1 and
          after['observations'][0]['trigger']['kind'] == 'immediate', 'no_post_settling_or_retry')
    check(before['request']['remote']['boundary_token'] != after['request']['remote']['boundary_token'], 'fresh_nonces')
    for guest_boundary, source_boundary in zip((pre, post), (before, after)):
        check(guest_boundary['observations'] == source_boundary['observations'] and
              guest_boundary['began_ns'] == source_boundary['request']['remote']['mono_ns'], 'boundary_request_reply_binding')
        observation, = source_boundary['observations']
        host = json.loads((CONTROL/'probe-1'/(observation['capture']+'.json')).read_text())
        check(host == guest_boundary['host'] and helper.sha(json.dumps(host, sort_keys=True).encode()) == observation['host_sha256'], 'selected_host_binding')
    trigger = before['observations'][0]
    check(len(before['sample_decisions']) == 12 and trigger['trigger']['sequence'] == 13 and
          trigger['trigger_freshness']['qualified'] and trigger['trigger_freshness']['dispatch_before_cutoff'], 'qualified_pretrigger')
    observed = [json.loads(line)['remote'] for line in (CONTROL/'probe-1/observer.jsonl').read_text().splitlines()]
    captures = [r for r in observed if r['event'] == 'capture']
    check([len(c['host']['qemu'][0]['tasks']) for c in captures] == [67, 67, 67, 70] and
          [c['host_gate']['passed'] for c in supervisor['captures']] == [True, True, True, False], 'full_capture_sequence_including_failed_endpoint')
    for phase in supervisor['phases']:
        guest, ack = phase['guest_event']['remote'], phase['host_ack']['ack']['remote']
        check(ack['marker'] == f"phase{guest['sequence']}-{guest['label']}-{guest['edge']}", 'phase_ack_binding')
    phases = {(p['guest_event']['remote']['label'], p['guest_event']['remote']['edge']):p for p in supervisor['phases']}
    check(post['finished_ns'] < phases[('client-warmup', 'end')]['guest_event']['remote']['mono_ns'] <
          phases[('prepare', 'end')]['guest_event']['remote']['mono_ns'] <
          phases[('measure-accounting', 'begin')]['guest_event']['remote']['mono_ns'], 'post_before_ordinary_accounting')
    check(pre['finished_ns'] <= control['command_began_ns'] <= work['started_ns'] <= work['finished_ns'] <=
          control['original_reply_saved_ns'] <= control['reply_validation_finished_ns'] <=
          post['times']['before_began_ns'] <= post['began_ns'], 'guest_clock_order')
    observer = json.loads((CONTROL/'observer-review-1.json').read_text())[0]
    check(observer['original_67_unchanged'] and observer['samples'] == 39 and observer['final_tasks'] == 70,
          'accounting_samples_distinct_from_endpoint')
    endpoint_extra = [t for t in captures[-1]['host']['qemu'][0]['tasks'] if t['tid'] not in
                      {t['tid'] for t in captures[2]['host']['qemu'][0]['tasks']}]
    samples = [r for r in observed if r['event'] == 'sample']
    check(all(t['tid'] in {task['tid'] for s in samples for task in s['tasks']} for t in endpoint_extra), 'endpoint_workers_have_accounting_samples')
    arms = [r for r in observed if r['event'] == 'accounting']
    arm, = arms
    check(supervisor['phase_accounting'] and arm['accounting_error'] is None and
          arm['expires_ns']-arm['armed_ns'] == 60_000_000_000 and arm['interval_ns'] == 250_000_000 and
          not any(r['event'] == 'accounting_expired' for r in observed), 'single_bounded_window')
    arm_request = supervisor['accounting_arm']
    check(arm_request['ack']['remote'] == arm and
          arm['accounting'] == 'warmup-through-endpoint-'+before['request']['remote']['boundary_token'] and
          trigger['ack_received_ns'] <= arm_request['sent']['mono_ns'] <= arm_request['ack']['received']['mono_ns'] <= before['reply_sent']['mono_ns'] and
          arm_request['ack']['received']['mono_ns']-arm_request['sent']['mono_ns'] <= 10_000_000_000, 'arm_before_guest_release')
    check([s['sequence'] for s in samples] == list(range(39)), 'continuous_sample_sequence')
    by_sequence = {s['sequence']:s for s in samples}
    dense = [s for s in samples if s['accounting_window_active']]
    check(len(dense) == 25 and dense[0]['sequence'] == arm['baseline_sample'] == 14 and
          dense[0]['reason'] == 'arm' and dense[0]['scan_finished']['mono_ns'] <= arm['mono_ns'], 'armed_baseline_before_ack')
    cap_by_name = {c['capture']:c for c in captures}
    post_capture = cap_by_name[after['observations'][0]['capture']]
    for capture in (post_capture, captures[-1]):
        sample = by_sequence[capture['following_sample']]
        check(capture['following_sample_error'] is None and sample['reason'] == 'after-capture' and
              sample['correlation'] == capture['capture'] and capture['capture_finished']['mono_ns'] <=
              sample['scan_began']['mono_ns'] <= sample['scan_finished']['mono_ns'] <= capture['mono_ns'], 'capture_then_accounting_then_ack')
    markers = [r for r in observed if r['event'] == 'marker' and r['accounting_sample'] is not None]
    check(len(markers) == 17 and markers[-1]['marker'] == 'stop', 'all_remaining_markers_sampled')
    for marker in markers:
        sample = by_sequence[marker['accounting_sample']]
        check(marker['accounting_error'] is None and sample['reason'] == 'marker' and
              sample['correlation'] == marker['marker'] and sample['scan_finished']['mono_ns'] <= marker['mono_ns'], 'sample_before_marker_ack')
    check(all(not [t for t in by_sequence[n]['tasks'] if t.get('comm') == 'worker'] for n in range(14, 20)), 'no_extra_workers_in_six_arm_to_post_reads')
    endpoint_ids = {t['tid'] for t in endpoint_extra}
    check(endpoint_ids == {452912, 452913, 452914}, 'three_endpoint_workers')
    marker_by_name = {m['marker']:m for m in markers}
    cleanup_boot = marker_by_name['phase27-cleanup-begin']['boot_ns']
    births = []
    for worker in observer['workers']:
        if worker['identity'][0] not in endpoint_ids:
            continue
        low, high = worker['birth_boot_interval_ns']
        first_sample = by_sequence[worker['first']['sequence']]
        check(post_capture['capture_finished']['boot_ns'] < low < high < captures[-1]['capture_began']['boot_ns'] and
              worker['final_sample_present'] and worker['tail_missing'] and worker['first']['affinity'] == [63], 'endpoint_birth_after_post_before_endpoint', worker['identity'])
        births.append(dict(identity=worker['identity'], birth_boot_interval_ns=[low, high],
            birth_after_post_capture_ns=[low-post_capture['capture_finished']['boot_ns'], high-post_capture['capture_finished']['boot_ns']],
            first_sample=worker['first']['sequence'], first_pending_marker=first_sample['correlation'],
            first_cumulative=worker['first']['counters'], observed_delta=worker['observed_counter_delta'],
            observations=worker['observations'], tail_missing=True))
    check([b['first_sample'] for b in births] == [20, 33, 34], 'phase_associated_first_observations')
    check(births[0]['birth_boot_interval_ns'][1] < cleanup_boot and
          marker_by_name['phase33-command-unload-kd.log-end']['boot_ns'] < births[1]['birth_boot_interval_ns'][0] <
          births[1]['birth_boot_interval_ns'][1] < marker_by_name['phase34-cleanup-end']['boot_ns'] and
          marker_by_name['phase34-cleanup-end']['boot_ns'] < births[2]['birth_boot_interval_ns'][0] <
          births[2]['birth_boot_interval_ns'][1] < marker_by_name['phase35-final-verification-begin']['boot_ns'],
          'new_cohort_has_one_precleanup_and_two_later_births')
    dense_gaps = [b['scan_began']['mono_ns']-a['scan_finished']['mono_ns'] for a,b in zip(dense,dense[1:])]
    active_cpu_floor = sum(s['observer_scan_cpu_ns'] for s in dense)+sum(c['capture_cpu_ns'] for c in (post_capture, captures[-1]))
    active_duration = observed[-1]['mono_ns']-arm['armed_ns']
    chronology = dict(guest=dict(
        pre_hold_ns=pre['finished_ns']-pre['began_ns'],
        pre_validation_ns=pre['times']['guest_validation_finished_ns']-pre['times']['guest_validation_began_ns'],
        pre_gate_to_command_ns=control['command_began_ns']-pre['finished_ns'],
        command_to_scheduled_work_start_ns=work['started_ns']-control['command_began_ns'],
        work_wall_ns=work['finished_ns']-work['started_ns'],
        work_finish_to_saved_reply_ns=control['original_reply_saved_ns']-work['finished_ns'],
        reply_validation_ns=control['reply_validation_finished_ns']-control['original_reply_saved_ns'],
        post_snapshot_ns=post['times']['before_finished_ns']-post['times']['before_began_ns'],
        saved_reply_to_post_request_ns=post['began_ns']-control['original_reply_saved_ns'],
        work_finish_to_post_request_ns=post['began_ns']-work['finished_ns'],
        post_exchange_ns=post['finished_ns']-post['began_ns'],
        post_validation_ns=post['times']['guest_validation_finished_ns']-post['times']['guest_validation_began_ns'],
        cleanup_phase_interval_ns=phases[('cleanup', 'end')]['guest_event']['remote']['mono_ns']-phases[('cleanup', 'begin')]['guest_event']['remote']['mono_ns']),
        source_post_receipt_to_capture_send_ns=after['observations'][0]['request_sent_ns']-after['request']['received']['mono_ns'],
        host_sample_start_to_pre_capture_ns=trigger['trigger_freshness']['sample_to_capture_ns'],
        captures=[dict(label=c['capture'], tasks=len(c['host']['qemu'][0]['tasks']),
            cpu_ns=c['capture_cpu_ns'], wall_ns=c['capture_finished']['mono_ns']-c['capture_began']['mono_ns']) for c in captures],
        endpoint_extra=endpoint_extra,
        accounting_arm_roundtrip_ns=arm_request['ack']['received']['mono_ns']-arm_request['sent']['mono_ns'],
        accounting_arm_ack_receipt_to_reply_send_stamp_ns=before['reply_sent']['mono_ns']-arm_request['ack']['received']['mono_ns'],
        accounting_window_observed_ns=observed[-1]['mono_ns']-arm['armed_ns'],
        dense_samples=len(dense), dense_maximum_gap_ns=max(dense_gaps),
        dense_scan_cpu_ns=sum(s['observer_scan_cpu_ns'] for s in dense),
        dense_scan_wall_ns=sum(s['scan_finished']['mono_ns']-s['scan_began']['mono_ns'] for s in dense),
        active_window_cpu_lower_bound_ns=active_cpu_floor,
        active_window_cpu_lower_bound_percent_one_core=100*active_cpu_floor/active_duration,
        endpoint_worker_births=births)
    records = json.loads((CONTROL/'probe-1/receipt-trace.json').read_text())
    trace, exported = records
    check(supervisor['receipt_trace'] and supervisor['receipt_export']['complete'] and
          trace['event'] == 'receipt_trace' and exported['event'] == 'receipt_export' and
          trace['token'] == exported['token'] == before['request']['remote']['boundary_token'] and
          trace['complete'] and exported['complete'] and not trace['errors'] and not trace['dropped'] and
          not trace['expired'] and len(trace['events']) == 49 and
          [e['sequence'] for e in trace['events']] == list(range(49)), 'complete_bounded_receipt_trace')
    check(a.files['probe-1/receipt_trace.py'] == helper.sha(a.git_bytes(result['source_commit'],
          'bench/mutex_api_compare/receipt_trace.py')), 'trace_source_binding')
    check(a.files['run-checks.py'] == a.files['checks-1/run-checks.py'], 'external_check_runner_binding')
    writes = [e for e in trace['events'] if e['kind'] == 'write']
    check(len(writes) == 17 and sum(e['completed_bytes'] for e in writes) == 4874247 and
          all(e['error'] is None and e['errno'] is None and e['requested_bytes'] == e['completed_bytes'] and
              e['began']['mono_before_ns'] <= e['began']['mono_ns'] <= e['finished']['mono_before_ns'] <=
              e['finished']['mono_ns'] for e in writes), 'logical_writes_complete_and_bracketed')
    check(sum(e['path'].endswith('/session.json') for e in writes) == 6 and
          sum(e['completed_bytes'] for e in writes if e['path'].endswith('/session.json')) == 3618281,
          'repeated_session_receipt_bytes')
    for path in {e['path'] for e in writes}:
        last = [e for e in writes if e['path'] == path][-1]
        check(last['completed_bytes'] == len(a.contents['probe-1/'+path]), 'last_observed_file_size', path)
    check(writes[-1]['path'] == 'result.json' and writes[-1]['finished']['mono_ns'] <= exported['began']['mono_before_ns'] and
          trace['finished']['mono_ns'] <= exported['serialized']['mono_before_ns'] <=
          exported['flushed']['mono_ns'], 'final_original_save_before_export')
    workload = [json.loads(line) for line in (CONTROL/'probe-1/workload.jsonl').read_text().splitlines()]
    envelopes = [r for r in workload if r['remote'].get('text', '').startswith(('KD_RECEIPTS ', 'KD_RECEIPT_EXPORT '))]
    check(len(envelopes) == 2 and len(envelopes[0]['remote']['text'].encode()) == exported['envelope_bytes'] == 17830 and
          json.loads(envelopes[0]['remote']['text'][len('KD_RECEIPTS '):]) == trace and
          json.loads(envelopes[1]['remote']['text'][len('KD_RECEIPT_EXPORT '):]) == exported, 'export_wire_binding')
    guest_stream, = [r for r in supervisor['streams'] if r['label'] == 'workload']
    endpoint_request, = [r for r in supervisor['requests'] if r.get('value') == 'endpoint']
    check(guest_stream['exit_code'] == 0 and envelopes[0]['received']['mono_ns'] <=
          envelopes[1]['received']['mono_ns'] <= guest_stream['finished']['mono_ns'] <=
          endpoint_request['sent']['mono_ns'], 'normal_guest_exit_before_original_endpoint')
    send = {e['label']:e for e in trace['events'] if e['kind'] == 'phase-send'}
    replies = {e['label']:e for e in trace['events'] if e['kind'] == 'phase-reply'}
    check(len(send) == len(replies) == 16 and set(send) == set(replies), 'paired_phase_trace_records')
    offsets = []
    for label in send:
        phase, = [p for p in supervisor['phases'] if p['host_ack']['ack']['remote']['marker'] == label]
        h = phase['host_ack']['ack']['remote']['boot_ns']
        hs, hr = phase['host_ack']['sent']['mono_ns'], phase['host_ack']['ack']['received']['mono_ns']
        gs, ge = send[label]['clock']['mono_before_ns'], replies[label]['clock']['mono_ns']
        gr, ga = phase['guest_event']['received']['mono_ns'], phase['guest_ack_sent']['mono_ns']
        low, high = (h-hr)+(ga-ge), (h-hs)+(gr-gs)
        check(low <= high and gs <= ge and hs <= hr and gr <= ga, 'local_phase_offset_bracket', label)
        offsets.append(dict(label=label, host_boot_minus_guest_mono_ns=[low, high],
            direct_interval_ns=[h-ge, h-gs], width_ns=high-low,
            assumption='Locally stable clock rates over this exchange; extension to nearby writes has no measured drift bound.'))
    # These are conditional overlap illustrations, not unconditional ordering
    # or causal attribution. No global clock fit or cross-run offset is used.
    overlaps = []
    for birth, label in zip(births, ['phase21-client-warmup-end', 'phase34-cleanup-end', 'phase35-final-verification-begin']):
        offset, = [o for o in offsets if o['label'] == label]
        low, high = offset['host_boot_minus_guest_mono_ns']
        b0, b1 = birth['birth_boot_interval_ns']
        interval = [b0-high, b1-low]
        overlapping = [e['sequence'] for e in writes if e['began']['mono_before_ns'] < interval[1] and
                       e['finished']['mono_ns'] >= interval[0]]
        overlaps.append(dict(identity=birth['identity'], nearby_phase=label,
                             conditional_guest_birth_interval_ns=interval, overlapping_write_sequences=overlapping))
    # All three appear in host sample34 before its phase35 ACK. That ACK's
    # guest receipt is before export, so births precede export by causality.
    sample34 = by_sequence[34]
    check(endpoint_ids <= {t['tid'] for t in sample34['tasks']} and
          marker_by_name['phase35-final-verification-begin']['accounting_sample'] == 34 and
          replies['phase35-final-verification-begin']['clock']['mono_ns'] < exported['began']['mono_before_ns'],
          'endpoint_births_precede_export_without_clock_alignment')
    io_before, io_after = trace['baseline_io']['counters'], trace['final_io']['counters']
    receipt_summary = dict(events=len(trace['events']), writes=len(writes), logical_bytes=4874247,
        hook_observer_cpu_lower_bound_ns=trace['observer_cpu_lower_bound_ns'],
        traced_elapsed_ns=trace['finished']['mono_ns']-trace['started']['mono_before_ns'],
        write_wall_sum_ns=sum(e['finished']['mono_ns']-e['began']['mono_before_ns'] for e in writes),
        write_cpu_sum_ns=sum(e['finished']['cpu_ns']-e['began']['cpu_ns'] for e in writes),
        process_io_delta={k:io_after[k]-v for k,v in io_before.items()},
        export_cpu_ns=exported['flushed']['cpu_ns']-exported['began']['cpu_ns'],
        export_wall_ns=exported['flushed']['mono_ns']-exported['began']['mono_before_ns'],
        export_bytes=exported['envelope_bytes'],
        export_trailer_receipt_to_recorded_guest_finish_ns=guest_stream['finished']['mono_ns']-envelopes[1]['received']['mono_ns'],
        recorded_guest_finish_to_endpoint_dispatch_ns=endpoint_request['sent']['mono_ns']-guest_stream['finished']['mono_ns'],
        offsets=offsets, conditional_overlaps=overlaps,
        scope='Phase-only control counts; logical file bytes; optional export cannot initiate earlier births but can add later activity. '
              'No fsync, FD/block attribution, full I/O coverage, measured clock-drift bound or causal acceptance.')
    failed_archive = json.loads((CONTROL/'archives-1/archives.json').read_text())
    check(not failed_archive['completed'] and not failed_archive['groups'] and
          'metadata is reserved' in failed_archive['error'], 'failed_archive_attempt_preserved')
    output = dict(integrity_passed=not a.issues, accepted=False, checks=sum(a.counts.values()),
        issues=a.issues, check_counts=dict(a.counts), archives=groups, archive_manifest_sha256=HASH,
        source_sha256=helper.hashfile(Path(__file__)),
        source_commit=supervisor['source_commit'], tested_commit=unit['source_revision'],
        warmup_operations=work['completed'], returned_bodies=row['warmup_counter_delta']['bench_jit_completions'],
        chronology=chronology, receipt_trace=receipt_summary, observer=observer['observer'], observer_limitations=observer['limitations'],
        unresolved=list(health['regressions']), acquisition_latency='UNRESOLVED_NOT_THROUGHPUT_GATE', p95='DEFERRED_NOT_THROUGHPUT_GATE',
        performance_variance='NOT_MEASURED', complete_operation_p95='SEPARATE_METRIC',
        raw_sha256={str(p.relative_to(CONTROL)):helper.hashfile(p) for p in sorted(CONTROL.rglob('*')) if p.is_file()})
    (HERE/'review.json').write_text(json.dumps(output, indent=2, sort_keys=True)+'\n')
    assert not a.issues, a.issues[:10]
    print(json.dumps(dict(passed=True, checks=output['checks'], chronology=chronology, accepted=False)))


if __name__ == '__main__':
    main()
