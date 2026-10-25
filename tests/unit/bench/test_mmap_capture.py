"""Mocked evidence failures only: no helper, socket, signal or workload starts."""
import base64
import copy
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/mmap_lock'))
import host_capture_control as control
import host_state

HELPER = b'print("fixture")'
SHA = hashlib.sha256(HELPER).hexdigest()
CAPTURE = dict(complete=True, tasks=[], initial_tids=[], final_tids=[], errors=[])


class Receipts(unittest.TestCase):
    def run_observer(self, *, code=0, failure=None, captures=None, identity_error=None):
        child = MagicMock(pid=9876, returncode=code)
        def consume(child, chunks):
            chunks['stdout'].extend(b'partial\xff')
            chunks['stderr'].extend(b'fixture error')
            if failure:
                raise failure
        with patch.object(control, 'capture', side_effect=captures or
                          [copy.deepcopy(CAPTURE), copy.deepcopy(CAPTURE)]), \
             patch.object(control, 'identity', side_effect=identity_error, return_value={}), \
             patch.object(control.subprocess, 'Popen', return_value=child) as spawn, \
             patch.object(control, 'read_helper', side_effect=consume), \
             patch.object(Path, 'read_text', return_value='fixture'), \
             patch.object(control.os, 'sched_getaffinity', return_value={63}):
            result = control.observe(42, 'command', HELPER, SHA, 11)
        self.assertEqual(spawn.call_count, 1)
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        self.assertFalse(result['accepted'])
        self.assertFalse(result['workload_started'])
        self.assertEqual(base64.b64decode(result['helper_stdout_base64']), b'partial\xff')
        return result

    def test_success_is_diagnostic_only(self):
        r = self.run_observer()
        self.assertTrue(r['passed'])
        self.assertFalse(r['helper_may_still_be_running'])

    def test_nonzero_retains_both_captures(self):
        r = self.run_observer(code=1)
        self.assertFalse(r['passed'])
        self.assertEqual(r['helper_status'], 'exited_nonzero')
        self.assertEqual(r['helper_stderr'], 'fixture error')
        self.assertIn('before', r)
        self.assertIn('after', r)

    def test_endpoint_exception_preserves_exit_and_output(self):
        r = self.run_observer(captures=[copy.deepcopy(CAPTURE), PermissionError('endpoint')])
        self.assertFalse(r['passed'])
        self.assertEqual(r['helper_exit'], 0)
        self.assertIn('endpoint_error', r)
        self.assertIn('before', r)

    def test_incomplete_endpoint_cannot_pass(self):
        bad = dict(CAPTURE, complete=False)
        r = self.run_observer(captures=[CAPTURE, bad])
        self.assertFalse(r['passed'])
        self.assertFalse(r['difference']['complete'])

    def test_final_identity_failure_preserves_captures(self):
        r = self.run_observer(identity_error=ValueError('PID reused'))
        self.assertFalse(r['passed'])
        self.assertIn('final_identity_error', r)
        self.assertIn('after', r)

    def test_timeout_preserves_partial_bytes_and_unknown_drain(self):
        r = self.run_observer(failure=subprocess.TimeoutExpired('fixture', 20))
        self.assertFalse(r['passed'])
        self.assertTrue(r['helper_may_still_be_running'])
        self.assertIn('helper_timeout_ns', r)
        self.assertNotIn('helper_exit', r)

    def test_interrupt_preserves_ownership_and_partial_bytes(self):
        for failure in (KeyboardInterrupt(), InterruptedError('SIGTERM fixture')):
            with self.subTest(failure=failure):
                r = self.run_observer(failure=failure)
                self.assertFalse(r['passed'])
                self.assertTrue(r['helper_may_still_be_running'])
                self.assertEqual(r['helper_status'], 'interrupted')
                self.assertEqual(r['helper_pid'], 9876)

    def test_spawn_failure_does_not_invent_child_or_endpoint(self):
        with patch.object(control, 'capture', return_value=CAPTURE), \
             patch.object(control.subprocess, 'Popen', side_effect=OSError('spawn')), \
             patch.object(Path, 'read_text', return_value='fixture'):
            r = control.observe(42, 'command', HELPER, SHA, 11)
        self.assertFalse(r['passed'])
        self.assertNotIn('helper_pid', r)
        self.assertNotIn('after', r)

    def test_bad_initial_capture_never_spawns(self):
        with patch.object(control, 'capture', return_value=dict(CAPTURE, complete=False)), \
             patch.object(control.subprocess, 'Popen') as spawn:
            r = control.observe(42, 'command', HELPER, SHA, 11)
        spawn.assert_not_called()
        self.assertFalse(r['passed'])


class ProcFixtures(unittest.TestCase):
    @staticmethod
    def stat(tid, start):
        fields = ['S'] + ['0'] * 37
        fields[19], fields[36] = str(start), '63'
        return str(tid) + ' (qemu (fixture)) ' + ' '.join(fields)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name) / '42'
        (self.proc / 'task/42').mkdir(parents=True)
        (self.proc / 'cmdline').write_bytes(b'/usr/bin/qemu-system-x86_64\0fixture\0')
        self.sha = hashlib.sha256((self.proc / 'cmdline').read_bytes()).hexdigest()
        for path in (self.proc / 'stat', self.proc / 'task/42/stat'):
            path.write_text(self.stat(42, 11))
        (self.proc / 'task/42/schedstat').write_text('100 20 3')
        (self.proc / 'task/42/status').write_text('Pid:\t42\nTgid:\t42\n')

    def test_same_arguments_different_start_rejected(self):
        control.identity(self.proc, 11, self.sha)
        (self.proc / 'stat').write_text(self.stat(42, 12))
        with self.assertRaises(ValueError):
            control.identity(self.proc, 11, self.sha)

    def test_foreign_tgid_is_a_partial_failed_capture(self):
        (self.proc / 'task/42/status').write_text('Pid:\t42\nTgid:\t43\n')
        with patch.object(control.os, 'sched_getaffinity', return_value={63}):
            row = control.capture(self.proc, 11, self.sha)
        self.assertFalse(row['complete'])
        self.assertFalse(row['tasks'][0]['complete'])
        self.assertIn('membership', row['errors'][0]['error'])

    def test_disappearing_task_retains_partial_row(self):
        (self.proc / 'task/43').mkdir()
        with patch.object(control.os, 'sched_getaffinity', return_value={63}):
            r = control.capture(self.proc, 11, self.sha)
        self.assertFalse(r['complete'])
        self.assertTrue(r['equal_observed_tid_lists'])
        self.assertEqual(len(r['tasks']), 2)
        self.assertFalse(r['tasks'][1]['complete'])

    def test_identity_rechecked_after_scan(self):
        with patch.object(control.os, 'sched_getaffinity', return_value={63}), \
             patch.object(control, 'identity', side_effect=[{}, ValueError('new start')]) as check:
            r = control.capture(self.proc, 11, self.sha)
        self.assertEqual(check.call_count, 2)
        self.assertFalse(r['complete'])
        self.assertTrue(r['tasks'][0]['complete'])

    def test_runtime_never_compares_reused_tid(self):
        old = dict(complete=True, tasks=[dict(tid=42, start_ticks=11, complete=True,
                   comm='qemu', runtime_ns=500)])
        new = copy.deepcopy(old)
        new['tasks'][0].update(start_ticks=12, runtime_ns=1)
        r = control.compare(old, new)
        self.assertEqual(r['runtime_delta_ns'], [])
        self.assertEqual(len(r['added']), 1)
        self.assertEqual(len(r['removed']), 1)


class Monitor(unittest.TestCase):
    def test_eof_is_immediate_failure(self):
        sock = MagicMock()
        sock.recv.return_value = b''
        with self.assertRaises(EOFError):
            host_state.read_prompt(sock, host_state.time.monotonic() + 1)
        self.assertEqual(sock.recv.call_count, 1)

    def test_total_deadline_binds_prompt(self):
        sock = MagicMock()
        sock.recv.return_value = b'incomplete'
        with patch.object(host_state.time, 'monotonic', side_effect=[1, 3]):
            with self.assertRaises(TimeoutError):
                host_state.read_prompt(sock, 2)
        self.assertEqual(sock.recv.call_count, 1)

    def test_own_socket_closes_on_banner_failure(self):
        context = MagicMock()
        context.__enter__.return_value.recv.return_value = b''
        with patch.object(host_state.socket, 'socket', return_value=context):
            with self.assertRaises(EOFError):
                host_state.snapshots()
        context.__exit__.assert_called_once()
        context.__enter__.return_value.sendall.assert_not_called()


if __name__ == '__main__':
    unittest.main()
