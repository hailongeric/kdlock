/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_API_H
#define KD_MUTEX_API_H

#include <linux/cleanup.h>
#include "kd_mutex_direct.h"

/*
 * Capture each call site's continuation through the existing two-word ABI2
 * wrapper. No caller cookie or named assembler label is required. DIRECT's
 * provider keeps the bounded physical fast path and exact nested CALL ledger.
 * A void expression also permits native-style comma expressions and returns.
 */
#define kd_mutex_lock(lock) ({ \
	KD_MUTEX_DIRECT_LOCK((lock), ""); \
	(void)0; \
})
#define kd_mutex_unlock(lock) ({ \
	KD_MUTEX_DIRECT_UNLOCK((lock)); \
	(void)0; \
})
/* Signalable entries use the common retained admission engine. Their Native
 * return keeps -EINTR, while the compiler-owned captured entry defines zero. */
#define kd_mutex_lock_interruptible(lock) \
	KD_LOCK_DIRECT_RESULT_CALL(kd_mutex_lock_interruptible_clobber_v1, \
		struct kd_mutex, (lock), "")
#define kd_mutex_lock_killable(lock) \
	KD_LOCK_DIRECT_RESULT_CALL(kd_mutex_lock_killable_clobber_v1, \
		struct kd_mutex, (lock), "")

/* Match the supported non-lockdep native configuration: annotations are not
 * evaluated. Distinct-object nesting is handled by DIRECT's existing protocol;
 * recursive acquisition of the same object remains invalid. */
#define kd_mutex_lock_nested(lock, subclass) kd_mutex_lock(lock)
#define kd_mutex_lock_nest_lock(lock, nest) kd_mutex_lock(lock)
#define kd_mutex_lock_interruptible_nested(lock, subclass) \
	kd_mutex_lock_interruptible(lock)
#define kd_mutex_lock_killable_nested(lock, subclass) kd_mutex_lock_killable(lock)
#define kd_mutex_lock_io_nested(lock, subclass) kd_mutex_lock_io(lock)

struct device;

/* The supported native !DEBUG_MUTEXES configuration has no devres destructor.
 * Keep the same evaluation order and return value without allocating a record. */
static inline int __kd_devm_mutex_init(struct device *dev, struct kd_mutex *lock)
{
	(void)dev;
	(void)lock;
	return 0;
}

#define __KD_DEVM_MUTEX_INIT(dev, mutex, captured) ({ \
	__auto_type captured = (mutex); \
	kd_mutex_init(captured); \
	__kd_devm_mutex_init((dev), captured); \
})
#define kd_devm_mutex_init(dev, mutex) \
	__KD_DEVM_MUTEX_INIT(dev, mutex, __UNIQUE_ID(__kd_devm_lock))

/* A cleanup constructor is an ordinary C function boundary: do not capture a
 * delegatable continuation inside a helper which returns before the section.
 * Parentheses select the local C acquisition and exact routed C unlock. */
DEFINE_GUARD(kd_mutex, struct kd_mutex *, (kd_mutex_lock)(_T),
	     (kd_mutex_unlock)(_T))
DEFINE_FREE(kd_mutex, struct kd_mutex *, if (_T) (kd_mutex_unlock)(_T))

#endif /* KD_MUTEX_API_H */
