#!/usr/bin/env python3
"""Recovery-VM scheduler probe; constructed results, separate from JIT tests."""
import argparse
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
import bench_runtime as runtime
import kernel_identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cpu', type=int, default=0)
    p.add_argument('--origin', action='store_true', help='also verify exclusive origin claims')
    kernel_identity.arguments(p)
    args = p.parse_args()
    runtime.require(ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0 and
                    os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1', 'confirmed recovery VM required')
    runtime.idle()
    out = args.output.resolve()
    runtime.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    kernel_identity.capture(args, out, runtime.command)
    hashes = {}
    for directory in ('include', 'kernel_module', 'tests/kernel/mutex'):
        for path in (ROOT/directory).rglob('*'):
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
                     'KDLOCK_SELFTEST=1', 'UBSAN_SANITIZE=n', 'W=1'], out/'build.log', timeout=180)
    module = ROOT/'kernel_module/kdlock_km.ko'
    shutil.copyfile(module, out/module.name)
    runtime.write_json(out/'identity.json', dict(module_sha256=runtime.digest(module),
        snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'), cpu=args.cpu, jit_bodies=0,
        owned_mutex_protocol='linux_local_split_v1',
        owned_release_policy='guarded_owner_release'))
    results = []
    for limit in (0, 1024, 4096):
        path = out/f'spin-{limit}'
        path.mkdir()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        messages = ''

        def collect():
            nonlocal messages
            while True:
                try:
                    messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
                except BlockingIOError:
                    break
            (path/'kernel.log').write_text(messages)
            runtime.require(not runtime.FAULT.search(messages), 'kernel fault: retain module and callers')

        try:
            prefix = 'owned_mutex'
            load = ['insmod', module, f'{prefix}_wait_selftest=1',
                    f'{prefix}_spin_limit={limit}', f'{prefix}_wait_cpu={args.cpu}']
            if args.origin:
                load = ['taskset', '-c', '1', *load, 'owned_mutex_origin_spin=1',
                        'owned_mutex_origin_selftest=1']
            runtime.command(load,
                path/'load.log', timeout=30)
            protocol = Path('/sys/module/kdlock_km/parameters/owned_mutex_protocol').read_text().strip()
            runtime.require(protocol == 'linux_local_split_v1',
                            'owned protocol identity differs')
            runtime.write_json(path/'policy.json', dict(
                owned_mutex_protocol=protocol, owned_release_policy='guarded_owner_release'))
            collect()
            runtime.require('kd_owned_mutex wait probe: queued_cooling=1 result_sleep=1 pickup=1 drained=1 jit_bodies=0' in messages,
                            'missing owned queued cooling/scheduler/pickup evidence')
            if args.origin:
                runtime.require('kd_owned_mutex origin probe: claims=256 scheduled_while_claimed=0 resched=256 reused=256 drained=1 jit_bodies=0' in messages,
                                'missing exclusive origin claim evidence')
            runtime.command([sys.executable, ROOT/'disassem/device_session.py', 'retire'], path/'retire.log')
            runtime.command(['rmmod', 'kdlock_km'], path/'unload.log')
            collect()
            runtime.idle()
            results.append(dict(spin_limit=limit, result_sleep=True, queued_cooling=True,
                                pickup=True, drained=True, jit_bodies=0,
                                origin_claims=256 if args.origin else 0,
                                scheduled_while_claimed=0 if args.origin else None,
                                owned_mutex_protocol=protocol,
                                owned_release_policy='guarded_owner_release'))
        finally:
            collect()
            os.close(fd)
    runtime.write_json(out/'result.json', dict(passed=True, drained=True, results=results))
    print('PASS: owned queued admission cooling, actual sleep, SELF pickup and drain')


if __name__ == '__main__':
    main()
