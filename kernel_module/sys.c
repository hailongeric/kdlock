/* /dev/kd_dev is the daemon's registry/image channel and source-control API.
 * Writable opens retain one translation-session writer; readonly status/CAPS
 * opens do not. Retirement closes admission before releasing source pins.
 * Mutex uploads stage complete immutable versions; spin images stay in place. */
#include <linux/build_bug.h>
#include <linux/cdev.h>
#include <linux/capability.h>
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/kallsyms.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/percpu.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/types.h>
#include <linux/uaccess.h>
#include <linux/version.h>

#include "exe.h"
#include "kd_lock.h"
#include "kd_mutex.h"
#include "kd_source.h"
#include "kd_spin_entry.h"
#include "sys.h"
#include "utils.h"

static dev_t kd_devno;
static struct cdev kd_cdev;
static struct class *kd_class;
/* Serializes uploads with rejection, not execution of already published code. */
static DEFINE_KD_MUTEX(kd_publish_lock);

static int kd_dev_open(struct inode *inode, struct file *file)
{
	/* Do not expose a lease from a provider whose initialization can fail. */
	if (READ_ONCE(THIS_MODULE->state) != MODULE_STATE_LIVE)
		return -ENODEV;
	file->private_data = NULL;
	if (file->f_mode & FMODE_WRITE) {
		struct kd_image_upload *upload = kzalloc(sizeof(*upload), GFP_KERNEL);

		if (!upload)
			return -ENOMEM;
		if (!kd_source_writer_get()) {
			kfree(upload);
			return -ESHUTDOWN;
		}
		file->private_data = upload;
	}
	return nonseekable_open(inode, file);
}

static int kd_dev_release(struct inode *inode, struct file *file)
{
	(void)inode;
	/* dup/fork share one open description; only its final release drops this. */
	if (file->private_data) {
		struct kd_image_upload *upload = file->private_data;

		kd_image_discard(upload->image);
		kfree(upload);
		kd_source_writer_put();
	}
	return 0;
}

static struct kd_jit_caps kd_jit_capabilities(void)
{
	struct kd_jit_caps caps = {
		.version = KD_JIT_CAPS_VERSION,
		.features = KD_JIT_CAP_MUTEX_STACK | KD_JIT_CAP_MUTEX_IMAGES |
			KD_JIT_CAP_MUTEX_EXCLUSIVE | KD_JIT_CAP_NATIVE_ESCAPE,
		.mutex_stack_bytes = KD_JIT_MUTEX_STACK_BYTES,
	};
#if defined(CONFIG_X86_64) && defined(CONFIG_SMP)
	unsigned long *reserved;

	/* x86 setup reserves this arena in either first-chunk allocator. A
	 * non-NULL boot-fixed reserved chunk forces module allocations to use
	 * it, even when full. Inspect only the pointer, never private chunk
	 * layout or live allocation maps. Missing capability must not make a
	 * translator assume all module per-CPU addresses have been checked. */
	BUILD_BUG_ON(PERCPU_MODULE_RESERVE != KD_JIT_PERCPU_MODULE_BYTES);
	BUILD_BUG_ON(PCPU_MIN_ALLOC_SIZE != KD_JIT_PERCPU_ALIGNMENT);
	reserved = (unsigned long *)kallsyms_lookup_name("pcpu_reserved_chunk");
	if (reserved && READ_ONCE(*reserved)) {
		caps.features |= KD_JIT_CAP_PERCPU_MODULE;
		caps.percpu_module_bytes = PERCPU_MODULE_RESERVE;
	}
#endif
	return caps;
}

static long kd_dev_ioctl(struct file *file, unsigned int command,
			 unsigned long arg)
{
	struct kd_jit_caps caps;
	struct kd_source_range range;
	struct kd_source_info info;
	int ret;

	switch (command) {
	case KD_JIT_CAPS:
		/* The open description pins this provider. Report immutable build
		 * semantics even while draining; this query opens no admission,
		 * reserves no resource and changes no existing packet layout. */
		caps = kd_jit_capabilities();
		return copy_to_user((void __user *)arg, &caps, sizeof(caps)) ?
			       -EFAULT :
			       0;
	case KD_SOURCE_INFO:
		kd_source_info(&info);
		return copy_to_user((void __user *)arg, &info, sizeof(info)) ?
			       -EFAULT :
			       0;
	case KD_SOURCE_PIN:
		if (!file->private_data)
			return -EBADF;
		if (copy_from_user(&range, (void __user *)arg, sizeof(range)))
			return -EFAULT;
		return kd_source_pin_range(range.address, range.size);
	case KD_SOURCE_RETIRE:
		if (!capable(CAP_SYS_MODULE))
			return -EPERM;
		if (kd_mutex_lock_interruptible(&kd_publish_lock))
			return -ERESTARTSYS;
		/* A readonly control FD does not count as its own writer. The caller
		 * must stop new workloads; idle snapshots are not a hook-reader barrier. */
		ret = kd_source_begin_retire();
		if (!ret && (!kd_mutex_check_idle() || !kd_mutex_tasks_idle() ||
			     kd_spin_entries_check_idle()))
			ret = -EBUSY;
		if (!ret) {
			kd_exe_retire_all();
			kd_source_finish_retire();
		}
		kd_source_info(&info);
		pr_info("kd_source retire: result=%d state=%u modules=%u frames=%u writers=%u\n",
			ret, info.state, info.modules, info.frames,
			info.writers);
		kd_mutex_local_unlock(&kd_publish_lock);
		return ret;
	default:
		return -ENOTTY;
	}
}

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

		kd_exe_snapshot(entry, &snapshot);
		if (copy_to_user(buf + len, &snapshot, entry_size))
			return -EFAULT;
		len += entry_size;
	}

	return len;
}

static ssize_t kd_dev_write_locked(struct kd_image_upload *upload,
				   const char __user *buf, size_t count)
{
	struct kd_recv_pkt head;
	struct kd_exe_info *entry;
	const char __user *payload;
	size_t len;
	void *code;
	int ret;

	if (!kd_source_is_open())
		return -ESHUTDOWN;
	if (count < sizeof(head))
		return -EINVAL;
	if (copy_from_user(&head, buf, sizeof(head)))
		return -EFAULT;
	if (head.version != KD_IMAGE_PROTOCOL || head.reserved ||
	    (head.requirements & ~KD_IMAGE_REQUIREMENTS))
		return -EPROTO;

	len = count - sizeof(head);
	payload = buf + sizeof(head);
	entry = kd_get_exe(head.pid, head.RIP);
	if (!entry)
		return -ENOSPC;
	if (READ_ONCE(entry->RIP) != head.RIP ||
	    READ_ONCE(entry->pid) != head.pid ||
	    smp_load_acquire(&entry->status_code) == KD_EXE_UNUSED) {
		KD_PR_ERR("translation entry not found: pid=%d rip=%px\n",
			  head.pid, (void *)head.RIP);
		return -ENOENT;
	}
	if (head.entry_abi != entry->entry_abi ||
	    !kd_entry_abi_valid(entry->lock_kind, head.entry_abi) ||
	    !kd_image_requirements_valid(entry->lock_kind, head.entry_abi,
					head.requirements))
		return -EPROTO;
	if (head.base_generation != READ_ONCE(entry->generation))
		return -ESTALE;
	if (head.status_code == KD_EXE_NATIVE_ONLY) {
		if (len || head.offset || head.image_length || head.requirements || head.upload_id)
			return -EINVAL;
		if (smp_load_acquire(&entry->status_code) !=
		    KD_EXE_NATIVE_ONLY) {
			kd_exe_publish_status(entry, KD_EXE_NATIVE_ONLY);
			KD_PR_INFO("JIT native-only: pid=%d rip=%px\n",
				   head.pid, (void *)head.RIP);
		}
		return count;
	}
	if (!len || !head.upload_id || head.image_length < KD_IMAGE_HEADER_SIZE ||
	    head.image_length > KD_CODE_BLOCK_SIZE || head.offset > head.image_length ||
	    len > head.image_length - head.offset ||
	    (head.status_code != KD_EXE_UNINIT &&
	     head.status_code != KD_EXE_NORMAL) ||
	    ((head.status_code == KD_EXE_NORMAL) != (head.offset + len == head.image_length)))
		return -EINVAL;
	if (smp_load_acquire(&entry->status_code) == KD_EXE_NATIVE_ONLY)
		return -EPERM;
	if (!head.offset) {
		kd_image_discard(upload->image);
		upload->image = NULL;
		upload->covered = 0;
		upload->identity = head;
		if (entry->lock_kind == KD_EXE_LOCK_MUTEX) {
			upload->image = kd_image_alloc();
			if (!upload->image)
				return -ENOSPC;
		}
	} else if (head.pid != upload->identity.pid || head.RIP != upload->identity.RIP ||
		   head.upload_id != upload->identity.upload_id ||
		   head.base_generation != upload->identity.base_generation ||
		   head.image_length != upload->identity.image_length ||
		   head.entry_abi != upload->identity.entry_abi ||
		   head.requirements != upload->identity.requirements)
		return -ESTALE;
	if (head.offset != upload->covered)
		return -EINVAL;
	code = upload->image ? upload->image->code : entry->code_block;
	if (!code)
		return -EINVAL;

	KD_PR_INFO(
		"install JIT chunk: pid=%d rip=%px status=%d offset=%lu bytes=%zu\n",
		head.pid, (void *)head.RIP, head.status_code, head.offset, len);

	if (copy_from_user((char *)code + head.offset, payload,
			   len))
		return -EFAULT;
	upload->covered += len;
	/* Keep the prior miss state recoverable until the full image is present. */
	if (head.status_code == KD_EXE_NORMAL) {
		const unsigned char *bytes = code;
		bool directory = !memcmp(bytes + 9, "KDWB002", 7) &&
		                 !memcmp(bytes + 25, "KDWC002", 7) &&
		                 !memcmp(bytes + 41, "KDAB", 4);

		/* Every uploaded image uses KD's private packet, including FULL
		 * recovery and legacy kernel-bridge entries. Old pt_regs offsets must
		 * never be published NORMAL for this provider's rearranged packet. */
		if (!directory || bytes[45] != entry->entry_abi ||
		    bytes[KD_IMAGE_VERSION_OFFSET] != head.version ||
		    bytes[KD_IMAGE_REQUIREMENTS_OFFSET] != head.requirements) {
			return -EPROTO;
		}
		if (upload->image) {
			upload->image->length = head.image_length;
			upload->image->requirements = head.requirements;
			upload->image->entry_abi = head.entry_abi;
			ret = kd_image_publish(entry, upload->image, head.base_generation);
			if (ret)
				return ret;
			upload->image = NULL;
		} else
			kd_exe_publish_status(entry, KD_EXE_NORMAL);
		upload->covered = 0;
	}
	return count;
}

static ssize_t kd_dev_write(struct file *file, const char __user *buf,
			    size_t count, loff_t *offset)
{
	ssize_t ret;

	(void)offset;
	if (!file->private_data)
		return -EBADF;
	if (kd_mutex_lock_interruptible(&kd_publish_lock))
		return -ERESTARTSYS;
	ret = kd_dev_write_locked(file->private_data, buf, count);
	if (ret < 0) {
		struct kd_image_upload *upload = file->private_data;

		kd_image_discard(upload->image);
		upload->image = NULL;
		upload->covered = 0;
	}
	kd_mutex_local_unlock(&kd_publish_lock);
	return ret;
}

static const struct file_operations kd_dev_fops = {
	.owner = THIS_MODULE,
	.open = kd_dev_open,
	.release = kd_dev_release,
	.unlocked_ioctl = kd_dev_ioctl,
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
