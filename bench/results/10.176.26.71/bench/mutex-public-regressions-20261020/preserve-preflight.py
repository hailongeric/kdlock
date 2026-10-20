#!/usr/bin/env python3
"""Add a later, explicitly scoped receipt to the zero-session failed preflight."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    failed = BASE/'mutex-public-20261020-replay-1'
    completed = BASE/'mutex-public-20261020-replay-2'
    assert not (failed/'health.json').exists()
    original = {p.name: sha(p) for p in failed.iterdir() if p.is_file()
                and p.name != Path(__file__).name}
    absent = ('measurements', 'records.json', 'plan.json', 'execution-order.json', 'status.json')
    assert all(not (failed/name).exists() for name in absent)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](failed, bench_runtime.idle)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    later = json.loads((completed/'health.json').read_text())
    assert later['idle'] and later['boot_id'] == boot
    assert not later['per_session_kernel_faults']
    result = dict(
        state='PREFLIGHT_FAILED', measured_sessions=0,
        error='ValueError: replay QEMU thread placement differs',
        error_origin='Operator transcript of original failed invocation; not a reconstructed traceback',
        absent_measurement_paths=list(absent), original_partial_file_sha256=original,
        reason='Two extra QEMU worker threads, both on CPU 63. Exact thread-set comparison refused.',
        resolution='Workers retired naturally before replay-2; no placement/admission check changed.',
        related_completed_run=str(completed),
        later_health_sha256=sha(completed/'health.json'),
        recorded_unix=time.time())
    (failed/'preflight-outcome.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    health = dict(
        idle=True, boot_id=boot, checked_unix=time.time(), measured_sessions=0,
        per_session_kernel_faults=[], original_partial_file_sha256=original,
        scope='Later idle verification for a failed preflight with no measurement tree. '
              'This does not convert the original failure into a benchmark pass.',
        related_completed_run_health_sha256=sha(completed/'health.json'))
    (failed/'health.json').write_text(json.dumps(health, indent=2, sort_keys=True)+'\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
