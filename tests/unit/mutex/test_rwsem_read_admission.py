"""Guest-only production rwsem read admission and OSQ lifetime checks.

Deterministic queue/scheduler substitutes validate ordering and bounded control
flow. They do not prove concurrent OSQ unlink or sleeping-reader progress;
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
struct optimistic_spin_queue { int unused; };
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
static bool available, grant, reserved, queued, waiting;

static void preempt_disable(void)
{ assert(!pins && !owned); pins++; }
static void preempt_enable(void)
{ assert(pins == 1 && !reserved && !queued); pins--; }
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
    return grant;
}
static void kd_mutex_osq_unlock(struct optimistic_spin_queue *queue,
                                struct kd_mutex_osq_node *node)
{
    assert(queue == &sem.reader_osq && node == &slot && pins == 1 && reserved && queued);
    unlocks++;
    queued = false;
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
    available=grant=true;
    reserved=queued=waiting=false;
}
static void returned(bool acquired)
{
    assert(!pins && !reserved && !queued && !waiting);
    assert(owned == (unsigned int)acquired);
    assert(put_calls == (available ? gets : 0));
    assert(unlocks == (grant ? locks : 0));
    assert(pauses == early_pauses+pinned_pauses);
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
    puts("PASS rwsem read admission: local fast path, bounded OSQ head polling, released fallback");
}
'''


def main():
    source = read_source(ROOT / 'kernel_module/kd_rwsem.c')
    poll = source[source.index('#define kd_rwsem_poll(condition)'):
                  source.index('#define kd_rwsem_wait(queue, condition)')]
    code = poll + definition(source, 'static bool kd_rwsem_spin_read(struct kd_rwsem *sem)')
    code += definition(source, 'void kd_down_read(struct kd_rwsem *sem)')
    mutations = {
        'lost-slot-release': ('kd_mutex_osq_node_put(node);', '(void)kd_mutex_osq_node_put; (void)node;'),
        'lost-queue-release': ('kd_mutex_osq_unlock(&sem->reader_osq, node);', '(void)kd_mutex_osq_unlock; (void)node;'),
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
