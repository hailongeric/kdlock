"""Guest-only plan and fail-closed optional-peak boundary checks."""
import unittest
from unittest.mock import patch

import timing


class SingleRound(unittest.TestCase):
    def test_historical_plan_stays_three_rounds_and_two_modes(self):
        rows = timing.measurement_plan()
        self.assertEqual(len(rows), 48)
        self.assertEqual({r['repeat'] for r in rows}, {0, 1, 2})
        self.assertEqual({r['observation'] for r in rows}, {'plain', 'sampled'})
        self.assertTrue(all('peak_policy' not in r for r in rows))

    def test_new_grid_has_only_supported_arms_and_one_plain_point(self):
        grid = list(range(1, 9)) + list(range(12, 61, 4))
        for workload, arms in [('mmap', {'native'}), ('fault', {'native', 'kdlock', 'tclock'})]:
            rows = timing.measurement_plan(True, workload)
            identities = {(r['threads'], r['arm']) for r in rows}
            self.assertEqual(identities, {(n, arm) for n in grid for arm in arms})
            self.assertEqual(len(rows), len(identities))
            for r in rows:
                self.assertEqual((r['repeat'], r['observation'], r['collector_cpu']), (0, 'plain', 63))
                self.assertEqual(r['cpus'], list(range(r['threads'])))

    def test_invalid_plan_selection_is_rejected(self):
        for single, workload in [(True, None), (True, 'combined'), (False, 'fault')]:
            with self.assertRaises(timing.rt.Failure):
                timing.measurement_plan(single, workload)

    def test_only_exact_positive_peak_absence_is_optional(self):
        spec = {'peak_policy': 'optional-positive-window'}
        reason = 'no positive full-cohort peak window'
        with patch.object(timing, 'analyze_peak', side_effect=ValueError(reason)):
            self.assertEqual(timing.peak_result({}, spec), (None, reason))
            with self.assertRaises(ValueError):
                timing.peak_result({}, {})
        for error in [ValueError('bad progress'), TypeError(reason), timing.rt.Failure('DATA_ERROR', reason)]:
            with patch.object(timing, 'analyze_peak', side_effect=error):
                with self.assertRaises(type(error)):
                    timing.peak_result({}, spec)
        with self.assertRaises(timing.rt.Failure):
            timing.peak_result({}, {'peak_policy': 'unknown'})


if __name__ == '__main__':
    unittest.main()
