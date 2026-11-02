// SPDX-License-Identifier: GPL-2.0
#include <linux/init.h>
#define KD_RWSEM_FACADE_IMPLEMENTATION
#include <linux/kd_mmap_lock.h>
#include <linux/module.h>
#include <linux/sched.h>
#include "kd_mmap_rwsem.h"

/* Keep the invocation reference through callback return. Unlock may permit
 * object destruction, so the saved owner is never recovered from the object. */
#define KD_PROVIDER_VOID(ops, method, object) do { \
	struct module *kd_owner = (ops)->owner; \
	__module_get(kd_owner); \
	(ops)->method(object); \
	module_put(kd_owner); \
} while (0)
#define KD_PROVIDER_RESULT(ops, method, object) ({ \
	struct module *kd_owner = (ops)->owner; \
	__module_get(kd_owner); \
	__auto_type kd_result = (ops)->method(object); \
	module_put(kd_owner); \
	kd_result; \
})

/* Never changed after boot. Each mm retains its choice even if future boot
 * policy is extended; the union is initialized before publication. */
static bool kd_mmap_enabled __ro_after_init;

static int __init kd_mmap_setup(char *value)
{
	if (!value || kstrtobool(value, &kd_mmap_enabled))
		return -EINVAL;
	return 0;
}
early_param("kd_mmap", kd_mmap_setup);

static int __init kd_mmap_report(void)
{
	pr_info("KD mmap_lock: %s; immutable provider binding at object initialization\n",
		kd_mmap_enabled ? "KD_LOCAL" : "NATIVE_CONTROL");
	return 0;
}
late_initcall(kd_mmap_report);

void kd_mmap_init(struct kd_mmap_lock *lock)
{
	lock->use_kd = kd_mmap_enabled;
	lock->initialized = false;
	/* dup_mm may have copied another object's pointer. It is not our
	 * reference: overwrite it without putting the source object's binding. */
	lock->provider = NULL;
	if (lock->use_kd) {
		lock->provider = kd_rwsem_bind_provider();
		if (lock->provider)
			KD_PROVIDER_VOID(lock->provider, init, &lock->kd);
		else
			kd_mmap_rwsem_init(&lock->kd);
	} else {
		init_rwsem(&lock->native);
	}
	lock->initialized = true;
}
EXPORT_SYMBOL_GPL(kd_mmap_init);

void kd_mmap_destroy(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	/* mm_count and transferred read references have reached their final
	 * release. A residual reservation or waiter must never be freed. */
	BUG_ON(!lock->initialized);
	lock->initialized = false;
	lock->provider = NULL;
	if (ops) {
		KD_PROVIDER_VOID(ops, destroy, &lock->kd);
		kd_rwsem_unbind_provider(ops);
	} else if (lock->use_kd) {
		BUG_ON(!kd_mmap_rwsem_is_idle(&lock->kd));
	}
}

void kd_mmap_write_lock(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		KD_PROVIDER_VOID(ops, down_write, &lock->kd);
	else if (lock->use_kd)
		kd_mmap_down_write(&lock->kd);
	else
		down_write(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_lock);

void kd_mmap_write_lock_nested(struct kd_mmap_lock *lock, int subclass)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	/* Kconfig excludes lockdep; different mm objects still acquire distinct
	 * physical owners, and the local primitive rejects recursive ownership. */
	if (ops)
		KD_PROVIDER_VOID(ops, down_write, &lock->kd);
	else if (lock->use_kd)
		kd_mmap_down_write(&lock->kd);
	else
		down_write_nested(&lock->native, subclass);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_lock_nested);

int kd_mmap_write_lock_killable(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		return KD_PROVIDER_RESULT(ops, down_write_killable, &lock->kd);
	return lock->use_kd ? kd_mmap_down_write_killable(&lock->kd) :
		down_write_killable(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_lock_killable);

int kd_mmap_write_trylock(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		return KD_PROVIDER_RESULT(ops, down_write_trylock, &lock->kd);
	return lock->use_kd ? kd_mmap_down_write_trylock(&lock->kd) :
		down_write_trylock(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_trylock);

void kd_mmap_write_unlock(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		KD_PROVIDER_VOID(ops, up_write, &lock->kd);
	else if (lock->use_kd)
		kd_mmap_up_write(&lock->kd);
	else
		up_write(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_unlock);

void kd_mmap_write_downgrade(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		KD_PROVIDER_VOID(ops, downgrade_write, &lock->kd);
	else if (lock->use_kd)
		kd_mmap_downgrade_write(&lock->kd);
	else
		downgrade_write(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_downgrade);

void kd_mmap_read_lock(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		KD_PROVIDER_VOID(ops, down_read, &lock->kd);
	else if (lock->use_kd)
		kd_mmap_down_read(&lock->kd);
	else
		down_read(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_read_lock);

int kd_mmap_read_lock_killable(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		return KD_PROVIDER_RESULT(ops, down_read_killable, &lock->kd);
	return lock->use_kd ? kd_mmap_down_read_killable(&lock->kd) :
		down_read_killable(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_read_lock_killable);

int kd_mmap_read_trylock(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		return KD_PROVIDER_RESULT(ops, down_read_trylock, &lock->kd);
	/* The shared primitive also supports atomic speculation/rollback. The
	 * matching read unlock leaves IRQ and preemption state unchanged. */
	return lock->use_kd ? kd_mmap_down_read_trylock(&lock->kd) :
		down_read_trylock(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_read_trylock);

void kd_mmap_read_unlock(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops) {
		KD_PROVIDER_VOID(ops, up_read, &lock->kd);
	} else if (lock->use_kd) {
		BUG_ON(atomic_long_read(&lock->kd.readers) <= 0);
		kd_mmap_up_read(&lock->kd);
	} else {
		up_read(&lock->native);
	}
}
EXPORT_SYMBOL_GPL(kd_mmap_read_unlock);

void kd_mmap_read_unlock_non_owner(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	/* The in-tree asynchronous caller consumes its retained mm record before
	 * this release. That record, not the reader count, authorizes the transfer. */
	if (ops)
		KD_PROVIDER_VOID(ops, up_read_non_owner, &lock->kd);
	else if (lock->use_kd)
		kd_mmap_read_unlock(lock);
	else
		up_read_non_owner(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_read_unlock_non_owner);

bool kd_mmap_is_locked(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		return KD_PROVIDER_RESULT(ops, is_locked, &lock->kd);
	return lock->use_kd ? atomic_long_read(&lock->kd.readers) ||
		atomic_long_read(&lock->kd.admission) : rwsem_is_locked(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_is_locked);

bool kd_mmap_is_write_owner(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;
	unsigned long owner;

	if (ops) {
		struct module *provider_owner = ops->owner;
		bool owned;

		__module_get(provider_owner);
		owned = ops->write_owned(&lock->kd, current);
		module_put(provider_owner);
		return owned;
	}
	if (!lock->use_kd)
		return rwsem_is_locked(&lock->native);
	owner = atomic_long_read(&lock->kd.gate.owner);
	return atomic_long_read(&lock->kd.admission) == -1 && !(owner & 4UL) &&
		(owner & ~7UL) == (unsigned long)current;
}
EXPORT_SYMBOL_GPL(kd_mmap_is_write_owner);

bool kd_mmap_is_contended(struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		return KD_PROVIDER_RESULT(ops, is_contended, &lock->kd);
	/* Observation only; neither queue presence nor absence grants ownership. */
	return lock->use_kd ? kd_mmap_rwsem_condition_active(&lock->kd.phase_wait) ||
		kd_mmap_rwsem_condition_active(&lock->kd.reader_drain) || READ_ONCE(lock->kd.gate.wait_head) :
		rwsem_is_contended(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_is_contended);

/* Linux 7's per-VMA wrappers assert through a const mm. Keep the native
 * assertion semantics and check the KD writer's exact physical ownership. */
void kd_mmap_assert_held(const struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops)
		KD_PROVIDER_VOID(ops, assert_held, &lock->kd);
	else if (lock->use_kd)
		WARN_ON(!atomic_long_read(&lock->kd.readers) &&
			!atomic_long_read(&lock->kd.admission));
	else
		rwsem_assert_held(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_assert_held);

void kd_mmap_assert_held_write(const struct kd_mmap_lock *lock)
{
	const struct kd_rwsem_provider *ops = lock->provider;
	unsigned long owner;

	if (ops) {
		KD_PROVIDER_VOID(ops, assert_held_write, &lock->kd);
		return;
	}
	if (!lock->use_kd) {
		rwsem_assert_held_write(&lock->native);
		return;
	}
	owner = atomic_long_read(&lock->kd.gate.owner);
	WARN_ON(atomic_long_read(&lock->kd.admission) != -1 || (owner & 4UL) ||
		(owner & ~7UL) != (unsigned long)current);
}
EXPORT_SYMBOL_GPL(kd_mmap_assert_held_write);

/* These controls receive the real caller's three-word clobber entry. A
 * successful capture adopts the transient reference and never returns through
 * this helper frame. Cancellation returns normally and retires it here. */
__attribute__((noipa)) noinline notrace void
kd_mmap_write_lock_clobber_v1(struct kd_mmap_lock *lock, unsigned long sp,
			     unsigned long ip, unsigned long bp)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops) {
		struct module *owner = ops->owner;
		int result;

		__module_get(owner);
		result = ops->capture(&lock->kd, TASK_UNINTERRUPTIBLE, sp, ip, bp);
		module_put(owner);
		BUG_ON(result);
	} else {
		kd_mmap_write_lock(lock);
	}
}
EXPORT_SYMBOL_GPL(kd_mmap_write_lock_clobber_v1);

__attribute__((noipa)) noinline notrace int
kd_mmap_write_lock_killable_clobber_v1(struct kd_mmap_lock *lock, unsigned long sp,
				      unsigned long ip, unsigned long bp)
{
	const struct kd_rwsem_provider *ops = lock->provider;

	if (ops) {
		struct module *owner = ops->owner;
		int result;

		__module_get(owner);
		result = ops->capture(&lock->kd, TASK_KILLABLE, sp, ip, bp);
		module_put(owner);
		return result;
	}
	return kd_mmap_write_lock_killable(lock);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_lock_killable_clobber_v1);

__attribute__((noipa)) noinline notrace void
kd_mmap_write_unlock_clobber_v1(struct kd_mmap_lock *lock, unsigned long sp,
			       unsigned long ip, unsigned long bp)
{
	(void)sp;
	(void)ip;
	(void)bp;
	kd_mmap_write_unlock(lock);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_unlock_clobber_v1);

static void *kd_mmap_provider_object(void *argument,
				     const struct kd_rwsem_provider *expected)
{
	struct kd_mmap_lock *lock = argument;

	if (!lock || !expected || READ_ONCE(lock->provider) != expected ||
	    !READ_ONCE(lock->use_kd))
		return NULL;
	return &lock->kd;
}

#define KD_RWSEM_CONTROL(function, operation, flags) \
	{ (unsigned long)(function), operation, flags, kd_mmap_provider_object }
static const struct kd_rwsem_control_binding kd_mmap_controls[] = {
	KD_RWSEM_CONTROL(kd_mmap_write_lock, KD_RWSEM_OP_DOWN_WRITE, 0),
	KD_RWSEM_CONTROL(kd_mmap_write_lock_nested, KD_RWSEM_OP_DOWN_WRITE, 0),
	KD_RWSEM_CONTROL(kd_mmap_write_lock_killable, KD_RWSEM_OP_DOWN_WRITE_KILLABLE,
			 KD_RWSEM_CONTROL_INTEGER),
	KD_RWSEM_CONTROL(kd_mmap_write_trylock, KD_RWSEM_OP_DOWN_WRITE_TRYLOCK,
			 KD_RWSEM_CONTROL_INTEGER),
	KD_RWSEM_CONTROL(kd_mmap_write_unlock, KD_RWSEM_OP_UP_WRITE, 0),
	KD_RWSEM_CONTROL(kd_mmap_write_downgrade, KD_RWSEM_OP_DOWNGRADE_WRITE, 0),
	KD_RWSEM_CONTROL(kd_mmap_read_lock, KD_RWSEM_OP_DOWN_READ, 0),
	KD_RWSEM_CONTROL(kd_mmap_read_lock_killable, KD_RWSEM_OP_DOWN_READ_KILLABLE,
			 KD_RWSEM_CONTROL_INTEGER),
	KD_RWSEM_CONTROL(kd_mmap_read_trylock, KD_RWSEM_OP_DOWN_READ_TRYLOCK,
			 KD_RWSEM_CONTROL_INTEGER),
	KD_RWSEM_CONTROL(kd_mmap_read_unlock, KD_RWSEM_OP_UP_READ, 0),
	KD_RWSEM_CONTROL(kd_mmap_read_unlock_non_owner, KD_RWSEM_OP_UP_READ_NON_OWNER, 0),
	KD_RWSEM_CONTROL(kd_mmap_write_lock_clobber_v1, KD_RWSEM_OP_DOWN_WRITE,
			 KD_RWSEM_CONTROL_CAPTURE),
	KD_RWSEM_CONTROL(kd_mmap_write_lock_killable_clobber_v1, KD_RWSEM_OP_DOWN_WRITE_KILLABLE,
			 KD_RWSEM_CONTROL_CAPTURE | KD_RWSEM_CONTROL_INTEGER),
	KD_RWSEM_CONTROL(kd_mmap_write_unlock_clobber_v1, KD_RWSEM_OP_UP_WRITE,
			 KD_RWSEM_CONTROL_CAPTURE),
};
#undef KD_RWSEM_CONTROL

const struct kd_rwsem_control_binding *kd_rwsem_provider_controls(unsigned int *count)
{
	*count = ARRAY_SIZE(kd_mmap_controls);
	return kd_mmap_controls;
}
EXPORT_SYMBOL_GPL(kd_rwsem_provider_controls);
