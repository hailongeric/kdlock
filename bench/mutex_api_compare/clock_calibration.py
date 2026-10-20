#!/usr/bin/env python3
"""Bound host/guest monotonic offsets through the existing SSH connections.

The source host records send/receive bounds; each target reads its clock inside
that interval. These bounds include network/process-startup cost. They are not
an assumption that wall clocks agree or a precision latency measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import socket
import subprocess
import time

TARGETS = {'host': ['eric@10.176.26.71'],
           'guest': ['-p', '2222', 'root@10.176.26.71']}
CODE = (
    "import json,os,time;from pathlib import Path;"
    "os.sched_setaffinity(0,{62});"
    "r0=time.time_ns();m=time.monotonic_ns();r1=time.time_ns();"
    "print(json.dumps(dict(monotonic_ns=m,realtime_before_ns=r0,realtime_after_ns=r1,"
    "boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),"
    "affinity=sorted(os.sched_getaffinity(0)))))")


def offset_bounds(row):
    """Source monotonic minus target monotonic, including the entire RTT."""
    before, after = row['source_before_ns'], row['source_after_ns']
    if after < before:
        raise ValueError('source monotonic order differs')
    target = row['target_clock']['monotonic_ns']
    return [before-target, after-target]


def project_interval(begin, end, guest_bounds, host_bounds):
    """Conservative host interval for a guest interval using retained offsets."""
    if end < begin or any(b[1] < b[0] for b in (guest_bounds, host_bounds)):
        raise ValueError('invalid interval')
    return [begin+guest_bounds[0]-host_bounds[1],
            end+guest_bounds[1]-host_bounds[0]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=5)
    args = parser.parse_args()
    if socket.gethostname() != '380G10' or not 1 <= args.samples <= 10:
        raise ValueError('use the established source host and 1..10 bounded samples')
    if args.output.exists():
        raise ValueError('retain earlier calibration; choose a new output')
    result = dict(schema=1, source_host=socket.gethostname(),
                  source_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  samples=[], complete=False,
                  limits='Offset bounds include SSH RTT. Between-calibration clock drift '
                         'and polling gaps must remain explicit; no clock setting is changed.')
    try:
        for index in range(args.samples):
            for name, target in TARGETS.items():
                argv = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                        *target, 'timeout 10 python3 -c '+shlex.quote(CODE)]
                before = time.monotonic_ns()
                data = subprocess.check_output(argv, timeout=20)
                after = time.monotonic_ns()
                row = dict(target=name, repetition=index, source_before_ns=before,
                           source_after_ns=after, target_clock=json.loads(data))
                if row['target_clock']['affinity'] != [62]:
                    raise ValueError('clock reader affinity differs')
                row['source_minus_target_bounds_ns'] = offset_bounds(row)
                result['samples'].append(row)
        result['complete'] = True
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
    print(json.dumps(dict(complete=True, samples=len(result['samples']),
                          output=str(args.output)), sort_keys=True))


if __name__ == '__main__':
    main()
