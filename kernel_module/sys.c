/* /dev/kd_dev is the daemon's registry/image channel and source-control API.
 * Writable opens retain one translation-session writer; readonly status/CAPS
 * opens do not. Retirement closes admission before releasing source pins.
 * Mutex uploads and ABI1 guard/string-service uploads stage immutable versions.
 * Other spin/rwlock entries stay in place until their first such transition. */
#include <linux/build_bug.h>
#include <linux/cdev.h>
#include <linux/capability.h>
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/kallsyms.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/percpu.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/types.h>
#include <linux/uaccess.h>
#include <linux/version.h>

#include "exe.h"
#include "kd_api_provider.h"
#include "kd_lock.h"
#include "kd_learning_api.h"
#include "kd_mutex.h"
#include "kd_source.h"
#include "kd_service_calls.h"
#include "kd_spin_entry.h"
#include "sys.h"
#include "utils.h"

static dev_t kd_devno;
static struct cdev kd_cdev;
static struct class *kd_class;
/* Serializes uploads with rejection, not execution of already published code. */
static DEFINE_KD_MUTEX(kd_publish_lock);
/* Tokens are unique across writable descriptions in this provider lifetime.
 * The existing publication mutex serializes allocation and every view change. */
static unsigned long long kd_learning_next_token;

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
	kd_api_provider_release(file);
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
			KD_JIT_CAP_MUTEX_EXCLUSIVE | KD_JIT_CAP_NATIVE_ESCAPE |
			KD_JIT_CAP_ADDRESS_GUARD | KD_JIT_CAP_STRING_SERVICES |
			KD_JIT_CAP_STRING_WRITE | KD_JIT_CAP_AUDITED_STRINGS |
			KD_JIT_CAP_ROOT_NATIVE_ESCAPE | KD_JIT_CAP_INDIRECT_CALL |
			KD_JIT_CAP_ORIGIN_INSTRUCTION | KD_JIT_CAP_ORIGIN_CALL |
			KD_JIT_CAP_ORIGIN_MEMORY | KD_JIT_CAP_ORIGIN_CONTEXT_READ |
			KD_JIT_CAP_INDIRECT_TAIL | KD_JIT_CAP_SOURCE_FRONTIER |
			KD_JIT_CAP_LEARNING_BATCH,
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
	if (kd_image_direct_available())
		caps.features |= KD_JIT_CAP_DIRECT_STRINGS;
	return caps;
}

static bool kd_learning_reserved_zero(const __u64 *words, unsigned int count)
{
	unsigned int i;

	for (i = 0; i < count; ++i)
		if (words[i])
			return false;
	return true;
}

static bool kd_learning_root_equal(const struct kd_learning_root *left,
				  const struct kd_learning_root *right)
{
	return left->slot == right->slot && left->pid == right->pid &&
		left->rip == right->rip && left->lock_kind == right->lock_kind &&
		left->entry_abi == right->entry_abi;
}

static struct kd_exe_info *kd_learning_find_root(const struct kd_learning_root *root)
{
	struct kd_exe_info *entry;

	if (root->pid < 0 || !root->rip || root->lock_kind != KD_EXE_LOCK_MUTEX ||
	    root->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1)
		return NULL;
	entry = root->slot == KD_LEARNING_SLOT_LOOKUP ?
		kd_get_exe(root->pid, root->rip) :
		(struct kd_exe_info *)kd_exe_get_slot(root->slot);
	if (!entry || smp_load_acquire(&entry->status_code) == KD_EXE_UNUSED ||
	    READ_ONCE(entry->pid) != root->pid || READ_ONCE(entry->RIP) != root->rip ||
	    READ_ONCE(entry->lock_kind) != root->lock_kind ||
	    READ_ONCE(entry->entry_abi) != root->entry_abi)
		return NULL;
	return entry;
}

static void kd_learning_clear_view(struct kd_image_upload *upload)
{
	upload->learning_view_valid = 0;
	upload->learning_bound = 0;
	upload->learning_upload_id = 0;
	upload->learning_receipt.valid = 0;
}

static bool kd_learning_upload_matches(const struct kd_image_upload *upload,
				      const struct kd_recv_pkt *head)
{
	const struct kd_learning_snapshot *view = &upload->learning_snapshot;

	return upload->learning_view_valid && upload->learning_bound &&
		upload->learning_receipt.valid && upload->learning_receipt.batch &&
		upload->learning_receipt.generation == view->base_generation &&
		upload->learning_receipt.revision == view->revision &&
		head->pid == view->root.pid && head->RIP == view->root.rip &&
		head->entry_abi == view->root.entry_abi &&
		head->base_generation == view->base_generation &&
		head->upload_id == upload->learning_upload_id;
}

static long kd_learning_snapshot_locked(struct kd_image_upload *upload,
					void __user *argument)
{
	struct kd_learning_snapshot *request = &upload->learning_request;
	struct kd_learning_snapshot *view = &upload->learning_snapshot;
	struct kd_image_learning_receipt receipt;
	struct kd_exe_info snapshot, *entry;
	unsigned long long overflow;
	unsigned int count;

	/* Only the request header is input. The record array is output from the
	 * coherent ledger snapshot, never a userspace-supplied learning history. */
	if (copy_from_user(request, argument, KD_LEARNING_SNAPSHOT_HEADER_SIZE))
		return -EFAULT;
	if (request->version != KD_LEARNING_API_VERSION ||
	    request->header_size != KD_LEARNING_SNAPSHOT_HEADER_SIZE ||
	    request->record_size != KD_LEARNING_RECORD_SIZE ||
	    request->capacity != KD_LEARNING_CAPACITY ||
	    !kd_learning_reserved_zero(request->reserved, ARRAY_SIZE(request->reserved)))
		return -EPROTO;
	if (upload->learning_view_valid) {
		if (!request->token)
			return -EBUSY;
		if (request->token != view->token ||
		    !kd_learning_root_equal(&request->root, &view->root) ||
		    request->base_generation != view->base_generation ||
		    request->revision != view->revision)
			return -ESTALE;
		return copy_to_user(argument, view, sizeof(*view)) ? -EFAULT : 0;
	}
	if (request->token)
		return -ESTALE;
	if (request->revision || request->count || request->flags || request->overflow_report_events)
		return -EINVAL;
	if (upload->covered || upload->image)
		return -EBUSY;
	if (!kd_source_is_open())
		return -ESHUTDOWN;
	entry = kd_learning_find_root(&request->root);
	if (!entry)
		return -ENOENT;
	if (kd_learning_next_token == ~0ULL)
		return -EOVERFLOW;
	/* Only this bounded metadata view is initialized. Pending ledger rows and
	 * packet/frame storage retain their own exact lifetimes and contents. */
	memset(view, 0, sizeof(*view));
	kd_exe_snapshot_misses(entry, &snapshot, view->records, &count, &overflow, &receipt);
	if (snapshot.status_code == KD_EXE_NATIVE_ONLY)
		return -ESHUTDOWN;
	if (snapshot.generation != request->base_generation)
		return -ESTALE;
	if (!receipt.valid || !receipt.batch || receipt.generation != snapshot.generation ||
	    count > KD_LEARNING_CAPACITY)
		return -EPROTO;
	view->version = KD_LEARNING_API_VERSION;
	view->header_size = KD_LEARNING_SNAPSHOT_HEADER_SIZE;
	view->record_size = KD_LEARNING_RECORD_SIZE;
	view->capacity = KD_LEARNING_CAPACITY;
	view->root = request->root;
	view->root.slot = kd_exe_slot_index(entry);
	view->base_generation = snapshot.generation;
	view->revision = receipt.revision;
	view->token = ++kd_learning_next_token;
	view->overflow_report_events = overflow;
	view->count = count;
	view->flags = overflow ? KD_LEARNING_OVERFLOW : 0;
	upload->learning_receipt = receipt;
	if (copy_to_user(argument, view, sizeof(*view))) {
		kd_learning_clear_view(upload);
		return -EFAULT;
	}
	/* A copied view may be bound later; an initial failed copy grants nothing.
	 * Reports after this point cannot change the frozen compiler input. */
	upload->learning_view_valid = 1;
	return 0;
}

static long kd_learning_bind_locked(struct kd_image_upload *upload,
				    void __user *argument)
{
	struct kd_learning_bind request;
	const struct kd_learning_snapshot *view = &upload->learning_snapshot;
	struct kd_exe_info *entry;

	if (copy_from_user(&request, argument, sizeof(request)))
		return -EFAULT;
	if (request.version != KD_LEARNING_API_VERSION || request.size != sizeof(request) ||
	    !kd_learning_reserved_zero(request.reserved, ARRAY_SIZE(request.reserved)))
		return -EPROTO;
	if (!request.token || !request.upload_id || !upload->learning_view_valid ||
	    !upload->learning_receipt.valid || !upload->learning_receipt.batch ||
	    upload->learning_receipt.generation != view->base_generation ||
	    upload->learning_receipt.revision != view->revision ||
	    request.token != view->token ||
	    !kd_learning_root_equal(&request.root, &view->root) ||
	    request.base_generation != view->base_generation || request.revision != view->revision)
		return -ESTALE;
	entry = kd_learning_find_root(&request.root);
	if (!entry || READ_ONCE(entry->generation) != request.base_generation)
		return -ESTALE;
	if (!kd_source_is_open() ||
	    smp_load_acquire(&entry->status_code) == KD_EXE_NATIVE_ONLY)
		return -ESHUTDOWN;
	if (upload->covered || upload->image) {
		/* A userspace read/transport failure can leave part of this view's
		 * private upload staged. Restart only that exact unpublished attempt;
		 * neither the frozen receipt nor pending records are acknowledged. */
		if (!upload->acknowledgment.batch ||
		    !kd_learning_upload_matches(upload, &upload->identity))
			return -EBUSY;
		kd_image_discard(upload->image);
		upload->image = NULL;
		upload->code = NULL;
		upload->covered = 0;
		upload->acknowledgment.valid = 0;
	}
	upload->learning_upload_id = request.upload_id;
	upload->learning_bound = 1;
	return 0;
}

static long kd_learning_cancel_locked(struct kd_image_upload *upload,
				      void __user *argument)
{
	struct kd_learning_cancel request;
	const struct kd_learning_snapshot *view = &upload->learning_snapshot;

	if (copy_from_user(&request, argument, sizeof(request)))
		return -EFAULT;
	if (request.version != KD_LEARNING_API_VERSION || request.size != sizeof(request) ||
	    !kd_learning_reserved_zero(request.reserved, ARRAY_SIZE(request.reserved)))
		return -EPROTO;
	if (!upload->learning_view_valid || !request.token || request.token != view->token ||
	    !kd_learning_root_equal(&request.root, &view->root) ||
	    request.base_generation != view->base_generation)
		return -ESTALE;
	if (upload->acknowledgment.batch &&
	    kd_learning_upload_matches(upload, &upload->identity)) {
		kd_image_discard(upload->image);
		upload->image = NULL;
		upload->code = NULL;
		upload->covered = 0;
		upload->acknowledgment.valid = 0;
	}
	/* Releasing a userspace snapshot is not publication or learning progress. */
	kd_learning_clear_view(upload);
	return 0;
}

static long kd_learning_ioctl(struct file *file, unsigned int command,
			      unsigned long argument)
{
	struct kd_image_upload *upload = file->private_data;
	long ret;

	if (!upload)
		return -EBADF;
	if (kd_mutex_lock_interruptible(&kd_publish_lock))
		return -ERESTARTSYS;
	if (command == KD_LEARNING_SNAPSHOT)
		ret = kd_learning_snapshot_locked(upload, (void __user *)argument);
	else if (command == KD_LEARNING_BIND)
		ret = kd_learning_bind_locked(upload, (void __user *)argument);
	else
		ret = kd_learning_cancel_locked(upload, (void __user *)argument);
	kd_mutex_local_unlock(&kd_publish_lock);
	return ret;
}

static long kd_dev_ioctl(struct file *file, unsigned int command,
			 unsigned long arg)
{
	struct kd_jit_caps caps;
	struct kd_source_range range;
	struct kd_source_info info;
	int ret;

	switch (command) {
	case KD_LEARNING_SNAPSHOT:
	case KD_LEARNING_BIND:
	case KD_LEARNING_CANCEL:
		return kd_learning_ioctl(file, command, arg);
	case KD_API_SELECT:
	case KD_API_CANCEL:
	case KD_API_QUERY:
		return kd_api_provider_ioctl(file, command, arg);
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
	struct kd_image_upload *upload = file ? file->private_data : NULL;
	bool recorded[KD_MAX_EXE] = { false };
	size_t len = 0;
	unsigned int i;
	ssize_t result;

	(void)offset;
	/* dup/fork share these receipts and uploads. Serialize their reads with
	 * chunk writes, without holding the publication spin gate across a copy. */
	if (upload && kd_mutex_lock_interruptible(&kd_publish_lock))
		return -ERESTARTSYS;
	for (i = 0; i < KD_MAX_EXE; i++) {
		const struct kd_exe_info *entry = kd_exe_get_slot(i);
		struct kd_exe_info snapshot;
		struct kd_image_learning_receipt receipt;
		int status;

		if (!entry) {
			result = len ? (ssize_t)len : -ENODEV;
			goto out;
		}
		status = smp_load_acquire(&entry->status_code);
		if (status == KD_EXE_UNUSED)
			continue;
		if (entry_size > count - len)
			break;

		kd_exe_snapshot_learning(entry, &snapshot, &receipt);
		if (copy_to_user(buf + len, &snapshot, entry_size)) {
			result = -EFAULT;
			goto out;
		}
		/* Keep the first successful read at this generation, even when it
		 * observed no report. A later read cannot change the compiler's
		 * possible input. This conservative case may need another compile. */
		if (upload && (!upload->observed[i].valid ||
			       upload->observed[i].generation != receipt.generation)) {
			upload->observed[i] = receipt;
			recorded[i] = true;
		}
		len += entry_size;
	}
	result = len;
out:
	if (upload && result < 0)
		for (i = 0; i < KD_MAX_EXE; ++i)
			if (recorded[i])
				upload->observed[i].valid = 0;
	if (upload)
		kd_mutex_local_unlock(&kd_publish_lock);
	return result;
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
	if (!kd_image_protocol_valid(head.version, head.requirements) || head.reserved ||
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
	if (!len || !head.upload_id ||
	    head.image_length < (head.version == KD_IMAGE_PROTOCOL_SERVICE_QUEUE ?
		KD_IMAGE_SERVICE_HEADER_SIZE : KD_IMAGE_HEADER_SIZE) ||
	    head.image_length > KD_CODE_BLOCK_SIZE || head.offset > head.image_length ||
	    len > head.image_length - head.offset ||
	    (head.status_code != KD_EXE_UNINIT &&
	     head.status_code != KD_EXE_NORMAL) ||
	    ((head.status_code == KD_EXE_NORMAL) != (head.offset + len == head.image_length)))
		return -EINVAL;
	if (smp_load_acquire(&entry->status_code) == KD_EXE_NATIVE_ONLY)
		return -EPERM;
	if (!head.offset) {
		/* Legacy writers retain their exact single-tuple receipts. A writer
		 * with a frozen batch must bind that view before starting its upload. */
		if ((upload->learning_view_valid || upload->learning_bound) &&
		    !kd_learning_upload_matches(upload, &head))
			return -ESTALE;
		kd_image_discard(upload->image);
		upload->image = NULL;
		upload->covered = 0;
		upload->identity = head;
		upload->acknowledgment = upload->learning_bound ? upload->learning_receipt :
			upload->observed[kd_exe_slot_index(entry)];
		upload->code = entry->code_block;
		if (entry->lock_kind == KD_EXE_LOCK_MUTEX || head.requirements ||
		    (kd_image_current(entry) && kd_image_current(entry)->immutable)) {
			upload->image = head.requirements & KD_IMAGE_REQUIRE_DIRECT_STRINGS ?
				kd_image_alloc_direct() : kd_image_alloc();
			if (!upload->image)
				return -ENOSPC;
		}
	} else if (head.pid != upload->identity.pid || head.RIP != upload->identity.RIP ||
		   head.version != upload->identity.version ||
		   head.upload_id != upload->identity.upload_id ||
		   head.base_generation != upload->identity.base_generation ||
		   head.image_length != upload->identity.image_length ||
		   head.entry_abi != upload->identity.entry_abi ||
		   head.requirements != upload->identity.requirements)
		return -ESTALE;
	if (head.offset != upload->covered)
		return -EINVAL;
	code = upload->image ? upload->image->code : upload->code;
	if (!code)
		return -EINVAL;
	if (!upload->image &&
	    (entry->code_block != code || !kd_image_current(entry) ||
	     kd_image_current(entry)->immutable))
		return -ESTALE;

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
		unsigned int requirements;
		bool directory = !memcmp(bytes + 9, "KDWB002", 7) &&
		                 !memcmp(bytes + 25, "KDWC002", 7) &&
		                 !memcmp(bytes + 41, "KDAB", 4);

		/* Every uploaded image uses KD's private packet, including FULL
		 * recovery and legacy kernel-bridge entries. Old pt_regs offsets must
		 * never be published NORMAL for this provider's rearranged packet. */
		if (!directory || bytes[45] != entry->entry_abi ||
		    bytes[KD_IMAGE_VERSION_OFFSET] != head.version ||
		    !kd_image_header_requirements(bytes, head.image_length, &requirements) ||
		    requirements != head.requirements) {
			return -EPROTO;
		}
		if (upload->image) {
			upload->image->length = head.image_length;
			upload->image->requirements = head.requirements;
			upload->image->entry_abi = head.entry_abi;
			ret = kd_image_validate_address_guards(upload->image);
			if (ret)
				return ret;
			ret = kd_image_validate_origin_sites(upload->image);
			if (ret)
				return ret;
			ret = kd_image_validate_memory_sites(upload->image);
			if (ret)
				return ret;
			ret = kd_image_relocate_direct(upload->image);
			if (ret)
				return ret;
			/* An immutable body may reach a registered helper after its
			 * producer closes. Retain that exact source before publication,
			 * not only when a later transaction tries to call it. */
			if (head.requirements & KD_IMAGE_REQUIRE_ORIGIN_CALL) {
				ret = kd_service_calls_pin();
				if (ret)
					return ret;
			}
			ret = kd_image_publish_learned(entry, upload->image,
				head.base_generation, &upload->acknowledgment);
			if (ret)
				return ret;
			upload->image = NULL;
		} else {
			ret = kd_image_publish_mutable(entry, code, head.image_length);
			if (ret)
				return ret;
		}
		if (upload->acknowledgment.batch)
			kd_learning_clear_view(upload);
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

	BUILD_BUG_ON(sizeof(struct kd_exe_info) != 64);
	BUILD_BUG_ON(sizeof(struct kd_recv_pkt) != 64);
	BUILD_BUG_ON(sizeof(struct kd_learning_root) != 24);
	BUILD_BUG_ON(sizeof(struct kd_learning_record) != KD_LEARNING_RECORD_SIZE);
	BUILD_BUG_ON(offsetof(struct kd_learning_snapshot, records) != KD_LEARNING_SNAPSHOT_HEADER_SIZE);
	BUILD_BUG_ON(sizeof(struct kd_learning_snapshot) != KD_LEARNING_SNAPSHOT_SIZE);
	BUILD_BUG_ON(sizeof(struct kd_learning_bind) != KD_LEARNING_BIND_SIZE);
	BUILD_BUG_ON(sizeof(struct kd_learning_cancel) != KD_LEARNING_CANCEL_SIZE);

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
