/*
 * kd_lock.c — kdlock hook implementations.
 *
 * This file implements the hook callbacks that the patched kernel calls on
 * every spinlock and mutex operation for the target process:
 *
 *   Raw spinlock: __kd_raw_spin_lock  → kd_spin_lock()  (kd_spinlock.c)
 *                 __kd_raw_spin_unlock → kd_spin_unlock()
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
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/spinlock.h>

#include "exe.h"
#include "kd_exec.h"
#include "kd_hotlock.h"
#include "kd_lock.h"
#include "kd_mutex.h"
#include "kd_spin_fast.h"
#include "kd_spin_select.h"
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

/* --- mutex → kd_mutex shadow table ---------------------------------------- */

#define KD_MUTEX_SHADOW_TABLE_SIZE 1024

struct kd_mutex_shadow_entry {
	unsigned long mutex_addr;
	struct kd_mutex kd_mtx;
};

static struct kd_mutex_shadow_entry kd_mutex_shadows[KD_MUTEX_SHADOW_TABLE_SIZE];
static DEFINE_RAW_SPINLOCK(kd_mutex_shadow_lock);

/* --- externs from patched kernel ------------------------------------------ */

extern void __mutex_lock_slowpath(struct mutex *lock);
extern void __mutex_unlock_slowpath(struct mutex *lock, unsigned long ip);

/* --- mutex shadow table lookup -------------------------------------------- */

static struct kd_mutex *get_kd_mutex_shadow(struct mutex *lock)
{
	unsigned long flags;
	unsigned long mutex_addr = (unsigned long)lock;
	int start = mutex_addr % KD_MUTEX_SHADOW_TABLE_SIZE;
	int pos = start;

	raw_spin_lock_irqsave(&kd_mutex_shadow_lock, flags);
	do {
		if (kd_mutex_shadows[pos].mutex_addr == mutex_addr) {
			raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock,
						   flags);
			return &kd_mutex_shadows[pos].kd_mtx;
		}
		if (kd_mutex_shadows[pos].mutex_addr == 0) {
			kd_mutex_shadows[pos].mutex_addr = mutex_addr;
			kd_mutex_init(&kd_mutex_shadows[pos].kd_mtx);
			kd_mutex_shadows[pos].kd_mtx.origin_mutex_addr =
				mutex_addr;
			raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock,
						   flags);
			return &kd_mutex_shadows[pos].kd_mtx;
		}
		pos = (pos + 1) % KD_MUTEX_SHADOW_TABLE_SIZE;
	} while (pos != start);

	raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
	KD_PR_ERR("kd mutex shadow table is full\n");
	return NULL;
}

static struct kd_mutex *find_kd_mutex_shadow(struct mutex *lock)
{
	unsigned long flags;
	unsigned long mutex_addr = (unsigned long)lock;
	int start = mutex_addr % KD_MUTEX_SHADOW_TABLE_SIZE;
	int pos = start;

	raw_spin_lock_irqsave(&kd_mutex_shadow_lock, flags);
	do {
		if (kd_mutex_shadows[pos].mutex_addr == mutex_addr) {
			raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock,
						   flags);
			return &kd_mutex_shadows[pos].kd_mtx;
		}
		if (kd_mutex_shadows[pos].mutex_addr == 0) {
			raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock,
						   flags);
			return NULL;
		}
		pos = (pos + 1) % KD_MUTEX_SHADOW_TABLE_SIZE;
	} while (pos != start);

	raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
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
int kd_spin_native_cache __read_mostly = 1;
module_param_named(spin_native_cache, kd_spin_native_cache, bint, 0400);
MODULE_PARM_DESC(spin_native_cache,
	"Cache published native spin sites (default on; disable for entry-cost comparisons)");

/* Only an S/L owner needs the gate-release call and its two live pointers.
 * Keep them in this frame so cached native unlocks do not acquire additional
 * callee-saved register spills merely because this path exists. */
noinline void kd_spin_fast_release_gate(struct kd_spin_fast_cpu *fast)
{
	struct kd_spin_gate *gate = fast->hold.gate;

	BUG_ON(kd_spin_gate_release(&fast->hold));
	/* Release L before S; preserve a concurrent pending/tail. */
	smp_store_release(&gate->word.locked, 0);
	WRITE_ONCE(fast->held, NULL);
	preempt_enable();
}

/* Keep ticket objects and the general route's stack protector outside the
 * common native return. The saved kernel rsp still belongs to the original
 * guest hook and is passed unchanged through the cold acquisition helper. */
static noinline void kd_raw_spin_unlock_slow(raw_spinlock_t *lock)
{
	struct kd_spin_ref ref = { 0 };

	if (kd_exec_native_unlock((unsigned long)lock, false))
		return;
	/* Acquisition provenance wins over today's promotion state or comm. */
	if (kd_spin_entry_find(lock, &ref)) {
		kd_spin_unlock_ref((struct qspinlock *)lock, &ref);
		return;
	}
	if (!kd_hotlock_is_promoted((unsigned long)lock))
		kd_hotlock_record((unsigned long)lock);
	origin_raw_spin_unlock(lock);
}

static noinline void kd_raw_spin_lock_slow(raw_spinlock_t *lock,
					 unsigned long ret_rsp,
					 unsigned long ret_addr)
{
	if (kd_spin_entry_native_active() ||
	    !kd_hotlock_is_promoted((unsigned long)lock)) {
		kd_hotlock_record((unsigned long)lock);
		origin_raw_spin_lock(lock);
		return;
	}

	kd_exe_add(0, ret_addr, KD_EXE_LOCK_SPIN);
	kd_spin_lock((struct qspinlock *)lock, ret_rsp, ret_addr);
}

void __kd_raw_spin_unlock(raw_spinlock_t *lock, unsigned long ret_rsp,
			  unsigned long ret_addr)
{
	(void)ret_rsp;
	(void)ret_addr;
	if (likely(kd_spin_fast_unlock(lock)))
		return;
	kd_raw_spin_unlock_slow(lock);
}

void __kd_raw_spin_lock(raw_spinlock_t *lock, unsigned long ret_rsp,
			unsigned long ret_addr)
{
	if (likely(kd_spin_fast_trylock(lock, ret_addr)))
		return;
	kd_raw_spin_lock_slow(lock, ret_rsp, ret_addr);
}

static noinline void kd_spin_dispatch_lock_slow(raw_spinlock_t *lock,
		unsigned long ret_rsp, unsigned long ret_addr,
		enum kd_spin_fast_result result)
{
	if (result == KD_SPIN_FAST_MISS_PINNED)
		preempt_enable();
	if (kd_spin_task_selected())
		kd_raw_spin_lock_slow(lock, ret_rsp, ret_addr);
	else
		origin_raw_spin_lock(lock);
}

static noinline void kd_spin_dispatch_unlock_slow(raw_spinlock_t *lock)
{
	if (kd_spin_task_selected())
		kd_raw_spin_unlock_slow(lock);
	else
		origin_raw_spin_unlock(lock);
}

/* The cache proves a pinned, published site, not permission to execute JIT.
 * A hit performs only the original Linux acquisition and can also serve a
 * non-target caller of that same site. S, admission, CPU context and native L
 * still gate the try. Misses select the original target/retained-owner route;
 * no non-target miss is promoted, registered or delegated here. */
void kd_spin_dispatch_lock(raw_spinlock_t *lock, unsigned long ret_rsp,
			   unsigned long ret_addr)
{
	enum kd_spin_fast_result result = kd_spin_fast_acquire(lock, ret_addr);

	if (likely(result == KD_SPIN_FAST_OWNED))
		return;
	kd_spin_dispatch_lock_slow(lock, ret_rsp, ret_addr, result);
}

void kd_spin_dispatch_unlock(raw_spinlock_t *lock, unsigned long ret_rsp,
			     unsigned long ret_addr)
{
	(void)ret_rsp;
	(void)ret_addr;
	/* Acquisition provenance is sufficient for this native unlock, including
	 * a renamed task or closed admission; do not repeat target selection. */
	if (likely(kd_spin_fast_unlock(lock)))
		return;
	kd_spin_dispatch_unlock_slow(lock);
}

/* Preserve the four continuation arguments only on a cache miss. Keeping
 * registration and scheduling calls here avoids saving them across C calls
 * in every successful native acquisition, just as in the legacy dispatcher. */
static noinline void kd_spin_dispatch_clobber_lock_slow(raw_spinlock_t *lock,
        unsigned long sp, unsigned long ip, unsigned long bp,
        enum kd_spin_fast_result result)
{
	if (result == KD_SPIN_FAST_MISS_PINNED)
		preempt_enable();
	if (!kd_spin_task_selected() || kd_spin_entry_native_active()) {
		origin_raw_spin_lock(lock);
		return;
	}
	if (!kd_hotlock_is_promoted((unsigned long)lock)) {
		kd_hotlock_record((unsigned long)lock);
		origin_raw_spin_lock(lock);
		return;
	}
	kd_exe_add_abi(0, ip, KD_EXE_LOCK_SPIN, KD_ENTRY_ABI_SPIN_CLOBBER_V1);
	kd_spin_lock_abi((struct qspinlock *)lock, sp, ip, bp,
	                 KD_ENTRY_ABI_SPIN_CLOBBER_V1);
}

void kd_spin_dispatch_clobber_lock_v1(raw_spinlock_t *lock, unsigned long sp,
                                    unsigned long ip, unsigned long bp)
{
	enum kd_spin_fast_result result = kd_spin_fast_acquire(lock, ip);

	if (likely(result == KD_SPIN_FAST_OWNED))
		return;
	kd_spin_dispatch_clobber_lock_slow(lock, sp, ip, bp, result);
}

void kd_spin_dispatch_clobber_unlock_v1(raw_spinlock_t *lock, unsigned long sp,
                                      unsigned long ip, unsigned long bp)
{
	kd_spin_dispatch_unlock(lock, sp, ip);
}

#include "lock/mutex_calls.inc"

/* ==========================================================================
 * origin_* — original kernel lock paths (fallback when not delegating)
 * ========================================================================== */

static void origin_raw_spin_lock(raw_spinlock_t *lock)
{
	__raw_spin_lock(lock);
}

static void origin_raw_spin_unlock(raw_spinlock_t *lock)
{
	__raw_spin_unlock(lock);
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
