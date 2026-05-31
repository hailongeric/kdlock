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
 */
#include <linux/freezer.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <linux/string.h>
#include <linux/kernel.h>
#include <asm/barrier.h>
#include <linux/sched/topology.h>
#include <linux/kfifo.h>
#include <linux/syscalls.h>
#include <asm/processor.h>
#include <linux/atomic.h>
#include <asm/cacheflush.h>
#include <asm/uaccess.h>
#include <linux/hrtimer.h>
#include <asm/smp.h>
#include <asm/msr.h>
#include <linux/random.h>
#include <linux/numa.h>
#include <linux/topology.h>
#include <linux/cpumask.h>
#include <linux/bitmap.h>
#include <linux/plist.h>
#include <asm/cacheflush.h>
#include <linux/io.h>
#include <asm/pgtable.h>
#include <linux/pid.h>
#include <linux/page-flags.h>
#include <linux/fs.h>
#include <linux/mm.h>
#include <linux/highmem.h>
#include <asm/bitops.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>

#include "kd_lock.h"
#include "kd_futex.h"
#include "kd_int3.h"
#include "exe.h"
#include "utils.h"
#include "kd_spinlock.h"
#include "kd_mutex.h"

/* --- module parameters ---------------------------------------------------- */

int velvet_wait_queue = 1;
int delegate_election = 1;

int fast_path_wake_time[8] = { 1000, 2000, 4000, 8000, 16000, 32000, 64000, 128000 };

/* --- mutex → kd_mutex shadow table ---------------------------------------- */

#define KD_MUTEX_SHADOW_TABLE_SIZE 1024

struct kd_mutex_shadow_entry {
	unsigned long mutex_addr;
	struct kd_mutex kd_mtx;
	int delegated;            /* set when kd_mutex protocol acquired the lock */
};

static struct kd_mutex_shadow_entry kd_mutex_shadows[KD_MUTEX_SHADOW_TABLE_SIZE];
static DEFINE_RAW_SPINLOCK(kd_mutex_shadow_lock);


/* --- externs from exe.c --------------------------------------------------- */

extern int delegate_uaddr_cnt;
extern long kd_success_cnt;
extern unsigned long uaddrs[];
extern unsigned long uaddr_cnts[];
extern unsigned long kd_wake_rets[];
extern long uaddr_cnt;
extern atomic_t normal_wake_cnt;
extern atomic_t kd_d_lock;
extern atomic_t kd_com;
extern atomic_t kd_wake_state;
extern atomic_long_t start_work_cycle;
extern atomic_long_t count_uaddr_time;
extern atomic_t kd_is_delegating;
extern atomic_t int3_waiter_cnt;
extern spinlock_t int3_change_lock;
extern struct kd_delegate_numanode** kd_numanodes;
extern struct kd_cycle_cnt* kd_cycle_cnts;

/* --- externs from patched kernel ------------------------------------------ */

extern void futex_wake_mark(struct wake_q_head* wake_q, struct futex_q* q);
extern void futex_wake_mark_2(struct futex_q* q);
extern void wake_up_q(struct wake_q_head* head);
extern void wake_q_add_safe(struct wake_q_head* head, struct task_struct* task);
extern struct hrtimer_sleeper* futex_setup_timer(ktime_t* time,
	struct hrtimer_sleeper* timeout, int flags, u64 range_ns);
extern int futex_wait_setup(u32 __user* uaddr, u32 val, unsigned int flags,
	struct futex_q* q, struct futex_hash_bucket** hb);
extern void futex_wait_queue(struct futex_hash_bucket* hb, struct futex_q* q,
	struct hrtimer_sleeper* timeout);
extern int futex_unqueue(struct futex_q* q);
extern struct futex_hash_bucket* futex_q_lock(struct futex_q* q);
extern int futex_get_value_locked(u32* dest, u32 __user* from);
extern void futex_q_unlock(struct futex_hash_bucket* hb);
extern void __mutex_lock_slowpath(struct mutex *lock);
extern void __mutex_unlock_slowpath(struct mutex *lock, unsigned long ip);

/* --- mutex shadow table lookup -------------------------------------------- */

static struct kd_mutex* get_kd_mutex_shadow(struct mutex* lock)
{
	unsigned long flags;
	unsigned long mutex_addr = (unsigned long)lock;
	int start = mutex_addr % KD_MUTEX_SHADOW_TABLE_SIZE;
	int pos = start;

	raw_spin_lock_irqsave(&kd_mutex_shadow_lock, flags);
	do {
		if (kd_mutex_shadows[pos].mutex_addr == mutex_addr) {
			raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
			return &kd_mutex_shadows[pos].kd_mtx;
		}
		if (kd_mutex_shadows[pos].mutex_addr == 0) {
			kd_mutex_shadows[pos].mutex_addr = mutex_addr;
			kd_mutex_init(&kd_mutex_shadows[pos].kd_mtx);
			raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
			return &kd_mutex_shadows[pos].kd_mtx;
		}
		pos = (pos + 1) % KD_MUTEX_SHADOW_TABLE_SIZE;
	} while (pos != start);

	raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
	KD_PR_ERR("kd mutex shadow table is full\n");
	return NULL;
}

/* ==========================================================================
 * Raw spinlock hooks
 * ========================================================================== */

void __kd_raw_spin_unlock(raw_spinlock_t *lock, unsigned long ret_rsp,
			  unsigned long ret_addr)
{
	unsigned long long begin, t, end, start, cur_ts, check_ts;
	struct kd_delegate_complete* completes;
	volatile atomic_long_t* queue;
	volatile atomic_t* state;
	struct cpumask* mask;
	struct pt_regs* regs;
	unsigned long before_rip, after_rip, wait_cost;
	struct kd_delegate_uaddrnode* uaddrnode;
	struct kd_uaddr_state* u_state;
	int cpu_id, numa_id, cpu_index, temp, timeout_time;

	(void)ret_addr;
	(void)ret_rsp;

	if (!check_uaddr_state((unsigned long)lock)) {
		count_uaddr_cnt((unsigned long)lock);
		origin_raw_spin_unlock(lock);
		return;
	}

	kd_spin_unlock((struct qspinlock *)lock);
}

#include <linux/kgdb.h>

void __kd_raw_spin_lock(raw_spinlock_t *lock, unsigned long ret_rsp,
			unsigned long ret_addr)
{
	if (!check_uaddr_state((unsigned long)lock)) {
		count_uaddr_cnt((unsigned long)lock);
		origin_raw_spin_lock(lock);
		return;
	}

	kd_exe_add(current->pid, ret_addr);
	kd_spin_lock((struct qspinlock *)lock, ret_rsp);
}

/* ==========================================================================
 * Mutex hooks
 * ========================================================================== */

void __kd_mutex_lock(struct mutex *lock, unsigned long ret_rsp,
		     unsigned long ret_addr)
{
	struct kd_mutex* kd_mtx;
	struct kd_mutex_shadow_entry* entry;

	if (!check_uaddr_state((unsigned long)lock)) {
		count_uaddr_cnt((unsigned long)lock);
		origin_mutex_lock(lock);
		return;
	}

	kd_mtx = get_kd_mutex_shadow(lock);
	if (kd_mtx == NULL) {
		origin_mutex_lock(lock);
		return;
	}

	kd_exe_add(current->pid, ret_addr);
	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	entry->delegated = 1;
	_kd_mutex_lock(kd_mtx, ret_rsp);
}

void __kd_mutex_unlock(struct mutex *lock, unsigned long ret_rsp,
		       unsigned long ret_addr)
{
	struct kd_mutex* kd_mtx;
	struct kd_mutex_shadow_entry* entry;

	(void)ret_rsp;

	kd_mtx = get_kd_mutex_shadow(lock);
	if (kd_mtx == NULL) {
		origin_mutex_unlock(lock, ret_addr);
		return;
	}

	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	if (!entry->delegated) {
		origin_mutex_unlock(lock, ret_addr);
		return;
	}

	_kd_mutex_unlock(kd_mtx);
}

/* ==========================================================================
 * origin_* — original kernel lock paths (fallback when not delegating)
 * ========================================================================== */

void origin_raw_spin_lock(raw_spinlock_t *lock)
{
	__raw_spin_lock(lock);
}

void origin_raw_spin_unlock(raw_spinlock_t *lock)
{
	__raw_spin_unlock(lock);
}

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

void origin_mutex_lock(struct mutex *lock)
{
	might_sleep();
	if (!kd_mutex_trylock_fast(lock))
		__mutex_lock_slowpath(lock);
}

void origin_mutex_unlock(struct mutex *lock, unsigned long ret_addr)
{
#ifndef CONFIG_DEBUG_LOCK_ALLOC
	if (kd_mutex_unlock_fast(lock))
		return;
#endif
	__mutex_unlock_slowpath(lock, ret_addr);
}
