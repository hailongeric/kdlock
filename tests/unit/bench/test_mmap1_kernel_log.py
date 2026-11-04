"""VM-only continuous-reader and actual run_point diagnostic joins."""
from contextlib import ExitStack
import errno
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch

fixture_spec = importlib.util.spec_from_file_location(
    'mmap1_kernel_log_fixture', Path(__file__).with_name('test_mmap1.py'))
fixture = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixture)
bench, output = fixture.bench, fixture.output

logs = bench.kernel_log


def write_burst(fd, data):
    remaining = memoryview(data)
    deadline = time.monotonic() + 2
    while remaining:
        if time.monotonic() >= deadline:
            raise TimeoutError('reader did not drain its own fd during child wait')
        try:
            remaining = remaining[os.write(fd, remaining):]
        except BlockingIOError:
            time.sleep(0.001)


def wait_records(collector, count):
    deadline = time.monotonic() + 2
    while collector.records < count and time.monotonic() < deadline:
        time.sleep(0.001)
    if collector.records < count:
        raise AssertionError('reader did not receive expected records')


class DiagnosticKernelLogTests(unittest.TestCase):
    def test_fast_fault_check_preserves_all_alternatives_and_unicode_rules(self):
        examples = ('BUG:', 'WARNING:', 'kernel panic', 'double fault', 'soft lockup',
                    'hard LOCKUP', 'unable to handle', 'general protection fault',
                    'Oops:', '[ERROR]', '[KD_JIT][ERROR]', 'invariant_failures=1',
                    'invariant_failures=9', 'invariant_failures=0', 'warnings=0',
                    'notWARNING:', 'ordinary record', '\u0131nvariant_failures=1',
                    '\u00e9WARNING:', '\u212aernel panic')
        for example in examples:
            for text in (example, example.lower(), example.upper(), '6; ' + example + '\n'):
                with self.subTest(text=text):
                    self.assertEqual(bench.rt.kernel_fault(text), bool(bench.rt.FAULT.search(text)))

    def test_batch_boundary_and_final_partial_are_scanned(self):
        chunks = [b'x' * (64 * 1024) + b'BU', b'G: final fixture\n']
        for pattern, callback in ((bench.rt.FAULT, bench.rt.kernel_fault),
                                  (re.compile('final fixture'), None)):
            position = 0
            def read(fd, size):
                nonlocal position
                if position == len(chunks):
                    return b''
                value = chunks[position]
                position += 1
                return value
            with self.subTest(pattern=pattern), tempfile.TemporaryDirectory() as name, \
                 patch.object(logs.os, 'readv', side_effect=self.readv_fixture(read)):
                collector = logs.DiagnosticKernelLog(77, name, pattern, cpu=None,
                                                      fault_check=callback)
                collector.start()
                summary = collector.finish()
                self.assertTrue(summary['complete'], summary)
                self.assertTrue(summary['fault_detected'])
                self.assertEqual((Path(name) / 'kernel.log').read_bytes(), b''.join(chunks))

    @staticmethod
    def readv_fixture(reader):
        def readv(fd, buffers):
            data = reader(fd, len(buffers[0]))
            buffers[0][:len(data)] = data
            return len(data)
        return readv

    def test_own_fd_is_drained_before_final_collection_without_losing_bytes(self):
        read_fd, write_fd = os.pipe2(os.O_NONBLOCK)
        data = b'6,1,1,-;diagnostic sequence\n' * 32768
        try:
            with tempfile.TemporaryDirectory() as name:
                collector = logs.DiagnosticKernelLog(read_fd, name, bench.rt.FAULT,
                                                      fault_check=bench.rt.kernel_fault,
                                                      max_bytes=2 << 20, cpu=None)
                collector.start()
                write_burst(write_fd, data)
                summary = collector.finish()
                self.assertTrue(summary['complete'], summary)
                self.assertGreater(summary['records'], 1)
                self.assertEqual((Path(name) / 'kernel.log').read_bytes(), data)
        finally:
            os.close(write_fd)
            os.close(read_fd)

    def test_overrun_is_retained_and_following_records_are_still_collected(self):
        calls = 0
        def read(fd, size):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError(errno.EPIPE, 'lost fixture range')
            if calls == 2:
                return b'6,2,2,-;retained after loss\n'
            raise BlockingIOError()
        with tempfile.TemporaryDirectory() as name, patch.object(
                logs.os, 'readv', side_effect=self.readv_fixture(read)):
            collector = logs.DiagnosticKernelLog(77, name, bench.rt.FAULT, cpu=None,
                                                  fault_check=bench.rt.kernel_fault)
            try:
                collector.start()
            except OSError:
                # An already observed overrun can reach the caller before
                # start returns; collection still preserves following rows.
                pass
            wait_records(collector, 1)
            summary = collector.finish()
            self.assertFalse(summary['complete'])
            self.assertEqual(summary['errors'], 1)
            self.assertEqual((Path(name) / 'kernel.log').read_bytes(), b'6,2,2,-;retained after loss\n')
            errors = [json.loads(row) for row in (Path(name) / 'kernel-log-errors.jsonl').read_text().splitlines()]
            self.assertEqual([row['errno'] for row in errors], [errno.EPIPE])

    def test_fault_and_storage_limit_cannot_become_an_accepted_capture(self):
        for budget, chunks in ((1024, [b'6;BU', b'G: fixture\n']), (32, [b'x' * 64])):
            position = 0
            def read(fd, size):
                nonlocal position
                if position < len(chunks):
                    raw = chunks[position]
                    position += 1
                    return raw
                raise BlockingIOError()
            with self.subTest(budget=budget), tempfile.TemporaryDirectory() as name, \
                 patch.object(logs.os, 'readv', side_effect=self.readv_fixture(read)):
                collector = logs.DiagnosticKernelLog(77, name, bench.rt.FAULT,
                                                      fault_check=bench.rt.kernel_fault,
                                                      max_bytes=budget, cpu=None)
                # The budget case can fail in the reader immediately after
                # readiness; both startup and final summaries must retain it.
                try:
                    collector.start()
                except OSError:
                    self.assertEqual(budget, 32)
                if budget == 1024:
                    wait_records(collector, 2)
                summary = collector.finish()
                self.assertLessEqual(summary['bytes'], budget)
                if budget == 1024:
                    self.assertTrue(summary['fault_detected'])
                    self.assertEqual((Path(name) / 'kernel.log').read_bytes(), b'6;BUG: fixture\n')
                else:
                    self.assertFalse(summary['complete'])
                    self.assertEqual(summary['first_error']['errno'], errno.ENOSPC)

    def test_real_run_point_collects_during_child_wait_and_rejects_fault(self):
        for fault in (False, True):
            read_fd, write_fd = os.pipe2(os.O_NONBLOCK)
            data = b'6,1,1,-;delegated sequence\n' * 32768
            if fault:
                data += b'3,2,2,-;BUG: retained diagnostic fixture\n'
            class Child:
                pid = 700
                def poll(self): return None
                def wait(self, timeout):
                    write_burst(write_fd, data)
                    return 0
                def kill(self): raise AssertionError('forced kill forbidden')
                def terminate(self): raise AssertionError('forced termination forbidden')
            def spawn(command, **kwargs):
                kwargs['stdout'].write(output())
                kwargs['stdout'].flush()
                return Child()
            try:
                with self.subTest(fault=fault), tempfile.TemporaryDirectory() as name, ExitStack() as stack:
                    out = Path(name) / 'point'
                    for target, attribute, options in (
                        (bench, 'idle', {}),
                        (bench, 'capture_workers', {'return_value': [dict(tid=701, start_ticks=99), dict(tid=702, start_ticks=100)]}),
                        (bench, 'task_gone', {'return_value': True}),
                        (bench.os, 'sched_getaffinity', {'return_value': {63}}),
                        (bench.os, 'sched_setaffinity', {}),
                        (bench.os, 'open', {'return_value': read_fd}),
                        (bench.os, 'lseek', {}),
                        (bench.subprocess, 'Popen', {'side_effect': spawn}),
                    ):
                        stack.enter_context(patch.object(target, attribute, **options))
                    inputs = dict(binaries={'threads': '/tmp/mmap1_threads'},
                                  binary_sha256={'threads': 'a' * 64})
                    args = (out, dict(model='threads', workers=2, round=0, nominal_seconds=2), inputs, lambda: None)
                    if fault:
                        with self.assertRaises(bench.rt.Failure):
                            bench.run_point(*args, diagnostic=True)
                    else:
                        bench.run_point(*args, diagnostic=True, diagnostic_log_bytes=512 * 1024**2)
                    result = json.loads((out / 'result.json').read_text())
                    self.assertEqual(result['passed'], not fault)
                    self.assertTrue(result['drained'])
                    self.assertFalse(result['scored'])
                    self.assertTrue(result['kernel_log_collection']['complete'])
                    self.assertEqual(result['kernel_log_collection']['max_bytes'],
                                     logs.MAX_BYTES if fault else 512 * 1024**2)
                    self.assertEqual(result['kernel_log_collection']['fault_detected'], fault)
                    self.assertEqual((out / 'kernel.log').read_bytes(), data)
            finally:
                os.close(write_fd)
                try:
                    os.close(read_fd)
                except OSError:
                    pass


if __name__ == '__main__':
    unittest.main()
