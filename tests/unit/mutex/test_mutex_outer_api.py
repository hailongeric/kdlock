"""Guest-only actual outer header, compiler ABI and compiled-entry admission.

This does not model kernel owner/ACK concurrency. It executes real caller
constraints and translates the compiled hot continuation without relaxing the
production admission rules. The live benchmark supplies real returned bodies.
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path
from test_jit_diagnostics import ROOT, render


def check_variant(general_unlock, header_root):
    source = (header_root/'include/kd_mutex_direct.h').read_text()
    header = re.sub(r'^#include .*$', '', source, flags=re.M)
    gate_state = next(line for line in (header_root/'include/kd_mutex.h').read_text().splitlines()
                      if line.startswith('#define KD_MUTEX_GATE_COMBINER '))
    header = gate_state + '\n' + header
    with tempfile.TemporaryDirectory(prefix='kd-mutex-outer-') as directory:
        path = Path(directory)
        (path/'outer_api.h').write_text(header)
        (path/'asm').mkdir(); (path/'linux').mkdir()
        (path/'linux/objtool.h').write_text('#define UNWIND_HINT(...) ""\n')
        (path/'asm/asm.h').write_text('/* ASM_CALL_CONSTRAINT comes from fixture. */\n')
        (path/'asm/nospec-branch.h').write_text('#define CALL_NOSPEC "call *%[thunk_target]\\n"\n')
        binary = path/'fixture'
        flags=['-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
               f'-DKD_TEST_GENERAL_UNLOCK={int(general_unlock)}',
               '-fno-omit-frame-pointer', '-fno-optimize-sibling-calls',
               '-fno-reorder-blocks-and-partition', '-fno-toplevel-reorder',
               '-mno-red-zone', '-mpreferred-stack-boundary=4', '-fno-pie',
               '-I'+directory, '-I'+str(ROOT/'include')]
        subprocess.run(['cc', *flags, '-c',
                        str(ROOT/'tests/unit/mutex/mutex_outer_api_fixture.c'),
                        '-o', str(path/'fixture.o')], check=True, timeout=30)
        # Resolving the weak wrapper on the second link can shrink the PLT.
        # Anchor text as well as lock data so source identities remain exact;
        # retain the per-symbol identity assertions below.
        link=['cc', '-no-pie', '-Wl,--section-start=.text=0x1000000',
              '-Wl,--section-start=.outer_lock=0x60000000', str(path/'fixture.o')]
        subprocess.run([*link,'-o',str(binary)],check=True,timeout=30)
        subprocess.run([binary], check=True, timeout=10)
        symbols = {}
        sizes = {}
        for line in subprocess.check_output(['nm','-S','--defined-only',binary],text=True).splitlines():
            words=line.split()
            if len(words) not in (3,4):
                continue
            symbols[words[-1]]=int(words[0],16)
            if len(words)==4:
                sizes[words[-1]]=int(words[1],16)
        section = next(line.split() for line in subprocess.check_output(
            ['objdump','-h',binary],text=True).splitlines() if line.split()[1:2]==['.text'])
        text_base=int(section[3],16)
        subprocess.run(['objcopy','--dump-section',f'.text={path}/text.bin',binary],
                       check=True,timeout=10)
        text=(path/'text.bin').read_bytes()
        start=symbols['outer_jit_case']; entry=symbols['outer_jit_entry']
        raw=text[start-text_base:start-text_base+sizes['outer_jit_case']]
        selected={name:address for name,address in symbols.items()
                  if name in {'kd_mutex_local_unlock','kd_mutex_outer_contended_clobber_v1',
                              'kd_mutex_direct_unlock_clobber_v1'}}
        # ABI2's compatibility lock endpoint remains exported by the provider.
        selected['kd_mutex_direct_lock_clobber_v1']=0x70000000
        assembly,log,status=render('',regions=[(raw,start,[entry])],entry=entry,
                                  kernel_symbols=selected,abi=2,lock_kind='mutex',
                                  body_witness=True,return_status=True)
        assert status==0, log
        assert b'clobber_complete' in assembly, assembly
        # Preserve the actual compiler layout for review, including any spills
        # that remain despite native calls being bypassed. No timing claim here.
        print(subprocess.check_output(['objdump','-d','--disassemble=outer_jit_case',binary],text=True))
        (path/'asm/jit.S').write_bytes(assembly)
        (path/'wrapper.S').write_text((ROOT/'include/wrapper.S').read_text()+
                                     '\n.globl main\n.section .note.GNU-stack,"",@progbits\n')
        subprocess.run(['cc','-c','-DKD_GENERATED_ENTRY_ABI=2','-Dmain=main_wrapper',
                        '-I'+directory,'-I'+str(path/'asm'),'-I'+str(ROOT/'include'),
                        str(path/'wrapper.S'),'-o',str(path/'wrapper.o')],
                       check=True,timeout=30)
        second=path/'generated'
        subprocess.run([*link,str(path/'wrapper.o'),'-o',str(second)],
                       check=True,timeout=30)
        linked_symbols={words[-1]:int(words[0],16) for line in
                        subprocess.check_output(['nm','--defined-only',second],text=True).splitlines()
                        if len(words:=line.split())==3}
        # Same compiled object and fixed lock section: all source identities
        # embedded in the generated image must survive relinking unchanged.
        for name in ('outer_jit_entry','kd_mutex_direct_unlock_clobber_v1',
                     'kd_mutex_outer_contended_clobber_v1','kd_mutex_local_unlock','test_lock'):
            assert linked_symbols[name]==symbols[name], (name,symbols[name],linked_symbols[name])
        assert any(line.split()[1:] == ['T', 'main_wrapper'] for line in
                   subprocess.check_output(['nm','--defined-only',second],text=True).splitlines())
        result=subprocess.run([second],capture_output=True,text=True,check=True,timeout=10)
        assert 'PASS actual compiled/JIT outer entry:' in result.stdout, result.stdout
        print(result.stdout,end='')
        print('PASS actual compiled outer continuation: strict ABI2 admission and generated execution')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header-root', type=Path, default=ROOT,
                        help='explicit frozen caller header source; fixture/translator stay recorded')
    args = parser.parse_args()
    for general in (False, True):
        print('Checking OUTER acquisition with ' + ('general' if general else 'OUTER') + ' unlock', flush=True)
        check_variant(general, args.header_root.resolve(strict=True))


if __name__ == '__main__':
    main()
