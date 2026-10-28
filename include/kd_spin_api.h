/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_API_H
#define KD_SPIN_API_H

#include "kd_spin_direct.h"

/* Ordinary source calls use the same compiler-owned ABI1 spill boundary as
 * the named DIRECT shell. An anonymous continuation needs no preparation
 * label: the provider registers it on the contended path. Keep benchmark
 * continuations in DIRECT; both interfaces share its admission and unlock.
 *
 * Capture the expression before DIRECT declares its private temporaries.
 * __auto_type also keeps a same-named caller variable visible in its own
 * initializer. The typed pointer retains the KD-object type check.
 * These are source macros, not addressable C functions: a conventional helper
 * must state its own execution contract before capturing a continuation.
 */
#define kd_spin_lock(lock) ({ \
	__auto_type kd_spin_api_arg = (lock); \
	kd_spinlock_t *kd_spin_api_word = kd_spin_api_arg; \
	KD_SPIN_DIRECT_LOCK(kd_spin_api_word, kd_spin_direct_cookie, ""); \
	(void)0; \
})

#define kd_spin_unlock(lock) ({ \
	__auto_type kd_spin_api_arg = (lock); \
	kd_spinlock_t *kd_spin_api_word = kd_spin_api_arg; \
	KD_SPIN_DIRECT_UNLOCK(kd_spin_api_word, kd_spin_direct_cookie); \
	(void)0; \
})

#endif /* KD_SPIN_API_H */
