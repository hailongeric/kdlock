"""Execute the real resident runner and both wrapper ABIs in the recovery guest.

A tiny generated-body fixture exercises consecutive normal completions, a
mid-body hostcall/CALL miss and an unstarted refusal. It deliberately poisons
caller-saved registers: only final lock-ABI exits may omit writing those values.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

BODY = r'''
    cmp rax, 4
    je refuse
    mov Stack_JIT_WITNESS, 1
    inc QWORD PTR[rbx]
    mov rbx, 0x106
    mov R12, 0x105
    mov Stack_R12, 0x104
    mov Stack_R13, 0x103
    mov Stack_R14, 0x102
    mov Stack_R15, 0x101
    mov Stack_R11, 0x107
    mov rcx, 0x108
    mov rdx, 0x109
    mov rsi, 0x10a
    mov r8, 0x10b
    mov r9, 0x10c
    mov r10, 0x10d
    mov R14, 0x4000
    mov Stack_IJ, 1
    cmp rax, 1
    je exit
    mov R14, 0x5000
    cmp rax, 3
    je exit
    mov Stack_IJ, 5
    jmp exit
refuse:
    mov R14, 0x3000
    mov Stack_IJ, 6
    jmp exit
'''

FIXTURE = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
struct pt_regs { unsigned long w[21]; };
#define __KERNEL__
#include "kd_jit_batch.h"
extern void kd_spin_batch_enter(void *, struct kd_jit_batch_call *(*)(void *));
extern void main_wrapper(struct pt_regs *, unsigned long *);
static struct pt_regs packets[4];
static unsigned long bodies[4];
static struct kd_jit_batch_call call;
static int index_;
static struct kd_jit_batch_call *step(void *opaque)
{
    assert(opaque == packets);
    if (index_) {
        unsigned long *v = packets[index_ - 1].w;
        int kind = index_;
        assert(bodies[index_ - 1] == (kind != 4));
        assert(call.args[1] == (unsigned long)(kind != 4));
        if (kind == 4) {
            assert(call.args[0] == 6 && v[16] == 0x3000);
        } else {
            for (int j=0; j<6; j++) assert(v[j] == 0x101UL+j);
            assert(v[19] == 0x9000 && v[14] == 0x6000);
            if (kind == 1) {
                assert(v[6] == 0xdead && v[11] == 0xdead);
                assert(call.args[0] == 1 && v[16] == 0x4000);
            } else {
                assert(v[6] == 0x107 && v[11] == 0x108);
                assert(v[12] == 0x109 && v[13] == 0x10a);
                assert(v[9] == 0x10b && v[8] == 0x10c && v[7] == 0x10d);
                assert(v[16] == 0x5000);
                assert(call.args[0] == (kind == 2 ? 5UL : 1UL));
            }
        }
    }
    if (index_ == 4) return NULL;
    call.regs = &packets[index_];
    call.args[0] = 0x7000;
    call.args[1] = 0x8000;
    call.code = (char *)main_wrapper + KD_JIT_BATCH_OFFSET;
    call.lock = 0x6000;
    call.unlock = 0x4000;
    index_++;
    return &call;
}
int main(void)
{
    assert(offsetof(struct kd_jit_batch_call, lock) == 32);
    assert(offsetof(struct kd_jit_batch_call, unlock) == 40);
    assert(!memcmp((char *)main_wrapper + 9, "KDWB001", 7));
    for (int unified=0; unified<2; unified++) {
    index_=0;
    memset(bodies,0,sizeof(bodies));
    for (int i=0; i<4; i++) {
        for (int j=0;j<21;j++) packets[i].w[j]=0xdead;
        packets[i].w[5]=(unsigned long)&bodies[i];
        packets[i].w[10]=i+1;
        packets[i].w[14]=0x6000;
        packets[i].w[16]=0x3000;
        packets[i].w[19]=0x9000;
    }
    if (!unified) kd_spin_batch_enter(packets, step);
    else {
        struct kd_jit_batch_call *next;
        while ((next=step(packets))) kd_jit_legacy_batch_call(next);
    }
    assert(index_ == 4);
    }
    /* Normal C ABI still writes all GPRs, including a final unlock. */
    unsigned long args[2]={0x7000,0x8000};
    packets[0].w[5]=(unsigned long)&bodies[0];
    packets[0].w[10]=1;
    main_wrapper(&packets[0], args);
    assert(packets[0].w[6] == 0x107 && packets[0].w[11] == 0x108);
    assert(bodies[0] == 2 && args[1] == 1);
    puts("[PASS] legacy resident/unified C loop, reduced final ABI, full continuation/refusal ABI");
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="kdlock-wwjump-") as directory:
        path=Path(directory)
        (path/'linux').mkdir(); (path/'asm').mkdir()
        # Userspace has no objtool pass; the kernel build validates real hints.
        (path/'linux/objtool.h').write_text('#define UNWIND_HINT(...) ""\n')
        (path/'linux/linkage.h').write_text('#define SYM_FUNC_START(x) .globl x; .type x,@function; x:\n#define SYM_FUNC_END(x) .size x, .-x\n')
        (path/'asm/asm.h').write_text('register unsigned long current_stack_pointer asm("rsp");\n#define ASM_CALL_CONSTRAINT "+r"(current_stack_pointer)\n')
        (path/'asm/nospec-branch.h').write_text('#ifdef __ASSEMBLER__\n.macro CALL_NOSPEC reg\ncall *%\\reg\n.endm\n#define RET ret\n#else\n#define CALL_NOSPEC "call *%[thunk_target]\\n"\n#endif\n')
        (path/'jit.S').write_text(BODY)
        (path/'wrapper.S').write_text((ROOT/'include/wrapper.S').read_text()+'\n.globl main\n.section .note.GNU-stack,"",@progbits\n')
        (path/'fixture.c').write_text(FIXTURE)
        cc=shlex.split(os.environ.get('CC','cc'))
        for src,out,extra in [(path/'wrapper.S',path/'wrapper.o',['-Dmain=main_wrapper']),
                              (ROOT/'tests/unit/spin/legacy_batch.S',path/'runner.o',[])]:
            subprocess.run(cc+['-c','-I'+str(path),'-I'+str(ROOT/'include'),*extra,str(src),'-o',str(out)],check=True,timeout=30)
        subprocess.run(cc+['-O2','-fno-omit-frame-pointer','-Wall','-Wextra','-Werror','-mno-red-zone','-I'+str(path),'-I'+str(ROOT/'include'),str(path/'fixture.c'),str(path/'wrapper.o'),str(path/'runner.o'),'-o',str(path/'check')],check=True,timeout=30)
        subprocess.run([str(path/'check')],check=True,timeout=10)

if __name__ == '__main__':
    main()
