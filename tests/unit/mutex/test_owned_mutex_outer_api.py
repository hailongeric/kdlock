"""Guest-only compiled owned outer ABI, including its actual generated JIT."""
import re
import subprocess
import tempfile
from pathlib import Path
from test_jit_diagnostics import ROOT, render


def main():
    header = re.sub(r'^#include .*$', '',
                    (ROOT/'include/kd_owned_mutex_direct.h').read_text(), flags=re.M)
    fixture = (ROOT/'tests/unit/mutex/mutex_outer_api_fixture.c').read_text()
    # Reuse the destructive GPR/stack oracle, with the actual owned header and
    # owned endpoints. It tests the same ABI contract, not a copy of that header.
    fixture = fixture.replace('kd_mutex_', 'kd_owned_mutex_')
    fixture = fixture.replace('kd_hotlock_mutex_entry', 'kd_hotlock_owned_mutex_entry')
    fixture = fixture.replace('KD_MUTEX_', 'KD_OWNED_MUTEX_')
    fixture = fixture.replace('struct mutex', 'struct kd_mutex')
    fixture = fixture.replace('mutex_unlock(', 'kd_owned_mutex_outer_unlock_v1(')
    fixture = fixture.replace('#include "outer_api.h"',
                              '#define kd_mutex_unlock kd_owned_mutex_unlock_v1\n'
                              '#include "outer_api.h"')
    fixture = fixture.replace('untouched Linux owner', 'untouched owned mutex owner')
    with tempfile.TemporaryDirectory(prefix='kd-owned-outer-') as directory:
        path = Path(directory)
        (path/'outer_api.h').write_text(header)
        (path/'fixture.c').write_text(fixture)
        (path/'asm').mkdir()
        (path/'linux').mkdir()
        (path/'linux/objtool.h').write_text('#define UNWIND_HINT(...) ""\n')
        (path/'asm/asm.h').write_text('/* supplied by fixture */\n')
        (path/'asm/nospec-branch.h').write_text(
            '#define CALL_NOSPEC "call *%[thunk_target]\\n"\n')
        flags = ['-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                 '-fno-omit-frame-pointer', '-fno-optimize-sibling-calls',
                 '-fno-reorder-blocks-and-partition', '-fno-toplevel-reorder',
                 '-mno-red-zone', '-mpreferred-stack-boundary=4', '-fno-pie',
                 '-I'+directory, '-I'+str(ROOT/'include')]
        subprocess.run(['cc', *flags, '-c', str(path/'fixture.c'),
                        '-o', str(path/'fixture.o')], check=True, timeout=30)
        link = ['cc', '-no-pie', '-Wl,--section-start=.text=0x1000000',
                '-Wl,--section-start=.outer_lock=0x60000000', str(path/'fixture.o')]
        binary = path/'fixture'
        subprocess.run([*link, '-o', str(binary)], check=True, timeout=30)
        subprocess.run([binary], check=True, timeout=10)
        symbols, sizes = {}, {}
        for line in subprocess.check_output(['nm', '-S', '--defined-only', binary],
                                            text=True).splitlines():
            words = line.split()
            if len(words) in (3, 4):
                symbols[words[-1]] = int(words[0], 16)
                if len(words) == 4:
                    sizes[words[-1]] = int(words[1], 16)
        section = next(line.split() for line in subprocess.check_output(
            ['objdump', '-h', binary], text=True).splitlines()
            if line.split()[1:2] == ['.text'])
        text_base = int(section[3], 16)
        subprocess.run(['objcopy', '--dump-section', f'.text={path}/text.bin', binary],
                       check=True, timeout=10)
        text = (path/'text.bin').read_bytes()
        start, entry = symbols['outer_jit_case'], symbols['outer_jit_entry']
        raw = text[start-text_base:start-text_base+sizes['outer_jit_case']]
        names = {'kd_owned_mutex_outer_unlock_v1',
                 'kd_owned_mutex_outer_contended_clobber_v1',
                 'kd_owned_mutex_direct_unlock_clobber_v1'}
        selected = {name: symbols[name] for name in names}
        selected.update(kd_owned_mutex_lock_v1=0x70000000,
                        kd_owned_mutex_unlock_v1=0x70000080,
                        kd_owned_mutex_direct_lock_clobber_v1=0x70000100,
                        kd_owned_mutex_direct_contended_clobber_v1=0x70000200)
        assembly, log, status = render('', regions=[(raw, start, [entry])], entry=entry,
                                       kernel_symbols=selected, abi=2,
                                       lock_kind='mutex-owned', body_witness=True,
                                       return_status=True)
        assert status == 0, log
        assert b'clobber_complete' in assembly
        print(subprocess.check_output(['objdump', '-d', '--disassemble=outer_jit_case',
                                       binary], text=True))
        (path/'asm/jit.S').write_bytes(assembly)
        (path/'wrapper.S').write_text((ROOT/'include/wrapper.S').read_text()+
                                     '\n.globl main\n.section .note.GNU-stack,"",@progbits\n')
        subprocess.run(['cc', '-c', '-DKD_GENERATED_ENTRY_ABI=2', '-Dmain=main_wrapper',
                        '-I'+directory, '-I'+str(path/'asm'), '-I'+str(ROOT/'include'),
                        str(path/'wrapper.S'), '-o', str(path/'wrapper.o')],
                       check=True, timeout=30)
        generated = path/'generated'
        subprocess.run([*link, str(path/'wrapper.o'), '-o', str(generated)],
                       check=True, timeout=30)
        linked = {words[-1]: int(words[0], 16) for line in subprocess.check_output(
            ['nm', '--defined-only', generated], text=True).splitlines()
            if len(words := line.split()) == 3}
        for name in names | {'outer_jit_entry', 'test_lock'}:
            assert linked[name] == symbols[name], name
        result = subprocess.run([generated], capture_output=True, text=True,
                                check=True, timeout=10)
        assert 'PASS actual compiled/JIT outer entry:' in result.stdout
        print(result.stdout, end='')


if __name__ == '__main__':
    main()
