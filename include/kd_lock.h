#ifndef KD_LOCK_H
#define KD_LOCK_H

#include "kd_regs.h"
/*
 * kd_lock.h — kdlock hook declarations.
 *
 * Entry signatures installed by kd_main.c into the clobber kernel. Mutex
 * selectors preserve active-owner routing; fresh spin/mutex hooks check
 * CPU/local-lock frequency before task selection. kd_lock.c owns entry
 * handling; kernel_module/lock/ owns translated nested CALL handling.
 *
 * The inline helpers preserve lockdep accounting for native fallback paths.
 */

#include <linux/spinlock.h>
#include <linux/mutex.h>

struct kd_exec_frame;
struct task_struct;

/* Existing guest exports implement the contended paths, without hook reentry. */
void kd_origin_mutex_lock(struct mutex *lock);
void kd_origin_mutex_unlock(struct mutex *lock, unsigned long ip);
/* Both entry and retirement check the authoritative Linux owner, including
 * the same flag mask. Keep this tiny read inline in every delegated body. */
#define KD_MUTEX_OWNER_FLAGS 0x7UL
static __always_inline bool
kd_origin_mutex_owned(struct mutex *lock, struct task_struct *task)
{
	return (atomic_long_read(&lock->owner) & ~KD_MUTEX_OWNER_FLAGS) ==
	       (unsigned long)task;
}

bool kd_mutex_task_active(struct task_struct *task);
bool kd_mutex_task_reroute(struct task_struct *task);
bool kd_mutex_task_get(struct task_struct *task);
void kd_mutex_task_put(struct task_struct *task);
void kd_owned_mutex_task_enter(void);
void kd_owned_mutex_task_leave(void);
bool kd_owned_mutex_task_can_combine(void);
void kd_mutex_tasks_exit(void);
bool kd_mutex_tasks_idle(void);
#ifdef KDLOCK_SELFTEST
int kd_mutex_task_selftest(void);
#endif
/* --- mutex hooks ---------------------------------------------------------- */

void __kd_mutex_lock(struct mutex *lock, unsigned long ret_rsp,
		     unsigned long ret_addr);
void __kd_mutex_unlock(struct mutex *lock, unsigned long ret_rsp,
		       unsigned long ret_addr);
void __kd_mutex_lock_clobber_v1(struct mutex *, unsigned long, unsigned long,
				unsigned long);
void __kd_mutex_unlock_clobber_v1(struct mutex *, unsigned long, unsigned long,
				  unsigned long);

/* Known-call handlers used by the high-lock JIT continuation path. */
struct kd_mutex;
int kd_owned_mutex_jit_nested_lock_ctx(struct kd_mutex *, struct kd_regs *,
				      struct kd_exec_frame *);
int kd_owned_mutex_jit_nested_unlock_ctx(struct kd_mutex *,
					struct kd_exec_frame *);
int kd_owned_mutex_jit_abort_cleanup(struct kd_exec_frame *);
int kd_mutex_jit_nested_lock_ctx(struct mutex *lock, struct kd_regs *regs,
				 struct kd_exec_frame *frame);
int kd_mutex_jit_nested_unlock_ctx(struct mutex *lock,
				   struct kd_exec_frame *frame);
int kd_mutex_jit_abort_cleanup(struct kd_exec_frame *frame);
int kd_mutex_debug_waiter_count(struct mutex *lock);


#endif /* KD_LOCK_H */
