/* SPDX-License-Identifier: GPL-2.0 */
/* Production writer functions with deterministic atomic/wait/gate primitives.
 * These are control-flow and exact reservation checks, not a scheduler or weak
 * memory model. Wait counters count boundary attempts, not Native membership. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define TASK_UNINTERRUPTIBLE 1U
#define TASK_INTERRUPTIBLE 2U
#define TASK_KILLABLE 4U
#define KD_RWSEM_LOCAL_WRITER (-1L)
#define ERESTARTSYS 512
#define BUG_ON(x) assert(!(x))
#define READ_ONCE(x) (x)
#define current ((void *)0x1000UL)
struct kd_mutex { bool owned; };
struct kd_rwsem {
    struct kd_mutex gate;
    long admission, readers;
    unsigned int prepared_writes;
    struct { int tail; } reader_osq;
    int phase_wait, reader_drain;
};
static struct kd_rwsem sem;
static unsigned int attempts, reserves, releases, pauses, resched_checks, signal_checks;
static unsigned int locks, unlocks, scoped_locks, wait_calls, drain_waits, wake_phase, wake_reader;
static unsigned int available_at, fatal_at, nonfatal_at, resched_at, drain_empty_at, drain_reads;
static unsigned int wait_attempts, wait_exits, schedules, scenarios;
static bool phase_owned, fatal, nonfatal, irq, gate_cancel, try_busy, cas_loss, in_wait;
static bool drain_mode, drain_cancel;
enum boundary { NONE, BEFORE_WAIT, AFTER_PREPARE, SCHEDULE };
static enum boundary release_at;
static void kd_up_read(struct kd_rwsem *s);

static void available(void) { assert(!phase_owned); sem.admission=0; sem.reader_osq.tail=0; }
static long atomic_long_read(long *p)
{
    if (p==&sem.readers) return *p;
    assert(p==&sem.admission);
    if (!phase_owned) {
        assert(++attempts<20000);
        if (available_at==attempts) available();
        if (fatal_at==attempts) fatal=true;
        if (nonfatal_at==attempts) nonfatal=true;
    }
    return *p;
}
static long atomic_long_read_acquire(long *p)
{
    assert(p==&sem.readers);
    ++drain_reads; drain_mode=true;
    if (drain_empty_at==drain_reads) { assert(*p==1); kd_up_read(&sem); }
    return *p;
}
static int atomic_read(int *p) { assert(p==&sem.reader_osq.tail); return *p; }
static long atomic_long_cmpxchg(long *p,long old,long value)
{
    assert(p==&sem.admission && old==0 && value==-1 && !phase_owned);
    if(cas_loss) { *p=-1; cas_loss=false; }
    long seen=*p;
    if(seen==old) { *p=value; phase_owned=true; ++reserves; }
    return seen;
}
static bool atomic_long_try_cmpxchg(long *p,long *old,long value)
{
    assert(p==&sem.admission && value==*old+1 && !phase_owned);
    if(*p!=*old) { *old=*p; return false; }
    *p=value; return true;
}
static long atomic_long_xchg(long *p,long value)
{
    assert(p==&sem.admission && value==0 && phase_owned && !sem.gate.owned);
    long old=*p; *p=value; phase_owned=false; ++releases; return old;
}
static void atomic_long_inc(long *p) { assert(p==&sem.readers); ++*p; }
static bool atomic_long_dec_and_test(long *p) { assert(p==&sem.readers && *p>0); return --*p==0; }
static bool need_resched(void)
{
    ++resched_checks;
    return resched_at && (drain_mode?drain_reads:attempts)>=resched_at;
}
static bool signal_pending(void *task)
{ assert(task==current); ++signal_checks; return fatal||nonfatal; }
static bool signal_pending_state(unsigned int state,void *task)
{ assert(task==current); return state==TASK_INTERRUPTIBLE?(fatal||nonfatal):state==TASK_KILLABLE&&fatal; }
static void cpu_relax(void) { assert(!in_wait); ++pauses; }
static void might_sleep(void) { assert(!phase_owned && !sem.gate.owned); }
static bool irqs_disabled(void) { return irq; }
static bool in_atomic(void) { return irq; }
static void kd_rwsem_wake(int *q)
{
    if(q==&sem.phase_wait) { assert(!phase_owned && !sem.gate.owned); ++wake_phase; }
    else { assert(q==&sem.reader_drain); ++wake_reader; }
}
static int gate_lock(struct kd_mutex *g,unsigned int state,bool scoped)
{
    assert(g==&sem.gate && !g->owned && !in_wait);
    assert(phase_owned==!!sem.prepared_writes);
    assert(scoped==(state!=TASK_UNINTERRUPTIBLE));
    ++locks; scoped_locks+=scoped;
    if(gate_cancel) { assert(state!=TASK_UNINTERRUPTIBLE); return -EINTR; }
    g->owned=true; return 0;
}
static void kd_mutex_local_lock(struct kd_mutex *g) { assert(!gate_lock(g,TASK_UNINTERRUPTIBLE,false)); }
static int kd_mutex_local_lock_signal(struct kd_mutex *g,unsigned int s) { return gate_lock(g,s,true); }
static void kd_mutex_local_unlock(struct kd_mutex *g)
{ assert(g==&sem.gate && g->owned && !in_wait); g->owned=false; ++unlocks; }
static bool kd_mutex_trylock(struct kd_mutex *g)
{ assert(g==&sem.gate && phase_owned); if(try_busy) return false; assert(!g->owned); g->owned=true; return true; }
static bool kd_origin_mutex_owned(struct kd_mutex *g,void *task)
{ assert(g==&sem.gate && task==current); return g->owned; }
static void wait_begin(int *q)
{
    assert(!in_wait);
    if(q==&sem.phase_wait) {
        ++wait_calls; assert(!phase_owned);
        assert(sem.gate.owned==!sem.prepared_writes);
        if(release_at==BEFORE_WAIT) available();
    } else { assert(q==&sem.reader_drain && phase_owned && sem.gate.owned); ++drain_waits; }
}
static void wait_prepare(int *q)
{
    assert(!in_wait); in_wait=true; ++wait_attempts;
    if(q==&sem.phase_wait && release_at==AFTER_PREPARE) available();
}
static void wait_schedule(int *q)
{
    assert(in_wait); ++schedules;
    if(q==&sem.phase_wait) { assert(release_at==SCHEDULE); available(); }
    else { assert(sem.readers==1); kd_up_read(&sem); }
}
#define modeled_wait(queue,condition,state,timed) ({ \
    long result=(timed)?1:0; wait_begin(&(queue)); \
    if(!(condition)) { \
        wait_prepare(&(queue)); \
        if(!(condition)) { \
            if(signal_pending_state(state,current) || ((timed)&&drain_cancel)) \
                result=-ERESTARTSYS; \
            else { wait_schedule(&(queue)); \
                if((timed)&&irq) result=0; else assert(condition); } \
        } \
        in_wait=false; ++wait_exits; \
    } result; \
})
#define wait_event(queue,condition) ((void)modeled_wait(queue,condition,TASK_UNINTERRUPTIBLE,false))
#define wait_event_interruptible(queue,condition) modeled_wait(queue,condition,TASK_INTERRUPTIBLE,false)
#define wait_event_killable(queue,condition) modeled_wait(queue,condition,TASK_KILLABLE,false)
#define wait_event_timeout(queue,condition,ticks) modeled_wait(queue,condition,TASK_UNINTERRUPTIBLE,true)
#define wait_event_interruptible_timeout(queue,condition,ticks) modeled_wait(queue,condition,TASK_INTERRUPTIBLE,true)
#define wait_event_killable_timeout(queue,condition,ticks) modeled_wait(queue,condition,TASK_KILLABLE,true)
#include "rwsem_writer_production.h"

static void reset(bool prepared)
{
    assert(!phase_owned && !sem.gate.owned && wait_attempts==wait_exits);
    memset(&sem,0,sizeof(sem)); sem.prepared_writes=prepared;
    attempts=reserves=releases=pauses=resched_checks=signal_checks=0;
    locks=unlocks=scoped_locks=wait_calls=drain_waits=wake_phase=wake_reader=0;
    available_at=fatal_at=nonfatal_at=resched_at=drain_empty_at=drain_reads=0;
    wait_attempts=wait_exits=schedules=0;
    phase_owned=fatal=nonfatal=irq=gate_cancel=try_busy=cas_loss=in_wait=false;
    drain_mode=drain_cancel=false; release_at=NONE;
}
static int acquire(unsigned int state)
{
    if(state==TASK_INTERRUPTIBLE) return kd_down_write_interruptible(&sem);
    if(state==TASK_KILLABLE) return kd_down_write_killable(&sem);
    kd_down_write(&sem); return 0;
}
static void success(unsigned int state)
{
    assert(!acquire(state)); assert(phase_owned && sem.gate.owned && !sem.readers);
    assert(reserves==releases+1 && wait_attempts==wait_exits); ++scenarios;
}
static void release_writer(void)
{ kd_mutex_local_unlock(&sem.gate); kd_rwsem_release_local(&sem); }
static void cancelled(unsigned int state)
{
    assert(acquire(state)==-EINTR);
    assert(!phase_owned && !sem.gate.owned && reserves==releases);
    assert(wait_attempts==wait_exits); ++scenarios;
}
int main(void)
{
    const unsigned int states[]={TASK_UNINTERRUPTIBLE,TASK_INTERRUPTIBLE,TASK_KILLABLE};
    for(unsigned int prepared=0;prepared<2;++prepared) {
        for(unsigned int i=0;i<3;++i) {
            reset(prepared); fatal=true; resched_at=1; success(states[i]);
            assert(attempts==1 && !pauses && !resched_checks && !signal_checks && !wait_calls && !drain_waits);
            assert(scoped_locks==(i!=0)); release_writer();
            reset(prepared); sem.admission=-1; available_at=16384; success(states[i]);
            assert(attempts==16384 && pauses==16383 && !wait_calls); release_writer();
            for(unsigned int b=BEFORE_WAIT;b<=SCHEDULE;++b) {
                reset(prepared); sem.admission=-1; release_at=b; success(states[i]);
                assert(pauses==16384 && wait_calls==1 && attempts==16384+b);
                release_writer();
            }
            reset(prepared); sem.reader_osq.tail=1; available_at=4; success(states[i]);
            assert(attempts==4 && pauses==3); release_writer();
            reset(prepared); sem.readers=1; drain_empty_at=16384; success(states[i]);
            assert(drain_reads==16384 && pauses==16383 && !drain_waits); release_writer();
            reset(prepared); sem.readers=1; irq=true; success(states[i]);
            assert(pauses==16384 && drain_waits==2 && !wake_reader && schedules==1); release_writer();
        }
        for(unsigned int i=1;i<3;++i) {
            reset(prepared); sem.admission=-1; fatal=true; cancelled(states[i]);
            assert(attempts==3 && !pauses && !reserves && unlocks==!prepared);
            reset(prepared); gate_cancel=true; cancelled(states[i]);
            assert(reserves==prepared && releases==prepared && !unlocks);
            reset(prepared); sem.readers=1; fatal=true; cancelled(states[i]);
            assert(reserves==1 && releases==1 && unlocks==1 && !pauses);
            reset(prepared); sem.admission=-1; fatal=true; release_at=AFTER_PREPARE; success(states[i]);
            assert(attempts==3 && !pauses && wait_attempts==1 && !schedules); release_writer();
        }
        reset(prepared); sem.admission=-1; nonfatal=true; release_at=SCHEDULE; success(TASK_KILLABLE);
        assert(attempts==4 && !pauses && signal_checks==1 && schedules==1); release_writer();
        reset(prepared); sem.admission=-1; nonfatal_at=5; release_at=SCHEDULE; success(TASK_KILLABLE);
        assert(attempts==8 && pauses==4 && signal_checks==5); release_writer();
        reset(prepared); sem.admission=-1; nonfatal=true; cancelled(TASK_INTERRUPTIBLE);
        assert(!pauses && attempts==3);
        reset(prepared); sem.admission=-1; resched_at=1; release_at=BEFORE_WAIT; success(TASK_KILLABLE);
        assert(attempts==2 && !pauses && !signal_checks); release_writer();
        reset(prepared); sem.readers=1; nonfatal=true; success(TASK_KILLABLE);
        assert(!pauses && drain_waits==1 && schedules==1 && wake_reader==1); release_writer();
        reset(prepared); sem.readers=1; resched_at=1; success(TASK_UNINTERRUPTIBLE);
        assert(!pauses && drain_waits==1); release_writer();
    }
    /* A nonblocking phase-first try can overlap the gate-first owner's gap.
     * It relinquishes its own reservation immediately when that gate is busy. */
    reset(false); try_busy=true; assert(!kd_down_write_trylock(&sem));
    assert(!phase_owned && releases==1 && !sem.gate.owned); ++scenarios;
    reset(false); sem.readers=1; assert(!kd_down_write_trylock(&sem));
    assert(releases==1 && unlocks==1 && !phase_owned); ++scenarios;
    reset(false); assert(kd_down_write_trylock(&sem)); ++scenarios;
    kd_downgrade_write(&sem);
    assert(sem.readers==1 && !phase_owned && !sem.gate.owned && releases==1);
    drain_empty_at=2; drain_reads=0; drain_mode=false; success(TASK_KILLABLE); release_writer();
    /* Direct internal delegation must obey the object-wide prepared protocol. */
    reset(false);
    pid_t child=fork(); assert(child>=0);
    if(!child) { kd_rwsem_delegate_enter(&sem); _exit(0); }
    int status; assert(waitpid(child,&status,0)==child);
    assert(WIFSIGNALED(status) && WTERMSIG(status)==SIGABRT); ++scenarios;
    reset(true); kd_rwsem_delegate_enter(&sem);
    assert(sem.admission==1 && !sem.gate.owned && !reserves); sem.admission=0; ++scenarios;
    printf("PASS writer queue: %u scenarios; deterministic primitives only\n",scenarios);
    return 0;
}
