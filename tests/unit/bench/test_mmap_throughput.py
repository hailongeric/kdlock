"""Plain-plan fixtures only; no live mmap, module, observer or controller runs."""
import argparse
import copy
import hashlib
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

PLAN = paired.THROUGHPUT_PLAN


def bindings(plan=PLAN):
    return {key: dict(path='/fixture/' + str(i), sha256=hashlib.sha256(str(key).encode()).hexdigest())
            for i, key in enumerate(paired.order_for(plan))}


def rows():
    result, refs = [], bindings()
    for index, (repeat, mode, case) in enumerate(paired.order_for(PLAN)):
        block = paired.expected_block(repeat, mode)
        result.append(dict(plan=PLAN, passed=True, drained=True, accepted=True, endpoint_checked=True,
            prepared=dict(path='fixture', sha256='same'), repeat=repeat, mode=mode, case=case,
            block=block, boot_id='boot-' + str(block), ready=dict(path='ready-' + str(block), sha256='same'),
            previous=refs[paired.order_for(PLAN)[index-1]] if index else None,
            spec=paired.specification(case, repeat, mode, PLAN),
            measurement=dict(whole_ops_s=(100 if mode == 'native' else 90) + repeat,
                             latency_samples=0, latency_percentiles_ns={})))
    return result


def validation():
    v = legacy.Validation().fixture()
    v.update(plan=PLAN, cases=[dict(spec=paired.specification(i, 0, 'kd', PLAN)) for i in range(2)])
    return v


class PlainPlan(unittest.TestCase):
    def setUp(self):
        for target in ('subprocess.Popen', 'socket.socket'):
            guard = patch(target, side_effect=AssertionError('live action forbidden'))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch.object(paired.rt, 'command', side_effect=AssertionError('real command forbidden'))
        guard.start()
        self.addCleanup(guard.stop)

    def test_exact_shape_order_and_derived_bounds(self):
        self.assertEqual(paired.cases_for(PLAN), [(1, 'plain'), (16, 'plain')])
        order = paired.order_for(PLAN)
        self.assertEqual(len(order), 12)
        self.assertEqual([order[i][:2] for i in range(0, 12, 2)],
                         [(0, 'kd'), (0, 'native'), (1, 'native'), (1, 'kd'), (2, 'kd'), (2, 'native')])
        self.assertEqual(paired.bounds(PLAN), dict(measured_sessions=12, unscored_checks=6,
                         payload_cycles=18, boots=6, host_captures=31))
        self.assertEqual(paired.bounds(paired.LEGACY_PLAN), dict(measured_sessions=24, unscored_checks=10,
                         payload_cycles=34, boots=6, host_captures=55))
        for case in (0, 1):
            spec = paired.specification(case, 0, 'kd', PLAN)
            self.assertEqual(spec['sample_ms'], 10)  # Existing progress accounting.
            self.assertEqual(spec['observation'], 'plain')
            self.assertEqual(spec['cpus'], list(range(spec['threads'])))
        with self.assertRaises(paired.rt.Failure):
            paired.specification(2, 0, 'kd', PLAN)

    def test_paired_rates_spread_and_regression_remain_visible(self):
        result = report.summarize(rows(), bindings())
        self.assertEqual(result['qualified_cases'], 12)
        self.assertEqual(result['plan'], PLAN)
        self.assertEqual(len(result['points']), 2)
        point = result['points'][0]
        rates = point['arms']['native']['throughput_ops_s']
        self.assertEqual(rates['values'], [100, 101, 102])
        self.assertEqual((rates['median'], rates['minimum'], rates['maximum']), (101, 100, 102))
        self.assertAlmostEqual(rates['sample_cv'], statistics.stdev([100, 101, 102]) / 101)
        ratio = point['paired_kd_over_native_throughput']
        self.assertEqual(ratio['values'], [90/100, 91/101, 92/102])
        self.assertLess(ratio['median'], 1)
        self.assertNotIn('latency_percentiles_ns', point['arms']['native'])
        self.assertNotIn('sampled_over_plain_throughput', result)

    def test_missing_duplicate_extra_and_failed_records_reject(self):
        variants = [rows()[:-1], rows() + [rows()[0]], [rows()[0]] * 12]
        for key in ('passed', 'accepted', 'drained', 'endpoint_checked'):
            bad = rows()
            bad[0][key] = False
            variants.append(bad)
        for data in variants:
            with self.assertRaises(ValueError):
                report.summarize(data, bindings())
        refs = bindings()
        refs.pop(next(iter(refs)))
        with self.assertRaises(ValueError):
            report.summarize(rows(), refs)

    def test_plan_separation_never_infers_plain_from_missing_or_unknown_plan(self):
        for plan in (paired.LEGACY_PLAN, 'unknown', None, 1):
            bad = rows()
            bad[5]['plan'] = plan
            with self.subTest(plan=plan), self.assertRaises((ValueError, paired.rt.Failure)):
                report.summarize(bad, bindings())
        bad = rows()
        for row in bad:
            del row['plan']
        with self.assertRaises(ValueError):
            report.summarize(bad, bindings())
        old = legacy.rows()
        for row in old:
            row['plan'] = PLAN
        with self.assertRaises(ValueError):
            report.summarize(old, legacy.fixture_bindings())

    def test_historical_default_and_explicit_legacy_keep_same_report(self):
        self.assertEqual(paired.row_plan({}), paired.LEGACY_PLAN)
        self.assertEqual(paired.order_for(paired.LEGACY_PLAN), paired.ORDER)
        before = legacy.summary(legacy.rows())
        explicit = legacy.rows()
        for row in explicit:
            row['plan'] = paired.LEGACY_PLAN
        self.assertEqual(report.summarize(explicit, legacy.fixture_bindings()), before)
        self.assertEqual(before['qualified_cases'], 24)
        self.assertEqual(len(before['points']), 4)
        self.assertIn('sampled_over_plain_throughput', before)
        self.assertNotIn('plan', before)

    def test_spec_predecessor_boot_rate_and_latency_mutations_reject(self):
        for field, value in [('spec', paired.specification(1, 0, 'kd')),
                             ('previous', None), ('block', 4), ('boot_id', 'other'),
                             ('prepared', dict(path='other', sha256='other'))]:
            bad = rows()
            bad[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                report.summarize(bad, bindings())
        for field, value in [('whole_ops_s', 0), ('whole_ops_s', float('nan')),
                             ('whole_ops_s', float('inf')), ('latency_samples', 1),
                             ('latency_percentiles_ns', {'95': 10})]:
            bad = rows()
            bad[0]['measurement'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                report.summarize(bad, bindings())
        bad = rows()
        del bad[0]['measurement']['whole_ops_s']
        with self.assertRaises(KeyError):
            report.summarize(bad, bindings())

    def test_plain_measurement_reuses_business_validation_and_rejects_samples(self):
        with patch.object(paired.writer, 'validate', return_value=dict(latency_samples=0)) as validate:
            row = paired.measurement([], paired.specification(0, 0, 'kd', PLAN), 'kd', PLAN)
        validate.assert_called_once()
        self.assertEqual(row['latency_sample_policy'], 'disabled')
        self.assertEqual(row['latency_percentiles_ns'], {})
        self.assertEqual(row['execution'], 'KD_LOCAL_MMAP_LOCK')
        with patch.object(paired.writer, 'validate', return_value=dict(latency_samples=1)):
            with self.assertRaises(paired.rt.Failure):
                paired.measurement([], paired.specification(0, 0, 'kd', PLAN), 'kd', PLAN)

    def test_plain_validation_requires_both_counts_fixed_proof_and_matching_plan(self):
        paired.validation_shape(validation(), 'kd', {}, PLAN)
        for edit in (lambda v: v.pop('plan'), lambda v: v['cases'].pop(),
                     lambda v: v['cases'].append(copy.deepcopy(v['cases'][0])),
                     lambda v: v['fixed']['rejected_mutations'].pop()):
            bad = validation()
            edit(bad)
            with self.assertRaises(paired.rt.Failure):
                paired.validation_shape(bad, 'kd', {}, PLAN)
        v = validation()
        v['ready'] = {}
        with patch.object(paired.common, 'load', return_value=v), \
             patch.object(paired, 'load_bound', return_value=dict(passed=True, mode='kd', prepared={}, block=1)), \
             patch.object(paired.mapping, 'validate') as raw:
            with self.assertRaises(paired.rt.Failure):
                paired.validation_receipt(Path('/fixture'), 'kd', {}, PLAN)
        raw.assert_not_called()

    def test_validate_executes_only_one_fixed_and_two_plain_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'new-validation'
            ready = dict(plan=PLAN, mode='kd', prepared={})
            with patch.object(paired, 'readiness', return_value=(ready, dict(files={}))), \
                 patch.object(paired, 'bind', return_value={}), \
                 patch.object(paired, 'fixed', return_value=validation()['fixed']) as fixed, \
                 patch.object(paired, 'timed') as timed, \
                 patch.object(paired, 'business_finish', return_value=({}, 'exact drain')), \
                 patch.object(paired.common, 'verify_maps'), patch.object(paired.writer.check, 'idle'):
                paired.validate(argparse.Namespace(ready=Path('/fixture'), output=out))
            fixed.assert_called_once()
            self.assertEqual(timed.call_count, 2)
            self.assertEqual([(call.args[2]['threads'], call.args[2]['observation']) for call in timed.call_args_list],
                             [(1, 'plain'), (16, 'plain')])
            receipt = json.loads((out / 'result.json').read_text())
            self.assertEqual(receipt['plan'], PLAN)
            self.assertTrue(receipt['passed'] and receipt['drained'])

    def test_run_inherits_plan_and_refuses_legacy_predecessor_before_launch(self):
        for predecessor_plan in (PLAN, paired.LEGACY_PLAN):
            with self.subTest(predecessor_plan=predecessor_plan), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'run'
                ready = dict(plan=PLAN, mode='kd', boot_id='boot', block=1, prepared={})
                prior = dict(plan=predecessor_plan, passed=True, drained=True, accepted=True,
                             repeat=0, mode='kd', case=0, block=1, boot_id='boot', prepared={},
                             endpoint_captured_utc='2026-10-25T00:00:00')
                args = argparse.Namespace(ready=Path('/ready'), output=out, repeat=0, case=1,
                    previous=Path('/previous'), native_validation=Path('/native-validation'),
                    kd_validation=Path('/kd-validation'), host_state=Path('/host'))
                with patch.object(paired, 'readiness', return_value=(ready, {})), \
                     patch.object(paired, 'bind', return_value={}), \
                     patch.object(paired.common, 'load', side_effect=[prior, {'captured_utc': '2026-10-25T00:01:00'}]), \
                     patch.object(paired, 'validation_receipt') as validate, \
                     patch.object(paired, 'host_check'), patch.object(paired, 'environment', return_value=({}, {})), \
                     patch.object(paired, 'host_environment'), patch.object(paired, 'fault_check'), \
                     patch.object(paired.shutil, 'copyfile'), patch.object(paired, 'timed') as timed:
                    # host_comparison is serialized into the receipt.
                    paired.host_environment.return_value = {}
                    if predecessor_plan == PLAN:
                        paired.run(args)
                        timed.assert_called_once()
                        self.assertEqual(timed.call_args.args[2]['observation'], 'plain')
                        self.assertEqual(timed.call_args.args[2]['threads'], 16)
                        self.assertTrue(all(call.args[-1] == PLAN for call in validate.call_args_list))
                    else:
                        with self.assertRaises(paired.rt.Failure):
                            paired.run(args)
                        timed.assert_not_called()
                        validate.assert_not_called()
                self.assertEqual(json.loads((out / 'client-result.json').read_text())['plan'], PLAN)

    def test_replay_requires_plan_binding_in_client_and_readiness(self):
        for target in ('client', 'ready'):
            final = rows()[0]
            client = copy.deepcopy(final)
            ready = dict(passed=True, **{k: final[k] for k in ('mode', 'boot_id', 'block', 'prepared', 'plan')})
            (client if target == 'client' else ready).pop('plan')
            with patch.object(paired.common, 'load', side_effect=[final, client]), \
                 patch.object(paired, 'load_bound', return_value=ready), \
                 patch.object(paired, 'qualify') as qualify:
                with self.assertRaises(ValueError):
                    report.replay(Path('/fixture/result.json'))
            qualify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
