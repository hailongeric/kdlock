#!/usr/bin/env python3
"""Validate genuine file-write VM_FAULT_COMPLETED returns on exact mm/task."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity
sys.path.insert(0, str(ROOT / 'bench/mmap_writer'))
import shared_platform


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('native', 'kd'), required=True)
    p.add_argument('--output', type=Path, required=True)
    shared_platform.arguments(p)
    a = p.parse_args()
    shared_platform.guest(a)
    rt.idle()
    for m in Path('/sys/module').iterdir():
        rt.require(not m.name.startswith(('kd_', 'tclock_', 'tc_', 'jit_')), 'project module remains')
    rt.require([s for s in Path('/proc/cmdline').read_text().split() if s.startswith('kd_mmap=')] ==
               ['kd_mmap=' + ('on' if a.mode == 'kd' else 'off')], 'boot mode differs')
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new evidence required')
    out.mkdir(parents=True)
    result = dict(state='PREPARATION', passed=False, drained=False, accepted=False, timing=False,
                  mode=a.mode, delegated=False, workload='FILE_WRITE_FAULT_COMPLETED',
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    rt.write_json(out / 'result.json', result)
    fd, messages = None, ''

    def logs():
        nonlocal messages
        if fd is None:
            return
        while True:
            try:
                messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
            except BlockingIOError:
                break
        (out / 'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages), 'kernel fault; retain module', 'KERNEL_FAULT')

    try:
        result.update(shared_platform.admit(a,out))
        support=shared_platform.freeze_support(out)
        source, hashes = out / 'source', {}
        here = Path(__file__).parent
        for path in here.rglob('*'):
            if not path.is_file() or path.suffix not in ('.c', '.h', '.py') and path.name != 'Makefile':
                continue
            rel = path.relative_to(here)
            hashes[str(rel)] = rt.digest(path)
            target = source / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        rt.write_json(out / 'source-sha256.json', hashes)
        payload, client = source / 'payload/kd_mmap_completed.ko', out / 'client'
        rt.command(['make', '-C', payload.parent, 'KDIR=' + str(a.kernel_source), 'W=1', 'UBSAN_SANITIZE=n'],
                   out / 'build-payload.log', timeout=180)
        rt.command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', source / 'client.c', '-o', client],
                   out / 'build-client.log', timeout=60)
        binaries = {str(p.relative_to(out)): rt.digest(p) for p in (payload, client)}
        rt.write_json(out / 'binary-sha256.json', binaries)
        shared_platform.verify_boot(a)
        shared_platform.common.verify_maps(support)
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        rt.command(['insmod', payload], out / 'load.log')
        result['state'] = 'RUNNING'
        rt.write_json(out / 'result.json', result)
        data = rt.command([client, out / 'mapped-file', str(int(a.mode == 'kd'))], out / 'client.jsonl', timeout=120)
        logs()
        rows = [json.loads(line) for line in data.splitlines()]
        rt.require(len(rows) == 2 and rows[1] == dict(passed=True, pages=64, data_ok=True, timing=False),
                   'file data or completion differs')
        observed = rows[0]
        rt.require(observed['mm'] and observed['lock'] and observed['tid'] and
                   observed['use_kd'] == int(a.mode == 'kd') and
                   observed['entries'] == observed['returns'] == observed['completed'] == 64 and
                   observed['retries'] == observed['errors'] == observed['missed'] == 0 and
                   observed['write_reacquired'] == 1, 'genuine fault result or lock release differs')
        health = Path('/sys/module/kd_mmap_completed/parameters/health').read_text().strip()
        rt.require(health == 'opened=0 closes=1 errors=0', 'observer reference/probe teardown differs')
        rt.command(['rmmod', 'kd_mmap_completed'], out / 'unload.log')
        logs()
        rt.idle()
        for name, h in hashes.items():
            rt.require(rt.digest(here / name) == rt.digest(source / name) == h, 'frozen input changed')
        rt.require(all(rt.digest(out / name) == h for name, h in binaries.items()) and
                   not (out / 'mapped-file').exists(), 'binary or file teardown differs')
        shared_platform.verify_boot(a)
        shared_platform.common.verify_maps(support)
        result.update(state='COMPLETE', passed=True, drained=True, observation=observed, health=health,
                      binaries=binaries, source_unchanged=True)
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        shared_platform.common.finish_logs(out,result,logs,fd)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
