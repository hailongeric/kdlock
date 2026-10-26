"""Narrow aggregate/peak distinction; no module or workload execution."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'bench/mmap_lock'))
import aggregate


def fixture(peak=True):
    start = 1000000000
    deadline = start + 2000000000
    identity = dict(object=1, mm=2, mmap_lock=3, tid=1, tgid=1)
    before = dict(object=1, maps=0, closes=0, clones=0, vmas=0, faults=0,
                  context_errors=0, foreign_rejects=0, contended_mmaps=0, observe=0)
    workers = [dict(cpu=i, observed_cpu=i, identity=dict(identity, tid=i+2), error=0,
        completed=1024, cpu_ns=1000000, active_started_ns=start,
        kernel_finished_ns=deadline+50, finished_ns=deadline+100+i,
        latency_ns=[]) for i in range(2)]
    m = dict(event='measurement', complete=True, data_ok=True, workload='mmap-shared-mm',
        threads=2, joined=2, observation='plain', workers=workers, completed=2048,
        worker_cpu_ns=2000000, started_ns=start, deadline_ns=deadline,
        finished_ns=deadline+101, wall_ns=2000000101, duration_ns=2000000000,
        peak_window_ns=300000000, peak_settle_ns=300000000, sample_period_ns=10000000,
        collector_cpu=63, collector_observed_cpu=63, collector_error=0, progress_batch=256,
        before=before, after=dict(before, maps=2048, closes=2048),
        samples=[dict(started_ns=start+i*10000000, finished_ns=start+i*10000000+1,
                      completed=[(i//50)*256 if peak else 0]*2) for i in range(201)])
    return [dict(event='ready', identity=identity), m], aggregate.paired.writer.spec(2, 'plain', 0)


class Aggregate(unittest.TestCase):
    def test_available_peak_and_actual_denominator(self):
        rows, spec = fixture()
        r = aggregate.validate(rows, spec)
        self.assertEqual(r['peak_status'], 'available')
        self.assertEqual(r['pairs_s'], 2048 * 1e9 / 2000000101)
        self.assertFalse(r['paired_campaign_accepted'])

    def test_missing_peak_does_not_erase_aggregate(self):
        rows, spec = fixture(False)
        r = aggregate.validate(rows, spec)
        self.assertTrue(r['aggregate_valid'])
        self.assertEqual(r['peak_status'], 'unavailable')
        self.assertEqual(r['completed_pairs'], 2048)
        with self.assertRaisesRegex(ValueError, '^no positive full-cohort peak window$'):
            aggregate.paired.writer.validate(rows, spec)

    def test_errors_identity_affinity_accounting_and_timing_still_fail(self):
        edits = [lambda m: m['workers'][0].update(error=1),
                 lambda m: m['workers'][0]['identity'].update(mm=999),
                 lambda m: m['workers'][0].update(observed_cpu=63),
                 lambda m: m['after'].update(closes=0),
                 lambda m: m.update(joined=1),
                 lambda m: m.update(wall_ns=2000000000),
                 lambda m: m.update(deadline_ns=0),
                 lambda m: m['samples'][1].update(completed=[2049, 0]),
                 lambda m: m['workers'][0].update(latency_ns=[1])]
        for edit in edits:
            rows, spec = fixture(False)
            edit(rows[1])
            with self.subTest(edit=edit), self.assertRaises((ValueError, aggregate.paired.rt.Failure)):
                aggregate.validate(rows, spec)

    def test_other_exceptions_propagate(self):
        rows, spec = fixture(False)
        with patch.object(aggregate.paired.writer, 'validate', side_effect=ValueError('bad progress')):
            with self.assertRaisesRegex(ValueError, 'bad progress'):
                aggregate.validate(rows, spec)


if __name__ == '__main__':
    unittest.main()
