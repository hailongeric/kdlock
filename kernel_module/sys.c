#include <linux/types.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/slab.h>
#include <linux/errno.h>
#include <asm/uaccess.h>
#include <linux/device.h>
#include <linux/version.h>

#include "sys.h"
#include "exe.h"
#include "utils.h"

extern struct kd_exe_info *kd_exes;

int kd_major = 0;
int kd_minor = 0;

struct kd_dev *kd_device;
static struct class *kd_class;
static struct device *kd_device_node;

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
#define kd_class_create(name) class_create(name)
#else
#define kd_class_create(name) class_create(THIS_MODULE, name)
#endif

static int kd_dev_open(struct inode *inode, struct file *filp)
{
	return 0;
}

static int kd_dev_release(struct inode *inode, struct file *filp)
{
	return 0;
}

static ssize_t kd_dev_read(struct file *filp, char __user *buf, size_t count,
		       loff_t *fpos)
{
	ssize_t len = 0;
	const int sz = sizeof(struct kd_exe_info);
	int i;

	for (i = 0; i < KD_MAX_EXE; i++) {
		if (kd_exes[i].status_code == KD_EXE_UNUSED)
			continue;
		if (len + sz > count)
			break;
		if (copy_to_user(buf + len, &kd_exes[i], sz))
			return -EFAULT;
		len += sz;
	}

	return len;
}

static ssize_t kd_dev_write(struct file *filp, const char __user *buf, size_t count,
			loff_t *f_pos)
{
	int len;
	const char __user *payload;
	struct kd_exe_info *p;
	struct kd_recv_pkt *head;

	if (count < sizeof(*head))
		return -EINVAL;

	head = kmalloc(sizeof(*head), GFP_KERNEL);
	if (!head)
		return -ENOMEM;
	if (copy_from_user(head, buf, sizeof(*head))) {
		kfree(head);
		return -EFAULT;
	}

	len = count - sizeof(*head);
	payload = buf + sizeof(*head);
	p = kd_get_exe(head->pid, head->RIP);
	if (!p) {
		kfree(head);
		return -ENOSPC;
	}
	if (!READ_ONCE(p->code_block) || head->offset > KD_CODE_BLOCK_SIZE ||
	    len > KD_CODE_BLOCK_SIZE - head->offset ||
	    (head->status_code != KD_EXE_UNINIT &&
	     head->status_code != KD_EXE_NORMAL)) {
		kfree(head);
		return -EINVAL;
	}

	printk(KERN_EMERG "write to kernel %d %px %d %ld p-%px\n", head->pid,
	       (void *)head->RIP, head->status_code, head->offset, p);
	if (p->RIP == head->RIP && p->pid == head->pid) {
		if (copy_from_user(p->code_block + head->offset, payload, len)) {
			kfree(head);
			return -EFAULT;
		}
		smp_store_release(&p->status_code, head->status_code);
		kfree(head);
		return count;
	}

	printk(KERN_EMERG "exe to be written not found %d %p\n", head->pid,
	       (void *)head->RIP);
	kfree(head);
	return count;
}

static const struct file_operations kd_dev_fops = {
	.owner = THIS_MODULE,
	.read = kd_dev_read,
	.write = kd_dev_write,
	.open = kd_dev_open,
	.release = kd_dev_release,
};

static int kd_setup_cdev(struct kd_dev *dev)
{
	int err, devno = MKDEV(kd_major, kd_minor);

	cdev_init(&dev->cdev, &kd_dev_fops);
	dev->cdev.owner = THIS_MODULE;
	dev->cdev.ops = &kd_dev_fops;
	err = cdev_add(&dev->cdev, devno, 1);
	if (err)
		KD_PR_INFO("error %d adding kd_dev\n", err);

	return err;
}

void kd_sys_init(void)
{
	int ret;
	dev_t dev = 0;

	if (kd_major) {
		dev = MKDEV(kd_major, kd_minor);
		ret = register_chrdev_region(dev, 1, "kd_dev");
	} else {
		ret = alloc_chrdev_region(&dev, kd_minor, 1, "kd_dev");
		kd_major = MAJOR(dev);
	}
	if (ret < 0) {
		KD_PR_INFO("kd_dev: can't get major %d\n", kd_major);
		return;
	}

	kd_device = kzalloc(sizeof(*kd_device), GFP_KERNEL);
	if (!kd_device)
		goto err_chrdev;

	ret = kd_setup_cdev(kd_device);
	if (ret)
		goto err_device;

	kd_class = kd_class_create("kd_dev");
	if (IS_ERR(kd_class)) {
		ret = PTR_ERR(kd_class);
		kd_class = NULL;
		goto err_cdev;
	}

	kd_device_node = device_create(kd_class, NULL, dev, NULL, "kd_dev");
	if (IS_ERR(kd_device_node)) {
		ret = PTR_ERR(kd_device_node);
		kd_device_node = NULL;
		goto err_class;
	}

	return;

err_class:
	class_destroy(kd_class);
	kd_class = NULL;
err_cdev:
	cdev_del(&kd_device->cdev);
err_device:
	kfree(kd_device);
	kd_device = NULL;
err_chrdev:
	unregister_chrdev_region(dev, 1);
	KD_PR_INFO("kd_dev init failed: %d\n", ret);
}

void kd_sys_exit(void)
{
	dev_t devno = MKDEV(kd_major, kd_minor);

	if (kd_device_node)
		device_destroy(kd_class, devno);
	if (kd_class)
		class_destroy(kd_class);
	if (kd_device) {
		cdev_del(&kd_device->cdev);
		kfree(kd_device);
		kd_device = NULL;
	}
	unregister_chrdev_region(devno, 1);
}
