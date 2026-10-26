"""Focused VM-only checks for diagnostic scope, accounting and timeout ownership."""
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
            runner = types.SimpleNamespace(valid=lambda r: True, list_execution_class=lambda r: 'RETURNED_JIT')
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

    def test_default_profile_matrix_preserves_body_and_post_work(self):
        args = profile.parser().parse_args(['--mode', 'stat', '--output', '/tmp/new-profile',
                                           '--source-commit', 'a' * 40])
        self.assertEqual(args.threads, [16, 36, 60])
        self.assertEqual(args.backends, ['native', 'kdlock'])
        for name, post in [('mutex', '4'), ('mutex-locality', '64')]:
            argv = profile.runner_arguments(args, name)
            self.assertEqual(argv[argv.index('--post-work-rounds') + 1], post)
            self.assertEqual(argv[argv.index('--repeats') + 1], '1')
            self.assertEqual(argv[argv.index('--write-percent') + 1], '100')


if __name__ == '__main__':
    unittest.main()
