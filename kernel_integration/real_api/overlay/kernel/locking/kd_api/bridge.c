// SPDX-License-Identifier: GPL-2.0
/* Immutable object binding. The registry lock is setup/destruction only;
 * acquisition reads the object's provider and never consults this registry. */
#include <linux/capability.h>
#include <linux/err.h>
#include <linux/file.h>
#include <linux/fdtable.h>
#include <linux/kd_api_provider.h>
#include <linux/module.h>
#include <linux/pipe_fs_i.h>
#include <linux/sched/task.h>

#define KD_API_SELECTORS 32
struct kd_api_selector {
	struct task_struct *task;
	struct file *token; /* fd release clears this borrowed identity before free */
	const struct kd_api_provider *ops;
	u32 files_left, pipes_left;
};
static DEFINE_MUTEX(kd_api_registry_lock);
static const struct kd_api_provider *kd_api_registered;
static struct kd_api_selector kd_api_selectors[KD_API_SELECTORS];
static atomic_long_t kd_api_objects = ATOMIC_LONG_INIT(0);
extern const struct kd_api_site __kd_api_sites_start[], __kd_api_sites_end[];

const struct kd_api_site *kd_api_sites(unsigned int *count)
{
	*count = __kd_api_sites_end - __kd_api_sites_start;
	return __kd_api_sites_start;
}
EXPORT_SYMBOL_GPL(kd_api_sites);

int kd_api_register_provider(const struct kd_api_provider *ops)
{
	int ret = 0;

	static_assert(sizeof(kd_api_spinlock_t) == sizeof(spinlock_t));
	static_assert(sizeof(kd_api_spinlock_t) == 4);
	static_assert(__alignof__(kd_api_spinlock_t) == __alignof__(spinlock_t));
	static_assert(sizeof(kd_api_mutex_t) == sizeof(struct mutex));
	static_assert(sizeof(kd_api_mutex_t) == 32);
	static_assert(__alignof__(kd_api_mutex_t) == __alignof__(struct mutex));
#define KD_API_OFFSET(member, value) static_assert(offsetof(struct kd_api_provider, member) == value)
	KD_API_OFFSET(spin_lock, KD_API_OP_SPIN_LOCK);
	KD_API_OFFSET(spin_unlock, KD_API_OP_SPIN_UNLOCK);
	KD_API_OFFSET(mutex_lock, KD_API_OP_MUTEX_LOCK);
	KD_API_OFFSET(mutex_unlock, KD_API_OP_MUTEX_UNLOCK);
	KD_API_OFFSET(spin_local_lock, KD_API_OP_SPIN_LOCAL_LOCK);
	KD_API_OFFSET(spin_local_unlock, KD_API_OP_SPIN_LOCAL_UNLOCK);
	KD_API_OFFSET(mutex_local_lock, KD_API_OP_MUTEX_LOCAL_LOCK);
	KD_API_OFFSET(mutex_local_unlock, KD_API_OP_MUTEX_LOCAL_UNLOCK);
#undef KD_API_OFFSET
	if (!ops || ops->version != KD_API_VERSION || !ops->owner ||
	    !ops->spin_lock || !ops->spin_unlock || !ops->mutex_lock ||
	    !ops->mutex_unlock || !ops->spin_local_lock || !ops->spin_local_unlock ||
	    !ops->mutex_local_lock || !ops->mutex_local_unlock || !ops->spin_init ||
	    !ops->spin_idle || !ops->mutex_init || !ops->mutex_idle)
		return -EINVAL;
	mutex_lock(&kd_api_registry_lock);
	if (kd_api_registered)
		ret = -EBUSY;
	else
		kd_api_registered = ops;
	mutex_unlock(&kd_api_registry_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(kd_api_register_provider);

void kd_api_unregister_provider(const struct kd_api_provider *ops)
{
	unsigned int i;

	mutex_lock(&kd_api_registry_lock);
	BUG_ON(kd_api_registered != ops || atomic_long_read(&kd_api_objects));
	for (i = 0; i < KD_API_SELECTORS; i++)
		BUG_ON(kd_api_selectors[i].ops);
	/* Every live selector/object owns its own module reference. The count
	 * above is a teardown probe, not permission to drop somebody's reference. */
	kd_api_registered = NULL;
	mutex_unlock(&kd_api_registry_lock);
}
EXPORT_SYMBOL_GPL(kd_api_unregister_provider);

static void kd_api_selector_put(struct kd_api_selector *slot)
{
	const struct kd_api_provider *ops = slot->ops;
	struct task_struct *task = slot->task;

	slot->task = NULL;
	slot->token = NULL;
	slot->ops = NULL;
	slot->files_left = slot->pipes_left = 0;
	put_task_struct(task);
	module_put(ops->owner);
}

int kd_api_select_current(struct file *token, const struct kd_api_provider *ops,
			  const struct kd_api_select *selection)
{
	struct kd_api_selector *free = NULL;
	unsigned int i;
	int ret = 0;

	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;
	if (!token || selection->version != KD_API_VERSION || selection->reserved ||
	    selection->files_budget > 1 || selection->pipes_budget > 1)
		return -EINVAL;
	mutex_lock(&kd_api_registry_lock);
	if (ops != kd_api_registered) {
		ret = -ENODEV;
		goto out;
	}
	for (i = 0; i < KD_API_SELECTORS; i++) {
		struct kd_api_selector *slot = &kd_api_selectors[i];
		if (slot->task == current || slot->token == token) {
			ret = -EBUSY;
			goto out;
		}
		if (!slot->task && !free)
			free = slot;
	}
	/* Native setup validates the absence of another selector. It neither
	 * changes a live object nor consumes a provider reference. */
	if (!selection->files_budget && !selection->pipes_budget)
		goto out;
	if (!free) {
		ret = -ENOSPC;
		goto out;
	}
	if (!try_module_get(ops->owner)) {
		ret = -ENODEV;
		goto out;
	}
	get_task_struct(current);
	*free = (struct kd_api_selector) {
		.task = current, .token = token, .ops = ops,
		.files_left = selection->files_budget,
		.pipes_left = selection->pipes_budget,
	};
out:
	mutex_unlock(&kd_api_registry_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(kd_api_select_current);

void kd_api_cancel_selector(struct file *token)
{
	unsigned int i;

	mutex_lock(&kd_api_registry_lock);
	for (i = 0; i < KD_API_SELECTORS; i++)
		if (kd_api_selectors[i].token == token)
			kd_api_selector_put(&kd_api_selectors[i]);
	mutex_unlock(&kd_api_registry_lock);
}
EXPORT_SYMBOL_GPL(kd_api_cancel_selector);

/* A consumed budget names one binding attempt. Later unpublished allocation
 * failure drops its object reference; it does not silently re-arm a selector. */
static const struct kd_api_provider *kd_api_bind(bool pipe)
{
	const struct kd_api_provider *ops = NULL;
	unsigned int i;

	mutex_lock(&kd_api_registry_lock);
	for (i = 0; i < KD_API_SELECTORS; i++) {
		struct kd_api_selector *slot = &kd_api_selectors[i];
		u32 *left = pipe ? &slot->pipes_left : &slot->files_left;
		if (slot->task != current || !*left)
			continue;
		ops = slot->ops;
		BUG_ON(ops != kd_api_registered);
		if (!try_module_get(ops->owner)) {
			ops = ERR_PTR(-ENODEV);
			break;
		}
		--*left;
		atomic_long_inc(&kd_api_objects);
		if (!slot->files_left && !slot->pipes_left)
			kd_api_selector_put(slot);
		break;
	}
	mutex_unlock(&kd_api_registry_lock);
	return ops;
}

int kd_api_files_init(struct files_struct *files)
{
	const struct kd_api_provider *ops = kd_api_bind(false);
	if (IS_ERR(ops))
		return PTR_ERR(ops);
	files->kd_lock_provider = ops;
	if (ops)
		ops->spin_init(&files->file_lock.kd);
	else
		spin_lock_init(&files->file_lock.native);
	return 0;
}

void kd_api_files_destroy(struct files_struct *files)
{
	const struct kd_api_provider *ops = files->kd_lock_provider;
	if (ops) {
		BUG_ON(!ops->spin_idle(&files->file_lock.kd));
		atomic_long_dec(&kd_api_objects);
		module_put(ops->owner);
	}
}

int kd_api_pipe_init(struct pipe_inode_info *pipe)
{
	const struct kd_api_provider *ops = kd_api_bind(true);
	if (IS_ERR(ops))
		return PTR_ERR(ops);
	pipe->kd_lock_provider = ops;
	if (ops)
		(ops->mutex_init)(&pipe->mutex.kd);
	else
		mutex_init(&pipe->mutex.native);
	return 0;
}

void kd_api_pipe_destroy(struct pipe_inode_info *pipe)
{
	const struct kd_api_provider *ops = pipe->kd_lock_provider;
	if (ops) {
		BUG_ON(!ops->mutex_idle(&pipe->mutex.kd));
		atomic_long_dec(&kd_api_objects);
		module_put(ops->owner);
	}
}

/* Each object retains its provider through the full native lifetime. These
 * local paths never switch protocol based on current, source or heat. */
void kd_api_files_lock(kd_api_spinlock_t *lock)
{
	const struct kd_api_provider *ops = container_of(lock, struct files_struct, file_lock)->kd_lock_provider;
	if (ops) ops->spin_local_lock(&lock->kd);
	else spin_lock(&lock->native);
}
void kd_api_files_unlock(kd_api_spinlock_t *lock)
{
	const struct kd_api_provider *ops = container_of(lock, struct files_struct, file_lock)->kd_lock_provider;
	if (ops) ops->spin_local_unlock(&lock->kd);
	else spin_unlock(&lock->native);
}
void kd_api_pipe_lock(kd_api_mutex_t *lock)
{
	const struct kd_api_provider *ops = container_of(lock, struct pipe_inode_info, mutex)->kd_lock_provider;
	if (ops) ops->mutex_local_lock(&lock->kd);
	else mutex_lock(&lock->native);
}
void kd_api_pipe_unlock(kd_api_mutex_t *lock)
{
	const struct kd_api_provider *ops = container_of(lock, struct pipe_inode_info, mutex)->kd_lock_provider;
	if (ops) ops->mutex_local_unlock(&lock->kd);
	else mutex_unlock(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_api_files_lock);
EXPORT_SYMBOL_GPL(kd_api_files_unlock);
EXPORT_SYMBOL_GPL(kd_api_pipe_lock);
EXPORT_SYMBOL_GPL(kd_api_pipe_unlock);

int kd_api_query_current(struct kd_api_query *query)
{
	struct file *file = NULL;
	const struct kd_api_provider *ops;
	const struct kd_api_site *site;
	unsigned int i, count;

	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;
	if (query->version != KD_API_VERSION || query->fd < -1)
		return -EINVAL;
	if (query->fd == -1) {
		struct files_struct *files = current->files;
		query->kind = KD_API_KIND_FILES;
		query->object = (unsigned long)files;
		query->lock = (unsigned long)&files->file_lock;
		ops = files->kd_lock_provider;
	} else {
		struct pipe_inode_info *pipe;
		file = fget(query->fd);
		if (!file)
			return -EBADF;
		pipe = get_pipe_info(file, false);
		if (!pipe) {
			fput(file);
			return -EINVAL;
		}
		query->kind = KD_API_KIND_PIPE;
		query->object = (unsigned long)pipe;
		query->lock = (unsigned long)&pipe->mutex;
		ops = pipe->kd_lock_provider;
	}
	query->backend = ops ? KD_API_BACKEND_KD : KD_API_BACKEND_NATIVE;
	query->provider = (unsigned long)ops;
	for (i = 0; i < KD_API_SITE_COUNT; i++)
		query->entries[i] = 0;
	site = kd_api_sites(&count);
	for (i = 0; i < count; i++) {
		BUG_ON(!site[i].site || site[i].site > KD_API_SITE_COUNT || site[i].reserved);
		BUG_ON(query->entries[site[i].site - 1]);
		query->entries[site[i].site - 1] = site[i].entry;
	}
	if (file)
		fput(file);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_api_query_current);
