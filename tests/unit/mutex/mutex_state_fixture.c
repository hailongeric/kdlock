/* SPDX-License-Identifier: GPL-2.0 */
/* Actual phase/node-record/owner code. Primitive callbacks expose adversarial
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
/* This fixture exercises an ordinary path with no installed owner custody. */
#define DECLARE_PER_CPU(type, name) extern type name
#define raw_cpu_read(name) ((void)sizeof(name), 0UL)
#ifndef unlikely
#define unlikely(x) (x)
#endif
#include "mutex_state_types.h"

#define CHECK(c) do { if (!(c)) { \
 fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
static _Thread_local bool expected_bug;
static _Thread_local jmp_buf bug_target;
#define BUG_ON(c) do { if (c) { \
 if (expected_bug) longjmp(bug_target, 1); \
 fprintf(stderr, "BUG line %d: %s\n", __LINE__, #c); exit(2); } } while (0)
#define U64_MAX UINT64_MAX
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_SEQ_CST)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x), (v), __ATOMIC_SEQ_CST)
#define smp_wmb() __atomic_thread_fence(__ATOMIC_SEQ_CST)
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
static struct kd_mutex_node record;
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
#define atomic_cmpxchg_release(p,o,v) fixture_cmpxchg(p,o,v)
#define atomic_fetch_andnot_release(v,p) (++rmw_calls, __atomic_fetch_and(&(p)->counter, ~(u32)(v), __ATOMIC_SEQ_CST))
#define atomic_set_release(p,v) do { atomic_set(p,v); after_cas(p,v); } while (0)
#define atomic_fetch_add(v,p) (++rmw_calls, __atomic_fetch_add(&(p)->counter, (v), __ATOMIC_SEQ_CST))
#define atomic_fetch_sub(v,p) (++rmw_calls, __atomic_fetch_sub(&(p)->counter, (v), __ATOMIC_SEQ_CST))
static void kd_origin_mutex_lock(struct kd_mutex *lock);
static void kd_mutex_local_lock_node(struct kd_mutex *lock, struct kd_mutex_node *node)
{
 CHECK(!node);
 kd_origin_mutex_lock(lock);
}
static void kd_origin_mutex_unlock(struct kd_mutex *lock, unsigned long ip);
#include "mutex_state_actual.h"

static void before_cas(atomic_t *state)
{
 if (!cas_interleave)
  return;
 CHECK(state == &gate.delegation_state);
 unsigned int action = cas_interleave;
 cas_interleave = 0;
 if (action == 3) kd_mutex_gate_set(&gate, KD_MUTEX_GATE_HELD);
 else if (action == 4 || action == 6) CHECK(kd_mutex_gate_try_withdraw(&gate));
 else if (action == 5) CHECK(kd_mutex_gate_try_combine(&gate));
 else CHECK(false);
}
static void after_cas(atomic_t *state, u32 value)
{
 if (!handoff_window || state != &gate.delegation_state ||
     value != KD_MUTEX_GATE_FREE)
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
 memset(&record, 0, sizeof(record));
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
  if (kind == 0) kd_mutex_count_enter(&gate, &record);
  else if (kind == 1) kd_mutex_count_exit(&gate, &record);
  else kd_mutex_gate_set(&gate, kind == 2 ? KD_MUTEX_GATE_RELEASING + 1 : KD_MUTEX_GATE_COMBINER);
  CHECK(false);
 }
 expected_bug = false;
}
static void set_test_phase(u32 phase)
{
 kd_mutex_gate_set(&gate, phase == KD_MUTEX_GATE_COMBINER ? KD_MUTEX_GATE_HELD : phase);
 if (phase == KD_MUTEX_GATE_COMBINER) CHECK(kd_mutex_gate_try_combine(&gate));
}
static void check_layout_and_boundaries(void)
{
 CHECK(sizeof(struct kd_mutex) == 32 && _Alignof(struct kd_mutex) == 8);
 CHECK(offsetof(struct kd_mutex, owner) == 0 && offsetof(struct kd_mutex, wait_lock) == 8);
 CHECK(offsetof(struct kd_mutex, osq) == 12 && offsetof(struct kd_mutex, wait_head) == 16);
 CHECK(offsetof(struct kd_mutex, delegation_state) == 24 && offsetof(struct kd_mutex, delegation_tail) == 28);
 CHECK(sizeof(struct kd_mutex_node) == 320 && offsetof(struct kd_mutex_node, regs) == 128);
 CHECK(offsetof(struct kd_mutex_node, count_seq) == 88 && offsetof(struct kd_mutex_node, counted_lock) == 96);
 CHECK(offsetof(struct kd_mutex_node, completed) == 304 && offsetof(struct kd_mutex_node, locked) == 305);
 for (u32 phase = 0; phase <= KD_MUTEX_GATE_RELEASING; phase++) {
  reset();
  set_test_phase(phase);
  unsigned long before_enter = rmw_calls;
  kd_mutex_count_enter(&gate, &record);
  CHECK(rmw_calls == before_enter);
  CHECK(kd_mutex_gate_read(&gate) == phase && record.counted_lock == &gate && record.count_seq == 2);
  unsigned long before = rmw_calls;
  CHECK(kd_mutex_combiner_active(&gate) == (phase == KD_MUTEX_GATE_COMBINER));
  CHECK(!kd_mutex_delegation_owned(&gate, current));
  CHECK(rmw_calls == before); /* Observations and records need no shared RMW. */
  CHECK(kd_mutex_gate_trylock(&gate) == (phase == KD_MUTEX_GATE_FREE));
  CHECK(kd_mutex_gate_read(&gate) == (phase == KD_MUTEX_GATE_FREE ? KD_MUTEX_GATE_ACQUIRING : phase));
  set_test_phase(KD_MUTEX_GATE_COMBINER);
  before = rmw_calls;
  CHECK(record.counted_lock == &gate);
  kd_mutex_count_exit(&gate, &record);
  CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_COMBINER && !record.counted_lock && record.count_seq == 4);
  CHECK(rmw_calls == before); /* Exact record updates still have no gate RMW. */
 }
 reset(); record.count_seq = U64_MAX - 1; expect_guard(0);
 CHECK(record.count_seq == U64_MAX - 1 && !record.counted_lock);
 reset(); record.count_seq = 1; expect_guard(0);
 CHECK(record.count_seq == 1 && !record.counted_lock);
 reset(); expect_guard(1); /* Clearing an unentered record cannot underflow. */
 reset(); kd_mutex_count_enter(&gate, &record); expect_guard(0);
 CHECK(record.counted_lock == &gate && record.count_seq == 2);
 static struct kd_mutex different;
 record.counted_lock = &different; expect_guard(1);
 CHECK(record.counted_lock == &different && record.count_seq == 2);
 reset(); unsigned long before = rmw_calls; expect_guard(2); CHECK(rmw_calls == before);
 reset(); before = rmw_calls; expect_guard(3); CHECK(rmw_calls == before);
 /* Reuse is the same permanent slot, with a monotonically advancing version. */
 reset();
 for (u64 generation = 0; generation < 1000; generation++) {
  kd_mutex_count_enter(&gate, &record);
  CHECK(record.count_seq == generation * 4 + 2 && record.counted_lock == &gate);
  kd_mutex_count_exit(&gate, &record);
  CHECK(record.count_seq == generation * 4 + 4 && !record.counted_lock);
 }
}
static void check_cas_interleavings(void)
{
 reset(); cas_interleave = 3;
 CHECK(!kd_mutex_gate_trylock(&gate));
 CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_HELD);
 reset(); CHECK(kd_mutex_gate_trylock(&gate));
 CHECK(!kd_mutex_gate_trylock(&gate) && kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_ACQUIRING);
}
static void check_epoch_withdrawal(void)
{
 /* Exercise the actual full-word admission CAS with each possible winner. */
 reset(); kd_mutex_gate_set(&gate,KD_MUTEX_GATE_HELD); cas_interleave=4;
 CHECK(!kd_mutex_gate_try_combine(&gate));
 CHECK((u32)atomic_read(&gate.delegation_state)==(KD_MUTEX_GATE_HELD|KD_MUTEX_GATE_WITHDRAW));
 kd_mutex_gate_end_withdraw(&gate);
 CHECK(kd_mutex_gate_try_combine(&gate));
 CHECK(!kd_mutex_gate_try_withdraw(&gate));
 reset(); kd_mutex_gate_set(&gate,KD_MUTEX_GATE_HELD); cas_interleave=5;
 CHECK(!kd_mutex_gate_try_withdraw(&gate));
 CHECK((u32)atomic_read(&gate.delegation_state)==KD_MUTEX_GATE_COMBINER);
 /* A concurrent withdrawal cannot be erased by an owner phase transition. */
 reset(); kd_mutex_gate_set(&gate,KD_MUTEX_GATE_HELD); cas_interleave=6;
 kd_mutex_gate_set(&gate,KD_MUTEX_GATE_RELEASING);
 CHECK((u32)atomic_read(&gate.delegation_state)==(KD_MUTEX_GATE_RELEASING|KD_MUTEX_GATE_WITHDRAW));
 kd_mutex_gate_set(&gate,KD_MUTEX_GATE_FREE);
 CHECK(kd_mutex_gate_read(&gate)==KD_MUTEX_GATE_FREE);
 CHECK((u32)atomic_read(&gate.delegation_state)==KD_MUTEX_GATE_WITHDRAW);
 CHECK(!kd_mutex_gate_trylock(&gate) && !kd_mutex_gate_try_combine(&gate));
 kd_mutex_gate_end_withdraw(&gate);
 CHECK(!atomic_read(&gate.delegation_state) && kd_mutex_gate_trylock(&gate));
 for(u32 phase=0;phase<=KD_MUTEX_GATE_RELEASING;phase++) {
  if(phase==KD_MUTEX_GATE_COMBINER)continue;
  reset();kd_mutex_gate_set(&gate,phase);
  CHECK(kd_mutex_gate_try_withdraw(&gate));
  CHECK(!kd_mutex_gate_try_withdraw(&gate) && !kd_mutex_gate_try_combine(&gate));
  for(u32 next=0;next<=KD_MUTEX_GATE_RELEASING;next++) {
   if(next==KD_MUTEX_GATE_COMBINER)continue;
   kd_mutex_gate_set(&gate,next);
   CHECK(kd_mutex_gate_read(&gate)==next);
   CHECK((u32)atomic_read(&gate.delegation_state)==(next|KD_MUTEX_GATE_WITHDRAW));
  }
  kd_mutex_gate_end_withdraw(&gate);
  CHECK((u32)atomic_read(&gate.delegation_state)==KD_MUTEX_GATE_RELEASING);
 }
}
static void check_current_owner(void)
{
 reset();
 CHECK(!kd_mutex_delegation_owned(NULL, current) && !kd_mutex_combiner_active(NULL));
 for (u32 phase = 0; phase <= KD_MUTEX_GATE_RELEASING; phase++) {
  set_test_phase(phase);
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
 kd_mutex_count_enter(&gate, &record);
 atomic_long_set(&gate.owner, &ordinary);
 acquiring_window = true;
 CHECK(kd_mutex_gate_trylock(&gate));
 kd_mutex_claim_origin(&gate);
 CHECK(kd_mutex_delegation_owned(&gate, current) && !acquiring_window && errors == 1);
 releasing_window = true;
 CHECK(!_kd_mutex_unlock_checked(&gate));
 CHECK(!releasing_window && errors == 2 && !atomic_long_read(&gate.owner));
 CHECK(!kd_mutex_gate_read(&gate) && record.counted_lock == &gate);
 CHECK(kd_mutex_origin_acquires == 1 && kd_mutex_origin_releases == 1);
 kd_mutex_count_exit(&gate, &record);
 reset();
 CHECK(kd_mutex_gate_trylock(&gate)); kd_mutex_claim_origin(&gate);
 handoff_window = true;
 CHECK(!_kd_mutex_unlock_checked(&gate));
 CHECK(!handoff_window && atomic_long_read(&gate.owner) == (unsigned long)&successor);
 CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_HELD);
 current = &successor; CHECK(!_kd_mutex_unlock_checked(&gate));
 CHECK(!atomic_long_read(&gate.owner) && !kd_mutex_gate_read(&gate));
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
 }
 for (size_t i = 0; i < sizeof(objects) / sizeof(*objects); i++) {
  CHECK(kd_mutex_gate_read(&objects[i]) == KD_MUTEX_GATE_ACQUIRING);
  kd_mutex_gate_set(&objects[i], KD_MUTEX_GATE_FREE);
  CHECK(!atomic_read(&objects[i].delegation_state));
 }
}
int main(void)
{
 check_layout_and_boundaries();
 check_cas_interleavings();
 check_epoch_withdrawal();
 check_current_owner();
 check_object_independence();
 puts("PASS embedded mutex state: 32 bytes/8 alignment; versioned node records, owner phases, PICKUP, release handoff, 131072 independent roots");
 return 0;
}
