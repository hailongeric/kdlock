/* SPDX-License-Identifier: GPL-2.0 */
/* Production router/gate/release decisions; physical queues and native records
 * below are controlled substitutes, not a second implementation of their ABI. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint32_t u32;
typedef struct { int counter; } atomic_t;
typedef struct { unsigned long counter; } atomic_long_t;
typedef int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct task_struct { int id; } __attribute__((aligned(8)));
#include "mutex_unlock_types.h"

#define CHECK(c) do { if (!(c)) { \
 fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
#define BUG_ON(c) CHECK(!(c))
#define WARN_ON_ONCE(c) ({ bool bad = !!(c); if (bad) errors++; bad; })
#define atomic_long_read(p) ((p)->counter)
#define atomic_read_acquire(p) ((p)->counter)
#define atomic_set_release(p,v) do { (p)->counter = (v); gate_stores++; } while (0)
#define atomic_cmpxchg(p,o,v) fixture_cmpxchg(p,o,v)
#define this_cpu_inc(v) (++(v))
#define _RET_IP_ 0x9000UL

static struct task_struct origin = { 1 }, executor = { 2 };
static struct task_struct *current = &origin;
static struct kd_mutex locks[3];
static unsigned int refs, task_queries, task_puts, native_queries, requests, acks;
static unsigned int releases, gate_stores, errors, mixed_pins, claims;
static unsigned long kd_mutex_origin_releases;
static bool claim_before_physical, pickup_probe;
struct record {
 struct kd_mutex *lock;
 bool outer, transferred, spin, released;
};
static struct record records[2];

static int fixture_cmpxchg(atomic_t *state, int old, int next)
{
 int seen = state->counter;
 if (seen == old) state->counter = next;
 return seen;
}
static void kd_origin_mutex_unlock(struct kd_mutex *lock, unsigned long ip);
static bool kd_mutex_task_reroute(struct task_struct *task);
static void kd_mutex_task_put(struct task_struct *task);
static bool kd_exec_native_unlock(unsigned long addr, bool mutex);
#include "mutex_unlock_actual.h"

static void kd_origin_mutex_unlock(struct kd_mutex *lock, unsigned long ip)
{
 (void)ip;
 CHECK((lock->owner.counter & ~KD_MUTEX_OWNER_FLAGS) == (unsigned long)current);
 CHECK(!(lock->owner.counter & 4UL));
 if (claim_before_physical) {
  /* A different delegation head wins the real gate CAS after the router's
   * FREE observation, while this task still owns physical exclusion. */
  claim_before_physical = false;
  CHECK(kd_mutex_gate_trylock(lock));
  claims++;
 }
 lock->owner.counter = 0;
 releases++;
}
static bool kd_mutex_task_reroute(struct task_struct *task)
{
 CHECK(task == current);
 task_queries++;
 return refs != 0;
}
static void kd_mutex_task_put(struct task_struct *task)
{
 CHECK(task == current && refs);
 task_puts++;
 refs--;
}
static bool records_live(void)
{
 for (unsigned int i = 0; i < 2; i++)
  if (records[i].lock && !records[i].released) return true;
 return false;
}
static void record_ack(struct record *record)
{
 CHECK(record->lock && !record->released);
 record->released = true;
 acks++;
 if (!records_live()) kd_mutex_task_put(current);
}
static bool kd_exec_native_unlock(unsigned long addr, bool mutex)
{
 CHECK(mutex && current == &origin);
 native_queries++;
 if (pickup_probe) {
  /* Synthetic pre-acquisition boundary: it must not take the local bypass.
   * A real owner consumes PICKUP before issuing a valid public unlock. */
  CHECK(addr == (unsigned long)&locks[0] && (locks[0].owner.counter & 4UL));
  return true;
 }
 for (unsigned int i = 0; i < 2; i++) {
  struct record *record = &records[i];
  if ((unsigned long)record->lock != addr || record->released || record->spin)
   continue;
  requests++;
  if (record->transferred) {
   CHECK(record->outer && kd_mutex_gate_read(record->lock) == KD_MUTEX_GATE_COMBINER);
   CHECK(!_kd_mutex_unlock_checked(record->lock));
  } else {
   CHECK((record->lock->owner.counter & ~KD_MUTEX_OWNER_FLAGS) == (unsigned long)&executor);
   current = &executor;
   if (record->outer) CHECK(!_kd_mutex_unlock_checked(record->lock));
   else kd_origin_mutex_unlock(record->lock, _RET_IP_);
   current = &origin;
  }
  /* ACK is observed only after the exact owner has completed release. The
   * real publication/wait/retirement functions have their separate fixture. */
  CHECK(!record->lock->owner.counter);
  if (record->outer) CHECK(kd_mutex_gate_read(record->lock) == KD_MUTEX_GATE_FREE);
  record_ack(record);
  return true;
 }
 return false;
}
static void reset(void)
{
 memset(locks, 0, sizeof(locks));
 memset(records, 0, sizeof(records));
 current = &origin;
 refs = task_queries = task_puts = native_queries = requests = acks = 0;
 releases = gate_stores = errors = mixed_pins = claims = 0;
 kd_mutex_origin_releases = 0;
 claim_before_physical = pickup_probe = false;
}
static void own(struct kd_mutex *lock, struct task_struct *task, u32 phase,
                unsigned long flags)
{
 lock->owner.counter = (unsigned long)task | flags;
 lock->delegation_state.counter = (int)phase;
}
static void release(struct kd_mutex *lock)
{
 __kd_mutex_unlock(lock, 0x8000, _RET_IP_);
 CHECK(!errors && current == &origin);
}
static void check_local(void)
{
 /* WAITERS/HANDOFF still go through the existing physical primitive. Its
  * queue behavior is substituted here; this checks only routing eligibility. */
 for (unsigned long flags = 0; flags < 4; flags++) {
  reset();
  own(&locks[0], current, KD_MUTEX_GATE_FREE, flags);
  release(&locks[0]);
  CHECK(!locks[0].owner.counter && releases == 1 && !gate_stores);
  CHECK(!task_queries && !native_queries && !task_puts && !refs);
 }
 for (unsigned int race = 0; race < 2; race++) {
  reset();
  own(&locks[0], &executor, KD_MUTEX_GATE_COMBINER, 0);
  records[0] = (struct record){ .lock = &locks[0], .outer = true };
  records[1] = (struct record){ .lock = &locks[1], .spin = true };
  refs = mixed_pins = 1;
  own(&locks[2], current, KD_MUTEX_GATE_FREE, 0);
  claim_before_physical = race;
  release(&locks[2]);
  CHECK(!task_queries && !native_queries && !task_puts && refs == 1);
  CHECK(!gate_stores && mixed_pins == 1 && !records[0].released && !records[1].released);
  CHECK(locks[0].owner.counter == (unsigned long)&executor);
  CHECK(kd_mutex_gate_read(&locks[0]) == KD_MUTEX_GATE_COMBINER);
  CHECK(kd_mutex_gate_read(&locks[2]) == (race ? KD_MUTEX_GATE_ACQUIRING : KD_MUTEX_GATE_FREE));
  CHECK(claims == race && releases == 1);
 }
}
static void check_gate_routes(void)
{
 const u32 phases[] = { KD_MUTEX_GATE_HELD, KD_MUTEX_GATE_COMBINER,
                        KD_MUTEX_GATE_ACQUIRING, KD_MUTEX_GATE_RELEASING };
 for (unsigned int i = 0; i < sizeof(phases) / sizeof(phases[0]); i++) {
  reset();
  own(&locks[0], current, phases[i], 0);
  refs = 1;
  release(&locks[0]);
  CHECK(task_queries == 1 && native_queries == 1 && releases == 1);
  if (i < 2) {
   CHECK(!refs && task_puts == 1 && gate_stores == 2);
   CHECK(kd_mutex_origin_releases == 1 && kd_mutex_gate_read(&locks[0]) == KD_MUTEX_GATE_FREE);
  } else {
   /* This is another gate owner's acquisition or release window. */
   CHECK(refs == 1 && !task_puts && !gate_stores && !kd_mutex_origin_releases);
   CHECK(kd_mutex_gate_read(&locks[0]) == phases[i]);
  }
 }
 reset();
 own(&locks[0], current, KD_MUTEX_GATE_FREE, 4UL);
 refs = 1;
 pickup_probe = true;
 release(&locks[0]);
 CHECK(task_queries == 1 && native_queries == 1 && !releases && !gate_stores);
 CHECK(refs == 1 && !task_puts && (locks[0].owner.counter & 4UL));
}
static void check_native_routes(void)
{
 for (unsigned int scenario = 0; scenario < 3; scenario++) {
  reset();
  bool transferred = scenario == 2;
  bool outer = scenario != 0;
  own(&locks[0], transferred ? &origin : &executor,
      outer ? KD_MUTEX_GATE_COMBINER : KD_MUTEX_GATE_FREE, 0);
  records[0] = (struct record){ .lock = &locks[0], .outer = outer,
                                .transferred = transferred };
  refs = 1;
  release(&locks[0]);
  CHECK(task_queries == 1 && native_queries == 1 && requests == 1 && acks == 1);
  CHECK(records[0].released && !refs && task_puts == 1 && releases == 1);
  CHECK(gate_stores == (outer ? 2U : 0U));
 }
}
static void check_early_outer(void)
{
 for (unsigned int spin = 0; spin < 2; spin++) {
  reset();
  own(&locks[0], &executor, KD_MUTEX_GATE_COMBINER, 0);
  own(&locks[1], &executor, KD_MUTEX_GATE_FREE, 0);
  records[0] = (struct record){ .lock = &locks[0], .outer = true };
  records[1] = (struct record){ .lock = &locks[1], .spin = spin };
  refs = 1;
  mixed_pins = spin;
  release(&locks[0]);
  CHECK(records[0].released && !records[1].released && refs == 1 && !task_puts);
  CHECK(requests == 1 && acks == 1 && mixed_pins == spin);
  /* A's old record is already released. A new independent local acquisition
   * must not consume the still-live borrowed B or its logical spin pin. */
  own(&locks[0], current, KD_MUTEX_GATE_FREE, 0);
  release(&locks[0]);
  CHECK(task_queries == 1 && native_queries == 1 && requests == 1 && acks == 1);
  CHECK(releases == 2 && gate_stores == 2 && refs == 1 && !task_puts && mixed_pins == spin);
  if (spin) {
   /* Stand-in for spin's separate exact ticket retirement/ACK endpoint. */
   CHECK(records[1].spin && mixed_pins == 1);
   record_ack(&records[1]);
   mixed_pins--;
  } else release(&locks[1]);
  CHECK(!records_live() && !refs && task_puts == 1 && acks == 2 && !mixed_pins);
 }
}
int main(void)
{
 check_local();
 check_gate_routes();
 check_native_routes();
 check_early_outer();
 puts("mutex unlock: local, unrelated/mixed, gate race, borrowed, transferred and early-outer routes passed");
 return 0;
}
