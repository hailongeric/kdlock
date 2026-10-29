// SPDX-License-Identifier: GPL-2.0
/* Actual origin wait/claim helpers with deterministic CAS and scheduler peers.
 * No kernel, timer or hardware memory model runs in this fixture. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef uint8_t u8;
struct kd_mutex_node { int tail; u8 locked; };
struct kd_mutex { unsigned int gate; };
#define KD_MUTEX_TAIL_CPU_OFFSET 8
#define KDLOCK_MUTEX_SPIN_BUDGET 8
#define CHECK(value) do { if (!(value)) { \
 fprintf(stderr, "FAIL proxy pin line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)
#define BUG_ON(value) CHECK(!(value))
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define smp_load_acquire(word) __atomic_load_n((word), __ATOMIC_ACQUIRE)
#define smp_store_release(word,value) __atomic_store_n((word),(value),__ATOMIC_RELEASE)

enum route { EARLY_DONE, EXPIRE, CLAIM_RACE, WAKE_RACE, CANCEL, CANCEL_AT_ENTRY,
 CLAIMED_AT_ENTRY, DONE_AT_ENTRY, WAKE_AT_UNPIN, NO_RESCHED, EXECUTOR, PHYSICAL };
static enum route route;
static struct kd_mutex_node node;
static struct kd_mutex lock;
static unsigned int pins, migration, pauses, schedules, need_checks, acquired;
static unsigned int pin_calls, unpin_calls, publish_attempts, publications;
static unsigned int claim_attempts, claims, withdraw_attempts, withdrawals;
static bool raced, executor;
static int cpu;
static void preempt_disable(void) { CHECK(!pins && migration==1);pins++;pin_calls++; }
static void preempt_enable(void);
static int raw_smp_processor_id(void) { return cpu; }
static bool need_resched(void);
static void cond_resched(void);
static unsigned int kd_mutex_gate_read(struct kd_mutex *value)
{ CHECK(value==&lock);return value->gate; }
static bool kd_mutex_gate_trylock(struct kd_mutex *value)
{ CHECK(value==&lock && !pins && !value->gate);value->gate=2;return true; }
static void kd_mutex_claim_origin_node(struct kd_mutex *value,struct kd_mutex_node *request)
{ CHECK(value==&lock && request==&node && !pins && value->gate==2);acquired++;value->gate=1; }
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
 if(route!=PHYSICAL) CHECK(node.locked==KD_MUTEX_WAIT || !node.locked);
 pins--;unpin_calls++;
 if(route==WAKE_AT_UNPIN) node.locked=0;
}
static void cond_resched(void)
{
 CHECK(!pins && migration==1);schedules++;
 if(route==PHYSICAL)lock.gate=0;
 else { CHECK(node.locked==KD_MUTEX_WAIT);node.locked=0; }
}
static u8 fixture_cas(u8 *word,u8 before,u8 after)
{
 CHECK(word==&node.locked && pins==1 && migration==1);
 if(before==KD_MUTEX_QUEUE_INIT) {
  CHECK(after==KD_MUTEX_PROXY_READY && !executor);publish_attempts++;
 } else if(after==KD_MUTEX_PROXY_CLAIMED) {
  CHECK(before==KD_MUTEX_PROXY_READY && executor);claim_attempts++;
 } else {
  CHECK(before==KD_MUTEX_PROXY_READY && after==KD_MUTEX_WAIT && !executor);
  CHECK(pauses>=KDLOCK_MUTEX_SPIN_BUDGET && need_checks);withdraw_attempts++;
  if(!raced && (route==CLAIM_RACE || route==WAKE_RACE)) {
   raced=true;
   if(route==CLAIM_RACE) {
    executor=true;CHECK(kd_mutex_proxy_request(&node));executor=false;
   } else node.locked=0;
  }
 }
 u8 seen=*word;
 if(seen==before) {
  *word=after;
  if(before==KD_MUTEX_QUEUE_INIT)publications++;
  else if(after==KD_MUTEX_PROXY_CLAIMED)claims++;
  else withdrawals++;
 }
 return seen;
}
static void peer_claim(void)
{
 executor=true;CHECK(kd_mutex_proxy_request(&node));executor=false;
 kd_mutex_proxy_assert_claimed(&node);
}
static bool need_resched(void)
{
 CHECK(migration==1);
 if(pins)CHECK(route!=PHYSICAL && pauses>=KDLOCK_MUTEX_SPIN_BUDGET);
 need_checks++;
 return route!=NO_RESCHED;
}
static void cpu_relax(void)
{
 CHECK(++pauses<=KDLOCK_MUTEX_SPIN_BUDGET+12 && migration==1);
 if(route==PHYSICAL) { CHECK(!pins);return; }
 if(!pins) { CHECK(node.locked==KD_MUTEX_WAIT);return; }
 CHECK(node.locked==KD_MUTEX_PROXY_READY || node.locked==KD_MUTEX_PROXY_CLAIMED);
 if(route==EARLY_DONE || (route==NO_RESCHED && pauses==KDLOCK_MUTEX_SPIN_BUDGET+2)) {
  peer_claim();node.locked=0;
 } else if(route==CANCEL) {
  if(node.locked==KD_MUTEX_PROXY_READY)peer_claim();
  else node.locked=KD_MUTEX_WAIT; /* Executor ended all proxy accesses. */
 } else if((route==CLAIM_RACE && raced) || route==CLAIMED_AT_ENTRY) {
  CHECK(node.locked==KD_MUTEX_PROXY_CLAIMED);node.locked=0;
 }
}
static void reset(enum route selected)
{
 route=selected;pins=migration=1;cpu=1;node.tail=3<<KD_MUTEX_TAIL_CPU_OFFSET;
 node.locked=KD_MUTEX_QUEUE_INIT;lock.gate=1;
 pauses=schedules=need_checks=acquired=pin_calls=unpin_calls=0;
 publish_attempts=publications=claim_attempts=claims=withdraw_attempts=withdrawals=0;
 raced=executor=false;
}
static void wait_case(enum route selected,u8 initial)
{
 reset(selected);node.locked=initial;kd_mutex_wait_for_result(&node);
 CHECK(pins==1 && migration==1 && !node.locked);
 CHECK(pin_calls==unpin_calls && publish_attempts==1);
 CHECK(publications==(initial==KD_MUTEX_QUEUE_INIT));
}
int main(void)
{
 wait_case(EARLY_DONE,KD_MUTEX_QUEUE_INIT);
 CHECK(claims==1 && pauses==1 && !need_checks && !schedules && !unpin_calls);
 wait_case(EXPIRE,KD_MUTEX_QUEUE_INIT);
 CHECK(withdraw_attempts==1 && withdrawals==1 && pauses>=KDLOCK_MUTEX_SPIN_BUDGET);
 CHECK(schedules==1 && pin_calls==1 && !claims);
 wait_case(CLAIM_RACE,KD_MUTEX_QUEUE_INIT);
 CHECK(claims==1 && withdraw_attempts==1 && !withdrawals && !unpin_calls && !schedules);
 wait_case(WAKE_RACE,KD_MUTEX_QUEUE_INIT);
 CHECK(withdraw_attempts==1 && !withdrawals && !unpin_calls && !schedules);
 wait_case(CANCEL,KD_MUTEX_QUEUE_INIT);
 CHECK(claims==1 && !withdraw_attempts && unpin_calls==1 && schedules==1);
 wait_case(CANCEL_AT_ENTRY,KD_MUTEX_WAIT);
 CHECK(!publications && !claims && !withdraw_attempts && unpin_calls==1 && schedules==1);
 wait_case(CLAIMED_AT_ENTRY,KD_MUTEX_PROXY_CLAIMED);
 CHECK(!publications && !claim_attempts && !need_checks && !unpin_calls);
 wait_case(DONE_AT_ENTRY,0);
 CHECK(!publications && !pauses && !need_checks && !unpin_calls);
 wait_case(WAKE_AT_UNPIN,KD_MUTEX_QUEUE_INIT);
 CHECK(withdrawals==1 && pin_calls==1 && !schedules && !node.locked);
 wait_case(NO_RESCHED,KD_MUTEX_QUEUE_INIT);
 CHECK(need_checks>=2 && claims==1 && !withdraw_attempts && !unpin_calls);
 for(unsigned int state=0;state<=KD_MUTEX_QUEUE_INIT;state++) {
  reset(EXECUTOR);node.locked=state;executor=true;
  CHECK(kd_mutex_proxy_request(&node)==(state==KD_MUTEX_PROXY_READY));
  CHECK(claim_attempts==1 && claims==(state==KD_MUTEX_PROXY_READY) && !pauses);
  CHECK(node.locked==(state==KD_MUTEX_PROXY_READY?KD_MUTEX_PROXY_CLAIMED:state));
 }
 reset(EXECUTOR);executor=true;node.locked=KD_MUTEX_PROXY_READY;
 node.tail=(cpu+1)<<KD_MUTEX_TAIL_CPU_OFFSET;
 CHECK(!kd_mutex_proxy_request(&node) && !claim_attempts && !pauses);
 reset(PHYSICAL);node.locked=KD_MUTEX_WAIT;
 kd_mutex_wait_and_lock_node(&lock,&node);
 CHECK(pins==1 && migration==1 && schedules==1 && acquired==1 && lock.gate==1);
 CHECK(pin_calls==1 && unpin_calls==1);
 puts("PASS production READY pin: initial grace, both claim/expiry winners, wake/cancel races, no rearm, balanced pins and nonblocking claims");
 return 0;
}
