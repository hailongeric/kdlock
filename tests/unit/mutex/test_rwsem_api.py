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
            assert status == 0, (body, status, log)
            for target in controls.values():
                label = f'loc_{target:x}:'.encode()
                if label in assembly:
                    # A retained typed CALL can have a callee-table exit
                    # label. It must contain only the exact control exit,
                    # never decoded physical acquisition/release helper code.
                    stub = assembly.split(label, 1)[1].split(b'\n\n', 1)[0]
                    instructions = [' '.join(line.decode().split())
                                    for line in stub.splitlines() if line.strip()]
                    assert instructions == [f'MOVABS R14, 0x{target:x}',
                                            'MOV Stack_IJ, 0x1', 'JMP exit'], instructions
            if body == 'write_body':
                assert b'clobber_complete' in assembly and b'kd_terminal_full_' in assembly, assembly
            else:
                assert text[entry-base:entry-base+2] == b'\x31\xc0'
                # GCC can share the acquisition-failure RET block with the
                # success unlock continuation. That reachable source PC must
                # use the exact FULL CALL, not terminal-clobber optimization.
                listing = subprocess.check_output(
                    ['objdump', '-d', '--disassemble=' + body, binary], text=True)
                calls = re.findall(r'^\s*([0-9a-f]+):\s+e8(?:\s+[0-9a-f]{2}){4}\s+call\s+'
                                   r'[0-9a-f]+\s+<kd_rwsem_up_write_clobber_v1>', listing, re.M)
                assert len(calls) == 1, listing
                return_pc = int(calls[0], 16) + 5
                emitted = assembly.decode()
                assert f'loc_{return_pc:x}:' in emitted, (listing, emitted)
                assert re.search(rf'MOVABS\s+R\d+,\s*0x{return_pc:x}\b', emitted, re.I), emitted
                target = controls['kd_rwsem_up_write_clobber_v1']
                assert re.search(rf'JMP\s+loc_{target:x}\b', emitted), emitted
        print('PASS public rwsem: compiled ordinary/integer capture, exact typed release, downgrade and ABI2 endpoints')


if __name__ == '__main__':
    main()
