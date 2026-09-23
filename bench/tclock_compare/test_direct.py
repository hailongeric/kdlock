"""Direct comparison matrix and result exclusion; no modules are loaded."""
from argparse import Namespace
import copy
import contextlib
import io
import sys
from unittest.mock import patch
import json
from pathlib import Path
import tempfile
import unittest

import run
from session import hash_layout, tc_quiescent, check_jit_evidence
from context_audit import audit as audit_context


class DirectTests(unittest.TestCase):
    def test_functional_report_has_no_performance_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'plan.json').write_text(json.dumps([
                dict(name='plain', scenario='plain', functional=True),
                dict(name='missing', scenario='early', functional=True)]))
            (out/'plain').mkdir()
            (out/'plain/session.json').write_text(json.dumps(dict(
                execution_status='PASS', drained=True, jit_bodies=9,
                jit_acceptance='PASS', measurement=dict(completed=10, wall_ns=100))))
            run.report(out)
            rows = json.loads((out/'functional.json').read_text())
            self.assertEqual(rows[0]['completed'], 10)
            self.assertEqual(rows[1]['status'], 'NOT_RUN')
            self.assertFalse(rows[1]['drained'])
            self.assertFalse((out/'summary.csv').exists())
            self.assertFalse((out/'summary.json').exists())
            self.assertFalse(any('throughput' in key or 'ns_op' in key for row in rows for key in row))

    def test_disabled_control_rejects_any_jit(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0,
                      hotlock_mode='observe', spin_delegate='off')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'DISABLED_CONTROL')
        with self.assertRaisesRegex(run.Failure, 'disabled control executed JIT'):
            check_jit_evidence(dict(record, jit_bodies=1))

    def test_policy_no_jit_is_not_protocol_acceptance(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0, hotlock_mode='observe')
        with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
            check_jit_evidence(record)
        check_jit_evidence(record := dict(record, hotlock_mode='adaptive'))
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')
        check_jit_evidence(record := dict(record, jit_bodies=1))
        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_small_cold_queue_policy_requires_native_execution(self):
        for threads in (1, 2, 3):
            for mode in ('observe', 'adaptive'):
                record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                    hotlock_mode=mode, caller_shell='cold_clobber',
                    spin_cold_fastpath='on', spin_hot_min_queue=4, scenario='plain')
                check_jit_evidence(record)
                self.assertEqual(record['jit_acceptance'], 'NO_JIT_COLD')
                with self.assertRaisesRegex(run.Failure, 'unexpectedly executed JIT'):
                    check_jit_evidence(dict(record, jit_bodies=1))

    def test_cold_queue_policy_does_not_relax_protocol_positives(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0,
            hotlock_mode='observe', caller_shell='cold_clobber',
            spin_cold_fastpath='on', spin_hot_min_queue=4, scenario='plain')
        # Original MCS mode, high contention and nested
        # protocol cases must retain actual-body evidence for observe.
        for change in (dict(spin_hot_min_queue=0), dict(threads=20),
                       dict(spin_cold_fastpath='off'), dict(caller_shell='paired'),
                       dict(scenario='nested'), dict(scenario='early')):
            with self.subTest(change=change):
                with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                    check_jit_evidence(dict(record, **change))
        check_jit_evidence(record := dict(record, spin_delegate='off'))
        self.assertEqual(record['jit_acceptance'], 'DISABLED_CONTROL')

    def test_small_plain_native_completion_is_not_jit_acceptance(self):
        for threads in (2, 3):
            for mode in ('observe', 'adaptive'):
                for cold, shell in (('off', 'clobber'), ('on', 'cold_clobber')):
                    with self.subTest(threads=threads, mode=mode, cold=cold):
                        record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                            hotlock_mode=mode, caller_shell=shell, scenario='plain',
                            spin_cold_fastpath=cold, spin_hot_min_queue=0)
                        check_jit_evidence(record)
                        self.assertEqual(record['jit_acceptance'], 'NO_JIT_LOW_CONTENTION')
                        check_jit_evidence(record := dict(record, jit_bodies=1))
                        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_small_nested_protocol_cases_still_require_jit(self):
        for threads in (2, 3):
            for mode in ('observe', 'adaptive'):
                for scenario in ('nested', 'early'):
                    with self.subTest(threads=threads, mode=mode, scenario=scenario):
                        record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                            hotlock_mode=mode, caller_shell='cold_clobber',
                            scenario=scenario, spin_cold_fastpath='on', spin_hot_min_queue=4)
                        with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                            check_jit_evidence(record)
                        check_jit_evidence(record := dict(record, jit_bodies=1))
                        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_four_workers_do_not_guarantee_queue_pressure(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0,
            hotlock_mode='observe', caller_shell='cold_clobber',
            spin_cold_fastpath='on', spin_hot_min_queue=4, scenario='plain')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT_POLICY')
        check_jit_evidence(record := dict(record, jit_bodies=1))
        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_high_contention_requires_jit_in_both_policies(self):
        for mode in ('observe', 'adaptive'):
            record = dict(arm='kdlock', threads=20, jit_bodies=0,
                hotlock_mode=mode, caller_shell='cold_clobber',
                spin_cold_fastpath='on', spin_hot_min_queue=4, scenario='plain')
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
        self.assertEqual(len(plan), 40)
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
                ([], 120, 3), (['--workload', 'rcuht'], 60, 3),
                (['--hotlock-mode', 'adaptive'], 90, 3),
                (['--hotlock-mode', 'observe'], 90, 3),
                (['--repeats', '1'], 40, 1),
                (['--functional', '--backends', 'kdlock', '--repeats', '1'], 20, 1)):
            with self.subTest(args=extra):
                output = io.StringIO()
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run', *extra]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                    self.assertEqual(run.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(len(plan), sessions)
                self.assertEqual(len({s['name'] for s in plan}), sessions)
                self.assertEqual({s['repeat'] for s in plan}, set(range(repeats)))
                expected_modes = {extra[-1]} if '--hotlock-mode' in extra else {'observe', 'adaptive'}
                self.assertEqual({s['hotlock_mode'] for s in plan if s['arm'] == 'kdlock'},
                                 expected_modes)

    def test_functional_mode_requires_explicit_single_round(self):
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--functional', '--backends', 'kdlock']
        with patch.object(sys, 'argv', argv):
            with self.assertRaisesRegex(run.Failure, 'functional mode requires'):
                run.main()

    def test_cli_small_thread_cold_matrix(self):
        output = io.StringIO()
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--threads', '1', '2', '3', '4', '20',
                '--spin-cold-fastpath', 'on', 'off', '--spin-hot-min-queue', '4']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
            self.assertEqual(run.main(), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(len(plan), 180)
        self.assertEqual(len({s['name'] for s in plan}), 180)
        self.assertEqual({s['threads'] for s in plan}, {1, 2, 3, 4, 20})
        self.assertEqual({s['repeat'] for s in plan}, {0, 1, 2})
        for spec in plan:
            queue = (4 if spec['spin_cold_fastpath'] == 'on' else 0)
            self.assertEqual(spec['spin_hot_min_queue'],
                             queue if spec['arm'] == 'kdlock' else 'not_applicable')

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
        self.assertEqual(len(plan), 120)
        self.assertEqual([(s['arm'], s['hotlock_mode']) for s in plan[:12]],
                         [('native', 'not_applicable'), ('tclock', 'not_applicable'),
                          ('kdlock', 'observe'), ('kdlock', 'adaptive'),
                          ('kdlock', 'adaptive'), ('kdlock', 'observe'),
                          ('tclock', 'not_applicable'), ('native', 'not_applicable'),
                          ('native', 'not_applicable'), ('tclock', 'not_applicable'),
                          ('kdlock', 'observe'), ('kdlock', 'adaptive')])
        self.assertTrue(all(s['api_mode'] == 'direct' for s in plan))

    def test_summary_excludes_bad_and_undrained_samples(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=3,
            iterations=100, backends=['native', 'tclock', 'kdlock'], hotlock_mode=['observe']))
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

    def test_summary_keeps_admission_modes_separate(self):
        # A faster adaptive run must not replace observe or duplicate baselines.
        # An undrained adaptive repeat must not win either policy's result.
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
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

    def test_cold_option_builds_and_reports_distinct_callers(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[1], repeats=1,
            iterations=100, backends=['native', 'tclock', 'kdlock'],
            spin_cold_fastpath=['on', 'off']))
        self.assertEqual(len(plan), 6)
        self.assertEqual(len({s['name'] for s in plan}), 6)
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
                    self.assertEqual(spec['caller_shell'],
                                     'cold_clobber' if spec['spin_cold_fastpath']=='on' else 'clobber')
                    self.assertEqual(spec['cookie_storage'],
                                     'percpu_rate_hot' if spec['spin_cold_fastpath']=='on' else 'not_applicable')
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(r['sessions'] == r['valid'] == 1 for r in rows))
            self.assertTrue(all(r['min_throughput_ops_s'] == r['median_throughput_ops_s'] ==
                                r['max_throughput_ops_s'] == r['best_throughput_ops_s']
                                for r in rows))
            self.assertTrue(all(r['throughput_spread_pct'] is None for r in rows))
            self.assertEqual({r['cookie_storage'] for r in rows}, {'percpu_rate_hot', 'not_applicable'})

    def test_summary_keeps_cold_queue_thresholds_separate(self):
        plans = [run.make_plan(Namespace(cachelines=[1], threads=[2], repeats=1,
            iterations=100, backends=['kdlock'], hotlock_mode=['observe'],
            spin_cold_fastpath=['on'], spin_hot_min_queue=queue))[0]
            for queue in (0, 4)]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    jit_bodies=int(spec['spin_hot_min_queue'] == 0),
                    measurement=dict(completed=200, wall_ns=100000,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 2)
            self.assertEqual({r['spin_hot_min_queue'] for r in rows}, {0, 4})
            self.assertEqual(sum(r['actual_jit_sessions'] for r in rows), 1)


if __name__ == '__main__':
    unittest.main()
