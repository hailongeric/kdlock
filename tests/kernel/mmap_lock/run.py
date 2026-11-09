#!/usr/bin/env python3
"""Serial actual-mm API probe on the separately captured integration kernel."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity
sys.path.insert(0, str(ROOT / 'bench/mmap_writer'))
import shared_platform

FIELDS = ('abi', 'use_kd', 'mm', 'lock', 'checks', 'errors', 'api_checks', 'nested_checks',
          'cancellation_checks', 'readers_slept', 'writer_slept', 'late_reader_slept',
          'downgrade_checks', 'transfer_checks', 'irq_checks', 'destroy_checks', 'idle')


def idle():
    rt.idle()
    for p in Path('/sys/module').iterdir():
        rt.require(not p.name.startswith(('kd_', 'tc_', 'tclock_', 'jit_')) and
                   p.name != 'rwsem_probe', 'existing project module: ' + p.name)


def gate_waiter_layout(text):
    """Complete only the source-bound private waiter tag used by this fixture."""
    flags = re.findall(r'^#define KD_(?:WAITERS|HANDOFF|PICKUP|FLAGS) [^\n]+$', text, re.M)
    structs = re.findall(r'^struct kd_local_waiter \{\n(?:[^\n]*\n)*?\};$', text, re.M)
    rt.require(len(flags) == 4 and len(structs) == 1, 'captured gate layout declaration differs')
    declaration = '\n'.join(flags) + '\n\n' + structs[0]
    return ('/* SPDX-License-Identifier: GPL-2.0 */\n'
            '/* Test-only view checked against the captured local-gate source by run.py. */\n'
            '#ifndef KD_MMAP_PROBE_GATE_WAITER_LAYOUT_H\n'
            '#define KD_MMAP_PROBE_GATE_WAITER_LAYOUT_H\n'
            '#include <linux/list.h>\n\n' +
            declaration.replace('kd_', 'kd_mmap_').replace('KD_', 'KD_MMAP_') +
            '\n\n#endif\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--client', action='store_true')
    p.add_argument('--mode', choices=('native', 'kd'), required=True)
    p.add_argument('--reuse-probe', type=Path,
                   help='verified prebuilt receipt; reuse prior basic/build checks')
    shared_platform.arguments(p, required=False)
    a = p.parse_args()
    expected_kd = int(a.mode == 'kd')
    if a.client:
        buffer = bytearray(8 * len(FIELDS))
        with open('/dev/kd_mmap_probe', 'rb', buffering=0) as device:
            fcntl.ioctl(device, 0x80884d71, buffer, True)
        row = dict(zip(FIELDS, struct.unpack('=17Q', buffer)))
        print(json.dumps(row), flush=True)
        expected = dict(abi=1, use_kd=expected_kd, errors=0, api_checks=8, nested_checks=1,
                        cancellation_checks=3, readers_slept=2, writer_slept=1,
                        late_reader_slept=1, downgrade_checks=1, transfer_checks=1,
                        irq_checks=1, destroy_checks=1, idle=1)
        rt.require(all(row[k] == v for k, v in expected.items()) and row['mm'] and
                   row['lock'] and row['checks'] >= 100, 'probe result differs', 'CHECK_FAILED')
        return
    rt.require(a.output is not None, 'new evidence output required')
    shared_platform.guest(a)
    idle()
    boot_args = Path('/proc/cmdline').read_text().split()
    rt.require(boot_args.count('kd_mmap=' + ('on' if expected_kd else 'off')) == 1 and
               sum(s.startswith('kd_mmap=') for s in boot_args) == 1 and
               all(s in boot_args for s in ('nokaslr', 'nopvspin')), 'explicit boot mode/policy differs')
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new evidence output required')
    out.mkdir(parents=True)
    result = dict(state='PREPARATION', passed=False, drained=False, accepted=False,
                  mode=a.mode, delegated=False, jit_bodies=0, full_suite=False,
                  snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], boot_args=boot_args,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    rt.write_json(out / 'result.json', result)
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
        rt.require(not rt.FAULT.search(messages), 'kernel fault; retain module', 'KERNEL_FAULT')

    try:
        result.update(shared_platform.admit(a,out))
        support=shared_platform.freeze_support(out)
        source, hashes = out / 'source', {}
        layout_source = ROOT / 'kernel_module/kd_mutex_local.c'
        layout_header = ROOT / 'tests/kernel/mmap_lock/fixture/gate_waiter_layout.h'
        rt.require(layout_header.read_text() == gate_waiter_layout(layout_source.read_text()),
                   'test-only gate view differs from captured source')
        layout_copy = source / 'kernel_module/kd_mutex_local.c'
        layout_copy.parent.mkdir(parents=True)
        shutil.copyfile(layout_source, layout_copy)
        hashes['kernel_module/kd_mutex_local.c'] = rt.digest(layout_source)
        result['queue_observation'] = dict(schema=1, kinds=['reader-phase', 'writer-gate', 'reader-drain'],
            gate_source_sha256=hashes['kernel_module/kd_mutex_local.c'],
            gate_layout_sha256=rt.digest(layout_header), singleton_task_checked_under_wait_lock=True,
            cancellation_holder_checked_before_release=True)
        for directory in ('tests/kernel/mmap_lock', 'tests/unit', 'include', 'daemon'):
            for path in (ROOT / directory).rglob('*'):
                rel = path.relative_to(ROOT)
                if (not path.is_file() or any(s.startswith('.') or s == '__pycache__' for s in rel.parts)
                        or path.name.endswith('.mod.c') or
                        (path.suffix not in ('.c', '.h', '.inc', '.S', '.py', '.def') and path.name != 'Makefile')):
                    continue
                hashes[str(rel)] = rt.digest(path)
                target = source / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        rt.write_json(out / 'source-sha256.json', hashes)
        shutil.copyfile(__file__, out / 'runner.py')

        def verify():
            shared_platform.verify_boot(a)
            shared_platform.common.verify_maps(support)
            for name, h in hashes.items():
                rt.require(rt.digest(ROOT / name) == rt.digest(source / name) == h,
                           'frozen source changed: ' + name)

        payload = source / 'tests/kernel/mmap_lock/fixture/kd_mmap_probe.ko'
        if a.reuse_probe:
            from elftools.elf.elffile import ELFFile
            prior = json.loads(a.reuse_probe.read_text())
            expected_sources = {name: h for name, h in hashes.items()
                                if name.startswith('tests/kernel/mmap_lock/fixture/')}
            rt.require(prior['passed'] and prior['source'] == expected_sources,
                       'prebuilt probe source bindings differ')
            old_payload = Path(prior['module'])
            rt.require(rt.digest(old_payload) == prior['sha256'] and
                       rt.digest(a.kernel_source / 'vmlinux') == prior['vmlinux_sha256'],
                       'prebuilt probe or kernel ELF differs')
            with (a.kernel_source / 'vmlinux').open('rb') as f:
                btf = ELFFile(f).get_section_by_name('.BTF').data()
            rt.require(hashlib.sha256(btf).hexdigest() == prior['base_btf_sha256'] ==
                       rt.digest(Path('/sys/kernel/btf/vmlinux')), 'prebuilt base BTF differs')
            with old_payload.open('rb') as f:
                rt.require(ELFFile(f).get_section_by_name('.BTF') is not None,
                           'prebuilt split BTF missing')
            vermagic = rt.command(['modinfo', '-F', 'vermagic', old_payload], out / 'vermagic.log')
            rt.require(vermagic.split()[0] == os.uname().release, 'prebuilt release differs')
            shutil.copyfile(old_payload, payload)
            rt.require(rt.digest(payload) == prior['sha256'], 'prebuilt copy differs')
            shutil.copyfile(a.reuse_probe, out / 'prebuilt.json')
            result.update(reused_probe=str(a.reuse_probe), basic_programs=0,
                          base_btf_sha256=prior['base_btf_sha256'])
        else:
            rt.command([sys.executable, '-m', 'pip', 'check'], out / 'dependencies.log', timeout=60)
            rt.command(['make', '-C', source / 'tests/unit', 'run', 'PYTHON=' + sys.executable,
                        'PY_TESTS='], out / 'basic.log', timeout=180)
            rt.command(['make', '-C', payload.parent, 'KDIR=' + str(a.kernel_source),
                        'W=1', 'UBSAN_SANITIZE=n'], out / 'build.log', timeout=180)
            result['basic_programs'] = 2
        result['probe_sha256'] = rt.digest(payload)
        verify()
        idle()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        rt.command(['insmod', payload, 'expected_kd=' + str(expected_kd)], out / 'load.log')
        result['state'] = 'RUNNING'
        rt.write_json(out / 'result.json', result)
        data = rt.command([sys.executable, Path(__file__), '--client', '--mode', a.mode],
                          out / 'probe.json', timeout=120)
        logs()
        result['probe'] = json.loads(data)
        verify()
        rt.require(rt.digest(payload) == result['probe_sha256'], 'probe binary changed')
        rt.command(['rmmod', 'kd_mmap_probe'], out / 'unload.log')
        logs()
        idle()
        result.update(state='COMPLETE', passed=True, drained=True, source_unchanged=True)
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        shared_platform.common.finish_logs(out,result,logs,fd)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
