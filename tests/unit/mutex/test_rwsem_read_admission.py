"""Guest-only production rwsem read admission and OSQ lifetime checks.

Deterministic queue/scheduler substitutes validate ordering and bounded control
flow, including pinned NUMA stripe selection and matching queue retirement.
They do not prove concurrent OSQ unlink or sleeping-reader progress;
the existing mutex OSQ fixture and live rwsem probe cover those separately.
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
#include <stdbool.h>
#include <stdio.h>

struct kd_mutex { int unused; };
struct kd_mutex_osq_node { int unused; };
struct optimistic_spin_queue { int tail; };
struct kd_rwsem {
    struct kd_mutex gate;
    long readers, admission;
    int phase_wait, reader_drain;
    struct optimistic_spin_queue reader_osq, reader_osq_alt;
};
static struct kd_rwsem sem;
static struct kd_mutex_osq_node slot;
static unsigned int pins, gets, locks, unlocks, put_calls, tries, pauses, waits;
static unsigned int early_pauses, pinned_pauses;
static unsigned int resched_calls, resched_at, acquire_at, owned, sleeps;
static unsigned int current_numa_node, numa_calls;
static struct optimistic_spin_queue *selected_queue, *held_queue;
static bool available, grant, reserved, queued, waiting;

static void kd_mutex_init(struct kd_mutex *gate)
{ assert(gate == &sem.gate); gate->unused = 0; }
static void atomic_long_set(long *value, long count) { *value = count; }
static long atomic_long_read(const long *value) { return *value; }
static int atomic_read(const int *value) { return *value; }
static void init_waitqueue_head(int *queue) { *queue = 0; }
static bool waitqueue_active(const int *queue) { return *queue != 0; }
static bool kd_mutex_is_idle(const struct kd_mutex *gate) { return !gate->unused; }
static void osq_lock_init(struct optimistic_spin_queue *queue)
{
    assert(queue == &sem.reader_osq || queue == &sem.reader_osq_alt);
    queue->tail = 0;
}

static void preempt_disable(void)
{ assert(!pins && !owned); pins++; }
static void preempt_enable(void)
{ assert(pins == 1 && !reserved && !queued && !held_queue); pins--; }
static int numa_node_id(void)
{
    /* Four explicit node IDs exercise both stripes and the 2/3 collisions.
     * A topology query before pinning or a second selection before retirement
     * is forbidden. Unlock must retain the original queue pointer. */
    static const unsigned int expected_stripe[] = { 0, 1, 0, 1 };
    assert(pins == 1 && !owned && !queued && !numa_calls && !held_queue);
    assert(current_numa_node < sizeof(expected_stripe)/sizeof(expected_stripe[0]));
    numa_calls++;
    selected_queue = expected_stripe[current_numa_node] ?
        &sem.reader_osq_alt : &sem.reader_osq;
    return (int)current_numa_node;
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
    assert(numa_calls == 1 && queue == selected_queue && node == &slot);
    assert(pins == 1 && reserved && !queued && !owned && !held_queue);
    locks++;
    queued = grant;
    held_queue = grant ? queue : NULL;
    return grant;
}
static void kd_mutex_osq_unlock(struct optimistic_spin_queue *queue,
                                struct kd_mutex_osq_node *node)
{
    assert(queue == held_queue && queue == selected_queue && node == &slot);
    assert(numa_calls == 1 && pins == 1 && reserved && queued);
    unlocks++;
    queued = false;
    held_queue = NULL;
}
static void kd_mutex_osq_node_put(struct kd_mutex_osq_node *node)
{
    assert(node == &slot && pins == 1 && reserved && !queued && !held_queue);
    put_calls++;
    reserved = false;
}
static int kd_down_read_trylock(struct kd_rwsem *s)
{
    assert(s == &sem && !owned);
    assert(pins ? (pins == 1 && reserved && queued && held_queue == selected_queue) :
                  (!reserved && !queued && !held_queue));
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
    assert(queue == &sem.phase_wait && !pins && !reserved && !queued && !owned && !held_queue);
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
    assert(!pins && !reserved && !queued && !held_queue);
    pins=gets=locks=unlocks=put_calls=tries=pauses=waits=0;
    numa_calls=0;
    selected_queue=held_queue=NULL;
    early_pauses=pinned_pauses=0;
    resched_calls=resched_at=acquire_at=owned=sleeps=0;
    available=grant=true;
    reserved=queued=waiting=false;
}
static void returned(bool acquired)
{
    assert(!pins && !reserved && !queued && !waiting && !held_queue);
    assert(owned == (unsigned int)acquired);
    assert(numa_calls == (gets ? 1U : 0U));
    assert(put_calls == (available ? gets : 0));
    assert(unlocks == (grant ? locks : 0));
    assert(pauses == early_pauses+pinned_pauses);
}
static void run_node_cases(void)
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
}

static void init_idle_cases(void)
{
    /* Dynamic initialization must clear both dirty tails and preserve the
     * existing exact count/waitqueue/gate inspection. */
    sem.gate.unused = sem.phase_wait = sem.reader_drain = 1;
    sem.readers = 3;
    sem.admission = 2;
    sem.reader_osq.tail = 5;
    sem.reader_osq_alt.tail = 7;
    kd_rwsem_init(&sem);
    assert(kd_rwsem_is_idle(&sem));
    for (unsigned int tails=0; tails<4; tails++) {
        sem.reader_osq.tail = tails & 1;
        sem.reader_osq_alt.tail = (tails >> 1) & 1;
        assert(kd_rwsem_is_idle(&sem) == (tails == 0));
    }
    sem.reader_osq.tail = sem.reader_osq_alt.tail = 0;
    sem.readers = 1;
    assert(!kd_rwsem_is_idle(&sem));
    sem.readers = 0;
    sem.admission = -1;
    assert(!kd_rwsem_is_idle(&sem));
    sem.admission = 1;
    assert(!kd_rwsem_is_idle(&sem));
    sem.admission = 0;
    sem.phase_wait = 1;
    assert(!kd_rwsem_is_idle(&sem));
    sem.phase_wait = 0;
    sem.reader_drain = 1;
    assert(!kd_rwsem_is_idle(&sem));
    sem.reader_drain = 0;
    sem.gate.unused = 1;
    assert(!kd_rwsem_is_idle(&sem));
    sem.gate.unused = 0;
    assert(kd_rwsem_is_idle(&sem));
}

int main(void)
{
    init_idle_cases();
    /* Run every success, budget and fallback case on nodes 0/1 and on nodes
     * 2/3, which intentionally share those same stripes. Fast acquisitions
     * must avoid a topology query entirely. */
    for (current_numa_node=0; current_numa_node<4; current_numa_node++)
        run_node_cases();
    puts("PASS rwsem read admission: pinned NUMA stripes, local fast path, bounded OSQ heads, released fallback");
}

'''


def main():
    source = read_source(ROOT / 'kernel_module/kd_rwsem.c')
    poll = source[source.index('#define kd_rwsem_poll(condition)'):
                  source.index('#define kd_rwsem_wait(queue, condition)')]
    code = definition(source, 'void kd_rwsem_init(struct kd_rwsem *sem)') + poll
    code += definition(source, 'static bool kd_rwsem_spin_read(struct kd_rwsem *sem)')
    code += definition(source, 'void kd_down_read(struct kd_rwsem *sem)')
    code += definition(source, 'bool kd_rwsem_is_idle(struct kd_rwsem *sem)')
    mutations = {
        'lost-slot-release': ('kd_mutex_osq_node_put(node);', '(void)kd_mutex_osq_node_put; (void)node;'),
        'lost-queue-release': ('kd_mutex_osq_unlock(queue, node);', '(void)kd_mutex_osq_unlock; (void)node;'),
        'wrong-numa-stripe': ('(numa_node_id() & 1)', '((numa_node_id() & 1) ^ 1)'),
        'collapsed-numa-stripes': ('(numa_node_id() & 1)', '(numa_node_id() & 0)'),
        'topology-before-pin': ('preempt_disable();',
                               '(void)numa_node_id(); preempt_disable();'),
        'wrong-unlock-queue': ('kd_mutex_osq_unlock(queue, node);',
                               'kd_mutex_osq_unlock(queue == &sem->reader_osq ? '
                               '&sem->reader_osq_alt : &sem->reader_osq, node);'),
        'reselect-unlock-queue': ('kd_mutex_osq_unlock(queue, node);',
                                  'kd_mutex_osq_unlock((numa_node_id() & 1) ? '
                                  '&sem->reader_osq_alt : &sem->reader_osq, node);'),
        'ignored-primary-idle-tail': ('!atomic_read(&sem->reader_osq.tail) &&', 'true &&'),
        'ignored-alternate-idle-tail': ('!atomic_read(&sem->reader_osq_alt.tail) &&', 'true &&'),
        'uncleared-primary-tail': ('osq_lock_init(&sem->reader_osq);', '(void)sem;'),
        'uncleared-alternate-tail': ('osq_lock_init(&sem->reader_osq_alt);', '(void)sem;'),
        'failure-returns-ownership': ('return acquired;', '(void)acquired; return true;'),
        'early-retry-budget': ('unsigned int retries = 8;', 'unsigned int retries = 9;'),
        'unbounded-poll': ('while (--kd_rwsem_budget)', 'while (--kd_rwsem_budget || true)'),
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
