#!/usr/bin/env python3
"""Bracket one reviewed helper with read-only QEMU task observations.

A diagnostic receipt never qualifies timing. Timeout/interruption preserves
partial evidence and leaves the child untouched; neither proves child drain.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import selectors
import subprocess
import sys
import time


def stat_fields(text):
    end = text.rindex(')')
    rest = text[end + 2:].split()
    return dict(tid=int(text.split('(', 1)[0]),
                comm=text[text.index('(') + 1:end], state=rest[0],
                start_ticks=int(rest[19]), processor=int(rest[36]))


def identity(proc, start_ticks, command_sha):
    row = stat_fields((proc / 'stat').read_text())
    command = (proc / 'cmdline').read_bytes()
    if (row['tid'] != int(proc.name) or row['start_ticks'] != start_ticks or
            hashlib.sha256(command).hexdigest() != command_sha or
            Path(os.fsdecode(command.split(b'\0')[0])).name != 'qemu-system-x86_64'):
        raise ValueError('QEMU PID/start/command identity changed')
    return dict(pid=row['tid'], start_ticks=start_ticks, command_sha256=command_sha)


def capture(proc, start_ticks, command_sha):
    """Retain partial rows; equal observed lists cannot exclude intervening tasks."""
    out = dict(begin_ns=time.monotonic_ns(), complete=False, tasks=[], errors=[])
    try:
        out['identity_before'] = identity(proc, start_ticks, command_sha)
        out['initial_tids'] = sorted(int(p.name) for p in (proc / 'task').iterdir())
        for tid in out['initial_tids']:
            task = proc / 'task' / str(tid)
            row = dict(tid=tid, complete=False)
            out['tasks'].append(row)
            try:
                first = stat_fields((task / 'stat').read_text())
                row.update(first)
                row['runtime_ns'], row['runqueue_wait_ns'], row['timeslices'] = map(
                    int, (task / 'schedstat').read_text().split())
                row['affinity'] = sorted(os.sched_getaffinity(tid))
                last = stat_fields((task / 'stat').read_text())
                if (first['tid'], first['start_ticks']) != (last['tid'], last['start_ticks']):
                    raise ValueError('task identity changed during capture')
                row.update(last, complete=True)
            except (OSError, ValueError) as error:
                row['error'] = repr(error)
                out['errors'].append(dict(tid=tid, error=repr(error)))
        out['final_tids'] = sorted(int(p.name) for p in (proc / 'task').iterdir())
        out['equal_observed_tid_lists'] = out['initial_tids'] == out['final_tids']
    except (OSError, ValueError) as error:
        out['errors'].append(dict(error=repr(error)))
    finally:
        try:
            out['identity_after'] = identity(proc, start_ticks, command_sha)
        except (OSError, ValueError) as error:
            out['errors'].append(dict(phase='identity_after', error=repr(error)))
        out['end_ns'] = time.monotonic_ns()
    out['complete'] = not out['errors'] and out.get('equal_observed_tid_lists', False)
    return out


def compare(before, after):
    key = lambda t: (t['tid'], t['start_ticks'])
    old = {key(t): t for t in before['tasks'] if t['complete']}
    new = {key(t): t for t in after['tasks'] if t['complete']}
    return dict(complete=before['complete'] and after['complete'],
                added=[new[k] for k in sorted(new.keys() - old.keys())],
                removed=[old[k] for k in sorted(old.keys() - new.keys())],
                runtime_delta_ns=[dict(tid=k[0], start_ticks=k[1], comm=new[k]['comm'],
                    delta=new[k]['runtime_ns'] - old[k]['runtime_ns'])
                    for k in sorted(old.keys() & new.keys())])


def read_helper(child, chunks, timeout=20):
    """Keep every consumed byte outside communicate() even on interruption."""
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        for name in ('stdout', 'stderr'):
            selector.register(getattr(child, name), selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(child.args, timeout)
            for key, _ in selector.select(remaining):
                block = os.read(key.fd, 65536)
                if block:
                    chunks[key.data].extend(block)
                    if len(chunks[key.data]) > 16 * 1024 * 1024:
                        raise ValueError('helper output exceeds bound; completion unconfirmed')
                else:
                    selector.unregister(key.fileobj)
        child.wait(timeout=max(0, deadline - time.monotonic()))


def observe(pid, command_sha, helper, helper_sha, start_ticks):
    out = dict(schema=2, passed=False, accepted=False, workload_started=False,
        captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        pid=pid, process_start_ticks=start_ticks, command_sha256=command_sha,
        helper_sha256=helper_sha, helper_may_still_be_running=False, phase='binding',
        limits='Non-atomic observations can miss intervening task lifetimes. '
               'This diagnostic does not qualify timing or identify worker creation causes.')
    child = None
    chunks = dict(stdout=bytearray(), stderr=bytearray())
    proc = Path('/proc') / str(pid)
    own_cpu = time.process_time_ns()
    try:
        if hashlib.sha256(helper).hexdigest() != helper_sha:
            raise ValueError('reviewed helper identity differs')
        out['helper_command'] = [sys.executable, '-c', '<source bound by helper_sha256>']
        out['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        out['observer_affinity'] = sorted(os.sched_getaffinity(0))
        out['phase'] = 'before'
        out['before'] = capture(proc, start_ticks, command_sha)
        if not out['before']['complete']:
            raise ValueError('initial capture incomplete')
        out['phase'] = 'spawn'
        out['helper_start_ns'] = time.monotonic_ns()
        child = subprocess.Popen([sys.executable, '-c', helper.decode()],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True)
        # Record ownership before anything else can fail. A missed /proc read
        # does not invent a process start identity or imply the child exited.
        out.update(helper_pid=child.pid, helper_may_still_be_running=True)
        try:
            out['helper_process'] = stat_fields(Path('/proc', str(child.pid), 'stat').read_text())
        except (OSError, ValueError) as error:
            out['helper_identity_error'] = repr(error)
        out['phase'] = 'helper'
        try:
            read_helper(child, chunks)
        except subprocess.TimeoutExpired as error:
            out.update(helper_status='timed_out', helper_timeout_ns=time.monotonic_ns())
            raise
        out.update(helper_end_ns=time.monotonic_ns(), helper_exit=child.returncode,
                   helper_status='exited' if child.returncode == 0 else 'exited_nonzero',
                   helper_may_still_be_running=False)
    except BaseException as error:
        out.update(error=repr(error), failed_phase=out['phase'])
        if isinstance(error, (KeyboardInterrupt, InterruptedError)):
            out.update(helper_status='interrupted', interruption_ns=time.monotonic_ns())
    finally:
        for name, data in chunks.items():
            out['helper_' + name + '_base64'] = base64.b64encode(data).decode()
            out['helper_' + name] = bytes(data).decode(errors='replace')
        if child is not None:
            out['phase'] = 'after'
            try:
                out['after'] = capture(proc, start_ticks, command_sha)
                out['difference'] = compare(out['before'], out['after'])
                if not out['after']['complete']:
                    raise ValueError('endpoint capture incomplete')
            except BaseException as error:
                out['endpoint_error'] = repr(error)
            out['phase'] = 'final_identity'
            try:
                out['final_identity'] = identity(proc, start_ticks, command_sha)
            except BaseException as error:
                out['final_identity_error'] = repr(error)
        out['passed'] = (out.get('helper_exit') == 0 and
                         not any(k in out for k in ('error', 'endpoint_error', 'final_identity_error')))
        out['phase'] = 'complete' if out['passed'] else 'failed'
        out['observer_cpu_ns'] = time.process_time_ns() - own_cpu
    return out


def interrupted(signum, frame):
    raise InterruptedError('controller received signal ' + str(signum))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--start-ticks', type=int, required=True)
    p.add_argument('--cmdline-sha256', required=True)
    p.add_argument('--helper-base64', required=True)
    p.add_argument('--helper-sha256', required=True)
    a = p.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    out = observe(a.pid, a.cmdline_sha256, base64.b64decode(a.helper_base64, validate=True),
                  a.helper_sha256, a.start_ticks)
    # SIGKILL, transport loss or a broken output pipe can still lose this receipt.
    print(json.dumps(out), flush=True)
    return int(not out['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
