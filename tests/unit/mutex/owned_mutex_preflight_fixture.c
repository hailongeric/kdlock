/* Production preflight/OSQ functions with deterministic scheduling primitives.
 * This checks protocol cleanup and bounds, not concurrent kernel execution. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
unsigned int owned_mutex_reuse_spins;
typedef struct { unsigned long counter; } atomic_long_t;
typedef struct { int counter; } atomic_t;
struct optimistic_spin_queue { atomic_t tail; };
struct kd_mutex { atomic_long_t owner; struct optimistic_spin_queue osq; bool adaptive_hot; };
struct kd_owned_mutex_waiter;
struct task_struct { bool on_cpu; char comm[16]; } __attribute__((aligned(64)));
#include "preflight_types.h"
static struct task_struct tasks[3], *current;
static struct kd_mutex lock;
static struct kd_owned_osq_node kd_owned_osq_nodes, successor;
static unsigned int pins, polls, releases, entries, contentions, self_calls, eligibility_calls;
static unsigned int comm_calls, active_calls, task_get_calls, task_put_calls, task_refs;
static unsigned int migrations, registry_calls, reserve_calls, unreserve_calls, wait_calls;
static unsigned int native_queue_polls, native_queue_calls, self_wait_calls;
static unsigned int schedules, pin_entries, pin_exits, action_after;
static bool schedule_frees_owner, cancel_frees_owner;
static unsigned int owner_reads, handoff_steps, resched_on_poll;
static bool cabi_gate_active;
static bool native_queue_cancel, change_owner_after_read, free_owner_after_read, churn_owner;
static unsigned int kd_owned_mutex_refusals;
static bool resched, cas_race, admitted, source_open, comm_matches, task_active;
static bool task_get_ok, reserve_ok, node_reserved;
static bool owned_mutex_self_route,owned_mutex_preflight_queue;
static bool owned_mutex_adaptive, crowded;
static unsigned int owned_mutex_preflight_spins;
static int kd_spin_target;
static enum { NONE, FREE_OWNER, RESCHED, OWNER_OFF_CPU, ADD_WAITERS, ADD_HANDOFF,
 ADD_PICKUP, FREE_WITH_WAITERS, CHANGE_OWNER_SNAPSHOT, ADD_SUCCESSOR, DIRECTED_CYCLE, REUSE_OWNER } action;
#define KD_OWNED_MUTEX_FLAG_WAITERS 1UL
#define KD_OWNED_MUTEX_FLAG_HANDOFF 2UL
#define KD_OWNED_MUTEX_FLAG_PICKUP 4UL
#define KD_OWNED_MUTEX_FLAG_DELEGATION 8UL
#define KD_OWNED_MUTEX_FLAGS 15UL
#define OSQ_UNLOCKED_VAL 0
#define KD_EXE_LOCK_OWNED_MUTEX 3
#define KD_ENTRY_ABI_MUTEX_CLOBBER_V1 2
#define KD_OWNED_MUTEX_DELEGATE 1
#define KD_PACKET_MINIMAL 0
#define this_cpu_inc(x) ((x)++)
struct list_head { struct list_head *next, *prev; };
#define INIT_LIST_HEAD(p) do { (p)->next=(p); (p)->prev=(p); } while(0)
struct kd_owned_mutex_node {
 struct { struct list_head list; struct task_struct *task; unsigned int kind; } waiter;
 struct { unsigned long ip, sp, bp; } regs;
 unsigned int entry_abi, packet_state;
 struct kd_mutex *lock;
 unsigned long saved_ret_addr, gsbase;
};
static struct kd_owned_mutex_node request;
static const unsigned long saved_sp=0x10000, saved_ip=0x20000, saved_bp=0x30000;
#define likely(x) (x)
#define BUG_ON(x) assert(!(x))
#define barrier() __asm__ __volatile__("" ::: "memory")
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_RELAXED)
static unsigned long read_owner(atomic_long_t *word)
{
 unsigned long value=READ_ONCE(word->counter);
 assert(++owner_reads < 32768);
 if(free_owner_after_read) {
  assert(word==&lock.owner); free_owner_after_read=false;
  word->counter &= KD_OWNED_MUTEX_FLAG_WAITERS|KD_OWNED_MUTEX_FLAG_DELEGATION;
 }
 if(change_owner_after_read) {
  assert(word==&lock.owner); change_owner_after_read=false;
  word->counter=(unsigned long)&tasks[2];
 }
 if(churn_owner) {
  assert(word==&lock.owner);
  word->counter=(unsigned long)((value&~KD_OWNED_MUTEX_FLAGS)==(unsigned long)&tasks[1] ?
                               &tasks[2] : &tasks[1]);
 }
 return value;
}
#define atomic_long_read read_owner
#define atomic_read(p) READ_ONCE((p)->counter)
#define atomic_long_try_cmpxchg_acquire(p,old,v) \
 __atomic_compare_exchange_n(&(p)->counter,(old),(v),false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)
#define xchg(p,v) __atomic_exchange_n((p),(v),__ATOMIC_SEQ_CST)
#define this_cpu_ptr(p) (p)
#define smp_processor_id() 0
static void lockdep_assert_preemption_disabled(void) { assert(pins == 1); }
static inline bool kd_owned_osq_crowded(struct optimistic_spin_queue *queue)
{
 assert(queue==&lock.osq && pins==1);
 return crowded;
}
static bool need_resched(void) { return resched; }
static bool owner_on_cpu(struct task_struct *owner) { assert(pins == 1); return owner->on_cpu; }
static int ordered_cas(atomic_t *p, int old, int value)
{
 /* Fail if fields were not initialized before publication. */
 assert(kd_owned_osq_nodes.locked == 0 && kd_owned_osq_nodes.next == NULL);
 assert(kd_owned_osq_nodes.cpu == 1);
 if (cas_race) { p->counter=2; cas_race=false; }
 __atomic_compare_exchange_n(&p->counter,&old,value,false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
 return old;
}
static int release_cas(atomic_t *p, int old, int value)
{
 releases++;
 __atomic_compare_exchange_n(&p->counter,&old,value,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
 return old;
}
static int acquire_cas(atomic_t *p, int old, int value)
{
 __atomic_compare_exchange_n(&p->counter,&old,value,false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED);
 return old;
}
#define atomic_cmpxchg ordered_cas
#define atomic_cmpxchg_release release_cas
#define atomic_cmpxchg_acquire acquire_cas
static void cpu_relax(void)
{
 assert(pins == 1 && ++polls < 32768);
 if(resched_on_poll == polls) resched=true;
 if(polls < action_after) return;
 switch (action) {
 case FREE_OWNER: lock.owner.counter=0; break;
 case RESCHED: resched=true; break;
 case OWNER_OFF_CPU: tasks[1].on_cpu=false; break;
 case ADD_WAITERS: lock.owner.counter |= KD_OWNED_MUTEX_FLAG_WAITERS; break;
 case ADD_HANDOFF: lock.owner.counter |= KD_OWNED_MUTEX_FLAG_HANDOFF; break;
 case ADD_PICKUP: lock.owner.counter |= KD_OWNED_MUTEX_FLAG_PICKUP; break;
 case FREE_WITH_WAITERS:
  lock.owner.counter=KD_OWNED_MUTEX_FLAG_WAITERS|
   (lock.owner.counter&KD_OWNED_MUTEX_FLAG_DELEGATION); break;
 case CHANGE_OWNER_SNAPSHOT: change_owner_after_read=true; break;
 case ADD_SUCCESSOR:
  successor=(struct kd_owned_osq_node){.prev=&kd_owned_osq_nodes,.cpu=2};
  kd_owned_osq_nodes.next=&successor; lock.osq.tail.counter=2;
  lock.owner.counter=0; break;
 case DIRECTED_CYCLE: {
  unsigned long flags=lock.owner.counter &
   (KD_OWNED_MUTEX_FLAG_WAITERS|KD_OWNED_MUTEX_FLAG_DELEGATION);
  /* The OSQ head is never the directed recipient. Assert it cannot steal
   * before that recipient consumes PICKUP and releases the lock. */
  assert((lock.owner.counter&~KD_OWNED_MUTEX_FLAGS)!=(unsigned long)current);
  switch(handoff_steps++) {
  case 0:
   assert((lock.owner.counter&~KD_OWNED_MUTEX_FLAGS)==(unsigned long)&tasks[1]);
   lock.owner.counter|=KD_OWNED_MUTEX_FLAG_HANDOFF;break;
  case 1:
   assert(lock.owner.counter&KD_OWNED_MUTEX_FLAG_HANDOFF);
   lock.owner.counter=(unsigned long)&tasks[2]|flags|KD_OWNED_MUTEX_FLAG_PICKUP;break;
  case 2:
   assert(lock.owner.counter==((unsigned long)&tasks[2]|flags|KD_OWNED_MUTEX_FLAG_PICKUP));
   lock.owner.counter &= ~KD_OWNED_MUTEX_FLAG_PICKUP;break;
  case 3:
   assert(lock.owner.counter==((unsigned long)&tasks[2]|flags));
   lock.owner.counter=flags;action=NONE;break;
  default: assert(false);
  }
  return;
 }
 case REUSE_OWNER:
  if(polls==1 || polls==10) lock.owner.counter=0;
  if(polls==2) lock.owner.counter=(unsigned long)&tasks[1];
  return;
 case NONE: return;
 }
 action=NONE;
}
static void preempt_disable(void) { assert(!pins); pins=1; pin_entries++; }
static void preempt_enable(void) { assert(pins==1); pins=0; pin_exits++; }
#define TASK_RUNNING 0
static void __set_current_state(int state) { assert(state==TASK_RUNNING && pins==1); }
static void kd_owned_mutex_schedule(void)
{
 assert(pins==1 && !lock.osq.tail.counter);
 schedules++; resched=false;
 if(schedule_frees_owner)
  lock.owner.counter &= KD_OWNED_MUTEX_FLAG_WAITERS|KD_OWNED_MUTEX_FLAG_DELEGATION;
}
void kd_owned_mutex_lock_wait_pinned(struct kd_mutex *target)
{
 assert(pins==1 && target==&lock && !lock.osq.tail.counter);
 assert(!migrations && !node_reserved && !resched);
 self_wait_calls++; lock.owner.counter=(unsigned long)current;
}
static void kd_hotlock_owned_mutex_entry(void) { assert(pins==1); entries++; }
static bool kd_hotlock_record_owned_mutex_pinned(unsigned long address)
{
 assert(pins==1 && address==(unsigned long)&lock); contentions++; return admitted;
}
static bool kd_source_is_open(void) { eligibility_calls++; return source_open; }
static bool kd_comm_matches(const int *target, const char *comm)
{
 assert(target==&kd_spin_target && comm==current->comm); comm_calls++; return comm_matches;
}
static bool kd_mutex_task_active(struct task_struct *task)
{
 assert(task==current); active_calls++; return task_active;
}
static void kd_owned_mutex_lock_self(struct kd_mutex *target)
{
 assert(!pins && !migrations && !node_reserved && target==&lock);
 self_calls++; lock.owner.counter=(unsigned long)current;
}
void kd_owned_mutex_lock_self_wait(struct kd_mutex *target)
{
 assert(!pins && !migrations && !node_reserved && target==&lock);
 assert(!lock.osq.tail.counter);
 self_wait_calls++; lock.owner.counter=(unsigned long)current;
}
static bool kd_owned_osq_lock_bounded(struct optimistic_spin_queue *osq, unsigned int *remaining)
{ (void)osq;(void)remaining;assert(false);return false; }
bool kd_owned_osq_lock(struct optimistic_spin_queue *osq);
/* Only resource primitives are modeled. The eligibility ordering, reference
 * cleanup, packet setup and SELF return below execute the production entry. */
static bool kd_mutex_task_get(struct task_struct *task)
{
 assert(task==current && !pins && !migrations);
 assert(source_open && comm_matches && !task_active);
 assert(eligibility_calls==1 && comm_calls==1 && active_calls==1);
 task_get_calls++;
 if (!task_get_ok) return false;
 task_refs++; return true;
}
static void kd_mutex_task_put(struct task_struct *task)
{
 assert(task==current && task_refs && !pins && !migrations && !node_reserved);
 task_put_calls++; task_refs--;
}
static void kd_exe_add_abi(int bucket, unsigned long ip, int kind, unsigned int abi)
{
 assert(bucket==0 && ip==saved_ip && kind==KD_EXE_LOCK_OWNED_MUTEX);
 assert(abi==KD_ENTRY_ABI_MUTEX_CLOBBER_V1 && task_refs==1 && task_get_calls==1);
 assert(!pins && !migrations); registry_calls++;
}
static void migrate_disable(void) { assert(!pins && !migrations); migrations=1; }
static void migrate_enable(void) { assert(!pins && migrations==1); migrations=0; }
static struct kd_owned_mutex_node *kd_owned_mutex_reserve(struct kd_mutex *target)
{
 assert(target==&lock && pins==1 && migrations==1 && task_refs==1);
 assert(registry_calls==1 && !node_reserved); reserve_calls++;
 if (!reserve_ok) return NULL;
 node_reserved=true; return &request;
}
static void kd_owned_mutex_unreserve(struct kd_owned_mutex_node *node)
{
 assert(node==&request && pins==1 && migrations==1 && task_refs==1 && node_reserved);
 unreserve_calls++; node_reserved=false;
}
static unsigned long kd_read_kernel_gsbase(void) { return 0x40000; }
static int kd_owned_mutex_clobber_wait(struct kd_mutex *target, struct kd_owned_mutex_node *node)
{
 assert(target==&lock && node==&request && node_reserved && pins==1 && migrations==1);
 assert(task_refs==1 && node->waiter.task==current && node->waiter.kind==KD_OWNED_MUTEX_DELEGATE);
 assert(node->waiter.list.next==&node->waiter.list && node->waiter.list.prev==&node->waiter.list);
 assert(node->regs.ip==saved_ip && node->regs.sp==saved_sp && node->regs.bp==saved_bp);
 assert(node->entry_abi==KD_ENTRY_ABI_MUTEX_CLOBBER_V1 && node->packet_state==KD_PACKET_MINIMAL);
 assert(node->lock==&lock && node->saved_ret_addr==saved_ip && node->gsbase==0x40000);
 wait_calls++;
 /* Model directed SELF pickup. COMPLETE/FULL leave through the real thunk
  * and remain covered by the separate compiled outer/wait fixtures. */
 lock.owner.counter=(unsigned long)current;
 return 2;
}
#include "preflight_production.h"

/* Only OSQ admission/waiting is modeled here; cancellation/link races run
 * against production code in test_owned_mutex_osq.py. Local-first must choose
 * full queue admission and never leave OSQ owned after canceled admission. */
bool kd_owned_osq_lock(struct optimistic_spin_queue *osq)
{
 assert(pins==1 && osq==&lock.osq);
 if(cabi_gate_active) assert(!entries && !contentions && !eligibility_calls && !task_get_calls);
 native_queue_calls++;
 for(unsigned int i=0;i<native_queue_polls;i++) cpu_relax();
 if(native_queue_cancel) {
  if(cancel_frees_owner) lock.owner.counter=0;
  return false;
 }
 osq->tail.counter=0;
 return kd_owned_osq_trylock(osq);
}

static void reset(void)
{
 memset(tasks,0,sizeof(tasks)); tasks[1].on_cpu=true; tasks[2].on_cpu=true;
 current=&tasks[0]; lock=(struct kd_mutex){.owner={(unsigned long)&tasks[1]}};
 memset(&kd_owned_osq_nodes,0xa5,sizeof(kd_owned_osq_nodes));
 memset(&successor,0,sizeof(successor));
 pins=1; polls=releases=entries=contentions=self_calls=eligibility_calls=0;
 comm_calls=active_calls=task_get_calls=task_put_calls=task_refs=0;
 migrations=registry_calls=reserve_calls=unreserve_calls=wait_calls=kd_owned_mutex_refusals=0;
 task_get_ok=reserve_ok=true; node_reserved=false;
 native_queue_polls=native_queue_calls=self_wait_calls=0;
 owner_reads=handoff_steps=resched_on_poll=owned_mutex_reuse_spins=0;
 cabi_gate_active=false; schedules=pin_entries=pin_exits=0; action_after=1;
 schedule_frees_owner=cancel_frees_owner=false;
 native_queue_cancel=change_owner_after_read=free_owner_after_read=churn_owner=false;
 memset(&request,0xa5,sizeof(request));
 resched=cas_race=owned_mutex_self_route=task_active=false;
 owned_mutex_adaptive=crowded=false;
 admitted=source_open=comm_matches=true; owned_mutex_preflight_spins=64; action=NONE;
}
static void check_cleanup(void)
{
 /* Four independent exits after acquiring OSQ: acquire, budget, scheduler,
  * and owner off-CPU. Each must release exactly once with no pin imbalance. */
 reset(); action=FREE_OWNER;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED);
 assert(lock.owner.counter==(unsigned long)current && polls==1);
 assert(releases==1 && !lock.osq.tail.counter && pins==1);
 reset();
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(polls==64 && releases==1 && !lock.osq.tail.counter && pins==1);
 reset(); action=RESCHED;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_SELF);
 assert(polls==1 && releases==1 && !lock.osq.tail.counter && pins==1);
 reset(); action=OWNER_OFF_CPU;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_SELF);
 assert(polls==1 && releases==1 && !lock.osq.tail.counter && pins==1);
 reset(); action=ADD_WAITERS;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(polls==64 && releases==1 && !lock.osq.tail.counter);
 assert(lock.owner.counter==((unsigned long)&tasks[1]|KD_OWNED_MUTEX_FLAG_WAITERS));
 reset(); lock.owner.counter|=KD_OWNED_MUTEX_FLAG_WAITERS; action=FREE_WITH_WAITERS;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED);
 assert(polls==1 && releases==1 && !lock.osq.tail.counter);
 assert(lock.owner.counter==((unsigned long)current|KD_OWNED_MUTEX_FLAG_WAITERS));
 reset(); action=ADD_HANDOFF;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(polls==1 && releases==1 && !lock.osq.tail.counter);
 reset(); action=ADD_PICKUP;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(polls==1 && releases==1 && !lock.osq.tail.counter);
 /* Exercise the real OSQ unlock's linked-successor transfer too. */
 reset(); action=ADD_SUCCESSOR;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED);
 assert(releases==1 && successor.locked==1 && lock.osq.tail.counter==2);
}
static void check_refusals_and_bounds(void)
{
 reset(); lock.owner.counter=0;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,0,false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(!lock.owner.counter && !polls && !releases);
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED);
 assert(!polls && !releases);
 reset(); lock.owner.counter=KD_OWNED_MUTEX_FLAG_WAITERS;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED);
 assert(lock.owner.counter==((unsigned long)current|KD_OWNED_MUTEX_FLAG_WAITERS));
 for (unsigned long flags=1;flags<8;flags++) {
  reset(); lock.owner.counter|=flags;
  unsigned long owner=lock.owner.counter;
  assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
  assert(lock.owner.counter==owner && !lock.osq.tail.counter);
  assert(polls==(flags==KD_OWNED_MUTEX_FLAG_WAITERS ? 64U : 0U));
  assert(releases==(flags==KD_OWNED_MUTEX_FLAG_WAITERS ? 1U : 0U));
 }
 reset(); lock.osq.tail.counter=2;
 struct kd_owned_osq_node saved=kd_owned_osq_nodes;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(!memcmp(&saved,&kd_owned_osq_nodes,sizeof(saved)));
 assert(lock.osq.tail.counter==2 && !polls && !releases);
 reset(); cas_race=true;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
 assert(lock.osq.tail.counter==2 && !polls && !releases);
 reset(); resched=true;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_SELF);
 assert(!polls && !releases && !lock.osq.tail.counter);
 reset(); tasks[1].on_cpu=false;
 assert(kd_owned_mutex_try_optimistic_pinned(&lock,64,false)==KD_OWNED_MUTEX_PREFLIGHT_SELF);
 assert(!polls && !releases && !lock.osq.tail.counter);
 for (unsigned int i=0;i<=4097;i++)
  assert(kd_owned_mutex_preflight_spins_valid(i)==
         (i==0 || i==64 || i==256 || i==1024 || i==4096));
 const unsigned int budgets[]={1,64,256,1024,4096};
 for (unsigned int i=0;i<sizeof(budgets)/sizeof(*budgets);i++) {
  reset();
  assert(kd_owned_mutex_try_optimistic_pinned(&lock,budgets[i],false)==KD_OWNED_MUTEX_PREFLIGHT_BUSY);
  assert(polls==budgets[i] && releases==1 && !lock.osq.tail.counter);
 }
}
static void gate_done(bool acquired, unsigned int expected_self)
{
 assert(pins==0 && entries==1 && contentions==1 && self_calls==expected_self);
 if (acquired) assert(lock.owner.counter==(unsigned long)current);
 else assert(lock.owner.counter==(unsigned long)&tasks[1]);
}
static void check_gate(void)
{
 reset(); pins=0; admitted=false;
 assert(kd_owned_mutex_outer_preflight_v1(&lock)); gate_done(true,1);
 assert(!polls && !releases && !eligibility_calls);
 reset(); pins=0; owned_mutex_self_route=true;
 assert(kd_owned_mutex_outer_preflight_v1(&lock)); gate_done(true,1);
 assert(!polls && !eligibility_calls);
 reset(); pins=0; action=FREE_OWNER; source_open=false;
 assert(kd_owned_mutex_outer_preflight_v1(&lock)); gate_done(true,0);
 assert(polls==1 && releases==1 && !eligibility_calls);
 reset(); pins=0;
 assert(!kd_owned_mutex_outer_preflight_v1(&lock)); gate_done(false,0);
 assert(polls==64 && releases==1 && !eligibility_calls);
 reset(); pins=0; owned_mutex_preflight_spins=0;
 assert(!kd_owned_mutex_outer_preflight_v1(&lock)); gate_done(false,0);
 assert(!polls && !releases);
 reset(); pins=0; resched=true;
 assert(kd_owned_mutex_outer_preflight_v1(&lock)); gate_done(true,1);
 assert(!polls && !eligibility_calls);
 for(unsigned int reason=0;reason<3;reason++) {
  reset(); pins=0; owned_mutex_preflight_spins=0;
  if(reason==0) source_open=false;
  if(reason==1) comm_matches=false;
  if(reason==2) task_active=true;
  assert(!kd_owned_mutex_outer_preflight_v1(&lock)); gate_done(false,0);
  assert(!eligibility_calls && !comm_calls && !active_calls && !task_get_calls);
 }
}
static void capture_only_gate(void)
{
 assert(!kd_owned_mutex_outer_preflight_v1(&lock)); gate_done(false,0);
 assert(!eligibility_calls && !comm_calls && !active_calls && !task_get_calls);
 assert(!migrations && !reserve_calls && !registry_calls && !node_reserved);
}
static void check_prepared(void)
{
 /* Reject each cause already present at the gate and each cause appearing
  * afterward. A false gate grants capture permission, never eligibility. */
 for (unsigned int after_gate=0;after_gate<2;after_gate++) {
  for (unsigned int reason=0;reason<3;reason++) {
   reset(); pins=0; owned_mutex_preflight_spins=0;
   if (after_gate) capture_only_gate();
   if (reason==0) source_open=false;
   if (reason==1) comm_matches=false;
   if (reason==2) { task_active=true; task_refs=3; }
   if (!after_gate) capture_only_gate();
   unsigned int retained_refs=task_refs;
   assert(kd_owned_mutex_outer_prepared_clobber_v1(&lock,saved_sp,saved_ip,saved_bp)==(unsigned long)current);
   gate_done(true,1);
   assert(eligibility_calls==1 && comm_calls==(reason!=0) && active_calls==(reason==2));
   assert(!task_get_calls && !task_put_calls && task_refs==retained_refs);
   assert(!registry_calls && !reserve_calls && !unreserve_calls && !wait_calls);
   assert(!migrations && !node_reserved);
  }
 }
 /* The prepared endpoint independently enforces diagnostic SELF, even if
  * called directly. The read-only policy does not actually change in flight. */
 reset(); pins=0; owned_mutex_self_route=true;
 assert(kd_owned_mutex_outer_prepared_clobber_v1(&lock,saved_sp,saved_ip,saved_bp)==(unsigned long)current);
 assert(self_calls==1 && !entries && !contentions && !eligibility_calls && !task_get_calls);

 reset(); pins=0; owned_mutex_preflight_spins=0; capture_only_gate(); task_get_ok=false;
 assert(kd_owned_mutex_outer_prepared_clobber_v1(&lock,saved_sp,saved_ip,saved_bp)==(unsigned long)current);
 gate_done(true,1);
 assert(eligibility_calls==1 && active_calls==1 && task_get_calls==1 && !task_refs && !task_put_calls);
 assert(!registry_calls && !reserve_calls && !wait_calls && !migrations);

 reset(); pins=0; owned_mutex_preflight_spins=0; capture_only_gate(); reserve_ok=false;
 assert(kd_owned_mutex_outer_prepared_clobber_v1(&lock,saved_sp,saved_ip,saved_bp)==(unsigned long)current);
 gate_done(true,1);
 assert(eligibility_calls==1 && active_calls==1 && task_get_calls==1 && task_put_calls==1 && !task_refs);
 assert(registry_calls==1 && reserve_calls==1 && !unreserve_calls && !wait_calls);
 assert(kd_owned_mutex_refusals==1 && !migrations && !node_reserved);

 reset(); pins=0; owned_mutex_preflight_spins=0; capture_only_gate();
 assert(kd_owned_mutex_outer_prepared_clobber_v1(&lock,saved_sp,saved_ip,saved_bp)==(unsigned long)current);
 gate_done(true,0);
 assert(eligibility_calls==1 && comm_calls==1 && active_calls==1);
 assert(task_get_calls==1 && task_put_calls==1 && !task_refs);
 assert(registry_calls==1 && reserve_calls==1 && unreserve_calls==1 && wait_calls==1);
 assert(!migrations && !node_reserved && !kd_owned_mutex_refusals);
}
static void check_capture_first(void)
{
 /* Configuring provider polling cannot activate the gate for default callers.
  * Both cold refusal and hot capture count exactly this one failed attempt. */
 for(unsigned int hot=0;hot<2;hot++) {
  reset(); pins=0; admitted=hot;
  owned_mutex_preflight_spins=4096; owned_mutex_preflight_queue=true;
  assert(kd_owned_mutex_outer_contended_clobber_v1(&lock,saved_sp,saved_ip,saved_bp)==(unsigned long)current);
  assert(entries==1 && contentions==1 && !pins && !migrations && !task_refs && !node_reserved);
  assert(!polls && !releases && eligibility_calls==hot && task_get_calls==hot && task_put_calls==hot);
  assert(self_calls==!hot && wait_calls==hot);
 }
 reset(); pins=0; source_open=false;
 assert(kd_owned_mutex_outer_contended_clobber_v1(&lock,saved_sp,saved_ip,saved_bp)==(unsigned long)current);
 assert(entries==1 && contentions==1 && self_calls==1 && eligibility_calls==1 && !task_get_calls);
}

static void check_local_first(void)
{
 const unsigned long permissive[]={0,KD_OWNED_MUTEX_FLAG_WAITERS,
  KD_OWNED_MUTEX_FLAG_WAITERS|KD_OWNED_MUTEX_FLAG_DELEGATION};
 /* More than the removed maximum head budget: a still-running owner is
  * allowed to release naturally. Neither queue waiting nor head polling
  * invokes heat admission, resource checks or a forced sleeping boundary. */
 for(unsigned int i=0;i<sizeof(permissive)/sizeof(permissive[0]);i++) {
  reset(); lock.owner.counter|=permissive[i]; native_queue_polls=100;
  lock.osq.tail.counter=2; action=FREE_WITH_WAITERS; action_after=6000;
  assert(kd_owned_mutex_try_local_pinned(&lock));
  assert(native_queue_calls==1 && polls==6001 && releases==1 && pins==1);
  assert(!schedules && !lock.osq.tail.counter && !entries && !contentions);
  assert(lock.owner.counter==((unsigned long)current|KD_OWNED_MUTEX_FLAG_WAITERS|
                             (permissive[i]&KD_OWNED_MUTEX_FLAG_DELEGATION)));
 }
 for(unsigned int released=0;released<2;released++) {
  reset(); native_queue_cancel=true;cancel_frees_owner=released;
  assert(kd_owned_mutex_try_local_pinned(&lock)==(bool)released);
  assert(native_queue_calls==1 && !polls && !releases && !lock.osq.tail.counter);
  assert(!schedules && pins==1);
 }
 reset(); lock.owner.counter=0;
 assert(kd_owned_mutex_try_local_pinned(&lock));
 assert(lock.owner.counter==(unsigned long)current && !native_queue_calls);

 /* Release/reacquisition between snapshots is an acquisition opportunity,
  * including ownerless WAITERS|D. It must not become premature SELF sleep. */
 reset();lock.owner.counter|=KD_OWNED_MUTEX_FLAG_WAITERS|KD_OWNED_MUTEX_FLAG_DELEGATION;
 free_owner_after_read=true;
 assert(kd_owned_mutex_try_local_pinned(&lock));
 assert(lock.owner.counter==((unsigned long)current|KD_OWNED_MUTEX_FLAG_WAITERS|
                            KD_OWNED_MUTEX_FLAG_DELEGATION));
 assert(native_queue_calls==1 && !polls && releases==1 && !lock.osq.tail.counter);
 reset();change_owner_after_read=true;tasks[1].on_cpu=false;action=FREE_OWNER;
 assert(kd_owned_mutex_try_local_pinned(&lock));
 assert(lock.owner.counter==(unsigned long)current && polls==2 && releases==1);
 assert(native_queue_calls==1 && !lock.osq.tail.counter);

 /* A running directed recipient can consume PICKUP and finish while this
  * CPU remains OSQ head. Exact acquisition never steals its owner word. */
 for(unsigned int guarded=0;guarded<2;guarded++) {
  for(unsigned int initial_handoff=0;initial_handoff<2;initial_handoff++) {
   unsigned long flags=KD_OWNED_MUTEX_FLAG_WAITERS|
    (guarded ? KD_OWNED_MUTEX_FLAG_DELEGATION : 0);
   reset();lock.owner.counter|=flags|(initial_handoff ? KD_OWNED_MUTEX_FLAG_HANDOFF : 0);
   action=DIRECTED_CYCLE;
   assert(kd_owned_mutex_try_local_pinned(&lock));
   assert(handoff_steps==4 && polls==5 && releases==1 && native_queue_calls==1);
   assert(lock.owner.counter==((unsigned long)current|flags) && !lock.osq.tail.counter);
  }
 }
 reset(); lock.owner.counter=(unsigned long)current|KD_OWNED_MUTEX_FLAG_PICKUP|
  KD_OWNED_MUTEX_FLAG_WAITERS|KD_OWNED_MUTEX_FLAG_DELEGATION;
 assert(kd_owned_mutex_try_local_pinned(&lock));
 assert(lock.owner.counter==((unsigned long)current|KD_OWNED_MUTEX_FLAG_WAITERS|
  KD_OWNED_MUTEX_FLAG_DELEGATION) && !native_queue_calls);

 /* These are real Linux spin failure exits. A required yield happens after
  * OSQ release; the final exact retry acquires if that yield released L. */
 for(unsigned int after_join=0;after_join<2;after_join++) {
  for(unsigned int released=0;released<2;released++) {
   reset();schedule_frees_owner=released;
   if(after_join) action=RESCHED; else resched=true;
   assert(kd_owned_mutex_try_local_pinned(&lock)==(bool)released);
   assert(schedules==1 && !resched && pins==1 && !lock.osq.tail.counter);
   assert(native_queue_calls==after_join && releases==after_join && polls==after_join);
  }
  reset();
  if(after_join) action=OWNER_OFF_CPU; else tasks[1].on_cpu=false;
  assert(!kd_owned_mutex_try_local_pinned(&lock));
  assert(!schedules && !lock.osq.tail.counter && pins==1);
  assert(native_queue_calls==after_join && releases==after_join && polls==after_join);
 }
 /* An actual successor handoff releases our OSQ node even though the shared
  * tail remains nonzero for the next spinner. */
 reset(); action=ADD_SUCCESSOR;
 assert(kd_owned_mutex_try_local_pinned(&lock));
 assert(releases==1 && successor.locked==1 && lock.osq.tail.counter==2);
}
static void check_reuse_grace(void)
{
 const unsigned int limits[]={0,8,32,128};
 for(unsigned int i=0;i<sizeof(limits)/sizeof(limits[0]);i++) {
  reset();owned_mutex_reuse_spins=limits[i];action=FREE_OWNER;
  assert(kd_owned_mutex_try_local_pinned(&lock));
  assert(polls==1+(limits[i] ? limits[i] : 1) && releases==1 && !lock.osq.tail.counter);
  reset();owned_mutex_reuse_spins=limits[i];action=FREE_WITH_WAITERS;
  assert(kd_owned_mutex_try_local_pinned(&lock));
  assert(polls==2 && releases==1 && !lock.osq.tail.counter);
  reset();owned_mutex_reuse_spins=limits[i];action=FREE_OWNER;
  assert(kd_owned_mutex_optimistic_spin(&lock,(struct kd_owned_mutex_waiter *)1));
  assert(polls==2 && !releases && !native_queue_calls);
 }
 /* A second release during the same OSQ head turn gets no second grace. */
 reset();owned_mutex_reuse_spins=8;action=REUSE_OWNER;
 assert(kd_owned_mutex_try_local_pinned(&lock));
 assert(polls==11 && releases==1 && !lock.osq.tail.counter);
 /* Scheduling interrupts the grace; cleanup precedes the required yield. */
 reset();owned_mutex_reuse_spins=128;action=FREE_OWNER;resched_on_poll=2;
 assert(kd_owned_mutex_try_local_pinned(&lock));
 assert(polls==2 && releases==1 && schedules==1 && !lock.osq.tail.counter);
}
static unsigned long run_cabi_gate(void)
{
 unsigned long result;
 cabi_gate_active=true;
 result=kd_owned_mutex_outer_cabi_gate(&lock,saved_ip);
 cabi_gate_active=false;
 assert(!pins && !migrations && !node_reserved && !lock.osq.tail.counter);
 assert(pin_entries==1 && pin_exits==1);
 assert(!entries && !contentions);
 assert(!eligibility_calls && !comm_calls && !active_calls && !task_get_calls && !task_put_calls);
 assert(!registry_calls && !reserve_calls && !wait_calls);
 return result;
}
static void check_cabi_gate(void)
{
 /* Local acquisition is first for cold heat, diagnostic SELF, source closure
  * and tracked tasks alike. Only the captured path evaluates eligibility. */
 for(unsigned int route=0;route<5;route++) {
  reset();pins=0;action=FREE_OWNER;
  if(route==0) admitted=false;
  if(route==1) owned_mutex_self_route=true;
  if(route==2) source_open=false;
  if(route==3) comm_matches=false;
  if(route==4) {task_active=true;task_refs=3;}
  assert(run_cabi_gate()==(unsigned long)current);
  assert(lock.owner.counter==(unsigned long)current && polls==2 && releases==1);
  assert(native_queue_calls==1 && !self_calls && !self_wait_calls);
  assert(task_refs==(route==4 ? 3U : 0U));
 }
 /* Every genuine spin failure may request capture, with no eligibility or
  * source lease and no task reference retained across the C gate. */
 for(unsigned int refusal=0;refusal<4;refusal++) {
  reset();pins=0;tasks[1].on_cpu=false;
  if(refusal==1) source_open=false;
  if(refusal==2) comm_matches=false;
  if(refusal==3) {task_active=true;task_refs=3;}
  assert(run_cabi_gate()==0);
  assert(!polls && !releases && !native_queue_calls);
  assert(!self_calls && !self_wait_calls && task_refs==(refusal==3 ? 3U : 0U));
  assert(lock.owner.counter==(unsigned long)&tasks[1]);
 }
 for(unsigned int reason=0;reason<3;reason++) {
  reset();pins=0;owned_mutex_self_route=true;
  if(reason==0) resched=true;
  if(reason==1) tasks[1].on_cpu=false;
  if(reason==2) native_queue_cancel=true;
  assert(run_cabi_gate()==(unsigned long)current);
  assert(self_wait_calls==1 && !self_calls && schedules==(reason==0));
  assert(!polls && !releases && native_queue_calls==(reason==2));
 }
 reset();pins=0;lock.owner.counter=0;
 assert(run_cabi_gate()==(unsigned long)current);
 assert(!native_queue_calls && !polls && !self_calls && !self_wait_calls);
 reset();pins=0;resched=true;schedule_frees_owner=true;
 assert(run_cabi_gate()==(unsigned long)current);
 assert(schedules==1 && !self_calls && !self_wait_calls);
}
static void check_adaptive_gate(void)
{
 reset();pins=0;owned_mutex_adaptive=true;lock.adaptive_hot=true;lock.owner.counter=0;
 assert(run_cabi_gate()==(unsigned long)current && !lock.adaptive_hot);
 assert(!native_queue_calls && !self_calls && !self_wait_calls);
 /* Crowded admission carries no queue ownership, pin, or request resource
  * into capture. Exact eligibility is still checked by the prepared entry. */
 for(unsigned int reason=0;reason<2;reason++) {
  reset();pins=0;owned_mutex_adaptive=true;
  if(reason==0) crowded=true;
  else lock.adaptive_hot=true;
  unsigned long owner=lock.owner.counter;
  assert(run_cabi_gate()==0);
  assert(lock.owner.counter==owner && !native_queue_calls && !polls && !releases);
  assert(!self_calls && !self_wait_calls);
 }
 /* Short cohorts, disabled policy, and diagnostic SELF retain local reuse. */
 for(unsigned int route=0;route<4;route++) {
  reset();pins=0;action=FREE_OWNER;
  owned_mutex_adaptive=route!=1;
  crowded=route==1 || route==2;
  owned_mutex_self_route=route==2;
  if(route==3) lock.owner.counter|=KD_OWNED_MUTEX_FLAG_DELEGATION;
  assert(run_cabi_gate()==(unsigned long)current);
  assert(native_queue_calls==1 && !self_wait_calls && releases==1);
 }
}
int main(void)
{
 check_cleanup(); check_refusals_and_bounds(); check_gate(); check_prepared(); check_capture_first(); check_local_first(); check_cabi_gate(); check_reuse_grace();
 check_adaptive_gate();
 puts("PASS owned preflight: ABI2 once-only admission/resources, Linux unbounded local OSQ, directed transitions, cancellation/yield cleanup, final retry and one-pin ABI4 gate");
 return 0;
}
