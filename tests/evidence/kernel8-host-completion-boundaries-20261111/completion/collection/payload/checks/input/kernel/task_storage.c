// SPDX-License-Identifier: GPL-2.0-only
/* Cold task provisioning and exact final storage release around native source. */
#include <linux/compiler.h>
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/overflow.h>
#include <linux/module.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <linux/workqueue.h>
#include <asm/page.h>

#include "task_storage.h"
#include "task_setup.h"
#include "source_stack.h"

struct kd_task_storage {
	struct kd_task_root_context root;
	struct kd_request_pool pool;
	struct kd_episode_resources resources;
	struct kd_source_stack source;
	struct kd_request_slot *slots;
	struct kd_episode_frame *frames;
	void *auxiliary;
	void *native_lease;
	kd_task_native_release_fn native_release;
	bool stack_held;
	/* Lock order is storage -> request pool. Exact actors bridge the final
	 * pool API return; neither a task ref nor node.retirable pins allocation.
	 */
	raw_spinlock_t guard;
	struct list_head cancel_actors;
	struct work_struct retire_work;
	bool deferred_cancel_exit;
	bool detached;
	struct module *retire_code_owner;
};

static bool native_context(void)
{
	return in_task() && !in_atomic() && !irqs_disabled() &&
		READ_ONCE(current->__state) == TASK_RUNNING;
}

/* Private storage with no published root or remaining observer. No native lease
 * is released here: NULL-output allocation/setup failure leaves it with caller.
 */
static void free_private(struct kd_task_storage *storage)
{
	if (storage->stack_held)
		kd_source_stack_release(&storage->source);
	vfree(storage->auxiliary);
	kvfree(storage->frames);
	kvfree(storage->slots);
	kfree(storage);
}

static void retire_cancelled_work(struct work_struct *work)
{
	struct kd_task_storage *storage =
		container_of(work, struct kd_task_storage, retire_work);
	kd_task_native_release_fn release;
	struct module *code_owner;
	struct task_struct *task;
	unsigned long flags;
	void *lease;
	int result;

	/* The last callback queues work while still holding this guard. Taking
	 * it establishes that callback's final pool unlock and storage access.
	 */
	raw_spin_lock_irqsave(&storage->guard, flags);
	if (WARN_ON_ONCE(!storage->detached || !list_empty(&storage->cancel_actors))) {
		raw_spin_unlock_irqrestore(&storage->guard, flags);
		return;
	}
	result = kd_request_pool_retire_detached(&storage->pool);
	if (WARN_ON_ONCE(result)) {
		/* A violated last-user contract retains every allocation and hold.
		 * No polling, current-bound collection or forced free is permitted.
		 */
		raw_spin_unlock_irqrestore(&storage->guard, flags);
		return;
	}
	release = storage->native_release;
	lease = storage->native_lease;
	code_owner = storage->retire_code_owner;
	task = storage->root.task;
	raw_spin_unlock_irqrestore(&storage->guard, flags);
	/* Every queue/source observer ended. Invalidate/drop the independently
	 * retained original stack first, then attach's separate task reference.
	 */
	if (storage->stack_held) {
		storage->stack_held = false;
		kd_source_stack_release(&storage->source);
	}
	put_task_struct(task);
	vfree(storage->auxiliary);
	kvfree(storage->frames);
	kvfree(storage->slots);
	kfree(storage);
	/* Only cached independent inputs survive freeing. The module hold ends
	 * after the native/provider callback has returned to this built-in code.
	 */
	release(lease);
	module_put(code_owner);
}

void kd_task_cancel_actor_init(struct kd_task_cancel_actor *actor)
{
	INIT_LIST_HEAD(&actor->link);
	actor->storage = NULL;
	actor->slot = NULL;
	actor->claim = NULL;
	actor->queue_user = NULL;
	actor->identity = NULL;
	actor->linked = false;
}

int kd_task_cancel_actor_hold(struct kd_task_root_context *root,
		struct kd_task_cancel_actor *actor, struct kd_request_slot *slot,
		const void *claim, struct kd_request_user *queue_user,
		const void *identity)
{
	struct kd_task_storage *storage;
	struct kd_task_cancel_actor *other;
	unsigned long flags;
	int result = 0;

	if (!root || !actor || !slot || !claim || !queue_user || !identity ||
	    actor->linked || actor->storage || !list_empty(&actor->link))
		return -EINVAL;
	storage = root->storage;
	/* A custom caller-owned root cannot opt into allocation retirement. */
	if (!storage)
		return 0;
	raw_spin_lock_irqsave(&storage->guard, flags);
	if (storage->detached || root != &storage->root || slot->pool != &storage->pool)
		result = -ESTALE;
	else {
		/* Private serialized frame construction owns this already-held user.
		 * The pool guard pairs validation with all user metadata APIs.
		 */
		raw_spin_lock(&storage->pool.guard);
		if (slot->claim != claim || !queue_user->linked || queue_user->slot != slot ||
		    queue_user->identity != identity ||
		    queue_user->kind == KD_REQUEST_USER_UNUSED ||
		    queue_user->kind == KD_REQUEST_USER_PARENT)
			result = -ESTALE;
		raw_spin_unlock(&storage->pool.guard);
	}
	if (!result) {
		list_for_each_entry(other, &storage->cancel_actors, link)
			if (other->slot == slot) {
				result = -EALREADY;
				break;
			}
	}
	if (!result) {
		actor->storage = storage;
		actor->slot = slot;
		actor->claim = claim;
		actor->queue_user = queue_user;
		actor->identity = identity;
		actor->linked = true;
		list_add_tail(&actor->link, &storage->cancel_actors);
	}
	raw_spin_unlock_irqrestore(&storage->guard, flags);
	return result;
}

int kd_task_cancel_actor_finish(struct kd_task_cancel_actor *actor,
		struct kd_request_user *queue_user, const void *identity)
{
	struct kd_task_storage *storage;
	struct kd_request_slot *slot;
	const void *claim;
	unsigned long flags;
	int result;

	if (!actor || !queue_user || !identity)
		return -EINVAL;
	storage = actor->storage;
	if (!storage) {
		if (actor->linked)
			return -EUCLEAN;
		return kd_request_user_finish(queue_user, identity);
	}
	raw_spin_lock_irqsave(&storage->guard, flags);
	if (!actor->linked || actor->storage != storage ||
	    actor->queue_user != queue_user || actor->identity != identity) {
		raw_spin_unlock_irqrestore(&storage->guard, flags);
		return -ESTALE;
	}
	slot = actor->slot;
	claim = actor->claim;
	list_del_init(&actor->link);
	actor->linked = false;
	actor->storage = NULL;
	actor->slot = NULL;
	actor->claim = NULL;
	actor->queue_user = NULL;
	actor->identity = NULL;
	/* The still-linked pool user protects actor until this API starts.
	 * A successful finish can immediately reuse its slot: no actor, frame,
	 * user or slot access follows that success, including flag updates.
	 */
	result = kd_request_user_finish(queue_user, identity);
	if (result) {
		/* Failure consumes nothing, so the exact user still retains actor. */
		actor->storage = storage;
		actor->slot = slot;
		actor->claim = claim;
		actor->queue_user = queue_user;
		actor->identity = identity;
		actor->linked = true;
		list_add_tail(&actor->link, &storage->cancel_actors);
	} else if (storage->detached && list_empty(&storage->cancel_actors)) {
		queue_work(system_unbound_wq, &storage->retire_work);
	}
	/* The worker takes this same guard before freeing. Unlock is the last
	 * storage access, after the final pool API has completely returned.
	 */
	raw_spin_unlock_irqrestore(&storage->guard, flags);
	return result;
}

int kd_task_storage_defer_cancelled_current(struct kd_task_storage *storage,
		struct kd_execution_binding *expected_native)
{
	struct module *code_owner;
	unsigned long flags;
	int result;

	if (!storage || !expected_native)
		return -EINVAL;
	if (!native_context())
		return -EWOULDBLOCK;
	if (!storage->deferred_cancel_exit)
		return -EBUSY;
	code_owner = storage->retire_code_owner;
	if (!try_module_get(code_owner))
		return -EAGAIN;
	raw_spin_lock_irqsave(&storage->guard, flags);
	if (storage->detached || list_empty(&storage->cancel_actors))
		result = -EBUSY;
	else
		result = kd_task_root_revoke_cancelled(&storage->root, expected_native,
			&storage->cancel_actors);
	if (!result)
		storage->detached = true;
	raw_spin_unlock_irqrestore(&storage->guard, flags);
	if (result)
		module_put(code_owner);
	/* Successful revocation leaves the independent owner reference with the
	 * worker. Current must not revisit root/endpoint/storage after success.
	 */
	return result;
}

static int start_task(const struct kd_task_storage_args *args,
		     struct task_struct *task, bool unpublished,
		     struct kd_task_storage **out)
{
	struct kd_task_storage_args input;
	struct kd_episode_config config;
	struct kd_task_setup_args setup;
	struct kd_task_storage *storage;
	unsigned long auxiliary_low, auxiliary_high;
	size_t checked_bytes;
	int result;

	if (!out)
		return -EINVAL;
	*out = NULL;
	if (!args || !task || (unpublished && task == current))
		return -EINVAL;
	input = *args;
	if (!native_context())
		return -EWOULDBLOCK;
	if (smp_load_acquire(&task->kd_root_context))
		return -EEXIST;
	if (!input.capacity || !input.auxiliary_bytes ||
	    (input.auxiliary_bytes & (PAGE_SIZE - 1)) ||
	    input.required_control_bytes < sizeof(unsigned long) ||
	    input.required_control_bytes > input.auxiliary_bytes ||
	    !input.config || !input.native_lease || !input.native_release)
		return -EINVAL;
	config = *input.config;
	if (config.stack)
		return -EINVAL;
	if (check_mul_overflow((size_t)input.capacity,
			      sizeof(*storage->slots), &checked_bytes) ||
	    check_mul_overflow((size_t)input.capacity,
			      sizeof(*storage->frames), &checked_bytes))
		return -EOVERFLOW;

	storage = kmalloc(sizeof(*storage), GFP_KERNEL);
	if (!storage)
		return -ENOMEM;
	/* Initialize metadata only. The one canonical packet is never cleared. */
	kd_task_root_context_init(&storage->root);
	storage->slots = NULL;
	storage->frames = NULL;
	storage->auxiliary = NULL;
	storage->native_lease = input.native_lease;
	storage->native_release = input.native_release;
	storage->stack_held = false;
	raw_spin_lock_init(&storage->guard);
	INIT_LIST_HEAD(&storage->cancel_actors);
	INIT_WORK(&storage->retire_work, retire_cancelled_work);
	storage->deferred_cancel_exit = input.deferred_cancel_exit;
	storage->detached = false;
	storage->retire_code_owner = input.retire_code_owner;
	storage->slots = kvmalloc_array(input.capacity, sizeof(*storage->slots), GFP_KERNEL);
	storage->frames = kvmalloc_array(input.capacity, sizeof(*storage->frames), GFP_KERNEL);
	storage->auxiliary = vmalloc(input.auxiliary_bytes);
	if (!storage->slots || !storage->frames || !storage->auxiliary) {
		result = -ENOMEM;
		goto fail;
	}
	auxiliary_low = (unsigned long)storage->auxiliary;
	if (check_add_overflow(auxiliary_low, (unsigned long)input.auxiliary_bytes,
			       &auxiliary_high)) {
		result = -EOVERFLOW;
		goto fail;
	}
	result = unpublished ? kd_source_stack_acquire_unpublished(&storage->source, task) :
		kd_source_stack_acquire_current(&storage->source);
	if (result)
		goto fail;
	storage->stack_held = true;
	config.stack = &storage->source.ops;
	setup.root = &storage->root;
	setup.pool = &storage->pool;
	setup.slots = storage->slots;
	setup.resources = &storage->resources;
	setup.frames = storage->frames;
	setup.capacity = input.capacity;
	setup.origin_gs = input.origin_gs;
	setup.aux_low = auxiliary_low;
	setup.aux_high = auxiliary_high;
	setup.aux_current = auxiliary_high;
	setup.required_control_bytes = input.required_control_bytes;
	setup.config = &config;
	if (!unpublished) {
		result = kd_task_setup_current(&setup);
	} else {
		/* All backing is freshly allocated, parent-owned and outside both
		 * stacks. The inherited immutable provider configuration was already
		 * admitted by the managed parent and remains independently retained.
		 */
		result = kd_task_root_attach_unpublished(&storage->root, task,
			input.origin_gs, auxiliary_low, auxiliary_high, auxiliary_high,
			&storage->pool, storage->slots, input.capacity);
		if (!result) {
			result = kd_episode_resources_init(&storage->resources, &storage->pool,
				storage->frames, input.capacity, &config);
			if (!result) {
				storage->root.mutex_resources = &storage->resources;
				storage->root.mutex_control_bytes = input.required_control_bytes;
				storage->root.owners.atomic_spin = config.atomic_spin;
			} else {
				int unwind = kd_task_root_detach_unpublished(&storage->root, task);

				if (unwind)
					result = unwind;
			}
		}
	}
	if (result) {
		/* Setup reports a failed post-attach unwind by leaving the exact
		 * root attached. Do not free it or release its native provider hold.
		 */
		if (storage->root.attached ||
		    smp_load_acquire(&task->kd_root_context) == &storage->root) {
			storage->root.storage = storage;
			*out = storage;
			return result;
		}
		goto fail;
	}
	storage->root.storage = storage;
	*out = storage;
	return 0;
fail:
	free_private(storage);
	return result;
}

int kd_task_storage_start_current(const struct kd_task_storage_args *args,
				 struct kd_task_storage **out)
{
	return start_task(args, current, false, out);
}

int kd_task_storage_prepare_unpublished(const struct kd_task_storage_args *args,
		struct task_struct *child, struct kd_task_storage **out)
{
	return start_task(args, child, true, out);
}

int kd_task_storage_abort_unpublished(struct kd_task_storage *storage,
				      struct task_struct *child)
{
	kd_task_native_release_fn release;
	void *lease;
	int result;

	if (!storage || !child || child == current || !native_context())
		return -EINVAL;
	release = storage->native_release;
	lease = storage->native_lease;
	result = kd_task_root_detach_unpublished(&storage->root, child);
	if (result)
		return result;
	free_private(storage);
	release(lease);
	return 0;
}

struct kd_task_root_context *kd_task_storage_root(struct kd_task_storage *storage)
{
	return storage ? &storage->root : NULL;
}

int kd_task_storage_stop_current(struct kd_task_storage *storage,
		struct kd_execution_binding *expected_native, bool *pending)
{
	kd_task_native_release_fn release;
	void *lease;
	unsigned long flags;
	int result;

	if (!storage || !expected_native || !pending)
		return -EINVAL;
	if (!native_context())
		return -EWOULDBLOCK;
	if (kd_task_root_context_current() != &storage->root ||
	    !storage->root.attached || storage->root.task != current)
		return -EPERM;
	/* Cache only independent finalizer inputs before detach can revoke and
	 * reclaim the slot containing expected_native. Never read it afterward.
	 */
	release = storage->native_release;
	lease = storage->native_lease;
	result = kd_task_teardown_current(&storage->root, expected_native, pending);
	if (result)
		return result;
	/* A final queue user may have ended immediately before pool detach while
	 * its actor_finish still owns storage.guard. Join that API's final unlock
	 * before synchronous free too. Full pool detach proves no actor can remain
	 * linked or newly begin; the source-closed last-user contract excludes new
	 * construction. No source/progress callback runs under this guard.
	 */
	raw_spin_lock_irqsave(&storage->guard, flags);
	BUG_ON(!list_empty(&storage->cancel_actors) || storage->detached);
	raw_spin_unlock_irqrestore(&storage->guard, flags);
	free_private(storage);
	/* All storage/stack accesses finished; native/provider lease is last. */
	release(lease);
	return 0;
}
