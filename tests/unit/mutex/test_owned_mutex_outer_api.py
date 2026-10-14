"""Guest-only compiled owned outer ABI, including its actual generated JIT."""
import re
import subprocess
import tempfile
from pathlib import Path
from test_jit_diagnostics import ROOT, render


def check_mode(preflight):
    header = re.sub(r'^#include .*$', '',
                    (ROOT/'include/kd_owned_mutex_direct.h').read_text(), flags=re.M)
    header = '#define KD_OWNED_MUTEX_PREFLIGHT ' + str(int(preflight)) + '\n' + header
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
    if preflight:
        # The ordinary call owns the once-only observation, including capture
        # attempts. Mode 4 acquires through C without ever entering capture asm.
        fixture = fixture.replace('#include "outer_api.h"', r'''unsigned long preflight_calls;
    static bool preflight_self;
    __attribute__((noinline,noipa)) bool
    kd_owned_mutex_outer_preflight_v1(struct kd_mutex *lock)
    {
     preflight_calls++; entries++;
     if (!preflight_self) return false;
     lock->owner=(unsigned long)current;
     return true;
    }
    #include "outer_api.h"
    ''')
        fixture = fixture.replace('incq routed_locks(%rip)\\n incq entries(%rip)\\n',
                                  'incq routed_locks(%rip)\\n')
        fixture = fixture.replace('(mode==1 || mode==3) ? 0x9000UL',
                                  '(mode==1 || mode==3 || mode==4) ? 0x9000UL')
        fixture = fixture.replace(' contended_native_return=mode==3',
                                  ' preflight_self=mode==4;\n contended_native_return=mode==3')
        fixture = fixture.replace('for(int mode=0;mode<4;mode++)',
                                  'for(int mode=0;mode<5;mode++)')
        fixture = fixture.replace('unsigned long before=entries, locks=routed_locks, unlocks=routed_unlocks;',
                                  'unsigned long before=entries, locks=routed_locks, unlocks=routed_unlocks;\n'
                                  '  unsigned long gates=preflight_calls;')
        fixture = fixture.replace('assert(entries==before+1);',
                                  'assert(entries==before+1);\n'
                                  '  assert(preflight_calls==gates+(mode==1 || mode==3 || mode==4));')
        fixture = fixture.replace('assert(native_unlocks==3);', 'assert(native_unlocks==4);')
        fixture = fixture.replace(' contended_native_return=0;\n',
                                  ' preflight_self=false;\n contended_native_return=0;\n')
        fixture = fixture.replace('kd_owned_mutex_outer_contended_clobber_v1',
                                  'kd_owned_mutex_outer_prepared_clobber_v1')
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
        endpoint = ('kd_owned_mutex_outer_prepared_clobber_v1' if preflight else
                    'kd_owned_mutex_outer_contended_clobber_v1')
        names = {'kd_owned_mutex_outer_unlock_v1', endpoint,
                 'kd_owned_mutex_direct_unlock_clobber_v1'}
        if preflight:
            names.add('kd_owned_mutex_outer_preflight_v1')
        selected = {name: symbols[name] for name in names}
        # Unused provider endpoints remain known to admission, but the compiled
        # caller must contain exactly its selected capture route and no gate
        # call at all when preflight is disabled.
        for i, name in enumerate(('kd_owned_mutex_outer_contended_clobber_v1',
                                  'kd_owned_mutex_outer_prepared_clobber_v1',
                                  'kd_owned_mutex_outer_preflight_v1')):
            selected.setdefault(name, 0x71000000 + i*0x100)
        caller = subprocess.check_output(['objdump', '-dr', '--disassemble=outer_jit_case',
                                          binary], text=True)
        assert endpoint in caller
        forbidden = ('kd_owned_mutex_outer_contended_clobber_v1' if preflight else
                     'kd_owned_mutex_outer_prepared_clobber_v1')
        assert forbidden not in caller
        assert ('kd_owned_mutex_outer_preflight_v1' in caller) == preflight
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
        # Default ABI2 images retain their original completion layout.
        assert 'callee_complete' not in linked
        for name in names | {'outer_jit_entry', 'test_lock'}:
            assert linked[name] == symbols[name], name
        result = subprocess.run([generated], capture_output=True, text=True,
                                check=True, timeout=10)
        assert 'PASS actual compiled/JIT outer entry:' in result.stdout
        print(('preflight' if preflight else 'capture-first') + ': ' + result.stdout, end='')


def main():
    for preflight in (False, True):
        check_mode(preflight)


if __name__ == '__main__':
    main()
