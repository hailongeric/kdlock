#!/usr/bin/env python3
"""Run one bounded, correctness-only original-TCLock probe in the recovery VM."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider', type=Path, required=True)
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--workers', type=int, default=8)
    p.add_argument('--writes', type=int, default=20)
    p.add_argument('--iterations', type=int, default=10000)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1'
    assert os.environ.get('KDLOCK_SNAPSHOT_TAG')
    assert not a.output.exists()
    a.output.mkdir(parents=True)
    with open('/run/lock/kdlock-original-probe.lock', 'w') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ('tclock_backend_km', 'tclock_mutex_backend_km',
                     'tclock_rwlock_backend_km', 'tclock_rwsem_backend_km',
                     'tc_original_test', 'tc_original_reap', 'rwlock_bench', 'kdlock_km'):
            assert not Path('/sys/module', name).exists(), name
        def run(argv, label, timeout=30):
            with (a.output / label).open('w') as log:
                subprocess.run([str(x) for x in argv], stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=timeout)
        run(['insmod', a.provider], 'load-provider.log')
        # A timeout never authorizes unload: on an exception leave evidence and
        # live state intact for diagnosis instead of freeing active stacks.
        run(['insmod', a.probe, f'workers={a.workers}', f'iterations={a.iterations}',
             f'write_percent={a.writes}'], 'load-probe.log')
        params = Path('/sys/module/tc_original_test/parameters')
        row = {x.name: int(x.read_text()) for x in params.iterdir()}
        provider = Path('/sys/module', a.provider.stem, 'parameters')
        row['quiescent'] = int((provider / 'quiescent').read_text())
        row['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        row['kernel'] = os.uname().release
        row['provider'] = str(a.provider)
        row['probe'] = str(a.probe)
        row['drained'] = False
        (a.output / 'result.json').write_text(json.dumps(row, indent=2) + '\n')
        run(['dmesg'], 'dmesg.log')
        assert row['quiescent'] == 1, 'retain live state: registration/queue not drained'
        run(['rmmod', 'tc_original_test'], 'unload-probe.log')
        run(['rmmod', a.provider.stem], 'unload-provider.log')
        row['drained'] = True
        (a.output / 'result.json').write_text(json.dumps(row, indent=2) + '\n')
        print(json.dumps(row))
        assert row['result'] == 0, 'correctness failure; retained result is not a pass'
        assert row['reads'] + row['writes'] == a.workers * a.iterations


if __name__ == '__main__':
    main()
