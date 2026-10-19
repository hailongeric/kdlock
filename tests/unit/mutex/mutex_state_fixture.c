/* SPDX-License-Identifier: GPL-2.0 */
/* Actual packed-state/owner code. Primitive callbacks expose adversarial
 * orderings; they do not model kernel sleeping, stack switching or weak memory. */
#include <errno.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "exe_info.h"

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
typedef struct { unsigned long counter; } atomic_long_t;
typedef int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct task_struct { int id; } __attribute__((aligned(8)));
#include "mutex_state_types.h"

#define CHECK(c) do { if (!(c)) { \
 fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
static _Thread_local bool expected_bug;
static _Thread_local jmp_buf bug_target;
#define BUG_ON(c) do { if (c) { \
 if (expected_bug) longjmp(bug_target, 1); \
 fprintf(stderr, "BUG line %d\n", __LINE__); exit(2); } } while (0)
#define U32_MAX UINT32_MAX
#define KD_MUTEX_OWNER_FLAGS 7UL
#define atomic_read(p) __atomic_load_n(&(p)->counter, __ATOMIC_SEQ_CST)
#define atomic_read_acquire(p) atomic_read(p)
#define atomic_set(p,v) __atomic_store_n(&(p)->counter, (v), __ATOMIC_SEQ_CST)
#define atomic_long_read(p) __atomic_load_n(&(p)->counter, __ATOMIC_SEQ_CST)
#define atomic_long_set(p,v) __atomic_store_n(&(p)->counter, (unsigned long)(v), __ATOMIC_SEQ_CST)
#define osq_lock_init(p) atomic_set(&(p)->tail, 0)
#define raw_spin_lock_init(p) (*(p) = 0)
#define this_cpu_inc(v) (++(v))
#define WARN_ON_ONCE(c) ({ bool bad = !!(c); if (bad) errors++; bad; })
#define _RET_IP_ 0x9000UL
static _Thread_local struct task_struct *current;
static struct task_struct delegated = { 1 }, ordinary = { 2 }, successor = { 3 };
static _Thread_local unsigned long rmw_calls;
static unsigned long kd_mutex_origin_acquires, kd_mutex_origin_releases;
static unsigned int errors;
static struct kd_mutex gate;
static _Thread_local unsigned int cas_interleave;
static bool acquiring_window, releasing_window, handoff_window;
static void before_cas(atomic_t *state);
static void after_cas(atomic_t *state, u32 value);
static int fixture_cmpxchg(atomic_t *state, int old, int value)
{
 before_cas(state);
 rmw_calls++;
 int expected = old;
 if (__atomic_compare_exchange_n(&state->counter, &expected, value, false,
                                 __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST))
  after_cas(state, (u32)value);
 return expected;
}
#define atomic_cmpxchg(p,o,v) fixture_cmpxchg(p,o,v)
#define atomic_fetch_add(v,p) (++rmw_calls, __atomic_fetch_add(&(p)->counter, (v), __ATOMIC_SEQ_CST))
#define atomic_fetch_sub(v,p) (++rmw_calls, __atomic_fetch_sub(&(p)->counter, (v), __ATOMIC_SEQ_CST))
static void kd_origin_mutex_lock(struct kd_mutex *lock);
static void kd_origin_mutex_unlock(struct kd_mutex *lock, unsigned long ip);
#include "mutex_state_actual.h"

static void before_cas(atomic_t *state)
{
 unsigned int action = cas_interleave;
 if (!action)
  return;
 CHECK(state == &gate.delegation_state);
 cas_interleave = 0;
 if (action == 1) kd_mutex_state_waiter_enter(&gate);
 else if (action == 2) kd_mutex_state_waiter_exit(&gate);
 else {
  CHECK(action == 3);
  kd_mutex_gate_set(&gate, KD_MUTEX_GATE_HELD);
 }
}
static void after_cas(atomic_t *state, u32 value)
{
 if (!handoff_window || state != &gate.delegation_state ||
     (value & KD_MUTEX_PHASE_MASK) != KD_MUTEX_GATE_FREE)
  return;
 CHECK(!atomic_long_read(&gate.owner));
 handoff_window = false;
 struct task_struct *saved = current;
 current = &successor;
 CHECK(kd_mutex_gate_trylock(&gate));
 kd_mutex_claim_origin(&gate);
 current = saved;
}
static void kd_origin_mutex_lock(struct kd_mutex *lock)
{
 CHECK(kd_mutex_gate_read(lock) == KD_MUTEX_GATE_ACQUIRING);
 if (acquiring_window) {
  acquiring_window = false;
  CHECK(current == &delegated && atomic_long_read(&lock->owner) == (unsigned long)&ordinary);
  current = &ordinary;
  /* T already owns the physical word while U reserves the delegation gate. */
  CHECK(!kd_mutex_delegation_owned(lock, current));
  CHECK(_kd_mutex_unlock_checked(lock) == -EINVAL);
  CHECK(kd_mutex_gate_read(lock) == KD_MUTEX_GATE_ACQUIRING);
  atomic_long_set(&lock->owner, 0); /* T's ordinary physical unlock. */
  current = &delegated;
 }
 CHECK(!atomic_long_read(&lock->owner));
 atomic_long_set(&lock->owner, current);
}
static void kd_origin_mutex_unlock(struct kd_mutex *lock, unsigned long ip)
{
 (void)ip;
 CHECK(atomic_long_read(&lock->owner) == (unsigned long)current);
 CHECK(kd_mutex_gate_read(lock) == KD_MUTEX_GATE_RELEASING);
 atomic_long_set(&lock->owner, 0);
 if (releasing_window) {
  releasing_window = false;
  struct task_struct *saved = current;
  current = &ordinary;
  atomic_long_set(&lock->owner, current); /* Next ordinary physical acquire. */
  CHECK(!kd_mutex_delegation_owned(lock, current));
  CHECK(_kd_mutex_unlock_checked(lock) == -EINVAL);
  CHECK(kd_mutex_gate_read(lock) == KD_MUTEX_GATE_RELEASING);
  atomic_long_set(&lock->owner, 0);
  current = saved;
 }
}
static void reset(void)
{
 kd_mutex_init(&gate);
 current = &delegated;
 rmw_calls = 0; errors = 0;
 kd_mutex_origin_acquires = kd_mutex_origin_releases = 0;
 acquiring_window = releasing_window = handoff_window = false;
 cas_interleave = 0;
}
static void expect_guard(unsigned int kind)
{
 expected_bug = true;
 if (!setjmp(bug_target)) {
  if (kind == 0) kd_mutex_state_waiter_enter(&gate);
  else if (kind == 1) kd_mutex_state_waiter_exit(&gate);
  else kd_mutex_gate_set(&gate, KD_MUTEX_GATE_RELEASING + 1);
  CHECK(false);
 }
 expected_bug = false;
}
static void check_layout_and_boundaries(void)
{
 CHECK(sizeof(struct kd_mutex) == 32 && _Alignof(struct kd_mutex) == 8);
 CHECK(offsetof(struct kd_mutex, owner) == 0 && offsetof(struct kd_mutex, wait_lock) == 8);
 CHECK(offsetof(struct kd_mutex, osq) == 12 && offsetof(struct kd_mutex, wait_head) == 16);
 CHECK(offsetof(struct kd_mutex, delegation_state) == 24 && offsetof(struct kd_mutex, delegation_tail) == 28);
 CHECK(sizeof(struct kd_mutex_node) == 320 && offsetof(struct kd_mutex_node, regs) == 128);
 CHECK(offsetof(struct kd_mutex_node, completed) == 304 && offsetof(struct kd_mutex_node, locked) == 305);
 for (u32 phase = 0; phase <= KD_MUTEX_GATE_RELEASING; phase++) {
  reset();
  kd_mutex_gate_set(&gate, phase);
  kd_mutex_state_waiter_enter(&gate);
  CHECK(kd_mutex_gate_read(&gate) == phase && kd_mutex_state_waiter_count(&gate) == 1);
  unsigned long before = rmw_calls;
  CHECK(kd_mutex_combiner_active(&gate) == (phase == KD_MUTEX_GATE_COMBINER));
  CHECK(!kd_mutex_delegation_owned(&gate, current));
  CHECK(rmw_calls == before); /* Observations must not acquire shared refs. */
  CHECK(kd_mutex_gate_trylock(&gate) == (phase == KD_MUTEX_GATE_FREE));
  CHECK(kd_mutex_state_waiter_count(&gate) == 1);
  kd_mutex_gate_set(&gate, KD_MUTEX_GATE_COMBINER);
  CHECK(kd_mutex_state_waiter_count(&gate) == 1);
  kd_mutex_state_waiter_exit(&gate);
  CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_COMBINER && !kd_mutex_state_waiter_count(&gate));
 }
 reset();
 atomic_set(&gate.delegation_state, ((KD_MUTEX_WAITER_MAX - 1) << 8) | KD_MUTEX_GATE_HELD);
 kd_mutex_state_waiter_enter(&gate);
 CHECK(kd_mutex_state_waiter_count(&gate) == (int)KD_MUTEX_WAITER_MAX);
 CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_HELD);
 expect_guard(0);
 reset(); expect_guard(1);
 reset(); unsigned long before = rmw_calls; expect_guard(2); CHECK(rmw_calls == before);
}
static void check_cas_interleavings(void)
{
 for (unsigned int change = 1; change <= 2; change++) {
  reset();
  kd_mutex_state_waiter_enter(&gate);
  cas_interleave = change;
  CHECK(kd_mutex_gate_trylock(&gate));
  CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_ACQUIRING);
  CHECK(kd_mutex_state_waiter_count(&gate) == (change == 1 ? 2 : 0));
  kd_mutex_state_waiter_enter(&gate);
  int count = kd_mutex_state_waiter_count(&gate);
  cas_interleave = change;
  kd_mutex_gate_set(&gate, KD_MUTEX_GATE_COMBINER);
  CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_COMBINER);
  CHECK(kd_mutex_state_waiter_count(&gate) == count + (change == 1 ? 1 : -1));
 }
 reset(); cas_interleave = 3;
 CHECK(!kd_mutex_gate_trylock(&gate));
 CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_HELD);
}
static void check_current_owner(void)
{
 reset();
 CHECK(!kd_mutex_delegation_owned(NULL, current) && !kd_mutex_combiner_active(NULL));
 for (u32 phase = 0; phase <= KD_MUTEX_GATE_RELEASING; phase++) {
  kd_mutex_gate_set(&gate, phase);
  bool owns = phase == KD_MUTEX_GATE_HELD || phase == KD_MUTEX_GATE_COMBINER;
  atomic_long_set(&gate.owner, current);
  CHECK(kd_mutex_delegation_owned(&gate, current) == owns);
  CHECK(!kd_mutex_delegation_owned(&gate, &ordinary));
  atomic_long_set(&gate.owner, &ordinary);
  CHECK(!kd_mutex_delegation_owned(&gate, current));
  for (unsigned long flags = 0; flags < 8; flags++) {
   atomic_long_set(&gate.owner, (unsigned long)current | flags);
   CHECK(kd_mutex_delegation_owned(&gate, current) == (owns && !(flags & 4)));
  }
 }
 reset();
 kd_mutex_state_waiter_enter(&gate);
 atomic_long_set(&gate.owner, &ordinary);
 acquiring_window = true;
 CHECK(kd_mutex_gate_trylock(&gate));
 kd_mutex_claim_origin(&gate);
 CHECK(kd_mutex_delegation_owned(&gate, current) && !acquiring_window && errors == 1);
 releasing_window = true;
 CHECK(!_kd_mutex_unlock_checked(&gate));
 CHECK(!releasing_window && errors == 2 && !atomic_long_read(&gate.owner));
 CHECK(!kd_mutex_gate_read(&gate) && kd_mutex_state_waiter_count(&gate) == 1);
 CHECK(kd_mutex_origin_acquires == 1 && kd_mutex_origin_releases == 1);
 kd_mutex_state_waiter_exit(&gate);
 reset();
 CHECK(kd_mutex_gate_trylock(&gate)); kd_mutex_claim_origin(&gate);
 handoff_window = true;
 CHECK(!_kd_mutex_unlock_checked(&gate));
 CHECK(!handoff_window && atomic_long_read(&gate.owner) == (unsigned long)&successor);
 CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_HELD);
 current = &successor; CHECK(!_kd_mutex_unlock_checked(&gate));
 CHECK(!atomic_long_read(&gate.owner) && !kd_mutex_gate_read(&gate));
}
#define WORKERS 8
static pthread_barrier_t rendezvous;
static void barrier(void)
{
 int result = pthread_barrier_wait(&rendezvous);
 CHECK(!result || result == PTHREAD_BARRIER_SERIAL_THREAD);
}
static void *count_worker(void *arg)
{
 (void)arg;
 barrier();
 kd_mutex_state_waiter_enter(&gate);
 barrier(); barrier();
 kd_mutex_state_waiter_exit(&gate);
 for (int i = 0; i < 10000; i++) {
  kd_mutex_state_waiter_enter(&gate);
  kd_mutex_state_waiter_exit(&gate);
 }
 return NULL;
}
static void check_concurrent_counts(void)
{
 pthread_t threads[WORKERS];
 reset();
 CHECK(!pthread_barrier_init(&rendezvous, NULL, WORKERS + 1));
 for (int i = 0; i < WORKERS; i++) CHECK(!pthread_create(&threads[i], NULL, count_worker, NULL));
 barrier(); barrier();
 CHECK(kd_mutex_state_waiter_count(&gate) == WORKERS);
 kd_mutex_gate_set(&gate, KD_MUTEX_GATE_COMBINER);
 CHECK(kd_mutex_state_waiter_count(&gate) == WORKERS);
 barrier();
 for (int i = 0; i < 10000; i++) kd_mutex_gate_set(&gate, i % 5);
 for (int i = 0; i < WORKERS; i++) CHECK(!pthread_join(threads[i], NULL));
 CHECK(!kd_mutex_state_waiter_count(&gate));
 kd_mutex_gate_set(&gate, KD_MUTEX_GATE_FREE);
 CHECK(!atomic_read(&gate.delegation_state));
 CHECK(!pthread_barrier_destroy(&rendezvous));
}
static struct kd_mutex objects[131072];
static void check_object_independence(void)
{
 /* More simultaneous embedded roots than the removed fixed registry held.
  * Acquisitions have no allocation/failure boundary or address lookup. */
 reset();
 for (size_t i = 0; i < sizeof(objects) / sizeof(*objects); i++) {
  kd_mutex_init(&objects[i]);
  CHECK(kd_mutex_gate_trylock(&objects[i]));
  kd_mutex_state_waiter_enter(&objects[i]);
 }
 for (size_t i = 0; i < sizeof(objects) / sizeof(*objects); i++) {
  CHECK(kd_mutex_gate_read(&objects[i]) == KD_MUTEX_GATE_ACQUIRING);
  CHECK(kd_mutex_state_waiter_count(&objects[i]) == 1);
  kd_mutex_state_waiter_exit(&objects[i]);
  kd_mutex_gate_set(&objects[i], KD_MUTEX_GATE_FREE);
  CHECK(!atomic_read(&objects[i].delegation_state));
 }
}
int main(void)
{
 check_layout_and_boundaries();
 check_cas_interleavings();
 check_current_owner();
 check_concurrent_counts();
 check_object_independence();
 puts("PASS embedded mutex state: 32 bytes/8 alignment; exact counts, CAS retries, owner phases, PICKUP, release handoff, 8 workers, 131072 independent roots");
 return 0;
}
