/*
 * kd_lock.c — kdlock hook implementations.
 *
 * This file implements the hook callbacks that the patched kernel calls on
 * ordinary spinlock and mutex operations before target-process selection:
 *
 *   Spin callers use the explicit kd_spin_lock_abi() API.
 *
 *   Mutex:        __kd_mutex_lock  → _kd_mutex_lock()   (kd_mutex.c)
 *                 __kd_mutex_unlock → _kd_mutex_unlock()
 *
 * Each struct mutex * is mapped to a struct kd_mutex * via the shadow table.
 * The origin_* functions provide fallback to the original kernel lock paths.
 * The shadow entry schedules work alongside the original mutex, not instead
 * of it. A native suffix's unlock is routed to its retained physical owner
 * before target-name or fresh-admission decisions can bypass that routing.
 */
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/hash.h>
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

/* Hook entry, native fast paths and the mutex shadow map stay in this file.
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
static __always_inline bool kd_mutex_trylock_fast(struct mutex *lock);

/* --- mutex → kd_mutex shadow table ---------------------------------------- */

#define KD_MUTEX_SHADOW_BITS 10
#define KD_MUTEX_SHADOW_TABLE_SIZE (1 << KD_MUTEX_SHADOW_BITS)

/* The initialized original address is also the immutable map key. */
struct kd_mutex_shadow_entry {
	struct kd_mutex kd_mtx;
} ____cacheline_aligned;

static struct kd_mutex_shadow_entry kd_mutex_shadows[KD_MUTEX_SHADOW_TABLE_SIZE];
/* Initialize before any direct caller or component selftest can publish a key.
 * Keys never move or disappear; a published exact address pins this gate slot
 * until provider teardown. Full capacity keeps using the native mutex. */
void kd_mutex_shadows_init(void)
{
	unsigned int i;

	BUILD_BUG_ON(sizeof(struct kd_mutex_shadow_entry) != L1_CACHE_BYTES);
	for (i = 0; i < KD_MUTEX_SHADOW_TABLE_SIZE; i++)
		kd_mutex_init(&kd_mutex_shadows[i].kd_mtx);
}

/* --- externs from patched kernel ------------------------------------------ */

extern void __mutex_lock_slowpath(struct mutex *lock);
extern void __mutex_unlock_slowpath(struct mutex *lock, unsigned long ip);

/* --- mutex shadow table lookup -------------------------------------------- */

static struct kd_mutex *get_kd_mutex_shadow(struct mutex *lock)
{
	unsigned long key = (unsigned long)lock;
	unsigned int pos = hash_long(key, KD_MUTEX_SHADOW_BITS), probes;

	for (probes = 0; probes < KD_MUTEX_SHADOW_TABLE_SIZE; probes++) {
		struct kd_mutex *gate = &kd_mutex_shadows[pos].kd_mtx;
		unsigned long seen = smp_load_acquire(&gate->origin_mutex_addr);

		if (!seen)
			/* All gate fields were initialized before module publication.
			 * cmpxchg orders a winning key and observes a racing winner;
			 * never reinitialize storage another caller may already own. */
			seen = cmpxchg(&gate->origin_mutex_addr, 0UL, key);
		if (!seen || seen == key)
			return gate;
		pos = (pos + 1) & (KD_MUTEX_SHADOW_TABLE_SIZE - 1);
	}
	KD_PR_ERR("kd mutex shadow table is full\n");
	return NULL;
}

static struct kd_mutex *find_kd_mutex_shadow(struct mutex *lock)
{
	unsigned long key = (unsigned long)lock;
	unsigned int pos = hash_long(key, KD_MUTEX_SHADOW_BITS), probes;

	for (probes = 0; probes < KD_MUTEX_SHADOW_TABLE_SIZE; probes++) {
		struct kd_mutex *gate = &kd_mutex_shadows[pos].kd_mtx;
		unsigned long seen = smp_load_acquire(&gate->origin_mutex_addr);

		if (seen == key)
			return gate;
		if (!seen)
			return NULL;
		pos = (pos + 1) & (KD_MUTEX_SHADOW_TABLE_SIZE - 1);
	}
	return NULL;
}

#ifdef KDLOCK_SELFTEST
/* Read-only capacity evidence; no test may manufacture table membership. */
#include "../tests/kernel/mutex/mutex_shadow_trace.c"
#endif

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

static __always_inline bool kd_mutex_trylock_fast(struct mutex *lock)
{
	unsigned long curr = (unsigned long)current;
	unsigned long zero = 0UL;
	return atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, curr);
}

static __always_inline bool kd_mutex_unlock_fast(struct mutex *lock)
{
	unsigned long curr = (unsigned long)current;
	return atomic_long_try_cmpxchg_release(&lock->owner, &curr, 0UL);
}

void kd_origin_mutex_lock(struct mutex *lock)
{
	might_sleep();
	BUG_ON(kd_origin_mutex_owned(lock, current));
	if (!kd_mutex_trylock_fast(lock))
		__mutex_lock_slowpath(lock);
}

void kd_origin_mutex_unlock(struct mutex *lock, unsigned long ret_addr)
{
	BUG_ON(!kd_origin_mutex_owned(lock, current));
#ifndef CONFIG_DEBUG_LOCK_ALLOC
	if (kd_mutex_unlock_fast(lock))
		return;
#endif
	__mutex_unlock_slowpath(lock, ret_addr);
}
