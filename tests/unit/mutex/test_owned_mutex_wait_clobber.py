"""Guest-only actual owned producer and executor stack-switch assembly."""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from source_text import ROOT
from test_spin_shadow import definition
from test_mutex_wait_clobber import FIXTURE


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
    fixture = FIXTURE.replace('kd_mutex_', 'kd_owned_mutex_')
    fixture = fixture.replace('KD_MUTEX_', 'KD_OWNED_MUTEX_')
    fixture = fixture.replace('struct kd_owned_mutex_legacy_gate', 'struct kd_mutex')
    fixture = fixture.replace('kd_owned_mutex_release_node', 'kd_owned_mutex_unreserve')
    fixture = fixture.replace('kd_owned_mutex_task_put', 'kd_mutex_task_put')
    fixture = fixture.replace('kd_owned_mutex_lock_slowpath', 'kd_owned_mutex_wait_on_stack')
    fixture = fixture.replace('static struct { struct kd_owned_mutex_node *resume_node; } kd_owned_mutex_shadows;\n', '')
    fixture = fixture.replace('static unsigned long kd_owned_mutex_jit_resume_count;\n', '')
    fixture = fixture.replace('    assert(kd_owned_mutex_jit_resume_count==32);\n', '')
    fixture = fixture.replace('n->completed=1;', 'n->outcome=KD_OWNED_MUTEX_COMPLETE;')
    fixture = fixture.replace('node.native_resume=false; node.completed=0;',
                              'node.outcome=KD_OWNED_MUTEX_QUEUED;')
    fixture = fixture.replace('#include "clobber.inc"',
                              'void kd_owned_mutex_resume_cabi(const struct kd_owned_mutex_cabi_state *p) '
                              '{ (void)p; abort(); }\n#include "clobber.inc"')
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
