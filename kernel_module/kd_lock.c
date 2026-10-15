/* Spin and owned-mutex translated control calls. No global hooks. */
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/spinlock.h>

#include "exe.h"
#include "kd_exec.h"
#include "kd_hotlock.h"
#include "kd_source.h"
#include "kd_comm.h"

/* Mutex task selection remains active independently of spin dispatch. */
extern struct kd_comm_key kd_spin_target;
#include "kd_lock.h"
#include "kd_owned_mutex_internal.h"
#include "kd_spin_fast.h"
#include "kd_spinlock.h"
#include "utils.h"

int kd_spin_jit_fail_after_nested_lock;
static int kd_jit_fail_pending_lock;
module_param_named(jit_fail_pending_lock, kd_jit_fail_pending_lock, int, 0644);
MODULE_PARM_DESC(jit_fail_pending_lock,
		 "One-shot pre-acquisition resource failure: 1=spin, 2=mutex");

static void origin_raw_spin_lock(raw_spinlock_t *lock);
static void origin_raw_spin_unlock(raw_spinlock_t *lock);

DEFINE_PER_CPU(struct kd_spin_fast_cpu, kd_spin_fast_cpu);
EXPORT_PER_CPU_SYMBOL_GPL(kd_spin_fast_cpu);

/* Shared checked CALL capture and continuation advancement. */
static int kd_jit_begin_call(struct kd_exec_frame *frame, struct kd_regs *regs)
{
	if (!frame || !regs || !regs->sp || !kd_exec_frame_validate(frame))
		return -EINVAL;
	return kd_call_begin(&frame->control_call, regs->ip, regs->sp,
			     READ_ONCE(*(unsigned long *)regs->sp));
}

static int kd_jit_advance_call(struct kd_exec_frame *frame,
			       struct kd_regs *regs)
{
	unsigned long return_ip;

	if (!frame || !regs || !regs->sp)
		return -EINVAL;
	return_ip = READ_ONCE(*(unsigned long *)regs->sp);
	if (!return_ip)
		return -EINVAL;
	regs->sp += sizeof(unsigned long);
	regs->ip = return_ip;
	kd_exec_frame_save_continuation(frame, regs);
	return 0;
}

#include "lock/owned_mutex_calls.inc"

static void origin_raw_spin_lock(raw_spinlock_t *lock)
{
	kd_spin_lock_nondelegated((kd_spinlock_t *)lock);
}

static void origin_raw_spin_unlock(raw_spinlock_t *lock)
{
	kd_spin_unlock_nondelegated((kd_spinlock_t *)lock);
}

#include "lock/spin_calls.inc"
