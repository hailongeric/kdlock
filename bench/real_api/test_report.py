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
    def test_source_and_protocol_variants_never_pool(self):
        for changes in (dict(source_identity='other-source'),
                        dict(entry_abi=4), dict(mutex_implementation='owned-v1'),
                        dict(caller_shell='mutex_public_direct'),
                        dict(cookie_storage='provider_acquisition_ledger'),
                        dict(cpus=[2, 3]), dict(pmu=True), dict(mutex_lock_offset=40)):
            rows = [record(kind='pipebytes', query='query', source_identity='current',
                           entry_abi=2, mutex_implementation='kd-only-legacy', cpus=[0, 1])]
            rows.append(dict(rows[0], **changes))
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temporary:
                self.assertEqual(len(summarize(rows)), 2)
                with self.assertRaisesRegex(ValueError, 'distinct'):
                    write_report(Path(temporary), rows)

    def test_backend_comparison_requires_matching_source_and_placement(self):
        for changes in (dict(source_identity='other-source'), dict(cpus=[2, 3]),
                        dict(collector_cpu=3), dict(duration_ms=5000)):
            rows = [record(source_identity='current', cpus=[0, 1], collector_cpu=63,
                           duration_ms=2000)]
            rows.append(dict(rows[0], arm='native', **changes))
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(ValueError, 'cannot compare'):
                    write_report(Path(temporary), rows)

    def test_protocol_cannot_change_between_thread_counts(self):
        for changes in (dict(entry_abi=4), dict(mutex_lock_offset=40)):
            rows = [record(entry_abi=2), record(threads=4, entry_abi=2) | changes]
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(ValueError, 'across cohorts'):
                    write_report(Path(temporary), rows)

    def test_instrumented_syscall_records_are_unscored(self):
        row, = summarize([record(diagnostic=True)])
        self.assertEqual((row['accepted'], row['diagnostics']), (0, 1))
        self.assertIsNone(row['whole_median'])

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

    def test_completion_groups_are_not_pooled(self):
        rows = [record(whole=10, jit_evidence_version=2, jit_completions=4),
                record(whole=20, jit_evidence_version=2, jit_completions=0),
                record(whole=30, jit_evidence_version=2, jit_bodies=0, jit_completions=0)]
        groups = {r['execution_group']: r for r in summarize(rows)}
        self.assertEqual(set(groups), {'PASS', 'PARTIAL_JIT', 'NO_JIT'})
        self.assertEqual(groups['PASS']['whole_median'], 10)
        self.assertEqual(groups['PARTIAL_JIT']['whole_median'], 20)
        self.assertEqual(groups['NO_JIT']['whole_median'], 30)
        self.assertEqual(groups['PASS']['jit_completions'], 4)
        self.assertEqual(groups['PASS']['jit_complete_share'], .4)
        with tempfile.TemporaryDirectory() as temporary:
            write_report(Path(temporary), rows)
            text = (Path(temporary)/'README.md').read_text()
            for group in groups:
                self.assertIn('| '+group+' |', text)

    def test_historical_entry_counts_remain_unknown_completions(self):
        row, = summarize([record()])
        self.assertEqual(row['execution_group'], 'LEGACY_ENTRY_ONLY')
        self.assertIsNone(row['jit_completions'])
        self.assertIsNone(row['jit_complete_positive'])
        self.assertIsNone(row['jit_complete_share'])

    def test_different_completion_instrumentation_never_pools(self):
        rows = [record(jit_evidence_version=2, jit_completions=4, jit_completion_probe=True),
                record(jit_evidence_version=2, jit_completions=4, jit_completion_probe=False)]
        self.assertEqual(len(summarize(rows)), 2)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'distinct'):
                write_report(Path(temporary), rows)

    def test_impossible_returned_body_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'completion'):
            summarize([record(jit_evidence_version=2, jit_completions=5)])

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
