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

extern struct exe_info *exes;

int nf_major = 0;
int nf_minor = 0;

struct nf_dev *nf_device;
static struct class *nf_class;
static struct device *nf_device_node;

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
#define kd_class_create(name) class_create(name)
#else
#define kd_class_create(name) class_create(THIS_MODULE, name)
#endif

static int nf_open(struct inode *inode, struct file *filp)
{
	return 0;
}

static int nf_release(struct inode *inode, struct file *filp)
{
	return 0;
}

static ssize_t nf_read(struct file *filp, char __user *buf, size_t count,
		       loff_t *fpos)
{
	ssize_t len = 0;
	const int sz = sizeof(struct exe_info);
	int i;

	for (i = 0; i < MAX_EXE; i++) {
		if (exes[i].status_code == F_UN_USED)
			continue;
		if (len + sz > count)
			break;
		if (copy_to_user(buf + len, &exes[i], sz))
			return -EFAULT;
		len += sz;
	}

	return len;
}

static ssize_t nf_write(struct file *filp, const char __user *buf, size_t count,
			loff_t *f_pos)
{
	int len;
	const char __user *payload;
	struct exe_info *p;
	struct recv_pkt *head;

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
	p = get_exe(head->pid, head->RIP);

	printk(KERN_EMERG "write to kernel %d %px %d %ld p-%px\n", head->pid,
	       (void *)head->RIP, head->status_code, head->offset, p);
	if (p->RIP == head->RIP && p->pid == head->pid) {
		if (copy_from_user(p->code_block + head->offset, payload, len)) {
			kfree(head);
			return -EFAULT;
		}
		p->status_code = head->status_code;
		kfree(head);
		return count;
	}

	printk(KERN_EMERG "exe to be written not found %d %p\n", head->pid,
	       (void *)head->RIP);
	kfree(head);
	return count;
}

static const struct file_operations nf_fops = {
	.owner = THIS_MODULE,
	.read = nf_read,
	.write = nf_write,
	.open = nf_open,
	.release = nf_release,
};

static int nf_setup_cdev(struct nf_dev *dev)
{
	int err, devno = MKDEV(nf_major, nf_minor);

	cdev_init(&dev->cdev, &nf_fops);
	dev->cdev.owner = THIS_MODULE;
	dev->cdev.ops = &nf_fops;
	err = cdev_add(&dev->cdev, devno, 1);
	if (err)
		KD_PR_INFO("error %d adding kd_dev\n", err);

	return err;
}

void sys_init(void)
{
	int ret;
	dev_t dev = 0;

	if (nf_major) {
		dev = MKDEV(nf_major, nf_minor);
		ret = register_chrdev_region(dev, 1, "kd_dev");
	} else {
		ret = alloc_chrdev_region(&dev, nf_minor, 1, "kd_dev");
		nf_major = MAJOR(dev);
	}
	if (ret < 0) {
		KD_PR_INFO("kd_dev: can't get major %d\n", nf_major);
		return;
	}

	nf_device = kzalloc(sizeof(*nf_device), GFP_KERNEL);
	if (!nf_device)
		goto err_chrdev;

	ret = nf_setup_cdev(nf_device);
	if (ret)
		goto err_device;

	nf_class = kd_class_create("kd_dev");
	if (IS_ERR(nf_class)) {
		ret = PTR_ERR(nf_class);
		nf_class = NULL;
		goto err_cdev;
	}

	nf_device_node = device_create(nf_class, NULL, dev, NULL, "kd_dev");
	if (IS_ERR(nf_device_node)) {
		ret = PTR_ERR(nf_device_node);
		nf_device_node = NULL;
		goto err_class;
	}

	return;

err_class:
	class_destroy(nf_class);
	nf_class = NULL;
err_cdev:
	cdev_del(&nf_device->cdev);
err_device:
	kfree(nf_device);
	nf_device = NULL;
err_chrdev:
	unregister_chrdev_region(dev, 1);
	KD_PR_INFO("kd_dev init failed: %d\n", ret);
}

void sys_exit(void)
{
	dev_t devno = MKDEV(nf_major, nf_minor);

	if (nf_device_node)
		device_destroy(nf_class, devno);
	if (nf_class)
		class_destroy(nf_class);
	if (nf_device) {
		cdev_del(&nf_device->cdev);
		kfree(nf_device);
		nf_device = NULL;
	}
	unregister_chrdev_region(devno, 1);
}
