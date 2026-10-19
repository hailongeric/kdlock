/*
 * KD-only direct mutex routing. Native-sized objects contain physical exclusion;
 * address-indexed auxiliary records retain the legacy scheduling queue while
 * delegation is live. No Linux object or Linux slowpath is used.
 * A native suffix (original code on the producer) still requests unlock from
 * its retained executor before any fresh admission or task-name decision.
 */
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
#include "kd_mutex.h"
#include "kd_mutex_direct.h"
#include "kd_spin_fast.h"
#include "kd_spinlock.h"
#include "utils.h"

/* Direct entry and the uncontended owner CAS stay in this file.
 * lock/mutex_calls.inc and lock/spin_calls.inc own translated nested CALL
 * admission/cleanup. Their static helpers share this translation unit so a
 * file split does not add dispatch calls or change hot-path inlining. */

/* --- module parameters ---------------------------------------------------- */

int kd_spin_jit_fail_after_nested_lock;
static int kd_jit_fail_pending_lock;
module_param_named(jit_fail_pending_lock, kd_jit_fail_pending_lock, int, 0644);
MODULE_PARM_DESC(jit_fail_pending_lock,
		 "One-shot pre-acquisition resource failure: 1=spin, 2=mutex");

static void origin_raw_spin_lock(raw_spinlock_t *lock);
static void origin_raw_spin_unlock(raw_spinlock_t *lock);
static __always_inline bool kd_mutex_trylock_fast(struct kd_mutex *lock);

/* ==========================================================================
 * Raw spinlock hooks
 * ========================================================================== */

DEFINE_PER_CPU(struct kd_spin_fast_cpu, kd_spin_fast_cpu);
EXPORT_PER_CPU_SYMBOL_GPL(kd_spin_fast_cpu);

#include "lock/mutex_calls.inc"

/* ==========================================================================
 * origin_* — original kernel lock paths (fallback when not delegating)
 * ========================================================================== */

static void origin_raw_spin_lock(raw_spinlock_t *lock)
{
	kd_spin_lock_nondelegated((kd_spinlock_t *)lock);
}

static void origin_raw_spin_unlock(raw_spinlock_t *lock)
{
	kd_spin_unlock_nondelegated((kd_spinlock_t *)lock);
}

#include "lock/spin_calls.inc"

static __always_inline bool kd_mutex_trylock_fast(struct kd_mutex *lock)
{
	return kd_mutex_outer_trylock(lock, (unsigned long)current);
}
