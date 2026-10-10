"""Check that a transient procfs retry cannot turn a failed idle scan into success."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('resume_full_bench',
                                            Path(__file__).with_name('resume_full_bench.py'))
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)


class IdleRetryTest(unittest.TestCase):
    def exited_task(self):
        return FileNotFoundError(2, 'No such file or directory', '/proc/123/task')

    @patch.object(resume.time, 'sleep')
    def test_disappearing_task_requires_a_second_complete_scan(self, sleep):
        with patch('builtins.print'):
            calls = []
            def scan():
                calls.append(1)
                if len(calls) == 1:
                    raise self.exited_task()
                return 'entire scan completed'
            self.assertEqual(resume.verified_idle(scan), 'entire scan completed')
            self.assertEqual(len(calls), 2)
            sleep.assert_called_once_with(0.05)

    @patch.object(resume.time, 'sleep')
    def test_second_scan_still_rejects_a_live_worker(self, sleep):
        calls = []
        def scan():
            calls.append(1)
            if len(calls) == 1:
                raise self.exited_task()
            raise RuntimeError('existing task: sc_worker')
        with patch('builtins.print'), self.assertRaisesRegex(RuntimeError, 'sc_worker'):
            resume.verified_idle(scan)
        self.assertEqual(len(calls), 2)

    @patch.object(resume.time, 'sleep')
    def test_missing_payload_is_never_retried(self, sleep):
        def scan():
            raise FileNotFoundError(2, 'No such file or directory', '/root/workload.ko')
        with self.assertRaises(FileNotFoundError):
            resume.verified_idle(scan)
        sleep.assert_not_called()

    @patch.object(resume.time, 'sleep')
    def test_repeated_task_scan_failures_stop_after_three_attempts(self, sleep):
        calls = []
        def scan():
            calls.append(1)
            raise self.exited_task()
        with patch('builtins.print'), self.assertRaises(FileNotFoundError):
            resume.verified_idle(scan)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)


if __name__ == '__main__':
    unittest.main()
