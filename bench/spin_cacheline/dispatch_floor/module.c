// SPDX-License-Identifier: GPL-2.0
/* Diagnostic floor for guest hook dispatch, never a kdlock performance arm.
 * The actual payload remains workload_modules/spin_cacheline. This provider
 * performs only original Linux locking: no promotion, registration, S, ticket,
 * source lease, JIT, ownership cache or per-operation observation.
 */
#include <linux/module.h>
#include <linux/spinlock.h>
#include "kd_comm.h"
#if __has_include(<linux/kd_spin_hooks.h>)
#include <linux/kd_spin_hooks.h>
#endif

extern int (*is_kd_test)(void);
extern void (*kd_raw_spin_lock)(raw_spinlock_t *, unsigned long, unsigned long);
extern void (*kd_raw_spin_unlock)(raw_spinlock_t *, unsigned long, unsigned long);

static bool callbacks;
module_param(callbacks, bool, 0444);
MODULE_PARM_DESC(callbacks, "0: selector returns native; 1: target uses minimal native callbacks");
#ifdef KD_SPIN_STATIC_DISPATCH
static bool combined;
module_param(combined, bool, 0444);
MODULE_PARM_DESC(combined, "minimal unconditional native dispatch via the combined interface");
#endif
static struct kd_comm_key target;

static notrace int select_target(void)
{
	return callbacks && kd_comm_matches(&target, current->comm) ? 2 : 0;
}

static notrace void native_lock(raw_spinlock_t *lock, unsigned long rsp,
				unsigned long rip)
{
	(void)rsp;
	(void)rip;
	__raw_spin_lock(lock);
}

static notrace void native_unlock(raw_spinlock_t *lock, unsigned long rsp,
				  unsigned long rip)
{
	(void)rsp;
	(void)rip;
	__raw_spin_unlock(lock);
}

static int __init floor_init(void)
{
	if (is_kd_test || kd_raw_spin_lock || kd_raw_spin_unlock)
		return -EBUSY;
	kd_comm_init(&target, "sc_worker");
#ifdef KD_SPIN_STATIC_DISPATCH
	if (combined)
		return kd_spin_static_install_dispatch(select_target, native_lock,
					       native_unlock);
#endif
#ifdef KD_SPIN_STATIC_HOOKS
	return kd_spin_static_install(select_target, native_lock, native_unlock);
#else
	if (callbacks) {
		kd_raw_spin_lock = native_lock;
		kd_raw_spin_unlock = native_unlock;
	}
	is_kd_test = select_target;
	return 0;
#endif
}

static void __exit floor_exit(void)
{
	/* Same controlled recovery-guest/no-new-callers restriction as kdlock:
	 * the existing kernel hook ABI has no generic hot-unload reader barrier. */
#ifdef KD_SPIN_STATIC_HOOKS
	kd_spin_static_remove();
#else
	is_kd_test = NULL;
	kd_raw_spin_lock = NULL;
	kd_raw_spin_unlock = NULL;
#endif
}

module_init(floor_init);
module_exit(floor_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Spin cacheline native hook dispatch diagnostic");
