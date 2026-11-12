// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock ww_mutex: a kdlock mutex plus the acquire context that holds it.
 *
 * A task that takes several ww mutexes of one class in arbitrary order
 * uses one acquire context, stamped when it starts. Deadlocks are avoided
 * by never letting a younger context that already holds a lock wait for an
 * older one: it gets -EDEADLK, releases what it holds and starts over with
 * kd_ww_mutex_lock_slow() on the lock it lost. That is the wait-die rule,
 * applied here to every class; the native wound-wait alternative differs
 * in who backs off, not in what callers must handle.
 *
 * Why this cannot deadlock: a context waits only for holders younger than
 * itself, or while it holds nothing. Along any chain of waiting contexts
 * the stamps therefore decrease, so the chain cannot close. The rule must
 * hold for whoever holds the lock *now*, so a context that acquires a lock
 * wakes the parked waiters that would have to back off from it
 * (kd_ww_check_waiters()), and every parked waiter rechecks when it wakes.
 *
 * ww mutexes are never delegated: acquisition is trylock, then the parked
 * path of the mutex with the back-off check in its loop.
 */
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/sched.h>
#include <linux/ww_mutex.h>
#include "kd_internal.h"

void kd_ww_mutex_init(struct kd_ww_mutex *lock, struct ww_class *ww_class)
{
	kd_mutex_init(&lock->base);
	lock->ctx = NULL;
}
EXPORT_SYMBOL(kd_ww_mutex_init);

/* Is @a younger than @b? Stamps wrap, as in the native implementation. */
static __always_inline bool kd_ww_younger(struct ww_acquire_ctx *a, struct ww_acquire_ctx *b)
{
	return (signed long)(a->stamp - b->stamp) > 0;
}

/* Must context @ctx, holding @ctx->acquired locks, back off from @holder? */
static __always_inline bool kd_ww_dies(struct ww_acquire_ctx *ctx, struct ww_acquire_ctx *holder)
{
	return holder && holder != ctx && ctx->acquired > 0 && kd_ww_younger(ctx, holder);
}

/* Called by the parked wait loop under the mutex's wait lock. */
bool kd_ww_must_back_off(struct kd_ww_wait *ww)
{
	return kd_ww_dies(ww->ctx, READ_ONCE(ww->lock->ctx));
}

static bool kd_ww_waiter_dies(struct ww_acquire_ctx *waiter, void *holder)
{
	return kd_ww_dies(waiter, holder);
}

/*
 * @ctx now holds @lock. Record it, and make every parked waiter that must
 * not wait for @ctx look again. The store, a full barrier, then the flag
 * read pair with a parking waiter's flag set (full barrier) followed by
 * its read of ->ctx: one of the two sees the other.
 */
static void kd_ww_set_ctx(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	ctx->acquired++;
	WRITE_ONCE(lock->ctx, ctx);
	smp_mb();
	if (READ_ONCE(lock->base.q.flags) & KD_QF_SLEEPERS)
		kd_mutex_wake_matching(&lock->base, kd_ww_waiter_dies, ctx);
}

static int __kd_ww_mutex_lock(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx,
			      unsigned int state, bool slow)
{
	struct kd_ww_wait ww = { .lock = lock, .ctx = ctx };
	int ret;

	might_sleep();
	if (ctx && READ_ONCE(lock->ctx) == ctx)
		return -EALREADY;
	if (!kd_mutex_trylock(&lock->base)) {
		/*
		 * After a back-off the context holds nothing and waits
		 * unconditionally; kd_ww_dies() already says so.
		 */
		ret = kd_mutex_sleep(&lock->base, state, ctx ? &ww : NULL);
		if (ret)
			return ret;
	}
	if (ctx)
		kd_ww_set_ctx(lock, ctx);
	return 0;
}

int kd_ww_mutex_lock(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	return __kd_ww_mutex_lock(lock, ctx, TASK_UNINTERRUPTIBLE, false);
}
EXPORT_SYMBOL(kd_ww_mutex_lock);

int kd_ww_mutex_lock_interruptible(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	return __kd_ww_mutex_lock(lock, ctx, TASK_INTERRUPTIBLE, false);
}
EXPORT_SYMBOL(kd_ww_mutex_lock_interruptible);

/* After -EDEADLK and releasing every lock of @ctx: wait for the lost lock. */
void kd_ww_mutex_lock_slow(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	int ret = __kd_ww_mutex_lock(lock, ctx, TASK_UNINTERRUPTIBLE, true);

	WARN_ON_ONCE(ret);
}
EXPORT_SYMBOL(kd_ww_mutex_lock_slow);

int kd_ww_mutex_lock_slow_interruptible(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	return __kd_ww_mutex_lock(lock, ctx, TASK_INTERRUPTIBLE, true);
}
EXPORT_SYMBOL(kd_ww_mutex_lock_slow_interruptible);

int kd_ww_mutex_trylock(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	if (!kd_mutex_trylock(&lock->base))
		return 0;
	if (ctx)
		kd_ww_set_ctx(lock, ctx);
	return 1;
}
EXPORT_SYMBOL(kd_ww_mutex_trylock);

void kd_ww_mutex_unlock(struct kd_ww_mutex *lock)
{
	struct ww_acquire_ctx *ctx = lock->ctx;

	if (ctx) {
		ctx->acquired--;
		WRITE_ONCE(lock->ctx, NULL);
	}
	kd_mutex_unlock(&lock->base);
}
EXPORT_SYMBOL(kd_ww_mutex_unlock);
