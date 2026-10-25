"""Offline scaling receipts; never launch a workload, observer or transport."""
import argparse
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import statistics
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/mmap_lock'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired
import report
import test_mmap_paired as legacy

PLAN = 'plain-scaling-v1'
COUNTS = [1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60]
ARMS = [(0, 'kd', 1), (0, 'native', 2), (1, 'native', 2),
        (1, 'kd', 3), (2, 'kd', 3), (2, 'native', 4)]
ORDER = [(repeat, mode, case) for repeat, mode, _ in ARMS for case in range(21)]


def bindings():
    return {key: dict(path='/fixture/' + str(i), sha256=hashlib.sha256(str(key).encode()).hexdigest())
            for i, key in enumerate(ORDER)}


def rows():
    refs = bindings()
    result = []
    for index, (repeat, mode, case) in enumerate(ORDER):
        block = next(b for r, m, b in ARMS if (r, m) == (repeat, mode))
        result.append(dict(plan=PLAN, passed=True, drained=True, accepted=True, endpoint_checked=True,
            prepared=dict(path='fixture', sha256='same'), repeat=repeat, mode=mode, case=case,
            block=block, boot_id='boot-' + str(block), ready=dict(path='ready-' + str(block), sha256='same'),
            previous=refs[ORDER[index-1]] if index else None,
            spec=paired.specification(case, repeat, mode, PLAN),
            measurement=dict(whole_ops_s=(100 if mode == 'native' else 90) + repeat,
                             latency_samples=0, latency_percentiles_ns={})))
    return result


def validation(mode='kd'):
    value = legacy.Validation().fixture()
    value.update(plan=PLAN, mode=mode,
                 cases=[dict(spec=paired.specification(i, 0, mode, PLAN)) for i in range(21)])
    value['fixed']['protocol'] = 'KD_LOCAL_MMAP_LOCK' if mode == 'kd' else 'NATIVE_CONTROL_MMAP_LOCK'
    return value


class ScalingPlan(unittest.TestCase):
    def setUp(self):
        for target in ('subprocess.Popen', 'socket.socket'):
            guard = patch(target, side_effect=AssertionError('live action forbidden'))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch.object(paired.rt, 'command', side_effect=AssertionError('real command forbidden'))
        guard.start()
        self.addCleanup(guard.stop)

    def test_exact_grid_order_bounds_and_placement(self):
        self.assertEqual(paired.cases_for(PLAN), [(n, 'plain') for n in COUNTS])
        self.assertEqual(paired.order_for(PLAN), ORDER)
        self.assertEqual(paired.bounds(PLAN), dict(measured_sessions=126, unscored_checks=44,
                         payload_cycles=170, boots=6, host_captures=259))
        for case, n in enumerate(COUNTS):
            spec = paired.specification(case, 0, 'kd', PLAN)
            self.assertEqual(spec['threads'], n)
            self.assertEqual(spec['cpus'], list(range(n)))
            self.assertEqual(spec['sample_ms'], 10)  # Progress remains enabled.
            self.assertEqual(spec['duration_ms'], 2000)
            self.assertEqual(spec['observation'], 'plain')
            self.assertNotIn(63, spec['cpus'])
        self.assertNotIn(64, COUNTS)
        for case in (-1, 21):
            with self.assertRaises(paired.rt.Failure):
                paired.specification(case, 0, 'kd', PLAN)

    def test_estimates_include_saved_replays_logs_and_retained_copies(self):
        plan = paired.describe_plan(PLAN)
        self.assertEqual(plan['worker_counts'], COUNTS)
        self.assertEqual(plan['order'], ORDER)
        self.assertEqual(plan['checks'], dict(fixed=2, timed_validation=42, warmups=0,
            fixed_worker_cycles=160000, negative_receipt_mutations=18, dmesg_dumps=639,
            runtime_saved_timed_replays=5292, runtime_saved_fixed_replays=252,
            report_saved_timed_replays=5292, report_saved_fixed_replays=252))
        self.assertEqual(plan['time']['components_ms']['measured_intervals_ms'], 252000)
        self.assertEqual(plan['time']['components_ms']['validation_intervals_ms'], 84000)
        self.assertEqual(plan['time']['components_ms']['client_start_delays_ms'], 16800)
        self.assertEqual(plan['time']['estimated_ms'], 2676800)
        self.assertEqual(plan['storage']['one_copy_bytes'], int(786.75 * 1024**2))
        self.assertEqual(plan['storage']['reserve_bytes'], int(1966.875 * 1024**2))
        self.assertEqual(plan['storage']['rounded_gib_bytes'], 2 * 1024**3)
        self.assertEqual(plan['placement']['collector_cpu'], 63)
        self.assertFalse(plan['placement']['collector_shared'])

    def test_planning_assumptions_are_explicit_and_change_estimate_only(self):
        original = paired.describe_plan(PLAN)
        assumptions = dict(paired.PLANNING_ASSUMPTIONS)
        assumptions['boot_ms'] += 1000
        revised = paired.describe_plan(PLAN, assumptions)
        self.assertEqual(revised['time']['estimated_ms'] - original['time']['estimated_ms'], 6000)
        self.assertEqual(revised['limits'], original['limits'])
        self.assertEqual(paired.describe_plan(PLAN), original)
        for key, value in [('boot_ms', -1), ('boot_ms', True), ('retained_copies', 0), ('extra', 1)]:
            bad = dict(assumptions, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(paired.rt.Failure):
                paired.describe_plan(PLAN, bad)
        with self.assertRaises(paired.rt.Failure):
            paired.describe_plan(PLAN, {})

    def test_cli_describe_is_explicit_and_stdout_only(self):
        with patch.object(sys, 'argv', ['paired.py', 'describe', '--plan', PLAN]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            paired.main()
        self.assertEqual(json.loads(output.getvalue())['limits']['measured_sessions'], 126)
        for args in [[], ['--plan', paired.LEGACY_PLAN], ['--plan', PLAN, '--output', '/fixture']]:
            with patch.object(sys, 'argv', ['paired.py', 'describe', *args]), \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                paired.main()
            self.assertEqual(error.exception.code, 2)

    def test_cli_case20_parses_and_case21_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for case in (20, 21):
                args = ['paired.py', 'run', '--case', str(case), '--output', str(Path(tmp) / 'new')]
                with patch.object(sys, 'argv', args), patch.object(paired, 'run') as run, \
                     contextlib.redirect_stderr(io.StringIO()):
                    if case == 20:
                        paired.main()
                        self.assertEqual(run.call_args.args[0].case, 20)
                    else:
                        with self.assertRaises(SystemExit) as error:
                            paired.main()
                        self.assertEqual(error.exception.code, 2)
                        run.assert_not_called()

    def test_run_inherits_case20_and_checks_both_validation_plans(self):
        for plan in (PLAN, paired.THROUGHPUT_PLAN, paired.LEGACY_PLAN):
            with self.subTest(plan=plan), tempfile.TemporaryDirectory() as tmp:
                ready = dict(plan=plan, mode='kd', boot_id='boot', block=1, prepared={})
                prior = dict(plan=plan, passed=True, drained=True, accepted=True,
                             repeat=0, mode='kd', case=19, block=1, boot_id='boot', prepared={},
                             endpoint_captured_utc='2026-10-26T00:00:00')
                args = argparse.Namespace(ready=Path('/ready'), output=Path(tmp) / 'run', repeat=0,
                    case=20, previous=Path('/previous'), native_validation=Path('/native-validation'),
                    kd_validation=Path('/kd-validation'), host_state=Path('/host'))
                with patch.object(paired, 'readiness', return_value=(ready, {})), \
                     patch.object(paired, 'bind', return_value={}), \
                     patch.object(paired.common, 'load', side_effect=[prior, {'captured_utc': '2026-10-26T00:01:00'}]), \
                     patch.object(paired, 'validation_receipt') as validate, \
                     patch.object(paired, 'host_check'), patch.object(paired, 'environment', return_value=({}, {})), \
                     patch.object(paired, 'host_environment', return_value={}), patch.object(paired, 'fault_check'), \
                     patch.object(paired.shutil, 'copyfile'), patch.object(paired, 'timed') as timed:
                    if plan == PLAN:
                        paired.run(args)
                        self.assertEqual(timed.call_args.args[2]['threads'], 60)
                        self.assertEqual([(c.args[1], c.args[-1]) for c in validate.call_args_list],
                                         [('native', PLAN), ('kd', PLAN)])
                        receipt = json.loads((args.output / 'client-result.json').read_text())
                        self.assertTrue(receipt['client_exited'])
                        self.assertFalse(receipt['passed'] or receipt['accepted'] or receipt['drained'])
                    else:
                        with self.assertRaises(paired.rt.Failure):
                            paired.run(args)
                        timed.assert_not_called()
                        validate.assert_not_called()

    def test_validate_executes_fixed_proof_and_all_counts_for_each_backend(self):
        for mode in ('native', 'kd'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'validation'
                ready = dict(plan=PLAN, mode=mode, prepared={})
                with patch.object(paired, 'readiness', return_value=(ready, dict(files={}))), \
                     patch.object(paired, 'bind', return_value={}), \
                     patch.object(paired, 'fixed', return_value=validation(mode)['fixed']) as fixed, \
                     patch.object(paired, 'timed') as timed, \
                     patch.object(paired, 'business_finish', return_value=({}, 'exact drain')) as finish, \
                     patch.object(paired.common, 'verify_maps'), patch.object(paired.writer.check, 'idle'):
                    paired.validate(argparse.Namespace(ready=Path('/fixture'), output=out))
                fixed.assert_called_once()
                self.assertEqual([c.args[2]['threads'] for c in timed.call_args_list], COUNTS)
                self.assertEqual(finish.call_count, 21)
                self.assertTrue(all(c.args[-1] == PLAN for c in finish.call_args_list))
                receipt = json.loads((out / 'result.json').read_text())
                paired.validation_shape(receipt, mode, {}, PLAN)
                self.assertFalse(receipt['accepted'])

    def test_failed_control_preserves_partial_receipt_and_stops_new_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'validation'
            with patch.object(paired, 'readiness', return_value=(dict(plan=PLAN, mode='kd', prepared={}), {})), \
                 patch.object(paired, 'bind', return_value={}), \
                 patch.object(paired, 'fixed', return_value=validation()['fixed']), \
                 patch.object(paired, 'timed') as timed, \
                 patch.object(paired, 'business_finish', side_effect=[({}, 'drained'), ValueError('fixture failure')]):
                with self.assertRaisesRegex(ValueError, 'fixture failure'):
                    paired.validate(argparse.Namespace(ready=Path('/fixture'), output=out))
            self.assertEqual(timed.call_count, 2)
            receipt = json.loads((out / 'result.json').read_text())
            self.assertEqual(receipt['plan'], PLAN)
            self.assertEqual(len(receipt['cases']), 1)
            self.assertFalse(receipt['passed'] or receipt['drained'] or receipt['accepted'])

    def test_validation_requires_exact_grid_and_fixed_writer_proof(self):
        paired.validation_shape(validation(), 'kd', {}, PLAN)
        for edit in (lambda v: v.pop('plan'), lambda v: v['cases'].pop(),
                     lambda v: v['cases'].__setitem__(20, copy.deepcopy(v['cases'][19])),
                     lambda v: v['cases'][20]['spec'].__setitem__('threads', 64),
                     lambda v: v['fixed']['rejected_mutations'].pop()):
            bad = validation()
            edit(bad)
            with self.assertRaises(paired.rt.Failure):
                paired.validation_shape(bad, 'kd', {}, PLAN)

    def test_all_points_keep_paired_variability_and_regressions(self):
        result = report.summarize(rows(), bindings())
        self.assertEqual(result['qualified_cases'], 126)
        self.assertEqual([p['threads'] for p in result['points']], COUNTS)
        for point in result['points']:
            rates = point['arms']['native']['throughput_ops_s']
            self.assertEqual(rates['values'], [100, 101, 102])
            self.assertEqual((rates['median'], rates['minimum'], rates['maximum']), (101, 100, 102))
            self.assertAlmostEqual(rates['sample_cv'], statistics.stdev([100, 101, 102]) / 101)
            self.assertEqual(point['paired_kd_over_native_throughput']['values'], [90/100, 91/101, 92/102])
            self.assertLess(point['paired_kd_over_native_throughput']['median'], 1)
            self.assertNotIn('latency_percentiles_ns', point['arms']['native'])
        self.assertNotIn('sampled_over_plain_throughput', result)
        constant = rows()
        for row in constant:
            row['measurement']['whole_ops_s'] = 100
        equal = report.summarize(constant, bindings())['points'][0]
        self.assertEqual(equal['arms']['native']['throughput_ops_s']['sample_cv'], 0)
        self.assertEqual(equal['paired_kd_over_native_throughput']['values'], [1, 1, 1])

    def test_missing_duplicate_extra_and_subset_campaigns_reject(self):
        for data in ([], rows()[:-1], rows() + [rows()[0]], [rows()[0]] * 126,
                     [r for r in rows() if r['case'] in (0, 9)]):
            with self.assertRaises(ValueError):
                report.summarize(data, bindings())
        refs = bindings()
        refs.pop(ORDER[-1])
        with self.assertRaises(ValueError):
            report.summarize(rows(), refs)

    def test_plan_identity_is_not_inferred_from_count_or_missing_field(self):
        for plan in (paired.LEGACY_PLAN, paired.THROUGHPUT_PLAN, 'unknown', None, 1):
            bad = rows()
            bad[5]['plan'] = plan
            with self.subTest(plan=plan), self.assertRaises((ValueError, paired.rt.Failure)):
                report.summarize(bad, bindings())
        bad = rows()
        for row in bad:
            row.pop('plan')
        with self.assertRaises(ValueError):
            report.summarize(bad, bindings())
        self.assertEqual(paired.row_plan({}), paired.LEGACY_PLAN)

    def test_identity_predecessor_boot_and_acceptance_mutations_reject(self):
        mutations = [('previous', None), ('block', 4), ('boot_id', 'other'),
                     ('prepared', {'path': 'other', 'sha256': 'other'}),
                     ('ready', {'path': 'other', 'sha256': 'other'})]
        mutations += [(key, False) for key in ('passed', 'drained', 'accepted', 'endpoint_checked')]
        for key, value in mutations:
            bad = rows()
            bad[1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                report.summarize(bad, bindings())
        bad = rows()
        for row in bad:
            if row['block'] == 3:
                row['boot_id'] = 'boot-1'
        with self.assertRaises(ValueError):
            report.summarize(bad, bindings())
        bad = rows()
        bad[20]['spec']['threads'] = 64
        with self.assertRaises(ValueError):
            report.summarize(bad, bindings())

    def test_nonpositive_nonfinite_rates_and_latency_reject(self):
        for key, value in [('whole_ops_s', 0), ('whole_ops_s', -1), ('whole_ops_s', float('nan')),
                           ('whole_ops_s', float('inf')), ('whole_ops_s', '100'),
                           ('latency_samples', 1), ('latency_percentiles_ns', {'95': 10})]:
            bad = rows()
            bad[0]['measurement'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                report.summarize(bad, bindings())

    def test_plain_measurement_reuses_business_validation_and_rejects_samples(self):
        spec = paired.specification(20, 0, 'kd', PLAN)
        with patch.object(paired.writer, 'validate', return_value=dict(latency_samples=0)) as validate:
            result = paired.measurement([], spec, 'kd', PLAN)
        validate.assert_called_once_with([], spec)
        self.assertEqual(result['latency_percentiles_ns'], {})
        self.assertEqual(result['latency_sample_policy'], 'disabled')
        with patch.object(paired.writer, 'validate', return_value=dict(latency_samples=1)):
            with self.assertRaises(paired.rt.Failure):
                paired.measurement([], spec, 'kd', PLAN)

    def test_replay_requires_matching_client_readiness_and_validation_plan(self):
        for target in ('client', 'ready'):
            final = rows()[0]
            client = copy.deepcopy(final)
            ready = dict(passed=True, **{k: final[k] for k in ('mode', 'boot_id', 'block', 'prepared', 'plan')})
            (client if target == 'client' else ready)['plan'] = paired.THROUGHPUT_PLAN
            with patch.object(paired.common, 'load', side_effect=[final, client]), \
                 patch.object(paired, 'load_bound', return_value=ready), \
                 patch.object(paired, 'qualify') as qualify:
                with self.assertRaises(ValueError):
                    report.replay(Path('/fixture/result.json'))
            qualify.assert_not_called()
        v = validation()
        v['ready'] = {}
        with patch.object(paired.common, 'load', return_value=v), \
             patch.object(paired, 'load_bound', return_value=dict(passed=True, mode='kd', prepared={}, block=1,
                                                               plan=paired.THROUGHPUT_PLAN)), \
             patch.object(paired.mapping, 'validate') as raw:
            with self.assertRaises(paired.rt.Failure):
                paired.validation_receipt(Path('/fixture'), 'kd', {}, PLAN)
        raw.assert_not_called()


if __name__ == '__main__':
    unittest.main()
