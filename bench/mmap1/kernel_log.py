"""Continuous diagnostic collection for one retained nonblocking kmsg fd."""
import errno
import json
import os
from pathlib import Path
import shutil
import threading
import time

MAX_BYTES = 256 * 1024 * 1024
HEADROOM_BYTES = 64 * 1024 * 1024


class DiagnosticKernelLog:
    def __init__(self, fd, directory, fault_pattern, *, max_bytes=MAX_BYTES, cpu=63):
        self.fd, self.directory, self.fault_pattern = fd, Path(directory), fault_pattern
        self.max_bytes, self.cpu = max_bytes, cpu
        self.bytes = self.records = self.errors = 0
        self.first_error = self.last_error = None
        self.fault = False
        self.exhausted = False
        self.started = False
        self.tail = ''
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

    def _run(self):
        try:
            with (self.directory / 'kernel.log').open('xb', buffering=0) as output, \
                 (self.directory / 'kernel-log-errors.jsonl').open('xb', buffering=0) as errors:
                if self.cpu is not None:
                    os.sched_setaffinity(0, {self.cpu})
                self.ready.set()
                while True:
                    if self.stop_deadline is not None and time.monotonic() >= self.stop_deadline:
                        self._error(TimeoutError('diagnostic final drain exceeded its deadline'), errors)
                        break
                    try:
                        raw = os.read(self.fd, 1 << 20)
                    except BlockingIOError:
                        if self.stop.is_set():
                            break
                        self.stop.wait(0.005)
                        continue
                    except InterruptedError:
                        continue
                    except OSError as error:
                        self._error(error, errors)
                        if error.errno != errno.EPIPE:
                            break
                        # kmsg advances past a lost range on EPIPE. Retain the
                        # loss and all subsequent available records, but fail.
                        time.sleep(0.005)
                        continue
                    if not raw:
                        break
                    self._write(output, raw)
                    self.records += 1
                    text = self.tail + raw.decode(errors='replace')
                    self.fault |= bool(self.fault_pattern.search(text))
                    self.tail = text[-256:]
        except BaseException as error:
            self._error(error)
        finally:
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
