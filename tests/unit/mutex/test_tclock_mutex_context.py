"""Execute the port's actual mutex stack switch and both waiter continuations.

The upstream ordinary mutex has its own trampoline, independent of spin.
Kernel scheduling/parking is validated by live runs, not by these stubs.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source

from test_tclock_context import C, CHECK, ROOT
from test_spin_shadow import definition


PARK = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
struct task_struct { int references, wakes; } task;
struct komb_mutex_node { u8 completed, locked; struct task_struct *task_struct_ptr; } node;
struct context { unsigned int parks; } context;
#define tc_mutex_current() (&context)
#define KOMB_WAITER_UNPROCESSED 0
#define KOMB_WAITER_PARKED 1
#define KOMB_WAITER_PROCESSING 2
#define KOMB_WAITER_PROCESSED 4
#define TASK_RUNNING 0
#define TASK_INTERRUPTIBLE 1
#define WRITE_ONCE(p, value) ((p) = (value))
#define cmpxchg(p, old, value) __sync_val_compare_and_swap(p, old, value)
#define xchg(p, value) __sync_lock_test_and_set(p, value)
static int state, preempt = 1, schedules;
static void preempt_enable(void) { assert(preempt == 1); preempt--; }
static void preempt_disable(void) { assert(!preempt); preempt++; }
static void __set_current_state(int value) { state = value; }
static void get_task_struct(struct task_struct *t) { t->references++; }
static void put_task_struct(struct task_struct *t) { assert(t->references == 1); t->references--; }
static void wake_up_process(struct task_struct *t) { assert(t->references == 1); t->wakes++; }
static inline void wake_up_waiter(struct komb_mutex_node *);
static void schedule(void)
{
    assert(!preempt && state == TASK_INTERRUPTIBLE && node.completed == 1);
    schedules++;
    wake_up_waiter(&node);
}
/* PRODUCTION_PARK */
int main(void)
{
    node.task_struct_ptr = &task;
    park_waiter(&node);
    assert(schedules == 1 && context.parks == 1 && preempt == 1);
    assert(state == TASK_RUNNING && node.completed == 2);
    assert(task.wakes == 1 && !task.references);
    /* Processing won before the parking CAS: no missed wake and no sleep. */
    park_waiter(&node);
    assert(schedules == 1 && state == TASK_RUNNING);
    wake_up_waiter(&node);
    assert(task.wakes == 1 && !task.references);
    node.locked = 1;
    clear_locked_set_completed(&node);
    assert(node.completed == 4 && !node.locked);
    puts("PASS TCLock mutex parking: parked wake, pre-CAS processing race, task references and completion");
}
'''


def main():
    if ROOT != Path('/root/host_fs/kdlock'):
        raise RuntimeError('execute machine-code tests only in recovery guest')
    source = read_source(ROOT/'tclock_backend/komb_mutex.c')
    marker = '#pragma GCC push_options\n#pragma GCC optimize("O3")\n__attribute__((noipa)) noinline notrace void\n__komb_mutex_lock('
    start = source.index(marker)
    end = source.index('#pragma GCC pop_options', start) + len('#pragma GCC pop_options')
    switch = (ROOT/'tclock_backend/combiner.c').read_text()
    switch = switch[switch.index('#pragma GCC push_options'):]
    header = (ROOT/'tclock_backend/include/mutex/komb_mutex.h').read_text()
    node = re.search(r'struct komb_mutex_node \{.*?\n\};', header, re.S).group(0)
    prefix = ('#include <stdint.h>\n#include <stddef.h>\n'
              'typedef uint8_t u8; typedef uint16_t u16; typedef long atomic_long_t;\n'
              'struct komb_mutex;\n'
              '#define noinline __attribute__((noinline))\n'
              '#define notrace __attribute__((no_instrument_function))\n')
    fixture = C.replace('__komb_spin_lock_slowpath', 'komb_mutex_lock_slowpath')
    fixture = fixture.replace('komb_spin_lock_slowpath', '__komb_mutex_lock')
    fixture = fixture.replace('struct komb_node', 'struct komb_mutex_node')
    fixture = fixture.replace('get_komb_node(void)', 'get_komb_mutex_node(struct komb_mutex *unused)')
    fixture = fixture.replace('get_shadow_stack_ptr(void)', 'get_shadow_stack_ptr(struct komb_mutex *unused)')
    fixture = fixture.replace('__komb_mutex_lock(void *)', '__komb_mutex_lock(struct komb_mutex *)')
    fixture = fixture.replace('PASS TCLock C', 'PASS TCLock mutex C')
    declarations = ('struct komb_mutex_node *get_komb_mutex_node(struct komb_mutex *);\n'
                    'uint64_t *get_shadow_stack_ptr(struct komb_mutex *);\n'
                    'int komb_mutex_lock_slowpath(void *);\n')
    with tempfile.TemporaryDirectory(prefix='tc-mutex-context-') as temporary:
        p = Path(temporary)
        (p/'test.c').write_text(prefix + node + '\n' + fixture)
        (p/'inline.c').write_text(prefix + node + '\n' + declarations + switch +
                                 '\n' + source[start:end] + '\n')
        (p/'check.S').write_text(CHECK)
        flags = ['-O2', '-fno-omit-frame-pointer', '-mno-red-zone', '-fno-pie',
                 '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter']
        subprocess.run(['cc', *flags, '-mpreferred-stack-boundary=3', '-c',
                        str(p/'inline.c'), '-o', str(p/'inline.o')], check=True, timeout=30)
        subprocess.run(['cc', *flags, '-no-pie', str(p/'inline.o'), str(p/'check.S'),
                        str(p/'test.c'), '-o', str(p/'test')], check=True, timeout=30)
        subprocess.run([p/'test'], check=True, timeout=10)
        functions = ''.join(definition(source, marker) for marker in (
            'static inline void schedule_out_curr_task(void)',
            'static inline void park_waiter(struct komb_mutex_node *node)',
            'static inline void wake_up_waiter(struct komb_mutex_node *node)',
        ))
        functions += 'static inline void\n' + definition(
            source, 'clear_locked_set_completed(struct komb_mutex_node *node)')
        (p/'park.c').write_text(PARK.replace('/* PRODUCTION_PARK */', functions))
        subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(p/'park.c'), '-o', str(p/'park')], check=True, timeout=30)
        subprocess.run([p/'park'], check=True, timeout=10)


if __name__ == '__main__':
    main()
