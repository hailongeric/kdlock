#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/string.h>
#include <linux/types.h>
#include <linux/uaccess.h>
#include <linux/version.h>

#include "exe.h"
#include "sys.h"
#include "utils.h"

static dev_t kd_devno;
static struct cdev kd_cdev;
static struct class *kd_class;
/* Serializes uploads with rejection, not execution of already published code. */
static DEFINE_MUTEX(kd_publish_lock);

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
#define kd_class_create(name) class_create(name)
#else
#define kd_class_create(name) class_create(THIS_MODULE, name)
#endif

static ssize_t kd_dev_read(struct file *file, char __user *buf, size_t count,
			   loff_t *offset)
{
	const size_t entry_size = sizeof(struct kd_exe_info);
	size_t len = 0;
	unsigned int i;

	(void)file;
	(void)offset;
	for (i = 0; i < KD_MAX_EXE; i++) {
		const struct kd_exe_info *entry = kd_exe_get_slot(i);
		struct kd_exe_info snapshot;
		int status;

		if (!entry)
			return len ? (ssize_t)len : -ENODEV;
		status = smp_load_acquire(&entry->status_code);
		if (status == KD_EXE_UNUSED)
			continue;
		if (entry_size > count - len)
			break;

		memcpy(&snapshot, entry, entry_size);
		snapshot.status_code = status;
		if (copy_to_user(buf + len, &snapshot, entry_size))
			return -EFAULT;
		len += entry_size;
	}

	return len;
}

static ssize_t kd_dev_write_locked(const char __user *buf, size_t count)
{
	struct kd_recv_pkt head;
	struct kd_exe_info *entry;
	const char __user *payload;
	size_t len;

	if (count < sizeof(head))
		return -EINVAL;
	if (copy_from_user(&head, buf, sizeof(head)))
		return -EFAULT;

	len = count - sizeof(head);
	payload = buf + sizeof(head);
	entry = kd_get_exe(head.pid, head.RIP);
	if (!entry)
		return -ENOSPC;
	if (READ_ONCE(entry->RIP) != head.RIP ||
	    READ_ONCE(entry->pid) != head.pid ||
	    !READ_ONCE(entry->code_block)) {
		KD_PR_ERR("translation entry not found: pid=%d rip=%px\n",
			  head.pid, (void *)head.RIP);
		return -ENOENT;
	}
	if (head.status_code == KD_EXE_NATIVE_ONLY) {
		if (len || head.offset)
			return -EINVAL;
		if (smp_load_acquire(&entry->status_code) !=
		    KD_EXE_NATIVE_ONLY) {
			kd_exe_publish_status(entry, KD_EXE_NATIVE_ONLY);
			KD_PR_INFO("JIT native-only: pid=%d rip=%px\n",
				   head.pid, (void *)head.RIP);
		}
		return count;
	}
	if (!len || head.offset > KD_CODE_BLOCK_SIZE ||
	    len > KD_CODE_BLOCK_SIZE - head.offset ||
	    (head.status_code != KD_EXE_UNINIT &&
	     head.status_code != KD_EXE_NORMAL))
		return -EINVAL;
	if (smp_load_acquire(&entry->status_code) == KD_EXE_NATIVE_ONLY)
		return -EPERM;

	KD_PR_INFO(
		"install JIT chunk: pid=%d rip=%px status=%d offset=%lu bytes=%zu\n",
		head.pid, (void *)head.RIP, head.status_code, head.offset, len);

	if (copy_from_user((char *)entry->code_block + head.offset, payload,
			   len))
		return -EFAULT;
	/* Keep the prior miss state recoverable until the full image is present. */
	if (head.status_code == KD_EXE_NORMAL)
		kd_exe_publish_status(entry, KD_EXE_NORMAL);
	return count;
}

static ssize_t kd_dev_write(struct file *file, const char __user *buf,
			    size_t count, loff_t *offset)
{
	ssize_t ret;

	(void)file;
	(void)offset;
	if (mutex_lock_interruptible(&kd_publish_lock))
		return -ERESTARTSYS;
	ret = kd_dev_write_locked(buf, count);
	mutex_unlock(&kd_publish_lock);
	return ret;
}

static const struct file_operations kd_dev_fops = {
	.owner = THIS_MODULE,
	.read = kd_dev_read,
	.write = kd_dev_write,
};

int kd_sys_init(void)
{
	struct device *device;
	int ret;

	ret = alloc_chrdev_region(&kd_devno, 0, 1, "kd_dev");
	if (ret) {
		KD_PR_ERR("kd_dev number allocation failed: %d\n", ret);
		return ret;
	}

	cdev_init(&kd_cdev, &kd_dev_fops);
	kd_cdev.owner = THIS_MODULE;
	ret = cdev_add(&kd_cdev, kd_devno, 1);
	if (ret)
		goto err_chrdev;

	kd_class = kd_class_create("kd_dev");
	if (IS_ERR(kd_class)) {
		ret = PTR_ERR(kd_class);
		kd_class = NULL;
		goto err_cdev;
	}

	device = device_create(kd_class, NULL, kd_devno, NULL, "kd_dev");
	if (IS_ERR(device)) {
		ret = PTR_ERR(device);
		goto err_class;
	}

	return 0;

err_class:
	class_destroy(kd_class);
	kd_class = NULL;
err_cdev:
	cdev_del(&kd_cdev);
err_chrdev:
	unregister_chrdev_region(kd_devno, 1);
	kd_devno = 0;
	KD_PR_ERR("kd_dev init failed: %d\n", ret);
	return ret;
}

void kd_sys_exit(void)
{
	device_destroy(kd_class, kd_devno);
	class_destroy(kd_class);
	kd_class = NULL;
	cdev_del(&kd_cdev);
	unregister_chrdev_region(kd_devno, 1);
	kd_devno = 0;
}
