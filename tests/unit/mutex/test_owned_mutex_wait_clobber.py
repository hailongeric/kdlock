"""Guest-only actual owned producer and executor stack-switch assembly."""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from source_text import ROOT
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
static void *current;
static int mode, entered, after_bridge, released, task_put;
static struct kd_owned_mutex_node node;
static unsigned char shadow[KD_OWNED_MUTEX_SHADOW_STACK_SIZE] __attribute__((aligned(16)));
static void preempt_enable(void) {}
static void migrate_enable(void) {}
static void kd_mutex_task_put(void *p) { assert(p==current); task_put++; }
static void kd_owned_mutex_unreserve(struct kd_owned_mutex_node *n) {
    assert(n==&node); released++; memset(n, 0xaf, sizeof(*n));
}
static void jump_to_saved_regs(struct kd_regs *p) { (void)p; abort(); }
static void jump_to_saved_regs_in_cs(struct kd_regs *p) { (void)p; abort(); }
static __attribute__((__noinline__,noipa)) int
kd_owned_mutex_wait_on_stack(struct kd_mutex *lock, struct kd_owned_mutex_node *n) {
    unsigned long physical;
    asm volatile("mov %%rsp,%0":"=r"(physical));
    assert(lock==(void *)0x1230 && n==&node);
    assert(physical>(unsigned long)shadow && physical<(unsigned long)(shadow+sizeof(shadow)));
    entered++;
    if (mode==2) return 2;
    n->packet_state=KD_PACKET_COMPLETE;
    n->outcome=KD_OWNED_MUTEX_COMPLETE;
    /* Remote JIT may use the lent stack down through all hook frames. */
    for (unsigned long *p=(void *)n->rsp; p<(unsigned long *)n->regs.sp; p++)
        *p=0xdeadbeef;
    return 3;
}
void kd_owned_mutex_resume_cabi(const struct kd_owned_mutex_cabi_state *p) { (void)p; abort(); }
#include "clobber.inc"
static __attribute__((__noinline__,noipa,used)) void
bridge(struct kd_mutex *lock, unsigned long sp, unsigned long ip, unsigned long bp) {
    memset(&node, 0xa5, sizeof(node));
    node.entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
    node.packet_state=KD_PACKET_MINIMAL;
    node.outcome=KD_OWNED_MUTEX_QUEUED;
    node.regs.sp=sp; node.regs.ip=ip; node.regs.bp=bp;
    node.shadow_stack_ptr=(unsigned long)(shadow+sizeof(shadow));
    int result=kd_owned_mutex_clobber_wait(lock,&node);
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
    puts("[PASS] production owned mutex stack switch: 32 intact returns, 32 destroyed-frame minimal resumes");
}
'''


EXECUTOR = r'''
struct kd_owned_mutex_batch { unsigned long expected; };
static unsigned char executor_stack[8192] __attribute__((aligned(16)));
static int executor_calls;
__attribute__((noipa,__noinline__)) static void
kd_owned_mutex_run_batch(struct kd_owned_mutex_batch *batch) {
    unsigned long physical;
    asm volatile("mov %%rsp,%0":"=r"(physical));
    assert(physical>(unsigned long)executor_stack &&
           physical<(unsigned long)(executor_stack+sizeof(executor_stack)));
    assert(batch->expected==0x15161718);
    executor_calls++;
    /* The C ABI owns preserving R12, which holds the executor identity. */
    asm volatile("mov $1,%%rax\nmov $2,%%rdi\nmov $3,%%rsi\nmov $4,%%rdx\n"
                 "mov $5,%%rcx\nmov $6,%%r8\nmov $7,%%r9\nmov $8,%%r10\nmov $9,%%r11"
                 : : : "rax","rdi","rsi","rdx","rcx","r8","r9","r10","r11","memory");
}
#include "executor.inc"
static __attribute__((noipa,__noinline__)) void check_executor(void) {
    struct kd_owned_mutex_batch batch={.expected=0x15161718};
    struct kd_owned_mutex_executor executor={
        .stack_ptr=(unsigned long)(executor_stack+sizeof(executor_stack)),
    };
    unsigned long before,after, a=17,b=31,c=59,d=127;
    asm volatile("mov %%rsp,%0":"=r"(before));
    asm volatile("":"+r"(a),"+r"(b),"+r"(c),"+r"(d)::"memory");
    kd_owned_mutex_executor_call(&batch,&executor);
    asm volatile("":"+r"(a),"+r"(b),"+r"(c),"+r"(d)::"memory");
    asm volatile("mov %%rsp,%0":"=r"(after));
    assert(before==after && a+b+c+d==234);
    assert(batch.expected==0x15161718);
}
'''


def main():
    source = (ROOT/'kernel_module/owned_mutex/delegation.c').read_text()
    types = definition((ROOT/'include/kd_regs.h').read_text(), 'struct kd_regs {')+';\n'
    types += ('#include "kd_owned_mutex_cabi.h"\n#include "kd_image.h"\n'
              'typedef uint64_t u64;\n'
              'struct list_head { struct list_head *next,*prev; };\n'
              'struct task_struct; struct kd_mutex; struct rcuwait;\n'
              '#define __aligned(n) __attribute__((aligned(n)))\n'
              '#define KD_OWNED_MUTEX_SHADOW_STACK_SIZE 8192\n')
    types += definition((ROOT/'include/kd_owned_mutex_internal.h').read_text(),
                        'enum kd_owned_mutex_waiter_state {')+';\n'
    types += definition((ROOT/'include/kd_owned_mutex_internal.h').read_text(),
                        'struct kd_owned_mutex_waiter {')+';\n'
    types += definition(source, 'struct kd_owned_mutex_node {')+';\n'
    types += definition(source, 'struct kd_owned_mutex_executor {')+';\n'
    fixture = FIXTURE
    fixture = fixture.replace('int main(void) {', EXECUTOR+'\nint main(void) {\n'
                              '    for(int i=0;i<32;i++) check_executor();\n'
                              '    assert(executor_calls==32);')
    clobber = 'static __attribute__((noipa, used, noreturn)) noinline notrace void\n'
    clobber += definition(source, 'kd_owned_mutex_resume(struct kd_owned_mutex_node *node)')
    clobber += '\nstatic __always_inline int\n'
    clobber += definition(source,
        'kd_owned_mutex_clobber_wait(struct kd_mutex *lock, struct kd_owned_mutex_node *node)')
    executor = 'static __always_inline void\n'+definition(source,
        'kd_owned_mutex_executor_call(struct kd_owned_mutex_batch *batch,')
    with tempfile.TemporaryDirectory(prefix='kd-owned-stack-') as directory:
        path = Path(directory)
        (path/'types.h').write_text(types)
        (path/'clobber.inc').write_text(clobber)
        (path/'executor.inc').write_text(executor)
        (path/'fixture.c').write_text(fixture.replace('#define __always_inline',
                                                     '#undef __always_inline\n#define __always_inline'))
        cc = shlex.split(os.environ.get('CC', 'gcc'))
        subprocess.run(cc+['-O2', '-fno-omit-frame-pointer', '-mno-red-zone',
                           '-Wall', '-Wextra', '-Werror', '-I'+str(ROOT/'include'),
                           str(path/'fixture.c'), '-o', str(path/'fixture')],
                       check=True, timeout=30)
        subprocess.run([path/'fixture'], check=True, timeout=10)
        print('PASS production owned producer destroyed-frame resume and independent executor stack')


if __name__ == '__main__':
    main()
