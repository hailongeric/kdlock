#!/usr/bin/env python3
"""Preserve the failed provider load without converting it into a probe pass."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/mutex-entry-restored-20261020')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](BASE, rt.idle)
    failed = BASE/'live-1'
    tasks = json.loads((failed/'tasks.json').read_text())
    result = json.loads((failed/'mutex-local/result.json').read_text())
    checks = json.loads((BASE/'checks-1/result.json').read_text())
    assert tasks['state'] == 'FAILED' and tasks['failed_task'] == 'mutex-local'
    assert len(tasks['tasks']) == 1 and tasks['tasks'][0]['exit_code'] == 1
    assert result['status'] == 'PREPARATION_FAILED' and not result['passed']
    assert not result['drained'] and result['modules_remaining'] == []
    assert not (failed/'mutex-local/load-probe.log').exists()
    kernel = (failed/'mutex-local/kernel.log').read_text()
    assert 'allocation failed, size=7592 align=128' in kernel
    assert 'Could not allocate 7592 bytes percpu data' in kernel
    assert 'Cannot allocate memory' in (failed/'mutex-local/load-provider.log').read_text()
    faults = [line for line in kernel.splitlines() if rt.FAULT.search(line)]
    manifest = json.loads((BASE/'checks-1/committed-source.json').read_text())
    for path, expected in manifest['files'].items():
        assert sha(ROOT/path) == expected, path
    hashes = {}
    for path in sorted(failed.rglob('*')):
        if path.is_file():
            assert not path.is_symlink()
            hashes[str(path.relative_to(BASE))] = sha(path)
    diagnostics = BASE/'failure-diagnostics'
    diagnostics.mkdir()
    shutil.copyfile(Path(__file__), diagnostics/'preserve-restored-failure.py')
    for name, path in [('meminfo.txt', '/proc/meminfo'), ('modules.txt', '/proc/modules'),
                       ('tainted.txt', '/proc/sys/kernel/tainted')]:
        (diagnostics/name).write_bytes(Path(path).read_bytes())
    stats = Path('/sys/kernel/debug/percpu_stats')
    if stats.exists():
        (diagnostics/'percpu-stats.txt').write_bytes(stats.read_bytes())
    (diagnostics/'failed-live1-file-sha256.json').write_text(
        json.dumps(hashes, indent=2, sort_keys=True)+'\n')
    health = dict(idle=True, passed=False, boot_id=tasks['boot_id'],
                  checked_unix=time.time(), source_commit=manifest['commit'],
                  basic_affected_passed=checks['passed'], live_passed=False,
                  failed_task='mutex-local', completed_live_probes=0,
                  unstarted_probes=['mutex-outer', 'mutex-public', 'owner-ack'],
                  original_result=result, per_session_kernel_faults=faults,
                  kernel_allocation_failure=dict(bytes=7592, alignment=128,
                      area='reserved per-CPU chunk', provider_initialized=False,
                      kernel_log='live-1/mutex-local/kernel.log'),
                  percpu_debug_stats_available=stats.exists(),
                  failure_inventory_sha256=sha(diagnostics/'failed-live1-file-sha256.json'),
                  script_sha256=sha(Path(__file__)),
                  scope='Later idle verification and preservation of a failed provider load. '
                        'No live probe passed and no source retirement is claimed.')
    assert health['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    output = BASE/'failed-live1-health.json'
    with output.open('x') as stream:
        json.dump(health, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(health, sort_keys=True))


if __name__ == '__main__':
    main()
