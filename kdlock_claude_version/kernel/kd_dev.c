// SPDX-License-Identifier: GPL-2.0
/*
 * /dev/kdlock: control channel for the userspace translator, plus a
 * read-only statistics file in debugfs.
 *
 * read()  drains learning/request events (struct kd_event), never blocks.
 *         The lock slow paths that produce events may run under any lock,
 *         so they do not wake anybody; the translator polls.
 * ioctl() see kd_uapi.h.
 */
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/capability.h>
#include <linux/debugfs.h>
#include <linux/seq_file.h>
#include "kd_internal.h"

static int kd_dev_open(struct inode *inode, struct file *file)
{
	return capable(CAP_SYS_ADMIN) ? 0 : -EPERM;
}

static ssize_t kd_dev_read(struct file *file, char __user *buf, size_t len, loff_t *pos)
{
	return kd_event_read(buf, len);
}

static long kd_dev_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	return kd_image_ioctl(cmd, arg);
}

static const struct file_operations kd_dev_fops = {
	.owner		= THIS_MODULE,
	.open		= kd_dev_open,
	.read		= kd_dev_read,
	.unlocked_ioctl	= kd_dev_ioctl,
	.compat_ioctl	= compat_ptr_ioctl,
	.llseek		= noop_llseek,
};

static struct miscdevice kd_miscdev = {
	.minor	= MISC_DYNAMIC_MINOR,
	.name	= "kdlock",
	.fops	= &kd_dev_fops,
};

static const char * const kd_stat_names[KD_STAT_NR] = {
	[KD_STAT_SESSIONS]		= "sessions",
	[KD_STAT_DELEGATED]		= "delegated",
	[KD_STAT_HANDBACK]		= "handback",
	[KD_STAT_HANDBACK_PINNED]	= "handback_pinned",
	[KD_STAT_NESTED_LOCAL]		= "nested_local",
	[KD_STAT_NESTED_DELEGATED]	= "nested_delegated",
	[KD_STAT_OFFERED]		= "offered",
	[KD_STAT_PLAIN]			= "plain",
	[KD_STAT_NUMA_DEFERRED]		= "numa_deferred",
};

static int kd_stats_show(struct seq_file *m, void *v)
{
	int i;

	seq_printf(m, "delegation %d\n", static_key_enabled(&kd_delegation.key));
	for (i = 0; i < KD_STAT_NR; i++)
		seq_printf(m, "%s %lu\n", kd_stat_names[i], kd_stat_sum(i));
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(kd_stats);

static int __init kd_dev_init(void)
{
	int ret = misc_register(&kd_miscdev);

	if (ret)
		return ret;
	debugfs_create_file("kdlock_stats", 0444, NULL, NULL, &kd_stats_fops);
	return 0;
}
device_initcall(kd_dev_init);
