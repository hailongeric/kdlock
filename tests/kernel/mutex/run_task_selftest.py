#!/usr/bin/env python3
"""Recovery-guest task lifetime / physical-owner ACK resource probe.

The in-provider fixture uses real pinned tasks and original Linux mutexes. Its
continuation packet is constructed and executes no JIT bodies. The provider
always enables mutex JIT; this probe cannot replace returned-body JIT tests.
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
    parser.add_argument('--mutex-wait-mode', choices=('spin', 'blocking'), default='spin')
    parser.add_argument('--cpus', type=int, nargs=3, default=[0, 1, 2],
                        help='distinct owner, waiter and RCU-reader CPUs')
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
                     'KDLOCK_SELFTEST=1', 'UBSAN_SANITIZE=n', 'W=1'],
                    out/'build.log', timeout=180)
    module = ROOT/'kernel_module/kdlock_km.ko'
    shutil.copyfile(module, out/module.name)
    runtime.write_json(out/'identity.json', dict(module_sha256=runtime.digest(module),
        snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'), provider_ubsan='off', jit=False,
        jit_bodies=0, mutex_jit_required=True, scope='task_owner_ack_resource_probe',
        cpus=args.cpus, mutex_wait_mode=args.mutex_wait_mode))
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
        runtime.command(['insmod', module, 'mutex_task_selftest=1',
                         'mutex_blocking='+str(int(args.mutex_wait_mode == 'blocking')),
                         'mutex_task_cpus=' + ','.join(map(str, args.cpus))],
                        out/'load.log', timeout=30)
        collect()
        runtime.require(not Path('/sys/module/kdlock_km/parameters/mutex_jit').exists(),
                        'obsolete mutex JIT switch present')
        runtime.require('orders=2 acks=4 deferred_frees=2 failures=0 jit_bodies=0' in messages,
                        'missing task/owner ACK evidence')
        runtime.require('registry stress: workers=3 iterations=4096 deferred_frees=3 failures=0 jit_bodies=0' in messages,
                        'missing concurrent task-registry evidence')
        runtime.command([sys.executable, ROOT/'disassem/device_session.py', 'retire'],
                        out/'retire.log')
        runtime.command(['rmmod', 'kdlock_km'], out/'unload.log')
        collect()
        runtime.require('kd_mutex tasks: active_tasks=0 ' in messages,
                        'task registry was not empty at unload')
        runtime.idle()
        runtime.write_json(out/'result.json', dict(passed=True, drained=True,
            mutex_wait_mode=args.mutex_wait_mode, orders=['B-A', 'A-B'], acks=4, deferred_frees=2, jit=False,
            registry_stress_workers=3, registry_stress_iterations=4096,
            registry_stress_deferred_frees=3,
            jit_bodies=0, mutex_jit_required=True, scope='task_owner_ack_resource_probe'))
        print('PASS: RCU task lifetime and real owner ACKs; two orders, four ACKs, no JIT bodies')
    finally:
        # An exception is not authorization to force retirement or unloading.
        collect()
        os.close(fd)


if __name__ == '__main__':
    main()
