/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KD_MUTEX_H
#define KD_MUTEX_H

#include <linux/atomic.h>
#include <linux/build_bug.h>
#include <linux/list.h>
#include <linux/mutex.h>
#include <linux/osq_lock.h>
#include <linux/spinlock.h>

/* Owned objects are used exclusively through KD for their entire lifetime.
 * Matching Linux's layout does not permit mixing either mutex's waiters or
 * APIs. This first port targets the captured x86-64 non-RT configuration. */
#if !defined(CONFIG_X86_64) || !defined(CONFIG_MUTEX_SPIN_ON_OWNER) || \
    defined(CONFIG_PREEMPT_RT) || defined(CONFIG_DEBUG_MUTEXES) || \
    defined(CONFIG_DEBUG_LOCK_ALLOC) || defined(CONFIG_DEBUG_SPINLOCK)
#error "KD owned mutex v1 requires the captured x86-64 non-RT mutex layout"
#endif

struct kd_mutex {
	atomic_long_t owner;
	raw_spinlock_t wait_lock;
	struct optimistic_spin_queue osq;
	struct list_head wait_list;
};

static_assert(sizeof(struct kd_mutex) == 32);
static_assert(sizeof(struct kd_mutex) == sizeof(struct mutex));
static_assert(__alignof__(struct kd_mutex) == __alignof__(struct mutex));
static_assert(offsetof(struct kd_mutex, owner) == 0);
static_assert(offsetof(struct kd_mutex, wait_lock) == 8);
static_assert(offsetof(struct kd_mutex, osq) == 12);
static_assert(offsetof(struct kd_mutex, wait_list) == 16);
static_assert(offsetof(struct kd_mutex, owner) == offsetof(struct mutex, owner));
static_assert(offsetof(struct kd_mutex, wait_lock) == offsetof(struct mutex, wait_lock));
static_assert(offsetof(struct kd_mutex, osq) == offsetof(struct mutex, osq));
static_assert(offsetof(struct kd_mutex, wait_list) == offsetof(struct mutex, wait_list));

#define __KD_MUTEX_INITIALIZER(name) { \
	.owner = ATOMIC_LONG_INIT(0), \
	.wait_lock = __RAW_SPIN_LOCK_UNLOCKED(name.wait_lock), \
	.osq = OSQ_LOCK_UNLOCKED, \
	.wait_list = LIST_HEAD_INIT(name.wait_list), \
}
#define DEFINE_KD_MUTEX(name) \
	struct kd_mutex name = __KD_MUTEX_INITIALIZER(name)

void kd_mutex_init(struct kd_mutex *lock);
void kd_owned_mutex_lock_v1(struct kd_mutex *lock);
void kd_owned_mutex_unlock_v1(struct kd_mutex *lock);
/* Paired only with the outermost cookie interface, never an ordinary lock. */
void kd_owned_mutex_outer_unlock_v1(struct kd_mutex *lock);
int kd_mutex_trylock(struct kd_mutex *lock);
bool kd_mutex_is_locked(struct kd_mutex *lock);

/* The captured kernel already exports callback variables named kd_mutex_lock
 * and kd_mutex_unlock. Keep their namespace separate from these control CALLs.
 * Function-like macros also leave those callback declarations untouched. */
#define kd_mutex_lock(lock) kd_owned_mutex_lock_v1(lock)
#define kd_mutex_unlock(lock) kd_owned_mutex_unlock_v1(lock)

/* Quiescent inspection only: callers must first join all lock/unlock users.
 * The provider's separate executor/request drain must also be complete. */
bool kd_owned_mutex_is_idle(struct kd_mutex *lock);

#endif /* KD_MUTEX_H */
