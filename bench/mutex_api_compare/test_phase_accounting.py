#!/usr/bin/env python3
"""Guest-only lifetime, scheduling and accounting-order checks; no host reads."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qemu_trace import AccountingWindow, accounting_scan, capture_with_accounting, periodic_due


def stat(tid, ticks=123):
    fields = ['0']*50
    fields[19] = str(ticks)
    return str(tid)+' (worker) '+' '.join(fields)+'\n'


class PhaseAccounting(unittest.TestCase):
    def test_window_is_opt_in_bounded_and_nonrenewable(self):
        window = AccountingWindow(5_000_000_000)
        self.assertFalse(window.active(100))
        self.assertEqual(window.next_read(100), 5_000_000_100)
        window.arm(100)
        self.assertEqual(window.next_read(100), 250_000_100)
        self.assertTrue(window.active(60_000_000_099))
        self.assertFalse(window.active(60_000_000_100))
        self.assertEqual(window.next_read(60_000_000_100), 65_000_000_100)
        with self.assertRaises(ValueError):
            window.arm(61_000_000_100)

    def test_slow_read_has_no_catchup_and_ready_control_has_priority(self):
        window = AccountingWindow(5_000_000_000)
        window.arm(0)
        self.assertEqual(window.next_read(900_000_000), 1_150_000_000)
        self.assertFalse(periodic_due(900, 800, True, True))
        self.assertTrue(periodic_due(900, 800, True, False))
        self.assertFalse(periodic_due(700, 800, True, False))
        self.assertTrue(periodic_due(900, 800, False, True))

    def test_capture_precedes_accounting_and_failure_cannot_fabricate_it(self):
        events = []
        def capture():
            events.append('full-gate')
            return dict(host='unchanged', capture_finished=42)
        def sample():
            events.append('accounting')
            return 7
        result = capture_with_accounting(capture, sample, True)
        self.assertEqual(events, ['full-gate', 'accounting'])
        self.assertEqual(result, dict(host='unchanged', capture_finished=42, following_sample=7, following_sample_error=None))
        events.clear()
        self.assertNotIn('following_sample', capture_with_accounting(capture, sample, False))
        self.assertEqual(events, ['full-gate'])
        def fail():
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            capture_with_accounting(fail, sample, True)
        self.assertEqual(events, ['full-gate'])
        result = capture_with_accounting(capture, fail, True)
        self.assertEqual(result['host'], 'unchanged')
        self.assertEqual(result['capture_finished'], 42)
        self.assertIsNone(result['following_sample'])
        self.assertEqual(result['following_sample_error'], 'TimeoutError()')

    def fixture(self, base):
        (base/'task/123').mkdir(parents=True)
        task = base/'task/123'
        for name, text in dict(stat=stat(123), comm='worker\n', schedstat='10 20 3\n',
                               io='read_bytes: 4096\nwrite_bytes: 8192\n', wchan='io_schedule\n').items():
            (task/name).write_text(text)
        (base/'io').write_text('read_bytes: 4096\n')
        return task

    def test_exact_identity_accounting_brackets_and_unavailable_file_retained(self):
        with tempfile.TemporaryDirectory() as folder, patch('qemu_trace.os.sched_getaffinity', return_value={63}):
            base = Path(folder)
            self.fixture(base)
            sample = accounting_scan(base)
            row, = sample['tasks']
            self.assertTrue(row['complete'])
            self.assertEqual(row['identity_before'], row['identity_after'])
            self.assertEqual(row['identity_before'], [123, 123])
            self.assertEqual(row['files']['io']['text'], 'read_bytes: 4096\nwrite_bytes: 8192\n')
            self.assertEqual(row['files']['syscall']['status'], 'UNAVAILABLE')
            self.assertLessEqual(sample['scan_began']['mono_ns'], row['read_began']['mono_ns'])
            self.assertLessEqual(row['read_finished']['mono_ns'], sample['scan_finished']['mono_ns'])

    def test_reused_identity_and_departed_task_remain_partial_rows(self):
        with tempfile.TemporaryDirectory() as folder, patch('qemu_trace.os.sched_getaffinity', return_value={63}):
            base = Path(folder)
            task = self.fixture(base)
            original = Path.read_text
            for vanish in (False, True):
                reads = 0
                def changed(path, *args, **kwargs):
                    nonlocal reads
                    if path == task/'stat':
                        reads += 1
                        if reads == 2:
                            if vanish:
                                raise FileNotFoundError('departed during read')
                            return stat(123, 124)
                    return original(path, *args, **kwargs)
                with patch.object(Path, 'read_text', changed):
                    row, = accounting_scan(base)['tasks']
                self.assertFalse(row['complete'])
                self.assertEqual(row['identity_before'], [123, 123])
                self.assertIn('files', row)
                self.assertEqual(row.get('disappeared', False), vanish)


if __name__ == '__main__':
    unittest.main()
