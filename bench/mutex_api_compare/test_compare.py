"""Guest-only tests for immutable input selection and matched comparison gates."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
import subprocess

import run
import report


class ComparisonTests(unittest.TestCase):
    def test_retained_program_copy_can_restore_execute_bit_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source, binary = folder/'program.c', folder/'program'
            source.write_text('int main(void) { return 0; }\n')
            subprocess.run(['gcc', str(source), '-o', str(binary)], check=True,
                           capture_output=True)
            digest = run.sha(binary)
            binary.chmod(0o644)
            result = run.executable_copy(binary)
            self.assertEqual(result['mode_before'], '0o644')
            self.assertEqual(result['mode_after'], '0o744')
            self.assertEqual(run.sha(binary), digest)
            module = folder/'object.o'
            subprocess.run(['gcc', '-c', str(source), '-o', str(module)], check=True,
                           capture_output=True)
            with self.assertRaisesRegex(ValueError, 'executable'):
                run.executable_copy(module)

    def test_full_grid_has_three_matched_rotated_rounds_without_duplicates(self):
        plan = run.execution_order()
        self.assertEqual(len(plan), 7 * 21 * 3 * 4)
        self.assertEqual(len(set(plan)), len(plan))
        self.assertEqual(set(n for _, n, _, _ in plan), set(run.THREADS))
        counts = Counter((w, n, arm) for w, n, _, arm in plan)
        self.assertEqual(set(counts.values()), {3})
        for index in range(0, len(plan), 4):
            self.assertEqual({r[3] for r in plan[index:index+4]}, set(run.ARMS))
        self.assertNotEqual(plan[0][3], plan[4][3])

    def test_frozen_variants_preserve_directories_and_ignore_overwritten_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            run.save(bundle/'binary-sha256.json', {
                '/root/host_fs/kdlock/daemon/daemon': 'daemon-hash',
                '/old/c01/variants/native/mutex_cacheline.ko': 'native-hash',
                '/old/c01/variants/kdlock/mutex_cacheline.ko': 'kd-hash'})
            paths = run.binary_paths(bundle, True)
            self.assertEqual(paths[str(bundle/'binaries/daemon')], 'daemon-hash')
            self.assertEqual(paths[str(bundle/'variants/native/mutex_cacheline.ko')], 'native-hash')
            self.assertEqual(paths[str(bundle/'variants/kdlock/mutex_cacheline.ko')], 'kd-hash')
            run.save(bundle/'binaries.json', {
                'tclock-mutex/provider.ko': dict(path='/old/build/tclock-mutex/provider.ko', sha256='nested'),
                'provider.ko': dict(path='/old/build/provider.ko', sha256='top')})
            self.assertEqual(set(run.binary_paths(bundle, False).values()), {'nested', 'top'})
            run.save(bundle/'binaries.json', {
                '../escape': dict(path='/old/build/../escape', sha256='bad')})
            with self.assertRaises(ValueError):
                run.binary_paths(bundle, False)

    @staticmethod
    def record(arm, repeat, entries=1, rate=100):
        return dict(comparison_workload='c01', threads=1, comparison_arm=arm,
            arm='kdlock' if arm.endswith('-kd') else arm, repeat=repeat, cpus=[0],
            source_identity=arm, caller_shell=arm, cookie_storage=arm,
            execution_status='OK', drained=True, jit_bodies=entries,
            measurement=dict(complete=True, data_ok=True, completed=rate, wall_ns=1000000000,
                workers=[dict(cpu=0, observed_cpu=0, error=0, completed=rate)],
                peak=dict(throughput_ops_s=rate)))

    def test_mixed_jit_classes_and_missing_repeats_cannot_pass_gate(self):
        rows = [self.record(arm, repeat, entries=int(repeat != 1))
                for arm in run.ARMS for repeat in range(3)]
        summary = report.summarize(rows)
        comparisons = report.comparisons(summary)
        self.assertTrue(comparisons)
        self.assertTrue(all(row['throughput_gate'] == 'INCOMPLETE' for row in comparisons))
        self.assertTrue(all(row['p95_latency_gate'] == 'UNMEASURED' for row in comparisons))

    def test_losses_and_unknown_latency_stay_visible(self):
        rows = [self.record(arm, repeat, rate=80 if arm == 'public-kd' else 100)
                for arm in run.ARMS for repeat in range(3)]
        comparisons = report.comparisons(report.summarize(rows))
        self.assertEqual(len(comparisons), 3)
        self.assertTrue(all(row['whole_median_ratio'] == .8 for row in comparisons))
        self.assertTrue(all(row['loss_exceeds_observed_range'] for row in comparisons))
        self.assertTrue(all(row['overall_acceptance'] == 'OPEN' for row in comparisons))

    def test_undrained_or_zero_progress_records_are_excluded(self):
        row = self.record('public-kd', 0)
        self.assertTrue(report.accepted(row))
        self.assertFalse(report.accepted(dict(row, drained=False)))
        row['measurement']['workers'][0]['completed'] = 0
        self.assertFalse(report.accepted(row))

    def test_unmeasured_counters_and_mismatched_geometry_are_not_inferred(self):
        row = self.record('public-kd', 0)
        del row['jit_bodies']
        self.assertEqual(report.execution_class(row), 'UNMEASURED')
        with self.assertRaisesRegex(ValueError, 'geometry'):
            report.summarize([self.record('public-kd', 0),
                              dict(self.record('native', 0), duration_ms=1000)])


if __name__ == '__main__':
    unittest.main()
