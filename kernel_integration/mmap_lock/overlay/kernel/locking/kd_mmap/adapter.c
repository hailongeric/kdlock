// SPDX-License-Identifier: GPL-2.0
#include <linux/init.h>
#include <linux/kd_mmap_lock.h>
#include <linux/module.h>
#include <linux/sched.h>
#include "kd_mmap_rwsem.h"

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
	pr_info("KD mmap_lock: %s; local readers; typed body delegation requires per-mm opt-in\n",
		kd_mmap_enabled ? "KD_LOCAL" : "NATIVE_CONTROL");
	return 0;
}
late_initcall(kd_mmap_report);

void kd_mmap_init(struct kd_mmap_lock *lock)
{
	lock->use_kd = kd_mmap_enabled;
	lock->body_enabled = lock->body_native_only = false;
	lock->body_calls = lock->body_supported = lock->body_delegated = 0;
	lock->body_handbacks = lock->body_native = lock->body_post_ban = 0;
	lock->body_cancelled = lock->body_acks = 0;
	kd_mmap_fault_init(lock);
	kd_mmap_unmap_init(lock);
	if (lock->use_kd)
		kd_mmap_rwsem_init(&lock->kd);
	else
		init_rwsem(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_init);

void kd_mmap_destroy(struct kd_mmap_lock *lock)
{
	/* mm_count and transferred read references have reached their final
	 * release. A residual reservation or waiter must never be freed. */
	if (lock->use_kd)
		BUG_ON(!kd_mmap_rwsem_is_idle(&lock->kd) || !kd_mmap_fault_idle(lock) ||
		       READ_ONCE(lock->unmap.tail));
}

void kd_mmap_write_lock(struct kd_mmap_lock *lock)
{
	if (lock->use_kd)
		kd_mmap_down_write(&lock->kd);
	else
		down_write(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_lock);

void kd_mmap_write_lock_nested(struct kd_mmap_lock *lock, int subclass)
{
	/* Kconfig excludes lockdep; different mm objects still acquire distinct
	 * physical owners, and the local primitive rejects recursive ownership. */
	if (lock->use_kd)
		kd_mmap_down_write(&lock->kd);
	else
		down_write_nested(&lock->native, subclass);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_lock_nested);

int kd_mmap_write_lock_killable(struct kd_mmap_lock *lock)
{
	return lock->use_kd ? kd_mmap_down_write_killable(&lock->kd) :
		down_write_killable(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_lock_killable);

int kd_mmap_write_trylock(struct kd_mmap_lock *lock)
{
	return lock->use_kd ? kd_mmap_down_write_trylock(&lock->kd) :
		down_write_trylock(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_trylock);

void kd_mmap_write_unlock(struct kd_mmap_lock *lock)
{
	if (lock->use_kd)
		kd_mmap_up_write(&lock->kd);
	else
		up_write(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_unlock);

void kd_mmap_write_downgrade(struct kd_mmap_lock *lock)
{
	if (lock->use_kd)
		kd_mmap_downgrade_write(&lock->kd);
	else
		downgrade_write(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_write_downgrade);

void kd_mmap_read_lock(struct kd_mmap_lock *lock)
{
	if (lock->use_kd)
		kd_mmap_down_read(&lock->kd);
	else
		down_read(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_read_lock);

int kd_mmap_read_lock_killable(struct kd_mmap_lock *lock)
{
	return lock->use_kd ? kd_mmap_down_read_killable(&lock->kd) :
		down_read_killable(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_read_lock_killable);

int kd_mmap_read_trylock(struct kd_mmap_lock *lock)
{
	/* KD's speculative reader rollback can wake a draining writer. BPF's
	 * IRQ-disabled lookup already has an explicit trylock-failure fallback;
	 * choose that before any reservation, rather than waking under rq_lock.
	 * This does not acquire the Native backend of a KD mm. */
	if (lock->use_kd && irqs_disabled())
		return 0;
	return lock->use_kd ? kd_mmap_down_read_trylock(&lock->kd) :
		down_read_trylock(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_read_trylock);

void kd_mmap_read_unlock(struct kd_mmap_lock *lock)
{
	if (lock->use_kd) {
		BUG_ON(atomic_long_read(&lock->kd.readers) <= 0);
		kd_mmap_up_read(&lock->kd);
	} else {
		up_read(&lock->native);
	}
}
EXPORT_SYMBOL_GPL(kd_mmap_read_unlock);

void kd_mmap_read_unlock_non_owner(struct kd_mmap_lock *lock)
{
	/* The in-tree asynchronous caller consumes its retained mm record before
	 * this release. That record, not the reader count, authorizes the transfer. */
	if (lock->use_kd)
		kd_mmap_read_unlock(lock);
	else
		up_read_non_owner(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_read_unlock_non_owner);

bool kd_mmap_is_locked(struct kd_mmap_lock *lock)
{
	return lock->use_kd ? atomic_long_read(&lock->kd.readers) ||
		atomic_long_read(&lock->kd.admission) : rwsem_is_locked(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_is_locked);

bool kd_mmap_is_write_owner(struct kd_mmap_lock *lock)
{
	unsigned long owner;

	if (!lock->use_kd)
		return rwsem_is_locked(&lock->native);
	owner = atomic_long_read(&lock->kd.gate.owner);
	return atomic_long_read(&lock->kd.admission) == -1 && !(owner & 4UL) &&
		((owner & ~7UL) == (unsigned long)current || kd_mmap_body_write_owned(lock));
}
EXPORT_SYMBOL_GPL(kd_mmap_is_write_owner);

bool kd_mmap_is_contended(struct kd_mmap_lock *lock)
{
	/* Observation only; neither queue presence nor absence grants ownership. */
	return lock->use_kd ? waitqueue_active(&lock->kd.phase_wait) ||
		waitqueue_active(&lock->kd.reader_drain) || READ_ONCE(lock->kd.gate.wait_head) :
		rwsem_is_contended(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_is_contended);

bool kd_mmap_is_idle(struct kd_mmap_lock *lock)
{
	/* Stopped/joined users only; includes exact reserved CPU-slot records. */
	return lock->use_kd ? kd_mmap_rwsem_is_idle(&lock->kd) && kd_mmap_fault_idle(lock) &&
		!READ_ONCE(lock->unmap.tail) :
		!rwsem_is_locked(&lock->native);
}
EXPORT_SYMBOL_GPL(kd_mmap_is_idle);
