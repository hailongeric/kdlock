// SPDX-License-Identifier: GPL-2.0
/* Ordinary rwsem object binding. Activation follows source/image preparation;
 * module load alone never changes an existing or newly initialized object. */
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/cpu.h>
#include <linux/string.h>
#include "kd_rwsem_provider.h"
#include "kd_rwsem.h"
#include "kd_lock.h"
#include "kd_service_api.h"
#include "kd_service_calls.h"
#include "kd_source.h"
#include "exe.h"

static bool kd_rwsem_provider_registered;
static bool kd_rwsem_provider_initialized;
#ifdef CONFIG_KDLOCK_MMAP
static DEFINE_MUTEX(kd_rwsem_provider_state_lock);
#endif
module_param_named(rwsem_provider_active, kd_rwsem_provider_registered, bool, 0444);
MODULE_PARM_DESC(rwsem_provider_active, "New rwsem objects bind to the prepared execution provider");

#ifdef CONFIG_KDLOCK_MMAP
static void kd_provider_init_object(void *object)
{
	struct kd_rwsem *sem = object;

	BUILD_BUG_ON(sizeof(*sem) != KD_RWSEM_PROVIDER_STORAGE_BYTES);
	BUILD_BUG_ON(__alignof__(*sem) != KD_RWSEM_PROVIDER_STORAGE_ALIGN);
	kd_rwsem_init(sem);
	/* Capability is selected before publication, never changed on a live mm.
	 * Entry images are prepared independently of individual object storage. */
	WRITE_ONCE(sem->prepared_writes, 1);
}

static bool kd_provider_idle(const void *object)
{
	return kd_rwsem_is_idle((struct kd_rwsem *)object);
}

static void kd_provider_destroy_object(void *object)
{
	BUG_ON(!kd_provider_idle(object));
}

#define KD_PROVIDER_VOID_WRAPPER(name, function) \
static void name(void *object) { (function)((struct kd_rwsem *)object); }
#define KD_PROVIDER_INT_WRAPPER(name, function) \
static int name(void *object) { return (function)((struct kd_rwsem *)object); }
KD_PROVIDER_VOID_WRAPPER(kd_provider_down_write, kd_down_write)
KD_PROVIDER_INT_WRAPPER(kd_provider_down_write_interruptible, kd_down_write_interruptible)
KD_PROVIDER_INT_WRAPPER(kd_provider_down_write_killable, kd_down_write_killable)
KD_PROVIDER_INT_WRAPPER(kd_provider_down_write_trylock, kd_down_write_trylock)
KD_PROVIDER_VOID_WRAPPER(kd_provider_up_write, kd_up_write)
KD_PROVIDER_VOID_WRAPPER(kd_provider_downgrade_write, kd_downgrade_write)
KD_PROVIDER_VOID_WRAPPER(kd_provider_down_read, kd_down_read)
KD_PROVIDER_INT_WRAPPER(kd_provider_down_read_interruptible, kd_down_read_interruptible)
KD_PROVIDER_INT_WRAPPER(kd_provider_down_read_killable, kd_down_read_killable)
KD_PROVIDER_INT_WRAPPER(kd_provider_down_read_trylock, kd_down_read_trylock)
KD_PROVIDER_VOID_WRAPPER(kd_provider_up_read, kd_up_read)
KD_PROVIDER_VOID_WRAPPER(kd_provider_down_read_non_owner, kd_down_read_non_owner)
KD_PROVIDER_VOID_WRAPPER(kd_provider_up_read_non_owner, kd_up_read_non_owner)
#undef KD_PROVIDER_VOID_WRAPPER
#undef KD_PROVIDER_INT_WRAPPER

static bool kd_provider_is_locked(const void *object)
{
	return kd_rwsem_is_locked((struct kd_rwsem *)object);
}

static bool kd_provider_is_contended(const void *object)
{
	return kd_rwsem_is_contended((struct kd_rwsem *)object);
}

static bool kd_provider_write_owned(const void *object, const struct task_struct *task)
{
	const struct kd_rwsem *sem = object;
	unsigned long owner = atomic_long_read(&sem->gate.owner);

	/* LOCAL callers retain their successful grant in the object's owner and
	 * phase fields. Delegated origin helpers require the runtime's exact token. */
	if (atomic_long_read(&sem->admission) == -1 &&
	    READ_ONCE(sem->selected_kind) == KD_RWSEM_PHASE_LOCAL &&
	    READ_ONCE(sem->selected_owner) == task && !(owner & 4UL) &&
	    (owner & ~KD_MUTEX_OWNER_FLAGS) == (unsigned long)task)
		return true;
	return kd_service_write_owned((void *)object, (struct task_struct *)task);
}

static void kd_provider_assert_held(const void *object)
{
	kd_rwsem_assert_held(object);
}

static void kd_provider_assert_held_write(const void *object)
{
	WARN_ON_ONCE(!kd_provider_write_owned(object, current));
}

static const struct kd_service_completion kd_provider_completion = {
	.owner = THIS_MODULE,
	.resume = kd_rwsem_provider_resume,
};

static int kd_provider_capture(void *object, unsigned int state,
			       unsigned long sp, unsigned long ip, unsigned long bp)
{
	return kd_service_capture_bound(object, KD_ADMISSION_RWSEM_WRITE, state,
		sp, ip, bp, &kd_provider_completion);
}

static const struct kd_rwsem_provider kd_rwsem_ops = {
	.version = KD_RWSEM_PROVIDER_VERSION,
	.storage_bytes = KD_RWSEM_PROVIDER_STORAGE_BYTES,
	.storage_align = KD_RWSEM_PROVIDER_STORAGE_ALIGN,
	.packet_layout = KD_RWSEM_PROVIDER_PACKET_LAYOUT,
	.owner = THIS_MODULE,
	.binding_get = kd_source_binding_get,
	.binding_put = kd_source_binding_put,
	.init = kd_provider_init_object,
	.destroy = kd_provider_destroy_object,
	.idle = kd_provider_idle,
	.down_write = kd_provider_down_write,
	.down_write_interruptible = kd_provider_down_write_interruptible,
	.down_write_killable = kd_provider_down_write_killable,
	.down_write_trylock = kd_provider_down_write_trylock,
	.up_write = kd_provider_up_write,
	.downgrade_write = kd_provider_downgrade_write,
	.down_read = kd_provider_down_read,
	.down_read_interruptible = kd_provider_down_read_interruptible,
	.down_read_killable = kd_provider_down_read_killable,
	.down_read_trylock = kd_provider_down_read_trylock,
	.up_read = kd_provider_up_read,
	.down_read_non_owner = kd_provider_down_read_non_owner,
	.up_read_non_owner = kd_provider_up_read_non_owner,
	.is_locked = kd_provider_is_locked,
	.is_contended = kd_provider_is_contended,
	.write_owned = kd_provider_write_owned,
	.assert_held = kd_provider_assert_held,
	.assert_held_write = kd_provider_assert_held_write,
	.capture = kd_provider_capture,
};
#endif

static int kd_rwsem_controls_get(char *buffer, const struct kernel_param *parameter)
{
	int used = 0;
#ifdef CONFIG_KDLOCK_MMAP
	const struct kd_rwsem_control_binding *controls;
	unsigned int count, index;
#endif

	(void)parameter;
	(void)buffer;
#ifdef CONFIG_KDLOCK_MMAP

	controls = kd_rwsem_provider_controls(&count);
	for (index = 0; index < count; ++index) {
		const struct kd_rwsem_control_binding *binding = &controls[index];

		if (used >= PAGE_SIZE - 96)
			return -EOVERFLOW;
		used += scnprintf(buffer + used, PAGE_SIZE - used,
			"%lx %u %u rwsem_control_%u_%u\n", binding->target,
			binding->operation, binding->flags, binding->operation, binding->flags);
	}
#endif
	return used;
}
static const struct kernel_param_ops kd_rwsem_controls_ops = {
	.get = kd_rwsem_controls_get,
};
module_param_cb(rwsem_control_table, &kd_rwsem_controls_ops, NULL, 0444);
MODULE_PARM_DESC(rwsem_control_table, "Exact facade control target, operation and ABI flags");

bool kd_rwsem_provider_lookup_control(unsigned long target, void *source_argument,
				     unsigned int *operation, unsigned int *flags,
				     void **object)
{
#ifdef CONFIG_KDLOCK_MMAP
	const struct kd_rwsem_control_binding *controls;
	unsigned int count, index;

	controls = kd_rwsem_provider_controls(&count);
	for (index = 0; index < count; ++index) {
		const struct kd_rwsem_control_binding *binding = &controls[index];
		void *storage;

		if (binding->target != target)
			continue;
		/* Returning queries retain their facade argument and execute as a
		 * balanced Native CALL, rather than an ownership-changing service. */
		if (binding->flags & KD_RWSEM_CONTROL_PRIMITIVE)
			continue;
		storage = binding->resolve(source_argument, &kd_rwsem_ops);
		if (!storage)
			return false;
		*operation = binding->operation;
		*flags = binding->flags;
		*object = storage;
		return true;
	}
#else
	(void)target;
	(void)source_argument;
	(void)operation;
	(void)flags;
	(void)object;
#endif
	return false;
}

int kd_rwsem_provider_prepare_entries(void)
{
#ifdef CONFIG_KDLOCK_MMAP
	const struct kd_rwsem_site *sites;
	unsigned int count, index;
	int result = 0;

	mutex_lock(&kd_rwsem_provider_state_lock);
	if (!kd_rwsem_provider_initialized || kd_rwsem_provider_registered) {
		result = -EBUSY;
		goto out;
	}
	if (!kd_source_is_open()) {
		result = -ESHUTDOWN;
		goto out;
	}
	sites = kd_rwsem_provider_sites(&count);
	if (!count) {
		result = -ENOENT;
		goto out;
	}
	for (index = 0; index < count; ++index) {
		struct kd_exe_info *exe;

		if (!sites[index].entry || sites[index].reserved ||
		    (sites[index].operation != KD_RWSEM_OP_DOWN_WRITE &&
		     sites[index].operation != KD_RWSEM_OP_DOWN_WRITE_KILLABLE)) {
			result = -EINVAL;
			goto out;
		}
		kd_exe_add_abi(0, sites[index].entry, KD_EXE_LOCK_MUTEX,
			       KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
		exe = kd_get_exe(0, sites[index].entry);
		if (!exe || READ_ONCE(exe->status_code) == KD_EXE_UNUSED ||
		    READ_ONCE(exe->RIP) != sites[index].entry ||
		    READ_ONCE(exe->entry_abi) != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
		    READ_ONCE(exe->lock_kind) != KD_EXE_LOCK_MUTEX) {
			result = -ENOMEM;
			goto out;
		}
	}
out:
	mutex_unlock(&kd_rwsem_provider_state_lock);
	return result;
#else
	return -EOPNOTSUPP;
#endif
}

int kd_rwsem_provider_activate(void)
{
	int result = -EOPNOTSUPP;

#ifdef CONFIG_KDLOCK_MMAP
	const struct kd_rwsem_site *sites;
	unsigned int count, index;

	mutex_lock(&kd_rwsem_provider_state_lock);
	if (!kd_rwsem_provider_initialized) {
		result = -EAGAIN;
		goto out;
	}
	if (kd_rwsem_provider_registered) {
		result = -EALREADY;
		goto out;
	}
	if (!kd_source_is_open()) {
		result = -ESHUTDOWN;
		goto out;
	}
	if (num_online_cpus() < 2) {
		result = -EOPNOTSUPP;
		goto out;
	}
	sites = kd_rwsem_provider_sites(&count);
	if (!count) {
		result = -ENOENT;
		goto out;
	}
	for (index = 0; index < count; ++index) {
		struct kd_exe_info *exe = kd_exe_find_ready(0, sites[index].entry);

		if (!kd_exe_capture_image(exe, sites[index].entry)) {
			result = -EAGAIN;
			goto out;
		}
	}
	if (!kd_source_binding_get()) {
		result = -ESHUTDOWN;
		goto out;
	}
	result = kd_rwsem_register_provider(&kd_rwsem_ops);
	if (!result) {
		WRITE_ONCE(kd_rwsem_provider_registered, true);
	} else {
		kd_source_binding_put();
	}
out:
	mutex_unlock(&kd_rwsem_provider_state_lock);
#endif
	return result;
}

void kd_rwsem_provider_deactivate(void)
{
#ifdef CONFIG_KDLOCK_MMAP
	mutex_lock(&kd_rwsem_provider_state_lock);
	if (kd_rwsem_provider_registered) {
		kd_rwsem_unregister_provider(&kd_rwsem_ops);
		WRITE_ONCE(kd_rwsem_provider_registered, false);
		kd_source_binding_put();
	}
	mutex_unlock(&kd_rwsem_provider_state_lock);
#endif
}

bool kd_rwsem_provider_active(void)
{
	return READ_ONCE(kd_rwsem_provider_registered);
}

int kd_rwsem_provider_init(void)
{
#ifdef CONFIG_KDLOCK_MMAP
	const struct kd_rwsem_control_binding *controls;
	struct kd_service_call_desc descriptors[2];
	char labels[2][32];
	const struct kd_service_call_desc ownership_query = {
		.symbol = "kd_service_write_owned",
		.target = (unsigned long)kd_service_write_owned,
		.nargs = 2,
		.result_kind = KD_SERVICE_CALL_WORD,
		.context_kind = KD_SERVICE_CALL_ATOMIC_ORIGIN,
	};
	unsigned int count, index, registered = 0;
	int result;

	controls = kd_rwsem_provider_controls(&count);
	for (index = 0; index < count; ++index) {
		const struct kd_rwsem_control_binding *binding = &controls[index];
		unsigned char result_kind;

		if (!(binding->flags & KD_RWSEM_CONTROL_PRIMITIVE))
			continue;
		switch (binding->operation) {
		case KD_RWSEM_OP_ASSERT_HELD:
		case KD_RWSEM_OP_ASSERT_HELD_WRITE:
		case KD_RWSEM_OP_IS_LOCKED:
			/* These ordinary state-query bodies use original JIT lowering and
			 * reached CALL learning. Their discovery rows remain unchanged. */
			if (binding->flags != KD_RWSEM_CONTROL_PRIMITIVE)
				return -EINVAL;
			continue;
		case KD_RWSEM_OP_IS_CONTENDED:
		case KD_RWSEM_OP_IS_WRITE_OWNER:
			result_kind = KD_SERVICE_CALL_WORD;
			break;
		default:
			return -EINVAL;
		}
		if (registered == ARRAY_SIZE(descriptors) ||
		    binding->flags != KD_RWSEM_CONTROL_PRIMITIVE)
			return -EINVAL;
		scnprintf(labels[registered], sizeof(labels[registered]),
			  "rwsem_query_%u", binding->operation);
		descriptors[registered] = (struct kd_service_call_desc) {
			.symbol = labels[registered],
			.target = binding->target,
			.nargs = 1,
			.result_kind = result_kind,
			.context_kind = KD_SERVICE_CALL_BALANCED_ORIGIN,
		};
		++registered;
	}
	if (registered != ARRAY_SIZE(descriptors))
		return -EINVAL;
	/* These targets are builtin facades. Their callback pins and the exact
	 * bound object retain the module independently of the returning CALL. */
	result = kd_service_call_register(descriptors, registered, NULL);
	if (result)
		return result;
	/* Only the inner runtime ledger query needs physical task/CPU context.
	 * Its existing O transaction checks exact E ownership while E is
	 * suspended. The query neither allocates nor changes held-lock context;
	 * the descriptor pins this module through its returning service ACK. */
	result = kd_service_call_register(&ownership_query, 1, THIS_MODULE);
	if (result)
		return result;
#endif
	/* Registration remains an explicit post-preparation action. */
	WRITE_ONCE(kd_rwsem_provider_initialized, true);
	return 0;
}

void kd_rwsem_provider_exit(void)
{
	kd_rwsem_provider_deactivate();
	WRITE_ONCE(kd_rwsem_provider_initialized, false);
}

static int kd_rwsem_provider_mode_set(const char *value,
				    const struct kernel_param *parameter)
{
	(void)parameter;
	if (!READ_ONCE(kd_rwsem_provider_initialized))
		return -EAGAIN;
	if (sysfs_streq(value, "prepare"))
		return kd_rwsem_provider_prepare_entries();
	if (sysfs_streq(value, "activate"))
		return kd_rwsem_provider_activate();
	if (sysfs_streq(value, "deactivate")) {
		kd_rwsem_provider_deactivate();
		return 0;
	}
	return -EINVAL;
}

static int kd_rwsem_provider_mode_get(char *buffer,
				    const struct kernel_param *parameter)
{
	(void)parameter;
	return scnprintf(buffer, PAGE_SIZE, "%s\n",
		READ_ONCE(kd_rwsem_provider_registered) ? "active" : "inactive");
}

static const struct kernel_param_ops kd_rwsem_provider_mode_ops = {
	.set = kd_rwsem_provider_mode_set,
	.get = kd_rwsem_provider_mode_get,
};
module_param_cb(rwsem_provider_mode, &kd_rwsem_provider_mode_ops, NULL, 0644);
MODULE_PARM_DESC(rwsem_provider_mode, "Setup action: prepare, activate or deactivate new object binding");

static int kd_rwsem_provider_bindings_get(char *buffer,
					const struct kernel_param *parameter)
{
	(void)parameter;
	return scnprintf(buffer, PAGE_SIZE, "%llu\n",
		(unsigned long long)kd_source_binding_count());
}

static const struct kernel_param_ops kd_rwsem_provider_bindings_ops = {
	.get = kd_rwsem_provider_bindings_get,
};
module_param_cb(rwsem_provider_bindings, &kd_rwsem_provider_bindings_ops, NULL, 0444);
MODULE_PARM_DESC(rwsem_provider_bindings, "Exact source residency leases: active registration and bound objects");
