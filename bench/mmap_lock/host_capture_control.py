#!/usr/bin/env python3
"""Bracket one historical capture helper with read-only QEMU task observations.

Run on the benchmark host. This is a no-workload diagnostic, never timing
qualification. It changes no placement or settings and performs no quiet wait.
The helper's stdout stays in memory until the immediate endpoint is captured.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def stat_fields(text):
    # comm may contain spaces or parentheses; fields after the last ')' start
    # at stat field 3. Start time distinguishes a reused PID/TID.
    end = text.rindex(')')
    rest = text[end + 2:].split()
    return dict(tid=int(text.split('(', 1)[0]),
                comm=text[text.index('(') + 1:end], state=rest[0],
                start_ticks=int(rest[19]), processor=int(rest[36]))


def capture(proc, start_ticks):
    begin = time.monotonic_ns()
    process = stat_fields((proc / 'stat').read_text())
    if process['start_ticks'] != start_ticks:
        raise RuntimeError('QEMU process identity changed')
    tasks, disappeared = [], []
    initial = sorted(int(p.name) for p in (proc / 'task').iterdir())
    for tid in initial:
        task = proc / 'task' / str(tid)
        try:
            first = stat_fields((task / 'stat').read_text())
            runtime, waiting, slices = map(int, (task / 'schedstat').read_text().split())
            affinity = sorted(os.sched_getaffinity(tid))
            last = stat_fields((task / 'stat').read_text())
            if (first['tid'], first['start_ticks']) != (last['tid'], last['start_ticks']):
                raise RuntimeError('task identity changed during capture')
            tasks.append(dict(**last, affinity=affinity, runtime_ns=runtime,
                              runqueue_wait_ns=waiting, timeslices=slices))
        except (FileNotFoundError, ProcessLookupError):
            disappeared.append(tid)
    final = sorted(int(p.name) for p in (proc / 'task').iterdir())
    return dict(begin_ns=begin, end_ns=time.monotonic_ns(), tasks=tasks,
                initial_tids=initial, final_tids=final,
                disappeared=disappeared, stable_listing=initial == final and not disappeared)


def compare(before, after):
    key = lambda t: (t['tid'], t['start_ticks'])
    old = {key(t): t for t in before['tasks']}
    new = {key(t): t for t in after['tasks']}
    return dict(added=[new[k] for k in sorted(new.keys() - old.keys())],
                removed=[old[k] for k in sorted(old.keys() - new.keys())],
                runtime_delta_ns=[dict(tid=k[0], start_ticks=k[1], comm=new[k]['comm'],
                    delta=new[k]['runtime_ns'] - old[k]['runtime_ns'])
                    for k in sorted(old.keys() & new.keys())])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--cmdline-sha256', required=True)
    p.add_argument('--helper-base64', required=True)
    p.add_argument('--helper-sha256', required=True)
    a = p.parse_args()
    helper = base64.b64decode(a.helper_base64, validate=True)
    if hashlib.sha256(helper).hexdigest() != a.helper_sha256:
        raise ValueError('historical helper identity differs')
    proc = Path('/proc') / str(a.pid)
    command = (proc / 'cmdline').read_bytes()
    if (Path(os.fsdecode(command.split(b'\0')[0])).name != 'qemu-system-x86_64'
            or hashlib.sha256(command).hexdigest() != a.cmdline_sha256):
        raise ValueError('QEMU command identity differs')
    start = stat_fields((proc / 'stat').read_text())['start_ticks']
    result = dict(schema=1, accepted=False, workload_started=False,
        captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        pid=a.pid, process_start_ticks=start, command_sha256=a.cmdline_sha256,
        helper_sha256=a.helper_sha256, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        observer_affinity=sorted(os.sched_getaffinity(0)),
        limits='Two non-atomic observations can miss intervening tasks. Association with '
               'the capture helper does not identify its internal cause or qualify historical timings.')
    own_cpu = time.process_time_ns()
    result['before'] = capture(proc, start)
    result['helper_start_ns'] = time.monotonic_ns()
    child = subprocess.Popen([sys.executable, '-c', helper.decode()],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True)
    try:
        stdout, stderr = child.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        # No retry, wait-for-quiet, or signal to a possibly blocked helper.
        result.update(helper_pid=child.pid, helper_timeout=True)
        result['after'] = capture(proc, start)
        print(json.dumps(result), flush=True)
        return 1
    result['helper_end_ns'] = time.monotonic_ns()
    result['after'] = capture(proc, start)
    result.update(helper_pid=child.pid, helper_exit=child.returncode,
                  helper_stdout=stdout.decode(errors='replace'),
                  helper_stderr=stderr.decode(errors='replace'),
                  difference=compare(result['before'], result['after']),
                  observer_cpu_ns=time.process_time_ns() - own_cpu)
    if hashlib.sha256((proc / 'cmdline').read_bytes()).hexdigest() != a.cmdline_sha256:
        raise RuntimeError('QEMU command identity changed')
    print(json.dumps(result), flush=True)
    return int(child.returncode != 0)


if __name__ == '__main__':
    raise SystemExit(main())
