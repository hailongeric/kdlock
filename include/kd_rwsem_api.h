/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_API_H
#define KD_RWSEM_API_H

#include <linux/cleanup.h>
#include "kd_rwsem.h"
#include "kd_mutex_direct.h"

/* Quiescent preparation is an object-wide promise for ordinary macro writers:
 * same-task lexical acquire/release, no downgrade and no translated nesting.
 * Callable/signal/try/cleanup writer acquisitions remain local and can downgrade.
 * Never race preparation/reinitialization with any participant. */
int kd_rwsem_prepare(struct kd_rwsem *sem, unsigned long ip, unsigned int abi);
void kd_rwsem_down_write_clobber_v1(struct kd_rwsem *sem, unsigned long sp,
                                   unsigned long ip, unsigned long bp);

#define kd_down_write(sem) ({ \
	__auto_type kd_rw_arg = (sem); \
	struct kd_rwsem *kd_rw_sem = kd_rw_arg; \
	unsigned long kd_sp, kd_ip, kd_bp; \
	asm volatile("movq %%rsp, %%rsi\n\t" \
	             "leaq 1f(%%rip), %%rdx\n\t" \
	             "movq %%rbp, %%rcx\n\t" \
	             "call kd_rwsem_down_write_clobber_v1\n\t1:\n\t" \
	             : "+D"(kd_rw_sem), "=S"(kd_sp), "=d"(kd_ip), "=c"(kd_bp), \
	               ASM_CALL_CONSTRAINT \
	             : \
	             : "rax", "rbx", "r8", "r9", "r10", "r11", \
	               "r12", "r13", "r14", "r15", "cc", "memory"); \
	(void)0; \
})

#define kd_up_write(sem) ({ \
	__auto_type kd_rw_arg = (sem); \
	struct kd_rwsem *kd_rw_sem = kd_rw_arg; \
	/* JIT terminates at the mutex endpoint. Only the resumed origin reaches \
	 * the phase release, after exact physical ownership and unlock ACK. */ \
	KD_MUTEX_DIRECT_UNLOCK(&kd_rw_sem->gate); \
	kd_rwsem_write_release(kd_rw_sem); \
	(void)0; \
})

/* Non-lockdep annotations are intentionally not evaluated, matching Native. */
#define kd_down_read_nested(sem, subclass) kd_down_read(sem)
#define kd_down_read_killable_nested(sem, subclass) kd_down_read_killable(sem)
#define kd_down_write_nested(sem, subclass) kd_down_write(sem)
#define kd_down_write_killable_nested(sem, subclass) kd_down_write_killable(sem)
#define kd_down_write_nest_lock(sem, nest) kd_down_write(sem)

/* Constructors return before their user's body, so they use callable local
 * acquisitions. The same public unlock routes every successful acquisition. */
DEFINE_LOCK_GUARD_1(kd_rwsem_read, struct kd_rwsem,
                    kd_down_read(_T->lock), kd_up_read(_T->lock))
DEFINE_LOCK_GUARD_1_COND(kd_rwsem_read, _try, kd_down_read_trylock(_T->lock))
DEFINE_LOCK_GUARD_1_COND(kd_rwsem_read, _intr,
                         kd_down_read_interruptible(_T->lock), _RET == 0)
DEFINE_LOCK_GUARD_1(kd_rwsem_write, struct kd_rwsem,
                    (kd_down_write)(_T->lock), (kd_up_write)(_T->lock))
DEFINE_LOCK_GUARD_1_COND(kd_rwsem_write, _try, kd_down_write_trylock(_T->lock))
DEFINE_LOCK_GUARD_1_COND(kd_rwsem_write, _kill,
                         kd_down_write_killable(_T->lock), _RET == 0)

DEFINE_LOCK_GUARD_1(kd_rwsem_init, struct kd_rwsem, kd_init_rwsem(_T->lock), /* */)

#endif /* KD_RWSEM_API_H */
