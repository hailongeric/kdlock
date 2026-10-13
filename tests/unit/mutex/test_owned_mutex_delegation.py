"""Guest-only production snapshot/retirement/early-release transitions.

The extracted combiner is driven by explicit execution outcomes. The core has
its own production fixture; this one checks the FIFO presented to that core and
poisons completed packets to catch access after publication. No timing claims.
"""
import argparse
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from source_text import ROOT
from test_spin_shadow import definition


PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define BUG_ON(x) assert(!(x))
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x,v) (*(volatile __typeof__(x) *)&(x)=(v))
#define noinline __attribute__((noinline))
#define notrace
#define this_cpu_inc(x) (++(x))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
static void (*lock_action)(void);
#define raw_spin_lock_irqsave(p,f) do { assert(!*(p)); *(p)=1; (f)=0; if(lock_action) lock_action(); } while(0)
#define raw_spin_unlock_irqrestore(p,f) do { assert(*(p)); *(p)=0; (void)(f); } while(0)
#define atomic_long_read(p) (*(p))
#define KDLOCK_SPIN_BATCH 3
#define KD_OWNED_MUTEX_FLAG_WAITERS 1UL
#define KD_OWNED_MUTEX_FLAG_HANDOFF 2UL
#define KD_EXEC_LOCK_QUEUE_OWNER 1
#define KD_EXE_NATIVE_DONE 5
#define KD_EXE_NO_RUN 9
#define EINVAL 22
struct task_struct { int id; } owner __attribute__((aligned(8)))={1}, tasks[8];
static struct task_struct *current=&owner;
struct list_head { struct list_head *next,*prev; };
static struct list_head *refill_source;
static int refills,flushes,last_refill_flush;
static void INIT_LIST_HEAD(struct list_head *h) { h->next=h->prev=h; }
static bool list_empty(const struct list_head *h) { return h->next==h; }
static void list_add_tail(struct list_head *n,struct list_head *h) {
 n->prev=h->prev; n->next=h; h->prev->next=n; h->prev=n;
}
static void list_del_init(struct list_head *n) {
 n->next->prev=n->prev; n->prev->next=n->next; INIT_LIST_HEAD(n);
}
static void list_splice_init(struct list_head *from,struct list_head *to) {
 if(list_empty(from)) return;
 if(from==refill_source) {
  assert(list_empty(to)); assert(flushes>last_refill_flush);
  last_refill_flush=flushes;refills++;
 }
 struct list_head *first=from->next,*last=from->prev,*next=to->next;
 first->prev=to; to->next=first; last->next=next; next->prev=last;
 INIT_LIST_HEAD(from);
}
#define list_first_entry(h,t,m) container_of((h)->next,t,m)
enum { KD_OWNED_MUTEX_SELF, KD_OWNED_MUTEX_DELEGATE };
enum { KD_OWNED_MUTEX_QUEUED, KD_OWNED_MUTEX_GRANTED };
struct kd_owned_mutex_waiter {
 struct list_head list; struct task_struct *task; unsigned int kind,state,*outcome;
};
struct kd_mutex { unsigned long owner; int wait_lock; struct list_head wait_list; };
struct kd_owned_mutex_node { struct kd_owned_mutex_waiter waiter; unsigned int id; };
struct kd_exec_frame {
 bool owned_mutex; unsigned long outer_lock_addr;
 unsigned int outer_lock_index; int jit_lock_kind[1]; void *jit_lock_node[1];
};
struct kd_exec_outer_unlock {
 int (*release)(struct kd_exec_frame *,struct kd_exec_outer_unlock *); bool released;
};
struct kd_exe_info; struct rcuwait;
static unsigned long kd_owned_mutex_batches,kd_owned_mutex_refusals,kd_owned_mutex_bodies,kd_owned_mutex_early_releases;
static bool resched,owned_mutex_refill;
static bool need_resched(void) { return resched; }
static bool kd_owned_mutex_owned(struct kd_mutex *lock,struct task_struct *task) {
 return (lock->owner&~7UL)==(unsigned long)task;
}
static int released,executed,completed,scenario;
static unsigned int release_order[8], release_count;
static struct kd_owned_mutex_node nodes[8];
static struct kd_mutex *arrival_lock;
static unsigned int arrival_next,arrival_end;
static void kd_owned_mutex_flush_wakes(struct rcuwait **wake,unsigned int *count) {
 (void)wake; flushes++;
 if(*count && arrival_next<arrival_end) {
  assert(arrival_lock && kd_owned_mutex_owned(arrival_lock,current));
  list_add_tail(&nodes[arrival_next++].waiter.list,&arrival_lock->wait_list);
 }
 *count=0;
}
static void kd_owned_mutex_release(struct kd_mutex *lock) {
 assert(kd_owned_mutex_owned(lock,current)); assert(!lock->wait_lock);
 release_count=0;
 for(struct list_head *p=lock->wait_list.next;p!=&lock->wait_list;p=p->next) {
  struct kd_owned_mutex_node *n=container_of(p,struct kd_owned_mutex_node,waiter.list);
  release_order[release_count++]=n->id;
 }
 released++; lock->owner=0;
}
static void kd_owned_mutex_defer(struct kd_owned_mutex_node *node,
                                struct rcuwait **wake,unsigned int *count) {
 (void)wake;(*count)++;
 assert(list_empty(&node->waiter.list));
 completed++;
 /* Publication permits immediate packet reuse. The combiner must retain
  * every needed successor and retirement fact outside this packet. */
 memset(node,0xaf,sizeof(*node));
}
'''

EXECUTE = r'''
static int kd_owned_mutex_execute(struct kd_owned_mutex_node *node,
                                  struct kd_owned_mutex_batch *batch) {
 assert(kd_owned_mutex_owned(batch->lock,current));
 executed++;
 if(scenario==1) return KD_EXE_NO_RUN;
 if(scenario==8 && node->id==1) {
  list_add_tail(&nodes[3].waiter.list,&batch->lock->wait_list);
  return KD_EXE_NO_RUN;
 }
 if(scenario==9 && node->id==1) {
  kd_owned_mutex_retire_current(batch);
  kd_owned_mutex_defer(node,batch->wake,&batch->wake_count);
  list_add_tail(&nodes[3].waiter.list,&batch->lock->wait_list);
  return KD_EXE_NATIVE_DONE;
 }
 if(scenario==2 || scenario==3 || (scenario==10 && node->id==1)) {
  struct kd_exec_frame frame={
   .owned_mutex=true,.outer_lock_addr=(unsigned long)batch->lock,
   .jit_lock_kind={KD_EXEC_LOCK_QUEUE_OWNER},.jit_lock_node={batch->lock},
  };
  if(scenario==3) {
   kd_owned_mutex_retire_current(batch);
   kd_owned_mutex_defer(node,batch->wake,&batch->wake_count);
  }
  if(scenario==10)
   list_add_tail(&nodes[3].waiter.list,&batch->lock->wait_list);
  assert(kd_owned_mutex_release_outer(&frame,&batch->outer)==0);
  batch->outer.released=true;
  return scenario==3 ? KD_EXE_NATIVE_DONE : 0;
 }
 if(scenario==4) {
  /* A newer public SELF requests handoff after one older body commits. */
  list_add_tail(&nodes[5].waiter.list,&batch->lock->wait_list);
  batch->lock->owner|=KD_OWNED_MUTEX_FLAG_HANDOFF;
 }
 if(scenario==5) resched=true;
 return 0;
}
'''

CASES = r'''
static void setup(struct kd_mutex *lock,struct kd_owned_mutex_batch *batch,int count) {
 memset(lock,0,sizeof(*lock)); memset(batch,0,sizeof(*batch));
 INIT_LIST_HEAD(&lock->wait_list); INIT_LIST_HEAD(&batch->pending);
 lock->owner=(unsigned long)current|KD_OWNED_MUTEX_FLAG_WAITERS;
 batch->lock=lock; batch->outer.release=kd_owned_mutex_release_outer;
 memset(nodes,0,sizeof(nodes));
 for(int i=0;i<8;i++) {
  INIT_LIST_HEAD(&nodes[i].waiter.list); nodes[i].id=i;
  nodes[i].waiter.task=&tasks[i]; nodes[i].waiter.kind=KD_OWNED_MUTEX_DELEGATE;
 }
 for(int i=0;i<count;i++) list_add_tail(&nodes[i].waiter.list,&batch->pending);
 nodes[5].waiter.kind=KD_OWNED_MUTEX_SELF;
 released=executed=completed=flushes=scenario=0; release_count=0;resched=false;
 owned_mutex_refill=false;refills=last_refill_flush=0;refill_source=&lock->wait_list;
 arrival_lock=lock;arrival_next=arrival_end=0;lock_action=NULL;
}
static void check_order(unsigned int count,const unsigned int *order) {
 assert(released==1 && release_count==count);
 for(unsigned int i=0;i<count;i++) assert(release_order[i]==order[i]);
}
static void handoff_during_refill(void) {
 lock_action=NULL;arrival_lock->owner|=KD_OWNED_MUTEX_FLAG_HANDOFF;
}
static void reschedule_during_refill(void) { lock_action=NULL;resched=true; }
int main(void) {
 struct kd_mutex lock; struct kd_owned_mutex_batch batch;
 const unsigned int all[]={0,1,2,5},suffix[]={1,2,5},self_suffix[]={1,2};
 setup(&lock,&batch,3); scenario=1;
 list_add_tail(&nodes[5].waiter.list,&lock.wait_list);
 kd_owned_mutex_run_batch(&batch);
 assert(executed==1 && completed==0 && batch.outer.released);
 check_order(4,all); /* refusal keeps current ahead of later public arrivals */

 setup(&lock,&batch,3); scenario=4;
 kd_owned_mutex_run_batch(&batch);
 assert(executed==1 && completed==1);
 check_order(3,suffix); /* newer SELF handoff cannot bypass older suffix */

 setup(&lock,&batch,3); nodes[1].waiter.kind=KD_OWNED_MUTEX_SELF;
 kd_owned_mutex_run_batch(&batch);
 assert(executed==1 && completed==1);
 check_order(2,self_suffix); /* a batch cannot cross a SELF boundary */

 setup(&lock,&batch,5);
 kd_owned_mutex_run_batch(&batch);
 assert(executed==KDLOCK_SPIN_BATCH && completed==KDLOCK_SPIN_BATCH);
 {const unsigned int capped[]={3,4};check_order(2,capped);}

 for(int mode=2;mode<=3;mode++) {
  setup(&lock,&batch,3); scenario=mode;
  list_add_tail(&nodes[5].waiter.list,&lock.wait_list);
  kd_owned_mutex_run_batch(&batch);
  assert(executed==1 && completed==1 && batch.outer.released);
  check_order(3,suffix); /* early A release and FULL ACK never reacquire A */
 }

 setup(&lock,&batch,3); scenario=5;
 kd_owned_mutex_run_batch(&batch);
 assert(executed==1 && completed==1);
 check_order(2,self_suffix);

 setup(&lock,&batch,3);lock.owner|=KD_OWNED_MUTEX_FLAG_HANDOFF;
 kd_owned_mutex_run_batch(&batch);
 assert(executed==0 && completed==0);
 {const unsigned int untouched[]={0,1,2};check_order(3,untouched);}

 setup(&lock,&batch,1);kd_owned_mutex_run_batch(&batch);
 assert(executed==1 && completed==1 && list_empty(&batch.pending));
 check_order(0,NULL);
 puts("PASS production owned FIFO: refusal, cap, SELF, HANDOFF, reschedule, COMPLETE reuse, FULL reuse, early release");

 /* The default finite snapshot ignores arrivals even when a refill could
  * execute them safely. Enabling the candidate changes only this boundary. */
 for(int enabled=0;enabled<=1;enabled++) {
  setup(&lock,&batch,1);owned_mutex_refill=enabled;
  list_add_tail(&nodes[1].waiter.list,&lock.wait_list);
  kd_owned_mutex_run_batch(&batch);
  assert(executed==1+enabled && completed==1+enabled && refills==enabled);
  if(enabled) check_order(0,NULL);
  else {const unsigned int later[]={1};check_order(1,later);}
 }

 /* Each flushed result makes the next producer visible. The body quota
  * spans all snapshots, and final wakeups remain queued for the next owner. */
 setup(&lock,&batch,1);owned_mutex_refill=true;arrival_next=1;arrival_end=4;
 kd_owned_mutex_run_batch(&batch);
 assert(executed==KDLOCK_SPIN_BATCH && completed==KDLOCK_SPIN_BATCH && refills==2);
 {const unsigned int later[]={3};check_order(1,later);}

 /* A SELF at the public head vetoes refill; a SELF inside a refilled
  * snapshot terminates its delegated prefix without bypassing that request. */
 for(int first_self=1;first_self<=2;first_self++) {
  setup(&lock,&batch,1);owned_mutex_refill=true;
  for(int i=1;i<=3;i++) list_add_tail(&nodes[i].waiter.list,&lock.wait_list);
  nodes[first_self].waiter.kind=KD_OWNED_MUTEX_SELF;
  kd_owned_mutex_run_batch(&batch);
  assert(executed==first_self && completed==first_self && refills==first_self-1);
  if(first_self==1) {const unsigned int tail[]={1,2,3};check_order(3,tail);}
  else {const unsigned int tail[]={2,3};check_order(2,tail);}
 }

 /* A request can ask for HANDOFF after the outside-lock check. The
  * under-lock recheck must leave the public FIFO untouched. */
 for(int stop=0;stop<2;stop++) {
  setup(&lock,&batch,1);owned_mutex_refill=true;
  list_add_tail(&nodes[1].waiter.list,&lock.wait_list);
  lock_action=stop ? reschedule_during_refill : handoff_during_refill;
  kd_owned_mutex_run_batch(&batch);
  assert(executed==1 && completed==1 && refills==0);
  {const unsigned int tail[]={1};check_order(1,tail);}
 }

 /* Refused and FULL requests never trigger a refill; unstarted suffixes
  * rejoin before arrivals even when the previous snapshot was exhausted. */
 for(int mode=8;mode<=10;mode++) {
  setup(&lock,&batch,1);owned_mutex_refill=true;scenario=mode;
  list_add_tail(&nodes[1].waiter.list,&lock.wait_list);
  list_add_tail(&nodes[2].waiter.list,&lock.wait_list);
  kd_owned_mutex_run_batch(&batch);
  assert(executed==2 && completed==(mode==8 ? 1 : 2) && refills==1);
  if(mode==8) {const unsigned int tail[]={1,2,3};check_order(3,tail);}
  else {const unsigned int tail[]={2,3};check_order(2,tail);}
 }

 /* At quota, and after release, the helper must not even inspect a FIFO.
  * The released object's address deliberately cannot be dereferenced. */
 setup(&lock,&batch,0);owned_mutex_refill=true;
 list_add_tail(&nodes[0].waiter.list,&lock.wait_list);
 assert(!kd_owned_mutex_refill_batch(&batch,KDLOCK_SPIN_BATCH));
 assert(!refills && !flushes && !list_empty(&lock.wait_list));
 batch.outer.released=true;batch.lock=(void *)1;
 assert(!kd_owned_mutex_refill_batch(&batch,0));
 assert(!refills && !flushes);
 puts("PASS production optional FIFO refill: off gate, quota across snapshots, wake-time arrivals, SELF cutoff, locked HANDOFF/reschedule, refusal/FULL/early stop");
}
'''


def production(source):
    value = definition(source, 'struct kd_owned_mutex_batch {')+';\n'
    for marker in ('static void kd_owned_mutex_retire_current(struct kd_owned_mutex_batch *batch)',
                   'static void kd_owned_mutex_rejoin(struct kd_owned_mutex_batch *batch)',
                   'static int kd_owned_mutex_release_outer(struct kd_exec_frame *frame,'):
        value += definition(source, marker)
    value += EXECUTE
    value += definition(source, 'static bool kd_owned_mutex_refill_batch(struct kd_owned_mutex_batch *batch,')
    value += 'static __attribute__((noipa)) noinline notrace void\n'
    value += definition(source, 'kd_owned_mutex_run_batch(struct kd_owned_mutex_batch *batch)')
    return PREFIX+value+CASES


NOTIFICATION_PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
struct rcuwait { int active, wakes; } waits[16];
struct kd_owned_mutex_node { struct rcuwait *wait; u32 outcome; } nodes[16];
static struct kd_owned_mutex_node *publishing;
static int publications, barriers, last_publish_barrier, reads;
static u32 expected_outcome;
static unsigned long kd_owned_mutex_wakes,kd_owned_mutex_parks;
static unsigned int owned_mutex_spin_limit;
static int pin=1,prepares,finishes,sleeps,relaxes;
static void (*state_action)(void),(*sleep_action)(void);
#define this_cpu_inc(x) (++(x))
#define TASK_UNINTERRUPTIBLE 2
static bool need_resched(void) { return false; }
static void cpu_relax(void) { relaxes++; }
static void preempt_enable(void) { assert(pin==1);pin=0; }
static void preempt_disable(void) { assert(!pin);pin=1; }
static void prepare_to_rcuwait(struct rcuwait *wait) { prepares++;wait->active=1; }
static void finish_rcuwait(struct rcuwait *wait) { finishes++;wait->active=0; }
static void set_current_state(int state) {
 assert(state==TASK_UNINTERRUPTIBLE && pin==1);
 if(state_action) { void (*action)(void)=state_action;state_action=NULL;action(); }
}
static void schedule_timeout(int duration) {
 assert(!pin && duration==1 && sleep_action);sleeps++;sleep_action();
}
static void publish(u32 *p,u32 value) {
 assert(publishing && p==&publishing->outcome && value==expected_outcome);
 *p=value; publications++; last_publish_barrier=barriers;
 /* The producer can reuse its packet immediately. Only the separately
  * captured rcuwait identity remains available to the old executor. */
 publishing->wait=(void *)1;
}
#define smp_store_release(p,v) publish((p),(v))
static u32 observe(const u32 *p) { reads++;return *p; }
#define smp_load_acquire(p) observe(p)
#define smp_mb() (++barriers)
static bool rcuwait_active(struct rcuwait *wait) {
 assert((uintptr_t)wait>=(uintptr_t)waits && (uintptr_t)wait<(uintptr_t)(waits+16));
 return wait->active;
}
static bool rcuwait_wake_up(struct rcuwait *wait) {
 assert((uintptr_t)wait>=(uintptr_t)waits && (uintptr_t)wait<(uintptr_t)(waits+16));
 assert(barriers>last_publish_barrier);
 wait->wakes++; return true;
}
'''

NOTIFICATION_CASES = r'''
static void grant_before_schedule(void) { nodes[0].outcome=KD_OWNED_MUTEX_GRANTED; }
static void full_after_schedule(void) { nodes[0].outcome=KD_OWNED_MUTEX_FULL; }
int main(void) {
 struct rcuwait *wake[16]; unsigned int count=0;
 for(u32 state=KD_OWNED_MUTEX_QUEUED;state<=KD_OWNED_MUTEX_FULL;state++) {
  nodes[0].outcome=state; reads=0;
  assert(kd_owned_mutex_result_ready(&nodes[0])==(state!=KD_OWNED_MUTEX_QUEUED));
  assert(reads==1);
 }
 for(int complete=0;complete<=1;complete++) {
  publishing=&nodes[0]; publishing->wait=&waits[0];waits[0].active=1;
  expected_outcome=complete ? KD_OWNED_MUTEX_COMPLETE : KD_OWNED_MUTEX_FULL;
  kd_owned_mutex_notify(publishing,complete);
  assert(publishing->outcome==expected_outcome);
 }
 assert(publications==2 && waits[0].wakes==2 && kd_owned_mutex_wakes==2);
 for(int i=0;i<16;i++) {
  publishing=&nodes[i];publishing->wait=&waits[i];waits[i].active=1;
  expected_outcome=KD_OWNED_MUTEX_COMPLETE;
  kd_owned_mutex_defer(publishing,wake,&count);
  assert(publishing->outcome==KD_OWNED_MUTEX_COMPLETE);
  if(i<15) assert(count==(unsigned int)i+1);
 }
 assert(count==0 && publications==18 && kd_owned_mutex_wakes==18);
 for(int i=0;i<16;i++) assert(waits[i].wakes==(i==0 ? 3 : 1));
 nodes[0].wait=&waits[0];nodes[0].outcome=KD_OWNED_MUTEX_QUEUED;
 owned_mutex_spin_limit=0;state_action=grant_before_schedule;
 kd_owned_mutex_wait_result(&nodes[0]);
 assert(prepares==1 && finishes==1 && !sleeps && !waits[0].active && pin==1);
 nodes[0].outcome=KD_OWNED_MUTEX_QUEUED;owned_mutex_spin_limit=2;
 sleep_action=full_after_schedule;
 kd_owned_mutex_wait_result(&nodes[0]);
 assert(prepares==2 && finishes==2 && sleeps==1 && relaxes==2 && pin==1);
 assert(kd_owned_mutex_parks==1 && !waits[0].active);
 nodes[0].outcome=KD_OWNED_MUTEX_COMPLETE;
 kd_owned_mutex_wait_result(&nodes[0]);
 assert(prepares==2 && finishes==2 && sleeps==1);
 puts("PASS production owned single outcome: grant/COMPLETE/FULL acquire poll, notification reuse, deferred stable wake identity");
}
'''


def notifications(source):
    header = (ROOT/'include/kd_owned_mutex_internal.h').read_text()
    value = definition(header, 'enum kd_owned_mutex_waiter_state {')+';\n'
    for marker in ('static void kd_owned_mutex_flush_wakes(struct rcuwait **wake, unsigned int *count)',
                   'static void kd_owned_mutex_notify(struct kd_owned_mutex_node *node, bool complete)',
                   'static void kd_owned_mutex_defer(struct kd_owned_mutex_node *node,',
                   'static bool kd_owned_mutex_result_ready(struct kd_owned_mutex_node *node)',
                   'static void kd_owned_mutex_wait_result(struct kd_owned_mutex_node *node)'):
        value += definition(source, marker)
    return NOTIFICATION_PREFIX+value+NOTIFICATION_CASES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mutations', action='store_true')
    args = parser.parse_args()
    source = (ROOT/'kernel_module/owned_mutex/delegation.c').read_text()
    mutations = {
        'retire-before-notify': ('\t\t\tkd_owned_mutex_retire_current(batch);\n'
                                '\t\t\tthis_cpu_inc(kd_owned_mutex_bodies);',
                                '\t\t\tthis_cpu_inc(kd_owned_mutex_bodies);'),
        'honor-self-boundary': ('waiter->kind != KD_OWNED_MUTEX_DELEGATE ||', 'false ||'),
        'honor-handoff': ('(atomic_long_read(&batch->lock->owner) & KD_OWNED_MUTEX_FLAG_HANDOFF)', 'false'),
        'honor-cap': ('count >= KDLOCK_SPIN_BATCH || need_resched() ||',
                      'count >= 100 || need_resched() ||'),
        'honor-reschedule': ('|| need_resched() ||', '|| (need_resched() && false) ||'),
        'refusal-preserves-current': ('this_cpu_inc(kd_owned_mutex_refusals);\n\t\t\tbreak;',
                                     'this_cpu_inc(kd_owned_mutex_refusals);\n'
                                     '\t\t\tlist_del_init(&node->waiter.list);\n\t\t\tbreak;'),
        'full-retire-idempotent': ('if (batch->current_retired)\n\t\treturn;',
                                   'if (false)\n\t\treturn;'),
        'early-release-no-second-release': ('if (batch->outer.released) {', 'if (false) {'),
        'refill-off-gate': ('if (!owned_mutex_refill || batch->outer.released ||',
                            'if ((owned_mutex_refill && false) || batch->outer.released ||'),
        'refill-total-quota': ('count >= KDLOCK_SPIN_BATCH || need_resched())',
                               'count >= 100 || need_resched())'),
        'refill-wake-before-check': ('\tkd_owned_mutex_flush_wakes(batch->wake, &batch->wake_count);\n'
                                     '\traw_spin_lock_irqsave(&lock->wait_lock, flags);',
                                     '\traw_spin_lock_irqsave(&lock->wait_lock, flags);'),
        'refill-locked-handoff': ('(atomic_long_read(&lock->owner) & KD_OWNED_MUTEX_FLAG_HANDOFF) ||\n'
                                  '\t    list_empty(&lock->wait_list))',
                                  'false ||\n\t    list_empty(&lock->wait_list))'),
        'refill-locked-reschedule': ('if (need_resched() ||\n',
                                     'if ((need_resched() && false) ||\n'),
        'refill-self-head': ('if (first->kind != KD_OWNED_MUTEX_DELEGATE)\n\t\tgoto out;',
                             'if (first->kind != KD_OWNED_MUTEX_DELEGATE && false)\n\t\tgoto out;'),
        'refill-after-release': ('!owned_mutex_refill || batch->outer.released ||',
                                 '!owned_mutex_refill || false ||'),
        'stop-after-full': ('if (ret == KD_EXE_NATIVE_DONE)\n\t\t\tbreak;',
                            'if (false)\n\t\t\tbreak;'),
    }
    notification_mutations = {
        'notification-swaps-full-complete': (
            'complete ? KD_OWNED_MUTEX_COMPLETE :\n\t\t\t  KD_OWNED_MUTEX_FULL',
            'complete ? KD_OWNED_MUTEX_FULL :\n\t\t\t  KD_OWNED_MUTEX_COMPLETE'),
        'notification-ignores-granted': (
            'smp_load_acquire(&node->outcome) != KD_OWNED_MUTEX_QUEUED',
            'smp_load_acquire(&node->outcome) == KD_OWNED_MUTEX_COMPLETE'),
        'defer-captures-retired-packet': (
            'wake[(*count)++] = node->wait;\n\tsmp_store_release(&node->outcome, KD_OWNED_MUTEX_COMPLETE);',
            'smp_store_release(&node->outcome, KD_OWNED_MUTEX_COMPLETE);\n\twake[(*count)++] = node->wait;'),
        'notify-touches-retired-packet': (
            'if (rcuwait_active(wait) && rcuwait_wake_up(wait))',
            '(void)wait;\n\tif (rcuwait_active(node->wait) && rcuwait_wake_up(node->wait))'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-owned-fifo-') as directory:
        path = Path(directory)
        cc = shlex.split(os.environ.get('CC', 'gcc'))

        def run(text, name, generate=production):
            cfile, binary = path/(name+'.c'), path/name
            cfile.write_text(generate(text))
            subprocess.run(cc+['-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                               str(cfile), '-o', str(binary)],
                           check=True, timeout=30)
            return subprocess.run([binary], capture_output=True, text=True, timeout=10)

        result = run(source, 'original')
        assert result.returncode == 0, result.stdout+result.stderr
        print(result.stdout, end='')
        result = run(source, 'notifications', notifications)
        assert result.returncode == 0, result.stdout+result.stderr
        print(result.stdout, end='')
        if args.mutations:
            for name, (old, new) in mutations.items():
                assert source.count(old) == 1, (name, source.count(old))
                result = run(source.replace(old, new), name)
                assert result.returncode != 0, f'mutation escaped: {name}'
                print(f'PASS rejected mutation: {name}')
            for name, (old, new) in notification_mutations.items():
                assert source.count(old) == 1, (name, source.count(old))
                result = run(source.replace(old, new), name, notifications)
                assert result.returncode != 0, f'mutation escaped: {name}'
                print(f'PASS rejected mutation: {name}')


if __name__ == '__main__':
    main()
