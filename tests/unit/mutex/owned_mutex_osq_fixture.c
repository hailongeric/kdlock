/* Real owned OSQ and preflight code, with deterministic peer interleavings.
 * Cleanup loops deliberately exceed the polling budget in several cases. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct { int counter; } atomic_t;
typedef struct { unsigned long counter; } atomic_long_t;
struct optimistic_spin_queue { atomic_t tail; } queue;
struct kd_mutex { atomic_long_t owner; struct optimistic_spin_queue osq; } mutex;
struct task_struct { int on_cpu; } __attribute__((aligned(64)));
static struct task_struct tasks[4], *current;
static unsigned int cpu, observations, relaxes, releases, event_at;
static bool resched, event_done, core_mode;
static enum { QUIET, GRANT_IN_WAIT, GRANT_STEP_A, SUCCESSOR_LINK,
              SUCCESSOR_CANCEL, PREDECESSOR_CANCEL, RESCHEDULE } scenario;
static void before_compare(void *address);
static void after_write(void *address);
static void before_conditional(void);
static void cpu_relax(void);
static struct optimistic_spin_queue *active_queue(void) { return core_mode ? &mutex.osq : &queue; }
#define DEFINE_PER_CPU_SHARED_ALIGNED(type,name) static type name[8]
#define this_cpu_ptr(p) (&(*(p))[cpu])
#define per_cpu_ptr(p,n) (&(*(p))[n])
#define smp_processor_id() ((int)cpu)
#define OSQ_UNLOCKED_VAL 0
#define KD_OWNED_MUTEX_FLAG_WAITERS 1UL
#define KD_OWNED_MUTEX_FLAG_HANDOFF 2UL
#define KD_OWNED_MUTEX_FLAG_PICKUP 4UL
#define KD_OWNED_MUTEX_FLAG_DELEGATION 8UL
#define KD_OWNED_MUTEX_FLAGS 15UL
#define likely(x) (x)
#define BUG_ON(x) assert(!(x))
#define barrier() __asm__ __volatile__("" ::: "memory")
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_RELAXED)
#define WRITE_ONCE(x,v) do { __atomic_store_n(&(x),(v),__ATOMIC_RELAXED); after_write(&(x)); } while(0)
#define data_race(x) (x)
#define atomic_read(p) READ_ONCE((p)->counter)
#define atomic_long_read(p) READ_ONCE((p)->counter)
#define atomic_xchg(p,v) __atomic_exchange_n(&(p)->counter,(v),__ATOMIC_SEQ_CST)
#define xchg(p,v) __atomic_exchange_n((p),(v),__ATOMIC_SEQ_CST)
#define compare(p,old,v,order) ({ \
 __typeof__(*(p)) expected=(old); before_compare(p); \
 __atomic_compare_exchange_n((p),&expected,(v),false,(order),__ATOMIC_RELAXED); expected; })
#define cmpxchg(p,old,v) compare((p),(old),(v),__ATOMIC_SEQ_CST)
#define atomic_cmpxchg(p,old,v) compare(&(p)->counter,(old),(v),__ATOMIC_SEQ_CST)
#define atomic_cmpxchg_acquire(p,old,v) compare(&(p)->counter,(old),(v),__ATOMIC_ACQUIRE)
#define atomic_cmpxchg_release(p,old,v) ({ releases++; compare(&(p)->counter,(old),(v),__ATOMIC_RELEASE); })
#define atomic_long_try_cmpxchg_acquire(p,old,v) \
 __atomic_compare_exchange_n(&(p)->counter,(old),(v),false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n((p),__ATOMIC_ACQUIRE)
#define smp_wmb() __atomic_thread_fence(__ATOMIC_RELEASE)
#define smp_cond_load_relaxed(p,condition) ({ \
 __typeof__(*(p)) VAL; \
 for(;;) { before_conditional(); VAL=READ_ONCE(*(p)); \
  if(condition) { break; } cpu_relax(); } VAL; })
static void lockdep_assert_preemption_disabled(void) { assert(cpu<4); }
static bool need_resched(void) { return resched; }
static bool vcpu_is_preempted(int id) { assert(id>=0 && id<4); return false; }
static bool owner_on_cpu(struct task_struct *task) { return task->on_cpu; }
#include "osq_production.h"

static void grant_to_current(void)
{
 struct kd_owned_osq_node *node=&kd_owned_osq_nodes[cpu];
 node->prev->next=NULL;
 node->locked=1;
 event_done=true;
}
static void before_conditional(void)
{
 assert(++observations<32);
 if(observations!=event_at || event_done) return;
 if(scenario==GRANT_IN_WAIT) grant_to_current();
 if(scenario==RESCHEDULE) { resched=true;event_done=true; }
}
static void before_compare(void *address)
{
 struct kd_owned_osq_node *node=&kd_owned_osq_nodes[cpu];
 if(event_done || !node->prev || address!=&node->prev->next) return;
 if(scenario==GRANT_STEP_A) grant_to_current();
 if(scenario==PREDECESSOR_CANCEL) {
  /* The predecessor completed its own A/B/C before our stale Step-A CAS.
   * Our next iteration must refresh prev, rather than unlink the old node. */
  struct kd_owned_osq_node *old=node->prev, *head=old->prev;
  old->next=NULL;node->prev=head;head->next=node;event_done=true;
 }
}
static void after_write(void *address)
{
 struct kd_owned_osq_node *node=&kd_owned_osq_nodes[cpu], *next=&kd_owned_osq_nodes[2];
 if(cpu!=1 || event_done || address!=&kd_owned_osq_nodes[0].next) return;
 if(scenario==SUCCESSOR_LINK || scenario==SUCCESSOR_CANCEL) {
  /* The successor advanced tail; link publication is delayed, or its
   * cancellation cleared our next link before our Step B could consume it. */
  next->prev=node;next->cpu=3;next->locked=0;next->next=NULL;
  active_queue()->tail.counter=3;
 }
}
static void cpu_relax(void)
{
 assert(++relaxes<128);
 if(event_done || observations<event_at) return;
 if(scenario==SUCCESSOR_LINK) {
  kd_owned_osq_nodes[1].next=&kd_owned_osq_nodes[2];event_done=true;
 }
 if(scenario==SUCCESSOR_CANCEL) {
  active_queue()->tail.counter=2;event_done=true;
 }
}
static void reset(unsigned int waiter_cpu)
{
 memset(kd_owned_osq_nodes,0,sizeof(kd_owned_osq_nodes));
 for(unsigned int i=0;i<4;i++) { kd_owned_osq_nodes[i].cpu=(int)i+1;tasks[i].on_cpu=1; }
 queue.tail.counter=1;mutex.osq.tail.counter=1;
 cpu=waiter_cpu;current=&tasks[cpu];mutex.owner.counter=(unsigned long)&tasks[0];
 observations=relaxes=releases=0;event_at=3;resched=event_done=core_mode=false;scenario=QUIET;
}
static void release_head(void)
{
 cpu=0;kd_owned_osq_unlock(active_queue());assert(!active_queue()->tail.counter);
}
static void check_crowded(void)
{
 reset(0);
 queue.tail.counter=0;
 assert(!kd_owned_osq_crowded(&queue));
 for(unsigned int n=1;n<=7;n++) {
  memset(kd_owned_osq_nodes,0,sizeof(kd_owned_osq_nodes));
  for(unsigned int i=0;i<n;i++) {
   kd_owned_osq_nodes[i].queue=&queue;
   kd_owned_osq_nodes[i].prev=i ? &kd_owned_osq_nodes[i-1] : NULL;
  }
  queue.tail.counter=n;
  for(unsigned int probe=0;probe<63;probe++)
   assert(!kd_owned_osq_crowded(&queue));
  assert(kd_owned_osq_crowded(&queue)==(n>=7));
 }
 queue.tail.counter=7;
 kd_owned_osq_nodes[3].queue=&mutex.osq;
 kd_owned_osq_nodes[0].probes=63;
 assert(!kd_owned_osq_crowded(&queue));
 kd_owned_osq_nodes[3].queue=&queue;
 kd_owned_osq_nodes[3].prev=&kd_owned_osq_nodes[5];
 kd_owned_osq_nodes[0].probes=63;
 assert(!kd_owned_osq_crowded(&queue));
 kd_owned_osq_nodes[3].prev=&kd_owned_osq_nodes[2];
 kd_owned_osq_nodes[3].locked=1;
 kd_owned_osq_nodes[0].probes=63;
 assert(!kd_owned_osq_crowded(&queue));
 kd_owned_osq_nodes[3].locked=0;
 kd_owned_osq_nodes[0].probes=63;
 assert(kd_owned_osq_crowded(&queue));
}
int main(void)
{
 unsigned int remaining;
 check_crowded();
 reset(1);remaining=0;
 assert(!kd_owned_osq_lock_bounded(&queue,&remaining));
 assert(queue.tail.counter==1 && !observations && !kd_owned_osq_nodes[0].next);

 reset(1);queue.tail.counter=0;remaining=3;
 assert(kd_owned_osq_lock_bounded(&queue,&remaining));
 assert(remaining==3 && !observations && queue.tail.counter==2);
 kd_owned_osq_unlock(&queue);assert(!queue.tail.counter);

 reset(1);remaining=3;
 assert(!kd_owned_osq_lock_bounded(&queue,&remaining));
 assert(!remaining && observations==3 && relaxes==2);
 assert(queue.tail.counter==1 && !kd_owned_osq_nodes[0].next);
 release_head();

 for(unsigned int when=1;when<=3;when+=2) {
  reset(1);remaining=3;scenario=GRANT_IN_WAIT;event_at=when;
  assert(kd_owned_osq_lock_bounded(&queue,&remaining));
  assert(event_done && observations==when && remaining==3-when);
  kd_owned_osq_unlock(&queue);assert(!queue.tail.counter);
 }

 reset(1);remaining=3;scenario=GRANT_STEP_A;
 assert(kd_owned_osq_lock_bounded(&queue,&remaining));
 assert(event_done && observations==3 && !remaining);
 kd_owned_osq_unlock(&queue);assert(!queue.tail.counter);

 reset(1);remaining=3;scenario=SUCCESSOR_LINK;
 assert(!kd_owned_osq_lock_bounded(&queue,&remaining));
 assert(event_done && !remaining && observations==3 && relaxes==3);
 assert(queue.tail.counter==3 && kd_owned_osq_nodes[0].next==&kd_owned_osq_nodes[2]);
 assert(kd_owned_osq_nodes[2].prev==&kd_owned_osq_nodes[0] && !kd_owned_osq_nodes[1].next);
 cpu=0;kd_owned_osq_unlock(&queue);assert(kd_owned_osq_nodes[2].locked);
 cpu=2;kd_owned_osq_unlock(&queue);assert(!queue.tail.counter);

 reset(1);remaining=3;scenario=SUCCESSOR_CANCEL;
 assert(!kd_owned_osq_lock_bounded(&queue,&remaining));
 assert(event_done && !remaining && observations==3 && relaxes==3);
 assert(queue.tail.counter==1 && !kd_owned_osq_nodes[0].next);
 release_head();

 reset(2);remaining=1;scenario=PREDECESSOR_CANCEL;
 queue.tail.counter=2;kd_owned_osq_nodes[0].next=&kd_owned_osq_nodes[1];
 kd_owned_osq_nodes[1].prev=&kd_owned_osq_nodes[0];
 assert(!kd_owned_osq_lock_bounded(&queue,&remaining));
 assert(event_done && !remaining && observations==1 && relaxes==1);
 assert(queue.tail.counter==1 && !kd_owned_osq_nodes[0].next);
 release_head();

 /* The original API has no budget and still cancels solely for scheduler/
  * predecessor conditions, even after more observations than our budgets. */
 reset(1);scenario=RESCHEDULE;event_at=9;
 assert(!kd_owned_osq_lock(&queue));
 assert(event_done && observations==9 && queue.tail.counter==1);
 release_head();

 /* A grant during timeout cleanup leaves zero owner polls, but the actual
  * preflight must release its acquired OSQ before returning BUSY. */
 reset(1);core_mode=true;scenario=GRANT_STEP_A;
 assert(kd_owned_mutex_try_optimistic_pinned(&mutex,3,true)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(event_done && observations==3 && releases==1 && !mutex.osq.tail.counter);
 assert(mutex.owner.counter==(unsigned long)&tasks[0]);

 /* Queue wait and owner wait consume one shared budget: two queue samples
  * leave exactly two owner polls. Queue relaxation adds one more pause. */
 reset(1);core_mode=true;scenario=GRANT_IN_WAIT;event_at=2;
 assert(kd_owned_mutex_try_optimistic_pinned(&mutex,4,true)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(observations==2 && relaxes==3 && releases==1 && !mutex.osq.tail.counter);
 /* Guarded delegation does not stop bounded spinning on WAITERS alone.
  * Acquiring or cancelling OSQ must never clear the physical owner's guard. */
 for(unsigned long flags=KD_OWNED_MUTEX_FLAG_WAITERS;flags<=9;flags+=8) {
  reset(1);core_mode=true;scenario=GRANT_STEP_A;
  mutex.owner.counter|=flags;
  assert(kd_owned_mutex_try_optimistic_pinned(&mutex,3,true)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
  assert(event_done && observations==3 && releases==1 && !mutex.osq.tail.counter);
  assert(mutex.owner.counter==((unsigned long)&tasks[0]|flags));

  reset(1);core_mode=true;mutex.owner.counter|=flags;
  assert(kd_owned_mutex_try_optimistic_pinned(&mutex,3,true)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
  assert(observations==3 && !releases && mutex.osq.tail.counter==1);
  assert(mutex.owner.counter==((unsigned long)&tasks[0]|flags));
  assert(!kd_owned_osq_nodes[0].next);release_head();

  reset(1);core_mode=true;mutex.owner.counter=flags;
  assert(kd_owned_mutex_try_optimistic_pinned(&mutex,3,true)==KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED);
  assert(mutex.owner.counter==((unsigned long)current|flags));
  assert(!observations && !releases && mutex.osq.tail.counter==1);
  release_head();
 }
 puts("PASS owned bounded OSQ: exact budget, timeout/grant race, predecessor cancellation, delayed/canceling successor, unbounded compatibility, guard preservation and mandatory preflight unlock");
 return 0;
}
