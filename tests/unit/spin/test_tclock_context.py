"""Run the production C inline assembly with synthetic native continuations.

No kernel module is loaded. Check six callee-saved registers, RSP and both
unexecuted acquisition and delegated unlock returns before the live experiment.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source

ROOT = Path(__file__).resolve().parents[3]

CHECK = r'''
.text
.globl checked_call
.type checked_call,@function
checked_call:
    push %rbp
    push %rbx
    push %r12
    push %r13
    push %r14
    push %r15
    sub $8,%rsp
    mov %rsp,(%rsp)
    mov %rdi,%r11
    mov %rsi,%rdi
    mov %rdx,%rsi
    mov $0x101,%rbp
    mov $0x102,%rbx
    mov $0x103,%r12
    mov $0x104,%r13
    mov $0x105,%r14
    mov $0x106,%r15
    call *%r11
    cmp %rsp,(%rsp)
    jne bad_context
    cmp $0x101,%rbp
    jne bad_context
    cmp $0x102,%rbx
    jne bad_context
    cmp $0x103,%r12
    jne bad_context
    cmp $0x104,%r13
    jne bad_context
    cmp $0x105,%r14
    jne bad_context
    cmp $0x106,%r15
    jne bad_context
    add $8,%rsp
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %rbx
    pop %rbp
    ret
bad_context:
    ud2
.size checked_call,.-checked_call
.section .note.GNU-stack,"",@progbits
'''

C = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
typedef uintptr_t word;
extern void komb_context_switch(void *,void *);
extern void komb_spin_lock_slowpath(void *);
extern void checked_call(void *,void *,void *);
static word main_sp, worker_sp, shadow_sp;
/* The production node declaration is inserted before this fixture. */
static struct komb_node node;
#define node_sp node.rsp
static word worker_stack[4096] __attribute__((aligned(16)));
static word shadow_stack[4096] __attribute__((aligned(16)));
static int visits, mode, phase, effects;
__attribute__((noipa)) struct komb_node *get_komb_node(void) { return &node; }
__attribute__((noipa)) word *get_shadow_stack_ptr(void) { return &shadow_sp; }
static void worker(void)
{
    for (int i=0;i<128;i++) {
        visits++;
        checked_call(komb_context_switch,&main_sp,&worker_sp);
    }
    abort();
}
__attribute__((noipa)) int __komb_spin_lock_slowpath(void *lock)
{
    word address=(word)&address;
    assert(lock==(void *)0x1234);
    assert(address>(word)shadow_stack && address<(word)(shadow_stack+4096));
    assert(phase==0);
    phase=1;
    if (mode) {
        /* Lend the original stack to the body. Its later unlock saves a
         * different continuation, which the waiter-entry assembly restores. */
        komb_context_switch(&node_sp,&shadow_sp);
        assert(phase==2);
        phase=3;
    }
    return 0;
}
int main(void)
{
    word *sp=worker_stack+4096;
    *--sp=(word)abort;
    *--sp=(word)worker;
    for (int i=0;i<6;i++) *--sp=0x200+i;
    worker_sp=(word)sp;
    for (int i=0;i<128;i++) {
        checked_call(komb_context_switch,&worker_sp,&main_sp);
        assert(visits==i+1);
    }
    for (int i=0;i<128;i++) {
        mode=i%2; phase=0;
        shadow_sp=(word)(shadow_stack+4096);
        checked_call(komb_spin_lock_slowpath,(void *)0x1234,NULL);
        assert(phase==1);
        effects++;
        if (mode) {
            phase=2;
            checked_call(komb_context_switch,&shadow_sp,&node_sp);
            assert(phase==3);
        }
        assert(shadow_sp==(word)(shadow_stack+4096));
    }
    assert(effects==128);
    puts("PASS TCLock C inline asm: 128 switches, 64 acquire returns, 64 unlock continuations; six GPRs/RSP intact");
}
'''


def main():
    if ROOT != Path('/root/host_fs/kdlock'):
        raise RuntimeError('execute machine-code tests only in recovery guest')
    with tempfile.TemporaryDirectory(prefix='tc-context-') as temporary:
        p = Path(temporary)
        # Compile the actual production function bodies, not a second assembly
        # implementation. Kernel-only surrounding code is replaced by stubs.
        source = read_source(ROOT/'tclock_backend/komb.c')
        marker = '#pragma GCC push_options\n#pragma GCC optimize("O3")\n__attribute__((noipa)) noinline notrace void\nkomb_spin_lock_slowpath('
        start = source.index(marker)
        end = source.index('#pragma GCC pop_options', start) + len('#pragma GCC pop_options')
        switch = (ROOT/'tclock_backend/combiner.c').read_text()
        switch = switch[switch.index('#pragma GCC push_options'):]
        header = (ROOT/'tclock_backend/include/spinlock/komb.h').read_text()
        node = re.search(r'struct komb_node \{.*?\n\};', header, re.S).group(0)
        prefix = ('#include <stdint.h>\n'
                  'typedef uint8_t u8; typedef uint16_t u16;\n'
                  '#define noinline __attribute__((noinline))\n'
                  '#define notrace __attribute__((no_instrument_function))\n')
        # The public test declaration uses the real opaque lock pointer type.
        fixture = C.replace('komb_spin_lock_slowpath(void *)',
                            'komb_spin_lock_slowpath(struct qspinlock *)')
        (p/'test.c').write_text(prefix + node + '\n' + fixture)
        declarations = ('#include <stddef.h>\n'
                        'struct komb_node *get_komb_node(void);\n'
                        'uint64_t *get_shadow_stack_ptr(void);\n'
                        'int __komb_spin_lock_slowpath(void *);\n')
        (p/'inline.c').write_text(prefix + node + '\n' + declarations + switch +
                                 '\n' + source[start:end] + '\n')
        (p/'check.S').write_text(CHECK)
        flags = ['-O2','-fno-omit-frame-pointer','-mno-red-zone','-fno-pie',
                 '-Wall','-Wextra','-Werror','-Wno-unused-parameter']
        # Only the production functions use the kernel's 8-byte stack ABI.
        # The userspace harness must retain 16-byte alignment for libc calls.
        subprocess.run(['cc', *flags, '-mpreferred-stack-boundary=3', '-c',
                        str(p/'inline.c'), '-o', str(p/'inline.o')],check=True,timeout=30)
        subprocess.run(['cc', *flags, '-no-pie', str(p/'inline.o'),
                        str(p/'check.S'),
                        str(p/'test.c'),'-o',str(p/'test')],check=True,timeout=30)
        subprocess.run([p/'test'],check=True,timeout=10)


if __name__ == '__main__':
    main()
