#!/usr/bin/env python3
"""Checks against pooling policies, incomplete repeats and tampered peaks."""
import copy
import unittest

import export


class ExportTests(unittest.TestCase):
    def rows(self, mode='spin'):
        return [dict(subject='mutex-cacheline-c01', threads=16, backend='kd-' + mode,
            repeat=i, mutex_spin_limit=4096, lock_kind='mutex', suite='micro',
            accepted=True,
            jit_bodies=100 if i else 0, jit_eligible_ops=1000,
            execution_type='ACTUAL_JIT' if i else 'NO_JIT', whole_ops_s=10 + i,
            peak_ops_s=12 + i, cpu_ns_per_op=20 - i) for i in range(3)]

    def test_policies_are_distinct_and_execution_is_explicit(self):
        rows = self.rows() + self.rows('blocking')
        stats = export.aggregate(rows)
        self.assertEqual({r['backend'] for r in stats}, {'kd-spin', 'kd-blocking'})
        self.assertTrue(all(r['jit_rounds'] == 2 and r['whole_ops_s_median'] == 11 for r in stats))
        separated = export.aggregate(rows, split_execution=True)
        self.assertEqual(len(separated), 4)
        self.assertEqual(sorted(r['rounds'] for r in separated), [1, 1, 2, 2])

    def test_refuse_missing_repeated_or_differently_tuned_rounds(self):
        rows = self.rows()
        for bad in (rows[:2], rows + [rows[0]], [rows[0], rows[0], rows[2]]):
            with self.assertRaises(ValueError):
                export.aggregate(bad)
        rows[1]['mutex_spin_limit'] = 1024
        with self.assertRaises(ValueError):
            export.aggregate(rows)

    def test_baselines_are_required(self):
        with self.assertRaises(ValueError):
            export.comparisons(export.aggregate(self.rows() + self.rows('blocking')))

    def test_rejected_no_jit_is_retained_but_not_scored(self):
        rows = self.rows()
        rows[0].update(accepted=False, whole_ops_s=1000, peak_ops_s=2000)
        result, = export.aggregate(rows)
        self.assertEqual((result['rounds'], result['accepted_rounds']), (3, 2))
        self.assertFalse(result['complete'])
        self.assertEqual(result['whole_ops_s_median'], 11.5)
        self.assertEqual(result['peak_ops_s_max'], 14)

    def test_execution_verdict_matches_returned_bodies(self):
        row = dict(arm='kdlock', lock_kind='mutex', threads=16, jit_bodies=1,
                   jit_status='JIT', jit_acceptance='PASS', execution_status='OK')
        export.check_execution(row)
        row.update(jit_bodies=0, jit_status='NO_JIT', jit_acceptance='NO_JIT')
        with self.assertRaises(ValueError):
            export.check_execution(row)
        row['execution_status'] = 'NO_JIT'
        export.check_execution(row)
        # Uncontended and optional writer controls retain zero-JIT data.
        row.update(threads=1, execution_status='OK')
        export.check_execution(row)
        row.update(threads=16, lock_kind='rwlock')
        export.check_execution(row)
        row.update(arm='native', jit_bodies=1)
        with self.assertRaises(ValueError):
            export.check_execution(row)

    def test_peak_recomputed_and_every_worker_must_progress(self):
        row = dict(name='raw', measurement=dict(workers=[dict(active_started_ns=0, kernel_finished_ns=100)],
            peak_settle_ns=10, deadline_ns=100, peak_window_ns=30,
            samples=[dict(started_ns=t, finished_ns=t + 1, completed=[n, n])
                     for t, n in ((10, 0), (40, 30), (70, 50))],
            peak=dict(completed=60, elapsed_ns=31, start_sample_index=0, end_sample_index=1,
                      worker_completed=[30, 30], throughput_ops_s=60e9 / 31)))
        export.check_peak(row)
        bad = copy.deepcopy(row)
        bad['measurement']['peak']['throughput_ops_s'] *= 1.01
        with self.assertRaises(ValueError):
            export.check_peak(bad)
        bad = copy.deepcopy(row)
        for sample in bad['measurement']['samples']:
            sample['completed'][1] = 0
        with self.assertRaises(ValueError):
            export.check_peak(bad)

    def test_full_scope_has_thirty_one_subjects(self):
        self.assertEqual(len(export.SUBJECTS), 31)
        self.assertIn('rwlock-rcuht-w20', export.SUBJECTS)
        self.assertIn('pipebytes-query-n128-v64', export.SUBJECTS)


if __name__ == '__main__':
    unittest.main()
