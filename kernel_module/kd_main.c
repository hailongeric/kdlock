#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/rcupdate.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/string.h>

#include "exe.h"
#include "kd_exec.h"
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
MODULE_PARM_DESC(spin_jit_fail_after_nested_lock,
		 "one-shot failure after a JIT nested spinlock acquisition");

static char *target_process = "kd_test";
module_param(target_process, charp, S_IRUGO);
MODULE_PARM_DESC(target_process, "task comm routed through kdlock hooks");

extern int (*is_kd_test)(void);

extern void (*kd_raw_spin_lock)(raw_spinlock_t *lock, unsigned long ret_rsp,
				unsigned long ret_addr);
extern void (*kd_raw_spin_unlock)(raw_spinlock_t *lock, unsigned long ret_rsp,
				  unsigned long ret_addr);

extern int (*is_kd)(void);
extern void (*kd_mutex_lock)(struct mutex *lock, unsigned long ret_rsp,
			     unsigned long ret_addr);
extern void (*kd_mutex_unlock)(struct mutex *lock, unsigned long ret_rsp,
			       unsigned long ret_addr);

static bool kd_target_matches(void)
{
	return target_process && !strcmp(current->comm, target_process);
}

static int __is_kd_test(void)
{
	return kd_target_matches() || kd_spin_entry_task_active() ? 2 : 0;
}

/* A renamed task must still finish its queued or borrowed mutex acquisition. */
static int __is_kd_mutex_task(void)
{
	return kd_target_matches() || kd_mutex_task_reroute(current) ? 2 : 0;
}

static int __init kdlock_km_init(void)
{
	int ret;

	ret = kd_hotlock_init();
	if (ret)
		return ret;

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
#endif

	is_kd_test = __is_kd_test;
	kd_raw_spin_unlock = __kd_raw_spin_unlock;
	kd_raw_spin_lock = __kd_raw_spin_lock;
	is_kd = __is_kd_mutex_task;
	kd_mutex_lock = __kd_mutex_lock;
	kd_mutex_unlock = __kd_mutex_unlock;

	KD_PR_INFO("kd kernel module init: target_process=%s\n",
		   target_process);
	return 0;

#ifdef KDLOCK_SELFTEST
err_mutex:
	kd_mutex_exit();
#endif
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
	return ret;
}

static void __exit kdlock_km_exit(void)
{
	kd_raw_spin_unlock = NULL;
	kd_raw_spin_lock = NULL;
	is_kd_test = NULL;
	kd_mutex_unlock = NULL;
	kd_mutex_lock = NULL;
	is_kd = NULL;

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

	KD_PR_INFO("kd kernel module exit\n");
}

module_init(kdlock_km_init);
module_exit(kdlock_km_exit);
