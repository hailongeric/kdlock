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

    def test_cli_defaults_to_one_round(self):
        # Exercise the CLI default for both payloads and functional admission;
        # a second measurement must be an explicit choice, not an implicit run.
        for extra, sessions in (([], 40), (['--workload', 'rcuht'], 20),
                                (['--functional', '--backends', 'kdlock'], 20),
                                (['--hotlock-mode', 'adaptive'], 30),
                                (['--hotlock-mode', 'observe'], 30)):
            with self.subTest(args=extra):
                output = io.StringIO()
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run', *extra]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                    self.assertEqual(run.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(len(plan), sessions)
                self.assertEqual(len({s['name'] for s in plan}), sessions)
                self.assertEqual({s['repeat'] for s in plan}, {0})
                expected_modes = {extra[-1]} if '--hotlock-mode' in extra else {'observe', 'adaptive'}
                self.assertEqual({s['hotlock_mode'] for s in plan if s['arm'] == 'kdlock'},
                                 expected_modes)

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
                            'best_amortized_ns_op', 'throughput_over_linux'):
                    self.assertIsNone(row[key])

    def test_matrix_and_alternating_order(self):
        plan = run.make_plan(Namespace(cachelines=[1, 16], threads=[1, 4, 8, 16, 20],
            repeats=2, iterations=100000, backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 80)
        self.assertEqual([(s['arm'], s['hotlock_mode']) for s in plan[:8]],
                         [('native', 'not_applicable'), ('tclock', 'not_applicable'),
                          ('kdlock', 'observe'), ('kdlock', 'adaptive'),
                          ('kdlock', 'adaptive'), ('kdlock', 'observe'),
                          ('tclock', 'not_applicable'), ('native', 'not_applicable')])
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
                self.assertFalse(any(k.startswith('median_') for k in rows[arm]))
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
                                     'paired' if spec['spin_cold_fastpath']=='on' else 'clobber')
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(r['sessions'] == r['valid'] == 1 for r in rows))


if __name__ == '__main__':
    unittest.main()
