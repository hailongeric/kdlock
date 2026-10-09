#!/usr/bin/env python3
"""Guest client: one kernel ioctl per pinned worker, no Python per-operation loop."""
import argparse
import ctypes
import fcntl
import json
import os
import struct
import threading
import time

from protocol import DEVICE, RUN, RUN_FORMAT, configure, progress, snapshot
from oracle import validate


def run(spec):
    count = spec['threads']
    before = snapshot()
    ready = threading.Barrier(count + 1)
    start = threading.Event()
    state = {}
    rows = [None] * count

    def worker(index, cpu):
        row = dict(cpu=cpu, error=None)
        rows[index] = row
        try:
            os.sched_setaffinity(0, {cpu})
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.prctl(15, b'rb_worker', 0, 0, 0):
                raise OSError(ctypes.get_errno(), 'PR_SET_NAME')
            with open(DEVICE, 'rb', buffering=0) as device:
                ready.wait()
                start.wait()
                if 'started_ns' not in state:
                    return
                buffer = bytearray(struct.pack(RUN_FORMAT, state['started_ns'], state['deadline_ns'],
                    0 if spec['duration_ms'] else spec['iterations'], index, 0, *([0] * 10)))
                cpu_start = time.thread_time_ns()
                fcntl.ioctl(device, RUN, buffer, True)
                row['finished_ns'] = time.monotonic_ns()
                row['cpu_ns'] = time.thread_time_ns() - cpu_start
                values = struct.unpack(RUN_FORMAT, buffer)
                row.update(zip(('completed', 'reads', 'writes', 'read_errors', 'read_hits', 'checksum',
                                'active_started_ns', 'kernel_finished_ns', 'observed_cpu'), values[5:14]))
        except BaseException as error:
            row['error'] = repr(error)
            ready.abort()

    threads = [threading.Thread(target=worker, args=(i, cpu)) for i, cpu in enumerate(spec['cpus'])]
    samples = []
    collector_error = None
    # Pin the collector before creating workers; every worker then sets its own
    # distinct affinity. Preparation never shares a measured worker's CPU.
    os.sched_setaffinity(0, {spec['collector_cpu']})
    for thread in threads:
        thread.start()
    try:
        ready.wait(timeout=15)
        with open(DEVICE, 'rb', buffering=0) as device:
            started = time.monotonic_ns()
            deadline = started + spec['duration_ms'] * 1000000 if spec['duration_ms'] else 0
            configure(device, started, deadline, count, spec['write_percent'])
            state.update(started_ns=started, deadline_ns=deadline)
            start.set()
            if deadline:
                tick = started
                period = spec['sample_ms'] * 1000000
                while any(thread.is_alive() for thread in threads):
                    samples.append(progress(device, started, deadline, count))
                    tick += period
                    now = time.monotonic_ns()
                    if tick <= now:
                        tick += ((now - tick) // period + 1) * period
                    time.sleep(max(0, tick - time.monotonic_ns()) / 1e9)
    except BaseException as error:
        collector_error = repr(error)
        ready.abort()
    finally:
        start.set()
        # A released barrier may still have workers returning from wait().
        # Aborting it on a successful fixed phase can cancel those late exits.
        # Never infer drain from a timeout. The outer command retains this
        # process/modules if a kernel worker cannot return from its ioctl.
        for thread in threads:
            thread.join()
    finished = time.monotonic_ns()
    m = dict(schema=1, complete=bool(state) and not collector_error and
             all(row and not row['error'] for row in rows), before=before, after=snapshot(),
             workers=rows, samples=samples, collector_error=collector_error or 0,
             collector_cpu=spec['collector_cpu'], collector_observed_cpu=ctypes.CDLL(None).sched_getcpu(),
             progress_batch=256, started_ns=state.get('started_ns', finished),
             deadline_ns=state.get('deadline_ns', 0), finished_ns=finished)
    m['wall_ns'] = finished - m['started_ns']
    for name in ('completed', 'reads', 'writes'):
        m[name] = sum(row.get(name, 0) for row in rows if row)
    for name, source in (('duration_ns', 'duration_ms'), ('peak_window_ns', 'peak_window_ms'),
                         ('peak_settle_ns', 'peak_settle_ms'), ('sample_period_ns', 'sample_ms')):
        m[name] = spec[source] * 1000000
    try:
        validate(m, spec)
        m['data_ok'] = True
    except (ValueError, KeyError, TypeError) as error:
        m.update(data_ok=False, validation_error=str(error))
    return m


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=str, required=True)
    args = parser.parse_args()
    with open(args.spec) as source:
        result = run(json.load(source))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['data_ok'] else 1)
