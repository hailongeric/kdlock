"""Focused VM-only checks for diagnostic scope, accounting and timeout ownership."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('nano_profile', ROOT / 'bench/nano/profile.py')
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


BATCH_METADATA = dict(schema=3, compiled=1, total_cap=1024, numa_boundary=1024,
                      deferred_handoff=8, scan_budget=64, numa_aware=1,
                      completed_hist_bins=16, deferred_peak_hist_bins=8)
BATCH_COUNTERS = ('batches', 'attempts', 'jit_completed', 'native_completed', 'owner_transfers',
                  'execution_refusals', 'jit_local', 'jit_remote', 'deferred_total',
                  'scan_steps', 'scan_exhausted_batches', 'small_fifo_batches')


def batch_snapshot(scale=1, *, schema=3):
    """Five historical batches; schema 3 also records one unfinished transfer."""
    completed = [0] * 16
    completed[0], completed[1], completed[2], completed[4] = 2, 1, 1, 1
    deferred = [0] * 8
    deferred[0], deferred[1], deferred[4] = 3, 1, 1
    result = dict(BATCH_METADATA, batches=5, attempts=12, jit_completed=10,
                  native_completed=1, execution_refusals=1, jit_local=7, jit_remote=3,
                  deferred_total=9, scan_steps=9, scan_exhausted_batches=0,
                  small_fifo_batches=1, completed_hist=completed, deferred_peak_hist=deferred,
                  stop_reason=dict(unclassified=0, initial_unexecutable=1, source_refusal=0,
                      numa_boundary=0, numa_tail=1, execution_refusal=1, early_outer_release=0,
                      native_done=1, total_cap=0, empty_tail=1, unsupported_tail=0),
                  legacy=dict(combiner=5, jit_success=10, handoff=2))
    result['schema'] = schema
    if schema == 3:
        result.update(owner_transfers=1, batches=6, attempts=13)
        result['completed_hist'][0] += 1
        result['deferred_peak_hist'][0] += 1
        result['stop_reason']['owner_transfer'] = 1
        result['legacy']['combiner'] += 1
    for key in BATCH_COUNTERS:
        if key in result:
            result[key] *= scale
    for key in ('completed_hist', 'deferred_peak_hist'):
        result[key] = [value * scale for value in result[key]]
    for key in ('stop_reason', 'legacy'):
        result[key] = {name: value * scale for name, value in result[key].items()}
    return result


def pin_snapshot(scale=1, *, shift=0):
    """Pins can be consumed by native exits or repeated FULL continuations."""
    result = dict(schema=1, compiled=2, window=4, total_cap=1024, numa_boundary=1024,
        tsc_sample_shift=shift, batches=2, selections=5, requested=10, consumed=7, cancelled=3,
        drain_calls=6, drain_nonempty=3, drain_keep_current=1,
        current_ack_immediate=6, current_ack_stalled=2, current_ack_loops=5,
        cancel_ack_immediate=2, cancel_ack_stalled=1, cancel_ack_loops=3,
        full_resumes=1, tsc_samples=2 if shift else 0, tsc_cycles=200 if shift else 0,
        occupancy_before=[2, 1, 0, 1, 1], occupancy_after=[1, 0, 1, 1, 2],
        refill_stop=dict(self_current=1, single=0, budget=0, window=2, no_link=1,
                         entry=0, numa=0, deferred_tail=0, duplicate_cpu=1, self_future=0))
    for key in profile.PIN_COUNTERS:
        result[key] *= scale
    for key in profile.PIN_HISTOGRAMS:
        result[key] = [value * scale for value in result[key]]
    result['refill_stop'] = {key: value * scale for key, value in result['refill_stop'].items()}
    return result


class NanoProfileTests(unittest.TestCase):
    def test_stat_requires_every_event_and_valid_runtime(self):
        valid = '100;;cycles:k;2000000;100.00;;\n0;;cache-misses:k;2000000;100.00;;\n'
        result = profile.parse_stat(valid, ['cycles:k', 'cache-misses:k'])
        self.assertEqual(result['events']['cache-misses:k']['value'], 0)
        for bad in ('', valid.replace('100;;cycles', '<not counted>;;cycles'),
                    valid.replace('100;;cycles', '<not supported>;;cycles'),
                    valid.replace(';2000000;', ';0;'), valid.replace('100;;cycles', 'nan;;cycles'),
                    valid + valid, valid.splitlines()[0]):
            with self.assertRaises(ValueError):
                profile.parse_stat(bad, ['cycles:k', 'cache-misses:k'])

    def test_multiplexing_is_explicit_and_never_a_zero_counter(self):
        raw = '100;;cycles:k;2000000;67.50;;\n'
        with self.assertRaises(ValueError):
            profile.parse_stat(raw, ['cycles:k'])
        result = profile.parse_stat(raw, ['cycles:k'], allow_multiplex=True)
        self.assertEqual(result['status'], 'MULTIPLEXED')
        self.assertEqual(result['events']['cycles:k']['runtime_percent'], 67.5)

    def test_profile_commands_keep_perf_output_separate_and_flat(self):
        client = ['python3', '/frozen/client.py', '--spec', '/run/measure.spec.json']
        options = dict(cpu=63, events=['cycles:k'], record_event='cycles:k', frequency=997)
        stat = profile.perf_command('/retained/perf', 'stat', Path('/run'), client, **options)
        record = profile.perf_command('/retained/perf', 'record', Path('/run'), client, **options)
        self.assertEqual(stat[-4:], client)
        self.assertEqual(record[-4:], client)
        self.assertIn('/run/perf-stat.csv', stat)
        self.assertIn('--inherit', record)
        self.assertIn('mono', record)
        self.assertNotIn('--call-graph', record)
        self.assertEqual(record[:3], ['taskset', '-c', '63'])

    def test_samples_separate_worker_roi_startup_unknown_and_generated(self):
        m = dict(deadline_ns=2_000_000_000, peak_settle_ns=200_000_000,
                 workers=[dict(active_started_ns=1_000_000_000, kernel_finished_ns=2_100_000_000)])
        def line(comm, timestamp, period, address, symbol='func', dso='kernel'):
            return f'{comm} 10/11 [000] {timestamp}: {period} cycles:k: {address:x} {symbol} ({dso})'
        text = '\n'.join([line('python3', '1.1', 10, 0x10),
            line('rb_worker', '0.9', 20, 0x10), line('rb_worker', '1.2', 30, 0x1001, '[unknown]', '[unknown]'),
            line('rb_worker', '1.3', 40, 0x20, '[unknown]', '[unknown]'),
            line('rb_worker', '1.4', 50, 0x30),
            line('rb_worker', '1.1', 70, 0x30), 'PERF_RECORD_LOST 1 event'])
        result = profile.summarize_samples(text, m, [0], 'cycles:k', [dict(start=0x1000, end=0x1010)])
        self.assertEqual(result['totals']['worker_settled_cohort_period'], 120)
        self.assertEqual(result['totals']['other_client_thread_samples'], 1)
        self.assertEqual(result['totals']['worker_outside_settled_cohort_samples'], 2)
        self.assertEqual(result['sampled_begin_ns'], 1_200_000_000)
        self.assertEqual(result['status'], 'LOST_SAMPLES')
        self.assertEqual({r['category'] for r in result['hot_paths']}, {'SYMBOL', 'UNKNOWN', 'GENERATED_IMAGE'})
        with self.assertRaises(ValueError):
            profile.summarize_samples(line('python3', '1.1', 5, 0x10), m, [0], 'cycles:k', [])
        with self.assertRaises(ValueError):
            profile.summarize_samples(text.replace('[000]', '[001]'), m, [0], 'cycles:k', [])

    def test_observation_delta_preserves_missing_counters_and_rejects_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name in profile.OBSERVATION_PARAMS:
                (folder / name).write_text('10')
            self.assertFalse((folder / 'mutex_batch_stats').exists())
            before = profile.observations(folder)
            self.assertIn('kd_mutex_combiner_count', before['unavailable_static_counters'])
            self.assertNotIn('kd_mutex_combiner_count', before['values'])
            (folder / 'bench_jit_completions').write_text('15')
            after = profile.observations(folder)
            self.assertEqual(profile.observation_delta(before, after)['bench_jit_completions'], 5)
            with self.assertRaises(ValueError):
                profile.observation_delta(after, before)
            (folder / 'address_guard_count').unlink()
            with self.assertRaises(ValueError):
                profile.observations(folder)

    def test_diagnostic_report_cannot_promote_returned_jit_to_score(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            (out / 'case').mkdir()
            (out / 'plan.json').write_text(json.dumps([dict(name='case')]))
            (out / 'case/session.json').write_text(json.dumps(dict(name='case', functional=False,
                score_eligible=True, measurement=dict(completed=10, reads=0, writes=10, wall_ns=100,
                    peak=dict(throughput_ops_s=10)), execution_status='OK', drained=True)))
            runner = types.SimpleNamespace(valid=lambda r: True, execution_class=lambda r: 'RETURNED_JIT')
            self.assertEqual(profile.diagnostic_report(runner, out)['status'], 'DIAGNOSTIC')
            row = json.loads((out / 'records.json').read_text())[0]
            self.assertFalse(row['score_eligible'])
            self.assertTrue(row['diagnostic'])
            self.assertEqual(json.loads((out / 'summary.json').read_text()), [])

    def test_warmup_passes_through_without_starting_perf(self):
        class Base:
            def run(self, command, log, **kwargs):
                return (command, log)
        runner = types.SimpleNamespace(RWSession=Base)
        cls = profile.profiled_session(runner, types.SimpleNamespace(), Path('/perf'), 'hash')
        with patch.object(profile, 'launch_profiled_client') as launch:
            self.assertEqual(cls().run(['client'], 'warmup.json'), (['client'], 'warmup.json'))
            launch.assert_not_called()

    def test_timeout_preserves_recorder_and_never_kills_workload(self):
        class Failure(RuntimeError):
            def __init__(self, status, message, unsafe=False):
                super().__init__(message)
                self.unsafe = unsafe
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            child = Mock(pid=123)
            child.wait.side_effect = subprocess.TimeoutExpired(['perf'], 120)
            session = types.SimpleNamespace(path=out)
            with patch.object(profile.subprocess, 'Popen', return_value=child):
                with self.assertRaises(Failure) as caught:
                    profile.launch_profiled_client(session, ['perf'], 120, Failure)
            self.assertTrue(caught.exception.unsafe)
            child.kill.assert_not_called()
            child.terminate.assert_not_called()
            self.assertEqual(json.loads((out / 'perf-command.json').read_text())['state'], 'UNKNOWN_DRAIN')

    def test_policy_cli_is_forwarded_and_invalid_policy_precedes_live_work(self):
        base = ['--mode', 'batch', '--output', '/tmp/new-profile', '--source-commit', 'a' * 40]
        for cap, boundary in ((1024, 1024), (1024, 768), (4096, 768), (1024, 256)):
            args = profile.parser().parse_args(base + ['--mutex-batch-limit', str(cap),
                                                      '--mutex-numa-boundary', str(boundary)])
            argv = profile.runner_arguments(args, 'mutex-throughput')
            self.assertEqual(argv[argv.index('--mutex-batch-limit') + 1], str(cap))
            self.assertEqual(argv[argv.index('--mutex-numa-boundary') + 1], str(boundary))
        for extra in (['--mutex-batch-limit', '0'], ['--mutex-batch-limit', '32768'],
                      ['--mutex-numa-boundary', '0'], ['--mutex-numa-boundary', '32768'],
                      ['--mutex-batch-limit', '4096', '--backends', 'native']):
            with self.subTest(extra=extra), patch.object(profile.sys, 'argv', ['profile.py', *base, *extra]), \
                    patch.object(profile.os, 'geteuid') as identity, self.assertRaises(ValueError):
                profile.main()
            identity.assert_not_called()

    def test_default_profile_matrix_preserves_body_and_post_work(self):
        args = profile.parser().parse_args(['--mode', 'stat', '--output', '/tmp/new-profile',
                                           '--source-commit', 'a' * 40])
        self.assertEqual(args.threads, [16, 36, 60])
        self.assertEqual((args.mutex_batch_limit, args.mutex_numa_boundary), (1024, 1024))
        self.assertEqual(args.profiles, ['mutex-throughput', 'mutex-locality'])
        self.assertEqual(profile.selected_backends(args), ['native', 'kdlock'])
        self.assertEqual(set(profile.PROFILES), {'mutex-throughput', 'mutex-locality'})
        with patch.object(profile.sys, 'stderr'), self.assertRaises(SystemExit):
            profile.parser().parse_args(['--mode', 'stat', '--output', '/tmp/retired-profile',
                                        '--source-commit', 'a' * 40, '--profiles', 'mutex'])
        for name, workload, lines, post in [('mutex-throughput', 'cacheline', '1', '256'),
                ('mutex-locality', 'cacheline', '16', '256')]:
            argv = profile.runner_arguments(args, name)
            self.assertEqual(argv[argv.index('--workloads') + 1], workload)
            self.assertEqual(argv[argv.index('--cachelines') + 1], lines)
            self.assertEqual(argv[argv.index('--post-work-rounds') + 1], post)
            self.assertEqual(argv[argv.index('--repeats') + 1], '1')
            self.assertEqual(argv[argv.index('--write-percent') + 1], '100')

    def test_batch_defaults_select_only_kd_and_allow_the_same_node_boundary(self):
        args = profile.parser().parse_args(['--mode', 'batch', '--output', '/tmp/new-profile',
                                           '--source-commit', 'a' * 40,
                                           '--threads', '16', '32', '36', '60'])
        self.assertEqual(profile.selected_backends(args), ['kdlock'])
        self.assertEqual(args.threads, [16, 32, 36, 60])
        argv = profile.runner_arguments(args, 'mutex-throughput')
        selected = argv[argv.index('--backends') + 1:argv.index('--repeats')]
        self.assertEqual(selected, ['kdlock'])

    def test_batch_measurement_passes_through_without_perf(self):
        class Base:
            def run(self, command, log, **kwargs):
                return (command, log)
        runner = types.SimpleNamespace(RWSession=Base)
        cls = profile.profiled_session(runner, types.SimpleNamespace(mode='batch'), None, None)
        with patch.object(profile, 'launch_profiled_client') as launch:
            self.assertEqual(cls().run(['client'], 'measure.json'), (['client'], 'measure.json'))
            launch.assert_not_called()


    def test_pin_mode_and_tsc_guards_precede_live_work(self):
        base = ['--output', '/tmp/new-profile', '--source-commit', 'a' * 40]
        for sampled in (False, True):
            args = profile.parser().parse_args(base + ['--mode', 'pin', '--threads', '20'] +
                                               (['--pin-tsc'] if sampled else []))
            self.assertEqual(profile.selected_backends(args), ['kdlock'])
            self.assertEqual(profile.diagnostic_settings(args),
                dict(mutex_diag=2, mutex_pin_tsc_shift=6 if sampled else 0))
            self.assertEqual(args.threads, [20])
        for mode, expected in (('stat', 0), ('record', 0), ('batch', 1)):
            args = profile.parser().parse_args(base + ['--mode', mode])
            self.assertEqual(profile.diagnostic_settings(args),
                             dict(mutex_diag=expected, mutex_pin_tsc_shift=0))
        for options in (['--mode', 'pin', '--backends', 'native'],
                        ['--mode', 'pin', '--backends', 'native', 'kdlock'],
                        ['--mode', 'batch', '--backends', 'native'],
                        *(['--mode', mode, '--pin-tsc'] for mode in ('stat', 'record', 'batch'))):
            with self.subTest(options=options), \
                    patch.object(profile.sys, 'argv', ['profile.py', *base, *options]), \
                    patch.object(profile.os, 'geteuid') as identity, self.assertRaises(ValueError):
                profile.main()
            identity.assert_not_called()

    def test_current_kernel_defaults_and_explicit_identity_are_forwarded(self):
        base = ['--mode', 'pin', '--output', '/tmp/new-profile', '--source-commit', 'a' * 40]
        args = profile.parser().parse_args(base)
        self.assertEqual(args.kernel_source, Path('/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'))
        self.assertEqual(args.kernel_baseline, Path('/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'))
        for args in (args, profile.parser().parse_args(base + ['--kernel-source', '/selected/build',
                '--kernel-baseline', '/selected/bundle', '--kernel-variant', 'kdmm1-native'])):
            argv = profile.runner_arguments(args, 'mutex-throughput')
            for option, expected in (('--kernel-source', args.kernel_source),
                    ('--kernel-baseline', args.kernel_baseline), ('--kernel-variant', args.kernel_variant)):
                self.assertEqual(argv[argv.index(option) + 1], str(expected))

    def test_pin_measurement_passes_through_without_perf(self):
        class Base:
            def run(self, command, log, **kwargs):
                return (command, log)
        runner = types.SimpleNamespace(RWSession=Base)
        cls = profile.profiled_session(runner, types.SimpleNamespace(mode='pin'), None, None)
        with patch.object(profile, 'launch_profiled_client') as launch:
            self.assertEqual(cls().run(['client'], 'measure.json'), (['client'], 'measure.json'))
            launch.assert_not_called()

    def test_pin_snapshots_bracket_joined_measurement_without_body_equivalence(self):
        events = []
        class Base:
            def measure(self):
                events.append('joined measurement')
                self.record['jit_completions'] = 999
            def save(self):
                pass
        with tempfile.TemporaryDirectory() as temporary:
            cls = profile.profiled_session(types.SimpleNamespace(RWSession=Base),
                types.SimpleNamespace(mode='pin', pin_tsc=True), None, None)
            session = cls()
            session.loaded_kd, session.path = True, Path(temporary)
            session.record = dict(provider_mutex_policy=dict(total_cap=1024, numa_boundary=1024,
                                                            deferred_handoff=8, scan_budget=64))
            snapshots = iter((pin_snapshot(shift=6), pin_snapshot(2, shift=6)))
            def read_snapshot(path):
                self.assertEqual(path.name, 'mutex_pin_stats')
                events.append('pin snapshot')
                return json.dumps(next(snapshots))
            with patch.object(profile, 'observations', side_effect=[dict(values={'n': 0}), dict(values={'n': 1})]), \
                    patch.object(Path, 'read_text', read_snapshot):
                session.measure()
            self.assertEqual(events, ['pin snapshot', 'joined measurement', 'pin snapshot'])
            self.assertEqual(session.record['pin_diagnostics']['delta'], pin_snapshot(shift=6))
            self.assertEqual(json.loads((session.path / 'pin-delta.json').read_text()), pin_snapshot(shift=6))
            self.assertTrue(session.record['diagnostic'])
            self.assertFalse(session.record['score_eligible'])
            self.assertNotIn('drained', session.record)


class NanoPinSnapshotTests(unittest.TestCase):
    def test_valid_snapshot_and_delta_preserve_metadata_and_inputs(self):
        for shift in (0, 6):
            zero, before, after = (pin_snapshot(n, shift=shift) for n in (0, 1, 2))
            original = deepcopy((zero, before, after))
            for snapshot in (zero, before, after):
                self.assertEqual(profile.validate_pin(snapshot, tsc_sample_shift=shift), snapshot)
            self.assertEqual(profile.pin_delta(before, after, tsc_sample_shift=shift), before)
            self.assertEqual(profile.pin_delta(zero, before, tsc_sample_shift=shift), before)
            self.assertEqual(profile.pin_delta(before, before, tsc_sample_shift=shift), zero)
            self.assertEqual((zero, before, after), original)

    def test_policy_and_tsc_metadata_must_match_explicit_selection(self):
        policy = dict(total_cap=4096, numa_boundary=768, deferred_handoff=8, scan_budget=64)
        before, after = pin_snapshot(shift=6), pin_snapshot(2, shift=6)
        for snapshot in (before, after):
            snapshot.update(total_cap=4096, numa_boundary=768)
        self.assertEqual(profile.pin_delta(before, after, policy, 6), before)
        for selected, shift in ((None, 6), (policy, 0), (policy, 1), (policy, True)):
            with self.subTest(policy=selected, shift=shift), self.assertRaises(ValueError):
                profile.validate_pin(before, selected, shift)
        for key in profile.PIN_METADATA:
            changed = deepcopy(after)
            changed[key] += 1
            with self.subTest(metadata=key), self.assertRaises(ValueError):
                profile.pin_delta(before, changed, policy, 6)

    def test_schema_and_exact_shapes_are_required(self):
        valid = pin_snapshot()
        for key in valid:
            invalid = deepcopy(valid)
            del invalid[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                profile.validate_pin(invalid)
        for key, value in (('schema', True), ('window', 3), ('compiled', 1),
                ('occupancy_before', [0] * 4), ('occupancy_after', [0] * 6),
                ('occupancy_after', {}), ('refill_stop', []), ('unexpected', 0)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                profile.validate_pin(dict(valid, **{key: value}))
        for key in profile.PIN_REASONS:
            invalid = deepcopy(valid)
            del invalid['refill_stop'][key]
            with self.subTest(missing_reason=key), self.assertRaises(ValueError):
                profile.validate_pin(invalid)
        invalid = deepcopy(valid)
        invalid['refill_stop']['unexpected'] = 0
        with self.assertRaises(ValueError):
            profile.validate_pin(invalid)

    def test_counters_require_nonnegative_u64_integers(self):
        for keys in (*((key,) for key in profile.PIN_COUNTERS),
                     ('occupancy_before', 0), ('occupancy_after', 0), ('refill_stop', 'window')):
            for value in (-1, True, 1.0, '1', None, 1 << 64):
                invalid = pin_snapshot()
                target = invalid if len(keys) == 1 else invalid[keys[0]]
                target[keys[-1]] = value
                with self.subTest(keys=keys, value=value), self.assertRaises(ValueError):
                    profile.validate_pin(invalid)

    def test_quiescent_accounting_identities_and_ack_bounds(self):
        for changes in (dict(selections=6), dict(requested=11), dict(consumed=8), dict(cancelled=4),
                dict(cancel_ack_immediate=3), dict(current_ack_loops=1),
                dict(current_ack_stalled=0), dict(cancel_ack_loops=0),
                dict(cancel_ack_stalled=0, cancel_ack_immediate=3),
                dict(drain_nonempty=7), dict(drain_keep_current=4),
                dict(tsc_samples=1), dict(tsc_cycles=1)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                profile.validate_pin(dict(pin_snapshot(), **changes))
        for key in profile.PIN_HISTOGRAMS:
            invalid = pin_snapshot()
            invalid[key][0] += 1
            with self.subTest(histogram=key), self.assertRaises(ValueError):
                profile.validate_pin(invalid)
        invalid = pin_snapshot()
        invalid['refill_stop']['window'] += 1
        with self.assertRaises(ValueError):
            profile.validate_pin(invalid)
        with self.assertRaises(ValueError):
            profile.validate_pin(dict(pin_snapshot(shift=6), tsc_samples=9), tsc_sample_shift=6)

    def test_delta_rejects_counter_bin_and_reason_resets(self):
        with self.assertRaises(ValueError):
            profile.pin_delta(pin_snapshot(2), pin_snapshot())
        for group, bucket, destination in (('occupancy_before', 1, 0),
                ('occupancy_after', 2, 0), ('refill_stop', 'self_current', 'no_link')):
            after = pin_snapshot(2)
            after[group][destination] += after[group][bucket]
            after[group][bucket] = 0
            profile.validate_pin(after)
            with self.subTest(group=group), self.assertRaises(ValueError):
                profile.pin_delta(pin_snapshot(), after)
        after = dict(pin_snapshot(2), full_resumes=0)
        profile.validate_pin(after)
        with self.assertRaises(ValueError):
            profile.pin_delta(pin_snapshot(), after)


class NanoBatchSnapshotTests(unittest.TestCase):
    def test_historical_schema_is_preserved_and_never_mixed_with_current(self):
        before, after = batch_snapshot(schema=2), batch_snapshot(2, schema=2)
        self.assertEqual(profile.validate_batch(before), before)
        self.assertEqual(profile.batch_delta(before, after, expected_completions=10), before)
        self.assertEqual(before['schema'], 2)
        self.assertNotIn('owner_transfers', before)
        self.assertNotIn('owner_transfer', before['stop_reason'])
        for old, new in ((before, batch_snapshot(2)), (batch_snapshot(), after)):
            with self.assertRaisesRegex(ValueError, 'schema changed'):
                profile.batch_delta(old, new)
        for invalid in (dict(before, owner_transfers=0), dict(batch_snapshot(), schema=2)):
            with self.assertRaises(ValueError):
                profile.validate_batch(invalid)

    def test_transfer_is_an_unfinished_attempt_with_its_own_stop_reason(self):
        snapshot = batch_snapshot()
        self.assertEqual(snapshot['attempts'], 13)
        self.assertEqual(snapshot['jit_completed'] + snapshot['native_completed'], 11)
        self.assertEqual(snapshot['owner_transfers'], 1)
        profile.validate_batch(snapshot)
        for classification in ('native_completed', 'execution_refusals'):
            invalid = deepcopy(snapshot)
            invalid['owner_transfers'] -= 1
            invalid[classification] += 1
            with self.assertRaisesRegex(ValueError, 'ownership transfer accounting'):
                profile.validate_batch(invalid)

    def test_nondefault_batch_metadata_requires_the_exact_recorded_policy(self):
        for cap, boundary in ((1024, 768), (4096, 768), (1024, 256)):
            policy = dict(total_cap=cap, numa_boundary=boundary, deferred_handoff=8, scan_budget=64)
            before, after = batch_snapshot(), batch_snapshot(2)
            before.update(policy)
            after.update(policy)
            self.assertEqual(profile.batch_delta(before, after, 10, policy), before)
            with self.assertRaises(ValueError):
                profile.validate_batch(before)
            with self.assertRaises(ValueError):
                profile.batch_delta(before, batch_snapshot(2), 10, policy)
            invalid = dict(policy, scan_budget=65)
            with self.assertRaises(ValueError):
                profile.validate_batch(dict(before, **invalid), invalid)

    def test_valid_snapshot_and_delta_preserve_metadata_and_inputs(self):
        zero, before, after = batch_snapshot(0), batch_snapshot(), batch_snapshot(2)
        original = deepcopy((zero, before, after))
        for snapshot in (zero, before, after):
            profile.validate_batch(snapshot)
        self.assertEqual(profile.batch_delta(before, after, expected_completions=10), before)
        self.assertEqual(profile.batch_delta(zero, before), before)
        self.assertEqual(profile.batch_delta(before, before, expected_completions=0), zero)
        self.assertEqual((zero, before, after), original)

    def test_schema_metadata_and_shapes_are_required(self):
        replacements = [
            (('schema',), 1), (('schema',), True), (('compiled',), 0),
            (('total_cap',), 0), (('numa_boundary',), 128),
            (('deferred_handoff',), 0), (('scan_budget',), 0), (('numa_aware',), 0),
            (('completed_hist_bins',), 33), (('deferred_peak_hist_bins',), 33),
            (('completed_hist',), [0] * 15), (('completed_hist',), [0] * 17),
            (('deferred_peak_hist',), [0] * 7), (('deferred_peak_hist',), [0] * 9),
            (('completed_hist',), {}), (('stop_reason',), []), (('legacy',), []),
        ]
        for keys, replacement in replacements:
            with self.subTest(path=keys, replacement=replacement):
                invalid = batch_snapshot()
                target = invalid
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = replacement
                with self.assertRaises(ValueError):
                    profile.validate_batch(invalid)
        for key in (*BATCH_METADATA, *BATCH_COUNTERS, 'completed_hist',
                    'deferred_peak_hist', 'stop_reason', 'legacy'):
            with self.subTest(missing=key):
                invalid = batch_snapshot()
                del invalid[key]
                with self.assertRaises(ValueError):
                    profile.validate_batch(invalid)
        for group, key in (('stop_reason', 'empty_tail'), ('stop_reason', 'owner_transfer'),
                           ('legacy', 'handoff')):
            with self.subTest(missing=(group, key)):
                invalid = batch_snapshot()
                del invalid[group][key]
                with self.assertRaises(ValueError):
                    profile.validate_batch(invalid)
            with self.subTest(extra=group):
                invalid = batch_snapshot()
                invalid[group]['unexpected'] = 0
                with self.assertRaises(ValueError):
                    profile.validate_batch(invalid)

    def test_counters_require_nonnegative_u64_integers(self):
        for keys in (('batches',), ('jit_local',), ('owner_transfers',), ('completed_hist', 1),
                     ('deferred_peak_hist', 1), ('stop_reason', 'empty_tail'),
                     ('legacy', 'combiner')):
            for value in (-1, 1.0, True, '1', None, 1 << 64):
                with self.subTest(path=keys, value=value):
                    invalid = batch_snapshot()
                    target = invalid
                    for key in keys[:-1]:
                        target = target[key]
                    target[keys[-1]] = value
                    with self.assertRaises(ValueError):
                        profile.validate_batch(invalid)

    def test_count_identities_and_batch_histogram_totals_are_checked(self):
        for keys in (('attempts',), ('jit_local',), ('native_completed',), ('owner_transfers',),
                     ('deferred_total',), ('legacy', 'combiner'), ('legacy', 'jit_success'),
                     ('legacy', 'handoff'), ('completed_hist', 0),
                     ('deferred_peak_hist', 0), ('stop_reason', 'empty_tail'),
                     ('stop_reason', 'owner_transfer')):
            with self.subTest(path=keys):
                invalid = batch_snapshot()
                target = invalid
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] += 1
                with self.assertRaises(ValueError):
                    profile.validate_batch(invalid)
        for key in ('small_fifo_batches', 'scan_exhausted_batches'):
            with self.subTest(path=key):
                invalid = batch_snapshot()
                invalid[key] = invalid['batches'] + 1
                with self.assertRaises(ValueError):
                    profile.validate_batch(invalid)
        invalid = batch_snapshot()
        invalid['stop_reason']['empty_tail'] = 0
        invalid['stop_reason']['unclassified'] = 1
        with self.assertRaises(ValueError):
            profile.validate_batch(invalid)

    def test_histogram_bounds_must_allow_reported_completions_and_deferrals(self):
        for histogram, source, destination in (('completed_hist', 4, 5),
                                                ('completed_hist', 4, 2),
                                                ('deferred_peak_hist', 4, 5)):
            with self.subTest(histogram=histogram, destination=destination):
                invalid = batch_snapshot()
                invalid[histogram][source] -= 1
                invalid[histogram][destination] += 1
                with self.assertRaises(ValueError):
                    profile.validate_batch(invalid)

    def test_deltas_reject_resets_including_individual_bins(self):
        with self.assertRaises(ValueError):
            profile.batch_delta(batch_snapshot(2), batch_snapshot())
        for histogram in ('completed_hist', 'deferred_peak_hist'):
            with self.subTest(histogram=histogram):
                before, after = batch_snapshot(), batch_snapshot(2)
                # The cumulative snapshot stays valid and total work grows,
                # but one histogram bucket has moved backward.
                after[histogram][0] += after[histogram][1]
                after[histogram][1] = 0
                profile.validate_batch(after)
                with self.assertRaises(ValueError):
                    profile.batch_delta(before, after)
        before, after = batch_snapshot(), batch_snapshot(2)
        after['stop_reason']['initial_unexecutable'] = 0
        after['stop_reason']['empty_tail'] += 2
        after['legacy']['handoff'] -= 2
        profile.validate_batch(after)
        with self.assertRaises(ValueError):
            profile.batch_delta(before, after)

    def test_deltas_reject_metadata_changes_and_completion_mismatch(self):
        before, after = batch_snapshot(), batch_snapshot(2)
        for key in BATCH_METADATA:
            with self.subTest(metadata=key):
                changed = deepcopy(after)
                changed[key] += 1
                with self.assertRaises(ValueError):
                    profile.batch_delta(before, changed)
        for expected in (9, 11, -1, True, 10.0):
            with self.subTest(expected_completions=expected):
                with self.assertRaises(ValueError):
                    profile.batch_delta(before, after, expected_completions=expected)
        invalid = deepcopy(before)
        invalid['attempts'] += 1
        with self.assertRaises(ValueError):
            profile.batch_delta(invalid, after)


if __name__ == '__main__':
    unittest.main()
