#!/usr/bin/env python3
"""VM-only observer transparency, bounded failure and endpoint protocol checks."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import receipt_trace as rt


class ReceiptObservation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.trace = None

    def tearDown(self):
        if self.trace and self.trace.armed:
            self.trace.freeze()
        self.tmp.cleanup()

    def start(self, **kwargs):
        self.trace = rt.ReceiptTrace(self.root, **kwargs)
        self.trace.arm('nonce')
        return self.trace

    def test_original_unicode_and_binary_bytes_returns_and_order(self):
        trace = self.start()
        self.assertEqual((self.root/'a').write_text('é\n', encoding='utf-8'), 2)
        self.assertEqual((self.root/'b').write_bytes(memoryview(b'abc')), 3)
        rows = trace.freeze()['events']
        self.assertEqual([(r['path'], r['requested_bytes'], r['completed_bytes'], r['result']) for r in rows],
                         [('a', 3, 3, 2), ('b', 3, 3, 3)])
        self.assertEqual((self.root/'a').read_bytes(), b'\xc3\xa9\n')
        self.assertEqual((self.root/'b').read_bytes(), b'abc')
        self.assertLessEqual(rows[0]['finished']['mono_ns'], rows[1]['began']['mono_before_ns'])

    def test_original_arguments_and_exception_identity_survive(self):
        problem = OSError(28, 'full')
        calls = []
        def fail(path, *args, **kwargs):
            calls.append((path, args, kwargs))
            raise problem
        with patch.object(Path, 'write_text', fail):
            trace = self.start()
            with self.assertRaises(OSError) as caught:
                (self.root/'a').write_text('é', encoding='utf-8', errors='strict')
            self.assertIs(caught.exception, problem)
            self.assertEqual(calls, [(self.root/'a', ('é',), dict(encoding='utf-8', errors='strict'))])
            row, = trace.freeze()['events']
        self.assertEqual(row['requested_bytes'], 2)
        self.assertIsNone(row['completed_bytes'])
        self.assertEqual(row['errno'], 28)

    def test_trace_failure_cannot_suppress_original_write_or_error(self):
        trace = self.start()
        with patch.object(trace, 'append', side_effect=ValueError('observer failed')):
            self.assertEqual((self.root/'a').write_bytes(b'kept'), 4)
            with self.assertRaises(FileNotFoundError):
                (self.root/'missing/a').write_bytes(b'attempted')
        self.assertEqual((self.root/'a').read_bytes(), b'kept')
        self.assertFalse(trace.freeze()['complete'])

    def test_excluded_paths_and_overflow_keep_all_original_effects(self):
        sub = self.root/'evidence'
        sub.mkdir()
        self.trace = rt.ReceiptTrace(sub, limit=1)
        self.trace.arm('nonce')
        for name in ('a', 'b', 'c'):
            (sub/name).write_text(name)
        (self.root/'outside').write_text('outside')
        data = self.trace.freeze()
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['dropped'], 2)
        self.assertFalse(data['complete'])
        self.assertEqual([p.read_text() for p in sorted(sub.iterdir())], ['a', 'b', 'c'])

    def test_clock_failures_preserve_write_and_exception(self):
        trace = self.start()
        original = rt.stamp
        for when in ('begin', 'end'):
            calls = 0
            def bad_stamp():
                nonlocal calls
                calls += 1
                if calls == (1 if when == 'begin' else 2):
                    raise OSError('clock failed')
                return original()
            with patch('receipt_trace.stamp', bad_stamp):
                self.assertEqual((self.root/when).write_text('kept'), 4)
            calls = 0
            with patch('receipt_trace.stamp', bad_stamp), self.assertRaises(FileNotFoundError):
                (self.root/'missing/a').write_text('attempted')
        with patch('receipt_trace.time.process_time_ns', side_effect=OSError('clock')):
            trace.mark('phase-send', 'marker', 1)
        self.assertFalse(trace.freeze()['complete'])

    def test_text_encoding_and_newline_report_logical_bytes(self):
        trace = self.start()
        self.assertEqual((self.root/'a').write_text('é\n', encoding='latin-1', newline='\r\n'), 2)
        row, = trace.freeze()['events']
        self.assertEqual((self.root/'a').read_bytes(), b'\xe9\r\n')
        self.assertEqual(row['completed_bytes'], 2)

    def test_expiry_and_rearm_refuse_without_losing_original_effects(self):
        trace = self.start(duration_ns=1)
        (self.root/'late').write_text('kept')
        data = trace.freeze()
        self.assertTrue(data['expired'])
        self.assertFalse(data['complete'])
        self.assertEqual((self.root/'late').read_text(), 'kept')
        with self.assertRaises(ValueError):
            trace.arm('again')

    def test_export_follows_final_save_and_never_runs_without_normal_drain(self):
        trace, stream = self.start(), io.StringIO()
        (self.root/'result.json').write_text('{"final_idle": true}\n')
        with self.assertRaises(ValueError):
            rt.export(trace, final_idle=False, completed=True, stream=stream)
        self.assertEqual(stream.getvalue(), '')
        rt.export(trace, final_idle=True, completed=True, stream=stream)
        records = []
        for line in stream.getvalue().splitlines(True):
            self.assertTrue(rt.collect_line(records, line))
        self.assertTrue(rt.validate_export(records, 'nonce')['complete'])
        self.assertEqual(records[0]['events'][-1]['path'], 'result.json')
        self.assertLessEqual(records[0]['events'][-1]['finished']['mono_ns'], records[1]['began']['mono_ns'])
        self.assertEqual(records[1]['envelope_bytes'], len(stream.getvalue().splitlines(True)[0].encode()))
        self.assertEqual([p.name for p in self.root.iterdir()], ['result.json'])

    def test_bad_exports_are_retained_until_after_eof_and_endpoint(self):
        valid = [dict(event='receipt_trace', token='nonce', complete=True, events=[]),
                 dict(event='receipt_export', token='nonce', complete=True)]
        lines = ['KD_RECEIPTS '+json.dumps(valid[0]), 'KD_RECEIPT_EXPORT '+json.dumps(valid[1])]
        for attempted in ([], lines[:1], lines+lines[:1], ['KD_RECEIPTS {bad}'],
                          ['KD_RECEIPTS '+('x'*rt.MAX_EXPORT)],
                          [s.replace('nonce', 'wrong') for s in lines]):
            events, records = [], []
            for line in attempted:
                rt.collect_line(records, line)
            with self.assertRaises(ValueError):
                rt.finish_control(lambda: events.append('guest-EOF'), events.append,
                                  lambda r: events.append('retained'), records, 'nonce')
            self.assertEqual(events, ['guest-EOF', 'endpoint', 'retained'])
        records = []
        for _ in range(1000):
            rt.collect_line(records, 'KD_RECEIPTS invalid')
        self.assertLessEqual(len(records), 3)

    def test_export_failures_preserve_normal_exit_and_refuse_diagnostic(self):
        trace = self.start()
        (self.root/'result.json').write_text('{"final_idle": true}\n')
        stream = io.StringIO()
        with patch.object(stream, 'flush', side_effect=OSError('export failed')):
            self.assertFalse(rt.export_safely(trace, final_idle=True, completed=True, stream=stream))
        records = []
        for line in stream.getvalue().splitlines(True):
            rt.collect_line(records, line)
        events = []
        with self.assertRaises(ValueError):
            rt.finish_control(lambda: events.append('normal-guest-exit'), events.append,
                              lambda r: events.append('retained'), records, 'nonce')
        self.assertEqual(events, ['normal-guest-exit', 'endpoint', 'retained'])

    def test_failed_guest_exit_does_not_fabricate_drain_or_endpoint(self):
        events = []
        def uncertain():
            raise TimeoutError('guest still running')
        with self.assertRaises(TimeoutError):
            rt.finish_control(uncertain, events.append, events.append, [], 'nonce')
        self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
