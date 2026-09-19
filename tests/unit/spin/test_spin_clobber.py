"""Run the actual clobber wrapper and kernel caller constraints in the guest.

Poison every absent entry register, exercise explicit completion/refusal/full
exits, and force caller spills with real all-GPR destruction between live values.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
BODY = r'''
    mov rax, [R12]
    cmp rax, 3
    je refuse_minimal
    inc QWORD PTR[R12 + 8]
    mov Stack_JIT_WITNESS, 1
    mov rbx, 0x106
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
    mov rdi, 0x6000
    mov R14, 0x4000
    mov Stack_IJ, 1
    test rax, rax
    jne middle
    lea rsi, [R13 + 8]
    mov rdx, [R13]
    mov rcx, R12
    jmp exit
middle:
    mov R14, 0x5000
    cmp rax, 2
    je exit
    mov Stack_IJ, 5
    jmp exit
refuse_minimal:
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
#include "caller.h"
extern void main_wrapper(struct pt_regs *, unsigned long *);
extern void legacy_wrapper(struct pt_regs *, unsigned long *);
static struct pt_regs mixed_packets[4];
static unsigned long mixed_logic[4][2], mixed_stacks[4][32];
static unsigned int mixed_states[4], mixed_index, mixed_first, mixed_unified;
static struct kd_jit_batch_call mixed_call;
/* Exercise both lock-side calling shells with real alternating wrapper ABIs.
 * The queue/owner C protocol has its separate production-source fixture. */
static struct kd_jit_batch_call *mixed_step(void *opaque) {
    assert(opaque == mixed_packets);
    for (;;) {
        if (mixed_index) {
            unsigned int previous=mixed_index-1, abi=(previous+mixed_first)&1;
            unsigned long *v=mixed_packets[previous].w;
            assert(mixed_logic[previous][1]==1 && mixed_call.args[1]==1);
            assert(mixed_call.args[0]==(abi?7:1));
            assert(mixed_states[previous]==(abi?2:0));
            assert(v[16]==(abi?0x7000:0x4000));
            assert(v[19]==(unsigned long)&mixed_stacks[previous][16]+(abi?8:0));
        }
        if (mixed_index==4) return NULL;
        unsigned int index=mixed_index++, abi=(index+mixed_first)&1;
        mixed_call=(struct kd_jit_batch_call){
            .regs=&mixed_packets[index],.args={0x8000,0x9000},
            .code=abi?(char *)main_wrapper+32:(char *)legacy_wrapper+16,
            .lock=0x6000,.unlock=0x4000,.entry_abi=abi,
            .packet_state=&mixed_states[index],.complete=1,
        };
        if (!abi) {
            if (!mixed_unified) return &mixed_call;
            kd_jit_legacy_batch_call(&mixed_call);
        } else kd_jit_clobber_call_v1(&mixed_call);
    }
}
static void check_mixed_batches(void) {
    for (mixed_unified=0;mixed_unified<2;mixed_unified++)
    for (mixed_first=0;mixed_first<2;mixed_first++) {
        mixed_index=0;
        memset(mixed_logic,0,sizeof(mixed_logic));
        for(unsigned int i=0;i<4;i++) {
            memset(&mixed_packets[i],0xde,sizeof(mixed_packets[i]));
            mixed_packets[i].w[4]=(unsigned long)mixed_logic[i];
            mixed_packets[i].w[16]=0x3000;
            mixed_packets[i].w[19]=(unsigned long)&mixed_stacks[i][16];
            mixed_stacks[i][16]=0x7000;
            mixed_states[i]=(i+mixed_first)&1;
        }
        if (mixed_unified) assert(!mixed_step(mixed_packets));
        else if (!mixed_first) kd_spin_batch_enter(mixed_packets,mixed_step);
        else {
            struct kd_jit_batch_call *call;
            while ((call=mixed_step(mixed_packets)))
                ((void (*)(struct pt_regs *,unsigned long *))
                 ((char *)call->code-KD_JIT_BATCH_OFFSET))(call->regs,call->args);
        }
        assert(mixed_index==4);
    }
}
static unsigned long hook_count;
static volatile unsigned long inputs[16];
__attribute__((noinline,noipa)) static unsigned long helper(unsigned long x) { return x * 37 + 19; }
__attribute__((noinline,noipa)) static unsigned long stress(int real) {
    unsigned long a=inputs[0], b=inputs[1], c=inputs[2], d=inputs[3];
    unsigned long e=inputs[4], f=inputs[5], g=inputs[6], h=inputs[7];
    unsigned long i=inputs[8], j=inputs[9], k=inputs[10], l=inputs[11];
    unsigned long stack[4]={inputs[12],inputs[13],inputs[14],inputs[15]};
    for (unsigned int n=0;n<31;n++) {
        if(real) raw_spin_lock(&hook_count);
        a+=helper(stack[n%4]); b^=a; c+=b; d^=c; e+=d; f^=e;
        g+=f; h^=g; i+=h; j^=i; k+=j; l^=k;
        stack[n%4]+=l;
        if(real) raw_spin_unlock(&hook_count);
    }
    return a+b+c+d+e+f+g+h+i+j+k+l+stack[0]+stack[1]+stack[2]+stack[3];
}
int main(void) {
    check_mixed_batches();
    assert(offsetof(struct kd_jit_batch_call, packet_state)==80);
    assert(offsetof(struct kd_jit_batch_call, complete)==88);
    assert((unsigned char) *((char *)main_wrapper+45)==1);
    for(unsigned long seed=1;seed<=32;seed++) {
        for(unsigned long mode=0;mode<4;mode++) {
            struct pt_regs packet;
            unsigned long logical[2]={mode,0}, stack[32];
            unsigned int state=1;
            for(int i=0;i<21;i++) packet.w[i]=seed*0x1234567UL+i;
            packet.w[4]=(unsigned long)logical;
            packet.w[16]=0x3000;
            packet.w[19]=(unsigned long)&stack[16];
            stack[16]=0x7000;
            struct pt_regs before=packet;
            struct kd_jit_batch_call call={
                .regs=&packet,.args={0x8000,0x9000},
                .code=(char *)main_wrapper+32,.lock=0x6000,.unlock=0x4000,
                .entry_abi=1,.packet_state=&state,.complete=1,
            };
            kd_jit_clobber_call_v1(&call);
            assert(logical[1]==(mode!=3));
            assert(call.args[1]==(mode!=3));
            assert(packet.w[4]==before.w[4]);
            if(mode==0 || mode==3) {
                assert(call.args[0]==(mode==0?7:6));
                assert(state==(mode==0?2:1));
                assert(packet.w[16]==(mode==0?0x7000:0x3000));
                assert(packet.w[19]==before.w[19]+(mode==0?8:0));
                /* COMPLETE validates only three words, but executed JIT
                 * spills now share the preallocated packet. A refusal must
                 * still preserve every input byte because no body ran. */
                for(int i=0;i<21;i++) if(i!=4&&i!=16&&i!=19) {
                    unsigned long expected=before.w[i];
                    if(mode==0 && i<4) expected=0x101UL+i;
                    if(mode==0 && i==6) expected=0x107;
                    assert(packet.w[i]==expected);
                }
            } else {
                assert(state==0 && call.args[0]==(mode==1?5:1));
                assert(packet.w[16]==0x5000 && packet.w[19]==before.w[19]);
                for(int i=0;i<4;i++) assert(packet.w[i]==0x101UL+i);
                assert(packet.w[5]==0x106 && packet.w[6]==0x107);
                assert(packet.w[7]==0x10d && packet.w[8]==0x10c && packet.w[9]==0x10b);
                assert(packet.w[10]==mode && packet.w[11]==0x108 && packet.w[12]==0x109);
                assert(packet.w[13]==0x10a && packet.w[14]==0x6000);
            }
        }
        for(int i=0;i<16;i++) inputs[i]=seed*987+i;
        assert(stress(1)==stress(0));
    }
    assert(hook_count==32*31*2);
    puts("[PASS] clobber caller spills/metadata, minimal completion/refusal, full hostcall/native packets (128 poisoned entries)");
    puts("[PASS] mixed legacy/clobber handoffs in old shells and unified C loop (16 entries)");
}
'''


def main(entry_abi=1):
    with tempfile.TemporaryDirectory(prefix="kdlock-clobber-") as directory:
        path=Path(directory)
        (path/'asm').mkdir()
        (path/'linux').mkdir()
        # Userspace has no objtool pass; the kernel build validates real hints.
        (path/'linux/objtool.h').write_text('#define UNWIND_HINT(...) ""\n')
        (path/'linux/linkage.h').write_text('#define SYM_FUNC_START(x) .globl x; .type x,@function; x:\n#define SYM_FUNC_END(x) .size x, .-x\n')
        (path/'asm/asm.h').write_text('register unsigned long current_stack_pointer asm("rsp");\n#define ASM_CALL_CONSTRAINT "+r"(current_stack_pointer)\n')
        (path/'asm/nospec-branch.h').write_text('#ifdef __ASSEMBLER__\n.macro CALL_NOSPEC reg\ncall *%\\reg\n.endm\n#define RET ret\n#else\n#define CALL_NOSPEC "call *%[thunk_target]\\n"\n#endif\n')
        # Extract the reviewed experiment macro, rather than maintaining a second ABI.
        patch=(ROOT/f'kernel_experiments/{"mutex" if entry_abi == 2 else "spin"}_clobber/guest-kernel.patch').read_text()
        added='\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
        marker = '#define __kd_mutex_clobber_call_v1' if entry_abi == 2 else '#define __kd_spin_clobber_call_v1'
        macro=added[added.index(marker):added.index('#else',added.index(marker))] if entry_abi == 1 else added[added.index(marker):added.index('#endif',added.index(marker))]
        if entry_abi == 2:
            macro = macro.replace('struct mutex', 'raw_spinlock_t').replace('__kd_mutex_clobber_call_v1', '__kd_spin_clobber_call_v1').replace('kd_mutex_', 'kd_raw_spin_').replace('mutex_lock(', 'raw_spin_lock(').replace('mutex_unlock(', 'raw_spin_unlock(')
        (path/'caller.h').write_text('typedef unsigned long raw_spinlock_t;\n'+macro+'\n#define raw_spin_unlock(lock) __kd_spin_clobber_call_v1(kd_raw_spin_unlock_clobber_v1, lock)\n')
        (path/'jit.S').write_text(BODY)
        (path/'wrapper.S').write_text((ROOT/'include/wrapper.S').read_text()+'\n.globl main\n.section .note.GNU-stack,"",@progbits\n')
        fixture = FIXTURE
        if entry_abi == 2:
            fixture = fixture.replace('.entry_abi=abi,', '.entry_abi=abi?2:0,').replace('.entry_abi=1,', '.entry_abi=2,').replace('main_wrapper+45)==1', 'main_wrapper+45)==2')
        (path/'fixture.c').write_text(fixture)
        stubs='.text\n.globl kd_raw_spin_lock_clobber_v1, kd_raw_spin_unlock_clobber_v1\nkd_raw_spin_lock_clobber_v1:\nkd_raw_spin_unlock_clobber_v1:\n'
        stubs+='lea 8(%rsp), %rax\ncmp %rax,%rsi\njne 1f\ncmp (%rsp),%rdx\njne 1f\ncmp %rbp,%rcx\njne 1f\nincq (%rdi)\n'
        for reg in ('rax','rbx','rcx','rdx','rsi','rdi',*(f'r{i}' for i in range(8,16))):
            stubs+=f'mov $0xdead,%{reg}\n'
        stubs+='ret\n1: ud2\n.section .note.GNU-stack,"",@progbits\n'
        (path/'stubs.S').write_text(stubs)
        cc=shlex.split(os.environ.get('CC','gcc'))
        subprocess.run(cc+['-c',f'-DKD_GENERATED_ENTRY_ABI={entry_abi}','-Dmain=main_wrapper','-I'+str(path),'-I'+str(ROOT/'include'),str(path/'wrapper.S'),'-o',str(path/'wrapper.o')],check=True,timeout=30)
        subprocess.run(cc+['-c','-Dmain=legacy_wrapper','-I'+str(path),'-I'+str(ROOT/'include'),str(path/'wrapper.S'),'-o',str(path/'legacy.o')],check=True,timeout=30)
        subprocess.run(cc+['-c','-I'+str(path),'-I'+str(ROOT/'include'),str(ROOT/'tests/unit/spin/legacy_batch.S'),'-o',str(path/'runner.o')],check=True,timeout=30)
        subprocess.run(cc+['-O2','-fno-omit-frame-pointer','-mno-red-zone','-Wall','-Wextra','-Werror','-I'+str(path),'-I'+str(ROOT/'include'),str(path/'fixture.c'),str(path/'stubs.S'),str(path/'wrapper.o'),str(path/'legacy.o'),str(path/'runner.o'),'-o',str(path/'fixture')],check=True,timeout=30)
        subprocess.run([str(path/'fixture')],check=True,timeout=30)

if __name__=='__main__':
    main()
