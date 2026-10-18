#!/usr/bin/env python3
"""Guest-only rwsem sleeping and outer admission checks; no result counts as JIT."""
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


def idle():
    rt.idle()
    for name in ('rwsem_probe', 'rwlock_bench', 'rwlock_test', 'real_api',
                 'tclock_backend_km', 'tclock_mutex_backend_km',
                 'tclock_rwlock_backend_km', 'tc_allocator_guard',
                 'kd_mutex_local_probe', 'kd_spin_irq_api_test'):
        rt.require(not Path('/sys/module', name).exists(), 'existing module: ' + name)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            name = path.read_text().strip()
        except FileNotFoundError:
            continue
        # Inspect exact thread comm values, not command-line substrings: this
        # runner's own path contains rwsem and must not reject itself.
        rt.require(name not in ('rb_worker', 'kd_rwsem_probe', 'kd_rwsem_cancel', 'kd-cancel')
                   and not name.startswith(('kd-local/', 'kd_mtask_', 'kd_irq_api/')),
                   f'existing task: {path}: {name}')


def sources(root):
    hashes = {}
    for directory in ('include', 'kernel_module', 'tests/kernel/rwsem', 'bench/spin_cacheline',
                      'kernel_baseline', 'disassem', 'tests/protocols'):
        for path in (root / directory).rglob('*'):
            relative = path.relative_to(root)
            if (not path.is_file() or any(s.startswith('.') or s == '__pycache__' for s in relative.parts)
                    or path.name.endswith('.mod.c') or
                    (path.suffix not in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch') and
                     path.name != 'Makefile')):
                continue
            hashes[str(relative)] = rt.digest(path)
    return hashes


def verify_inputs(source, hashes, binaries=None):
    rt.require(sources(ROOT) == hashes, 'source inputs changed after snapshot')
    rt.require(sources(source) == hashes, 'frozen source differs from snapshot')
    if binaries is not None:
        rt.require(all(rt.digest(Path(path)) == expected for path, expected in binaries.items()),
                   'frozen binary changed')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--client', action='store_true')
    kernel_identity.arguments(p)
    args = p.parse_args()
    if args.client:
        buffer = bytearray(96)
        with open('/dev/kd_rwsem_probe', 'rb', buffering=0) as device:
            fcntl.ioctl(device, 0x80605301, buffer, True)
        row = dict(zip(('errors', 'api_checks', 'readers_slept', 'writer_slept',
                        'late_reader_slept', 'cancellation_checks', 'colocated',
                        'idle', 'outer_readers_slept', 'outer_writer_slept',
                        'downgrade_checks', 'publication_checks'), struct.unpack('=12Q', buffer)))
        print(json.dumps(row))
        return 0 if row == dict(errors=0, api_checks=8, readers_slept=2,
                               writer_slept=1, late_reader_slept=1,
                               cancellation_checks=10, colocated=1, idle=1,
                               outer_readers_slept=2, outer_writer_slept=1,
                               downgrade_checks=1, publication_checks=3) else 1
    rt.require(args.output and os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed recovery guest required')
    idle()
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    identity = kernel_identity.capture(args, out, rt.command)
    source = out / 'source'
    hashes = sources(ROOT)
    for relative in hashes:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    verify_inputs(source, hashes)
    rt.write_json(out / 'source-sha256.json', hashes)
    provider = source / 'kernel_module/kdlock_km.ko'
    module = source / 'tests/kernel/rwsem/rwsem_probe.ko'
    rt.command(['make', '-C', provider.parent, f'KDIR={args.kernel_source}', 'W=1',
                'KDLOCK_SELFTEST=0', 'UBSAN_SANITIZE=n'], out / 'build-provider.log', timeout=180)
    rt.command(['make', '-C', module.parent, f'KDIR={args.kernel_source}',
                f'KDLOCK_INCLUDE={source / "include"}',
                f'KBUILD_EXTRA_SYMBOLS={provider.parent / "Module.symvers"}'], out / 'build-probe.log', timeout=180)
    binaries = {str(path): rt.digest(path) for path in (provider, module)}
    verify_inputs(source, hashes, binaries)
    rt.write_json(out / 'binary-sha256.json', binaries)
    results = []
    # No image or translator is provided for the outer bodies. Assertions
    # exercise local outer returns and ordering before queue publication.
    for mode in ('local',):
        idle()
        verify_inputs(source, hashes, binaries)
        path = out / mode
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
            rt.command(['insmod', provider], path / 'load-provider.log')
            rt.command(['insmod', module], path / 'load-probe.log')
            data = rt.command([sys.executable, source / 'tests/kernel/rwsem/run.py', '--client'],
                              path / 'result.json', timeout=40)
            check_log()
            verify_inputs(source, hashes, binaries)
            rt.command(['rmmod', 'rwsem_probe'], path / 'unload-probe.log')
            rt.command([sys.executable, source / 'disassem/device_session.py', 'retire'], path / 'retire.log')
            rt.command(['rmmod', 'kdlock_km'], path / 'unload-provider.log')
            check_log()
            idle()
            results.append(dict(execution=mode, **json.loads(data)))
        finally:
            check_log()
            os.close(fd)
    rt.write_json(out / 'result.json', dict(passed=True, drained=True, jit_bodies=0,
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], kernel_identity=identity, results=results,
        binaries={str(p.relative_to(out)): rt.digest(p) for p in (module, provider)}))
    print('PASS: sleeping readers, ordinary/outer writer admission, same-CPU '
          'progress, trylocks, downgrade before publication, cancellation and drain')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
