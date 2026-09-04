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
#include <linux/errno.h>

#include "kd_lock.h"
#include "kd_exec.h"
#include "kd_futex.h"
#include "kd_int3.h"
#include "exe.h"
#include "utils.h"
#include "kd_spinlock.h"
#include "kd_mutex.h"

/* --- module parameters ---------------------------------------------------- */

int velvet_wait_queue = 1;
int delegate_election = 1;
int kd_spin_jit_fail_after_nested_lock;

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
			kd_mutex_shadows[pos].kd_mtx.origin_mutex_addr =
				mutex_addr;
			raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
			return &kd_mutex_shadows[pos].kd_mtx;
		}
		pos = (pos + 1) % KD_MUTEX_SHADOW_TABLE_SIZE;
	} while (pos != start);

	raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
	KD_PR_ERR("kd mutex shadow table is full\n");
	return NULL;
}

static struct kd_mutex* find_kd_mutex_shadow(struct mutex* lock)
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
			raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
			return NULL;
		}
		pos = (pos + 1) % KD_MUTEX_SHADOW_TABLE_SIZE;
	} while (pos != start);

	raw_spin_unlock_irqrestore(&kd_mutex_shadow_lock, flags);
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

	kd_exe_add(0, ret_addr);  /* rip-only key: same kernel CS shared by all */
	kd_spin_lock((struct qspinlock *)lock, ret_rsp);
}

/* ==========================================================================
 * Mutex hooks
 * ========================================================================== */

/* Linux 6.1 stores the owner task pointer in struct mutex::owner and reserves
 * the low three bits for WAITERS/HANDOFF/PICKUP.  kdlock is already tied to
 * this patched kernel ABI, so use the owner to distinguish an in-flight
 * original acquisition from a shadow-mutex acquisition during promotion. */
#define KD_MUTEX_OWNER_FLAGS 0x7UL

static bool kd_origin_mutex_owned_by_current(struct mutex *lock)
{
	unsigned long owner = atomic_long_read(&lock->owner);

	return (owner & ~KD_MUTEX_OWNER_FLAGS) == (unsigned long)current;
}

static void kd_wait_for_origin_mutex_users(struct kd_uaddr_state *u_state)
{
	while (atomic_read(&u_state->mutex_origin_users) != 0) {
		cpu_relax();
		cond_resched();
	}
	/* Pair the drain with the atomic updates on the original path before
	 * allowing this task to acquire the independent shadow mutex. */
	smp_mb();
}

void __kd_mutex_lock(struct mutex *lock, unsigned long ret_rsp,
		     unsigned long ret_addr)
{
	struct kd_mutex* kd_mtx;
	struct kd_mutex_shadow_entry* entry;
	struct kd_uaddr_state* u_state;
	/*
	 * Capture callee-saved registers NOW, before any function calls
	 * in this hook can clobber them. At this point they hold the values
	 * that mutex_lock preserved from the original caller.
	 *
	 * We store them in local variables; they'll be passed to
	 * _kd_mutex_lock which saves them into the per-CPU node.
	 */
	unsigned long s_rbx, s_r12, s_r13, s_r14, s_r15, s_rbp;
	asm volatile(
		"movq %%rbx, %0\n"
		"movq %%r12, %1\n"
		"movq %%r13, %2\n"
		"movq %%r14, %3\n"
		"movq %%r15, %4\n"
		"movq %%rbp, %5\n"
		: "=m"(s_rbx), "=m"(s_r12), "=m"(s_r13),
		  "=m"(s_r14), "=m"(s_r15), "=m"(s_rbp)
		:
		: "memory"
	);

	u_state = kd_get_uaddr_state((unsigned long)lock);
	if (!check_uaddr_state((unsigned long)lock)) {
		/* Register before rechecking the promotion state.  If another CPU
		 * promotes between the two checks, withdraw and join the shadow path.
		 * Otherwise this acquisition remains counted through its unlock, so
		 * shadow users cannot overlap an original owner or waiter. */
		atomic_inc(&u_state->mutex_origin_users);
		smp_mb__after_atomic();
		if (!check_uaddr_state((unsigned long)lock)) {
			count_uaddr_cnt((unsigned long)lock);
			origin_mutex_lock(lock);
			return;
		}
		atomic_dec(&u_state->mutex_origin_users);
	}

	kd_wait_for_origin_mutex_users(u_state);

	kd_mtx = get_kd_mutex_shadow(lock);
	if (kd_mtx == NULL) {
		origin_mutex_lock(lock);
		return;
	}

	kd_exe_add(0, ret_addr);  /* pid=0: rip-only key, shared by all processes */
	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	entry->delegated = 1;
	_kd_mutex_lock(kd_mtx, ret_rsp, ret_addr,
		       s_rbx, s_r12, s_r13, s_r14, s_r15, s_rbp);
}

/*
 * __kd_mutex_unlock — unlock hook.
 *
 * NOTE: we intentionally do NOT clear entry->delegated here.  Once a mutex
 * has been routed through the kd_mutex protocol, all subsequent unlock calls
 * must also go through _kd_mutex_unlock to clear the kd_mutex.locked field.
 * Clearing delegated would cause the next unlock to call origin_mutex_unlock,
 * leaving kd_mutex.locked permanently set → deadlock for waiters.
 */
void __kd_mutex_unlock(struct mutex *lock, unsigned long ret_rsp,
		       unsigned long ret_addr)
{
	struct kd_mutex* kd_mtx;
	struct kd_mutex_shadow_entry* entry;
	struct kd_uaddr_state* u_state;

	(void)ret_rsp;
	u_state = kd_get_uaddr_state((unsigned long)lock);

	/* A task that entered before/during promotion still owns the Linux mutex.
	 * Release that exact lock and keep shadow acquisitions gated until all
	 * original owners and queued acquirers have drained. */
	if (kd_origin_mutex_owned_by_current(lock)) {
		origin_mutex_unlock(lock, ret_addr);
		atomic_add_unless(&u_state->mutex_origin_users, -1, 0);
		return;
	}

	kd_mtx = find_kd_mutex_shadow(lock);
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

int kd_mutex_jit_nested_lock(struct mutex *lock)
{
	struct kd_mutex *kd_mtx;
	struct kd_mutex_shadow_entry *entry;

	kd_mtx = find_kd_mutex_shadow(lock);
	if (!kd_mtx)
		return -ENOENT;

	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	if (!entry->delegated)
		return -EINVAL;

	return _kd_mutex_trylock(kd_mtx) ? 0 : -EBUSY;
}

int kd_mutex_jit_nested_unlock(struct mutex *lock)
{
	struct kd_mutex *kd_mtx;
	struct kd_mutex_shadow_entry *entry;

	kd_mtx = find_kd_mutex_shadow(lock);
	if (!kd_mtx)
		return -ENOENT;

	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	if (!entry->delegated)
		return -EINVAL;

	return _kd_mutex_unlock_checked(kd_mtx);
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

/*
 * Nested spinlock calls inside a translated critical section use the same
 * promoted lock protocol when possible.  The original path remains an
 * explicit fallback for locks that have not been promoted.
 */
int kd_spin_jit_nested_lock(raw_spinlock_t *lock)
{
	return kd_spin_jit_nested_lock_ctx(lock, NULL, kd_exec_current_frame());
}

int kd_spin_jit_nested_unlock(raw_spinlock_t *lock)
{
	return kd_spin_jit_nested_unlock_ctx(lock, kd_exec_current_frame());
}

static int kd_spin_jit_advance_call(struct kd_exec_frame *frame,
				    struct pt_regs *regs)
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

static int kd_spin_jit_nested_lock_common(raw_spinlock_t *lock,
					  struct pt_regs *regs,
					  struct kd_exec_frame *frame)
{
	struct kd_exec_frame *active_frame = frame;
	bool promoted;
	int ret;

	if (!lock)
		return -EINVAL;

	promoted = check_uaddr_state((unsigned long)lock);
	if (!active_frame)
		active_frame = kd_exec_current_frame();

	if (active_frame) {
		if (kd_exec_frame_lock_contains(active_frame,
						(unsigned long)lock))
			return -EDEADLK;
		if (kd_exec_frame_lock_depth(active_frame) >=
		    KD_EXEC_MAX_LOCK_DEPTH)
			return -E2BIG;
	}

	if (!regs || !regs->sp)
		goto fallback;
	if (!active_frame || kd_spin_jit_advance_call(active_frame, regs))
		return -EINVAL;
	if (promoted && !kd_exe_is_ready(0, regs->ip))
		kd_exe_add(0, regs->ip);

	if (kd_exec_frame_record_event(active_frame,
				       KD_EXEC_EVENT_NESTED_LOCK, regs))
		return -EINVAL;

	if (promoted) {
		enum kd_exec_lock_kind kind;

		ret = kd_spin_nested_lock((struct qspinlock *)lock, regs,
					  active_frame);
		if (ret < 0)
			return ret;

		kd_spin_debug_nested_lock(lock, false);
		if (ret == KD_SPIN_NESTED_DELEGATED ||
		    ret == KD_SPIN_NESTED_PARENT_OOO) {
			kd_spin_debug_nested_unlock(lock);
			kd_spin_debug_nested_remote(lock);
			kd_exec_frame_save_continuation(active_frame, regs);
			if (ret == KD_SPIN_NESTED_PARENT_OOO) {
				if (kd_exec_frame_record_event(
						active_frame,
						KD_EXEC_EVENT_OUTER_UNLOCK,
						NULL))
					return -EINVAL;
				return KD_EXE_KNOWN_OUTER_UNLOCK;
			}
			return KD_JIT_NESTED_REMOTE;
		}
		kind = ret == KD_SPIN_NESTED_ACQUIRED_QUEUE ?
			KD_EXEC_LOCK_QUEUE_OWNER : KD_EXEC_LOCK_FAST;

		ret = kd_spin_nested_shadow_push((struct qspinlock *)lock);
		if (ret) {
			kd_spin_unlock((struct qspinlock *)lock);
			return ret;
		}
		if (kd_exec_frame_lock_push(active_frame, (unsigned long)lock,
					    kind, NULL)) {
			kd_spin_unlock((struct qspinlock *)lock);
			kd_spin_nested_shadow_remove((struct qspinlock *)lock);
			return -E2BIG;
		}
		if ((kind == KD_EXEC_LOCK_FAST ||
		     kind == KD_EXEC_LOCK_QUEUE_OWNER) &&
		    unlikely(cmpxchg(&kd_spin_jit_fail_after_nested_lock,
				     1, 0) == 1)) {
			KD_PR_INFO("spin JIT injected failure after nested lock=%px outer=%lx val=%x kind=%d\n",
				   lock, active_frame->outer_lock_addr,
				   atomic_read(&((struct qspinlock *)lock)->val), kind);
			return -EIO;
		}
		return KD_JIT_NESTED_CONSUMED;
	}

fallback:
	if (active_frame && !regs &&
	    kd_exec_frame_record_event(active_frame,
				       KD_EXEC_EVENT_NESTED_LOCK, NULL))
		return -EINVAL;

	count_uaddr_cnt((unsigned long)lock);
	origin_raw_spin_lock(lock);
	if (kd_spin_nested_shadow_push((struct qspinlock *)lock)) {
		origin_raw_spin_unlock(lock);
		return -E2BIG;
	}
	if (active_frame &&
	    kd_exec_frame_lock_push(active_frame, (unsigned long)lock,
				    KD_EXEC_LOCK_NATIVE, NULL)) {
		kd_spin_nested_shadow_remove((struct qspinlock *)lock);
		origin_raw_spin_unlock(lock);
		return -E2BIG;
	}
	kd_spin_debug_nested_lock(lock, true);
	return regs ? KD_JIT_NESTED_CONSUMED : KD_JIT_NESTED_NATIVE;
}

int kd_spin_jit_nested_lock_ctx(raw_spinlock_t *lock,
				struct pt_regs *regs,
				struct kd_exec_frame *frame)
{
	return kd_spin_jit_nested_lock_common(lock, regs, frame);
}

int kd_spin_jit_nested_unlock_ctx(raw_spinlock_t *lock,
				  struct kd_exec_frame *frame)
{
	struct kd_exec_frame *active_frame = frame;
	enum kd_exec_lock_kind kind;

	if (!lock)
		return -EINVAL;
	if (!active_frame)
		active_frame = kd_exec_current_frame();
	if (!active_frame)
		return -EINVAL;

	kind = kd_exec_frame_lock_kind(active_frame, (unsigned long)lock);
	if (kind == KD_EXEC_LOCK_NONE)
		return -ENOENT;

	if (kd_exec_frame_record_event(active_frame,
				       KD_EXEC_EVENT_NESTED_UNLOCK, NULL))
		return -EINVAL;

	if (kind == KD_EXEC_LOCK_NATIVE) {
		kd_spin_debug_nested_unlock(lock);
		origin_raw_spin_unlock(lock);
		if (kd_spin_nested_shadow_remove((struct qspinlock *)lock))
			return -EINVAL;
		if (kd_exec_frame_lock_pop(active_frame,
					    (unsigned long)lock))
			return -EINVAL;
		if (kd_exec_frame_can_complete(active_frame))
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		return 0;
	}

	kd_spin_debug_nested_unlock(lock);
	{
		int unlock_ret = kd_spin_nested_unlock((struct qspinlock *)lock);

		if (unlock_ret < 0)
			return unlock_ret;
		if (unlock_ret == KD_SPIN_NESTED_UNLOCK_OOO)
			return kd_exec_frame_lock_mark_released(active_frame,
								(unsigned long)lock);
	}
	if (kd_exec_frame_lock_pop(active_frame, (unsigned long)lock))
		return -EINVAL;
	if (kd_exec_frame_can_complete(active_frame))
		return KD_EXE_KNOWN_OUTER_UNLOCK;
	return 0;
}

int kd_spin_jit_outer_unlock_ooo_ctx(raw_spinlock_t *lock,
				     struct pt_regs *regs,
				     struct kd_exec_frame *frame)
{
	if (!lock || !frame || frame->outer_lock_addr != (unsigned long)lock ||
	    !kd_exec_frame_has_unreleased_nested(frame))
		return -EINVAL;

	if (kd_exec_frame_record_event(frame, KD_EXEC_EVENT_OUTER_UNLOCK,
					       regs))
		return -EINVAL;

	/* The shadow stack contains the nested locks, so kdlock marks A as OOO
	 * and keeps its handoff state until the enclosing combiner returns. */
	kd_spin_unlock((struct qspinlock *)lock);
	return 0;
}

int kd_spin_jit_nested_cleanup(struct kd_exec_frame *frame)
{
	unsigned int i;

	if (!frame || !kd_exec_frame_can_complete(frame))
		return -EINVAL;

	for (i = frame->jit_lock_depth;
	     i > frame->outer_lock_index + 1; i--) {
		unsigned long lock_addr = frame->jit_lock_addr[i - 1];
		int ret;

		if (!frame->jit_lock_released[i - 1])
			return -EBUSY;
		ret = kd_spin_nested_shadow_remove((struct qspinlock *)lock_addr);
		if (ret && ret != -ENOENT)
			return ret;
		ret = kd_exec_frame_lock_pop(frame, lock_addr);
		if (ret)
			return ret;
	}

	return 0;
}

int kd_spin_jit_abort_cleanup(struct kd_exec_frame *frame)
{
	unsigned int cleaned = 0;

	if (!frame || !kd_exec_frame_validate(frame) ||
	    frame->outer_lock_index >= frame->jit_lock_depth)
		return -EINVAL;

	while (frame->jit_lock_depth > frame->outer_lock_index + 1) {
		unsigned int index = frame->jit_lock_depth - 1;
		unsigned long lock_addr = frame->jit_lock_addr[index];
		enum kd_exec_lock_kind kind = frame->jit_lock_kind[index];
		bool released = frame->jit_lock_released[index];
		int before = atomic_read(
			&((struct qspinlock *)lock_addr)->val);
		int ret;

		if (!released) {
			if (kind == KD_EXEC_LOCK_NATIVE) {
				kd_spin_debug_nested_unlock(
					(raw_spinlock_t *)lock_addr);
				origin_raw_spin_unlock(
					(raw_spinlock_t *)lock_addr);
			} else if (kind == KD_EXEC_LOCK_FAST ||
				   kind == KD_EXEC_LOCK_QUEUE_OWNER) {
				kd_spin_debug_nested_unlock(
					(raw_spinlock_t *)lock_addr);
				ret = kd_spin_nested_unlock(
					(struct qspinlock *)lock_addr);
				if (ret < 0)
					return ret;
				if (ret == KD_SPIN_NESTED_UNLOCK_OK)
					goto pop_entry;
			} else {
				return -EINVAL;
			}
		}

		/* OOO unlocks and native locks retain a shadow entry. */
		ret = kd_spin_nested_shadow_remove(
			(struct qspinlock *)lock_addr);
		if (ret && ret != -ENOENT)
			return ret;

pop_entry:
		ret = kd_exec_frame_lock_pop(frame, lock_addr);
		if (ret)
			return ret;
		KD_PR_INFO("spin JIT abort release: lock=%lx kind=%d was_released=%d before=%x after=%x\n",
			   lock_addr, kind, released, before,
			   atomic_read(&((struct qspinlock *)lock_addr)->val));
		cleaned++;
	}
	if (cleaned)
		KD_PR_INFO("spin JIT abort cleanup: outer=%lx released=%u\n",
			   frame->outer_lock_addr, cleaned);

	return 0;
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
