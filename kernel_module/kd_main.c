/* Provider lifecycle: allocate all services before publishing guest hooks.
 * Selectors retain active-task routing even after admission closes or a waiter
 * renames. Teardown requires the documented external no-new-callers boundary;
 * clearing plain hook pointers is not a general hot-unload reader protocol. */
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/rcupdate.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/string.h>
#if __has_include(<linux/kd_spin_hooks.h>)
#include <linux/kd_spin_hooks.h>
#endif
#ifndef KD_SPIN_CLOBBER_V1
#error "kdlock requires the spin caller-clobber v1 (kdclobber2 or compatible)"
#endif
#if __has_include(<linux/kd_mutex_hooks.h>)
#include <linux/kd_mutex_hooks.h>
#endif
#ifndef KD_MUTEX_CLOBBER_V1
#error "kdlock requires ordinary mutex clobber v1 (kdclobber2 or compatible)"
#endif

#include "exe.h"
#include "kd_exec.h"
#include "kd_comm.h"
#include "kd_source.h"
#include "kd_hotlock.h"
#include "kd_lock.h"
#include "kd_mutex.h"
#include "kd_spinlock.h"
#include "kd_spin_gate.h"
#include "kd_spin_entry.h"
#include "sys.h"
#include "utils.h"

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("kdlock JIT lock delegation");

extern int kd_spin_jit_fail_after_nested_lock;
module_param_named(spin_jit_fail_after_nested_lock,
		   kd_spin_jit_fail_after_nested_lock, int, 0644);
MODULE_PARM_DESC(
	spin_jit_fail_after_nested_lock,
	"one-shot local post-acquisition EIO; native only with a validated CALL/owner checkpoint");

static char *target_process = "kd_test";
struct kd_comm_key kd_spin_target;
module_param(target_process, charp, S_IRUGO);
MODULE_PARM_DESC(target_process, "task comm routed through kdlock hooks");

#if 0 /* Direct-API experiment: do not install global lock selectors. */
/* This kernel selector has no lock argument. Dispatch without reading comm;
 * the lock hook performs CPU -> address -> task admission, and the unlock
 * hook independently preserves every retained owner's route. */
static int kd_mutex_dispatch_enabled(void)
{
	return 2;
}
#endif

/* Error labels unwind only initialized services, in reverse dependency order.
 * Optional component selftests finish before any guest callback is published. */
static int __init kdlock_km_init(void)
{
	int ret;

	kd_comm_init(&kd_spin_target, target_process);
	ret = kd_source_init();
	if (ret)
		return ret;
	ret = kd_hotlock_init();
	if (ret)
		goto err_source;

	ret = kd_exe_init();
	if (ret)
		goto err_hotlock;

	kd_exec_context_init();
	ret = kd_spin_entries_init();
	if (ret)
		goto err_exec_context;
	ret = kd_sys_init();
	if (ret)
		goto err_spin_entries;

	ret = kd_spinlock_init();
	if (ret)
		goto err_sys;

	ret = kd_mutex_init_percpu();
	if (ret)
		goto err_spinlock;

#ifdef KDLOCK_SELFTEST
	ret = kd_spin_gate_selftest();
	if (ret)
		goto err_mutex;
	ret = kd_spin_entry_selftest();
	if (ret)
		goto err_mutex;
	ret = kd_mutex_task_selftest();
	if (ret)
		goto err_mutex;
#endif

#if 0 /* Temporarily disable unified spin/mutex interception for direct calls.
       * Keep this block together with its removal/error unwind below. */
	/* Ordinary callers use clobber v1. The legacy callbacks remain necessary
	 * for explicit nested APIs and modules compiled with the old caller ABI;
	 * supporting those callers does not require an older kernel installer. */
	ret = kd_mutex_static_install_clobber_v1(kd_mutex_dispatch_enabled,
		__kd_mutex_lock, __kd_mutex_unlock,
		__kd_mutex_lock_clobber_v1, __kd_mutex_unlock_clobber_v1);
	if (ret)
		goto err_mutex;
#endif

	KD_PR_INFO("kd kernel module init: direct spin API; unified hooks disabled\n");
	return 0;

#ifdef KDLOCK_SELFTEST
err_mutex:
#endif
	kd_mutex_exit();
err_spinlock:
	kd_spinlock_exit();
err_sys:
	kd_sys_exit();
err_spin_entries:
	kd_spin_entries_exit();
err_exec_context:
	kd_exec_context_exit();
	kd_exe_exit();
err_hotlock:
	kd_hotlock_exit();
err_source:
	kd_source_exit();
	return ret;
}

/* Callers, translators and source leases must already be drained/retired.
 * This RCU wait does not by itself protect the guest's unguarded hook readers. */
static void __exit kdlock_km_exit(void)
{
#if 0 /* Direct-API experiment: this module installed no global hooks. */
	kd_mutex_static_remove();
#endif

	synchronize_rcu();
	kd_mutex_exit();
	kd_mutex_tasks_exit();
	WARN_ON_ONCE(kd_spin_entries_check_idle());
	WARN_ON_ONCE(kd_spin_gates_check_idle());
	kd_spinlock_exit();
	kd_exec_context_exit();
	kd_spin_entries_exit();
	kd_sys_exit();
	kd_exe_exit();
	kd_hotlock_exit();
	kd_source_exit();

	KD_PR_INFO("kd kernel module exit\n");
}

module_init(kdlock_km_init);
module_exit(kdlock_km_exit);
