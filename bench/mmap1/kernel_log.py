"""Continuous diagnostic collection for one retained nonblocking kmsg fd."""
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time

MAX_BYTES = 256 * 1024 * 1024
HEADROOM_BYTES = 64 * 1024 * 1024


class DiagnosticKernelLog:
    def __init__(self, fd, directory, fault_pattern, *, max_bytes=MAX_BYTES, cpu=63,
                 fault_check=None):
        self.fd, self.directory, self.fault_pattern = fd, Path(directory), fault_pattern
        self.fault_check = fault_check or fault_pattern.search
        self.max_bytes, self.cpu = max_bytes, cpu
        self.bytes = self.records = self.errors = 0
        self.first_error = self.last_error = None
        self.fault = False
        self.exhausted = False
        self.started = False
        self.tail = ''
        self.scan_pending = []
        self.scan_bytes = 0
        self.raw_bytes = 0
        self.checkpoint_lock = threading.Lock()
        self.checkpoint_requested = threading.Event()
        self.checkpoint_ready = threading.Event()
        self.checkpoint_value = None
        self.record_buffer = bytearray(1 << 20)
        self.record_view = memoryview(self.record_buffer)
        self.read_buffers = [self.record_buffer]
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.stop_deadline = None
        self.thread = threading.Thread(target=self._run, name='mmap1-kmsg', daemon=True)

    def start(self):
        if shutil.disk_usage(self.directory).free < self.max_bytes + HEADROOM_BYTES:
            error = OSError(errno.ENOSPC, 'diagnostic log budget and headroom unavailable')
            self._error(error)
            raise error
        try:
            self.thread.start()
        except BaseException as error:
            self._error(error)
            raise
        self.started = True
        if not self.ready.wait(2):
            error = TimeoutError('diagnostic kmsg reader did not start within two seconds')
            self._error(error)
            raise error
        if self.first_error:
            raise OSError('diagnostic kmsg reader startup: ' + self.first_error['error'])

    def _write(self, stream, data):
        if self.bytes + len(data) > self.max_bytes:
            self.exhausted = True
            raise OSError(errno.ENOSPC, 'diagnostic log byte budget exhausted')
        remaining = memoryview(data)
        while remaining:
            count = stream.write(remaining)
            if not count:
                raise OSError(errno.EIO, 'diagnostic log write made no progress')
            self.bytes += count
            remaining = remaining[count:]

    def _error(self, error, stream=None):
        row = dict(error=repr(error)[:4096], errno=getattr(error, 'errno', None),
                   bytes=self.bytes, records=self.records, monotonic_ns=time.monotonic_ns())
        self.errors += 1
        self.first_error = self.first_error or row
        self.last_error = row
        if stream is not None:
            self._write(stream, (json.dumps(row, sort_keys=True) + '\n').encode())

    def _scan(self):
        if not self.scan_pending:
            return
        text = self.tail + ''.join(self.scan_pending)
        self.fault |= bool(self.fault_check(text))
        self.tail = text[-256:]
        self.scan_pending.clear()
        self.scan_bytes = 0

    def _checkpoint(self, output):
        if not self.checkpoint_requested.is_set():
            return
        self._scan()
        output.flush()
        self.checkpoint_value = dict(log=str(self.directory / 'kernel.log'),
            raw_offset=self.raw_bytes, records=self.records, errors=self.errors,
            first_error=self.first_error, last_error=self.last_error,
            fault_detected=self.fault, exhausted=self.exhausted,
            active=self.started and not self.stop.is_set(), monotonic_ns=time.monotonic_ns())
        self.checkpoint_requested.clear()
        self.checkpoint_ready.set()

    def checkpoint(self, timeout=2):
        """Acknowledge a scanned, flushed boundary after draining available records."""
        with self.checkpoint_lock:
            if not self.started or not self.thread.is_alive() or self.stop.is_set():
                raise RuntimeError('diagnostic checkpoint requires an active collector')
            self.checkpoint_ready.clear()
            self.checkpoint_requested.set()
            if not self.checkpoint_ready.wait(timeout):
                raise TimeoutError('diagnostic checkpoint was not acknowledged')
            return dict(self.checkpoint_value)

    def copy_window(self, begin, directory, *, max_bytes=MAX_BYTES):
        """Retain a fixed application interval without stopping the model reader."""
        end = self.checkpoint()
        if begin['log'] != end['log'] or not 0 <= begin['raw_offset'] <= end['raw_offset']:
            raise ValueError('diagnostic window boundaries do not belong to this collector')
        length = end['raw_offset'] - begin['raw_offset']
        if length > max_bytes:
            raise OSError(errno.ENOSPC, 'diagnostic application window exceeds its byte budget')
        target = Path(directory) / 'kernel.log'
        remaining, digest = length, hashlib.sha256()
        with Path(end['log']).open('rb') as source, target.open('xb', buffering=64 * 1024) as output:
            source.seek(begin['raw_offset'])
            while remaining:
                data = source.read(min(remaining, 1 << 20))
                if not data:
                    raise OSError(errno.EIO, 'flushed diagnostic window ended before its boundary')
                output.write(data)
                digest.update(data)
                remaining -= len(data)
        return dict(mode='continuous-diagnostic-window', drained=False, window_finished=True,
            collector_running=self.thread.is_alive(),
            complete=begin['active'] and end['active'] and not end['errors'] and not end['exhausted'],
            bytes=length, records=end['records'] - begin['records'], errors=end['errors'],
            first_error=end['first_error'], last_error=end['last_error'],
            fault_detected=end['fault_detected'], max_bytes=max_bytes, collector_cpu=self.cpu,
            log=str(target), sha256=digest.hexdigest(), source_log=end['log'],
            source_begin=begin, source_end=end,
            error_log=str(self.directory / 'kernel-log-errors.jsonl'))

    def _run(self):
        try:
            with (self.directory / 'kernel.log').open('xb', buffering=64 * 1024) as output, \
                 (self.directory / 'kernel-log-errors.jsonl').open('xb', buffering=64 * 1024) as errors:
                if self.cpu is not None:
                    os.sched_setaffinity(0, {self.cpu})
                self.ready.set()
                while True:
                    if self.stop_deadline is not None and time.monotonic() >= self.stop_deadline:
                        self._error(TimeoutError('diagnostic final drain exceeded its deadline'), errors)
                        break
                    try:
                        count = os.readv(self.fd, self.read_buffers)
                    except BlockingIOError:
                        self._scan()
                        self._checkpoint(output)
                        if self.stop.is_set():
                            break
                        self.stop.wait(0.005)
                        continue
                    except InterruptedError:
                        continue
                    except OSError as error:
                        self._scan()
                        self._error(error, errors)
                        if error.errno != errno.EPIPE:
                            break
                        # kmsg advances past a lost range on EPIPE. Retain the
                        # loss and all subsequent available records, but fail.
                        continue
                    if not count:
                        break
                    raw = bytes(self.record_view[:count])
                    self._write(output, raw)
                    self.raw_bytes += count
                    self.records += 1
                    self.scan_pending.append(raw.decode(errors='replace'))
                    self.scan_bytes += count
                    if self.scan_bytes >= 64 * 1024:
                        self._scan()
        except BaseException as error:
            self._error(error)
        finally:
            try:
                self._scan()
            except BaseException as error:
                self._error(error)
            self.ready.set()

    def finish(self, timeout=2):
        self.stop_deadline = time.monotonic() + timeout
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(timeout + 0.1)
        drained = not self.thread.is_alive()
        if not drained:
            self._error(TimeoutError('diagnostic reader join did not prove drain'))
        return dict(mode='continuous-diagnostic', drained=drained,
                    complete=self.started and drained and not self.errors and not self.exhausted,
                    bytes=self.bytes, records=self.records, errors=self.errors,
                    first_error=self.first_error, last_error=self.last_error,
                    fault_detected=self.fault, max_bytes=self.max_bytes,
                    collector_cpu=self.cpu, log=str(self.directory / 'kernel.log'),
                    error_log=str(self.directory / 'kernel-log-errors.jsonl'))
