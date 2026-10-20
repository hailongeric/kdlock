#!/usr/bin/env python3
"""Use the existing allocator guard before retrying the unchanged provider."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/mutex-entry-restored-20261020')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-state', required=True, type=Path)
    args = parser.parse_args()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert Path.cwd() == ROOT and os.environ['KDLOCK_RECOVERY_CONFIRMED'] == '1'
    host = json.loads(args.host_state.read_text())
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(host['captured_utc'])).total_seconds()
    assert host['snapshot_listed'] and host['pins_verified'] and 0 <= age <= 300
    assert host['recovery_snapshot'] == os.environ['KDLOCK_SNAPSHOT_TAG']
    manifest = json.loads((BASE/'checks-1/committed-source.json').read_text())
    failure = json.loads((BASE/'failed-live1-health.json').read_text())
    assert failure['idle'] and failure['passed'] is False and not failure['live_passed']
    assert failure['source_commit'] == manifest['commit']
    assert failure['kernel_allocation_failure']['bytes'] == 7592
    assert failure['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    failed_hashes = json.loads(
        (BASE/'failure-diagnostics/failed-live1-file-sha256.json').read_text())

    def verify():
        for path, expected in manifest['files'].items():
            assert sha(ROOT/path) == expected, path
        for path, expected in failed_hashes.items():
            assert sha(BASE/path) == expected, path

    verify()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    out = BASE/'allocator-refresh'
    archive['idle'](out, rt.idle)
    assert not out.exists()
    out.mkdir()
    shutil.copyfile(Path(__file__), out/'refresh-restored-allocator.py')
    shutil.copyfile(args.host_state, out/'host-before.json')
    source_hashes = {}
    for name in ('Makefile', 'tc_allocator_guard.c'):
        path = 'bench/tclock_compare/allocator_guard/'+name
        target = out/'source'/path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/path, target)
        assert sha(target) == manifest['files'][path]
        source_hashes[path] = sha(target)
    rt.write_json(out/'source-sha256.json', source_hashes)
    directory = out/'source/bench/tclock_compare/allocator_guard'
    result = dict(passed=False, idle=False, source_commit=manifest['commit'],
                  failure_health_sha256=sha(BASE/'failed-live1-health.json'),
                  boot_id=failure['boot_id'], commands=[],
                  scope='Preparation only: normal page-sized allocation/free through the '
                        'unchanged guard, unloaded before retry. This is not a mutex probe pass.')
    rt.write_json(out/'result.json', result)
    fd = None
    try:
        commands = [('build', ['make', '-C', str(directory),
                              'KDIR=/root/linux-6.1.159-kdclobber2'], 180),
                    ('load', ['insmod', str(directory/'tc_allocator_guard.ko')], 30),
                    ('unload', ['rmmod', 'tc_allocator_guard'], 30)]
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        for name, command, timeout in commands:
            rt.command(command, out/(name+'.log'), timeout=timeout)
            result['commands'].append(dict(name=name, exit_code=0))
            rt.write_json(out/'result.json', result)
        messages = ''
        while True:
            try:
                messages += os.read(fd, 1 << 20).decode(errors='replace')+'\n'
            except BlockingIOError:
                break
        (out/'kernel.log').write_text(messages)
        assert not rt.FAULT.search(messages), messages
        rt.write_json(out/'binary-sha256.json', {
            'source/bench/tclock_compare/allocator_guard/tc_allocator_guard.ko':
                sha(directory/'tc_allocator_guard.ko')})
        verify()
        for path, expected in source_hashes.items():
            assert sha(out/'source'/path) == expected
        archive['idle'](out, rt.idle)
        result.update(passed=True, idle=True, source_unchanged=True,
                      failed_attempt_unchanged=True)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        if fd is not None:
            os.close(fd)
        rt.write_json(out/'result.json', result)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
