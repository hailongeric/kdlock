// SPDX-License-Identifier: GPL-2.0
/* Independent external module: native arm loads without kdlock symbols. */
#include <linux/build_bug.h>
#include <linux/atomic.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include "api.h"
#include "payload.h"
#include "post_work.h"

/* >= 0 counts admitted workers; -1 reserves a quiescent snapshot. A plain
 * active==0 check is insufficient: another worker could enter while counts
 * are being copied. This atomic gate is outside the measured spinlock. */
static atomic_t sc_control __aligned(SC_LINE_BYTES) = ATOMIC_INIT(0);

static bool sc_run_enter(void)
{
	return atomic_add_unless(&sc_control, 1, -1);
}

static void sc_run_exit(void)
{
	/* Publish the completed payload before the last worker allows a reader. */
	(void)atomic_dec_return_release(&sc_control);
}

static bool sc_snapshot_begin(void)
{
	return atomic_cmpxchg_acquire(&sc_control, 0, -1) == 0;
}

static void sc_snapshot_end(void)
{
	atomic_set_release(&sc_control, 0);
}

static long sc_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct sc_counts counts = { 0 };
	struct sc_layout layout = {
		.version = SC_VERSION, .line_bytes = SC_LINE_BYTES,
		.slots = SC_SLOTS, .lock_bytes = sizeof(sc_lock),
		.lock_addr = (unsigned long)&sc_lock,
		.control_addr = (unsigned long)&sc_control,
		.data_addr = (unsigned long)sc_data,
	};
	struct sc_run run;
	void (*body)(void);
	__u64 post_state = 1;
	int i;

	(void)file;
	switch (cmd) {
	case SC_LAYOUT:
		for (i = 0; i < SC_SLOTS; i++)
			layout.slot_addr[i] = (unsigned long)&sc_data[i];
		return copy_to_user(user, &layout, sizeof(layout)) ? -EFAULT : 0;
	case SC_COUNTS:
		if (!sc_snapshot_begin())
			return -EBUSY;
		for (i = 0; i < SC_SLOTS; i++)
			counts.values[i] = READ_ONCE(sc_data[i].value);
		sc_snapshot_end();
		return copy_to_user(user, &counts, sizeof(counts)) ? -EFAULT : 0;
	case SC_RUN:
		if (copy_from_user(&run, user, sizeof(run)))
			return -EFAULT;
		if (run.reserved || !run.iterations ||
		    run.iterations > SC_MAX_ITERATIONS)
			return -EINVAL;
		switch (run.cachelines) {
		case 1: body = sc_body_1; break;
		case 2: body = sc_body_2; break;
		case 4: body = sc_body_4; break;
		case 8: body = sc_body_8; break;
		case 16: body = sc_body_16; break;
		default: return -EINVAL;
		}
		if (!sc_run_enter())
			return -EBUSY;
		/* One ioctl owns this full batch. A small register dependency chain
		 * after unlock leaves an acquisition gap without scheduling or a
		 * shared counter. Count both the CS and this work in batch time. */
		for (run.completed = 0; run.completed < run.iterations; run.completed++) {
			body();
			post_state = sc_post_work(post_state);
		}
		sc_run_exit();
		if (copy_to_user(user, &run, sizeof(run)))
			return -EFAULT;
		return 0;
	default:
		return -ENOTTY;
	}
}

static const struct file_operations sc_fops = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = sc_ioctl,
	.llseek = no_llseek,
};
static struct miscdevice sc_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "spin_cacheline",
	.fops = &sc_fops, .mode = 0600,
};

static int __init sc_init(void)
{
	BUILD_BUG_ON(sizeof(struct sc_slot) != SC_LINE_BYTES);
	BUILD_BUG_ON(__alignof__(struct sc_slot) != SC_LINE_BYTES);
	BUILD_BUG_ON(sizeof(sc_lock) > SC_LINE_BYTES);
	BUILD_BUG_ON(sizeof(sc_control) > SC_LINE_BYTES);
	BUILD_BUG_ON(offsetof(spinlock_t, rlock) != 0);
	spin_lock_init(&sc_lock);
	atomic_set(&sc_control, 0);
	return misc_register(&sc_device);
}

static void __exit sc_exit(void)
{
	WARN_ON(atomic_read(&sc_control));
	misc_deregister(&sc_device);
}
module_init(sc_init);
module_exit(sc_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Unrolled spinlock cacheline payload microbenchmark");
