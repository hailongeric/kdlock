#!/usr/bin/env python3
"""One ordinary allocator-hint refresh after the retained task-1 load failure.

This preparation does not change the provider or count as a mutex test pass.
The existing page-sized helper is unloaded before the unchanged probe retry.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/pipecap-unlock-20261021')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host-state', type=Path, required=True)
    a = p.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    require, sha = rt.require, rt.digest
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            Path('/proc/sys/kernel/random/boot_id').read_text().strip() ==
            '88449cfc-cea9-4647-a294-bc601e372146' and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1', 'same confirmed guest required')
    host = json.loads(a.host_state.read_text())
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(host['captured_utc'])).total_seconds()
    require(host['snapshot_listed'] and host['pins_verified'] and 0 <= age <= 300 and
            host['recovery_snapshot'] == os.environ['KDLOCK_SNAPSHOT_TAG'], 'fresh recovery receipt required')
    failure = BASE/'task-1'
    require('Cannot allocate memory' in (failure/'load.log').read_text() and
            'Could not allocate 7592 bytes percpu data' in (failure/'kernel.log').read_text() and
            not (failure/'result.json').exists(), 'expected pre-test allocation failure required')
    failed_hashes = {str(p.relative_to(failure)): sha(p) for p in failure.rglob('*') if p.is_file()}
    for relative, digest in json.loads((failure/'sources.json').read_text()).items():
        require(sha(ROOT/relative) == digest, 'failed probe source changed')
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    out = BASE/'allocator-refresh-1'
    require(not out.exists(), 'new output required')
    archive['idle'](out, rt.idle)
    out.mkdir()
    shutil.copyfile(Path(__file__), out/'driver.py')
    shutil.copyfile(a.host_state, out/'host-before.json')
    rt.write_json(out/'failed-attempt-sha256.json', failed_hashes)
    build = out/'source'
    build.mkdir()
    sources = {}
    for name in ('Makefile', 'tc_allocator_guard.c'):
        original = ROOT/'bench/tclock_compare/allocator_guard'/name
        shutil.copyfile(original, build/name)
        sources[name] = sha(original)
    rt.write_json(out/'source-sha256.json', sources)
    result = dict(passed=False, idle=False, commands=[],
        scope='Preparation only; unchanged normal allocator helper unloaded before probe retry.')
    rt.write_json(out/'result.json', result)
    fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
    os.lseek(fd, 0, os.SEEK_END)
    try:
        for name, command, limit in [
            ('build', ['make', '-C', build, 'KDIR=/root/linux-6.1.159-kdclobber2'], 180),
            ('load', ['insmod', build/'tc_allocator_guard.ko'], 30),
            ('unload', ['rmmod', 'tc_allocator_guard'], 30)]:
            rt.command(command, out/(name+'.log'), timeout=limit)
            result['commands'].append(dict(name=name, exit_code=0))
            rt.write_json(out/'result.json', result)
        messages = ''
        while True:
            try:
                messages += os.read(fd, 1 << 20).decode(errors='replace')+'\n'
            except BlockingIOError:
                break
        (out/'kernel.log').write_text(messages)
        require(not rt.FAULT.search(messages), 'kernel fault during preparation')
        require(all(sha(failure/p) == h for p, h in failed_hashes.items()), 'failed evidence changed')
        require(all(sha(build/p) == h for p, h in sources.items()), 'helper source changed')
        rt.write_json(out/'binary-sha256.json', {'tc_allocator_guard.ko': sha(build/'tc_allocator_guard.ko')})
        archive['idle'](out, rt.idle)
        result.update(passed=True, idle=True, failed_attempt_unchanged=True)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        os.close(fd)
        rt.write_json(out/'result.json', result)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
