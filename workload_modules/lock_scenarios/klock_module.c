/*
 * klock_module — test device driver for kdlock benchmarking.
 *
 * Exposes /dev/lock_dev with an ioctl interface.  Each ioctl call executes
 * a synthetic critical section using either a spinlock or mutex (depending
 * on mode), optionally with a nested lock or a kernel API call inside the
 * critical section.  When kdlock_km is loaded with target_process="klock_test",
 * these lock operations trigger the kdlock hooks and exercise the delegation
 * path.
 * Workload records and their independent integrity checks must agree after
 * drain. Optional fragments/ sources construct contention or observe it;
 * they are not standalone modules and must not be mistaken for production
 * lock code. Modes 10/11 are native-only negatives; mode 9 is fault diagnosis.
 * This file owns the ioctl dispatcher and module lifetime. common/ contains
 * shared locks, role state and integrity oracles; modes/ contains ordinary
 * mode bodies; fragments/ contains the existing focused protocol workloads.
 * Includes retain declaration order and inline CS code in one module object.
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/mutex.h>
#include <linux/percpu.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/ktime.h>
#include <linux/math.h>
#include <linux/string.h>
#include <linux/sched.h>
#include <linux/jiffies.h>
#include <kernel/locking/mutex.h>
#ifdef KDLOCK_SOURCE_HELPER
#include "kd_depth_source.h"
#endif

#define DRIVER_NAME "lock_dev"

extern int kd_spin_debug_waiter_count(raw_spinlock_t *lock);
extern unsigned int kd_spin_debug_word(raw_spinlock_t *lock);
extern unsigned long kd_spin_debug_owner(raw_spinlock_t *lock);
extern int kd_mutex_debug_waiter_count(struct mutex *lock);
extern int kd_mutex_debug_nested_waiters(void);

struct test_args {
	unsigned long loop_count;
	unsigned long work_load;
	unsigned int mode;
	unsigned int role;
};

#define IOC_MAGIC 'k'
#define IOC_RUN_TEST _IOW(IOC_MAGIC, 1, struct test_args)
#define IOC_PREPARE_TEST _IOW(IOC_MAGIC, 2, struct test_args)

/* Explicit protocol preparation; never enabled by performance drivers. */
static bool cpu_frequency_prepare;
module_param(cpu_frequency_prepare, bool, 0644);
MODULE_PARM_DESC(cpu_frequency_prepare, "Prepare local CPU and lock frequency before short probes");

#include "common/resume.inc"

#include "common/integrity.inc"

#include "fragments/native_ooo_workload.c"
#include "fragments/remote_outer_workload.c"
#include "fragments/spin_chain_workload.c"
#include "fragments/remote_depth_workload.c"
#include "fragments/spin_multi_workload.c"
#include "fragments/mutex_shared_workload.c"

#include "common/depth.inc"

#include "common/roles.inc"

#include "common/gs_probe.inc"

#include "fragments/spin_native_workload.c"

#include "modes/spin_basic.inc"

#include "modes/spin_inner.inc"

#include "modes/spin_outer.inc"

#include "modes/spin_abort.inc"

#include "modes/spin_service.inc"

#include "modes/mutex_basic.inc"

#include "modes/mutex_nested.inc"

#include "modes/mutex_contenders.inc"

#include "modes/mutex_service.inc"

#include "fragments/spin_routing_workload.c"
#include "fragments/mutex_signal_workload.c"
#include "fragments/mutex_parallel_workload.c"

/* A one-shot probe cannot supply 10000 local lock observations. Once code
 * is published, selected tests enable this native, empty-CS preparation. Use
 * the actual lock and CPU but a non-target comm, so preparation cannot register
 * entries, execute JIT, or change payload/register records. Migration pinning
 * permits mutex sleep and ends before the original ioctl workload begins. */
static void prepare_cpu_frequency(unsigned int mode)
{
	char comm[TASK_COMM_LEN];
	spinlock_t *spin = NULL;
	struct mutex *mutex = NULL;
	unsigned int i;

	if (!cpu_frequency_prepare)
		return;
	if (mode == MODE_SPIN_CONTENTION || mode == MODE_SPIN_API_IN_LOCK)
		spin = &global_lock;
	else if (mode == MODE_MUTEX_CONTENTION)
		mutex = &global_mutex;
	else if (mode == MODE_SPIN_NESTED || mode == MODE_SPIN_DEEP_NESTED ||
		 mode == MODE_SPIN_OOO_NESTED)
		spin = &nested_lock_a;
	else
		return;
	get_task_comm(comm, current);
	kd_test_rename("kd_cpu_prepare");
	migrate_disable();
	/* Four batches cover a stale CPU block, reopen, and a full local window.
	 * No sampler internals or forced promotion interfaces are used. */
	for (i = 0; i < 40960; i++) {
		if (spin) {
			spin_lock(spin);
			spin_unlock(spin);
		} else {
			mutex_lock(mutex);
			mutex_unlock(mutex);
		}
	}
	migrate_enable();
	kd_test_rename(comm);
}

static long my_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct test_args k_args;

	switch (cmd) {
	case IOC_PREPARE_TEST:
		if (!cpu_frequency_prepare)
			return -EACCES;
		if (copy_from_user(&k_args, (void __user *)arg, sizeof(k_args)))
			return -EFAULT;
		prepare_cpu_frequency(k_args.mode);
		return 0;
	case IOC_RUN_TEST:
		if (copy_from_user(&k_args, (void __user *)arg, sizeof(k_args)))
			return -EFAULT;
		/* Isolate the multi-frame workload from the ordinary mode ABI. */
		if (spin_multi_roots)
			return k_args.mode == MODE_SPIN_INNER_CONTENTION ?
				       kd_multi_run(k_args.loop_count, k_args.role) :
				       -EINVAL;
		if (mutex_parallel)
			return k_args.mode == MODE_MUTEX_CONTENTION ?
				       kd_parallel_run(k_args.loop_count,
						       k_args.role) :
				       -EINVAL;
		if (mutex_signal_probe) {
			if (k_args.mode != MODE_MUTEX_CONTENTION)
				return -EINVAL;
			if (k_args.role & KD_SIGNAL_ROLE)
				return k_args.loop_count == 1 ?
					       kd_signal_run(k_args.role &
							     ~KD_SIGNAL_ROLE) :
					       -EINVAL;
		}
		if (spin_route_probe)
			return k_args.mode == MODE_SPIN_CONTENTION &&
					       k_args.loop_count == 1 ?
				       kd_route_run(k_args.role) :
				       -EINVAL;
		if (context_lock_probe && k_args.mode != MODE_MUTEX_CONTENTION)
			return -EINVAL;
		if (spin_chain_depth)
			return k_args.mode == MODE_SPIN_INNER_CONTENTION ?
				       kd_chain_run(k_args.loop_count,
						    k_args.role) :
				       -EINVAL;
		if (remote_chain_depth)
			return k_args.mode == MODE_SPIN_INNER_CONTENTION ?
				       kd_deep_run(k_args.loop_count,
						   k_args.role) :
				       -EINVAL;
		/* Gate roles extend the paused ticket case with native pressure and
		 * a second prepared JIT root, not ordinary mode-8 selector values. */
		if (native_gate_pressure && (k_args.role & 0x40000000U))
			return k_args.mode == MODE_SPIN_INNER_CONTENTION &&
					       !(k_args.role & ~0x4000000fU) ?
				       kd_gate_capacity_run(k_args.loop_count,
							    k_args.role & 15U) :
				       -EINVAL;
		if (k_args.mode == MODE_SPIN_CONTENTION) {
			unsigned int api = k_args.role & 0x20000000U ?
						   k_args.role & 3U :
						   0;

			if (api)
				run_native_spin_contention_test(
					k_args.loop_count, k_args.work_load,
					api);
			else
				run_contention_test(k_args.loop_count,
						    k_args.work_load);
		} else if (k_args.mode == MODE_SPIN_NESTED)
			run_nested_spinlock_test(k_args.loop_count,
						 k_args.work_load, k_args.role);
		else if (k_args.mode == MODE_SPIN_API_IN_LOCK)
			run_api_in_lock_test(k_args.loop_count,
					     k_args.work_load);
		else if (k_args.mode == MODE_MUTEX_CONTENTION)
			return run_mutex_contention_test(k_args.loop_count,
							 k_args.work_load,
							 k_args.role);
		else if (k_args.mode == MODE_MUTEX_NESTED && mutex_shared)
			return kd_shared_run(k_args.loop_count, k_args.role);
		else if (k_args.mode == MODE_MUTEX_NESTED)
			run_nested_mutex_test(k_args.loop_count,
					      k_args.work_load, k_args.role,
					      false);
		else if (k_args.mode == MODE_MUTEX_API_IN_LOCK)
			run_api_in_mutex_test(k_args.loop_count,
					      k_args.work_load);
		else if (k_args.mode == MODE_SPIN_DEEP_NESTED)
			run_deep_nested_spinlock_test(k_args.loop_count,
						      k_args.work_load);
		else if (k_args.mode == MODE_SPIN_OOO_NESTED)
			run_ooo_nested_spinlock_test(k_args.loop_count,
						     k_args.work_load);
		else if (k_args.mode == MODE_SPIN_INNER_CONTENTION)
			run_inner_contention_spinlock_test(k_args.loop_count,
							   k_args.work_load,
							   k_args.role, false);
		else if (k_args.mode == MODE_SPIN_ABORT_RECOVERY)
			run_abort_recovery_spinlock_test(k_args.loop_count,
							 k_args.work_load,
							 k_args.role);
		else if (k_args.mode == MODE_SPIN_GS_CONTEXT)
			run_inner_contention_spinlock_test(k_args.loop_count,
							   k_args.work_load,
							   k_args.role, true);
		else if (k_args.mode == MODE_MUTEX_GS_CONTEXT)
			run_nested_mutex_test(k_args.loop_count,
					      k_args.work_load, k_args.role,
					      true);
		else
			return -EINVAL;
		break;
	default:
		return -EINVAL;
	}
	return 0;
}

static const struct file_operations my_fops = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = my_ioctl,
};

static struct miscdevice my_misc_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = DRIVER_NAME,
	.fops = &my_fops,
};

#include "common/validate.inc"

static int __init my_module_init(void)
{
	int cpu;
	int ret;

	ret = kd_parallel_init();
	if (ret)
		return ret;
	/* Shared-B gates start only after translation; reject ambiguous fixture
	 * combinations rather than silently replacing another mode-4 workload. */
	if (mutex_shared_armed ||
	    (mutex_shared && (mutex_parallel || mutex_nested_schedule ||
			      native_resume_stage || mixed_lock_probe)))
		return -EINVAL;
	ret = kd_signal_init();
	if (ret)
		return ret;
	ret = kd_route_init();
	if (ret)
		return ret;
	if (native_resume_stage > 5)
		return -EINVAL;
	if (native_pending_contended && native_resume_stage != 4)
		return -EINVAL;
	if (native_acquired_queue &&
	    (native_resume_stage != 3 || native_pending_contended ||
	     native_resume_registers || mixed_lock_probe ||
	     native_waiter_signal))
		return -EINVAL;
	ret = kd_ticket_init();
	if (ret)
		return ret;
	ret = kd_gate_capacity_init();
	if (ret)
		return ret;
	if (native_stack_armed ||
	    (native_stack_change &&
	     (!native_pending_contended || native_resume_stage != 4 ||
	      native_waiter_signal || native_resume_registers ||
	      mixed_lock_probe)))
		return -EINVAL;
	if (native_waiter_signal &&
	    ((native_waiter_signal != SIGUSR1 &&
	      native_waiter_signal != SIGKILL) ||
	     !native_pending_contended || native_resume_stage != 4))
		return -EINVAL;
	if (native_waiter_api &&
	    !((native_waiter_api == 1 && native_waiter_signal == SIGUSR1) ||
	      (native_waiter_api == 2 && native_waiter_signal == SIGKILL)))
		return -EINVAL;
	if ((native_waiter_race && !native_waiter_api) ||
	    native_waiter_release || native_waiter_phase || native_waiter_pid ||
	    kd_waiter_signal.acquired)
		return -EINVAL;
	if (native_resume_ooo || jit_mutex_ooo || mutex_ooo_dependency ||
	    spin_ooo_dependency)
		return -EINVAL;
	kd_ooo_init();
	if (context_lock_probe > 9 ||
	    (context_lock_probe && (mixed_lock_probe != 1 ||
				    native_resume_stage || spin_chain_depth)))
		return -EINVAL;
	ret = kd_chain_init();
	if (ret)
		return ret;
	ret = kd_deep_init();
	if (ret)
		return ret;
	for (cpu = 0; cpu < KD_RESUME_DEPTH_LOCKS; cpu++)
		mutex_init(&resume_depth_locks[cpu]);
	if (native_resume_stage) {
		resume_records = kvcalloc(KD_RESUME_RECORDS,
					  sizeof(*resume_records), GFP_KERNEL);
		if (!resume_records)
			return -ENOMEM;
	}
	ret = kd_register_init();
	if (ret) {
		kvfree(resume_records);
		return ret;
	}
	mode2_api_observations = 0;
	mode5_api_observations = 0;
	mode5_api_calls = 0;
	mode2_scalar_calls = mode2_scalar_failures = 0;
	mode5_scalar_calls = mode5_scalar_failures = 0;
	kd_multi_init();
	kd_shared_init();
	memset(kd_cs_states, 0, sizeof(kd_cs_states));
	memset(kd_cs_completed, 0, sizeof(kd_cs_completed));
	atomic64_set(&gs_spin_attempts, 0);
	atomic64_set(&gs_spin_successes, 0);
	atomic64_set(&gs_spin_failures, 0);
	atomic64_set(&gs_mutex_attempts, 0);
	atomic64_set(&gs_mutex_successes, 0);
	atomic64_set(&gs_mutex_failures, 0);
	for_each_possible_cpu(cpu) {
		per_cpu(kd_gs_probe_value, cpu) = ~0UL;
		per_cpu(kd_gs_probe_rmw, cpu) = ~0UL;
	}
	ret = misc_register(&my_misc_device);
	if (ret) {
		pr_err("failed to register %s: %d\n", DRIVER_NAME, ret);
		kvfree(register_samples);
		kvfree(resume_records);
		return ret;
	}
	pr_info("module loaded\n");
	return 0;
}

static void __exit my_module_exit(void)
{
	unsigned long cs_operations;
	unsigned long cs_completed;
	unsigned int cs_active_states;
	unsigned int cs_failures;
	int id, requests = atomic_read(&resume_requests);

	misc_deregister(&my_misc_device);
	kd_parallel_report();
	kd_shared_report();
	kd_chain_report();
	kd_deep_report();
	kd_context_report();
	kd_route_report();
	kd_signal_report();
	kd_waiter_signal_report();
	kd_ooo_report();
	kd_remote_ooo_report();
	kd_spin_oracle_report();
	kd_stack_change_report();
	kd_ticket_report();
	kd_gate_capacity_report();
	kd_acquired_spin_report();
	for (id = 0; id < min(requests, KD_RESUME_RECORDS); id++) {
		struct kd_resume_record *record = &resume_records[id];
		unsigned long expected = (((unsigned long)id + 1) * 3 + 17) ^
					 0x5a5a;

		if (record->before != 1 || record->called != 1 ||
		    record->after != 1 || record->value != expected)
			atomic_inc(&resume_failures);
	}
	pr_info("kd_resume records: requests=%d failures=%d\n", requests,
		atomic_read(&resume_failures));
	kd_register_report(requests);
	if (native_pending_contended)
		pr_info("kd_pending mutex: observed=%u acquired=%u\n",
			pending_mutex_observed, pending_mutex_acquired);
	if (native_pending_contended)
		pr_info("kd_pending spin: observed=%u acquired=%u\n",
			pending_spin_observed, pending_spin_acquired);
	if (native_resume_stage == 5)
		pr_info("kd_depth mutex stats: capacity=%d callee=%d native=%d\n",
			atomic_read(&depth_capacity_resumes),
			atomic_read(&depth_callee_resumes),
			atomic_read(&depth_native_runs));
	pr_info("kd_mutex oracle: inside=%d overlaps=%d\n",
		atomic_read(&mutex_inside), atomic_read(&mutex_overlaps));
	kvfree(resume_records);
	kvfree(register_samples);
	cs_failures = kd_cs_validate(&cs_operations, &cs_completed,
				     &cs_active_states);
	pr_info("module unloaded, final counter: %lu\n", cs_completed);
	pr_info("kd_cs integrity: operations=%lu active_states=%u failures=%u\n",
		cs_operations, cs_active_states, cs_failures);
	pr_info("mode2 api observations: %lu\n", mode2_api_observations);
	pr_info("mode5 api observations: %lu\n", mode5_api_observations);
	pr_info("mode5 api calls: %lu\n", mode5_api_calls);
	pr_info("kd_scalar service: mode=2 calls=%lu failures=%lu\n",
		mode2_scalar_calls, mode2_scalar_failures);
	pr_info("kd_scalar service: mode=5 calls=%lu failures=%lu\n",
		mode5_scalar_calls, mode5_scalar_failures);
	kd_multi_report();
	pr_info("kd_gs spin stats: attempts=%lld successes=%lld failures=%lld\n",
		(long long)atomic64_read(&gs_spin_attempts),
		(long long)atomic64_read(&gs_spin_successes),
		(long long)atomic64_read(&gs_spin_failures));
	pr_info("kd_gs mutex stats: attempts=%lld successes=%lld failures=%lld\n",
		(long long)atomic64_read(&gs_mutex_attempts),
		(long long)atomic64_read(&gs_mutex_successes),
		(long long)atomic64_read(&gs_mutex_failures));
}

module_init(my_module_init);
module_exit(my_module_exit);

MODULE_LICENSE("GPL");
