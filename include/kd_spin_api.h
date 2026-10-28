/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_API_H
#define KD_SPIN_API_H

#include "kd_spin_direct.h"

/* Ordinary source calls expose an ABI1 control CALL before any acquisition
 * pin or per-CPU operation. The provider owns the native pin, while a translated
 * nested CALL can use the runtime's exact acquisition ledger. An anonymous
 * continuation needs no preparation label: contention registers it. Named
 * benchmark DIRECT shells retain their separate inline admission prefix.
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
	KD_SPIN_DIRECT_CALL(kd_spin_lock_clobber_v1, kd_spin_api_word, ""); \
	(void)0; \
})

#define kd_spin_unlock(lock) ({ \
	__auto_type kd_spin_api_arg = (lock); \
	kd_spinlock_t *kd_spin_api_word = kd_spin_api_arg; \
	KD_SPIN_DIRECT_CALL(kd_spin_unlock_clobber_v1, kd_spin_api_word, ""); \
	(void)0; \
})

#endif /* KD_SPIN_API_H */
