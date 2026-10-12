// SPDX-License-Identifier: GPL-2.0
/* Production notification protocol with deterministic scheduler interleavings.
 * Real barriers, RCU and scheduling are exercised separately in the VM. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint16_t u16;
struct task_struct { int state; } waiter;
struct rcuwait { struct task_struct *task; } wait_slot;
struct kd_mutex_node {
    union { u16 result; struct { u8 completed, locked; }; };
    struct rcuwait *wait;
} probe_node;
struct kd_mutex { u8 locked; int gate_wait; } gate;
enum { TASK_RUNNING, TASK_UNINTERRUPTIBLE };
#define KD_MUTEX_WAITER_PROCESSED 1
static unsigned int kd_mutex_spin_limit;
static unsigned int kd_mutex_result_parks, kd_mutex_result_wakes, kd_mutex_gate_parks;
static int preempt = 1, schedules, wakes, mode, resched, pauses;
static struct rcuwait *deferred[16];
static unsigned int deferred_count;
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define smp_load_acquire(p) __atomic_load_n(p, __ATOMIC_ACQUIRE)
#define smp_store_release(p, v) do { __atomic_store_n(p, v, __ATOMIC_RELEASE); \
    if (mode==6 && (void *)(p)==(void *)&probe_node.result) probe_node.wait=(void *)1; } while(0)
#define this_cpu_inc(x) (++(x))
#define smp_mb() __atomic_thread_fence(__ATOMIC_SEQ_CST)
static void preempt_enable(void) { assert(preempt==1); preempt--; }
static void preempt_disable(void) { assert(!preempt); preempt++; }
static bool need_resched(void) { return resched; }
static void cpu_relax(void) { pauses++; if (mode==4 && pauses==2) probe_node.locked=0; }
static long schedule_timeout(long timeout);
static void prepare_to_rcuwait(struct rcuwait *w);
static void set_current_state(int state);
static void finish_rcuwait(struct rcuwait *w) {
    assert(w==&wait_slot); w->task=NULL; waiter.state=TASK_RUNNING;
}
static bool rcuwait_active(struct rcuwait *w) { assert(w==&wait_slot); return w->task!=NULL; }
static int rcuwait_wake_up(struct rcuwait *w) {
    assert(w==&wait_slot && w->task==&waiter && !probe_node.locked);
    if (waiter.state==TASK_RUNNING) return 0;
    wakes++; waiter.state=TASK_RUNNING;
    return 1;
}
static bool waitqueue_active(int *q) { return *q; }
static void wake_up_all(int *q) { assert(q==&gate.gate_wait); *q=0; }
#define wait_event(q,condition) do { assert(preempt==0); (q)=1; kd_mutex_open_gate(&gate); assert(condition); } while(0)
static void kd_mutex_open_gate(struct kd_mutex *lock);
#include "parking.inc"
static void prepare_to_rcuwait(struct rcuwait *w) {
    assert(w==&wait_slot && !w->task); w->task=&waiter;
    if (mode==3) kd_mutex_publish_result(&probe_node, true);
}
static void set_current_state(int state) {
    waiter.state=state;
    if (mode==5) kd_mutex_publish_result(&probe_node, true);
}
static long schedule_timeout(long timeout) {
    assert(!preempt && timeout==1); schedules++;
    if (mode==2 && schedules==1) { waiter.state=TASK_RUNNING; return 0; }
    if (mode==7) {
        /* Completion is visible but its wake is deliberately withheld. The
         * timed recheck must let this caller run before a batch can flush. */
        kd_mutex_defer_result(&probe_node, deferred, &deferred_count);
        assert(deferred_count==1 && !wakes);
        waiter.state=TASK_RUNNING;
        return 0;
    }
    kd_mutex_publish_result(&probe_node, true);
    assert(waiter.state==TASK_RUNNING);
    return 0;
}
static void reset(int m) {
    mode=m; preempt=1; schedules=wakes=pauses=resched=0; deferred_count=0;
    waiter.state=TASK_RUNNING; wait_slot.task=NULL;
    probe_node.result=1U << 8; probe_node.wait=&wait_slot; kd_mutex_spin_limit=0;
}
int main(void) {
    reset(0); kd_mutex_publish_result(&probe_node, true); kd_mutex_park_result(&probe_node);
    assert(!schedules && !wakes && preempt==1 && waiter.state==TASK_RUNNING);
    reset(1); kd_mutex_wait_for_result(&probe_node);
    assert(schedules==1 && wakes==1 && probe_node.completed && preempt==1);
    reset(2); kd_mutex_wait_for_result(&probe_node);
    assert(schedules==2 && wakes==1 && !probe_node.locked && !wait_slot.task);
    reset(3); kd_mutex_park_result(&probe_node); /* completion before state store */
    assert(!schedules && !wakes && waiter.state==TASK_RUNNING && !wait_slot.task);
    reset(5); kd_mutex_park_result(&probe_node); /* completion before condition read */
    assert(!schedules && wakes==1 && waiter.state==TASK_RUNNING && !wait_slot.task);
    reset(6); kd_mutex_park_result(&probe_node); /* publisher cannot reread recycled probe_node */
    assert(schedules==1 && wakes==1 && probe_node.wait==(void *)1 && !wait_slot.task);
    reset(7); kd_mutex_wait_for_result(&probe_node);
    assert(schedules==1 && !wakes && probe_node.completed && !wait_slot.task);
    kd_mutex_flush_wakes(deferred, &deferred_count);
    assert(!deferred_count && !wakes);
    reset(4); kd_mutex_spin_limit=64; kd_mutex_wait_for_result(&probe_node);
    assert(pauses==2 && !schedules && !wakes);
    for (unsigned int limit=1; limit<=4096; limit*=64) {
        reset(1); kd_mutex_spin_limit=limit; kd_mutex_wait_for_result(&probe_node);
        assert(pauses==(int)limit && schedules==1 && wakes==1 && preempt==1);
    }
    reset(1); kd_mutex_spin_limit=64; resched=1; kd_mutex_wait_for_result(&probe_node);
    assert(!pauses && schedules==1);
    gate.locked=1; kd_mutex_spin_limit=0; kd_mutex_wait_gate(&gate);
    assert(!gate.locked && !gate.gate_wait && preempt==1);
    reset(1);
    struct rcuwait *batch[16]; unsigned int count=0;
    prepare_to_rcuwait(&wait_slot); set_current_state(TASK_UNINTERRUPTIBLE);
    for (int i=0; i<15; i++) {
        probe_node.result=1U<<8;
        kd_mutex_defer_result(&probe_node,batch,&count);
        assert(count==(unsigned int)i+1 && !probe_node.locked && !wakes);
    }
    probe_node.result=1U<<8;
    kd_mutex_defer_result(&probe_node,batch,&count);
    assert(!count && wakes==1); finish_rcuwait(&wait_slot);
    reset(1); count=0; prepare_to_rcuwait(&wait_slot); set_current_state(TASK_UNINTERRUPTIBLE);
    kd_mutex_defer_result(&probe_node,batch,&count);
    assert(count==1 && !wakes); kd_mutex_flush_wakes(batch,&count);
    assert(!count && wakes==1); finish_rcuwait(&wait_slot);
    puts("PASS: completion/sleep races, spurious wake, persistent wake slot, bounded spin, gate wake");
}
