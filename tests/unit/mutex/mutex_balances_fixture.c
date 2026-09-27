/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise production enter/exit and drain across two CPU identities. The
 * origin pin is a fixture precondition; the real stack/queue has other tests. */
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(c) do { if (!(c)) { \
 fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
typedef struct { int value; } atomic_t;
struct kd_mutex { atomic_t waiter_count; };
static int cpu_id, pinned, errors;
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
#define atomic_inc(p) (++(p)->value)
#define atomic_dec_return(p) (--(p)->value)
#define atomic_set(p, v) ((p)->value = (v))
#define KD_PR_ERR(...) (++errors)
#include "mutex_balances_production.h"

int main(void)
{
 struct kd_mutex lock = {0};
 CHECK(kd_mutex_check_idle());
 /* CPU 1 can retain a reserved stack while its executor sleeps. CPU 0
  * progressing through many requests must neither hide nor consume it. */
 kd_mutex_reserved_nodes[1] = 1;
 kd_mutex_shadows[1].node_slots = 1;
 pinned = 1;
 for (int i = 0; i < 1000; i++) {
  cpu_id = 0;
  kd_mutex_waiter_enter(&lock);
  CHECK(!kd_mutex_check_idle() && lock.waiter_count.value == 1);
  kd_mutex_waiter_exit(&lock);
  CHECK(!kd_mutex_check_idle() && lock.waiter_count.value == 0);
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
 CHECK(lock.waiter_count.value == 3 && kd_mutex_max_waiters[1] == 2);
 cpu_id = 0; kd_mutex_waiter_exit(&lock);
 CHECK(!kd_mutex_check_idle() && kd_mutex_active_waiters[0] == 0);
 cpu_id = 1; kd_mutex_waiter_exit(&lock);
 CHECK(!kd_mutex_check_idle());
 kd_mutex_waiter_exit(&lock);
 CHECK(kd_mutex_check_idle() && !lock.waiter_count.value && !errors);
 kd_mutex_waiter_exit(&lock);
 CHECK(errors == 2 && kd_mutex_frame_failure_count[1] == 2);
 CHECK(!lock.waiter_count.value && !kd_mutex_active_waiters[1]);
 puts("PASS exact pinned balances: sleeping reservation, independent CPUs, slot lifetime, nested slots, underflow and drain");
 return 0;
}
