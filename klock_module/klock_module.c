/*
 * klock_module — test device driver for kdlock benchmarking.
 *
 * Exposes /dev/lock_dev with an ioctl interface.  Each ioctl call executes
 * a synthetic critical section using either a spinlock or mutex (depending
 * on mode), optionally with a nested lock or a kernel API call inside the
 * critical section.  When kdlock_km is loaded with target_process="klock_test",
 * these lock operations trigger the kdlock hooks and exercise the delegation
 * path.
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/ktime.h>

#define DRIVER_NAME "lock_dev"

extern int kd_spin_debug_waiter_count(raw_spinlock_t *lock);
extern int kd_mutex_debug_waiter_count(struct mutex *lock);

struct test_args {
	unsigned long loop_count;
	unsigned long work_load;
	unsigned int mode;
	unsigned int role;
};

#define IOC_MAGIC 'k'
#define IOC_RUN_TEST _IOW(IOC_MAGIC, 1, struct test_args)

static DEFINE_SPINLOCK(global_lock);
static DEFINE_SPINLOCK(nested_lock_a);
static DEFINE_SPINLOCK(nested_lock_b);
static DEFINE_SPINLOCK(nested_lock_c);
static DEFINE_MUTEX(global_mutex);
static DEFINE_MUTEX(nested_mutex_a);
static DEFINE_MUTEX(nested_mutex_b);

static unsigned long global_counter = 0;
static unsigned long mode2_api_observations;
static atomic_t inner_holder_ready = ATOMIC_INIT(0);
static atomic_t inner_direct_waiting = ATOMIC_INIT(0);
static atomic_t inner_nested_waiting = ATOMIC_INIT(0);
static atomic_t inner_trailing_waiting = ATOMIC_INIT(0);
static atomic_t outer_holder_ready = ATOMIC_INIT(0);
static atomic_t outer_direct_waiting = ATOMIC_INIT(0);
static atomic_t outer_nested_waiting = ATOMIC_INIT(0);
static atomic_t outer_trailing_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_holder_ready = ATOMIC_INIT(0);
static atomic_t mutex_inner_direct_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_nested_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_trailing_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_holder_ready = ATOMIC_INIT(0);
static atomic_t mutex_outer_direct_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_nested_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_trailing_waiting = ATOMIC_INIT(0);

#define MODE_ROLE_SYNCHRONIZED 0x80000000U
#define MODE_ROLE_OUTER_ONLY   0x40000000U

#define MODE_SPIN_CONTENTION 0
#define MODE_SPIN_NESTED 1
#define MODE_SPIN_API_IN_LOCK 2
#define MODE_MUTEX_CONTENTION 3
#define MODE_MUTEX_NESTED 4
#define MODE_MUTEX_API_IN_LOCK 5
#define MODE_SPIN_DEEP_NESTED 6
#define MODE_SPIN_OOO_NESTED 7
#define MODE_SPIN_INNER_CONTENTION 8
#define MODE_SPIN_ABORT_RECOVERY 9

static void run_contention_test(unsigned long loop_count, unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&global_lock);

		global_counter++;
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&global_lock);
	}
}

static void run_nested_spinlock_test(unsigned long loop_count, unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&nested_lock_a);
		spin_lock(&nested_lock_b);

		global_counter++;
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&nested_lock_b);
		spin_unlock(&nested_lock_a);
	}
}

static void run_deep_nested_spinlock_test(unsigned long loop_count,
					  unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&nested_lock_a);
		spin_lock(&nested_lock_b);
		spin_lock(&nested_lock_c);

		global_counter++;
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&nested_lock_c);
		spin_unlock(&nested_lock_b);
		spin_unlock(&nested_lock_a);
	}
}

static void run_ooo_nested_spinlock_test(unsigned long loop_count,
					 unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&nested_lock_a);
		spin_lock(&nested_lock_b);

		global_counter++;
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&nested_lock_a);
		spin_unlock(&nested_lock_b);
	}
}

static noinline void prepare_inner_nested_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&inner_holder_ready) ||
	       atomic_read(&inner_direct_waiting) < 2 ||
	       !atomic_read(&outer_holder_ready) ||
	       atomic_read(&outer_direct_waiting) < 2)
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 1 ||
	       kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 1)
		cpu_relax();
}

static noinline void run_inner_nested_role(unsigned long work_load,
					    bool synchronized,
					    bool outer_only)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_inner_nested_role(synchronized);
	atomic_set(&outer_nested_waiting, 1);
	smp_mb__after_atomic();
	spin_lock(&nested_lock_a);
	if (outer_only) {
		global_counter++;
		spin_unlock(&nested_lock_a);
		return;
	}
	atomic_set(&inner_nested_waiting, 1);
	smp_mb__after_atomic();
	spin_lock(&nested_lock_b);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
	spin_unlock(&nested_lock_a);
}

static noinline void prepare_inner_direct_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&inner_holder_ready))
		cpu_relax();
	atomic_inc(&inner_direct_waiting);
	smp_mb__after_atomic();
}

static noinline void run_inner_direct_role(unsigned long work_load,
					    bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_inner_direct_role(synchronized);
	spin_lock(&nested_lock_b);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
}

static noinline void run_inner_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&inner_holder_ready, 0);
	atomic_set(&inner_direct_waiting, 0);
	atomic_set(&inner_nested_waiting, 0);
	atomic_set(&inner_trailing_waiting, 0);
	smp_mb__after_atomic();

	spin_lock(&nested_lock_b);
	atomic_set(&inner_holder_ready, 1);
	smp_mb__after_atomic();
	while (atomic_read(&inner_direct_waiting) < 2 ||
	       !atomic_read(&inner_nested_waiting) ||
	       !atomic_read(&inner_trailing_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 3)
		cpu_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	global_counter++;
	spin_unlock(&nested_lock_b);
}

static noinline void prepare_inner_trailing_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&inner_nested_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 2)
		cpu_relax();
	atomic_set(&inner_trailing_waiting, 1);
	smp_mb__after_atomic();
}

static noinline void run_inner_trailing_role(unsigned long work_load,
					      bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_inner_trailing_role(synchronized);
	spin_lock(&nested_lock_b);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
}

static noinline void prepare_outer_direct_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&outer_holder_ready))
		cpu_relax();
	atomic_inc(&outer_direct_waiting);
	smp_mb__after_atomic();
}

static noinline void run_outer_direct_role(unsigned long work_load,
					    bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_outer_direct_role(synchronized);
	spin_lock(&nested_lock_a);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_a);
}

static noinline void run_outer_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&outer_holder_ready, 0);
	atomic_set(&outer_direct_waiting, 0);
	atomic_set(&outer_nested_waiting, 0);
	atomic_set(&outer_trailing_waiting, 0);
	smp_mb__after_atomic();

	spin_lock(&nested_lock_a);
	atomic_set(&outer_holder_ready, 1);
	smp_mb__after_atomic();
	while (atomic_read(&outer_direct_waiting) < 2 ||
	       !atomic_read(&outer_nested_waiting) ||
	       !atomic_read(&outer_trailing_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 3)
		cpu_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	global_counter++;
	spin_unlock(&nested_lock_a);
}

static noinline void prepare_outer_trailing_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&outer_nested_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 2)
		cpu_relax();
	atomic_set(&outer_trailing_waiting, 1);
	smp_mb__after_atomic();
}

static noinline void run_outer_trailing_role(unsigned long work_load,
					      bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_outer_trailing_role(synchronized);
	spin_lock(&nested_lock_a);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_a);
}

static void run_inner_contention_spinlock_test(unsigned long loop_count,
					       unsigned long work_load,
					       unsigned int role)
{
	unsigned long i;
	unsigned int sync_role = role & ~(MODE_ROLE_SYNCHRONIZED |
					 MODE_ROLE_OUTER_ONLY);
	bool synchronized = role & MODE_ROLE_SYNCHRONIZED;
	bool outer_only = role & MODE_ROLE_OUTER_ONLY;

	for (i = 0; i < loop_count; i++) {
		if (sync_role == 0)
			run_inner_nested_role(work_load, synchronized, outer_only);
		else if (synchronized && sync_role == 1)
			run_inner_holder_role(work_load);
		else if (synchronized && sync_role == 3)
			run_outer_holder_role(work_load);
		else if (sync_role == 4 || sync_role == 6)
			run_outer_direct_role(work_load, synchronized);
		else if (sync_role == 7)
			run_inner_trailing_role(work_load, synchronized);
		else if (sync_role == 8)
			run_outer_trailing_role(work_load, synchronized);
		else
			run_inner_direct_role(work_load, synchronized);
	}
}

static noinline void run_abort_target_role(unsigned long work_load,
					   bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	if (synchronized) {
		while (!atomic_read(&outer_holder_ready) ||
		       atomic_read(&outer_direct_waiting) < 2)
			cpu_relax();
		while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 1)
			cpu_relax();
		atomic_set(&outer_nested_waiting, 1);
		smp_mb__after_atomic();
	}
	spin_lock(&nested_lock_a);
	spin_lock(&nested_lock_b);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
	spin_unlock(&nested_lock_a);
}

static noinline void run_abort_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&outer_holder_ready, 0);
	atomic_set(&outer_direct_waiting, 0);
	atomic_set(&outer_nested_waiting, 0);
	atomic_set(&outer_trailing_waiting, 0);
	smp_mb__after_atomic();

	spin_lock(&nested_lock_a);
	atomic_set(&outer_holder_ready, 1);
	smp_mb__after_atomic();
	while (atomic_read(&outer_direct_waiting) < 2 ||
	       !atomic_read(&outer_nested_waiting) ||
	       !atomic_read(&outer_trailing_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 3)
		cpu_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	global_counter++;
	spin_unlock(&nested_lock_a);
}

static noinline void run_abort_trailing_role(unsigned long work_load,
					     bool synchronized)
{
	if (synchronized) {
		while (!atomic_read(&outer_nested_waiting))
			cpu_relax();
		while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 2)
			cpu_relax();
		atomic_set(&outer_trailing_waiting, 1);
		smp_mb__after_atomic();
	}
	run_outer_direct_role(work_load, false);
}

static void run_abort_recovery_spinlock_test(unsigned long loop_count,
					      unsigned long work_load,
					      unsigned int role)
{
	unsigned long i;
	unsigned int sync_role = role & ~MODE_ROLE_SYNCHRONIZED;
	bool synchronized = role & MODE_ROLE_SYNCHRONIZED;

	for (i = 0; i < loop_count; i++) {
		if (sync_role == 0)
			run_abort_target_role(work_load, synchronized);
		else if (synchronized && sync_role == 1)
			run_abort_holder_role(work_load);
		else if (sync_role == 4)
			run_abort_trailing_role(work_load, synchronized);
		else
			run_outer_direct_role(work_load, synchronized);
	}
}

static void run_api_in_lock_test(unsigned long loop_count, unsigned long work_load)
{
	unsigned long i, j;
	unsigned long now;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&global_lock);

		global_counter++;
		now = (unsigned long)ktime_get_ns();
		dummy_computation ^= (int)(now & 0xffff);
		if (now)
			mode2_api_observations++;

		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&global_lock);
	}
}

static void run_mutex_contention_test(unsigned long loop_count, unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		mutex_lock(&global_mutex);

		global_counter++;
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		mutex_unlock(&global_mutex);
	}
}

static noinline void prepare_nested_mutex_role(void)
{
	while (!atomic_read(&mutex_inner_holder_ready) ||
	       !atomic_read(&mutex_inner_direct_waiting) ||
	       !atomic_read(&mutex_outer_holder_ready) ||
	       !atomic_read(&mutex_outer_direct_waiting))
		cpu_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 1 ||
	       kd_mutex_debug_waiter_count(&nested_mutex_b) < 1)
		cpu_relax();
}

static noinline void run_nested_mutex_cs(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&mutex_outer_nested_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	atomic_set(&mutex_inner_nested_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);

	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;

	mutex_unlock(&nested_mutex_b);
	mutex_unlock(&nested_mutex_a);
}

static noinline void run_nested_mutex_role(unsigned long work_load,
					    bool synchronized)
{
	if (synchronized)
		prepare_nested_mutex_role();
	run_nested_mutex_cs(work_load);
}

static noinline void run_inner_mutex_direct_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_inner_holder_ready))
		cpu_relax();
	atomic_set(&mutex_inner_direct_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_b);
}

static noinline void run_inner_mutex_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&mutex_inner_holder_ready, 0);
	atomic_set(&mutex_inner_direct_waiting, 0);
	atomic_set(&mutex_inner_nested_waiting, 0);
	atomic_set(&mutex_inner_trailing_waiting, 0);
	smp_mb__after_atomic();

	mutex_lock(&nested_mutex_b);
	atomic_set(&mutex_inner_holder_ready, 1);
	smp_mb__after_atomic();
	while (!atomic_read(&mutex_inner_direct_waiting) ||
	       !atomic_read(&mutex_inner_nested_waiting) ||
	       !atomic_read(&mutex_inner_trailing_waiting))
		cpu_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_b) < 3)
		cpu_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	global_counter++;
	mutex_unlock(&nested_mutex_b);
}

static noinline void run_inner_mutex_trailing_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_inner_nested_waiting))
		cpu_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_b) < 2)
		cpu_relax();
	atomic_set(&mutex_inner_trailing_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_b);
}

static noinline void run_outer_mutex_direct_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_outer_holder_ready))
		cpu_relax();
	atomic_set(&mutex_outer_direct_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_a);
}

static noinline void run_outer_mutex_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&mutex_outer_holder_ready, 0);
	atomic_set(&mutex_outer_direct_waiting, 0);
	atomic_set(&mutex_outer_nested_waiting, 0);
	atomic_set(&mutex_outer_trailing_waiting, 0);
	smp_mb__after_atomic();

	mutex_lock(&nested_mutex_a);
	atomic_set(&mutex_outer_holder_ready, 1);
	smp_mb__after_atomic();
	while (!atomic_read(&mutex_outer_direct_waiting) ||
	       !atomic_read(&mutex_outer_nested_waiting) ||
	       !atomic_read(&mutex_outer_trailing_waiting))
		cpu_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 3)
		cpu_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	global_counter++;
	mutex_unlock(&nested_mutex_a);
}

static noinline void run_outer_mutex_trailing_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_outer_nested_waiting))
		cpu_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 2)
		cpu_relax();
	atomic_set(&mutex_outer_trailing_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	global_counter++;
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_a);
}

static void run_nested_mutex_test(unsigned long loop_count,
				  unsigned long work_load,
				  unsigned int role)
{
	unsigned long i;
	unsigned int sync_role = role & ~MODE_ROLE_SYNCHRONIZED;
	bool synchronized = role & MODE_ROLE_SYNCHRONIZED;

	for (i = 0; i < loop_count; i++) {
		if (!synchronized || sync_role == 0)
			run_nested_mutex_role(work_load, synchronized);
		else if (sync_role == 1)
			run_inner_mutex_holder_role(work_load);
		else if (sync_role == 2)
			run_inner_mutex_direct_role(work_load);
		else if (sync_role == 3)
			run_outer_mutex_holder_role(work_load);
		else if (sync_role == 4)
			run_outer_mutex_direct_role(work_load);
		else if (sync_role == 5)
			run_inner_mutex_trailing_role(work_load);
		else if (sync_role == 6)
			run_outer_mutex_trailing_role(work_load);
	}
}

static void run_api_in_mutex_test(unsigned long loop_count, unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		mutex_lock(&global_mutex);

		global_counter++;
		dummy_computation ^= (int)(ktime_get_ns() & 0xffff);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		mutex_unlock(&global_mutex);
	}
}

static long my_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct test_args k_args;

	switch (cmd) {
	case IOC_RUN_TEST:
		if (copy_from_user(&k_args, (void __user *)arg, sizeof(k_args)))
			return -EFAULT;
		if (k_args.mode == MODE_SPIN_CONTENTION)
			run_contention_test(k_args.loop_count, k_args.work_load);
		else if (k_args.mode == MODE_SPIN_NESTED)
			run_nested_spinlock_test(k_args.loop_count,
						 k_args.work_load);
		else if (k_args.mode == MODE_SPIN_API_IN_LOCK)
			run_api_in_lock_test(k_args.loop_count, k_args.work_load);
		else if (k_args.mode == MODE_MUTEX_CONTENTION)
			run_mutex_contention_test(k_args.loop_count,
						 k_args.work_load);
		else if (k_args.mode == MODE_MUTEX_NESTED)
			run_nested_mutex_test(k_args.loop_count,
					      k_args.work_load,
					      k_args.role);
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
			run_inner_contention_spinlock_test(
				k_args.loop_count, k_args.work_load, k_args.role);
		else if (k_args.mode == MODE_SPIN_ABORT_RECOVERY)
			run_abort_recovery_spinlock_test(
				k_args.loop_count, k_args.work_load, k_args.role);
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

static int __init my_module_init(void)
{
	int ret;

	global_counter = 0;
	mode2_api_observations = 0;
	ret = misc_register(&my_misc_device);
	if (ret) {
		pr_err("failed to register %s: %d\n", DRIVER_NAME, ret);
		return ret;
	}
	pr_info("module loaded\n");
	return 0;
}

static void __exit my_module_exit(void)
{
	misc_deregister(&my_misc_device);
	pr_info("module unloaded, final counter: %lu\n", global_counter);
	pr_info("mode2 api observations: %lu\n", mode2_api_observations);
}

module_init(my_module_init);
module_exit(my_module_exit);

MODULE_LICENSE("GPL");
