/* Execute the real provider lifecycle against observable service boundaries.
 * Opening the control device must never expose an uninitialized KD mutex core.
 */
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <stdbool.h>

#define CHECK(c) do { if (!(c)) { \
 fprintf(stderr, "FAIL line %d: %s (active=%x)\n", __LINE__, #c, active); \
 exit(1); } } while (0)
#define __init
#define __exit
#define KD_PR_INFO(...) do { } while (0)
#define WARN_ON_ONCE(c) CHECK(!(c))
enum { SOURCE=1, HOT=2, EXE=4, CONTEXT=8, ENTRIES=16,
       SPIN=32, MUTEX=64, DEVICE=128, SERVICES=127 };
static unsigned int active;
static int fail_at, attempts;
static bool call_depth;
static unsigned int comm_initializations, policy_errors;
#define X86_FEATURE_CALL_DEPTH 371
static bool boot_cpu_has(unsigned int capability)
{
 CHECK(capability == X86_FEATURE_CALL_DEPTH);
 return call_depth;
}
#define pr_err(...) do { policy_errors++; } while (0)
static int kd_spin_target;
static const char *target_process="test";
static void kd_comm_init(int *key, const char *name)
{
 (void)key; (void)name; comm_initializations++;
}
static int acquire(unsigned int bit)
{
 CHECK(!(active & bit));
 if (++attempts == fail_at) return -42;
 active |= bit;
 return 0;
}
static void release(unsigned int bit)
{
 CHECK(active & bit);
 if (bit != DEVICE) CHECK(!(active & DEVICE));
 active &= ~bit;
}
#define SERVICE(name, bit) \
 static int name##_init(void) { return acquire(bit); } \
 static void name##_exit(void) { release(bit); }
SERVICE(kd_source, SOURCE)
SERVICE(kd_hotlock, HOT)
SERVICE(kd_exe, EXE)
SERVICE(kd_spin_entries, ENTRIES)
SERVICE(kd_spinlock, SPIN)
static void kd_exec_context_init(void) { CHECK(!(active & CONTEXT)); active |= CONTEXT; }
static void kd_exec_context_exit(void) { release(CONTEXT); }
static int kd_mutex_init_percpu(void) { return acquire(MUTEX); }
static void kd_mutex_exit(void) { release(MUTEX); }
static int kd_sys_init(void)
{
 /* Simulate a control caller arriving as soon as the cdev is published. */
 CHECK(active == SERVICES);
 return acquire(DEVICE);
}
static void kd_sys_exit(void) { release(DEVICE); }
static void kd_mutex_tasks_exit(void) { CHECK(!(active & DEVICE)); }
static int kd_spin_entries_check_idle(void) { CHECK(active & ENTRIES); return 0; }
static void synchronize_rcu(void) { CHECK(!(active & DEVICE)); }
#ifdef KDLOCK_SELFTEST
static int selftest(void)
{
 CHECK(active == SERVICES);
 return ++attempts == fail_at ? -42 : 0;
}
static int kd_hotlock_lifetime_check(void) { return selftest(); }
static int kd_spin_entry_selftest(void) { return selftest(); }
static int kd_mutex_task_selftest(void) { return selftest(); }
#endif

#include "provider_lifecycle.h"

int main(void)
{
 int stages;
 call_depth=true;
 CHECK(kdlock_km_init() == -EOPNOTSUPP);
 CHECK(!active && !attempts && !comm_initializations && policy_errors == 1);
 call_depth=false;
 CHECK(kdlock_km_init() == 0);
 CHECK(active == (SERVICES | DEVICE));
 stages=attempts;
 kdlock_km_exit();
 CHECK(active == 0);
 for (int failure=1; failure<=stages; failure++) {
  fail_at=failure;
  attempts=0;
  CHECK(kdlock_km_init() == -42);
  CHECK(attempts == failure && active == 0);
 }
 printf("PASS call-depth policy rejected before initialization; control publication after KD runtime initialization; %d failure paths unwind; unpublish before teardown\n", stages);
 return 0;
}
