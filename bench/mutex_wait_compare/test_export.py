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

    def test_api_stock_and_native_ratios_remain_distinct(self):
        rows = []
        for arm, rate in (('stock', 10), ('native', 20), ('tclock', 30),
                          ('kd-spin', 40), ('kd-blocking', 50)):
            rows += [dict(r, subject='pipebytes-query-n16-v64', suite='api',
                          backend=arm, whole_ops_s=rate, peak_ops_s=rate)
                     for r in self.rows()]
        result, = export.comparisons(export.aggregate(rows))
        self.assertEqual(result['kd-spin_over_stock_whole_ops_s_median'], 4)
        self.assertEqual(result['kd-blocking_over_native_whole_ops_s_median'], 2.5)
        self.assertEqual(result['kd-blocking_over_kd-spin_peak_ops_s_max'], 1.25)
        with self.assertRaises(ValueError):
            export.comparisons(export.aggregate([r for r in rows if r['backend'] != 'stock']))

    def test_rejected_no_jit_is_retained_but_not_scored(self):
        rows = self.rows()
        rows[0].update(accepted=False, whole_ops_s=1000, peak_ops_s=2000)
        result, = export.aggregate(rows)
        self.assertEqual((result['rounds'], result['accepted_rounds']), (3, 2))
        self.assertFalse(result['complete'])
        self.assertEqual(result['whole_ops_s_median'], 11.5)
        self.assertEqual(result['peak_ops_s_max'], 14)

    def test_drained_no_jit_keeps_unscored_measurement_with_blank_reported_rate(self):
        row = dict(measurement=dict(completed=20, wall_ns=1000000000),
                   execution_status='NO_JIT', jit_bodies=0, whole_throughput_ops_s=None)
        self.assertEqual(export.check_whole(row), 20)
        with self.assertRaises(ValueError):
            export.check_whole(dict(row, execution_status='OK'))
        with self.assertRaises(ValueError):
            export.check_whole(dict(row, jit_bodies=1))
        with self.assertRaises(ValueError):
            export.check_whole(dict(row, whole_throughput_ops_s=21))

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

    def test_hash_mix_excludes_warmup_and_uses_writes_for_rwlock(self):
        before, after = [100, 25, 25, 50] + [0]*12, [120, 30, 31, 59] + [0]*12
        row = dict(workload='rcuht', lock_kind='mutex', measurement=dict(
            before=before, after=after, completed=20))
        expected = dict(hash_move_ops=5, hash_destination_conflict_ops=6, hash_source_miss_ops=9)
        self.assertEqual(export.hash_outcomes(row), expected)
        rw = dict(row, lock_kind='rwlock', measurement=dict(
            before=dict(values=before), after=dict(values=after), completed=100, writes=20))
        self.assertEqual(export.hash_outcomes(rw), expected)
        rw['measurement']['writes'] = 21
        with self.assertRaises(ValueError):
            export.hash_outcomes(rw)

    def test_low_contention_controls_do_not_relax_contended_acceptance(self):
        row = dict(arm='kdlock', lock_kind='mutex', threads=2, jit_bodies=0,
                   jit_status='NO_JIT', jit_acceptance='NO_JIT_LOW_CONTENTION', execution_status='OK')
        for n in (2, 3):
            export.check_execution(dict(row, threads=n))
        with self.assertRaises(ValueError):
            export.check_execution(dict(row, threads=4))
        with self.assertRaises(ValueError):
            export.check_execution(dict(row, threads=3, jit_acceptance='PASS'))

    def test_every_requested_point_and_round_is_required(self):
        rows = [dict(subject=name, threads=n, backend=arm, repeat=i)
                for name in export.SUBJECTS for n in export.FULL_THREADS
                for arm in (export.ARMS[1:] if name.startswith(('spin-', 'mutex-', 'rwlock-')) else export.ARMS)
                for i in range(3)]
        self.assertEqual(len(rows), 8910)
        export.check_coverage(rows, export.FULL_THREADS)
        with self.assertRaises(ValueError):
            export.check_coverage(rows[:-1], export.FULL_THREADS)
        # Same sample total cannot conceal a duplicated point and a missing one.
        with self.assertRaises(ValueError):
            export.check_coverage(rows[:-1] + rows[:1], export.FULL_THREADS)

    def test_full_grid_rejects_collector_collision(self):
        state = dict(state='COMPLETE', threads=export.FULL_THREADS, collector_cpu=65,
                     worker_cpus=[*range(32), *range(33, 65)], expected_sessions=8910,
                     paired_policies=True)
        plan = [dict(name=str(i), expected=0) for i in range(14)]
        plan[-1]['expected'] = 8910
        self.assertEqual(export.matrix_grid(state, plan)[-1], 8910)
        with self.assertRaises(ValueError):
            export.matrix_grid(dict(state, collector_cpu=64), plan)

    def test_pair_order_rejects_separated_policies(self):
        base = dict(kind='pipebytes', query='query', entries=16, value_size=64,
                    threads=64, repeat=1, arm='kdlock')
        rows = [dict(base, mutex_wait_mode=mode) for mode in ('blocking', 'spin')]
        export.check_pair_order(rows, dict(mode='both'))
        with self.assertRaises(ValueError):
            export.check_pair_order([rows[0], dict(base, arm='native'), rows[1]], dict(mode='both'))


if __name__ == '__main__':
    unittest.main()
