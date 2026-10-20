"""Guest-only parser and placement checks; no live host process is sampled."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import host_observer as observer
import clock_calibration as calibration


def stat(tid=123, comm='worker', start=456, cpu=63):
    fields = ['0']*50
    fields[0], fields[11], fields[12], fields[19], fields[36] = (
        'S', '7', '9', str(start), str(cpu))
    return f'{tid} ({comm}) '+' '.join(fields)+'\n'


class ObserverTests(unittest.TestCase):
    def test_clock_projection_uses_both_network_bounds(self):
        row = dict(source_before_ns=1000, source_after_ns=1020,
                   target_clock=dict(monotonic_ns=200))
        self.assertEqual(calibration.offset_bounds(row), [800, 820])
        self.assertEqual(calibration.project_interval(100, 200, [800, 820], [300, 330]),
                         [570, 720])
        with self.assertRaises(ValueError):
            calibration.project_interval(200, 100, [800, 820], [300, 330])
        with self.assertRaises(ValueError):
            calibration.offset_bounds(dict(row, source_after_ns=900))

    def test_proc_stat_parentheses_and_field_offsets(self):
        self.assertEqual(observer.stat_fields(stat(comm='worker (io)')),
                         dict(tid=123, comm='worker (io)', state='S', user_ticks=7,
                              system_ticks=9, start_ticks=456, last_cpu=63))
        for value in ('123 no parentheses', '123 (worker) S 0'):
            with self.assertRaises(ValueError):
                observer.stat_fields(value)

    def test_thread_sample_retains_exact_identity_and_accounting(self):
        with tempfile.TemporaryDirectory() as temporary:
            task = Path(temporary)
            (task/'stat').write_text(stat())
            (task/'schedstat').write_text('1000000 250000 3\n')
            row = observer.thread_sample(task, lambda tid: {63})
            self.assertEqual((row['runtime_ns'], row['runqueue_wait_ns'], row['timeslices']),
                             (1000000, 250000, 3))
            self.assertEqual(row['affinity'], [63])
            with patch.object(Path, 'read_text', side_effect=[
                    stat(), '1000000 250000 3', stat(start=457)]):
                with self.assertRaises(ProcessLookupError):
                    observer.thread_sample(task, lambda tid: {63})

    def test_wrong_affinity_missing_vcpu_and_duplicate_are_not_ignored(self):
        tasks = [dict(tid=i, comm=f'CPU {i}/KVM', affinity=[i]) for i in range(64)]
        tasks += [dict(tid=100, comm='qemu-system-x86', affinity=[63])]
        self.assertEqual(observer.placement_issues(tasks), [])
        self.assertTrue(observer.placement_issues(tasks[1:]))
        self.assertTrue(observer.placement_issues(tasks+[tasks[0]]))
        self.assertTrue(observer.placement_issues(tasks+[
            dict(tid=101, comm='worker', affinity=[62])]))
        # Dynamic workers stay in the sample. Correct placement does not claim
        # they were absent or that the original exact thread set still matches.
        self.assertEqual(observer.placement_issues(tasks+[
            dict(tid=101, comm='worker', affinity=[63])]), [])


if __name__ == '__main__':
    unittest.main()
