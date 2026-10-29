// SPDX-License-Identifier: GPL-2.0
/* Actual origin wait/claim helpers with deterministic CAS and scheduler peers.
 * No kernel, timer or hardware memory model runs in this fixture. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
struct task_struct { int id; };
struct kd_mutex { atomic_t delegation_state; struct task_struct *owner; };
struct kd_mutex_node { int tail; u8 locked; struct kd_mutex *lock, *counted_lock; u64 count_seq; };
#define U64_MAX UINT64_MAX
#define smp_wmb() __atomic_thread_fence(__ATOMIC_RELEASE)
#define KD_MUTEX_TAIL_CPU_OFFSET 8
#define KDLOCK_MUTEX_SPIN_BUDGET 8
static void failure_context(void);
#define CHECK(value) do { if (!(value)) { \
 fprintf(stderr, "FAIL proxy pin line %d: %s\n", __LINE__, #value); failure_context(); exit(1); \
} } while (0)
#define BUG_ON(value) CHECK(!(value))
#define unlikely(value) __builtin_expect(!!(value), 0)
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
static void observe_claim(const void *word, unsigned int value);
static __attribute__((noinline)) u8 node_acquire(const u8 *word);
#define smp_load_acquire(word) node_acquire(word)
#define smp_store_release(word,value) do { observe_claim((word),(value)); __atomic_store_n((word),(value),__ATOMIC_RELEASE); } while(0)
#define WRITE_ONCE(value,after) __atomic_store_n(&(value),(after),__ATOMIC_RELAXED)
#define atomic_read(word) __atomic_load_n(&(word)->counter,__ATOMIC_RELAXED)
#define atomic_read_acquire(word) __atomic_load_n(&(word)->counter,__ATOMIC_ACQUIRE)
static int gate_cas(atomic_t *word,int before,int after);
static int gate_clear(unsigned int mask,atomic_t *word);
#define atomic_cmpxchg(word,before,after) gate_cas((word),(before),(after))
#define atomic_fetch_andnot_release(mask,word) gate_clear((mask),(word))

enum route { EARLY_DONE, EXPIRE, CLAIM_RACE, WAKE_RACE, CANCEL, CANCEL_AT_ENTRY,
 CLAIMED_AT_ENTRY, DONE_AT_ENTRY, WAKE_AT_UNPIN, NO_RESCHED, EXECUTOR, PHYSICAL, RELEASE_RACE, STALE_READY, READY_EPOCH };
static enum route route;
static struct kd_mutex_node node;
static struct kd_mutex lock;
static struct task_struct owner={1};
static struct task_struct *current=&owner;
static unsigned int pins, migration, pauses, schedules, need_checks, acquired;
static unsigned int pin_calls, unpin_calls, publish_attempts, publications;
static unsigned int claim_attempts, claims, withdraw_attempts, withdrawals;
static unsigned int last_cas_before, last_cas_after, last_cas_seen;
static bool raced, executor;
static int cpu;
static void failure_context(void)
{
 fprintf(stderr,"proxy context route=%u node=%u gate=%u pins=%u migration=%u pauses=%u checks=%u last_node_cas=%u/%u/%u\n",
         (unsigned int)route,(unsigned int)node.locked,(unsigned int)lock.delegation_state.counter,
         pins,migration,pauses,need_checks,last_cas_before,last_cas_after,last_cas_seen);
}
static void preempt_disable(void) { CHECK(!pins && migration==1);pins++;pin_calls++; }
static void preempt_enable(void);
static inline int raw_smp_processor_id(void) { return cpu; }
static bool need_resched(void);
static void cond_resched(void);
static bool kd_mutex_delegation_owned(struct kd_mutex *value,struct task_struct *task)
{ return value==&lock && value->owner==task; }
static void kd_mutex_claim_origin_node(struct kd_mutex *value,struct kd_mutex_node *request);
static void cpu_relax(void);
static u8 fixture_cas(u8 *word,u8 before,u8 after);
#define cmpxchg(word,before,after) fixture_cas((word),(before),(after))
#define cmpxchg_acquire(word,before,after) fixture_cas((word),(before),(after))
#include "proxy_production.h"

/* The generated header supplies the actual queue state definitions. Keep the
 * scheduler mocks below it while their declarations remain visible to helpers. */
static void preempt_enable(void)
{
 CHECK(pins==1 && migration==1);
 CHECK(!(atomic_read(&lock.delegation_state)&KD_MUTEX_GATE_WITHDRAW));
 if(route!=PHYSICAL) CHECK(node.locked==KD_MUTEX_WAIT || !node.locked);
 pins--;unpin_calls++;
 if(route==WAKE_AT_UNPIN) node.locked=0;
}
static void cond_resched(void)
{
 CHECK(!pins && migration==1);schedules++;
 if(route==PHYSICAL)kd_mutex_gate_set(&lock,KD_MUTEX_GATE_FREE);
 else { CHECK(node.locked==KD_MUTEX_WAIT);node.locked=0; }
}
static void kd_mutex_claim_origin_node(struct kd_mutex *value,struct kd_mutex_node *request)
{
 CHECK(value==&lock && request==&node && !pins && kd_mutex_gate_read(value)==KD_MUTEX_GATE_ACQUIRING);
 acquired++;kd_mutex_gate_set(value,KD_MUTEX_GATE_HELD);
}
static void observe_claim(const void *word,unsigned int value)
{
 CHECK(word==&node.locked && value==KD_MUTEX_PROXY_CLAIMED);
 CHECK(executor && pins==1 && migration==1 && node.locked==KD_MUTEX_PROXY_READY);
 CHECK(atomic_read(&lock.delegation_state)==KD_MUTEX_GATE_COMBINER);claims++;
}
/* Keep this simulated peer read as a call boundary. In the captured GCC 15.2
 * O2 fixture build, IPA inlining marked both complementary pointer-check call
 * paths unreachable; its later pass then emitted an unconditional state BUG.
 * The isolated noinline arm passes with unchanged production helpers and checks.
 * This annotation affects only the mock, not production compilation or flags. */
static __attribute__((noinline)) u8 node_acquire(const u8 *word)
{
 CHECK(word==&node.locked);
 if(executor)claim_attempts++;
 return __atomic_load_n(word,__ATOMIC_ACQUIRE);
}
static int gate_cas(atomic_t *word,int before,int after)
{
 CHECK(word==&lock.delegation_state && migration==1);
 if(!raced && route==CLAIM_RACE && (after&KD_MUTEX_GATE_WITHDRAW)) {
  raced=true;executor=true;
  CHECK(kd_mutex_gate_try_combine(&lock));
  CHECK(kd_mutex_proxy_request(&lock,&node));
  smp_store_release(&node.locked,KD_MUTEX_PROXY_CLAIMED);executor=false;
 }
 int seen=atomic_read(word);
 if(seen==before)__atomic_store_n(&word->counter,after,__ATOMIC_SEQ_CST);
 return seen;
}
static int gate_clear(unsigned int mask,atomic_t *word)
{
 CHECK(pins==1 && migration==1 && word==&lock.delegation_state);
 CHECK(mask==KD_MUTEX_GATE_WITHDRAW && (atomic_read(word)&mask));
 return __atomic_fetch_and(&word->counter,~mask,__ATOMIC_RELEASE);
}
static u8 fixture_cas(u8 *word,u8 before,u8 after)
{
 CHECK(word==&node.locked && pins==1 && migration==1);
 if(before==KD_MUTEX_QUEUE_INIT) {
  CHECK(after==KD_MUTEX_PROXY_READY && !executor);publish_attempts++;
 } else {
  CHECK(before==KD_MUTEX_PROXY_READY && after==KD_MUTEX_WAIT && !executor);
  CHECK(pauses>=KDLOCK_MUTEX_SPIN_BUDGET && need_checks);withdraw_attempts++;
  CHECK(atomic_read(&lock.delegation_state)&KD_MUTEX_GATE_WITHDRAW);
  CHECK(!kd_mutex_gate_try_combine(&lock)); /* Reservation winner skips proxying. */
  if(!raced && route==WAKE_RACE) { raced=true;node.locked=0; }
  if(route==RELEASE_RACE) {
   kd_mutex_gate_set(&lock,KD_MUTEX_GATE_RELEASING);
   kd_mutex_gate_set(&lock,KD_MUTEX_GATE_FREE);
   CHECK(atomic_read(&lock.delegation_state)==KD_MUTEX_GATE_WITHDRAW);
   CHECK(!kd_mutex_gate_trylock(&lock));
  }
 }
 u8 seen=*word;
 last_cas_before=before;last_cas_after=after;last_cas_seen=seen;
 if(seen==before) {
  *word=after;
  if(before==KD_MUTEX_QUEUE_INIT)publications++;
  else withdrawals++;
 }
 return seen;
}
static void peer_claim(void)
{
 executor=true;
 if(kd_mutex_gate_read(&lock)==KD_MUTEX_GATE_HELD)CHECK(kd_mutex_gate_try_combine(&lock));
 CHECK(kd_mutex_proxy_request(&lock,&node));
 /* Model the cold boundary only; ordinary readiness admission does not store. */
 smp_store_release(&node.locked,KD_MUTEX_PROXY_CLAIMED);executor=false;
 kd_mutex_proxy_assert_claimed(&node);
}
static bool need_resched(void)
{
 CHECK(migration==1);
 if(pins)CHECK(route!=PHYSICAL && pauses>=KDLOCK_MUTEX_SPIN_BUDGET);
 need_checks++;
 if(route==STALE_READY && !raced) {
  raced=true;peer_claim();kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);
 }
 return route!=NO_RESCHED;
}
static void cpu_relax(void)
{
 CHECK(++pauses<=KDLOCK_MUTEX_SPIN_BUDGET+12 && migration==1);
 if(route==PHYSICAL) { CHECK(!pins);return; }
 if(!pins) { CHECK(node.locked==KD_MUTEX_WAIT);return; }
 CHECK(node.locked==KD_MUTEX_PROXY_READY || node.locked==KD_MUTEX_PROXY_CLAIMED);
 if(route==READY_EPOCH) {
  if(pauses==1) {
   executor=true;CHECK(kd_mutex_gate_try_combine(&lock));
   CHECK(kd_mutex_proxy_request(&lock,&node));executor=false;
  }
  CHECK(node.locked==KD_MUTEX_PROXY_READY && !claims);
  if(pauses==KDLOCK_MUTEX_SPIN_BUDGET+2)node.locked=0;
 } else if(route==EARLY_DONE || (route==NO_RESCHED && pauses==KDLOCK_MUTEX_SPIN_BUDGET+2)) {
  peer_claim();node.locked=0;kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);
 } else if(route==CANCEL) {
  if(node.locked==KD_MUTEX_PROXY_READY)peer_claim();
  else { node.locked=KD_MUTEX_WAIT;kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD); } /* End every proxy access. */
 } else if(((route==CLAIM_RACE || route==STALE_READY) && raced) || route==CLAIMED_AT_ENTRY) {
  CHECK(node.locked==KD_MUTEX_PROXY_CLAIMED);node.locked=0;kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);
 }
}
static void reset(enum route selected)
{
 route=selected;pins=migration=1;cpu=1;node.tail=3<<KD_MUTEX_TAIL_CPU_OFFSET;
 node.locked=KD_MUTEX_QUEUE_INIT;node.lock=&lock;lock.owner=current;lock.delegation_state.counter=KD_MUTEX_GATE_HELD;
 pauses=schedules=need_checks=acquired=pin_calls=unpin_calls=0;
 publish_attempts=publications=claim_attempts=claims=withdraw_attempts=withdrawals=0;
 last_cas_before=last_cas_after=last_cas_seen=0;
 raced=executor=false;
}
static void wait_case(enum route selected,u8 initial)
{
 reset(selected);node.locked=initial;kd_mutex_wait_for_result(&node);
 CHECK(pins==1 && migration==1 && !node.locked);
 CHECK(pin_calls==unpin_calls && !publish_attempts && !publications);
}
int main(void)
{
 /* INIT belongs to an unlinked invocation, never to this observe-only loop. */
 if (getenv("KDLOCK_PROXY_INIT")) {
  reset(EARLY_DONE);
  kd_mutex_wait_for_result(&node);
  fprintf(stderr,"FAIL unpublished INIT unexpectedly returned\n");
  return 3;
 }
 wait_case(EARLY_DONE,KD_MUTEX_PROXY_READY);
 CHECK(claims==1 && pauses==1 && !need_checks && !schedules && !unpin_calls);
 wait_case(EXPIRE,KD_MUTEX_PROXY_READY);
 CHECK(withdraw_attempts==1 && withdrawals==1 && pauses>=KDLOCK_MUTEX_SPIN_BUDGET);
 CHECK(schedules==1 && pin_calls==1 && !claims);
 wait_case(CLAIM_RACE,KD_MUTEX_PROXY_READY);
 CHECK(claims==1 && !withdraw_attempts && !withdrawals && !unpin_calls && !schedules);
 wait_case(WAKE_RACE,KD_MUTEX_PROXY_READY);
 CHECK(withdraw_attempts==1 && !withdrawals && !unpin_calls && !schedules);
 wait_case(CANCEL,KD_MUTEX_PROXY_READY);
 CHECK(claims==1 && !withdraw_attempts && unpin_calls==1 && schedules==1);
 wait_case(CANCEL_AT_ENTRY,KD_MUTEX_WAIT);
 CHECK(!publications && !claims && !withdraw_attempts && unpin_calls==1 && schedules==1);
 wait_case(CLAIMED_AT_ENTRY,KD_MUTEX_PROXY_CLAIMED);
 CHECK(!publications && !claim_attempts && !need_checks && !unpin_calls);
 wait_case(DONE_AT_ENTRY,0);
 CHECK(!publications && !pauses && !need_checks && !unpin_calls);
 wait_case(WAKE_AT_UNPIN,KD_MUTEX_PROXY_READY);
 CHECK(withdrawals==1 && pin_calls==1 && !schedules && !node.locked);
 wait_case(NO_RESCHED,KD_MUTEX_PROXY_READY);
 CHECK(need_checks>=2 && claims==1 && !withdraw_attempts && !unpin_calls);
 wait_case(RELEASE_RACE,KD_MUTEX_PROXY_READY);
 CHECK(withdrawals==1 && pin_calls==1 && !atomic_read(&lock.delegation_state));
 wait_case(STALE_READY,KD_MUTEX_PROXY_READY);
 CHECK(claims==1 && withdraw_attempts==1 && !withdrawals && !unpin_calls);
 wait_case(READY_EPOCH,KD_MUTEX_PROXY_READY);
 CHECK(!claims && claim_attempts==1 && need_checks>=2 && !withdraw_attempts && !withdrawals && !unpin_calls && !schedules);
 kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);
 for(unsigned int state=0;state<=KD_MUTEX_QUEUE_INIT;state++) {
  reset(EXECUTOR);node.locked=state;executor=true;CHECK(kd_mutex_gate_try_combine(&lock));
  CHECK(kd_mutex_proxy_request(&lock,&node)==(state==KD_MUTEX_PROXY_READY));
  CHECK(claim_attempts==1 && !claims && !pauses);
  CHECK(node.locked==state);
 }
 reset(EXECUTOR);executor=true;node.locked=KD_MUTEX_PROXY_READY;CHECK(kd_mutex_gate_try_combine(&lock));
 node.tail=(cpu+1)<<KD_MUTEX_TAIL_CPU_OFFSET;
 CHECK(!kd_mutex_proxy_request(&lock,&node) && !claim_attempts && !pauses);
 reset(PHYSICAL);node.locked=KD_MUTEX_WAIT;
 kd_mutex_wait_and_lock_node(&lock,&node);
 CHECK(pins==1 && migration==1 && schedules==1 && acquired==1 && kd_mutex_gate_read(&lock)==KD_MUTEX_GATE_HELD);
 CHECK(pin_calls==1 && unpin_calls==1);
 puts("PASS production READY pin: initial grace, both claim/expiry winners, wake/cancel races, no rearm, balanced pins and gate epochs, read-only readiness admission, READY epoch completion, cold promotion and flag clearance before unpin");
 return 0;
}
