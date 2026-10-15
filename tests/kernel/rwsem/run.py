#!/usr/bin/env python3
"""Guest-only sleeping rwsem checks; no constructed result counts as JIT."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--client', action='store_true')
    kernel_identity.arguments(p)
    args = p.parse_args()
    if args.client:
        buffer = bytearray(48)
        with open('/dev/kd_rwsem_probe', 'rb', buffering=0) as device:
            fcntl.ioctl(device, 0x80305301, buffer, True)
        row = dict(zip(('errors', 'api_checks', 'readers_slept', 'writer_slept',
                        'late_reader_slept', 'idle'), struct.unpack('=6Q', buffer)))
        print(json.dumps(row))
        return 0 if row == dict(errors=0, api_checks=8, readers_slept=2,
                               writer_slept=1, late_reader_slept=1, idle=1) else 1
    rt.require(args.output and os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed recovery guest required')
    rt.idle()
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    identity = kernel_identity.capture(args, out, rt.command)
    hashes = {}
    for directory in ('include', 'kernel_module', 'tests/kernel/rwsem', 'bench/spin_cacheline',
                      'kernel_baseline', 'disassem', 'tests/protocols'):
        for path in (ROOT / directory).rglob('*'):
            if (not path.is_file() or any(s.startswith('.') or s == '__pycache__' for s in path.relative_to(ROOT).parts)
                    or path.name.endswith('.mod.c') or
                    (path.suffix not in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch') and
                     path.name != 'Makefile')):
                continue
            relative = path.relative_to(ROOT)
            target = out / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            hashes[str(relative)] = rt.digest(path)
    rt.write_json(out / 'source-sha256.json', hashes)
    source = out / 'source'
    provider = source / 'kernel_module/kdlock_km.ko'
    module = source / 'tests/kernel/rwsem/rwsem_probe.ko'
    rt.command(['make', '-C', provider.parent, f'KDIR={args.kernel_source}', 'W=1',
                'KDLOCK_SELFTEST=0', 'UBSAN_SANITIZE=n'], out / 'build-provider.log', timeout=180)
    rt.command(['make', '-C', module.parent, f'KDIR={args.kernel_source}',
                f'KDLOCK_INCLUDE={source / "include"}',
                f'KBUILD_EXTRA_SYMBOLS={provider.parent / "Module.symvers"}'], out / 'build-probe.log', timeout=180)
    results = []
    # Ordinary SELF admission is Linux-style owner spinning/sleeping; this
    # result-poll budget is relevant only to delegated requests tested elsewhere.
    for spins in (4096,):
        path = out / f'spins-{spins}'
        path.mkdir()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        messages = ''

        def check_log():
            nonlocal messages
            while True:
                try:
                    messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
                except BlockingIOError:
                    break
            (path / 'kernel.log').write_text(messages)
            if rt.FAULT.search(messages):
                raise rt.Failure('KERNEL_FAULT', 'kernel fault; retain modules', unsafe=True)

        try:
            rt.command(['insmod', provider, f'owned_mutex_spin_limit={spins}'], path / 'load-provider.log')
            rt.command(['insmod', module], path / 'load-probe.log')
            data = rt.command([sys.executable, source / 'tests/kernel/rwsem/run.py', '--client'],
                              path / 'result.json', timeout=40)
            check_log()
            rt.command(['rmmod', 'rwsem_probe'], path / 'unload-probe.log')
            rt.command([sys.executable, source / 'disassem/device_session.py', 'retire'], path / 'retire.log')
            rt.command(['rmmod', 'kdlock_km'], path / 'unload-provider.log')
            check_log()
            rt.idle()
            results.append(dict(spin_limit=spins, **json.loads(data)))
        finally:
            check_log()
            os.close(fd)
    rt.write_json(out / 'result.json', dict(passed=True, drained=True, jit_bodies=0,
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], kernel_identity=identity, results=results,
        binaries={str(p.relative_to(out)): rt.digest(p) for p in (module, provider)}))
    print('PASS: concurrent sleeping readers, parked writer/late reader, exclusion, trylocks, downgrade and drain')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
