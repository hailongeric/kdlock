"""VM-only focused checks for bounded Native versus current KD-off comparison."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bench/nano'))
import run as nano_run


class NativeCurrentPlan(unittest.TestCase):
    def receipts(self):
        return [dict(status='FUNCTIONAL_PASS', stage='functional', family=family, backend=backend,
                     scope='native-current', build_receipt_sha256='build', boot_id='boot',
                     runner_sha256='runner',
                     recorder_modes=['on', 'off'] if backend == 'kdlock' else ['unavailable'])
                for family in ('mutex', 'rwsem') for backend in ('native', 'kdlock')]

    def validate(self, rows, runner='runner'):
        nano_run.validate_prerequisites(rows, 'native-current', 'mutex', 'build', 'boot', runner)

    def test_four_lanes_total_twelve_matching_single_worker_timings(self):
        total = 0
        for family in ('mutex', 'rwsem'):
            for backend in ('native', 'kdlock'):
                with self.subTest(family=family, backend=backend):
                    plan = nano_run.measurement_plan('native-current', 'timing', backend)
                    functional = [row for row in plan if not row[2]]
                    timed = [row for row in plan if row[2]]
                    self.assertEqual(functional, nano_run.measurement_plan('native-current', 'functional', backend))
                    self.assertEqual([row[1] for row in plan], [1] * len(plan))
                    self.assertEqual(len(timed), 3)
                    self.assertEqual([row[3] for row in timed],
                                     ['off' if backend == 'kdlock' else 'unavailable'] * 3)
                    self.assertEqual([row[3] for row in functional],
                                     ['on', 'off'] if backend == 'kdlock' else ['unavailable'])
                    total += len(timed)
        self.assertEqual(total, 12)

    def test_native_has_no_kd_recorder_control_and_tclock_is_refused(self):
        for backend in ('native', 'kdlock'):
            nano_run.validate_scope('native-current', backend)
        with self.assertRaises(ValueError):
            nano_run.validate_scope('native-current', 'tclock')
        with self.assertRaises(ValueError):
            nano_run.measurement_plan('native-current', 'timing')
        with mock.patch.object(nano_run, 'set_recording') as control:
            self.assertIsNone(nano_run.phase_recording('native-current', 'native', 'unavailable'))
            control.assert_not_called()
            nano_run.phase_recording('native-current', 'kdlock', 'on')
            nano_run.phase_recording('native-current', 'kdlock', 'off')
            self.assertEqual(control.call_args_list, [mock.call(True), mock.call(False)])
            with self.assertRaises(ValueError):
                nano_run.phase_recording('native-current', 'kdlock', 'unavailable')
            self.assertEqual(control.call_count, 2)

    def test_mutex_only_rounds_require_both_matched_backends(self):
        scope = 'mutex-uncontended'
        rows = self.receipts()[:2]
        for row in rows:
            row.update(scope=scope, collector_cpu=39,
                       kd_delegation='on' if row['backend'] == 'kdlock' else None)
            plan = nano_run.measurement_plan(scope, 'timing', row['backend'])
            self.assertEqual(plan, nano_run.measurement_plan('native-current', 'timing', row['backend']))
        def check(prior):
            nano_run.validate_prerequisites(prior, scope, 'mutex', 'build', 'boot', 'runner', 39)
        check(rows)
        with self.assertRaises(ValueError):
            check(rows[:1])
        for field, value in (('collector_cpu', 38), ('family', 'rwsem'), ('kd_delegation', 'off'),
                             ('recorder_modes', ['on']), ('runner_sha256', 'other')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                check([rows[0], dict(rows[1], **{field: value})])
        with mock.patch.object(nano_run, 'set_recording') as control:
            nano_run.phase_recording(scope, 'native', 'unavailable')
            nano_run.phase_recording(scope, 'kdlock', 'off')
            control.assert_called_once_with(False)

    def test_all_four_distinct_functional_lanes_are_required(self):
        rows = self.receipts()
        self.validate(rows)
        for omitted in range(4):
            with self.subTest(omitted=omitted), self.assertRaises(ValueError):
                self.validate(rows[:omitted] + rows[omitted + 1:])
        for invalid in ([], rows + [rows[0]], rows[:3] + [rows[0]]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.validate(invalid)

    def test_prerequisites_bind_status_stage_build_boot_and_runner(self):
        for key, value in (('status', 'TIMING_COMPLETE'), ('stage', 'timing'),
                           ('build_receipt_sha256', 'old-build'), ('boot_id', 'old-boot'),
                           ('runner_sha256', 'old-runner')):
            rows = self.receipts()
            rows[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(rows)
        for runner in (None, '', 'different'):
            with self.subTest(runner=runner), self.assertRaises(ValueError):
                self.validate(self.receipts(), runner)

    def test_other_scopes_and_missing_kd_functional_mode_cannot_qualify(self):
        for index, key, value in ((0, 'recorder_modes', ['off']), (1, 'recorder_modes', ['off']),
                                  (1, 'recorder_modes', ['on']), (0, 'scope', 'comparison'),
                                  (1, 'scope', 'recorder-pair'), (0, 'backend', 'tclock')):
            rows = self.receipts()
            rows[index][key] = value
            with self.subTest(index=index, key=key, value=value), self.assertRaises(ValueError):
                self.validate(rows)

    def test_bounded_receipts_cannot_replace_existing_scope_prerequisites(self):
        for scope, rows in (('comparison', self.receipts()), ('recorder-pair', [self.receipts()[1]])):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                nano_run.validate_prerequisites(rows, scope, 'mutex', 'build', 'boot')
        pair = copy.deepcopy(self.receipts()[1])
        pair['scope'] = 'recorder-pair'
        nano_run.validate_prerequisites([pair], 'recorder-pair', 'mutex', 'build', 'boot')


if __name__ == '__main__':
    unittest.main()
