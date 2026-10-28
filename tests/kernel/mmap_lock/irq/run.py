#!/usr/bin/env python3
"""Focused standalone Native/KD adapter regression in the recovery guest."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity

FIELDS = ('checks', 'errors', 'contexts', 'concurrent', 'writers', 'cancellations',
          'rollbacks', 'injections', 'atomic_wakes', 'idle')


def idle():
    runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--client', action='store_true')
    parser.add_argument('--reuse-objects', type=Path)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    if args.client:
        buffer = bytearray(80)
        with open('/dev/kd_mmap_irq_probe', 'rb', buffering=0) as device:
            fcntl.ioctl(device, 0x80504901, buffer, True)
        row = dict(zip(FIELDS, struct.unpack('=10Q', buffer)))
        print(json.dumps(row), flush=True)
        expected = dict(errors=0, contexts=6, concurrent=6, writers=15,
                        cancellations=3, rollbacks=3, injections=3, atomic_wakes=0, idle=1)
        assert all(row[k] == v for k, v in expected.items()) and row['checks'] >= 200, row
        return
    assert os.geteuid() == 0 and str(ROOT).startswith('/root/')
    for name in list(os.environ):
        if name.startswith('LC_'):
            del os.environ[name]
    os.environ.update(LANG='C', LC_ALL='C')
    assert os.uname().release == '6.1.159-kdclobber2'
    assert os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and os.environ.get('KDLOCK_SNAPSHOT_TAG')
    idle()
    out = args.output.resolve()
    assert not out.exists() and not out.is_relative_to(ROOT)
    out.mkdir(parents=True)
    result = dict(passed=False, drained=False, kernel_built=False, installed=False,
                  booted=False, actual_mm=False, timing=False,
                  snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    fd = None
    messages = ''

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
        rt.require(not rt.FAULT.search(messages), 'kernel fault; retain module')

    try:
        # The measured existing provider is 15 MiB. This check generates five
        # small objects and a probe only; 256 MiB is reserved for all scratch.
        result['space'] = dict(root_free=shutil.disk_usage(out).free,
                              tmp_free=shutil.disk_usage('/tmp').free,
                              data_free=shutil.disk_usage('/mnt/kdlock-builds').free,
                              budget=256 * 1024 * 1024)
        assert result['space']['root_free'] > result['space']['budget']
        result['kernel_identity'] = kernel_identity.capture(args, out, rt.command)
        from elftools.elf.elffile import ELFFile
        with (args.kernel_source / 'vmlinux').open('rb') as f:
            btf = ELFFile(f).get_section_by_name('.BTF').data()
        btf_hash = hashlib.sha256(btf).hexdigest()
        assert btf_hash == rt.digest(Path('/sys/kernel/btf/vmlinux')), 'live/build base BTF mismatch'
        result['base_btf_sha256'] = btf_hash
        release = os.uname().release
        image = Path('/boot/vmlinuz-' + release)
        assert rt.digest(image) == rt.digest(args.kernel_source / 'arch/x86/boot/bzImage')
        result['boot_artifacts'] = {str(p): rt.digest(p) for p in
                                   (image, Path('/boot/initrd.img-' + release))}
        generated = out / 'generated'
        inputs, outputs = runpy.run_path(str(ROOT / 'kernel_integration/mmap_lock/prepare.py'))['generated_sources'](generated)
        private = generated / 'kernel/locking/kd_mmap'
        objects = ('adapter.o', 'pool.o', 'kd_mmap_mutex_local.o', 'kd_mmap_mutex_osq.o', 'kd_mmap_rwsem.o')
        # Uninstrumented production objects, including the adapter, first.
        command = ['make', '-C', str(args.kernel_source), 'M=' + str(private), 'W=1',
                   'UBSAN_SANITIZE=n', 'KCFLAGS=-I' + str(generated / 'include'), *objects]
        if args.reuse_objects:
            previous = args.reuse_objects.resolve()
            prior = json.loads((previous / 'result.json').read_text())
            assert prior['kernel_identity'] == result['kernel_identity']
            assert prior['base_btf_sha256'] == btf_hash
            for name, digest in outputs.items():
                assert rt.digest(previous / 'generated' / name) == digest, name
            receipt = json.loads((previous / 'production-build.log.command.json').read_text())
            # This field is recorded only after rt.command returned success.
            assert set(prior['production_objects']) == set(objects)
            assert [s.replace(str(previous), str(out)) for s in receipt['argv']] == command
            for name, digest in prior['production_objects'].items():
                assert rt.digest(previous / 'generated/kernel/locking/kd_mmap' / name) == digest
            result['production_objects'] = prior['production_objects']
            result['reused_objects_from'] = str(previous)
        else:
            rt.command(command, out / 'production-build.log', timeout=180)
            result['production_objects'] = {n: rt.digest(private / n) for n in objects}
        module_dir = out / 'payload'
        module_dir.mkdir()
        for p in private.iterdir():
            if p.suffix in ('.c', '.h'):
                shutil.copyfile(p, module_dir / p.name)
        # Builtins directly call the unexported I/O scheduler helpers. Use the
        # maintained module resolver for this module, preserving all lock bodies.
        prepare = runpy.run_path(str(ROOT / 'kernel_integration/mmap_lock/prepare.py'))
        (module_dir / 'kd_mmap_mutex_local.c').write_text(
            prepare['rename'](prepare['local_mutex_source'](
                (ROOT / 'kernel_module/kd_mutex_local.c').read_text())))
        result['module_io_bridge'] = 'maintained module resolver; no I/O operation tested'
        for p in Path(__file__).with_name('payload').iterdir():
            shutil.copyfile(p, module_dir / p.name)
            inputs[str(p.relative_to(ROOT))] = rt.digest(p)
        inputs[str(Path(__file__).relative_to(ROOT))] = rt.digest(Path(__file__))
        inputs['kernel_integration/mmap_lock/prepare.py'] = rt.digest(ROOT / 'kernel_integration/mmap_lock/prepare.py')
        rt.write_json(out / 'inputs.json', inputs)
        shutil.copyfile(__file__, out / 'runner.py')
        rt.command(['make', '-C', args.kernel_source, 'M=' + str(module_dir), 'W=1',
                    'KD_IRQ_INCLUDE=' + str(generated / 'include'), 'modules'],
                   out / 'probe-build.log', timeout=180)
        module = module_dir / 'kd_mmap_irq_probe.ko'
        result['probe_sha256'] = rt.digest(module)
        with module.open('rb') as f:
            assert ELFFile(f).get_section_by_name('.BTF') is not None
        result['split_btf'] = True
        for name, digest in inputs.items():
            assert rt.digest(ROOT / name) == digest, name
        idle()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        rt.command(['insmod', module], out / 'load.log', timeout=30)
        data = rt.command([sys.executable, Path(__file__), '--client'], out / 'probe.json', timeout=120)
        logs()
        result['probe'] = json.loads(data)
        rt.command(['rmmod', 'kd_mmap_irq_probe'], out / 'unload.log', timeout=30)
        logs()
        idle()
        for name, digest in inputs.items():
            assert rt.digest(ROOT / name) == digest, name
        for name, digest in result['boot_artifacts'].items():
            assert rt.digest(Path(name)) == digest, name
        assert rt.digest(module) == result['probe_sha256']
        result.update(passed=True, drained=True, source_unchanged=True, recovery_unchanged=True)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        try:
            logs()
        finally:
            rt.write_json(out / 'result.json', result)
            if fd is not None:
                os.close(fd)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
