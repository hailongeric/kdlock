// SPDX-License-Identifier: GPL-2.0
/* Ordinary rwsem object binding. Activation follows source preparation;
 * module load alone never changes an existing or newly initialized object. */
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/cpu.h>
#include <linux/string.h>
#include <linux/compat.h>
#include <linux/mman.h>
#include <linux/sched/task_stack.h>
#include <asm/syscall.h>
#include "kd_rwsem_provider.h"
#include "kd_rwsem.h"
#include "kd_lock.h"
#include "kd_service_api.h"
#include "kd_service_calls.h"
#include "kd_source.h"
#include "exe.h"

static bool kd_rwsem_provider_registered;
static bool kd_rwsem_provider_initialized;
static bool kd_rwsem_provider_demand;
module_param_named(rwsem_provider_demand, kd_rwsem_provider_demand, bool, 0444);
MODULE_PARM_DESC(rwsem_provider_demand, "Prepare images when their entries are encountered");
static unsigned long kd_rwsem_provider_entries[64];
static unsigned int kd_rwsem_provider_entry_count;
module_param_array_named(rwsem_provider_entries, kd_rwsem_provider_entries,
	ulong, &kd_rwsem_provider_entry_count, 0444);
MODULE_PARM_DESC(rwsem_provider_entries,
	"Immutable writer entry selection; empty selects every builtin writer entry");
static bool kd_rwsem_provider_syscall_shape;
module_param_named(rwsem_provider_syscall_shape, kd_rwsem_provider_syscall_shape, bool, 0444);
MODULE_PARM_DESC(rwsem_provider_syscall_shape,
	"Benchmark native64 syscall argument selection; excluded captures use local KD");

static int kd_rwsem_syscall_shape_version_get(char *buffer,
					    const struct kernel_param *parameter)
{
	(void)parameter;
	return scnprintf(buffer, PAGE_SIZE, "1\n");
}
static const struct kernel_param_ops kd_rwsem_syscall_shape_version_ops = {
	.get = kd_rwsem_syscall_shape_version_get,
};
module_param_cb(rwsem_provider_syscall_shape_version, &kd_rwsem_syscall_shape_version_ops, NULL, 0444);
MODULE_PARM_DESC(rwsem_provider_syscall_shape_version, "Getter-only syscall argument selection contract version");
#ifdef CONFIG_KDLOCK_MMAP
static DEFINE_MUTEX(kd_rwsem_provider_state_lock);
#endif
module_param_named(rwsem_provider_active, kd_rwsem_provider_registered, bool, 0444);
MODULE_PARM_DESC(rwsem_provider_active, "New rwsem objects bind to the prepared execution provider");

#ifdef CONFIG_KDLOCK_MMAP
static bool kd_rwsem_entry_selected(unsigned long entry)
{
	unsigned int index;

	if (!kd_rwsem_provider_entry_count)
		return true;
	for (index = 0; index < kd_rwsem_provider_entry_count; ++index)
		if (kd_rwsem_provider_entries[index] == entry)
			return true;
	return false;
}

static int kd_rwsem_entry_scope_valid(const struct kd_rwsem_site *sites,
				    unsigned int count)
{
	unsigned int index, other, site;

	/* Demand registration is what keeps excluded calls out of learning. */
	if (kd_rwsem_provider_syscall_shape &&
	    (!kd_rwsem_provider_demand || !kd_rwsem_provider_entry_count))
		return -EINVAL;
	for (index = 0; index < kd_rwsem_provider_entry_count; ++index) {
		unsigned long entry = kd_rwsem_provider_entries[index];

		if (!entry)
			return -EINVAL;
		for (other = 0; other < index; ++other)
			if (kd_rwsem_provider_entries[other] == entry)
				return -EINVAL;
		for (site = 0; site < count; ++site)
			if (sites[site].entry == entry && !sites[site].reserved &&
			    (sites[site].operation == KD_RWSEM_OP_DOWN_WRITE ||
			     sites[site].operation == KD_RWSEM_OP_DOWN_WRITE_KILLABLE))
				break;
		if (site == count)
			return -EINVAL;
	}
	return 0;
}

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

static bool kd_rwsem_syscall_shape_matches(long number, const unsigned long *arguments)
{
	const unsigned long bytes = 128UL * 1024 * 1024;

	if (number == __NR_mmap)
		return !arguments[0] && arguments[1] == bytes &&
			arguments[2] == (PROT_READ | PROT_WRITE) &&
			arguments[3] == (MAP_PRIVATE | MAP_ANONYMOUS) &&
			(unsigned int)arguments[4] == (unsigned int)-1 && !arguments[5];
	/* Address/length alone cannot identify the mapping type or its pair. */
	return number == __NR_munmap && arguments[0] &&
		!(arguments[0] & (PAGE_SIZE - 1)) && arguments[1] == bytes;
}

static bool kd_rwsem_capture_shape_selected(void)
{
	struct pt_regs *registers;
	unsigned long arguments[6];

	if (!kd_rwsem_provider_syscall_shape)
		return true;
	/* This public entry still runs on the caller. KD continuation tags live
	 * in a separate packet; only the task's saved userspace frame is read. */
	if (!current->mm || (current->flags & PF_KTHREAD) || in_compat_syscall())
		return false;
	registers = task_pt_regs(current);
	if (!user_64bit_mode(registers))
		return false;
	syscall_get_arguments(current, registers, arguments);
	return kd_rwsem_syscall_shape_matches(syscall_get_nr(current, registers), arguments);
}

static int kd_provider_capture(void *object, unsigned int state,
			       unsigned long sp, unsigned long ip, unsigned long bp)
{
	/* An excluded capture still acquires this object's KD protocol. Decide
	 * before source capture or registration; zero means the lock is held. */
	if (!kd_rwsem_entry_selected(ip) || !kd_rwsem_capture_shape_selected()) {
		if (state == TASK_KILLABLE)
			return kd_provider_down_write_killable(object);
		if (state == TASK_INTERRUPTIBLE)
			return kd_provider_down_write_interruptible(object);
		kd_provider_down_write(object);
		return 0;
	}
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
		/* Cold capture registers its entry and keeps acquisition local.
		 * Delegated requests require a usable image before publication. */
		if (kd_rwsem_provider_demand || !kd_rwsem_entry_selected(sites[index].entry))
			continue;
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
		struct kd_exe_info *exe;

		if (!sites[index].entry || sites[index].reserved ||
		    (sites[index].operation != KD_RWSEM_OP_DOWN_WRITE &&
		     sites[index].operation != KD_RWSEM_OP_DOWN_WRITE_KILLABLE)) {
			result = -EINVAL;
			goto out;
		}
		/* Image readiness remains mandatory at capture. A missing image
		 * takes ordinary local acquisition before any delegated effects. */
		if (kd_rwsem_provider_demand || !kd_rwsem_entry_selected(sites[index].entry))
			continue;
		exe = kd_exe_find_ready(0, sites[index].entry);

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
	const struct kd_rwsem_site *sites;
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

	sites = kd_rwsem_provider_sites(&count);
	result = kd_rwsem_entry_scope_valid(sites, count);
	if (result)
		return result;
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
#else
	if (kd_rwsem_provider_entry_count || kd_rwsem_provider_syscall_shape)
		return -EOPNOTSUPP;
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
