/* Production preflight/OSQ functions with deterministic scheduling primitives.
 * This checks protocol cleanup and bounds, not concurrent kernel execution. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct { unsigned long counter; } atomic_long_t;
typedef struct { int counter; } atomic_t;
struct optimistic_spin_queue { atomic_t tail; };
struct kd_mutex { atomic_long_t owner; struct optimistic_spin_queue osq; };
struct task_struct { bool on_cpu; char comm[16]; } __attribute__((aligned(64)));
#include "preflight_types.h"
static struct task_struct tasks[3], *current;
static struct kd_mutex lock;
static struct kd_owned_osq_node kd_owned_osq_nodes, successor;
static unsigned int pins, polls, releases, entries, contentions, self_calls, eligibility_calls;
static unsigned int comm_calls, active_calls, task_get_calls, task_put_calls, task_refs;
static unsigned int migrations, registry_calls, reserve_calls, unreserve_calls, wait_calls;
static unsigned int kd_owned_mutex_refusals;
static bool resched, cas_race, admitted, source_open, comm_matches, task_active;
static bool task_get_ok, reserve_ok, node_reserved;
static bool owned_mutex_self_route,owned_mutex_preflight_queue;
static unsigned int owned_mutex_preflight_spins;
static int kd_spin_target;
static enum { NONE, FREE_OWNER, RESCHED, OWNER_OFF_CPU, ADD_WAITERS, ADD_SUCCESSOR } action;
#define KD_OWNED_MUTEX_FLAG_WAITERS 1UL
#define KD_OWNED_MUTEX_FLAG_HANDOFF 2UL
#define KD_OWNED_MUTEX_FLAG_PICKUP 4UL
#define KD_OWNED_MUTEX_FLAGS 7UL
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
#define atomic_long_read(p) READ_ONCE((p)->counter)
#define atomic_read(p) READ_ONCE((p)->counter)
#define atomic_long_try_cmpxchg_acquire(p,old,v) \
 __atomic_compare_exchange_n(&(p)->counter,(old),(v),false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)
#define xchg(p,v) __atomic_exchange_n((p),(v),__ATOMIC_SEQ_CST)
#define this_cpu_ptr(p) (p)
#define smp_processor_id() 0
static void lockdep_assert_preemption_disabled(void) { assert(pins == 1); }
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
 assert(pins == 1 && ++polls < 8192);
 switch (action) {
 case FREE_OWNER: lock.owner.counter=0; break;
 case RESCHED: resched=true; break;
 case OWNER_OFF_CPU: tasks[1].on_cpu=false; break;
 case ADD_WAITERS: lock.owner.counter |= KD_OWNED_MUTEX_FLAG_WAITERS; break;
 case ADD_SUCCESSOR:
  successor=(struct kd_owned_osq_node){.prev=&kd_owned_osq_nodes,.cpu=2};
  kd_owned_osq_nodes.next=&successor; lock.osq.tail.counter=2;
  lock.owner.counter=0; break;
 case NONE: return;
 }
 action=NONE;
}
static void preempt_disable(void) { assert(!pins); pins=1; }
static void preempt_enable(void) { assert(pins==1); pins=0; }
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
static bool kd_owned_osq_lock_bounded(struct optimistic_spin_queue *osq, unsigned int *remaining)
{ (void)osq;(void)remaining;assert(false);return false; }
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
 memset(&request,0xa5,sizeof(request));
 resched=cas_race=owned_mutex_self_route=task_active=false;
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
  assert(lock.owner.counter==owner && !polls && !releases && !lock.osq.tail.counter);
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
int main(void)
{
 check_cleanup(); check_refusals_and_bounds(); check_gate(); check_prepared(); check_capture_first();
 puts("PASS owned preflight: production OSQ cleanup, once-only admission, prepared eligibility/refusals, capture-boundary transitions and reference/resource cleanup");
 return 0;
}
