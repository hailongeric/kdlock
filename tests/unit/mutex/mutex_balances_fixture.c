/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise production enter/exit and drain across two CPU identities. The
 * origin pin is a fixture precondition; the real stack/queue has other tests. */
#include <stdbool.h>
#include <stdint.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(c) do { if (!(c)) { \
 fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
struct kd_mutex { atomic_t delegation_state; };
struct kd_mutex_node { u64 count_seq; struct kd_mutex *counted_lock; };
#define KD_MUTEX_MAX_NODES 4
#define KD_MUTEX_GATE_FREE 0
static struct kd_mutex_node kd_mutex_nodes[KD_MUTEX_MAX_NODES];
static struct kd_mutex_node remote_nodes[KD_MUTEX_MAX_NODES];
#define KD_MUTEX_GATE_ACQUIRING 2
#define KD_MUTEX_GATE_RELEASING 4
static jmp_buf bug_target;
static bool expect_bug;
#define BUG_ON(c) do { if (c) { CHECK(expect_bug); longjmp(bug_target, 1); } } while (0)
#include "mutex_state_mock.h"
static int cpu_id, pinned, errors;
static bool tasks_idle = true;
static bool kd_mutex_tasks_idle(void) { return tasks_idle; }
#define per_cpu_ptr(p,cpu) ((cpu) ? &remote_nodes[(p)-kd_mutex_nodes] : (p))
static int fixture_count(struct kd_mutex *lock)
{
 int count = 0;
 for (int i = 0; i < KD_MUTEX_MAX_NODES; i++) {
  count += kd_mutex_nodes[i].counted_lock == lock;
  count += remote_nodes[i].counted_lock == lock;
 }
 return count;
}
static int kd_mutex_active_waiters[2], kd_mutex_reserved_nodes[2];
static int kd_mutex_max_waiters[2], kd_mutex_frame_failure_count[2];
static struct { unsigned long node_slots; } kd_mutex_shadows[2];
static unsigned long kd_mutex_custody_slots[2];
#define unlikely(c) (c)
#define READ_ONCE(v) (v)
#define per_cpu(v, cpu) ((v)[cpu])
#define for_each_possible_cpu(cpu) for ((cpu) = 0; (cpu) < 2; (cpu)++)
#define LOCAL(v) (*(CHECK_PIN(), &(v)[cpu_id]))
static void CHECK_PIN(void) { CHECK(pinned); }
#define this_cpu_read(v) LOCAL(v)
#define this_cpu_inc(v) (++LOCAL(v))
#define this_cpu_inc_return(v) (++LOCAL(v))
#define this_cpu_dec_return(v) (--LOCAL(v))
#define this_cpu_write(v, x) (LOCAL(v) = (x))
#define this_cpu_cmpxchg(v, old, new) ({ int seen = LOCAL(v); \
 if (seen == (old)) { LOCAL(v) = (new); } seen; })
#define KD_PR_ERR(...) (++errors)
#include "mutex_balances_production.h"

int main(void)
{
 static struct kd_mutex lock;
 struct kd_mutex_node *local = &kd_mutex_nodes[0], *remote = &remote_nodes[0], *nested = &remote_nodes[1];
 CHECK(kd_mutex_check_idle());
 kd_mutex_count_enter(&lock, remote);
 CHECK(!kd_mutex_check_idle()); /* Exact record independently protects drain. */
 kd_mutex_count_exit(&lock, remote);
 remote->count_seq++;
 CHECK(!kd_mutex_check_idle()); /* Interrupted publication is never quiescence. */
 remote->count_seq++;
 tasks_idle = false;
 CHECK(!kd_mutex_check_idle()); /* unpublished invocation still owns a record */
 tasks_idle = true;
 /* CPU 1 can retain a reserved stack while its executor sleeps. CPU 0
  * progressing through many requests must neither hide nor consume it. */
 kd_mutex_reserved_nodes[1] = 1;
 kd_mutex_shadows[1].node_slots = 1;
 pinned = 1;
 for (int i = 0; i < 1000; i++) {
  cpu_id = 0;
  kd_mutex_waiter_enter(&lock, local);
  CHECK(!kd_mutex_check_idle() && fixture_count(&lock) == 1);
  kd_mutex_waiter_exit(&lock, local);
  CHECK(!kd_mutex_check_idle() && fixture_count(&lock) == 0);
 }
 kd_mutex_reserved_nodes[1] = 0;
 CHECK(!kd_mutex_check_idle()); /* bitmap protects even a gauge disagreement */
 kd_mutex_shadows[1].node_slots = 0;
 CHECK(kd_mutex_check_idle());
 /* A retained native owner's custody hint independently prevents drain even
  * if a broken slot publication disagrees with it. Clearing it cannot replace
  * the exact task, count and reservation checks exercised above. */
 kd_mutex_custody_slots[1] = 1;
 CHECK(!kd_mutex_check_idle());
 kd_mutex_custody_slots[1] = 0;
 CHECK(kd_mutex_check_idle());
 kd_mutex_reserved_nodes[1] = 1;
 CHECK(!kd_mutex_check_idle());
 kd_mutex_reserved_nodes[1] = 0;
 /* Independent balances must not cancel, even if a protocol bug introduced
  * a negative value. Approximate cross-CPU totals cannot authorize drain. */
 kd_mutex_active_waiters[0] = 1;
 kd_mutex_active_waiters[1] = -1;
 CHECK(!kd_mutex_check_idle());
 kd_mutex_active_waiters[0] = kd_mutex_active_waiters[1] = 0;
 cpu_id = 0; kd_mutex_waiter_enter(&lock, local);
 cpu_id = 1; kd_mutex_waiter_enter(&lock, remote); kd_mutex_waiter_enter(&lock, nested);
 CHECK(fixture_count(&lock) == 3 && kd_mutex_max_waiters[1] == 2);
 cpu_id = 0; kd_mutex_waiter_exit(&lock, local);
 CHECK(!kd_mutex_check_idle() && kd_mutex_active_waiters[0] == 0);
 cpu_id = 1; kd_mutex_waiter_exit(&lock, remote);
 CHECK(!kd_mutex_check_idle());
 kd_mutex_waiter_exit(&lock, nested);
 CHECK(kd_mutex_check_idle() && !fixture_count(&lock) && !errors);
 /* A per-CPU imbalance remains diagnostic and cannot be hidden by totals. */
 kd_mutex_count_enter(&lock, remote);
 kd_mutex_waiter_exit(&lock, remote);
 CHECK(errors == 1 && kd_mutex_frame_failure_count[1] == 1);
 CHECK(!fixture_count(&lock) && !kd_mutex_active_waiters[1]);
 /* A duplicate record retirement is fail-closed, not a repaired count. */
 expect_bug = true;
 if (!setjmp(bug_target)) { kd_mutex_waiter_exit(&lock, local); CHECK(false); }
 CHECK(!fixture_count(&lock) && !local->counted_lock);
 expect_bug = false;
 puts("PASS exact pinned balances: sleeping reservation, independent CPUs, slot and custody lifetime, nested slots, underflow and drain");
 return 0;
}
