"""Run the production shadow-stack switch after destroying abandoned C frames.

This isolates physical restoration, not kernel scheduling/owner ACK. The real
waiter and resume assembly is compiled with frame pointers and no red zone.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT, without_includes
from test_spin_shadow import definition

FIXTURE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef struct { unsigned long opaque[3]; } wait_queue_head_t;
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct { int counter; } atomic_t;
#define noinline __attribute__((noinline))
#define notrace
#define __always_inline inline __attribute__((always_inline))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define BUG_ON(x) assert(!(x))
#define this_cpu_ptr(x) (x)
#define this_cpu_inc(x) (++(x))
#define atomic64_inc(x) (++*(x))
#define UNWIND_HINT(a,b,c,d) ""
#define ASM_CALL_CONSTRAINT "+r"(current_stack_pointer)
register unsigned long current_stack_pointer asm("rsp");
#include "exe_info.h"
#include "types.h"
static struct { struct kd_mutex_node *resume_node; } kd_mutex_shadows;
static unsigned long kd_mutex_jit_resume_count;
static void *current;
static int mode, entered, after_bridge, released, task_put;
static struct kd_mutex_node node;
static unsigned char shadow[KD_MUTEX_SHADOW_STACK_SIZE] __attribute__((aligned(16)));
static void preempt_enable(void) {}
static void migrate_enable(void) {}
static void kd_mutex_task_put(void *p) { assert(p==current); task_put++; }
static void kd_mutex_release_node(struct kd_mutex_node *n) {
    assert(n==&node); released++; memset(n, 0xaf, sizeof(*n));
}
static void jump_to_saved_regs(struct kd_regs *p) { (void)p; abort(); }
static void jump_to_saved_regs_in_cs(struct kd_regs *p) { (void)p; abort(); }
static __attribute__((__noinline__,noipa)) int
kd_mutex_lock_slowpath(struct kd_mutex *lock, struct kd_mutex_node *n) {
    unsigned long physical;
    asm volatile("mov %%rsp,%0":"=r"(physical));
    assert(lock==(void *)0x1230 && n==&node);
    assert(physical>(unsigned long)shadow && physical<(unsigned long)(shadow+sizeof(shadow)));
    entered++;
    if (mode==2) return 2;
    n->packet_state=KD_PACKET_COMPLETE;
    n->completed=1;
    /* Remote JIT may use the lent stack down through all hook frames. */
    for (unsigned long *p=(void *)n->rsp; p<(unsigned long *)n->regs.sp; p++)
        *p=0xdeadbeef;
    return 3;
}
#include "clobber.inc"
static __attribute__((__noinline__,noipa,used)) void
bridge(struct kd_mutex *lock, unsigned long sp, unsigned long ip, unsigned long bp) {
    memset(&node, 0xa5, sizeof(node));
    node.entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
    node.packet_state=KD_PACKET_MINIMAL;
    node.native_resume=false; node.completed=0;
    node.regs.sp=sp; node.regs.ip=ip; node.regs.bp=bp;
    node.shadow_stack_ptr=(unsigned long)(shadow+sizeof(shadow));
    int result=kd_mutex_clobber_wait(lock,&node);
    assert(result==2 && mode==2);
    after_bridge++;
}
static unsigned long input[16];
static __attribute__((__noinline__,noipa)) unsigned long run(void) {
    unsigned long a=input[0],b=input[1],c=input[2],d=input[3];
    unsigned long e=input[4],f=input[5],g=input[6],h=input[7];
    unsigned long slots[8]; memcpy(slots,input+8,sizeof(slots));
    void *lock=(void *)0x1230; unsigned long sp,ip,bp;
    asm volatile("mov %%rsp,%%rsi\nlea 1f(%%rip),%%rdx\nmov %%rbp,%%rcx\ncall bridge\n1:"
       : "+D"(lock),"=S"(sp),"=d"(ip),"=c"(bp),ASM_CALL_CONSTRAINT
       : : "rax","rbx","r8","r9","r10","r11","r12","r13","r14","r15","cc","memory");
    unsigned long total=a+b+c+d+e+f+g+h;
    for (int i=0;i<8;i++) total+=slots[i];
    return total;
}
int main(void) {
    for (int round=0;round<32;round++) {
        unsigned long expected=0;
        for (int i=0;i<16;i++) expected+=(input[i]=round*111+i);
        mode=2; assert(run()==expected);
        mode=3; assert(run()==expected);
    }
    assert(entered==64 && after_bridge==32 && released==32 && task_put==32);
    assert(kd_mutex_jit_resume_count==32);
    puts("[PASS] production mutex shadow switch: 32 intact returns, 32 destroyed-frame minimal resumes");
}
'''

def main():
    kernel=Path(f'/lib/modules/{os.uname().release}/build')
    ptrace=(ROOT/'include/kd_regs.h').read_text()
    types=definition(ptrace,'struct kd_regs {').rstrip()+';\n'
    types+=without_includes((ROOT/'include/kd_mutex.h').read_text())
    with tempfile.TemporaryDirectory(prefix='kd-mutex-wait-') as tmp:
        path=Path(tmp)
        (path/'types.h').write_text(types)
        (path/'clobber.inc').write_text((ROOT/'kernel_module/mutex/clobber.inc').read_text())
        (path/'fixture.c').write_text(FIXTURE.replace('#define __always_inline', '#undef __always_inline\n#define __always_inline'))
        cc=shlex.split(os.environ.get('CC','gcc'))
        subprocess.run(cc+['-O2','-fno-omit-frame-pointer','-mno-red-zone','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(path/'fixture.c'),'-o',str(path/'fixture')],check=True,timeout=30)
        subprocess.run([str(path/'fixture')],check=True,timeout=10)

if __name__=='__main__': main()
