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

struct test_args {
	unsigned long loop_count;
	unsigned long work_load;
	unsigned int mode;
};

#define IOC_MAGIC 'k'
#define IOC_RUN_TEST _IOW(IOC_MAGIC, 1, struct test_args)

static DEFINE_SPINLOCK(global_lock);
static DEFINE_SPINLOCK(nested_lock_a);
static DEFINE_SPINLOCK(nested_lock_b);
static DEFINE_MUTEX(global_mutex);
static DEFINE_MUTEX(nested_mutex_a);
static DEFINE_MUTEX(nested_mutex_b);

static unsigned long global_counter = 0;

#define MODE_SPIN_CONTENTION 0
#define MODE_SPIN_NESTED 1
#define MODE_SPIN_API_IN_LOCK 2
#define MODE_MUTEX_CONTENTION 3
#define MODE_MUTEX_NESTED 4
#define MODE_MUTEX_API_IN_LOCK 5

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

static void run_api_in_lock_test(unsigned long loop_count, unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&global_lock);

		global_counter += (unsigned long)(ktime_get_ns() & 0xffff);

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

static void run_nested_mutex_test(unsigned long loop_count, unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		mutex_lock(&nested_mutex_a);
		mutex_lock(&nested_mutex_b);

		global_counter++;
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		mutex_unlock(&nested_mutex_b);
		mutex_unlock(&nested_mutex_a);
	}
}

static void run_api_in_mutex_test(unsigned long loop_count, unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		mutex_lock(&global_mutex);

		global_counter += (unsigned long)(ktime_get_ns() & 0xffff);
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
					      k_args.work_load);
		else if (k_args.mode == MODE_MUTEX_API_IN_LOCK)
			run_api_in_mutex_test(k_args.loop_count,
					      k_args.work_load);
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
}

module_init(my_module_init);
module_exit(my_module_exit);

MODULE_LICENSE("GPL");
