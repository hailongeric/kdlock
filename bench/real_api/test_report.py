"""Offline acceptance/statistics checks; execute in the benchmark guest."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from report import summarize, write_report


def record(whole=10, peak=12, *, arm='kdlock', **changes):
    row = dict(kind='ofd', query='tail', entries=16, value_size=64,
               threads=2, arm=arm, execution_status='OK', drained=True,
               whole_throughput_ops_s=whole, peak_throughput_ops_s=peak,
               jit_bodies=4, measurement=dict(completed=10,
                   workers=[dict(completed=4, cpu_ns=20), dict(completed=6, cpu_ns=30)]))
    row.update(changes)
    return row


class ReportTests(unittest.TestCase):
    def test_owned_mutex_identity_is_not_pooled_with_legacy_or_other_policies(self):
        old = record(kind='pipebytes', query='query', mutex_wait_mode='blocking',
                     mutex_spin_limit=4096)
        owned = dict(old, mutex_implementation='owned-v1', entry_abi=4,
                     owned_mutex_reuse_spins=32, owned_mutex_origin_spin=False,
                     owned_mutex_numa=False)
        rows = [old, owned, dict(owned, owned_mutex_reuse_spins=0)]
        self.assertEqual(len(summarize(rows)), 3)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'distinct KD mutex protocols'):
                write_report(Path(d), rows)

    def test_wait_policies_are_not_pooled(self):
        rows = [record(mutex_wait_mode='spin', mutex_spin_limit=4096),
                record(100, 120, mutex_wait_mode='blocking', mutex_spin_limit=4096),
                record(200, 240, mutex_wait_mode='blocking', mutex_spin_limit=0)]
        self.assertEqual(len(summarize(rows)), 3)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'distinct KD waiting policies'):
                write_report(Path(d), rows)

    def test_failures_unrun_and_undrained_never_improve_score(self):
        rows = [record(), record(20, 25, jit_bodies=0),
                record(1000, 2000, execution_status='DATA_ERROR'),
                record(3000, 4000, drained=False),
                record(5000, 6000, execution_status='NOT_RUN', drained=False)]
        saved = copy.deepcopy(rows)
        r, = summarize(rows)
        self.assertEqual(rows, saved)
        self.assertEqual((r['planned'], r['accepted'], r['failed'], r['not_run']), (5, 2, 2, 1))
        self.assertEqual((r['whole_min'], r['whole_median'], r['whole_max']), (10, 15, 20))
        self.assertEqual((r['peak_min'], r['peak_median'], r['peak_max']), (12, 18.5, 25))
        self.assertAlmostEqual(r['whole_spread_pct'], 100*10/15)
        self.assertEqual((r['jit_positive'], r['jit_bodies']), (1, 4))
        self.assertEqual((r['worker_min_share'], r['worker_max_share']), (.4, .6))
        self.assertEqual(r['cpu_ns_per_op_median'], 5)

    def test_no_accepted_run_has_no_numeric_score(self):
        r, = summarize([record(execution_status='TRANSLATION_TIMEOUT', drained=True)])
        self.assertEqual(r['accepted'], 0)
        for field in ('whole_max', 'peak_max', 'cpu_ns_per_op_median', 'worker_min_share'):
            self.assertIsNone(r[field])

    def test_workloads_and_backends_remain_separate(self):
        rows = [record(), record(arm='stock', jit_bodies=0),
                record(kind='setfd', query='toggle'), record(entries=128),
                record(value_size=128), record(threads=4), record(query='miss')]
        self.assertEqual(len(summarize(rows)), len(rows))

    def test_rwlock_jit_share_counts_writes_and_mutex_delegation_is_retained(self):
        rw = record(kind='utsname', query='host', entries=20,
                    jit_bodies=2, measurement=dict(completed=10, reads=8, writes=2,
                    workers=[dict(completed=10, cpu_ns=50)]))
        result, = summarize([rw])
        self.assertEqual(result['jit_eligible_operations'], 2)
        self.assertEqual(result['jit_share'], 1)
        self.assertEqual(result['parameter_unit'], 'write percent')
        mutex = record(kind='pipebytes', query='query', arm='tclock', jit_bodies=0,
                       tclock_delegation=7)
        result, = summarize([mutex, dict(mutex, tclock_delegation=8)])
        self.assertEqual(result['tclock_delegated'], 15)

    def test_exports_retain_failures_and_setfd_operation_unit(self):
        rows = [record(kind='setfd', query='toggle'),
                record(kind='setfd', query='toggle', arm='native',
                       execution_status='NOT_RUN', drained=False)]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            expected = write_report(out, rows)
            self.assertEqual(json.loads((out/'summary.json').read_text()), expected)
            with (out/'summary.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 2)
            self.assertNotIn(b'\r', (out/'summary.csv').read_bytes())
            text = (out/'README.md').read_text()
            self.assertIn('1/2 sessions', text)
            self.assertIn('one F_SETFD plus a validating F_GETFD', text)
            self.assertIn('Entries/stride', text)


if __name__ == '__main__':
    unittest.main()
