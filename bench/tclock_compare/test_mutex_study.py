"""Acceptance must fail on either throughput metric, missing rounds or no JIT."""
import unittest

from mutex_study import GRID, evaluate, metrics, require_fresh, sample_identities
from bench_runtime import Failure


def samples(threads, arm, rate=100, peak=120, jit=1):
    return [dict(threads=threads, arm=arm, repeat=r, mutex_entry_ratio_limit=2,
                 mutex_routing='adaptive', mutex_acceptance='adaptive-performance',
                 jit_bodies=jit if arm == 'kdlock' else 0,
                 measurement=dict(completed=rate, wall_ns=1000000000,
                     worker_cpu_ns=threads*1000000000, peak=dict(throughput_ops_s=peak),
                     workers=[dict(completed=rate/threads) for _ in range(threads)]))
            for r in range(3)]


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.baseline = [r for t in GRID for r in samples(t, 'kdlock')]
        self.candidate = [r for t in GRID for arm in ('kdlock', 'native') for r in samples(t, arm)]

    def test_complete_and_partial(self):
        self.assertEqual(evaluate(self.baseline, self.candidate)['verdict'], 'PASS')
        partial = [r for r in self.candidate if r['threads'] == 4]
        self.assertEqual(evaluate(self.baseline, partial)['verdict'], 'INCOMPLETE')

    def test_both_metrics_are_independent(self):
        for metric in ('whole', 'peak'):
            with self.subTest(metric=metric):
                broken = [r for r in self.candidate if r['threads'] != 4 or r['arm'] != 'kdlock']
                broken += samples(4, 'kdlock', rate=96 if metric == 'whole' else 100,
                                  peak=115 if metric == 'peak' else 120)
                result = evaluate(self.baseline, broken)
                self.assertEqual(result['verdict'], 'REJECTED')
                self.assertEqual([c['threads'] for c in result['checks'] if not c['passed']], [4])

    def test_regression_requires_jit_in_every_round(self):
        for r in self.candidate:
            if r['threads'] == 60 and r['repeat'] == 1:
                r['jit_bodies'] = 0
        self.assertEqual(evaluate(self.baseline, self.candidate)['verdict'], 'REJECTED')

    def test_missing_or_duplicate_round_is_not_valid(self):
        rows = samples(4, 'kdlock')
        with self.assertRaises(Failure):
            metrics(rows[:2])
        with self.assertRaises(Failure):
            metrics([rows[0], rows[0], rows[2]])

    def test_primary_native_execution_is_allowed(self):
        for r in self.candidate:
            if r['threads'] <= 28:
                r['jit_bodies'] = 0
        self.assertEqual(evaluate(self.baseline, self.candidate)['verdict'], 'PASS')

    def test_confirmation_cannot_reuse_screen_or_previous_block(self):
        rows = samples(4, 'kdlock')
        for i, row in enumerate(rows):
            row['measurement'].update(started_ns=10*i, finished_ns=10*i+1)
        seen = sample_identities(rows)
        with self.assertRaises(Failure):
            require_fresh(rows, seen)
        for row in rows:
            row['measurement']['started_ns'] += 100
            row['measurement']['finished_ns'] += 100
        require_fresh(rows, seen)
        with self.assertRaises(Failure):
            require_fresh(rows, seen)


if __name__ == '__main__':
    unittest.main()
