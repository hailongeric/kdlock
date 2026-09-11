#ifndef KD_LOCK_H
#define KD_LOCK_H

/*
 * kd_lock.h — kdlock hook declarations.
 *
 * These are the function signatures the patched kernel calls on every
 * spinlock and mutex operation for the target process.  The module
 * installs its implementations (kd_lock.c) during init and clears them
 * during exit.
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
bool kd_origin_mutex_owned(struct mutex *lock, struct task_struct *task);

bool kd_mutex_task_active(struct task_struct *task);
bool kd_mutex_task_reroute(struct task_struct *task);
bool kd_mutex_task_get(struct task_struct *task);
void kd_mutex_task_put(struct task_struct *task);
void kd_mutex_tasks_exit(void);
bool kd_mutex_tasks_idle(void);
#ifdef KDLOCK_SELFTEST
int kd_mutex_task_selftest(void);
#endif
/* --- preemption helpers --------------------------------------------------- */

static inline void kd_preempt_disable_raw_spin_lock(raw_spinlock_t *lock)
{
	spin_acquire(&lock->dep_map, 0, 0, _RET_IP_);
	LOCK_CONTENDED(lock, do_raw_spin_trylock, do_raw_spin_lock);
}

static __always_inline void kd_preempt_disable_spin_lock(spinlock_t *lock)
{
	kd_preempt_disable_raw_spin_lock(&lock->rlock);
}

/* --- raw spinlock hooks --------------------------------------------------- */

void __kd_raw_spin_lock(raw_spinlock_t *lock, unsigned long ret_rsp,
			unsigned long ret_addr);
void __kd_raw_spin_unlock(raw_spinlock_t *lock, unsigned long ret_rsp,
			  unsigned long ret_addr);

/* --- mutex hooks ---------------------------------------------------------- */

void __kd_mutex_lock(struct mutex *lock, unsigned long ret_rsp,
		     unsigned long ret_addr);
void __kd_mutex_unlock(struct mutex *lock, unsigned long ret_rsp,
		       unsigned long ret_addr);

/* Known-call handlers used by the high-lock JIT continuation path. */
int kd_mutex_jit_nested_lock_ctx(struct mutex *lock, struct pt_regs *regs,
				 struct kd_exec_frame *frame);
int kd_mutex_jit_nested_unlock_ctx(struct mutex *lock,
				   struct kd_exec_frame *frame);
int kd_mutex_jit_abort_cleanup(struct kd_exec_frame *frame);
int kd_mutex_debug_waiter_count(struct mutex *lock);

#endif /* KD_LOCK_H */
