"""Guest-only production rwsem read admission and OSQ lifetime checks.

Deterministic queue/scheduler substitutes validate ordering, bounded reader
control flow and release wake ordering. Canonical writer phase selection and
queued-reader precedence run in test_admission.py with the production queue.
These checks do not prove weak-memory ordering,
concurrent OSQ unlink or sleeping-reader progress; the existing mutex OSQ
fixture and live rwsem probe cover the latter two separately.
"""
import os
import resource
import shlex
import signal
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_spin_shadow import definition


FIXTURE = r'''
#include <assert.h>
#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#define noinline __attribute__((noinline))
#define likely(value) (value)
#define TASK_UNINTERRUPTIBLE 1U

struct kd_mutex { int unused; };
struct kd_mutex_osq_node { int unused; };
struct optimistic_spin_queue { int tail; };
struct kd_rwsem {
    struct kd_mutex gate;
    struct optimistic_spin_queue reader_osq;
    int phase_wait;
};
static struct kd_rwsem sem;
static struct kd_mutex_osq_node slot;
static unsigned int pins, gets, locks, unlocks, put_calls, tries, pauses, waits;
static unsigned int early_pauses, pinned_pauses;
static unsigned int resched_calls, resched_at, acquire_at, owned, sleeps;
static unsigned int spin_exits, tail_checks, barriers, wakes;
static int remaining_tail;
static bool available, grant, reserved, queued, waiting;
static bool wake_barrier;

static void preempt_disable(void)
{ assert(!pins && !owned); pins++; }
static void preempt_enable(void)
{ assert(pins == 1 && !reserved && !queued); pins--; spin_exits++; }
static int atomic_read(int *counter)
{
    assert(counter == &sem.reader_osq.tail && !pins && !reserved && !queued);
    tail_checks++;
    return *counter;
}
static void smp_mb(void)
{
    assert(!pins && !reserved && !queued && !wake_barrier);
    assert(spin_exits == 1 && tail_checks == 1 && !sem.reader_osq.tail);
    barriers++;
    wake_barrier = true;
}
static void kd_rwsem_wake(struct kd_rwsem *s, int *queue)
{
    assert(s == &sem && queue == &sem.phase_wait && !pins && !reserved && !queued);
    assert(wake_barrier && barriers == wakes + 1);
    wakes++;
    wake_barrier = false;
}
static bool need_resched(void)
{
    assert(pins <= 1 && (pins || (!reserved && !queued)));
    resched_calls++;
    return resched_at && resched_calls >= resched_at;
}
static struct kd_mutex_osq_node *kd_mutex_osq_node_get(struct kd_mutex *gate)
{
    assert(gate == &sem.gate && pins == 1 && !reserved && !queued);
    gets++;
    if (!available)
        return NULL;
    reserved = true;
    return &slot;
}
static bool kd_mutex_osq_lock(struct optimistic_spin_queue *queue,
                              struct kd_mutex_osq_node *node)
{
    assert(queue == &sem.reader_osq && node == &slot && pins == 1 && reserved);
    assert(!queued && !owned);
    locks++;
    queued = grant;
    queue->tail = grant ? 1 : remaining_tail;
    return grant;
}
static void kd_mutex_osq_unlock(struct optimistic_spin_queue *queue,
                                struct kd_mutex_osq_node *node)
{
    assert(queue == &sem.reader_osq && node == &slot && pins == 1 && reserved && queued);
    unlocks++;
    queued = false;
    queue->tail = remaining_tail;
}
static void kd_mutex_osq_node_put(struct kd_mutex_osq_node *node)
{
    assert(node == &slot && pins == 1 && reserved && !queued);
    put_calls++;
    reserved = false;
}
static int kd_down_read_trylock(struct kd_rwsem *s)
{
    assert(s == &sem && !owned);
    assert(pins ? (pins == 1 && reserved && queued) : (!reserved && !queued));
    tries++;
    if (waiting || (acquire_at && tries == acquire_at)) {
        owned++;
        return 1;
    }
    return 0;
}
static void cpu_relax(void)
{
    assert(!owned);
    if (pins) {
        assert(pins == 1 && reserved && queued);
        pinned_pauses++;
    } else {
        assert(!reserved && !queued);
        early_pauses++;
    }
    pauses++;
}
static void might_sleep(void)
{ assert(!pins && !reserved && !queued && !owned); sleeps++; }
static void prepare_wait(int *queue)
{
    assert(queue == &sem.phase_wait && !pins && !reserved && !queued && !owned);
    assert(!wake_barrier && wakes == (sem.reader_osq.tail ? 0 : spin_exits));
    waits++;
    waiting = true;
}
#define wait_event(queue, condition) do { \
    prepare_wait(&(queue)); \
    assert(condition); \
    waiting = false; \
} while (0)

static long kd_rwsem_wait_condition(struct kd_rwsem *s, int *queue,
                                    int kind, unsigned int state, bool timed);
#include "rwsem_read_production.h"

static long kd_rwsem_wait_condition(struct kd_rwsem *s, int *queue,
                                    int kind, unsigned int state, bool timed)
{
    assert(s == &sem && kind == KD_RWSEM_CONDITION_READ);
    assert(state == TASK_UNINTERRUPTIBLE && !timed);
    prepare_wait(queue);
    assert(kd_down_read_trylock(s));
    waiting = false;
    return 0;
}

static void reset(void)
{
    assert(!pins && !reserved && !queued);
    pins=gets=locks=unlocks=put_calls=tries=pauses=waits=0;
    early_pauses=pinned_pauses=0;
    resched_calls=resched_at=acquire_at=owned=sleeps=0;
    spin_exits=tail_checks=barriers=wakes=0;
    remaining_tail=0;
    sem.reader_osq.tail=0;
    available=grant=true;
    reserved=queued=waiting=false;
    wake_barrier=false;
}
static void returned(bool acquired)
{
    assert(!pins && !reserved && !queued && !waiting);
    assert(owned == (unsigned int)acquired);
    assert(put_calls == (available ? gets : 0));
    assert(unlocks == (grant ? locks : 0));
    assert(pauses == early_pauses+pinned_pauses);
    assert(!wake_barrier && barriers == wakes && tail_checks == spin_exits);
    assert(wakes == (sem.reader_osq.tail ? 0 : spin_exits));
}
int main(void)
{
    reset(); acquire_at=1;
    kd_down_read(&sem);
    returned(true);
    assert(tries==1 && sleeps==1 && !gets && !locks && !waits && !resched_calls);

    /* All eight brief-phase probes stay unqueued. The last successful probe
     * must not reserve a slot, retry ownership, or add a trailing pause. */
    for (unsigned int at=2; at<=8; at++) {
        reset(); acquire_at=at;
        kd_down_read(&sem);
        returned(true);
        assert(tries==at && sleeps==1 && !gets && !locks && !waits);
        assert(early_pauses==at-1 && !pinned_pauses && resched_calls==at-1);
    }

    /* Successful OSQ-head admission is evaluated once; the payload returns
     * unpinned with read ownership and no reserved auxiliary slot. */
    reset(); acquire_at=12;
    kd_down_read(&sem);
    returned(true);
    assert(tries==12 && gets==1 && locks==1 && put_calls==1 && !waits);
    assert(early_pauses==8 && pinned_pauses==3);

    reset(); resched_at=1;
    assert(!kd_rwsem_spin_read(&sem));
    returned(false);
    assert(!gets && !tries && !pauses);

    reset(); available=false;
    assert(!kd_rwsem_spin_read(&sem));
    returned(false);
    assert(gets==1 && !locks && !tries && !pauses);

    reset(); grant=false;
    assert(!kd_rwsem_spin_read(&sem));
    returned(false);
    assert(gets==1 && locks==1 && put_calls==1 && !tries && !pauses && !unlocks);

    reset(); resched_at=2;
    assert(!kd_rwsem_spin_read(&sem));
    returned(false);
    assert(tries==1 && !pauses && unlocks==1 && put_calls==1);

    reset();
    assert(!kd_rwsem_spin_read(&sem));
    returned(false);
    assert(tries==16384 && pauses==16384 && unlocks==1 && put_calls==1);
    assert(!early_pauses && pinned_pauses==16384);

    reset(); acquire_at=16384;
    assert(kd_rwsem_spin_read(&sem));
    returned(true);
    assert(tries==16384 && pauses==16383 && unlocks==1 && put_calls==1 && !waits);
    assert(!early_pauses && pinned_pauses==16383);

    /* Another reader can remain queued after every exit class. In that
     * case this caller must release its own resources without waking the
     * writers whose phase predicate is still blocked by the cohort. */
    for (unsigned int mode=0; mode<5; mode++) {
        reset(); sem.reader_osq.tail=remaining_tail=7;
        if (mode==0) resched_at=1;
        if (mode==1) available=false;
        if (mode==2) grant=false;
        if (mode==3) resched_at=2;
        if (mode==4) acquire_at=1;
        assert(kd_rwsem_spin_read(&sem) == (mode==4));
        returned(mode==4);
        assert(sem.reader_osq.tail==7 && !wakes && !barriers);
    }

    /* Every failure class falls back only after pin, OSQ and slot release. */
    for (unsigned int mode=0; mode<6; mode++) {
        reset();
        if (mode==0) resched_at=1;
        if (mode==1) available=false;
        if (mode==2) grant=false;
        if (mode==3) resched_at=10;
        if (mode==5) resched_at=9;
        kd_down_read(&sem);
        returned(true);
        assert(waits==1 && sleeps==1);
        if (mode==0) assert(tries==2 && !early_pauses && !pinned_pauses && !gets);
        if (mode==1 || mode==2) assert(tries==9 && early_pauses==8 && !pinned_pauses);
        if (mode==3) assert(tries==10 && early_pauses==8 && !pinned_pauses && unlocks==1);
        if (mode==4) assert(tries==16393 && early_pauses==8 && pinned_pauses==16384);
        if (mode==5) assert(tries==9 && early_pauses==8 && !pinned_pauses && !gets);
    }
    puts("PASS rwsem read admission: bounded polling, released fallback and ordered cohort wake");
}
'''


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    source = read_source(ROOT / 'kernel_module/kd_rwsem.c')
    # Extract this statement-expression macro itself. Its former neighboring
    # wait macro was replaced by the common condition-channel implementation.
    poll_start = source.index('#define kd_rwsem_poll(condition)')
    poll_end = source.index('\n})\n', poll_start) + len('\n})\n')
    poll = source[poll_start:poll_end]
    spin = definition(source, 'static bool kd_rwsem_spin_read(struct kd_rwsem *sem)')
    fast = definition(source, 'void kd_down_read(struct kd_rwsem *sem)')
    condition_kind = definition(source, 'enum kd_rwsem_condition_kind {') + ';'
    # Writers now use canonical exact phase admission. Its queued-reader
    # precedence and drain checks live in test_admission.py, not the retired
    # scalar local/delegated cohort reservation functions.
    code = condition_kind + '\n' + poll + spin + fast
    pinned_wake = spin.replace('out:\n\tpreempt_enable();', 'out:', 1).replace(
        '\treturn acquired;', '\tpreempt_enable();\n\treturn acquired;', 1)
    mutations = {
        'lost-slot-release': ('kd_mutex_osq_node_put(node);', '(void)kd_mutex_osq_node_put; (void)node;'),
        'lost-queue-release': ('kd_mutex_osq_unlock(&sem->reader_osq, node);', '(void)kd_mutex_osq_unlock; (void)node;'),
        'failure-returns-ownership': ('return acquired;', '(void)acquired; return true;'),
        'early-retry-budget': ('unsigned int retries = 8;', 'unsigned int retries = 9;'),
        'repeat-successful-first-probe': (
            fast, fast.replace('if (kd_down_read_trylock(sem))',
                               'if (kd_down_read_trylock(sem) && false)', 1)),
        'lost-first-failed-pause': (
            fast, fast.replace('cpu_relax();', '(void)cpu_relax;', 1)),
        'unbounded-poll': ('while (--kd_rwsem_budget)', 'while (--kd_rwsem_budget || true)'),
        'lost-wake-barrier': ('smp_mb();', '(void)smp_mb;'),
        'lost-cohort-wake': ('kd_rwsem_wake(sem, &sem->phase_wait);', '(void)kd_rwsem_wake;'),
        'wake-before-barrier': (
            'smp_mb();\n\t\tkd_rwsem_wake(sem, &sem->phase_wait);',
            'kd_rwsem_wake(sem, &sem->phase_wait);\n\t\tsmp_mb();'),
        'wake-while-pinned': (spin, pinned_wake),
        'wake-with-reader-cohort': (
            'if (!atomic_read(&sem->reader_osq.tail))',
            'if ((void)atomic_read(&sem->reader_osq.tail), true)'),
        'wake-only-on-read-acquisition': (
            'if (!atomic_read(&sem->reader_osq.tail))',
            'if (acquired && !atomic_read(&sem->reader_osq.tail))'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-rwsem-read-') as directory:
        path = Path(directory)
        (path / 'fixture.c').write_text(FIXTURE)
        compiler = shlex.split(os.environ.get('CC', 'cc'))
        for name, replacement in [('production', None), *mutations.items()]:
            body = code
            if replacement:
                old, new = replacement
                assert old in body, name
                body = body.replace(old, new, 1)
            (path / 'rwsem_read_production.h').write_text(body)
            binary = path / name
            command = compiler + ['-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                  '-I', str(path),
                                  str(path / 'fixture.c'), '-o', str(binary)]
            subprocess.run(command, check=True, timeout=30)
            try:
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            except subprocess.TimeoutExpired:
                assert replacement and name == 'unbounded-poll', name
                print('rwsem read mutation detected:', name)
                continue
            if replacement:
                assert result.returncode == -signal.SIGABRT and 'Assertion' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('rwsem read mutation detected:', name)
            else:
                assert result.returncode == 0, result.stdout + result.stderr
                print(result.stdout, end='')
        count_checks(source, compiler, path)


def count_checks(source, compiler, path):
    """Use actual reader functions with deterministic publication boundaries.

    This checks exact count/rollback/final-access effects and source barrier ordering;
    the synthetic atomic functions are not a concurrent weak-memory model.
    """
    release = definition(source, 'void kd_up_read(struct kd_rwsem *sem)')
    acquire = definition(source, 'int kd_down_read_trylock(struct kd_rwsem *sem)')
    read_try = definition(source, 'static int kd_rwsem_try_read(struct kd_rwsem *sem, bool notify)')
    code = release + read_try + acquire
    fixture = ROOT / 'tests/unit/mutex/rwsem_read_count_fixture.c'
    (path / 'count_fixture.c').write_text(read_source(fixture))
    mutations = {
        'missing-before-atomic-order': (
            'atomic_long_inc_return(&sem->readers);',
            '(void)atomic_long_inc_return; atomic_long_inc(&sem->readers); smp_mb__after_atomic();'),
        'missing-after-atomic-order': (
            'atomic_long_inc_return(&sem->readers);',
            '(void)atomic_long_inc_return; smp_mb__before_atomic(); atomic_long_inc(&sem->readers);'),
        'publication-before-order': (
            'atomic_long_inc_return(&sem->readers);',
            '(void)atomic_long_inc_return; atomic_long_inc(&sem->readers); smp_mb__before_atomic(); smp_mb__after_atomic();'),
        'ignore-closed-phase-recheck': (
            'if (!atomic_long_read_acquire(&sem->admission))',
            'if ((void)atomic_long_read_acquire(&sem->admission), true)'),
        'missing-reader-rollback': ('kd_up_read(sem);', '(void)kd_up_read;'),
        'double-reader-rollback': ('kd_up_read(sem);', 'kd_up_read(sem); kd_up_read(sem);'),
        'release-reads-irq-context': (
            '(void)atomic_long_dec_and_test(&sem->readers);',
            '(void)irqs_disabled(); (void)atomic_long_dec_and_test(&sem->readers);'),
        'release-reads-atomic-context': (
            '(void)atomic_long_dec_and_test(&sem->readers);',
            '(void)in_atomic(); (void)atomic_long_dec_and_test(&sem->readers);'),
        'post-final-notification': (
            '(void)atomic_long_dec_and_test(&sem->readers);',
            'if (atomic_long_dec_and_test(&sem->readers)) kd_rwsem_wake(sem, &sem->reader_drain);'),
    }
    for name, replacement in [('count-production', None), *mutations.items()]:
        body = code
        if replacement:
            old, new = replacement
            assert old in body, name
            body = body.replace(old, new, 1)
        (path / 'rwsem_read_count_production.h').write_text(body)
        binary = path / name
        subprocess.run(compiler + ['-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                   '-I', str(path), str(path / 'count_fixture.c'),
                                   '-o', str(binary)], check=True, timeout=30)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
        if replacement:
            assert result.returncode == -signal.SIGABRT and 'Assertion' in result.stderr, (
                name, result.returncode, result.stdout, result.stderr)
            print('rwsem reader count mutation detected:', name)
        else:
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout, end='')


if __name__ == '__main__':
    main()
