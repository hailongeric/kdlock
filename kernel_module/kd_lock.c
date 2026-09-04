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
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/spinlock.h>

#include "exe.h"
#include "kd_exec.h"
#include "kd_hotlock.h"
#include "kd_lock.h"
#include "kd_mutex.h"
#include "kd_spinlock.h"
#include "utils.h"

/* --- module parameters ---------------------------------------------------- */

int kd_spin_jit_fail_after_nested_lock;

static void origin_raw_spin_lock(raw_spinlock_t *lock);
static void origin_raw_spin_unlock(raw_spinlock_t *lock);
static void origin_mutex_lock(struct mutex *lock);
static void origin_mutex_unlock(struct mutex *lock, unsigned long ret_addr);

/* --- mutex → kd_mutex shadow table ---------------------------------------- */

#define KD_MUTEX_SHADOW_TABLE_SIZE 1024

struct kd_mutex_shadow_entry {
	unsigned long mutex_addr;
	struct kd_mutex kd_mtx;
	bool delegated; /* Remains set after this mutex enters shadow mode. */
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

/* ==========================================================================
 * Raw spinlock hooks
 * ========================================================================== */

void __kd_raw_spin_unlock(raw_spinlock_t *lock, unsigned long ret_rsp,
			  unsigned long ret_addr)
{
	(void)ret_addr;
	(void)ret_rsp;

	if (!kd_hotlock_is_promoted((unsigned long)lock)) {
		kd_hotlock_record((unsigned long)lock);
		origin_raw_spin_unlock(lock);
		return;
	}

	kd_spin_unlock((struct qspinlock *)lock);
}

void __kd_raw_spin_lock(raw_spinlock_t *lock, unsigned long ret_rsp,
			unsigned long ret_addr)
{
	if (!kd_hotlock_is_promoted((unsigned long)lock)) {
		kd_hotlock_record((unsigned long)lock);
		origin_raw_spin_lock(lock);
		return;
	}

	kd_exe_add(0,
		   ret_addr); /* rip-only key: same kernel CS shared by all */
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

static void kd_wait_for_origin_mutex_users(struct kd_hotlock_state *state)
{
	while (atomic_read(&state->mutex_origin_users) != 0) {
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
	struct kd_mutex *kd_mtx;
	struct kd_mutex_shadow_entry *entry;
	struct kd_hotlock_state *state;
	/*
	 * Capture callee-saved registers NOW, before any function calls
	 * in this hook can clobber them. At this point they hold the values
	 * that mutex_lock preserved from the original caller.
	 *
	 * We store them in local variables; they'll be passed to
	 * _kd_mutex_lock which saves them into the per-CPU node.
	 */
	unsigned long s_rbx, s_r12, s_r13, s_r14, s_r15, s_rbp;
	asm volatile("movq %%rbx, %0\n"
		     "movq %%r12, %1\n"
		     "movq %%r13, %2\n"
		     "movq %%r14, %3\n"
		     "movq %%r15, %4\n"
		     "movq %%rbp, %5\n"
		     : "=m"(s_rbx), "=m"(s_r12), "=m"(s_r13), "=m"(s_r14),
		       "=m"(s_r15), "=m"(s_rbp)
		     :
		     : "memory");

	state = kd_hotlock_state_get((unsigned long)lock);
	if (!state) {
		origin_mutex_lock(lock);
		return;
	}
	if (!kd_hotlock_is_promoted((unsigned long)lock)) {
		/* Register before rechecking the promotion state.  If another CPU
		 * promotes between the two checks, withdraw and join the shadow path.
		 * Otherwise this acquisition remains counted through its unlock, so
		 * shadow users cannot overlap an original owner or waiter. */
		atomic_inc(&state->mutex_origin_users);
		smp_mb__after_atomic();
		if (!kd_hotlock_is_promoted((unsigned long)lock)) {
			kd_hotlock_record((unsigned long)lock);
			origin_mutex_lock(lock);
			return;
		}
		atomic_dec(&state->mutex_origin_users);
	}

	kd_wait_for_origin_mutex_users(state);

	kd_mtx = get_kd_mutex_shadow(lock);
	if (kd_mtx == NULL) {
		origin_mutex_lock(lock);
		return;
	}

	kd_exe_add(0,
		   ret_addr); /* pid=0: rip-only key, shared by all processes */
	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	WRITE_ONCE(entry->delegated, true);
	_kd_mutex_lock(kd_mtx, ret_rsp, ret_addr, s_rbx, s_r12, s_r13, s_r14,
		       s_r15, s_rbp);
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
	struct kd_mutex *kd_mtx;
	struct kd_mutex_shadow_entry *entry;
	struct kd_hotlock_state *state;

	(void)ret_rsp;
	state = kd_hotlock_state_get((unsigned long)lock);

	/* A task that entered before/during promotion still owns the Linux mutex.
	 * Release that exact lock and keep shadow acquisitions gated until all
	 * original owners and queued acquirers have drained. */
	if (kd_origin_mutex_owned_by_current(lock)) {
		origin_mutex_unlock(lock, ret_addr);
		if (state)
			atomic_add_unless(&state->mutex_origin_users, -1, 0);
		return;
	}

	kd_mtx = find_kd_mutex_shadow(lock);
	if (kd_mtx == NULL) {
		origin_mutex_unlock(lock, ret_addr);
		return;
	}

	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	if (!READ_ONCE(entry->delegated)) {
		origin_mutex_unlock(lock, ret_addr);
		return;
	}

	_kd_mutex_unlock(kd_mtx);
}

static int kd_mutex_jit_advance_call(struct kd_exec_frame *frame,
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

int kd_mutex_jit_nested_lock_ctx(struct mutex *lock, struct pt_regs *regs,
				 struct kd_exec_frame *frame)
{
	struct kd_mutex_shadow_entry *entry;
	struct kd_mutex *kd_mtx;
	enum kd_exec_lock_kind kind;
	int ret;

	if (!lock || !regs || !frame || !kd_exec_frame_validate(frame))
		return -EINVAL;
	if (kd_exec_frame_lock_contains(frame, (unsigned long)lock))
		return -EDEADLK;
	if (kd_exec_frame_lock_depth(frame) >= KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;

	kd_mtx = find_kd_mutex_shadow(lock);
	if (!kd_mtx)
		return -ENOENT;
	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	if (!READ_ONCE(entry->delegated))
		return -EINVAL;

	if (kd_mutex_jit_advance_call(frame, regs))
		return -EINVAL;
	if (kd_exec_frame_record_event(frame, KD_EXEC_EVENT_NESTED_LOCK, regs))
		return -EINVAL;

	ret = kd_mutex_nested_lock(kd_mtx, regs, frame);
	if (ret < 0)
		return ret;
	if (ret == KD_MUTEX_NESTED_DELEGATED) {
		kd_exec_frame_save_continuation(frame, regs);
		return 1;
	}

	kind = ret == KD_MUTEX_NESTED_ACQUIRED_QUEUE ?
		       KD_EXEC_LOCK_QUEUE_OWNER :
		       KD_EXEC_LOCK_FAST;
	if (kd_exec_frame_lock_push(frame, (unsigned long)lock, kind, kd_mtx)) {
		if (kd_mutex_nested_unlock(kd_mtx))
			return -EIO;
		return -E2BIG;
	}
	return 1;
}

int kd_mutex_jit_nested_unlock_ctx(struct mutex *lock,
				   struct kd_exec_frame *frame)
{
	struct kd_mutex_shadow_entry *entry;
	struct kd_mutex *kd_mtx;
	enum kd_exec_lock_kind kind;
	void *lock_node;
	int ret;

	if (!lock || !frame || !kd_exec_frame_validate(frame))
		return -EINVAL;
	kind = kd_exec_frame_lock_kind(frame, (unsigned long)lock);
	if (kind != KD_EXEC_LOCK_FAST && kind != KD_EXEC_LOCK_QUEUE_OWNER)
		return -ENOENT;

	kd_mtx = find_kd_mutex_shadow(lock);
	if (!kd_mtx)
		return -ENOENT;

	entry = container_of(kd_mtx, struct kd_mutex_shadow_entry, kd_mtx);
	if (!READ_ONCE(entry->delegated))
		return -EINVAL;
	lock_node = kd_exec_frame_lock_node(frame, (unsigned long)lock);
	if (lock_node != kd_mtx)
		return -EINVAL;
	if (kd_exec_frame_record_event(frame, KD_EXEC_EVENT_NESTED_UNLOCK,
				       NULL))
		return -EINVAL;

	ret = kd_mutex_nested_unlock(kd_mtx);
	if (ret)
		return ret;
	return kd_exec_frame_lock_pop(frame, (unsigned long)lock);
}

int kd_mutex_jit_abort_cleanup(struct kd_exec_frame *frame)
{
	unsigned int cleaned = 0;

	if (!frame || !kd_exec_frame_validate(frame) ||
	    frame->outer_lock_index >= frame->jit_lock_depth)
		return -EINVAL;

	while (frame->jit_lock_depth > frame->outer_lock_index + 1) {
		unsigned int index = frame->jit_lock_depth - 1;
		unsigned long lock_addr = frame->jit_lock_addr[index];
		enum kd_exec_lock_kind kind = frame->jit_lock_kind[index];
		struct kd_mutex *kd_mtx = frame->jit_lock_node[index];
		bool released = frame->jit_lock_released[index];
		int ret;

		if (kind != KD_EXEC_LOCK_FAST &&
		    kind != KD_EXEC_LOCK_QUEUE_OWNER)
			return -EINVAL;
		if (!kd_mtx || kd_mtx->origin_mutex_addr != lock_addr)
			return -EINVAL;
		if (!released) {
			ret = kd_mutex_nested_unlock(kd_mtx);
			if (ret)
				return ret;
			kd_mutex_note_nested_abort_release();
		}
		ret = kd_exec_frame_lock_pop(frame, lock_addr);
		if (ret)
			return ret;
		KD_PR_INFO(
			"mutex JIT abort release: lock=%lx kind=%d was_released=%d\n",
			lock_addr, kind, released);
		cleaned++;
	}
	if (cleaned)
		KD_PR_INFO("mutex JIT abort cleanup: outer=%lx released=%u\n",
			   frame->outer_lock_addr, cleaned);
	return 0;
}

int kd_mutex_debug_waiter_count(struct mutex *lock)
{
	struct kd_mutex *kd_mtx;

	if (!lock)
		return -EINVAL;
	kd_mtx = find_kd_mutex_shadow(lock);
	return kd_mtx ? kd_mutex_waiter_count(kd_mtx) : -ENOENT;
}
EXPORT_SYMBOL_GPL(kd_mutex_debug_waiter_count);

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

	promoted = kd_hotlock_is_promoted((unsigned long)lock);
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

	if (kd_exec_frame_record_event(active_frame, KD_EXEC_EVENT_NESTED_LOCK,
				       regs))
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
					    KD_EXEC_EVENT_OUTER_UNLOCK, NULL))
					return -EINVAL;
				return KD_EXE_KNOWN_OUTER_UNLOCK;
			}
			return KD_JIT_NESTED_REMOTE;
		}
		kind = ret == KD_SPIN_NESTED_ACQUIRED_QUEUE ?
			       KD_EXEC_LOCK_QUEUE_OWNER :
			       KD_EXEC_LOCK_FAST;

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
		    unlikely(cmpxchg(&kd_spin_jit_fail_after_nested_lock, 1,
				     0) == 1)) {
			KD_PR_INFO(
				"spin JIT injected failure after nested lock=%px outer=%lx val=%x kind=%d\n",
				lock, active_frame->outer_lock_addr,
				atomic_read(&((struct qspinlock *)lock)->val),
				kind);
			return -EIO;
		}
		return KD_JIT_NESTED_CONSUMED;
	}

fallback:
	if (active_frame && !regs &&
	    kd_exec_frame_record_event(active_frame, KD_EXEC_EVENT_NESTED_LOCK,
				       NULL))
		return -EINVAL;

	kd_hotlock_record((unsigned long)lock);
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

int kd_spin_jit_nested_lock_ctx(raw_spinlock_t *lock, struct pt_regs *regs,
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
		if (kd_exec_frame_lock_pop(active_frame, (unsigned long)lock))
			return -EINVAL;
		if (kd_exec_frame_can_complete(active_frame))
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		return 0;
	}

	kd_spin_debug_nested_unlock(lock);
	{
		int unlock_ret =
			kd_spin_nested_unlock((struct qspinlock *)lock);

		if (unlock_ret < 0)
			return unlock_ret;
		if (unlock_ret == KD_SPIN_NESTED_UNLOCK_OOO)
			return kd_exec_frame_lock_mark_released(
				active_frame, (unsigned long)lock);
	}
	if (kd_exec_frame_lock_pop(active_frame, (unsigned long)lock))
		return -EINVAL;
	if (kd_exec_frame_can_complete(active_frame))
		return KD_EXE_KNOWN_OUTER_UNLOCK;
	return 0;
}

int kd_spin_jit_outer_unlock_ooo_ctx(raw_spinlock_t *lock, struct pt_regs *regs,
				     struct kd_exec_frame *frame)
{
	if (!lock || !frame || frame->outer_lock_addr != (unsigned long)lock ||
	    !kd_exec_frame_has_unreleased_nested(frame))
		return -EINVAL;

	if (kd_exec_frame_record_event(frame, KD_EXEC_EVENT_OUTER_UNLOCK, regs))
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

	for (i = frame->jit_lock_depth; i > frame->outer_lock_index + 1; i--) {
		unsigned long lock_addr = frame->jit_lock_addr[i - 1];
		int ret;

		if (!frame->jit_lock_released[i - 1])
			return -EBUSY;
		ret = kd_spin_nested_shadow_remove(
			(struct qspinlock *)lock_addr);
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
		int before = atomic_read(&((struct qspinlock *)lock_addr)->val);
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
		KD_PR_INFO(
			"spin JIT abort release: lock=%lx kind=%d was_released=%d before=%x after=%x\n",
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

static void origin_mutex_lock(struct mutex *lock)
{
	might_sleep();
	if (!kd_mutex_trylock_fast(lock))
		__mutex_lock_slowpath(lock);
}

static void origin_mutex_unlock(struct mutex *lock, unsigned long ret_addr)
{
#ifndef CONFIG_DEBUG_LOCK_ALLOC
	if (kd_mutex_unlock_fast(lock))
		return;
#endif
	__mutex_unlock_slowpath(lock, ret_addr);
}
