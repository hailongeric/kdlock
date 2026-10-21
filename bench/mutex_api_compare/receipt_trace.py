#!/usr/bin/env python3
"""Bounded in-memory observation of existing guest evidence writes.

Path methods retain their original arguments, results and exceptions. Logical
bytes are not block I/O or proof of its initiator. Export adds stdout traffic
only after normal drain; the supervisor still captures the endpoint after EOF.
"""
import json
import locale
from pathlib import Path
import sys
import time

MAX_EXPORT = 256 * 1024


def stamp():
    began = time.monotonic_ns()
    return dict(mono_before_ns=began, real_ns=time.time_ns(),
                boot_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                cpu_ns=time.process_time_ns(), mono_ns=time.monotonic_ns())


class ReceiptTrace:
    def __init__(self, root, limit=256, duration_ns=60_000_000_000):
        assert root.is_absolute() and 1 <= limit <= 256 and 0 < duration_ns <= 60_000_000_000
        self.root, self.limit, self.duration_ns = root, limit, duration_ns
        self.encoding = locale.getpreferredencoding(False)
        self.events, self.errors = [], []
        self.dropped = self.overhead_cpu_ns = 0
        self.phase = None
        self.armed = self.closed = False
        self.originals = {}

    def io(self):
        began = stamp()
        text = Path('/proc/self/io').read_text()
        return dict(began=began, finished=stamp(),
                    counters={k: int(v) for k, v in (s.split(':') for s in text.splitlines())})

    def arm(self, token):
        if self.armed or self.closed:
            raise ValueError('receipt trace cannot be renewed')
        self.token, self.started = token, stamp()
        self.baseline = self.io()
        self.armed = True
        try:
            self.install()
        except Exception:
            for name, original in self.originals.items():
                setattr(Path, name, original)
            self.armed, self.closed = False, True
            raise

    def install(self):
        for name in ('write_text', 'write_bytes'):
            original = getattr(Path, name)
            self.originals[name] = original
            def wrapped(path, data, *args, _name=name, _original=original, **kwargs):
                if not self.armed or not path.is_relative_to(self.root):
                    return _original(path, data, *args, **kwargs)
                try:
                    cpu, began = time.process_time_ns(), stamp()
                except Exception as error:
                    self.error(error)
                    return _original(path, data, *args, **kwargs)
                result, failure, error_number = None, None, None
                try:
                    result = _original(path, data, *args, **kwargs)
                    return result
                except BaseException as error:
                    failure = type(error).__name__
                    error_number = getattr(error, 'errno', None)
                    raise
                finally:
                    try:
                        finished = stamp()
                        if _name == 'write_text':
                            encoding = kwargs.get('encoding', args[0] if args else None) or self.encoding
                            errors = kwargs.get('errors', args[1] if len(args) > 1 else None) or 'strict'
                            requested = len(data.encode(encoding, errors))
                            completed = len(data[:result].encode(encoding, errors)) if failure is None else None
                        else:
                            requested = memoryview(data).nbytes
                            completed = result if failure is None else None
                        relative = str(path.relative_to(self.root))
                        if len(relative) > 256:
                            self.error(ValueError('path metadata truncated'))
                        self.append(dict(kind='write', method=_name,
                            path=relative[:256], phase=self.phase,
                            began=began, finished=finished, requested_bytes=requested,
                            completed_bytes=completed, result=result, error=failure, errno=error_number))
                        self.overhead_cpu_ns += max(0, time.process_time_ns()-cpu-
                                                   (finished['cpu_ns']-began['cpu_ns']))
                    except Exception as error:
                        self.error(error)
            setattr(Path, name, wrapped)

    def error(self, error):
        if len(self.errors) < 8:
            self.errors.append(type(error).__name__)

    def append(self, row):
        if len(self.events) >= self.limit or time.monotonic_ns()-self.started['mono_ns'] >= self.duration_ns:
            self.dropped += 1
        else:
            row['sequence'] = len(self.events)
            self.events.append(row)

    def mark(self, kind, label, size=None):
        self.phase = label
        if not self.armed:
            return
        try:
            cpu = time.process_time_ns()
            self.append(dict(kind=kind, label=label, bytes=size, clock=stamp()))
            self.overhead_cpu_ns += time.process_time_ns()-cpu
        except Exception as error:
            self.error(error)

    def freeze(self):
        if not self.armed or self.closed:
            raise ValueError('receipt trace was not active')
        for name, original in self.originals.items():
            setattr(Path, name, original)
        self.armed, self.closed = False, True
        final_io = self.io()
        expired = time.monotonic_ns()-self.started['mono_ns'] >= self.duration_ns
        return dict(event='receipt_trace', schema=1, token=self.token, root=str(self.root),
                    started=self.started, finished=stamp(), baseline_io=self.baseline,
                    final_io=final_io, events=self.events, dropped=self.dropped,
                    errors=self.errors, expired=expired, complete=not (self.dropped or self.errors or expired),
                    observer_cpu_lower_bound_ns=self.overhead_cpu_ns,
                    scope='Logical Path writes only; no fsync or block-I/O causality. '
                          'Open-file/subprocess/copy writes and earlier I/O are not traced.')


def export(trace, *, final_idle, completed, stream=None):
    """No guest file, wait, new connection or process survives the endpoint."""
    if not final_idle or not completed:
        raise ValueError('trace export requires confirmed normal completion and drain')
    stream = sys.stdout if stream is None else stream
    began = stamp()
    data = trace.freeze()
    line = 'KD_RECEIPTS '+json.dumps(data, separators=(',', ':'))+'\n'
    if len(line.encode('utf-8')) > MAX_EXPORT:
        data.update(complete=False, export_oversize=True, events=[])
        line = 'KD_RECEIPTS '+json.dumps(data, separators=(',', ':'))+'\n'
    serialized = stamp()
    stream.write(line)
    stream.flush()
    flushed = stamp()
    # The trailer reports the first envelope's actual send/flush. Its own
    # flush is only bounded by source receipt and subsequent normal SSH EOF.
    trailer = dict(event='receipt_export', token=data['token'], began=began,
                   serialized=serialized, flushed=flushed,
                   envelope_bytes=len(line.encode('utf-8')), complete=data['complete'])
    stream.write('KD_RECEIPT_EXPORT '+json.dumps(trailer, separators=(',', ':'))+'\n')
    stream.flush()


def collect_line(records, line):
    """Retain export errors without skipping normal EOF or the endpoint."""
    prefix = next((p for p in ('KD_RECEIPTS ', 'KD_RECEIPT_EXPORT ') if line.startswith(p)), None)
    if prefix is None:
        return False
    if len(records) >= 3:
        records[-1] = dict(event='receipt_error', error='TooManyRecords')
        return True
    try:
        if len(line.encode('utf-8')) > MAX_EXPORT:
            raise ValueError('oversize receipt export')
        data = json.loads(line[len(prefix):])
        expected = 'receipt_trace' if prefix == 'KD_RECEIPTS ' else 'receipt_export'
        if data.get('event') != expected or any(r.get('event') == expected for r in records):
            raise ValueError('wrong or duplicate receipt export')
        records.append(data)
    except (ValueError, TypeError, AttributeError) as error:
        records.append(dict(event='receipt_error', error=type(error).__name__))
    return True


def export_safely(trace, *, final_idle, completed, stream=None):
    # The original result is already saved and no resources remain. Losing
    # this optional trace must not change the normal exit/endpoint path.
    # Missing/truncated records are rejected by the supervisor AFTER capture.
    try:
        export(trace, final_idle=final_idle, completed=completed, stream=stream)
        return True
    except Exception:
        return False


def validate_export(records, token):
    if ([r.get('event') for r in records] != ['receipt_trace', 'receipt_export'] or
            any(r.get('token') != token or not r.get('complete') for r in records)):
        raise ValueError('missing, incomplete or mismatched receipt export')
    return dict(complete=True, events=len(records[0]['events']), token=token)


def finish_control(finish_guest, capture, retain, records, token):
    """Normal guest exit and the original endpoint precede trace validation."""
    finish_guest()
    capture('endpoint')
    retain(records)
    return validate_export(records, token)
