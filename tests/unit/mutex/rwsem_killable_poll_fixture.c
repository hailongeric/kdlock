/* SPDX-License-Identifier: GPL-2.0 */
/* Deterministic control-flow doubles, not a kernel scheduler or memory model.
 * Production reserve/poll/acquire/drain/release/downgrade/up_read are extracted.
 * The wait double checks outer/retry conditions, condition-before-signal and
 * balanced synthetic boundary exits. Its publication/removal counters count
 * modeled attempts, not actual kernel queue membership: a real fatal-signal
 * prepare_to_wait_event can refuse/remove without adding a waiter. These hooks
 * do not prove Native enqueue/unlink ordering or concurrent scheduling. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define TASK_UNINTERRUPTIBLE 1U
#define TASK_INTERRUPTIBLE 2U
#define TASK_KILLABLE 4U
#define KD_RWSEM_LOCAL_WRITER (-1L)
#define BUG_ON(x) assert(!(x))
#define ERESTARTSYS 512
#define current ((void *)0x1000UL)
struct kd_mutex { bool owned; };
struct kd_rwsem {
    struct kd_mutex gate;
    long admission, readers;
    struct { int tail; } reader_osq;
    int phase_wait, reader_drain;
};
static struct kd_rwsem sem;
static unsigned int attempts, reserves, pauses, resched_checks, signal_checks;
static unsigned int wait_calls, publications, removals, schedules, releases;
static unsigned int locks, unlocks, drain_calls, timer_rechecks, phase_wakes, reader_wakes;
static unsigned int available_at, fatal_at, resched_at, checks;
static bool phase_owned, acquiring, fatal, nonfatal, cas_loss, gate_cancel, drain_cancel, irq;
enum boundary { NONE, BEFORE_WAIT, AFTER_ENQUEUE, SCHEDULE };
static enum boundary release_at;

static void make_available(void) { assert(!phase_owned); sem.admission=0; sem.reader_osq.tail=0; }
static long atomic_long_read(long *p)
{
    assert(p == &sem.admission);
    if (acquiring) {
        /* Rechecking a successful side-effecting predicate must fail the test. */
        assert(!phase_owned);
        ++attempts;
        assert(attempts <= 20000);
        if (available_at == attempts) make_available();
        if (fatal_at == attempts) fatal=true;
    }
    return *p;
}
static long atomic_long_read_acquire(long *p) { assert(p==&sem.readers); return *p; }
static int atomic_read(int *p) { assert(p==&sem.reader_osq.tail); return *p; }
static long atomic_long_cmpxchg(long *p, long old, long value)
{
    assert(p==&sem.admission && old==0 && value==-1 && !phase_owned);
    if (cas_loss) { sem.admission=-1; cas_loss=false; }
    long seen=*p;
    if (seen==old) { *p=value; phase_owned=true; ++reserves; }
    return seen;
}
static long atomic_long_xchg(long *p, long value)
{
    assert(p==&sem.admission && value==0 && phase_owned && !sem.gate.owned);
    long seen=*p; *p=value; phase_owned=false; ++releases; return seen;
}
static void atomic_long_inc(long *p) { assert(p==&sem.readers); ++*p; }
static bool atomic_long_dec_and_test(long *p) { assert(p==&sem.readers && *p>0); return --*p==0; }
static bool need_resched(void)
{
    assert(!phase_owned); ++resched_checks;
    return resched_at && attempts>=resched_at;
}
static bool signal_pending_state(unsigned int state, void *task)
{
    assert(state==TASK_KILLABLE && task==current && !phase_owned);
    ++signal_checks; (void)nonfatal; return fatal;
}
static void cpu_relax(void) { assert(!phase_owned && publications==removals); ++pauses; }
static void might_sleep(void) { assert(!phase_owned && !sem.gate.owned); acquiring=true; }
static bool irqs_disabled(void) { return irq; }
static bool in_atomic(void) { return irq; }
static void kd_rwsem_wake(int *queue)
{
    if (queue==&sem.phase_wait) { assert(!phase_owned && !sem.gate.owned); ++phase_wakes; }
    else { assert(queue==&sem.reader_drain); ++reader_wakes; }
}
static int kd_mutex_lock_killable(struct kd_mutex *lock)
{
    assert(lock==&sem.gate && phase_owned && sem.admission==-1 && !lock->owned);
    assert(publications==removals); acquiring=false; ++locks;
    if (gate_cancel) return -EINTR;
    lock->owned=true; return 0;
}
static void kd_mutex_local_unlock(struct kd_mutex *lock)
{ assert(lock==&sem.gate && lock->owned && phase_owned); lock->owned=false; ++unlocks; }
static bool kd_origin_mutex_owned(struct kd_mutex *lock, void *task)
{ assert(lock==&sem.gate && task==current); return lock->owned; }

static void wait_begin(int *queue)
{
    assert(queue==&sem.phase_wait && !phase_owned && acquiring); ++wait_calls;
    if (release_at==BEFORE_WAIT) make_available();
}
static void publish_wait(void)
{
    /* A synthetic preparation attempt, including an already-pending signal. */
    assert(!phase_owned && publications==removals); ++publications;
    if (release_at==AFTER_ENQUEUE) make_available();
}
static void wait_schedule(void)
{
    assert(!phase_owned && publications==removals+1 && !fatal);
    ++schedules; assert(release_at==SCHEDULE); make_available();
}
#define wait_event_killable(queue, condition) ({ \
    long wait_result=0; wait_begin(&(queue)); \
    if (!(condition)) { \
        publish_wait(); \
        if (!(condition)) { \
            if (signal_pending_state(TASK_KILLABLE,current)) wait_result=-ERESTARTSYS; \
            else { wait_schedule(); assert(condition); } \
        } \
        ++removals; \
    } \
    wait_result; \
})
/* Only the killable production drain is called. Keep other compiled branches
 * available; the unchanged ordinary poll is not modeled or tested here. */
#define kd_rwsem_poll(condition) (!!(condition))
static void kd_up_read(struct kd_rwsem *s);
static void drain_begin(int *queue, int ticks, unsigned int state)
{
    assert(queue==&sem.reader_drain && ticks==1 && state==TASK_KILLABLE);
    assert(phase_owned && sem.gate.owned && !acquiring); ++drain_calls;
}
static void drain_reader(void)
{
    assert(sem.readers==1); kd_up_read(&sem);
    if (irq) ++timer_rechecks;
}
#define drain_wait(queue, condition, ticks, state) ({ \
    long drain_result=1; drain_begin(&(queue), ticks, state); \
    if (!(condition)) { \
        if (drain_cancel) drain_result=-ERESTARTSYS; \
        else { \
            drain_reader(); \
            /* Force a timeout/recheck after a last reader omitted its wake. */ \
            if (irq) drain_result=0; \
            else assert(condition); \
        } \
    } \
    drain_result; \
})
#define wait_event_killable_timeout(queue, condition, ticks) \
    drain_wait(queue, condition, ticks, TASK_KILLABLE)
#define wait_event_interruptible_timeout(queue, condition, ticks) \
    drain_wait(queue, condition, ticks, TASK_INTERRUPTIBLE)
#define wait_event_timeout(queue, condition, ticks) \
    drain_wait(queue, condition, ticks, TASK_UNINTERRUPTIBLE)

#include "rwsem_killable_production.h"

static void reset(void)
{
    assert(!phase_owned && !sem.gate.owned && publications==removals);
    memset(&sem,0,sizeof(sem));
    attempts=reserves=pauses=resched_checks=signal_checks=0;
    wait_calls=publications=removals=schedules=releases=0;
    locks=unlocks=drain_calls=timer_rechecks=phase_wakes=reader_wakes=0;
    available_at=fatal_at=resched_at=0;
    phase_owned=acquiring=fatal=nonfatal=cas_loss=gate_cancel=drain_cancel=irq=false;
    release_at=NONE;
}
static void release_writer(void)
{
    assert(phase_owned && sem.gate.owned && !sem.readers);
    kd_mutex_local_unlock(&sem.gate); kd_rwsem_release_local(&sem);
    assert(!phase_owned && !sem.gate.owned && releases==reserves);
}
static void expect_success(void)
{
    assert(kd_down_write_killable(&sem)==0);
    assert(phase_owned && sem.gate.owned && !sem.readers && reserves==releases+1);
    assert(publications==removals); ++checks;
}
static void expect_cancel(void)
{
    assert(kd_down_write_killable(&sem)==-EINTR);
    assert(!phase_owned && !sem.gate.owned && reserves==releases);
    assert(publications==removals); acquiring=false; ++checks;
}
int main(void)
{
    reset(); expect_success();
    assert(attempts==1 && reserves==1 && !pauses && !wait_calls && !signal_checks && !resched_checks);
    release_writer();

    reset(); fatal=true; resched_at=1; expect_success();
    assert(attempts==1 && !signal_checks && !resched_checks && !wait_calls); release_writer();

    reset(); sem.admission=-1; available_at=16384; expect_success();
    assert(attempts==16384 && pauses==16383 && !wait_calls); release_writer();

    reset(); sem.admission=-1; release_at=SCHEDULE; expect_success();
    assert(attempts==16387 && pauses==16384 && wait_calls==1 && publications==1 && schedules==1);
    release_writer();

    reset(); sem.admission=-1; release_at=BEFORE_WAIT; expect_success();
    assert(attempts==16385 && pauses==16384 && wait_calls==1 && !publications); release_writer();

    reset(); sem.admission=-1; release_at=AFTER_ENQUEUE; expect_success();
    assert(attempts==16386 && publications==1 && !schedules); release_writer();

    reset(); sem.admission=-1; resched_at=1; release_at=BEFORE_WAIT; expect_success();
    assert(attempts==2 && !pauses && wait_calls==1 && !signal_checks); release_writer();

    reset(); sem.admission=-1; fatal=true; expect_cancel();
    assert(attempts==3 && !pauses && wait_calls==1 && publications==1 && !reserves && !locks);

    reset(); sem.admission=-1; fatal_at=5; expect_cancel();
    assert(attempts==7 && pauses==4 && wait_calls==1 && !locks);

    reset(); sem.admission=-1; nonfatal=true; available_at=8; expect_success();
    assert(attempts==8 && pauses==7 && signal_checks==7 && !wait_calls); release_writer();

    reset(); sem.admission=-1; fatal_at=8; available_at=8; expect_success();
    assert(attempts==8 && fatal && signal_checks==7 && !wait_calls); release_writer();

    reset(); sem.admission=-1; fatal=true; release_at=BEFORE_WAIT; expect_success();
    assert(attempts==2 && wait_calls==1 && !publications); release_writer();

    reset(); sem.admission=-1; fatal=true; release_at=AFTER_ENQUEUE; expect_success();
    assert(attempts==3 && wait_calls==1 && publications==1 && !schedules); release_writer();

    reset(); sem.reader_osq.tail=1; available_at=4; expect_success();
    assert(attempts==4 && pauses==3 && reserves==1); release_writer();

    reset(); sem.reader_osq.tail=1; resched_at=1; release_at=AFTER_ENQUEUE; expect_success();
    assert(attempts==3 && publications==1 && reserves==1); release_writer();

    reset(); cas_loss=true; available_at=2; expect_success();
    assert(attempts==2 && pauses==1 && reserves==1); release_writer();

    reset(); gate_cancel=true; expect_cancel();
    assert(reserves==1 && releases==1 && locks==1 && !unlocks && !drain_calls);

    reset(); sem.readers=1; drain_cancel=true; expect_cancel();
    assert(reserves==1 && releases==1 && locks==1 && unlocks==1 && sem.readers==1);
    assert(drain_calls==1 && phase_wakes==1);

    reset(); sem.readers=1; irq=true; expect_success();
    assert(drain_calls==2 && timer_rechecks==1 && !reader_wakes); release_writer();

    reset(); drain_cancel=true; expect_success();
    assert(drain_calls==1 && !sem.readers); release_writer();

    reset(); expect_success(); kd_downgrade_write(&sem);
    assert(!phase_owned && !sem.gate.owned && sem.readers==1 && releases==1 && unlocks==1);
    expect_success(); assert(reserves==2 && reader_wakes==1 && !sem.readers); release_writer();

    printf("PASS killable admission: %u deterministic production-function scenarios\n",checks);
    return 0;
}
