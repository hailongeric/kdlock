#ifndef KD_LOCK_H
#define KD_LOCK_H

#include "kd_regs.h"
/*
 * kd_lock.h — kdlock hook declarations.
 *
 * Task acquisition references and translated spin/owned-mutex controls.
 * kd_lock.c owns the dispatch translation unit; no global hooks are installed.
 */

#include <linux/spinlock.h>
#include <linux/mutex.h>

struct kd_exec_frame;
struct task_struct;

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
/* Known-call handlers used by the high-lock JIT continuation path. */
struct kd_mutex;
int kd_owned_mutex_jit_nested_lock_ctx(struct kd_mutex *, struct kd_regs *,
				      struct kd_exec_frame *);
int kd_owned_mutex_jit_nested_unlock_ctx(struct kd_mutex *,
					struct kd_exec_frame *);
int kd_owned_mutex_jit_abort_cleanup(struct kd_exec_frame *);


#endif /* KD_LOCK_H */
