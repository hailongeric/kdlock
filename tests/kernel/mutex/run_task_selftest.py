#!/usr/bin/env python3
"""Recovery-guest task lifetime / physical-owner ACK probe; explicitly JIT=0.

The in-provider fixture uses real pinned tasks and original Linux mutexes. Its
continuation packet is constructed, so this cannot replace returned JIT tests.
"""
import argparse
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as runtime
import kernel_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    runtime.require(ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0 and
                    os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1',
                    'confirmed recovery guest required')
    runtime.idle()
    for name in ('tclock_backend_km', 'tclock_mutex_backend_km'):
        runtime.require(not Path('/sys/module', name).exists(), 'TCLock still loaded')
    out = args.output.resolve()
    runtime.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    kernel_identity.capture(args, out, runtime.command)
    hashes = {}
    for directory in ('include', 'kernel_module', 'tests/kernel/mutex'):
        for path in (ROOT / directory).rglob('*'):
            if (not path.is_file() or path.name.endswith('.mod.c') or
                    (path.suffix not in ('.c', '.h', '.inc', '.S', '.py') and path.name != 'Makefile')):
                continue
            relative = path.relative_to(ROOT)
            target = out/'source'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            hashes[str(relative)] = runtime.digest(path)
    runtime.write_json(out/'sources.json', hashes)
    runtime.command(['make', '-C', ROOT/'kernel_module', f'KDIR={args.kernel_source}',
                     'KDLOCK_SELFTEST=1', 'W=1'], out/'build.log', timeout=180)
    module = ROOT/'kernel_module/kdlock_km.ko'
    shutil.copyfile(module, out/module.name)
    runtime.write_json(out/'identity.json', dict(module_sha256=runtime.digest(module),
        snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'), jit=False, cpus=[0, 1, 2]))
    messages = ''
    fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
    os.lseek(fd, 0, os.SEEK_END)

    def collect():
        nonlocal messages
        while True:
            try:
                messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
            except BlockingIOError:
                break
        (out/'kernel.log').write_text(messages)
        runtime.require(not runtime.FAULT.search(messages), 'kernel fault: retain state for recovery')

    try:
        runtime.command(['insmod', module, 'mutex_jit=0', 'mutex_task_selftest=1',
                         'mutex_task_cpus=0,1,2'], out/'load.log', timeout=30)
        collect()
        runtime.require('orders=2 acks=4 retained_records=2 failures=0 JIT=0' in messages,
                        'missing task/owner ACK evidence')
        runtime.command([sys.executable, ROOT/'disassem/device_session.py', 'retire'],
                        out/'retire.log')
        runtime.command(['rmmod', 'kdlock_km'], out/'unload.log')
        collect()
        runtime.require('active_tasks=0 retained_tasks=2 released_tasks=2' in messages,
                        'retained tasks were not released at unload')
        runtime.idle()
        runtime.write_json(out/'result.json', dict(passed=True, drained=True,
            orders=['B-A', 'A-B'], acks=4, retained_until_unload=2, jit=False))
        print('PASS: task cache lifetime and real owner ACKs; two orders, four ACKs, JIT=0')
    finally:
        # An exception is not authorization to force retirement or unloading.
        collect()
        os.close(fd)


if __name__ == '__main__':
    main()
