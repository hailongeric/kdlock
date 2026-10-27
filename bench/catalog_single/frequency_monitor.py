"""Read existing APERF/MPERF devices from host CPU63; bounded telemetry only."""
import datetime
import json
import os
from pathlib import Path
import time
import sys
import re

ROOT = Path('/sys/devices/system/cpu')
label = sys.argv[1]
assert re.fullmatch(r'[a-z0-9-]+', label)
STOP = Path('/tmp/kdlock-linux70-'+label+'-stop')
assert not STOP.exists()
os.sched_setaffinity(0, {63})
fds = [os.open(f'/dev/cpu/{cpu}/msr', os.O_RDONLY) for cpu in range(64)]
platform = [int.from_bytes(os.pread(fds[cpu], 8, 0xce), 'little') for cpu in (0, 32)]
assert all(((value >> 8) & 255) == 20 for value in platform)

def snapshot():
    begin = time.monotonic_ns()
    rows = []
    for fd in fds:
        rows.append([int.from_bytes(os.pread(fd, 8, reg), 'little') for reg in (0xe8, 0xe7)])
    return dict(monotonic_ns=(begin+time.monotonic_ns())//2,
                realtime_ns=time.time_ns(), counters=rows)

def policy_ok():
    policies=list((ROOT/'cpufreq').glob('policy*'))
    return ({p.name for p in policies} == {f'policy{cpu}' for cpu in range(64)} and
        (ROOT/'intel_pstate/no_turbo').read_text().strip() == '1' and all(
        (p/'scaling_min_freq').read_text().strip() == '2000000' and
        (p/'scaling_max_freq').read_text().strip() == '2000000' and
        (p/'scaling_governor').read_text().strip() == 'performance'
        for p in policies))

def thermal():
    return {str(p.relative_to(ROOT)): int(p.read_text())
            for p in ROOT.glob('cpu[0-9]*/thermal_throttle/*throttle_count')}

initial_thermal = thermal()
print(json.dumps(dict(event='start', pid=os.getpid(), cpu=63, reference_mhz=2000,
    reference='MSR_PLATFORM_INFO[15:8] = 20, 100MHz units',
    platform=[hex(v) for v in platform], interval_seconds=1.0,
    registers={'aperf':'0xe8','mperf':'0xe7'}, thermal=initial_thermal,
    utc=datetime.datetime.now(datetime.timezone.utc).isoformat())), flush=True)
first = previous = snapshot()
samples = 0
try:
    while time.monotonic_ns()-first['monotonic_ns'] < 3550*10**9 and not STOP.exists():
        time.sleep(1.0)
        current = snapshot()
        elapsed = current['monotonic_ns']-previous['monotonic_ns']
        rows = []
        for cpu, (now, old) in enumerate(zip(current['counters'], previous['counters'])):
            da, dm = [(a-b) % (1 << 64) for a,b in zip(now, old)]
            rows.append(dict(cpu=cpu, aperf_delta=da, mperf_delta=dm,
                busy_mhz=2000*da/dm if dm else None,
                busy_fraction=dm/(elapsed*2)))
        valid = policy_ok()
        print(json.dumps(dict(event='sample', **current, elapsed_ns=elapsed,
                              policy_ok=valid, cpus=rows)), flush=True)
        assert valid, 'Frequency policy drifted'
        previous = current
        samples += 1
    print(json.dumps(dict(event='complete', samples=samples, stop_requested=STOP.exists(),
                          thermal=thermal(), realtime_ns=time.time_ns())), flush=True)
finally:
    for fd in fds:
        os.close(fd)
