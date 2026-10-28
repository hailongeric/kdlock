"""Guest-only production rwsem read admission and OSQ lifetime checks.

Deterministic queue/scheduler substitutes validate ordering, bounded control
flow and writer reservation retries. They do not prove weak-memory ordering,
concurrent OSQ unlink or sleeping-reader progress; the existing mutex OSQ
fixture and live rwsem probe cover the latter two separately.
"""
import os
import shlex
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

struct kd_mutex { int unused; };
struct kd_mutex_osq_node { int unused; };
struct optimistic_spin_queue { int tail; };
struct kd_rwsem {
    struct kd_mutex gate;
    struct optimistic_spin_queue reader_osq;
    long admission;
    int phase_wait;
};
static struct kd_rwsem sem;
static struct kd_mutex_osq_node slot;
static unsigned int pins, gets, locks, unlocks, put_calls, tries, pauses, waits;
static unsigned int early_pauses, pinned_pauses;
static unsigned int resched_calls, resched_at, acquire_at, owned, sleeps;
static unsigned int spin_exits, tail_checks, barriers, wakes, cas_calls;
static int remaining_tail, injected_tail;
static long injected_phase;
static bool available, grant, reserved, queued, waiting;
static bool wake_barrier, inject_cas;

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
static void kd_rwsem_wake(int *queue)
{
    assert(queue == &sem.phase_wait && !pins && !reserved && !queued);
    assert(wake_barrier && barriers == wakes + 1);
    wakes++;
    wake_barrier = false;
}
static long atomic_long_read(long *counter)
{
    assert(counter == &sem.admission && !pins && !reserved && !queued);
    return *counter;
}
static void interfere(long *counter)
{
    assert(counter == &sem.admission && !pins && !reserved && !queued);
    assert(++cas_calls <= 2);
    if (inject_cas) {
        *counter = injected_phase;
        sem.reader_osq.tail = injected_tail;
        inject_cas = false;
    }
}
static long atomic_long_cmpxchg(long *counter, long old, long value)
{
    long observed;

    assert(old == 0 && value == -1);
    interfere(counter);
    observed = *counter;
    if (observed == old)
        *counter = value;
    return observed;
}
static bool atomic_long_try_cmpxchg(long *counter, long *old, long value)
{
    assert(*old >= 0 && *old < LONG_MAX && value == *old + 1);
    interfere(counter);
    if (*counter == *old) {
        *counter = value;
        return true;
    }
    *old = *counter;
    return false;
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

#include "rwsem_read_production.h"

static void reset(void)
{
    assert(!pins && !reserved && !queued);
    pins=gets=locks=unlocks=put_calls=tries=pauses=waits=0;
    early_pauses=pinned_pauses=0;
    resched_calls=resched_at=acquire_at=owned=sleeps=0;
    spin_exits=tail_checks=barriers=wakes=cas_calls=0;
    remaining_tail=injected_tail=0;
    injected_phase=sem.admission=0;
    sem.reader_osq.tail=0;
    available=grant=true;
    reserved=queued=waiting=false;
    wake_barrier=inject_cas=false;
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
static void reservation_result(long phase, unsigned int compares,
                               unsigned int queue_checks)
{
    assert(!pins && !reserved && !queued && !waiting && !owned);
    assert(!spin_exits && !barriers && !wakes && !wake_barrier);
    assert(sem.admission == phase && cas_calls == compares);
    assert(tail_checks == queue_checks);
}
static void check_writer_reservations(void)
{
    const long closed[] = {-1, 1, LONG_MAX};

    /* An ordinary writer can only close an open phase with no queued
     * readers. A closed phase must not even attempt the reservation RMW. */
    for (unsigned int i=0; i<sizeof(closed)/sizeof(closed[0]); i++) {
        reset(); sem.admission=closed[i];
        assert(!kd_rwsem_reserve_local(&sem));
        reservation_result(closed[i], 0, 0);
    }
    reset(); sem.reader_osq.tail=7;
    assert(!kd_rwsem_reserve_local(&sem));
    reservation_result(0, 0, 1);
    reset();
    assert(kd_rwsem_reserve_local(&sem));
    reservation_result(-1, 1, 1);
    reset(); inject_cas=true; injected_phase=3; injected_tail=7;
    assert(!kd_rwsem_reserve_local(&sem));
    reservation_result(3, 1, 1);

    /* Queue presence is a fairness hint. A racing enqueue after the check
     * does not replace the exact phase CAS with a queue ownership test. */
    reset(); inject_cas=true; injected_phase=0; injected_tail=7;
    assert(kd_rwsem_reserve_local(&sem));
    reservation_result(-1, 1, 1);
    assert(sem.reader_osq.tail == 7);

    reset(); sem.reader_osq.tail=7;
    assert(!kd_rwsem_reserve_delegate(&sem));
    reservation_result(0, 0, 1);
    reset();
    assert(kd_rwsem_reserve_delegate(&sem));
    reservation_result(1, 1, 1);

    /* Existing delegated cohorts retain exact reservations even when
     * readers are queued; only the transition from zero yields to them. */
    reset(); sem.admission=2; sem.reader_osq.tail=7;
    assert(kd_rwsem_reserve_delegate(&sem));
    reservation_result(3, 1, 0);
    reset(); sem.admission=LONG_MAX-1; sem.reader_osq.tail=7;
    assert(kd_rwsem_reserve_delegate(&sem));
    reservation_result(LONG_MAX, 1, 0);
    reset(); sem.admission=LONG_MAX;
    assert(!kd_rwsem_reserve_delegate(&sem));
    reservation_result(LONG_MAX, 0, 0);
    reset(); sem.admission=-1;
    assert(!kd_rwsem_reserve_delegate(&sem));
    reservation_result(-1, 0, 0);

    /* A failed CAS can observe the previous cohort's final release. The
     * next iteration must recheck the queue before creating a new cohort. */
    reset(); sem.admission=2;
    inject_cas=true; injected_phase=0; injected_tail=7;
    assert(!kd_rwsem_reserve_delegate(&sem));
    reservation_result(0, 1, 1);
    reset(); sem.admission=2;
    inject_cas=true; injected_phase=0;
    assert(kd_rwsem_reserve_delegate(&sem));
    reservation_result(1, 2, 1);
    reset(); sem.admission=2;
    inject_cas=true; injected_phase=4; injected_tail=7;
    assert(kd_rwsem_reserve_delegate(&sem));
    reservation_result(5, 2, 0);
    reset(); sem.admission=2;
    inject_cas=true; injected_phase=-1;
    assert(!kd_rwsem_reserve_delegate(&sem));
    reservation_result(-1, 1, 0);
    reset(); sem.admission=2;
    inject_cas=true; injected_phase=LONG_MAX;
    assert(!kd_rwsem_reserve_delegate(&sem));
    reservation_result(LONG_MAX, 1, 0);

    reset(); inject_cas=true; injected_phase=0; injected_tail=7;
    assert(kd_rwsem_reserve_delegate(&sem));
    reservation_result(1, 1, 1);
    assert(sem.reader_osq.tail == 7);
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
    check_writer_reservations();
    puts("PASS rwsem read admission: bounded polling, released fallback, ordered cohort wake, exact writer reservations");
}
'''


def main():
    source = read_source(ROOT / 'kernel_module/kd_rwsem.c')
    poll = source[source.index('#define kd_rwsem_poll(condition)'):
                  source.index('#define kd_rwsem_wait(queue, condition)')]
    spin = definition(source, 'static bool kd_rwsem_spin_read(struct kd_rwsem *sem)')
    local = definition(source, 'static bool kd_rwsem_reserve_local(struct kd_rwsem *sem)')
    delegate = definition(source, 'static bool kd_rwsem_reserve_delegate(struct kd_rwsem *sem)')
    local_phase = next(line for line in source.splitlines()
                       if line.startswith('#define KD_RWSEM_LOCAL_WRITER '))
    code = local_phase + '\n' + poll + spin + local + delegate
    code += definition(source, 'void kd_down_read(struct kd_rwsem *sem)')
    queue_guard = ('\t\tif (!phase && atomic_read(&sem->reader_osq.tail))\n'
                   '\t\t\treturn false;\n')
    delegate_loop = '\twhile (phase >= 0 && phase < LONG_MAX) {'
    assert queue_guard in delegate and delegate_loop in delegate
    stale_guard = delegate.replace(queue_guard, '', 1).replace(
        delegate_loop,
        '\tif (!phase && atomic_read(&sem->reader_osq.tail))\n'
        '\t\treturn false;\n' + delegate_loop, 1)
    pinned_wake = spin.replace('out:\n\tpreempt_enable();', 'out:', 1).replace(
        '\treturn acquired;', '\tpreempt_enable();\n\treturn acquired;', 1)
    mutations = {
        'lost-slot-release': ('kd_mutex_osq_node_put(node);', '(void)kd_mutex_osq_node_put; (void)node;'),
        'lost-queue-release': ('kd_mutex_osq_unlock(&sem->reader_osq, node);', '(void)kd_mutex_osq_unlock; (void)node;'),
        'failure-returns-ownership': ('return acquired;', '(void)acquired; return true;'),
        'early-retry-budget': ('unsigned int retries = 8;', 'unsigned int retries = 9;'),
        'unbounded-poll': ('while (--kd_rwsem_budget)', 'while (--kd_rwsem_budget || true)'),
        'lost-wake-barrier': ('smp_mb();', '(void)smp_mb;'),
        'lost-cohort-wake': ('kd_rwsem_wake(&sem->phase_wait);', '(void)kd_rwsem_wake;'),
        'wake-before-barrier': (
            'smp_mb();\n\t\tkd_rwsem_wake(&sem->phase_wait);',
            'kd_rwsem_wake(&sem->phase_wait);\n\t\tsmp_mb();'),
        'wake-while-pinned': (spin, pinned_wake),
        'wake-with-reader-cohort': (
            'if (!atomic_read(&sem->reader_osq.tail))',
            'if ((void)atomic_read(&sem->reader_osq.tail), true)'),
        'wake-only-on-read-acquisition': (
            'if (!atomic_read(&sem->reader_osq.tail))',
            'if (acquired && !atomic_read(&sem->reader_osq.tail))'),
        'local-writer-ignores-readers': (
            'if (atomic_long_read(&sem->admission) ||\n'
            '\t    atomic_read(&sem->reader_osq.tail))',
            'if (atomic_long_read(&sem->admission))'),
        'new-delegated-cohort-ignores-readers': (
            'if (!phase && atomic_read(&sem->reader_osq.tail))',
            'if (false && atomic_read(&sem->reader_osq.tail))'),
        'queued-readers-block-existing-cohort': (
            'if (!phase && atomic_read(&sem->reader_osq.tail))',
            'if (atomic_read(&sem->reader_osq.tail))'),
        'queue-hint-not-rechecked-after-cas-failure': (delegate, stale_guard),
        'delegated-reservation-saturates-early': (
            'while (phase >= 0 && phase < LONG_MAX)',
            'while (phase >= 0 && phase < LONG_MAX - 1)'),
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
                assert result.returncode != 0, name
                print('rwsem read mutation detected:', name)
            else:
                assert result.returncode == 0, result.stdout + result.stderr
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
