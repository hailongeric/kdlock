// SPDX-License-Identifier: GPL-2.0-only
/* Metadata-only opt-in binding for actual userspace mmap/munmap checks. */
#include <linux/atomic.h>
#include <linux/capability.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/limits.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/overflow.h>
#include <linux/sched.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/tracepoint.h>
#include <linux/uaccess.h>

#include "include/kd_linux_rwsem.h"
#include "kernel/observation.h"
#include "kernel/rw_native.h"
#include "../abi.h"

#ifndef CONFIG_KDLOCK_REBUILD
#error "The selected rebuilt Linux rwsem API is required"
#endif
#ifdef CONFIG_KDLOCK_MMAP
#error "The independent historical MM backend is outside this provider"
#endif

enum observed_count {
	COUNT_READ_ACQUIRE, COUNT_READ_RELEASE, COUNT_WRITE_ACQUIRE,
	COUNT_WRITE_RELEASE, COUNT_DOWNGRADE, COUNT_CANCEL, COUNT_TRY_MISS,
	COUNT_ENQUEUE, COUNT_SELECT_LOCAL, COUNT_PHYSICAL_BEGIN, COUNT_PHYSICAL_END,
	COUNT_EVENTS, COUNT_TOTAL,
};

struct selected_mm {
	struct kd_rwsem gate;
	struct kd_rw_native_pool pool;
	struct kd_rw_native_record *records;
	struct kd_linux_rwsem_binding binding;
	struct mm_struct *mm;
	struct task_struct *owner;
	pid_t owner_pid, owner_tgid;
	size_t record_bytes;
	atomic64_t counts[COUNT_TOTAL];
	atomic_t count_overflow;
};

static DEFINE_MUTEX(control_mutex);
static bool control_opened;
static struct selected_mm *selection;
static struct kd_mmap_api_status saved_status;

static void increment(struct selected_mm *selected, enum observed_count count)
{
	if (!atomic64_add_unless(&selected->counts[count], 1, S64_MAX))
		atomic_set(&selected->count_overflow, 1);
}

static void observe(void *context, const struct kd_observation *event)
{
	struct selected_mm *selected = context;
	enum observed_count count;

	if (event->object != (unsigned long)&selected->gate.core.queue)
		return;
	switch (event->kind) {
	case KD_OBS_NATIVE_READ_ACQUIRE: count = COUNT_READ_ACQUIRE; break;
	case KD_OBS_NATIVE_READ_RELEASE: count = COUNT_READ_RELEASE; break;
	case KD_OBS_NATIVE_WRITE_ACQUIRE: count = COUNT_WRITE_ACQUIRE; break;
	case KD_OBS_NATIVE_WRITE_RELEASE: count = COUNT_WRITE_RELEASE; break;
	case KD_OBS_NATIVE_DOWNGRADE: count = COUNT_DOWNGRADE; break;
	case KD_OBS_NATIVE_CANCEL: count = COUNT_CANCEL; break;
	case KD_OBS_NATIVE_TRY_MISS: count = COUNT_TRY_MISS; break;
	case KD_OBS_ENQUEUE: count = COUNT_ENQUEUE; break;
	case KD_OBS_SELECT_LOCAL: count = COUNT_SELECT_LOCAL; break;
	case KD_OBS_PHYSICAL_BEGIN: count = COUNT_PHYSICAL_BEGIN; break;
	case KD_OBS_PHYSICAL_END: count = COUNT_PHYSICAL_END; break;
	default: return;
	}
	/* Only immutable scalar event data is read. This probe neither sleeps nor
	 * takes a source right, traverses a node or changes a lock operation.
	 */
	increment(selected, count);
	increment(selected, COUNT_EVENTS);
}

static void snapshot(struct selected_mm *selected, struct kd_mmap_api_status *status)
{
	*status = (struct kd_mmap_api_status) {
		.state = KD_MMAP_API_SELECTED, .cleanup_required = 1,
		.native_capacity = selected->pool.capacity, .record_bytes = selected->record_bytes,
		.owner_pid = selected->owner_pid, .owner_tgid = selected->owner_tgid,
		.owner_is_current = selected->owner == current && selected->mm == current->mm,
		.owner_threads = selected->owner == current ? get_nr_threads(current) : 0,
		.mm_identity = (unsigned long)selected->mm,
		.object_identity = (unsigned long)&selected->mm->mmap_lock,
		.gate_identity = (unsigned long)&selected->gate.core.queue,
		.source_calls = selected->binding.source_calls,
		.pool_idle = kd_rw_native_pool_idle(&selected->pool),
		.gate_locked = kd_linux_rwsem_is_locked(&selected->binding),
		.gate_write_locked = kd_linux_rwsem_is_write_locked(&selected->binding),
		.gate_contended = kd_linux_rwsem_is_contended(&selected->binding),
		.native_read_acquires = atomic64_read(&selected->counts[COUNT_READ_ACQUIRE]),
		.native_read_releases = atomic64_read(&selected->counts[COUNT_READ_RELEASE]),
		.native_write_acquires = atomic64_read(&selected->counts[COUNT_WRITE_ACQUIRE]),
		.native_write_releases = atomic64_read(&selected->counts[COUNT_WRITE_RELEASE]),
		.native_downgrades = atomic64_read(&selected->counts[COUNT_DOWNGRADE]),
		.native_cancels = atomic64_read(&selected->counts[COUNT_CANCEL]),
		.native_try_misses = atomic64_read(&selected->counts[COUNT_TRY_MISS]),
		.queue_enqueues = atomic64_read(&selected->counts[COUNT_ENQUEUE]),
		.local_selections = atomic64_read(&selected->counts[COUNT_SELECT_LOCAL]),
		.physical_begins = atomic64_read(&selected->counts[COUNT_PHYSICAL_BEGIN]),
		.physical_ends = atomic64_read(&selected->counts[COUNT_PHYSICAL_END]),
		/* JIT_ENTER has no object identity for this per-gate listener. The
		 * native-only selection follows source_calls=false, not a zero count.
		 */
		.jit_entries = 0, .jit_observation_available = 0,
		.observed_events = atomic64_read(&selected->counts[COUNT_EVENTS]),
		.count_overflow = atomic_read(&selected->count_overflow),
	};
}

static int start_selection(const struct kd_mmap_api_request *request)
{
	struct selected_mm *selected;
	size_t bytes;
	unsigned int index;
	int result;

	if (selection || saved_status.state != KD_MMAP_API_IDLE)
		return -EALREADY;
	if (!current->mm || current != current->group_leader || get_nr_threads(current) != 1)
		return -EPERM;
	if (!request->native_capacity || request->native_capacity > UINT_MAX ||
	    request->contract_flags != KD_MMAP_API_QUIESCENT_CHANGE)
		return -EINVAL;
	if (check_mul_overflow((size_t)request->native_capacity,
			       sizeof(*selected->records), &bytes))
		return -EOVERFLOW;
	selected = kzalloc(sizeof(*selected), GFP_KERNEL);
	if (!selected)
		return -ENOMEM;
	selected->records = kvcalloc(request->native_capacity, sizeof(*selected->records), GFP_KERNEL);
	if (!selected->records) {
		kfree(selected);
		return -ENOMEM;
	}
	selected->record_bytes = bytes;
	kd_rwsem_init(&selected->gate);
	result = kd_rw_native_pool_init(&selected->gate.core, &selected->pool,
					selected->records, request->native_capacity);
	if (result)
		goto free_private;
	for (index = 0; index < COUNT_TOTAL; ++index)
		atomic64_set(&selected->counts[index], 0);
	atomic_set(&selected->count_overflow, 0);
	selected->mm = current->mm;
	selected->owner = current;
	selected->owner_pid = task_pid_nr(current);
	selected->owner_tgid = task_tgid_nr(current);
	/* mmgrab retains the containing mm/lock allocation, not mm_users. Later
	 * exit_mmap operations may still use this live gate until explicit END.
	 */
	mmgrab(selected->mm);
	get_task_struct(selected->owner);
	if (!try_module_get(THIS_MODULE)) {
		result = -ENODEV;
		goto drop_identity;
	}
	result = register_trace_kdlock_observe_tp(observe, selected);
	if (result)
		goto drop_self;
	/* Caller has already excluded ALL native/KD entry and observers. The
	 * thread count and bind consistency checks cannot establish that contract.
	 */
	result = kd_linux_rwsem_bind(&selected->mm->mmap_lock, &selected->binding,
				     &selected->gate, false);
	if (result) {
		unregister_trace_kdlock_observe_tp(observe, selected);
		tracepoint_synchronize_unregister();
		goto drop_self;
	}
	selection = selected;
	snapshot(selected, &saved_status);
	return 0;

drop_self:
	/* The executing fd's fops.owner independently retains this return path. */
	module_put(THIS_MODULE);
drop_identity:
	put_task_struct(selected->owner);
	mmdrop(selected->mm);
free_private:
	kvfree(selected->records);
	kfree(selected);
	return result;
}

static int end_selection(const struct kd_mmap_api_request *request)
{
	struct selected_mm *selected = selection;
	int result;

	if (!selected)
		return -ENODEV;
	if (current != selected->owner || current->mm != selected->mm)
		return -EPERM;
	if (get_nr_threads(current) != 1)
		return -EBUSY;
	if (request->native_capacity || request->contract_flags != KD_MMAP_API_QUIESCENT_CHANGE)
		return -EINVAL;
	/* Workers have joined and caller excludes entry/observers across unbind.
	 * These exact metadata predicates are necessary but do not prove quiescence.
	 */
	if (!kd_rw_native_pool_idle(&selected->pool) ||
	    kd_linux_rwsem_is_locked(&selected->binding) ||
	    kd_linux_rwsem_is_contended(&selected->binding))
		return -EBUSY;
	result = kd_linux_rwsem_unbind(&selected->binding);
	if (result)
		return result;
	unregister_trace_kdlock_observe_tp(observe, selected);
	tracepoint_synchronize_unregister();
	snapshot(selected, &saved_status);
	saved_status.state = KD_MMAP_API_RETIRED;
	saved_status.cleanup_required = 0;
	selection = NULL;
	put_task_struct(selected->owner);
	mmdrop(selected->mm);
	kvfree(selected->records);
	kfree(selected);
	/* The still-open control fd retains module entry/return code independently. */
	module_put(THIS_MODULE);
	return 0;
}

static long control_ioctl(struct file *file, unsigned int command, unsigned long argument)
{
	struct kd_mmap_api_request request, reply = { .abi = KD_MMAP_API_ABI };
	int result;

	(void)file;
	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;
	if (command != KD_MMAP_API_START && command != KD_MMAP_API_QUERY && command != KD_MMAP_API_END)
		return -ENOTTY;
	if (copy_from_user(&request, (void __user *)argument, sizeof(request)))
		return -EFAULT;
	if (request.abi != KD_MMAP_API_ABI || request.reserved)
		return -EINVAL;
	mutex_lock(&control_mutex);
	if (command == KD_MMAP_API_START)
		result = start_selection(&request);
	else if (command == KD_MMAP_API_END)
		result = end_selection(&request);
	else
		result = request.native_capacity || request.contract_flags ? -EINVAL : 0;
	if (selection)
		snapshot(selection, &saved_status);
	reply.status = saved_status;
	mutex_unlock(&control_mutex);
	if (copy_to_user((void __user *)argument, &reply, sizeof(reply)))
		return -EFAULT;
	return result;
}

static int control_open(struct inode *inode, struct file *file)
{
	int result = 0;
	(void)inode;
	(void)file;
	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;
	mutex_lock(&control_mutex);
	if (control_opened)
		result = -EBUSY;
	else
		control_opened = true;
	mutex_unlock(&control_mutex);
	return result;
}

static int control_release(struct inode *inode, struct file *file)
{
	(void)inode;
	(void)file;
	mutex_lock(&control_mutex);
	/* A close/owner exit supplies no whole-mm quiescence proof. An active
	 * selection and its self/module/mm/task/pool holds remain for explicit END.
	 */
	control_opened = false;
	mutex_unlock(&control_mutex);
	return 0;
}

static const struct file_operations operations = {
	.owner = THIS_MODULE, .open = control_open, .release = control_release,
	.unlocked_ioctl = control_ioctl,
};

static struct miscdevice control_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_api", .mode = 0600,
	.fops = &operations,
};

static int __init provider_init(void)
{
	return misc_register(&control_device);
}

static void __exit provider_exit(void)
{
	/* The independent selection hold prevents ordinary unload while bound. */
	BUG_ON(selection);
	misc_deregister(&control_device);
}

module_init(provider_init);
module_exit(provider_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Native-local mmap lock binding for actual syscall checks");
