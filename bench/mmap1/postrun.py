"""Bounded ordinary CPU activity after application execution has drained."""
from pathlib import Path
import subprocess
import time


def progress(parameters, source_status, reached_status, timeout=5):
    assert 0 < timeout <= 5
    assert (parameters / 'rwsem_provider_active').read_text().strip() == 'N'
    assert source_status()['frames'] == 0
    stats = reached_status()
    assert stats['active'] == stats['unsupported'] == 0
    assert stats['roots'] == stats['completions']
    result = dict(started_ns=time.monotonic_ns(), cpus=[],
                  bindings_before=int((parameters / 'rwsem_provider_bindings').read_text()))
    deadline = time.monotonic() + timeout
    for item in Path('/sys/devices/system/cpu/online').read_text().strip().split(','):
        ends = list(map(int, item.split('-')))
        for cpu in range(ends[0], ends[-1] + 1):
            remaining = deadline - time.monotonic()
            assert remaining > 0, 'postrun CPU progress exceeded its bound'
            subprocess.run(['taskset', '-c', str(cpu), '/usr/bin/true'], check=True,
                           timeout=remaining, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            result['cpus'].append(cpu)
    result.update(finished_ns=time.monotonic_ns(),
                  bindings_after=int((parameters / 'rwsem_provider_bindings').read_text()))
    return result
