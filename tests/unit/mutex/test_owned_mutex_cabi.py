"""Guest-only ordinary-C owned caller, late assembly capture and actual JIT.

The production assembly and C unlock fallback use deterministic SELF/promotion
and ACK dependencies. Scheduler/ACK concurrency remains a kernel live check.
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path
from test_jit_diagnostics import ROOT, render
from test_spin_shadow import definition

RESTORE = r'''
.text
.globl check_cabi_restore
.type check_cabi_restore,@function
check_cabi_restore:
 push %rbp
 push %rbx
 push %r12
 push %r13
 push %r14
 push %r15
 sub $8,%rsp
 lea restore_record(%rip),%rdi
 lea 1f(%rip),%rax
 mov %rax,0(%rdi)
 mov %rsp,8(%rdi)
 movq $0x81,16(%rdi)
 movq $0x82,24(%rdi)
 movq $0x83,32(%rdi)
 movq $0x84,40(%rdi)
 movq $0x85,48(%rdi)
 movq $0x86,56(%rdi)
 call kd_owned_mutex_resume_cabi
 ud2
1:
 cmp $0x81,%rbp
 jne 2f
 cmp $0x82,%r15
 jne 2f
 cmp $0x83,%r14
 jne 2f
 cmp $0x84,%r13
 jne 2f
 cmp $0x85,%r12
 jne 2f
 cmp $0x86,%rbx
 jne 2f
 cmp restore_record+8(%rip),%rsp
 jne 2f
 add $8,%rsp
 pop %r15
 pop %r14
 pop %r13
 pop %r12
 pop %rbx
 pop %rbp
 ret
2: ud2
.size check_cabi_restore,.-check_cabi_restore
.globl check_cabi_unlock
.type check_cabi_unlock,@function
check_cabi_unlock:
 push %rbp
 push %rbx
 push %r12
 push %r13
 push %r14
 push %r15
 sub $8,%rsp
 mov %rsp,(%rsp)
 mov $0x91,%rbp
 mov $0x92,%rbx
 mov $0x93,%r12
 mov $0x94,%r13
 mov $0x95,%r14
 mov $0x96,%r15
 call kd_owned_mutex_outer_unlock_cabi_v2
 cmp (%rsp),%rsp
 jne 2f
 cmp $0x91,%rbp
 jne 2f
 cmp $0x92,%rbx
 jne 2f
 cmp $0x93,%r12
 jne 2f
 cmp $0x94,%r13
 jne 2f
 cmp $0x95,%r14
 jne 2f
 cmp $0x96,%r15
 jne 2f
 add $8,%rsp
 pop %r15
 pop %r14
 pop %r13
 pop %r12
 pop %rbx
 pop %rbp
 ret
2: ud2
.size check_cabi_unlock,.-check_cabi_unlock
.bss
.balign 16
restore_record: .zero 64
.section .note.GNU-stack,"",@progbits
'''


def run(mutation=None):
    header = re.sub(r'^#include .*$', '', (ROOT/'include/kd_owned_mutex_direct.h').read_text(), flags=re.M)
    source = (ROOT/'kernel_module/owned_mutex/entry.S').read_text()
    wrapper = (ROOT/'include/wrapper.S').read_text()
    delegation = (ROOT/'kernel_module/owned_mutex/delegation.c').read_text()
    stub = definition(delegation,
                      'static bool kd_owned_mutex_cabi_stub_valid(unsigned long ip)')
    unlock = definition(delegation,
                        'void kd_owned_mutex_outer_cabi_unlock_slow(struct kd_mutex *lock, unsigned long owner)')
    if mutation:
        target, old, new = mutation
        original = {'entry': source, 'stub': stub, 'unlock': unlock, 'wrapper': wrapper}[target]
        assert original.count(old) == 1, old
        if target == 'entry': source = original.replace(old, new, 1)
        elif target == 'stub': stub = original.replace(old, new, 1)
        elif target == 'unlock': unlock = original.replace(old, new, 1)
        else: wrapper = original.replace(old, new, 1)
    with tempfile.TemporaryDirectory(prefix='kd-owned-cabi-') as directory:
        p=Path(directory)
        (p/'linux').mkdir();(p/'asm').mkdir()
        (p/'linux/linkage.h').write_text('#define SYM_FUNC_START(x) .globl x; .type x,@function; x:\n#define SYM_FUNC_END(x) .size x,.-x\n')
        (p/'linux/objtool.h').write_text('#define UNWIND_HINT(...) ""\n')
        (p/'asm/asm.h').write_text('/* fixture supplies constraint */\n')
        (p/'asm/nospec-branch.h').write_text('#ifdef __ASSEMBLER__\n#define RET ret\n#else\n#define CALL_NOSPEC "call *%[thunk_target]\\n"\n#endif\n')
        (p/'asm/percpu.h').write_text('#define PER_CPU_VAR(x) x(%rip)\n')
        (p/'asm/unwind_hints.h').write_text(
            '#define UNWIND_HINT_FUNC\n#define UNWIND_HINT_SAVE\n#define UNWIND_HINT_RESTORE\n'
            '.macro UNWIND_HINT sp_reg=0 sp_offset=0 type=0 end=0\n.endm\n')
        (p/'outer_api.h').write_text(header)
        (p/'cabi_stub.inc').write_text(stub)
        (p/'cabi_unlock.inc').write_text(unlock)
        fixture=(ROOT/'tests/unit/mutex/owned_mutex_cabi_fixture.c').read_text().replace('#define __always_inline', '#undef __always_inline\n#define __always_inline')
        (p/'fixture.c').write_text(fixture)
        (p/'entry.S').write_text(source+'\n.section .note.GNU-stack,"",@progbits\n')
        (p/'restore.S').write_text(RESTORE)
        # Match the kernel caller contract: a host libc FS canary is neither
        # a captured input nor an admissible delegated memory dependency.
        flags=['-O2','-std=gnu11','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer',
               '-fno-optimize-sibling-calls','-fno-reorder-blocks-and-partition',
               '-fno-toplevel-reorder','-mno-red-zone','-mpreferred-stack-boundary=4',
               '-fno-stack-protector','-fno-pie','-I'+directory,'-I'+str(ROOT/'include')]
        for filename in ('fixture.c','entry.S','restore.S'):
            subprocess.run(['cc',*flags,'-c',str(p/filename),'-o',str(p/(filename+'.o'))],check=True,timeout=30)
        link=['cc','-no-pie','-Wl,--section-start=.text=0x1000000',
              '-Wl,--section-start=.owned_lock=0x60000000',
              '-Wl,--section-start=.owned_state=0x61000000',
              *(str(p/(n+'.o')) for n in ('fixture.c','entry.S','restore.S'))]
        binary=p/'fixture'
        subprocess.run([*link,'-o',str(binary)],check=True,timeout=30)
        result=subprocess.run([binary],capture_output=True,text=True,timeout=10)
        if mutation and result.returncode: return
        if result.returncode:
            print(result.stdout,flush=True);print(result.stderr,flush=True)
        result.check_returncode()
        symbols,sizes={},{}
        for line in subprocess.check_output(['nm','-S','--defined-only',binary],text=True).splitlines():
            words=line.split()
            if len(words) in (3,4):
                symbols[words[-1]]=int(words[0],16)
                if len(words)==4:sizes[words[-1]]=int(words[1],16)
        caller=subprocess.check_output(['objdump','-dr','--disassemble=cabi_tiny',binary],text=True)
        assert not re.search(r'\b(?:push|pop)\w*\s+%(?:rbx|r1[2-5])\b',caller),caller
        unlock_assembly=subprocess.check_output(
            ['objdump','-d','--disassemble=kd_owned_mutex_outer_unlock_cabi_v2',binary],text=True)
        assert not re.search(r'\b(?:push|pop|call)\w*\s|%(?:rbp|rbx|r1[2-5])\b',unlock_assembly),unlock_assembly
        section=next(line.split() for line in subprocess.check_output(['objdump','-h',binary],text=True).splitlines()
                     if line.split()[1:2]==['.text'])
        base=int(section[3],16)
        subprocess.run(['objcopy','--dump-section',f'.text={p}/text.bin',binary],check=True,timeout=10)
        text=(p/'text.bin').read_bytes();start=symbols['cabi_case'];entry=symbols['cabi_entry']-9
        raw=text[start-base:start-base+sizes['cabi_case']]
        assert text[entry-base:entry-base+5]==bytes.fromhex('4885c00f85')
        selected={n:symbols[n] for n in ('kd_owned_mutex_outer_lock_cabi_v2','kd_owned_mutex_outer_unlock_cabi_v2')}
        for i,n in enumerate(('kd_owned_mutex_lock_v1','kd_owned_mutex_unlock_v1','kd_owned_mutex_outer_unlock_v1',
                             'kd_owned_mutex_direct_lock_clobber_v1','kd_owned_mutex_direct_contended_clobber_v1',
                             'kd_owned_mutex_outer_contended_clobber_v1','kd_owned_mutex_outer_prepared_clobber_v1',
                             'kd_owned_mutex_outer_preflight_v1','kd_owned_mutex_direct_unlock_clobber_v1')):
            selected[n]=0x70000000+i*0x100
        assembly,log,status=render('',regions=[(raw,start,[entry])],entry=entry,kernel_symbols=selected,
                                   abi=4,lock_kind='mutex-owned',body_witness=True,return_status=True)
        case_disassembly=subprocess.check_output(
            ['objdump','-dr','--disassemble=cabi_case',binary],text=True)

        def dump_codegen():
            # Temporary build directories are removed on failure. Preserve
            # the exact source caller and emitted JIT in the archived log.
            print('ABI4 caller disassembly:\n'+case_disassembly,flush=True)
            print('ABI4 tiny caller disassembly:\n'+caller,flush=True)
            print('ABI4 translation diagnostics:\n'+log,flush=True)
            print('ABI4 generated assembly:\n'+assembly.decode(),flush=True)

        if status != 0 or b'callee_complete' not in assembly:
            dump_codegen()
        assert status==0,log
        assert b'callee_complete' in assembly
        (p/'jit.S').write_bytes(assembly)
        (p/'wrapper.S').write_text(wrapper+'\n.globl main\n.section .note.GNU-stack,"",@progbits\n')
        subprocess.run(['cc','-c','-DKD_GENERATED_ENTRY_ABI=4','-Dmain=main_wrapper',
                        '-I'+directory,'-I'+str(ROOT/'include'),str(p/'wrapper.S'),'-o',str(p/'wrapper.o')],check=True,timeout=30)
        generated=p/'generated'
        subprocess.run([*link,str(p/'wrapper.o'),'-o',str(generated)],check=True,timeout=30)
        linked={w[-1]:int(w[0],16) for line in subprocess.check_output(['nm','--defined-only',generated],text=True).splitlines()
                if len(w:=line.split())==3}
        assert 'callee_complete' in linked
        for n in ('cabi_case','cabi_entry','test_lock','continuation_hits','bodies',
                  'cookie_override','expected_caller_sp','expected_caller_bp',
                  'cookie_address',*selected.keys()):
            if n in symbols:assert linked[n]==symbols[n],n
        # Matching entry addresses alone is insufficient: relinking must not
        # change source bytes (including displacements to referenced data).
        subprocess.run(['objcopy','--dump-section',f'.text={p}/generated-text.bin',generated],
                       check=True,timeout=10)
        linked_raw=(p/'generated-text.bin').read_bytes()[start-base:start-base+sizes['cabi_case']]
        assert linked_raw==raw,'relink changed the translated caller bytes'
        result=subprocess.run([generated],capture_output=True,text=True,timeout=10)
        if mutation:
            assert result.returncode,'mutation escaped ABI4 register/continuation oracle'
        else:
            if result.returncode:
                dump_codegen()
                print(result.stdout,flush=True)
                print(result.stderr,flush=True)
            result.check_returncode();print(result.stdout,end='');print(caller);print(unlock_assembly)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mutations',action='store_true')
    args=parser.parse_args();run()
    if args.mutations:
        mutations={
          'fast-touches-admission':('entry','\tmovq %rdx, %rax\n\tRET',
                                   '\tincq PER_CPU_VAR(kd_hotlock_owned_mutex_entries)\n\tmovq %rdx, %rax\n\tRET'),
          'fast-clobbers-rbx':('entry','\tmovq %rdx, %rax\n\tRET','\tmovq $1, %rbx\n\tmovq %rdx, %rax\n\tRET'),
          'capture-wrong-sp':('entry','\tleaq 80(%rsp), %rax','\tleaq 72(%rsp), %rax'),
          'capture-helper-bp':('entry','\tmovq (%rbp), %rax\n\tmovq %rax, KD_CABI_BP(%rsp)',
                              '\tmovq %rbp, KD_CABI_BP(%rsp)'),
          'malformed-stub-accepted':('stub','bytes[0] != 0x48 ||','false ||'),
          'resume-wrong-callee':('entry','\tmovq KD_CABI_R12(%rdi), %r12','\tmovq KD_CABI_R13(%rdi), %r12'),
          'omit-callee-import':('wrapper','\tmov rbx, PT_RBX\n\txor eax, eax','\txor ebx, ebx\n\txor eax, eax'),
          'wrong-borrowed-cookie':('wrapper','\tmov rbx, PT_RBX\n\txor eax, eax','\tmov rbx, PT_RBX\n\tmov eax, 1'),
          'omit-updated-rbx':('wrapper','callee_complete:\n\tmov PT_REG, Stack_PT_REG\n\tmov PT_RBX, rbx','callee_complete:\n\tmov PT_REG, Stack_PT_REG'),
          'unlock-skips-cookie-check':('entry','\tcmpq %rax, %rsi\n\tjne .Lowned_cabi_unlock_slow',
                                      '\tcmpq %rax, %rsi'),
          'unlock-zero-skips-ack':('entry','\ttestq %rsi, %rsi\n\tjz .Lowned_cabi_unlock_slow',
                                   '\ttestq %rsi, %rsi\n\tjnz 1f\n\tRET\n1:'),
          'unlock-overwrites-flags':('entry','\txorl %edx, %edx\n\tlock cmpxchgq %rdx, (%rdi)',
                                     '\tmovq $0, (%rdi)\n\txorl %eax, %eax'),
          'unlock-clobbers-r12':('entry','\tjne .Lowned_cabi_unlock_slow\n\tRET',
                                 '\tjne .Lowned_cabi_unlock_slow\n\tmovq $1, %r12\n\tRET'),
          'unlock-slow-skips-cookie-check':('unlock','BUG_ON(owner != (unsigned long)current);',
                                             '(void)owner;'),
        }
        for name,change in mutations.items():
            run(change);print('ABI4 mutation detected:',name)


if __name__=='__main__':main()
