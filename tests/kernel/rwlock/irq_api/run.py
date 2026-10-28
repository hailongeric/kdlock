#!/usr/bin/env python3
"""Guest-only local rwlock API and interrupted-reader regression; no JIT."""
import argparse
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity

MODULE = 'kd_rwlock_irq_api_test'
PASS = 'kd_rwlock_irq_api_test PASS irq_readers=1 writers=1 errors=0 idle=1 JIT=0'


def idle():
    runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
    rt.require(not Path('/sys/module', MODULE).exists(), 'existing rwlock IRQ probe')
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            name = path.read_text().strip()
        except FileNotFoundError:
            continue
        rt.require(name not in ('kd_rw_irq_read', 'kd_rw_irq_write'), 'existing probe worker')


def sources(root):
    result = {}
    for directory in ('include', 'kernel_module', 'tests/kernel/rwlock/irq_api',
                      'bench/spin_cacheline', 'kernel_baseline', 'kernel_integration/linux70',
                      'disassem'):
        for path in (root / directory).rglob('*'):
            relative = path.relative_to(root)
            if (not path.is_file() or path.name.endswith('.mod.c') or
                    any(part.startswith('.') or part == '__pycache__' for part in relative.parts)):
                continue
            if path.suffix in ('.c', '.h', '.inc', '.S', '.py', '.def', '.json', '.patch') or path.name == 'Makefile':
                result[str(relative)] = rt.digest(path)
    result['bench/archive_run.py'] = rt.digest(root / 'bench/archive_run.py')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/'), 'run inside recovery guest')
    rt.require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed recovery snapshot required')
    rt.require(len(os.sched_getaffinity(0)) >= 3, 'three available CPUs required')
    idle()
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    result = dict(passed=False, drained=False, jit_bodies=0, actual_mm=False,
                  snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'])
    messages = ''
    fd = None

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

    def check_log():
        logs()
        rt.require(not rt.FAULT.search(messages), 'kernel fault; retain modules')

    try:
        result['kernel_identity'] = kernel_identity.capture(args, out, rt.command)
        hashes = sources(ROOT)
        source = out / 'source'
        for relative in hashes:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        rt.write_json(out / 'source-sha256.json', hashes)
        provider = source / 'kernel_module/kdlock_km.ko'
        probe = source / ('tests/kernel/rwlock/irq_api/payload/' + MODULE + '.ko')
        rt.command(['make', '-C', provider.parent, f'KDIR={args.kernel_source}',
                    'W=1', 'KDLOCK_SELFTEST=0', 'UBSAN_SANITIZE=n'], out / 'build-provider.log', timeout=180)
        rt.command(['make', '-C', probe.parent, f'KDIR={args.kernel_source}',
                    f'KDLOCK_INCLUDE={source / "include"}',
                    f'KBUILD_EXTRA_SYMBOLS={provider.parent / "Module.symvers"}'],
                   out / 'build-probe.log', timeout=180)
        binaries = {str(path): rt.digest(path) for path in (provider, probe)}
        rt.write_json(out / 'binary-sha256.json', binaries)

        def verify():
            rt.require(sources(ROOT) == hashes and sources(source) == hashes, 'source inputs changed')
            rt.require(all(rt.digest(Path(path)) == value for path, value in binaries.items()),
                       'frozen binaries changed')

        verify()
        idle()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        rt.command(['insmod', provider], out / 'load-provider.log')
        rt.command(['insmod', probe], out / 'load-probe.log', timeout=30)
        check_log()
        rt.require(PASS in messages, 'missing exact local rwlock PASS')
        verify()
        rt.command(['rmmod', MODULE], out / 'unload-probe.log')
        rt.command([sys.executable, source / 'disassem/device_session.py', 'retire'],
                   out / 'retire.log')
        rt.command(['rmmod', 'kdlock_km'], out / 'unload-provider.log')
        check_log()
        idle()
        result.update(passed=True, drained=True, irq_readers=1, writers=1, errors=0)
    finally:
        logs()
        if fd is not None:
            os.close(fd)
        rt.write_json(out / 'result.json', result)


if __name__ == '__main__':
    main()
