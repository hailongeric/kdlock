#!/usr/bin/env python3
"""One bounded host observation window; no guest command or workload launch."""
import json
import os
from pathlib import Path
import select
import sys
import time

import host_capture_control as capture_tool
import host_state
import window


def sample(profile):
    proc = Path('/proc') / str(profile['pid'])
    row = capture_tool.capture(proc, profile['start_ticks'], profile['command_sha256'])
    try:
        for task in row['tasks']:
            root = proc / 'task' / str(task['tid'])
            task['io'] = {k: int(v) for k, v in (line.split(':') for line in
                           (root / 'io').read_text().splitlines())}
            final = capture_tool.stat_fields((root / 'stat').read_text())
            window.require(window.task_key(task) == window.task_key(final), 'task replaced during I/O read')
        row['final_tids'] = sorted(int(p.name) for p in (proc / 'task').iterdir())
        row['equal_observed_tid_lists'] = row['initial_tids'] == row['final_tids']
        row['identity_after'] = capture_tool.identity(proc, profile['start_ticks'], profile['command_sha256'])
        window.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == profile['boot_id'],
                       'host boot changed')
    except (OSError, ValueError) as error:
        row['errors'].append(dict(error=repr(error)))
    row['complete'] = row['complete'] and not row['errors'] and row['equal_observed_tid_lists']
    row['end_ns'] = time.monotonic_ns()
    return row


def observe(request, source, output):
    """Existing host channel spans guard and measurement; output is source-host I/O.

    Only this observer moves to spare CPU 62. QEMU and guest placement do not
    change. A single guard is attempted, never restarted after contamination.
    """
    nonce = request['nonce']
    window.Protocol(nonce)
    profile, core, definitions = request['profile'], request['core'], request['roles']
    roles = None
    os.sched_setaffinity(0, {62})
    started, cpu = time.monotonic_ns(), time.process_time_ns()
    samples, guard_end = [], None
    total_bytes = 0
    pending = bytearray()
    os.set_blocking(source.fileno(), False)

    def emit(event, **fields):
        nonlocal total_bytes
        data = (json.dumps(dict(event=event, nonce=nonce, **window.binding(), **fields)) + '\n').encode()
        window.require(len(data) <= 4 * 1024**2 and total_bytes + len(data) <= 16 * 1024**2,
                       'host observation output bound')
        total_bytes += len(data)
        window.write_all(output.fileno(), data, min(time.monotonic() + 5,
            (started + window.GUARD_TIMEOUT_NS + window.WINDOW_TIMEOUT_NS + 30_000_000_000) / 1e9))

    try:
        while len(samples) < 96:
            row = sample(profile)
            samples.append(row)
            # Emit even invalid/partial observations before refusing admission.
            emit('sample', sample=row)
            if roles is None:
                roles = window.resolve_roles(row['tasks'], core, definitions)
            window.check_samples(samples, core, roles, complete=False)
            now = time.monotonic_ns()
            if guard_end is None:
                window.require(now - started <= window.GUARD_TIMEOUT_NS, 'guard deadline exceeded')
                if len(samples) >= window.GUARD_SCANS and row['end_ns'] - samples[0]['begin_ns'] >= window.GUARD_NS:
                    window.check_samples(samples, core, roles)
                    guard_end = len(samples) - 1
                    emit('guard', index=guard_end)
            else:
                window.require(now - samples[guard_end]['end_ns'] <= window.WINDOW_TIMEOUT_NS,
                               'measurement completion/endpoint deadline exceeded')
            readable, _, _ = select.select([source], [], [], window.PERIOD_NS / 1e9)
            if readable:
                block = os.read(source.fileno(), window.MAX_FRAME + 1)
                window.require(block, 'controller closed endpoint channel')
                pending.extend(block)
                window.require(len(pending) <= window.MAX_FRAME, 'oversized endpoint command')
                if b'\n' not in pending:
                    continue
                window.require(pending.count(b'\n') == 1 and pending.endswith(b'\n'),
                               'duplicate or pipelined endpoint command')
                command = json.loads(pending)
                window.require(guard_end is not None and command == dict(event='endpoint', nonce=nonce),
                               'premature, duplicate or invalid endpoint command')
                # This final sample is causally after FINISHED, before EXPORT.
                row = sample(profile)
                samples.append(row)
                emit('sample', sample=row)
                deltas = window.check_samples(samples, core, roles)
                receipt = dict(**window.binding(), nonce=nonce, passed=True,
                    samples=samples, core=core, roles=roles, guard_end=guard_end,
                    observer_affinity=sorted(os.sched_getaffinity(0)),
                    observer_cpu_ns=time.process_time_ns() - cpu,
                    observer_elapsed_ns=time.monotonic_ns() - started,
                    stream_bytes_before_endpoint=total_bytes,
                    final_deltas=deltas[-len(core)-len(roles):])
                # Full metadata/monitor reads happen after the measurement sample;
                # receipt export remains held until this endpoint also completes.
                receipt['environment_endpoint'] = host_state.collect(profile['pid'],
                    profile['start_ticks'], profile['command_sha256'])
                window.require(receipt['environment_endpoint']['passed'], 'full endpoint capture failed')
                window.require(time.monotonic_ns() - row['end_ns'] <= 30_000_000_000,
                               'full endpoint completion deadline')
                receipt['observer_total_cpu_ns'] = time.process_time_ns() - cpu
                receipt['observer_total_elapsed_ns'] = time.monotonic_ns() - started
                emit('endpoint', receipt=receipt)
                return 0
        raise ValueError('observation count bound')
    except BaseException as error:
        emit('failed', error=repr(error), observer_cpu_ns=time.process_time_ns()-cpu,
             observer_elapsed_ns=time.monotonic_ns()-started)
        return 1


def main():
    request = window.read_frame(sys.stdin.fileno(), 128 * 1024, time.monotonic() + 10)
    return observe(request, sys.stdin.buffer, sys.stdout.buffer)


if __name__ == '__main__':
    raise SystemExit(main())
