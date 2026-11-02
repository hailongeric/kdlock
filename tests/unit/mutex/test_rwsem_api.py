"""Guest-only compiled public rwsem facade and production reservation retirement.

This checks literal compiler capture/terminal calls and prepared/local routing.
Scheduler, mutex acquisition and ACK primitives are deterministic substitutes;
the live rwsem/JIT probes establish their concurrent behavior separately.
"""
from pathlib import Path
import re
import subprocess
import tempfile

from source_text import ROOT, read_source
from test_spin_shadow import definition
from test_jit_diagnostics import render


def stripped(path):
    return re.sub(r"^#include .*$", "", read_source(ROOT / path), flags=re.M)


def main():
    source = read_source(ROOT / 'kernel_module/kd_rwsem.c')
    core = "\n".join(definition(source, name) for name in (
        'static void kd_rwsem_release_local(struct kd_rwsem *sem)',
        'void kd_up_write(struct kd_rwsem *sem)',
        'void kd_downgrade_write(struct kd_rwsem *sem)'))
    direct = stripped('include/kd_mutex_direct.h')
    direct = direct[direct.index('#define KD_MUTEX_DIRECT_CALL('):
                    direct.index('/* Explicit outer-only pair.')]
    api_source = read_source(ROOT / 'kernel_module/kd_rwsem_api.c')
    provider = definition(api_source, 'int kd_rwsem_prepare(struct kd_rwsem *sem, unsigned long ip, unsigned int abi)')
    for result, first_line in (
        ('void', 'kd_rwsem_down_write_clobber_v1(struct kd_rwsem *sem, unsigned long sp,'),
        ('int', 'kd_rwsem_down_write_interruptible_clobber_v1(struct kd_rwsem *sem,'),
        ('int', 'kd_rwsem_down_write_killable_clobber_v1(struct kd_rwsem *sem,'),
        ('void', 'kd_rwsem_up_write_clobber_v1(struct kd_rwsem *sem, unsigned long sp,'),
    ):
        # These provider definitions split their return type and identifier.
        provider += '\n' + result + ' ' + definition(api_source, first_line)
    with tempfile.TemporaryDirectory(prefix='kd-rwsem-api-') as directory:
        path = Path(directory)
        for name, text in {
            'types.h': stripped('include/kd_mutex_types.h') + stripped('include/kd_rwsem_types.h'),
            'decls.h': stripped('include/kd_rwsem.h'),
            'core.h': core,
            'api.h': direct + stripped('include/kd_rwsem_api.h'),
            'provider.h': provider,
        }.items():
            (path / name).write_text(text)
        binary = path / 'api'
        subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-fno-omit-frame-pointer', '-fno-optimize-sibling-calls',
                        '-fno-reorder-blocks-and-partition', '-fno-toplevel-reorder',
                        '-mno-red-zone', '-fno-pie', '-no-pie', '-I', str(path),
                        str(ROOT / 'tests/unit/mutex/rwsem_api_fixture.c'), '-o', str(binary)],
                       check=True, timeout=30)
        output = subprocess.check_output([binary], text=True, timeout=15)
        print(output, end='')
        symbols, sizes = {}, {}
        for line in subprocess.check_output(['nm', '-S', '--defined-only', binary], text=True).splitlines():
            words = line.split()
            if len(words) in (3, 4):
                symbols[words[-1]] = int(words[0], 16)
                if len(words) == 4:
                    sizes[words[-1]] = int(words[1], 16)
        sections = subprocess.check_output(['objdump', '-h', binary], text=True)
        base = int(next(line.split()[3] for line in sections.splitlines()
                        if line.split()[1:2] == ['.text']), 16)
        subprocess.run(['objcopy', '--dump-section', f'.text={path}/text.bin', binary], check=True)
        text = (path / 'text.bin').read_bytes()
        controls = {name: symbols[name] for name in (
            'kd_rwsem_down_write_clobber_v1',
            'kd_rwsem_down_write_interruptible_clobber_v1',
            'kd_rwsem_down_write_killable_clobber_v1',
            'kd_rwsem_up_write_clobber_v1')}
        for body, label in (('write_body', 'rwsem_entry'),
                            ('interruptible_body', 'rwsem_interruptible_entry'),
                            ('killable_body', 'rwsem_killable_entry')):
            entry, start = symbols[label], symbols[body]
            assert start < entry < start + sizes[body]
            raw = text[start-base:start-base+sizes[body]]
            assembly, log, status = render('', regions=[(raw, start, [entry])], entry=entry,
                kernel_symbols=controls, abi=2, lock_kind='mutex', mutex_stack_bytes=256,
                return_status=True, trusted_source=True)
            assert status == 0 and b'clobber_complete' in assembly, log
            for target in controls.values():
                assert f'loc_{target:x}:'.encode() not in assembly
            if body != 'write_body':
                assert text[entry-base:entry-base+2] == b'\x31\xc0'
        print('PASS public rwsem: compiled ordinary/integer capture, exact typed release, downgrade and ABI2 endpoints')


if __name__ == '__main__':
    main()
