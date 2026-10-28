// SPDX-License-Identifier: GPL-2.0
/* Compose real entry/primitive/ledger code. Scheduler and task routing are
 * deterministic substitutes; this does not execute a kernel or JIT image. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long atomic_long_t;
typedef unsigned int atomic_t;
typedef unsigned int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct task_struct { unsigned int pid; } __attribute__((aligned(8)));
#include "kd_regs.h"
#include "custody_acquire_types.h"

static struct task_struct owner_task = {1}, other_task = {2};
static struct task_struct *current;
static struct kd_mutex outer, nested;
static struct kd_mutex_node retained;
static struct kd_mutex_node *route;
static unsigned long kd_mutex_custody_slots;
static struct { unsigned long node_slots; } kd_mutex_shadows;
static unsigned int checks, route_lookups, acquire_cas, release_cas;
static unsigned int hot_entries, sleep_checks, relaxations, slow_calls, contended_calls;
static bool contended_local;
static int slow_result;
static unsigned long expected_sp, expected_ip, expected_bp;
static enum kd_entry_abi expected_abi;

#define CHECK(value) do { checks++; if (!(value)) { \
 fprintf(stderr, "FAIL custody acquire line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)
/* Preserve the production duplicate assertion and distinguish it from a
 * fixture assertion: both the regression mutant and real misuse must hit it. */
#define BUG_ON(value) do { if (value) { \
 fprintf(stderr, "BUG custody acquire: %s\n", #value); exit(86); \
} } while (0)
#ifndef __always_inline
#define __always_inline inline
#endif
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define unlikely(value) (value)
#define BIT(bit) (1UL << (bit))
#define this_cpu_read(value) (value)
#define raw_cpu_read(value) (value)
#define atomic_long_read(word) READ_ONCE(*(word))
#define atomic_read_acquire(word) __atomic_load_n((word), __ATOMIC_ACQUIRE)
#define KD_WAITERS 1UL
#define KD_HANDOFF 2UL
#define KD_PICKUP 4UL
#define KD_FLAGS 7UL
#define TASK_INTERRUPTIBLE 1U
#define TASK_UNINTERRUPTIBLE 2U

static bool atomic_long_try_cmpxchg_acquire(unsigned long *word,
 unsigned long *expected, unsigned long value)
{
 bool acquired = __atomic_compare_exchange_n(word, expected, value, false,
                                             __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
 if (acquired) acquire_cas++;
 return acquired;
}
static bool atomic_long_try_cmpxchg_release(unsigned long *word,
 unsigned long *expected, unsigned long value)
{
 bool released = __atomic_compare_exchange_n(word, expected, value, false,
                                             __ATOMIC_RELEASE, __ATOMIC_RELAXED);
 if (released) release_cas++;
 return released;
}
static void cpu_relax(void) { relaxations++; }
static void might_sleep(void) { sleep_checks++; }
static void kd_hotlock_mutex_entry(void) { hot_entries++; }
static struct kd_mutex_node *kd_mutex_task_custody(struct task_struct *task)
{
 route_lookups++;
 return task == &owner_task ? route : NULL;
}
static int kd_local_lock_slow(struct kd_mutex *lock, unsigned int state,
                              struct kd_mutex_node *node)
{
 unsigned long zero = 0;

 CHECK(lock == &nested &&
       (state == TASK_UNINTERRUPTIBLE || state == TASK_INTERRUPTIBLE) && !node);
 CHECK(lock->owner == (unsigned long)&other_task && !retained.custody.native_count);
 slow_calls++;
 if (slow_result)
  return slow_result;
 /* Model the old physical owner releasing while this local caller waits.
  * The subsequent successful CAS remains the only acquisition primitive. */
 __atomic_store_n(&lock->owner, 0, __ATOMIC_RELEASE);
 CHECK(atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, (unsigned long)current));
 return 0;
}
static void kd_local_unlock_slow(struct kd_mutex *lock)
{
 (void)lock;
 CHECK(false); /* Every acquisition in this fixture has an uncontended release. */
}
static void kd_mutex_contended_entry(struct kd_mutex *lock, unsigned long sp,
 unsigned long ip, unsigned long bp, enum kd_entry_abi abi);
#include "custody_acquire_production.h"

static void kd_mutex_contended_entry(struct kd_mutex *lock, unsigned long sp,
 unsigned long ip, unsigned long bp, enum kd_entry_abi abi)
{
 CHECK(lock == &nested && sp == expected_sp && ip == expected_ip &&
       bp == expected_bp && abi == expected_abi);
 CHECK(!retained.custody.native_count && !acquire_cas);
 contended_calls++;
 /* An unstarted substituted queue entry records no physical acquisition.
  * The local-success arm executes the real local acquisition/note path. */
 if (contended_local)
  CHECK(!kd_local_lock_state(lock, TASK_UNINTERRUPTIBLE, NULL));
}

static void setup(void)
{
 memset(&outer, 0, sizeof(outer));
 memset(&nested, 0, sizeof(nested));
 memset(&retained, 0, sizeof(retained));
 current = &owner_task;
 outer.owner = (unsigned long)current;
 route = &retained;
 retained.task_struct_ptr = current;
 retained.lock = &outer;
 retained.slot = 1;
 retained.count_seq = retained.custody.generation = 4;
 retained.custody.phase = KD_MUTEX_CUSTODY_NATIVE;
 kd_mutex_shadows.node_slots = kd_mutex_custody_slots = BIT(retained.slot);
 route_lookups = acquire_cas = release_cas = 0;
 hot_entries = sleep_checks = relaxations = slow_calls = contended_calls = 0;
 contended_local = false;
 slow_result = 0;
 expected_sp = 0x1000; expected_ip = 0x2000; expected_bp = 0x3000;
 expected_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
}

static void finish_tracked(void)
{
 CHECK(acquire_cas == 1 && !release_cas);
 CHECK(nested.owner == (unsigned long)current);
 CHECK(retained.custody.native_count == 1 &&
       retained.custody.native_locks[0] == &nested);
 kd_mutex_local_unlock(&nested);
 CHECK(!nested.owner && release_cas == 1 && !retained.custody.native_count);
 CHECK(!retained.custody.native_overflow);
}

int main(int argc, char **argv)
{
 setup();
 if (argc == 2 && !strcmp(argv[1], "duplicate")) {
  CHECK(kd_mutex_outer_trylock(&nested, (unsigned long)current));
  kd_mutex_note_native_acquire(&nested);
  CHECK(false); /* An actual repeated ledger entry must never be tolerated. */
 }
 CHECK(argc == 1);

 /* Actual DIRECT C entry, the ABI2 bridge alias, and the legacy hook all
  * compose with the same inline owner CAS and exact cold custody ledger. */
 kd_mutex_direct_lock_clobber_v1(&nested, expected_sp, expected_ip, expected_bp);
 CHECK(hot_entries == 1 && sleep_checks == 1 && !contended_calls);
 finish_tracked();
 setup();
 __kd_mutex_lock_clobber_v1(&nested, expected_sp, expected_ip, expected_bp);
 CHECK(hot_entries == 1 && !contended_calls);
 finish_tracked();
 setup();
 __kd_mutex_lock(&nested, expected_sp, expected_ip);
 CHECK(hot_entries == 1 && !contended_calls);
 finish_tracked();
 setup();
 CHECK(kd_mutex_outer_trylock(&nested, (unsigned long)current));
 CHECK(!hot_entries && !sleep_checks && !contended_calls);
 finish_tracked();

 /* Busy probes cannot create a ledger record. Both ordinary exhaustion and
  * the active-combiner hint are refusal, not ownership evidence. */
 setup();
 nested.owner = (unsigned long)&other_task;
 CHECK(!kd_mutex_outer_trylock(&nested, (unsigned long)current));
 CHECK(relaxations == 8 && !acquire_cas && !retained.custody.native_count);
 nested.delegation_state = KD_MUTEX_GATE_COMBINER;
 CHECK(!kd_mutex_trylock_fast(&nested));
 CHECK(relaxations == 8 && !acquire_cas && !retained.custody.native_count);

 /* Check SP/IP/BP/ABI forwarding on failed fast entry, before a simulated
  * local success supplies the real local primitive's one ledger update. */
 for (unsigned int alias = 0; alias < 3; alias++) {
  setup();
  nested.owner = (unsigned long)&other_task;
  contended_local = true;
  if (alias == 0)
   kd_mutex_direct_lock_clobber_v1(&nested, expected_sp, expected_ip, expected_bp);
  else if (alias == 1)
   __kd_mutex_lock_clobber_v1(&nested, expected_sp, expected_ip, expected_bp);
  else {
   expected_bp = 0; expected_abi = KD_ENTRY_ABI_LEGACY;
   __kd_mutex_lock(&nested, expected_sp, expected_ip);
  }
  CHECK(contended_calls == 1 && slow_calls == 1 && !hot_entries);
  finish_tracked();
 }
 setup();
 nested.owner = (unsigned long)&other_task;
 __kd_mutex_lock_clobber_v1(&nested, expected_sp, expected_ip, expected_bp);
 CHECK(contended_calls == 1 && !slow_calls && !acquire_cas &&
       !retained.custody.native_count);
 slow_result = -EINTR;
 CHECK(kd_local_lock_state(&nested, TASK_INTERRUPTIBLE, NULL) == -EINTR);
 CHECK(slow_calls == 1 && !acquire_cas && !retained.custody.native_count);

 setup();
 CHECK(kd_mutex_trylock(&nested) == 1);
 finish_tracked();
 setup();
 nested.owner = (unsigned long)&other_task;
 CHECK(!kd_mutex_trylock(&nested));
 CHECK(!acquire_cas && !retained.custody.native_count);

 /* The CPU mask only rejects work. A positive hint still needs the current
  * task's exact route; another task's retained slot grants no ledger access. */
 for (unsigned int untracked = 0; untracked < 3; untracked++) {
  setup();
  if (untracked == 0) kd_mutex_custody_slots = 0;
  if (untracked == 1) current = &other_task;
  if (untracked == 2) route = NULL;
  __kd_mutex_lock_clobber_v1(&nested, expected_sp, expected_ip, expected_bp);
  CHECK(acquire_cas == 1 && !retained.custody.native_count);
  kd_mutex_local_unlock(&nested);
  CHECK(!nested.owner && release_cas == 1 && !retained.custody.native_count);
  CHECK(untracked ? route_lookups == 2 : route_lookups == 0);
 }
 printf("PASS custody composed acquisition: %u checks; DIRECT/ABI2/legacy/OUTER/local/try routes, exact single ledger updates and hint isolation\n", checks);
 return 0;
}
