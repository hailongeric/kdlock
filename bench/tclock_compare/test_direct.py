"""Direct comparison matrix and result exclusion; no modules are loaded."""
from argparse import Namespace
import copy
import contextlib
import io
import sys
from unittest.mock import Mock, patch
import json
from pathlib import Path
import tempfile
import unittest

import run
from session import BackendSession, hash_layout, tc_quiescent, check_jit_evidence
from bench_session import Session
from context_audit import audit as audit_context


class DirectTests(unittest.TestCase):
    def test_numa_expanded_matrix(self):
        plan = run.make_plan(Namespace(cachelines=[1],
            threads=[1,2,3,4,5,6,7,8,12,16,20,24,28,32,36], repeats=3,
            iterations=100000, backends=['native','tclock','kdlock'],
            duration_ms=2000, collector_cpu=38, numa='on', kd_batch_size=128))
        self.assertEqual(len(plan), 135)
        for spec in plan:
            self.assertNotIn(38, spec['cpus'])
            if spec['arm'] == 'kdlock':
                self.assertEqual(spec['numa_policy'], 'on')
                self.assertEqual(spec['delegation_batch_limit'], 128)
            elif spec['arm'] == 'tclock':
                self.assertEqual(spec['delegation_batch_limit'], 1024)
        with self.assertRaises(run.Failure):
            run.make_plan(Namespace(cachelines=[1], threads=[36], repeats=1,
                iterations=100000, backends=['kdlock'], duration_ms=2000,
                collector_cpu=30))

    def test_timed_session_uses_fixed_warmup_and_continuous_measurement(self):
        session = BackendSession.__new__(BackendSession)
        spec, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['native'], duration_ms=2000))
        session.record = spec
        session.counts = Mock(return_value=dict(active=0))
        session.faults = Mock()
        session.run = Mock(return_value='{}')
        peak = dict(throughput_ops_s=1e6)
        with patch('bench_session.validate_measurement', side_effect=[None, peak]) as validate:
            session.phase('warmup', 48000)
            warmup = session.run.call_args.args[0]
            self.assertIn('--iterations', warmup)
            self.assertNotIn('--duration-ms', warmup)
            self.assertEqual(validate.call_args.args[1]['duration_ms'], 0)
            result = session.phase('measure', 100)
            measure = session.run.call_args.args[0]
            self.assertNotIn('--iterations', measure)
            self.assertIn('--duration-ms', measure)
            self.assertEqual(validate.call_args.args[1]['duration_ms'], 2000)
            self.assertEqual(result['peak'], peak)

    def test_timed_plan_and_peak_summary_keep_whole_run_visible(self):
        args = Namespace(cachelines=[1], threads=[3], repeats=2, iterations=100,
            backends=['native', 'tclock', 'kdlock'],
            duration_ms=2000)
        plan = run.make_plan(args)
        self.assertTrue(all(s['peak_window_ms'] == s['peak_settle_ms'] == 300 and
                            s['sample_ms'] == 10 and s['collector_cpu'] == 30 and
                            s['measurement_mode'] == 'timed_peak' for s in plan))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                # Winning peak and winning whole-run mean belong to different
                # rounds. Selection must keep the peak's matching whole rate.
                rate = (2 - spec['repeat']) * 1e6
                whole = (1 + spec['repeat']) * 0.5e6
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    measurement=dict(completed=whole * 2, wall_ns=2e9,
                        data_ok=True, complete=True,
                        peak=dict(throughput_ops_s=rate, amortized_ns_op=1e9/rate))))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            for row in rows:
                self.assertEqual(row['comparison_policy'], 'best_valid_warmed_peak')
                self.assertEqual(row['best_throughput_ops_s'], 2e6)
                self.assertEqual(row['best_whole_throughput_ops_s'], 0.5e6)
                self.assertEqual(row['best_amortized_ns_op'], 500)
                self.assertEqual(row['throughput_over_linux'], 1)
                self.assertEqual(row['min_throughput_ops_s'], 1e6)
        args.collector_cpu = 1
        with self.assertRaisesRegex(run.Failure, 'collector CPU'):
            run.make_plan(args)
        args.collector_cpu, args.duration_ms = 30, 600
        with self.assertRaisesRegex(run.Failure, 'timing intervals'):
            run.make_plan(args)

    def test_warmup_uses_all_workers_without_changing_preparation(self):
        cpus, nodes = [2, 7, 11], [0, 1, 0]
        warmup = dict(schema=1, complete=True, data_ok=True, workload='cacheline',
            cachelines=1, threads=3, iterations=48000, completed=144000,
            worker_cpu_ns=60, started_ns=100, finished_ns=300, wall_ns=200,
            before=[0]*16, after=[144000]+[0]*15,
            workers=[dict(cpu=cpu, observed_cpu=cpu, error=0, completed=48000,
                          cpu_ns=20, finished_ns=300) for cpu in cpus])

        def initialize(session, out, spec):
            # Substitute only module/device setup; retain BackendSession init.
            session.record = copy.deepcopy(spec)
            session.path = Path(out)/spec['name']
            session.workload_module = Path('/unused/spin_cacheline.ko')
            session.loaded_kd = session.loaded_source = False

        for arm in ('native', 'tclock', 'kdlock'):
            with self.subTest(arm=arm), patch.object(Session, '__init__', initialize):
                spec, = run.make_plan(Namespace(cachelines=[1], threads=[3],
                    repeats=1, iterations=17, backends=[arm],
                    pmu=True))
                spec.update(cpus=cpus, cpu_nodes=nodes)
                self.assertEqual((spec['warmup_policy'],
                                  spec['warmup_iterations_per_worker'],
                                  spec['warmup_pause_seconds']),
                                 ('all_workers', 48000, 0))
                session = BackendSession('/unused', spec)
                commands = []

                def command(args, log, **kwargs):
                    commands.append((args, log))
                    return json.dumps({'layout.json': {'lock_addr': 4096},
                                       'prepare.json': {}, 'warmup.json': warmup}.get(log, {}))

                session.counts = Mock(return_value=dict(active=0, values=[0]*16))
                session.faults = session.save = Mock()
                with patch.object(Session, 'run', side_effect=command), \
                        patch('session.time.sleep') as pause, \
                        patch('bench_session.validate_measurement',
                              wraps=run.runtime.validate_measurement) as validate:
                    if arm == 'native':
                        # Exercise the production 48,000-per-worker call and
                        # require separate preparation before worker warmup.
                        session.prepare()
                        labels = [label for _, label in commands]
                        self.assertLess(labels.index('prepare.json'), labels.index('warmup.json'))
                        preparation, = [args for args, label in commands if label == 'prepare.json']
                        self.assertEqual(preparation, [run.HERE/'client', '--prepare', '--cachelines', 1])
                        pause.assert_not_called()
                    else:
                        session.phase('warmup', 48000)
                args, = [args for args, label in commands if label == 'warmup.json']
                self.assertEqual(args[0], run.HERE/'client')  # No measured PMU wrapper.
                self.assertEqual(args[args.index('--cpus')+1], '2,7,11')
                self.assertEqual(args[args.index('--iterations')+1], 48000)
                actual, geometry, iterations = validate.call_args.args
                self.assertEqual((actual, iterations), (warmup, 48000))
                self.assertEqual((geometry['threads'], geometry['cpus'], geometry['cpu_nodes']),
                                 (3, cpus, nodes))
                self.assertNotIn('preparation_cpus', session.record)
                self.assertNotIn('measurement', session.record)
                self.assertNotIn('jit_before', session.record)

    def test_jit_measurement_starts_after_unmeasured_warmup(self):
        session = BackendSession.__new__(BackendSession)
        session.record = dict(arm='kdlock', threads=3, iterations=17,
                              hotlock_mode='adaptive', scenario='plain')
        session.loaded_kd = True
        session.save = Mock()
        events, counts = [], iter((700, 705))  # 700 bodies already returned in warmup.

        def counter():
            events.append('counter')
            return str(next(counts))

        def publication():
            events.append('publication')
            return {'source': {'writers': 0}}

        def phase(label, iterations):
            self.assertEqual((label, iterations), ('measure', 17))
            self.assertEqual(session.record['jit_before'], 700)
            events.append(label)
            return dict(completed=51)

        session.publication, session.phase = publication, phase
        with patch.object(Path, 'read_text', side_effect=counter):
            session.measure()
        self.assertEqual(events, ['publication', 'counter', 'measure', 'counter', 'publication'])
        self.assertEqual(session.record['jit_bodies'], 5)
        self.assertEqual(session.record['jit_share'], 5/51)
        self.assertEqual(session.record['measurement']['completed'], 51)

    def test_functional_report_has_no_performance_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'plan.json').write_text(json.dumps([
                dict(name='plain', scenario='plain', functional=True,
                     spin_entry_ratio_limit=4),
                dict(name='missing', scenario='early', functional=True),
                dict(name='historical', scenario='plain', functional=True,
                     spin_contention_pct=37)]))
            (out/'plain').mkdir()
            (out/'plain/session.json').write_text(json.dumps(dict(
                execution_status='PASS', drained=True, jit_bodies=9,
                jit_acceptance='PASS', measurement=dict(completed=10, wall_ns=100))))
            run.report(out)
            rows = json.loads((out/'functional.json').read_text())
            self.assertEqual(rows[0]['completed'], 10)
            self.assertEqual(rows[0]['spin_entry_ratio_limit'], 4)
            self.assertEqual(rows[0]['spin_contention_pct'], 'unrecorded')
            self.assertEqual(rows[1]['status'], 'NOT_RUN')
            self.assertFalse(rows[1]['drained'])
            self.assertEqual(rows[2]['spin_contention_pct'], 37)
            self.assertEqual(rows[2]['spin_entry_ratio_limit'], 'unrecorded')
            self.assertFalse((out/'summary.csv').exists())
            self.assertFalse((out/'summary.json').exists())
            self.assertFalse(any('throughput' in key or 'ns_op' in key for row in rows for key in row))

    def test_disabled_control_rejects_any_jit(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0,
                      hotlock_mode='adaptive', spin_delegate='off')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'DISABLED_CONTROL')
        with self.assertRaisesRegex(run.Failure, 'disabled control executed JIT'):
            check_jit_evidence(dict(record, jit_bodies=1))

    def test_policy_no_jit_is_not_protocol_acceptance(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0, hotlock_mode='adaptive')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')
        check_jit_evidence(record := dict(record, jit_bodies=1))
        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_single_thread_native_completion_is_not_jit_acceptance(self):
        record = dict(arm='kdlock', threads=1, jit_bodies=0,
            hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')

    def test_queue_depth_option_is_removed(self):
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--spin-hot-min-queue', '4']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                run.main()
        self.assertEqual(result.exception.code, 2)

    def test_shell_selection_option_is_removed(self):
        # Old commands must fail explicitly rather than silently select a
        # different caller from the one recorded in their original evidence.
        for choice in ('on', 'off'):
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                    '--spin-cold-fastpath', choice]
            with self.subTest(choice=choice), patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    run.main()
                self.assertEqual(result.exception.code, 2)

    def test_small_plain_native_completion_is_not_jit_acceptance(self):
        for threads in (2, 3):
            with self.subTest(threads=threads):
                record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                    hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain')
                check_jit_evidence(record)
                self.assertEqual(record['jit_acceptance'], 'NO_JIT_LOW_CONTENTION')
                check_jit_evidence(record := dict(record, jit_bodies=1))
                self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_nested_protocol_cases_still_require_jit(self):
        for threads in (2, 3, 4, 8, 20):
            for scenario in ('nested', 'early'):
                with self.subTest(threads=threads, scenario=scenario):
                    record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                        hotlock_mode='adaptive', caller_shell='cold_clobber',
                        spin_entry_ratio_limit=0, scenario=scenario)
                    with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                        check_jit_evidence(record)
                    check_jit_evidence(record := dict(record, jit_bodies=1))
                    self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_admission_mode_option_is_removed(self):
        # Old commands must not silently select a different admission contract.
        for choice in ('observe', 'adaptive'):
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                    '--hotlock-mode', choice]
            with self.subTest(choice=choice), patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    run.main()
            self.assertEqual(result.exception.code, 2)

    def test_high_contention_requires_jit(self):
        for threads in (20, 24, 28, 32, 36):
            record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain')
            with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                check_jit_evidence(record)
            check_jit_evidence(record := dict(record, jit_bodies=1))
            self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_contended_functional_plain_requires_jit(self):
        # Adaptive native completion is a valid performance result, but it
        # cannot satisfy an explicitly requested functional JIT positive.
        for threads in (2, 3, 4, 8, 16, 20):
            record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                          functional=True, scenario='plain')
            with self.subTest(threads=threads):
                with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                    check_jit_evidence(record)
                check_jit_evidence(record := dict(record, jit_bodies=1))
                self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_hash_layout_rejects_scheduling_enabled_module(self):
        layout = dict(workload='rcuht', buckets=1024, entries=4096,
                      key_range=8192, resched=0)
        hash_layout(layout)
        with self.assertRaisesRegex(run.Failure, 'hash payload configuration differs'):
            hash_layout(dict(layout, resched=1))

    def test_no_counter_quiescence_rejects_busy_or_old_provider(self):
        params = dict(target_lock=4096, komb_batch_size=1024, quiescent=1)
        tc_quiescent(params)
        for bad in (dict(params, quiescent=0), dict(params, delegated=0, completed=0)):
            with self.assertRaises(run.Failure):
                tc_quiescent(bad)

    def test_inline_audit_rejects_compiler_stack_prologue(self):
        # An extra compiler push invalidates the saved return-address offset
        # even though all six upstream register pushes still appear later.
        bad = '0000 <komb_context_switch>:\n 0: push %rbp\n 1: mov %rsp,%rbp\n'
        with self.assertRaisesRegex(ValueError, 'unexpected stack/register layout'):
            audit_context(bad)

    def test_hash_matrix_and_outcome_oracle(self):
        plan = run.make_plan(Namespace(workload='rcuht', cachelines=None,
            threads=[1, 4, 8, 16, 20], repeats=2, iterations=100000,
            backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 30)
        self.assertTrue(all(s['workload'] == 'rcuht' and s['cachelines'] == 0 for s in plan))
        spec = dict(workload='rcuht', cachelines=0, threads=1, cpus=[0])
        measurement = dict(schema=1, complete=True, data_ok=True, workload='rcuht',
            hash_integrity_ok=True, cachelines=0, threads=1, iterations=10,
            completed=10, worker_cpu_ns=100, started_ns=100, finished_ns=300,
            wall_ns=200, before=[3, 1, 1, 1] + [0]*12,
            after=[13, 4, 3, 6] + [0]*12,
            workers=[dict(cpu=0, observed_cpu=0, error=0, completed=10,
                          cpu_ns=100, finished_ns=300)])
        run.runtime.validate_measurement(measurement, spec, 10)
        # Lost/doubled outcomes and failed structure checks cannot be OK samples.
        for mutation in ('lost_outcome', 'extra_operation', 'bad_structure', 'wrong_payload'):
            broken = copy.deepcopy(measurement)
            if mutation == 'lost_outcome': broken['after'][1] -= 1
            if mutation == 'extra_operation': broken['after'][0] += 1
            if mutation == 'bad_structure': broken['hash_integrity_ok'] = False
            if mutation == 'wrong_payload': broken['workload'] = 'cacheline'
            with self.assertRaises(run.Failure):
                run.runtime.validate_measurement(broken, spec, 10)

    def test_cli_defaults_to_three_rounds(self):
        # Performance defaults to repeated measurements for both payloads;
        # explicit one-round performance and functional runs remain available.
        for extra, sessions, repeats in (
                ([], 90, 3), (['--workload', 'rcuht'], 45, 3),
                (['--repeats', '1'], 30, 1),
                (['--functional', '--backends', 'kdlock', '--repeats', '1'], 10, 1)):
            with self.subTest(args=extra):
                output = io.StringIO()
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run', *extra]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                    self.assertEqual(run.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(len(plan), sessions)
                self.assertEqual(len({s['name'] for s in plan}), sessions)
                self.assertEqual({s['repeat'] for s in plan}, set(range(repeats)))
                self.assertEqual({s['hotlock_mode'] for s in plan if s['arm'] == 'kdlock'},
                                 {'adaptive'})

    def test_functional_mode_requires_explicit_single_round(self):
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--functional', '--backends', 'kdlock']
        with patch.object(sys, 'argv', argv):
            with self.assertRaisesRegex(run.Failure, 'functional mode requires'):
                run.main()

    def test_cli_small_and_numa_thread_matrix(self):
        # Exercise parsing as well as placement: 36 workers leave CPU38 free.
        output = io.StringIO()
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--cachelines', '1', '--duration-ms', '2000', '--collector-cpu', '38',
                '--threads', '1', '2', '3', '4', '5', '6', '7', '8',
                '12', '16', '20', '24', '28', '32', '36']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
            self.assertEqual(run.main(), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(len(plan), 135)
        self.assertEqual(len({s['name'] for s in plan}), 135)
        self.assertEqual({s['threads'] for s in plan},
                         {1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36})
        self.assertEqual({s['repeat'] for s in plan}, {0, 1, 2})
        for spec in plan:
            self.assertEqual(spec['cpu_heat_policy'],
                             'mcs_reset1024_shift10_lock512_head6' if spec['arm'] == 'kdlock' else 'not_applicable')
            self.assertEqual(spec['spin_entry_ratio_limit'],
                             run.DEFAULT_SPIN_ENTRY_RATIO_LIMIT if spec['arm'] == 'kdlock' else None)
            self.assertNotIn('spin_contention_pct', spec)
            self.assertNotIn('spin_hot_min_queue', spec)
            self.assertNotIn('spin_cold_fastpath', spec)

    def test_contention_cli_preserves_explicit_threshold_and_zero_bypass(self):
        # A diagnostic zero must survive parsing;
        # non-KD baselines have no contention-policy setting.
        for threshold in (0, 2, 4, 1 << 31):
            with self.subTest(threshold=threshold):
                output = io.StringIO()
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                        '--cachelines', '1', '--threads', '4', '--repeats', '1',
                        '--spin-entry-ratio-limit', str(threshold)]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                    self.assertEqual(run.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(len(plan), 3)
                for spec in plan:
                    self.assertEqual(spec['spin_entry_ratio_limit'],
                                     threshold if spec['arm'] == 'kdlock' else None)

    def test_contention_threshold_rejects_out_of_range_and_non_integer(self):
        for threshold in ('-1', '1', '3', '4294967296', '2.5'):
            with self.subTest(threshold=threshold):
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                        '--spin-entry-ratio-limit', threshold]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as result:
                        run.main()
                self.assertEqual(result.exception.code, 2)
        for threshold in (-1, 1, 3, 1 << 32):
            with self.subTest(plan_threshold=threshold):
                with self.assertRaisesRegex(run.Failure, 'invalid spin entry ratio limit'):
                    run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
                        iterations=100, backends=['kdlock'], spin_entry_ratio_limit=threshold))

    def test_percentage_option_is_removed(self):
        # The new inverse ratio must not silently reinterpret an old percent.
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--spin-contention-pct', '100']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                run.main()
        self.assertEqual(result.exception.code, 2)

    def test_empty_summary_has_no_winner(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            run.report(out)
            for row in json.loads((out/'summary.json').read_text()):
                self.assertEqual(row['valid'], 0)
                for key in ('best_session', 'best_throughput_ops_s',
                            'best_amortized_ns_op', 'throughput_over_linux',
                            'min_throughput_ops_s', 'median_throughput_ops_s',
                            'max_throughput_ops_s', 'throughput_spread_pct'):
                    self.assertIsNone(row[key])

    def test_matrix_and_alternating_order(self):
        plan = run.make_plan(Namespace(cachelines=[1, 16], threads=[1, 4, 8, 16, 20],
            repeats=3, iterations=100000, backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 90)
        self.assertEqual([(s['arm'], s['hotlock_mode']) for s in plan[:9]],
                         [('native', 'not_applicable'), ('tclock', 'not_applicable'),
                          ('kdlock', 'adaptive'), ('kdlock', 'adaptive'),
                          ('tclock', 'not_applicable'), ('native', 'not_applicable'),
                          ('native', 'not_applicable'), ('tclock', 'not_applicable'),
                          ('kdlock', 'adaptive')])
        self.assertTrue(all(s['api_mode'] == 'direct' for s in plan))

    def test_summary_excludes_bad_and_undrained_samples(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=3,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                # Vary rates between rounds; reject the fastest corrupt/undrained rows.
                bad = spec['repeat'] == 2 and spec['arm'] != 'native'
                rate = {'native': 1, 'tclock': 2, 'kdlock': 4}[spec['arm']] * (spec['repeat'] + 1)
                record = dict(spec, execution_status='OK', drained=not (bad and spec['arm'] == 'kdlock'),
                    measurement=dict(completed=400, wall_ns=1 if bad else 400000/rate,
                                     data_ok=not (bad and spec['arm'] == 'tclock'), complete=True))
                run.write_json(folder/'session.json', record)
            run.report(out)
            rows = {r['arm']: r for r in json.loads((out/'summary.json').read_text())}
            for arm, rate, repeat in [('native', 3, 2), ('tclock', 4, 1), ('kdlock', 8, 1)]:
                self.assertEqual(rows[arm]['throughput_over_linux'], rate / 3)
                self.assertEqual(rows[arm]['valid'], 3 if arm == 'native' else 2)
                self.assertEqual(rows[arm]['best_throughput_ops_s'], rate * 1e6)
                self.assertAlmostEqual(rows[arm]['best_amortized_ns_op'], 1000 / rate)
                winner = next(s['name'] for s in plan if s['arm'] == arm and s['repeat'] == repeat)
                self.assertEqual(rows[arm]['best_session'], winner)
                self.assertEqual(rows[arm]['comparison_policy'], 'best_valid_throughput')
                minimum, median = {'native': (1, 2), 'tclock': (2, 3),
                                   'kdlock': (4, 6)}[arm]
                self.assertEqual(rows[arm]['sessions'], 3)
                self.assertEqual(rows[arm]['min_throughput_ops_s'], minimum * 1e6)
                self.assertEqual(rows[arm]['median_throughput_ops_s'], median * 1e6)
                self.assertEqual(rows[arm]['max_throughput_ops_s'], rate * 1e6)
                self.assertAlmostEqual(rows[arm]['throughput_spread_pct'],
                                       (rate - minimum) / median * 100)
            self.assertEqual(len(json.loads((out/'records.json').read_text())), 9)

    def test_summary_preserves_historical_admission_identity(self):
        # Reporting old frozen records must not merge their admission modes.
        # The live planner below creates adaptive sessions only.
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        plan += [dict(spec, name=spec['name'].replace('-adaptive', '-observe'),
                      hotlock_mode='observe') for spec in plan if spec['arm'] == 'kdlock']
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                mode = spec['hotlock_mode']
                rate = {'not_applicable': 1, 'observe': 2, 'adaptive': 4}[mode]
                bad = mode == 'adaptive' and spec['repeat'] == 1
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=not bad,
                    measurement=dict(completed=400, wall_ns=1 if bad else 400000/rate,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = {(r['arm'], r['hotlock_mode']): r
                    for r in json.loads((out/'summary.json').read_text())}
            self.assertEqual(len(rows), 4)
            for mode, rate, count in [('observe', 2, 2), ('adaptive', 4, 1)]:
                row = rows['kdlock', mode]
                self.assertEqual(row['sessions'], 2)
                self.assertEqual(row['valid'], count)
                self.assertEqual(row['best_throughput_ops_s'], rate * 1e6)
                self.assertEqual(row['throughput_over_linux'], rate)
                self.assertTrue(row['best_session'].endswith('-' + mode))
            self.assertEqual(rows['native', 'not_applicable']['sessions'], 2)
            self.assertEqual(rows['tclock', 'not_applicable']['sessions'], 2)

    def test_default_heat_caller_uses_one_adaptive_session(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[1], repeats=1,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 3)
        self.assertEqual(len({s['name'] for s in plan}), 3)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    measurement=dict(completed=100, wall_ns=100000,
                                     data_ok=True, complete=True)))
                if spec['arm'] == 'kdlock':
                    self.assertEqual(spec['caller_abi'], 'clobber')
                    self.assertEqual(spec['caller_shell'], 'cold_clobber')
                    self.assertEqual(spec['cookie_storage'], 'percpu_direct_gate')
                    self.assertEqual(spec['delegation_batch_limit'], 512)
                    self.assertNotIn('spin_cold_fastpath', spec)
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 3)
            self.assertEqual({r['hotlock_mode'] for r in rows if r['arm'] == 'kdlock'},
                             {'adaptive'})
            self.assertTrue(all('spin_cold_fastpath' not in r for r in rows))
            self.assertTrue(all(r['sessions'] == r['valid'] == 1 for r in rows))
            self.assertTrue(all(r['min_throughput_ops_s'] == r['median_throughput_ops_s'] ==
                                r['max_throughput_ops_s'] == r['best_throughput_ops_s']
                                for r in rows))
            self.assertTrue(all(r['throughput_spread_pct'] is None for r in rows))
            self.assertEqual({r['cookie_storage'] for r in rows}, {'percpu_direct_gate', 'not_applicable'})

    def test_summary_keeps_gate_storage_separate(self):
        # An old indirect-gate archive must not supply the winner for the new
        # direct scalar even when admission and workload settings match.
        base = run.make_plan(Namespace(cachelines=[1], threads=[1], repeats=1,
            iterations=100, backends=['kdlock']))[0]
        plans = [dict(base, name=base['name']+'-'+storage, cookie_storage=storage)
                 for storage in ('percpu_rate_hot', 'percpu_direct_gate')]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for index, spec in enumerate(plans):
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    measurement=dict(completed=100, wall_ns=100000*(index+1),
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = {r['cookie_storage']: r
                    for r in json.loads((out/'summary.json').read_text())}
            self.assertEqual(set(rows), {'percpu_rate_hot', 'percpu_direct_gate'})
            for index, spec in enumerate(plans):
                row = rows[spec['cookie_storage']]
                self.assertEqual(row['valid'], 1)
                self.assertEqual(row['best_session'], spec['name'])
                self.assertEqual(row['best_throughput_ops_s'], 1e6/(index+1))

    def test_summary_keeps_heat_policies_separate(self):
        base = run.make_plan(Namespace(cachelines=[1], threads=[2], repeats=1,
            iterations=100, backends=['kdlock']))[0]
        # Keep each resettable cadence separate from percentage samplers and
        # older native-head policies, even when their ratio cutoffs match.
        plans = [dict(base, name=base['name']+'-'+policy, cpu_heat_policy=policy)
                 for policy in ('mcs_reset1024_shift10_lock512_head6', 'mcs_reset_shift9_head6', 'mcs_entry_ratio512_head6', 'mcs_entry_ratio512_head5', 'mcs_entry_ratio512_simple', 'mcs_entry_ratio512_batch128', 'mcs_entry_ratio512_confirm2', 'mcs_entry_ratio512', 'mcs_entry_ratio',
                                'mcs_entry', 'historical_queue_depth')]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    jit_bodies=int(spec['cpu_heat_policy'] == 'mcs_reset1024_shift10_lock512_head6'),
                    measurement=dict(completed=200, wall_ns=100000,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 11)
            self.assertEqual({r['cpu_heat_policy'] for r in rows},
                             {'mcs_reset1024_shift10_lock512_head6', 'mcs_reset_shift9_head6', 'mcs_entry_ratio512_head6', 'mcs_entry_ratio512_head5', 'mcs_entry_ratio512_simple', 'mcs_entry_ratio512_batch128', 'mcs_entry_ratio512_confirm2', 'mcs_entry_ratio512', 'mcs_entry_ratio',
                              'mcs_entry', 'historical_queue_depth'})
            self.assertEqual(sum(r['actual_jit_sessions'] for r in rows), 1)

    def test_summary_keeps_contention_thresholds_separate(self):
        # Historical percentages and current limits each remain independent
        # tuning inputs, including zero's bypass in either unit.
        plans = []
        rates = {('spin_entry_ratio_limit', 0): 1,
                 ('spin_entry_ratio_limit', 2): 2,
                 ('spin_entry_ratio_limit', 4): 4,
                 ('spin_contention_pct', 0): 8,
                 ('spin_contention_pct', 37): 16,
                 ('spin_contention_pct', 100): 32}
        for field, threshold in rates:
            candidate = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
                iterations=100, backends=['kdlock']))
            for spec in candidate:
                if field == 'spin_contention_pct':
                    del spec['spin_entry_ratio_limit']
                    spec['cpu_heat_policy'] = 'mcs_entry_ratio512_head6'
                spec[field] = threshold
                spec['name'] += f'-{field}-{threshold}'
                plans.append(spec)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                field = ('spin_contention_pct' if 'spin_contention_pct' in spec
                         else 'spin_entry_ratio_limit')
                rate = rates[field, spec[field]] * (spec['repeat'] + 1)
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True, jit_bodies=1,
                    measurement=dict(completed=400, wall_ns=400000/rate,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), len(rates))
            self.assertEqual({row['hotlock_mode'] for row in rows}, {'adaptive'})
            observed = set()
            for row in rows:
                field = ('spin_contention_pct' if row['spin_contention_pct'] != 'unrecorded'
                         else 'spin_entry_ratio_limit')
                threshold = row[field]
                observed.add((field, threshold))
                self.assertEqual(row['sessions'], 2)
                self.assertEqual(row['valid'], 2)
                self.assertEqual(row['best_throughput_ops_s'], rates[field, threshold] * 2e6)
                self.assertEqual(row['best_amortized_ns_op'], 500 / rates[field, threshold])
                self.assertTrue(row['best_session'].endswith(f'-{field}-{threshold}'))
            self.assertEqual(observed, set(rates))

    def test_provider_load_has_no_admission_mode_parameter(self):
        session = BackendSession.__new__(BackendSession)
        session.record = dict(arm='kdlock', hotlock_mode='adaptive',
                              spin_entry_ratio_limit=4, spin_delegate='on', spin_prefetch=0)
        commands = []

        def command(args, log):
            commands.append((args, log))
            if log == 'load-kdlock.log':
                raise RuntimeError('stop after provider command')

        session.run = command
        with self.assertRaisesRegex(RuntimeError, 'stop after provider command'):
            session.prepare()
        args, = [args for args, log in commands if log == 'load-kdlock.log']
        self.assertFalse(any(str(arg).startswith('hotlock_mode=') for arg in args))
        self.assertFalse(any(str(arg).startswith('spin_contention_pct=') for arg in args))
        self.assertIn('spin_entry_ratio_limit=4', args)
        self.assertIn('spin_delegate=1', args)
        self.assertIn('spin_prefetch=0', args)


if __name__ == '__main__':
    unittest.main()
