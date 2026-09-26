/* Admission observes the acquisition pin; every fallback retains it until
 * the real public unlock router runs. Count calls, not merely final balance. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
typedef uint32_t u32;
struct qspinlock { union { u32 val; unsigned char locked; }; };
typedef struct qspinlock kd_spinlock_t;
typedef struct qspinlock raw_spinlock_t;
struct task_struct { bool migration_disabled; } task;
#define current (&task)
struct kd_spin_ref { int entry; };
struct kd_spin_request { struct kd_spin_ref ref; struct qspinlock *word; };
enum { FAST, COLD, OFF, IRQ, SOFTIRQ, MIGRATE, BUSY, FRAME, NATIVE_ACTIVE,
       TICKET_FULL, PENDING, PENDING_ONLY, PENDING_RACE, PENDING_FOREIGN,
       QUEUED, NOT_READY, NESTED, NESTED_PENDING, NESTED_QUEUED, CASES };
static int scenario, pins, initial, disables, enables, samples, ticket, reservations, claims, clears;
static unsigned int physical_entries;
static bool kd_spin_delegate;
static void pinned(void) { assert(pins == initial + 1 && disables == 1 && !enables); }
#define preempt_disable() do { ++pins; ++disables; } while (0)
#define preempt_enable() do { assert(pins); --pins; ++enables; } while (0)
#define preempt_count() pins
#define PREEMPT_MASK 255
#define in_task() (scenario != IRQ)
#define softirq_count() (scenario == SOFTIRQ)
#define DECLARE_PER_CPU(type, name) type name
#define raw_cpu_ptr(p) (p)
#define this_cpu_inc(x) (++(x))
#define this_cpu_dec(x) (--(x))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define smp_store_release(p,v) (*(p)=(v))
#define for_each_possible_cpu(cpu) for ((cpu)=0;(cpu)<1;(cpu)++)
#define per_cpu(x,cpu) (x)
#define BUG_ON(x) assert(!(x))
#define likely(x) (x)
#define unlikely(x) (x)
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define _Q_LOCKED_VAL_HL 1U
#define KD_SPIN_DIRECT_NATIVE_HELD 5U
#define _Q_LOCKED_MASK_HL 255U
#define _Q_PENDING_VAL_HL 256U
#define _Q_PENDING_MASK_HL 256U
#define _Q_PENDING_LOOPS_HL 1U
#define atomic_cond_read_relaxed(p,c) ({ u32 VAL=0; *(p)=0; assert(c); VAL; })
#define atomic_cond_read_acquire(p,c) atomic_cond_read_relaxed(p,c)
static u32 atomic_cmpxchg_acquire(u32 *p,u32 old,u32 val)
{ pinned(); u32 found=*p; if(found==old) *p=val; return found; }
static bool kd_hotlock_record_spin_pinned(unsigned long addr)
{ assert(addr); pinned(); samples++; return scenario != COLD; }
/* Every entry, including policy refusal, records once under the same pin. */
static void kd_hotlock_spin_entry_pinned(void)
{ pinned(); physical_entries++; }
static bool kd_spin_entry_native_active(void) { pinned(); return scenario == NATIVE_ACTIVE; }
static bool kd_exec_context_occupied(void)
{ pinned(); return scenario == FRAME || scenario == BUSY; }
static int kd_spin_entry_begin_pinned(raw_spinlock_t *lock, struct kd_spin_ref *ref)
{ (void)lock; pinned(); reservations++; if(scenario==TICKET_FULL) return -1; ref->entry=ticket=1; return 0; }
static u32 kd_spin_fetch_set_pending_acquire(struct qspinlock *lock)
{
 pinned();
 /* Tail can appear after the initial CAS. A foreign pending bit must survive;
  * clear only the pending bit introduced by this acquisition. */
 if(scenario==PENDING_RACE) lock->val=65537;
 if(scenario==PENDING_FOREIGN) lock->val=65793;
 u32 old=lock->val; lock->val |= 256U; return old;
}
static void clear_pending(struct qspinlock *lock) { pinned(); clears++; lock->val &= ~256U; }
static void clear_pending_set_locked(struct qspinlock *lock) { pinned(); lock->val=1; }
static void *kd_get_exe(int pid,unsigned long ip) { (void)pid; (void)ip; pinned(); return NULL; }
static bool kd_exe_entry_is_ready(void *exe,int pid,unsigned long ip)
{ (void)exe; (void)pid; (void)ip; pinned(); return scenario != NOT_READY; }
#define KD_EXE_LOCK_SPIN 1
#define KD_ENTRY_ABI_SPIN_CLOBBER_V1 1
static void kd_exe_add_abi(int pid,unsigned long ip,int kind,unsigned int abi)
{ (void)pid; (void)ip; (void)kind; (void)abi; pinned(); }
static void kd_spin_acquire_nondelegated(kd_spinlock_t *lock) { pinned(); lock->val=1; }
static void kd_spin_lock_slowpath(struct qspinlock *lock,unsigned long sp,
 struct kd_spin_request *r,unsigned long ip,unsigned long bp,unsigned int abi)
{ (void)sp; (void)ip; (void)bp; (void)abi; pinned();
  assert(r->ref.entry); claims++; lock->val=1; }
static void kd_spin_claim_origin(struct kd_spin_request *r) { pinned(); claims++; assert(r->ref.entry); }
static bool kd_exec_native_unlock(unsigned long addr,bool mutex)
{ (void)addr; (void)mutex; pinned(); return false; }
static bool kd_spin_entry_find(raw_spinlock_t *lock,struct kd_spin_ref *r)
{ (void)lock; pinned(); r->entry=ticket; return ticket; }
static void kd_spin_unlock_ref(struct qspinlock *lock,const struct kd_spin_ref *r)
{ pinned(); assert(r->entry && ticket); lock->val=0; ticket=0; preempt_enable(); }
#include "spin_preempt_api.h"
int main(void)
{
 for(int entry=0;entry<3;entry++)
 for(scenario=0;scenario<CASES;scenario++) {
  kd_spinlock_t lock={0};
  memset(&kd_spin_fast_cpu,0,sizeof(kd_spin_fast_cpu));
  initial=pins=scenario>=NESTED ? 2 : 0;
  disables=enables=samples=ticket=reservations=claims=clears=0;
  physical_entries=0;
  kd_spin_delegate=scenario!=OFF;
  task.migration_disabled=scenario==MIGRATE;
  if(scenario==PENDING || scenario==PENDING_RACE ||
     scenario==PENDING_FOREIGN || scenario==NESTED_PENDING) lock.val=1;
  if(scenario==PENDING_ONLY) lock.val=256;
  if(scenario==TICKET_FULL || scenario==QUEUED || scenario==NOT_READY ||
     scenario==NESTED_QUEUED) lock.val=65537;
  if(entry==0) kd_spin_lock_abi(&lock,0,0,0,1);
  else if(entry==1) kd_spin_lock_clobber_v1(&lock,0,0,0);
  else {
   preempt_disable(); /* The inline gate already owns this one pin. */
   kd_spin_lock_pinned_clobber_v1(&lock,0,0,0);
  }
  pinned(); assert(lock.locked==1 && samples==(scenario!=OFF));
  assert(physical_entries==1);
  bool needs_ticket=scenario==QUEUED || scenario==NOT_READY ||
      scenario==PENDING_RACE || scenario==PENDING_FOREIGN || scenario>=NESTED;
  assert(reservations == (needs_ticket || scenario==TICKET_FULL));
  assert(ticket == needs_ticket && claims == needs_ticket);
  assert(clears == (scenario==PENDING_RACE));
  if(entry==0) kd_spin_unlock(&lock);
  else kd_spin_unlock_clobber_v1(&lock,0,0,0);
  assert(pins==initial && disables==1 && enables==1 && !lock.locked && !ticket);
  assert(physical_entries==1); /* Native fallback and unlock never recount. */
  assert(kd_spin_fast_idle());
 }
 puts("PASS preemption: entry pinned before admission, 3 entries x 19 routes retain one pin; sole pending skips tickets; queued/nested preserve tickets");
}
