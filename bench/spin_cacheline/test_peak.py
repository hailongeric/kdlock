"""Focused guest tests for timed accounting and raw-sample peak selection."""
import copy
import unittest

import bench_runtime as runtime
from peak import analyze_peak


MS = 1000000


def fixture():
    spec = dict(cachelines=1, threads=2, cpus=[2, 7], workload='cacheline',
                duration_ms=1000, peak_window_ms=300, peak_settle_ms=100,
                sample_ms=100, collector_cpu=30)
    workers = [dict(cpu=cpu, observed_cpu=cpu, error=0, completed=completed,
                    cpu_ns=900 * MS, active_started_ns=start * MS,
                    kernel_finished_ns=finish * MS, finished_ns=(finish + 10) * MS)
               for cpu, completed, start, finish in
               ((2, 2816, 110, 1110), (7, 5376, 120, 1120))]
    measurement = dict(schema=2, measurement_mode='duration', complete=True,
        data_ok=True, workload='cacheline', cachelines=1, threads=2, iterations=0,
        completed=8192, worker_cpu_ns=1800 * MS, started_ns=100 * MS,
        finished_ns=1130 * MS, wall_ns=1030 * MS, deadline_ns=1100 * MS,
        duration_ns=1000 * MS, peak_window_ns=300 * MS, peak_settle_ns=100 * MS,
        sample_period_ns=100 * MS, collector_cpu=30, collector_observed_cpu=30,
        collector_error=0, progress_batch=256,
        before=[17] * 16, after=[8209] + [17] * 15, workers=workers,
        samples=[dict(started_ns=(200 + i * 100) * MS,
                      finished_ns=(200 + i * 100) * MS,
                      completed=[(i + 1) * 256, (i + 1) * 512]) for i in range(10)])
    return spec, measurement


class PeakTests(unittest.TestCase):
    def test_exact_variable_totals_and_earliest_tied_window(self):
        spec, measurement = fixture()
        saved = copy.deepcopy(measurement)
        peak = runtime.validate_measurement(measurement, spec, 0)
        self.assertEqual(measurement, saved)  # Raw client evidence is immutable.
        self.assertEqual((peak['start_sample_index'], peak['end_sample_index']), (1, 4))
        self.assertEqual((peak['completed'], peak['worker_completed']), (2304, [768, 1536]))
        self.assertEqual(peak['elapsed_ns'], 300 * MS)
        self.assertEqual(peak['throughput_ops_s'], 7680)
        self.assertEqual(peak['amortized_ns_op'], 300 * MS / 2304)
        self.assertEqual(peak['eligible_started_ns'], 220 * MS)
        self.assertEqual(peak['active_finished_ns'], 1100 * MS)
        self.assertEqual(peak['progress_count_error_bound'], 512)

    def test_hash_timing_preserves_outcome_and_structure_checks(self):
        spec, measurement = fixture()
        spec.update(workload='rcuht', cachelines=0)
        measurement.update(workload='rcuht', cachelines=0, hash_integrity_ok=True,
            before=[3, 1, 1, 1] + [0]*12,
            after=[8195, 2049, 2049, 4097] + [0]*12)
        peak = runtime.validate_measurement(measurement, spec, 0)
        self.assertEqual(peak['completed'], 2304)
        for change in (
            lambda m: m['after'].__setitem__(1, m['after'][1] - 1),
            lambda m: m['after'].__setitem__(0, m['after'][0] + 1),
            lambda m: m['after'].__setitem__(4, 1),
            lambda m: m.update(hash_integrity_ok=False),
            lambda m: m.update(workload='cacheline'),
        ):
            broken = copy.deepcopy(measurement)
            change(broken)
            with self.assertRaises(runtime.Failure):
                runtime.validate_measurement(broken, spec, 0)

    def test_actual_brackets_and_delayed_samples_without_interpolation(self):
        spec, measurement = fixture()
        measurement['samples'] = [dict(started_ns=begin * MS, finished_ns=end * MS,
                                      completed=counts) for begin, end, counts in
            ((230, 232, [256, 512]), (520, 522, [512, 1024]),
             (535, 537, [768, 1536]), (840, 842, [1024, 2048]))]
        peak = analyze_peak(measurement, spec)
        self.assertEqual((peak['start_sample_index'], peak['end_sample_index']), (0, 2))
        self.assertEqual(peak['elapsed_ns'], 307 * MS)
        self.assertEqual(peak['completed'], 1536)
        self.assertEqual(peak['throughput_ops_s'], 1536 * 1e9 / (307 * MS))
        self.assertEqual(peak['max_snapshot_span_ns'], 2 * MS)
        self.assertEqual(peak['start_snapshot_span_ns'], 2 * MS)
        self.assertEqual(peak['end_snapshot_span_ns'], 2 * MS)

    def test_start_settle_and_deadline_exclude_partial_cohort_samples(self):
        spec, measurement = fixture()
        # Large progress jumps before settling and after the deadline cannot
        # become a peak, even when the final payload is correct.
        for sample in measurement['samples']:
            sample['completed'] = [sample['completed'][0] + 10000,
                                   sample['completed'][1] + 10000]
        measurement['workers'][0]['completed'] = 50000
        measurement['workers'][1]['completed'] = 60000
        measurement['samples'].append(dict(started_ns=1130 * MS,
            finished_ns=1131 * MS, completed=[50000, 60000]))
        peak = analyze_peak(measurement, spec)
        self.assertEqual((peak['start_sample_index'], peak['end_sample_index']), (1, 4))
        self.assertEqual(peak['throughput_ops_s'], 7680)
        measurement['samples'][1]['started_ns'] = 219 * MS
        peak = analyze_peak(measurement, spec)
        self.assertEqual(peak['start_sample_index'], 2)

    def test_final_accounting_rejects_wrong_payload_and_worker_results(self):
        spec, measurement = fixture()
        changes = (
            lambda m: m.update(completed=m['completed'] + 1),
            lambda m: m['after'].__setitem__(0, m['after'][0] + 1),
            lambda m: m['after'].__setitem__(1, m['after'][1] + 1),
            lambda m: m['workers'][0].update(observed_cpu=7),
            lambda m: m['workers'][0].update(error=1),
            lambda m: m.update(worker_cpu_ns=m['worker_cpu_ns'] + 1),
            lambda m: m['workers'][0].update(kernel_finished_ns=1099 * MS),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                altered = copy.deepcopy(measurement)
                change(altered)
                with self.assertRaises(runtime.Failure):
                    runtime.validate_measurement(altered, spec, 0)

    def test_invalid_progress_and_timing_are_rejected(self):
        spec, measurement = fixture()
        changes = (
            lambda m: m.update(collector_cpu=2),
            lambda m: m.update(collector_observed_cpu=2),
            lambda m: m.update(deadline_ns=m['deadline_ns'] + 1),
            lambda m: m.update(progress_batch=128),
            lambda m: m['samples'][2]['completed'].__setitem__(0, 1),
            lambda m: m['samples'][-1]['completed'].__setitem__(0, 2817),
            lambda m: m['samples'][2].update(started_ns=299 * MS),
            lambda m: m['samples'][2].update(completed=[768]),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                altered = copy.deepcopy(measurement)
                change(altered)
                with self.assertRaises(ValueError):
                    analyze_peak(altered, spec)

    def test_late_worker_or_missing_window_cannot_pass(self):
        spec, measurement = fixture()
        measurement['workers'][1]['active_started_ns'] = 850 * MS
        with self.assertRaisesRegex(ValueError, 'full-cohort interval'):
            analyze_peak(measurement, spec)
        spec, measurement = fixture()
        measurement['samples'] = measurement['samples'][-2:]
        with self.assertRaisesRegex(ValueError, 'peak window'):
            analyze_peak(measurement, spec)

    def test_window_requires_progress_from_every_worker(self):
        spec, measurement = fixture()
        for sample in measurement['samples']:
            sample['completed'][1] = 0
        with self.assertRaisesRegex(ValueError, 'peak window'):
            analyze_peak(measurement, spec)


if __name__ == '__main__':
    unittest.main()
