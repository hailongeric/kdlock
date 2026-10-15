/*
 * Direct provider lifecycle: initialize all services before admitting callers.
 * Mutex acquisition records retain routing after admission closes or a waiter
 * renames. No global hooks are installed; teardown still requires the external
 * no-new-callers boundary and complete request/source retirement.
 */
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
#include "exe.h"
#include "kd_exec.h"
#include "kd_comm.h"
#include "kd_source.h"
#include "kd_hotlock.h"
#include "kd_lock.h"
#include "kd_owned_mutex_direct.h"
#include "kd_spinlock.h"
#include "kd_spin_entry.h"
#include "sys.h"
#include "utils.h"

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("kdlock JIT lock delegation");

extern int kd_spin_jit_fail_after_nested_lock;
module_param_named(spin_jit_fail_after_nested_lock,
		   kd_spin_jit_fail_after_nested_lock, int, 0644);
MODULE_PARM_DESC(spin_jit_fail_after_nested_lock,
		 "one-shot local post-acquisition EIO; native only with a validated CALL/owner checkpoint");

static char *target_process = "kd_test";
struct kd_comm_key kd_spin_target;
module_param(target_process, charp, S_IRUGO);
MODULE_PARM_DESC(target_process,
		 "task comm eligible for direct mutex delegation");

/*
 * Error labels unwind only initialized services, in reverse dependency order.
 * Optional component selftests finish before direct callers can use the module.
 */
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

	ret = kd_owned_mutex_init_percpu();
	if (ret)
		goto err_spinlock;

#ifdef KDLOCK_SELFTEST
	ret = kd_hotlock_lifetime_check();
	if (ret)
		goto err_owned_mutex;
	ret = kd_spin_entry_selftest();
	if (ret)
		goto err_owned_mutex;
	ret = kd_mutex_task_selftest();
	if (ret)
		goto err_owned_mutex;
	ret = kd_owned_mutex_wait_selftest();
	if (ret)
		goto err_owned_mutex;
#endif

	KD_PR_INFO("kd kernel module init: direct spin/mutex APIs; global hooks disabled\n");
	return 0;

#ifdef KDLOCK_SELFTEST
err_owned_mutex:
#endif
	kd_owned_mutex_exit();
	kd_mutex_tasks_exit();
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

/*
 * Callers, translators and source leases must already be drained/retired.
 * RCU alone does not protect outstanding direct calls or lock-object storage.
 */
static void __exit kdlock_km_exit(void)
{
	synchronize_rcu();
	kd_owned_mutex_exit();
	kd_mutex_tasks_exit();
	WARN_ON_ONCE(kd_spin_entries_check_idle());
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
