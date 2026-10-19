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
typedef struct { int counter; } atomic_t;
struct kd_mutex { atomic_t delegation_state; };
#define KD_MUTEX_GATE_ACQUIRING 2
#define KD_MUTEX_GATE_RELEASING 4
static jmp_buf bug_target;
static bool expect_bug;
#define BUG_ON(c) do { if (c) { CHECK(expect_bug); longjmp(bug_target, 1); } } while (0)
#include "mutex_state_mock.h"
static int cpu_id, pinned, errors;
static bool tasks_idle = true;
static bool kd_mutex_tasks_idle(void) { return tasks_idle; }
static int kd_mutex_active_waiters[2], kd_mutex_reserved_nodes[2];
static int kd_mutex_max_waiters[2], kd_mutex_frame_failure_count[2];
static struct { unsigned long node_slots; } kd_mutex_shadows[2];
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
 CHECK(kd_mutex_check_idle());
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
  kd_mutex_waiter_enter(&lock);
  CHECK(!kd_mutex_check_idle() && kd_mutex_state_waiter_count(&lock) == 1);
  kd_mutex_waiter_exit(&lock);
  CHECK(!kd_mutex_check_idle() && kd_mutex_state_waiter_count(&lock) == 0);
 }
 kd_mutex_reserved_nodes[1] = 0;
 CHECK(!kd_mutex_check_idle()); /* bitmap protects even a gauge disagreement */
 kd_mutex_shadows[1].node_slots = 0;
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
 cpu_id = 0; kd_mutex_waiter_enter(&lock);
 cpu_id = 1; kd_mutex_waiter_enter(&lock); kd_mutex_waiter_enter(&lock);
 CHECK(kd_mutex_state_waiter_count(&lock) == 3 && kd_mutex_max_waiters[1] == 2);
 cpu_id = 0; kd_mutex_waiter_exit(&lock);
 CHECK(!kd_mutex_check_idle() && kd_mutex_active_waiters[0] == 0);
 cpu_id = 1; kd_mutex_waiter_exit(&lock);
 CHECK(!kd_mutex_check_idle());
 kd_mutex_waiter_exit(&lock);
 CHECK(kd_mutex_check_idle() && !kd_mutex_state_waiter_count(&lock) && !errors);
 /* A per-CPU imbalance remains diagnostic and cannot be hidden by totals. */
 kd_mutex_state_waiter_enter(&lock);
 kd_mutex_waiter_exit(&lock);
 CHECK(errors == 1 && kd_mutex_frame_failure_count[1] == 1);
 CHECK(!kd_mutex_state_waiter_count(&lock) && !kd_mutex_active_waiters[1]);
 /* Packed-state underflow is fail-closed, not a repaired approximate count. */
 expect_bug = true;
 if (!setjmp(bug_target)) { kd_mutex_waiter_exit(&lock); CHECK(false); }
 CHECK(kd_mutex_state_waiter_count(&lock) == (int)KD_MUTEX_WAITER_MAX);
 expect_bug = false;
 puts("PASS exact pinned balances: sleeping reservation, independent CPUs, slot lifetime, nested slots, underflow and drain");
 return 0;
}
