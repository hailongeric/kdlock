// SPDX-License-Identifier: GPL-2.0
/* Reader/ordinary-writer/delegated-writer phases around an unchanged KD mutex. */
#include <linux/module.h>
#include <linux/limits.h>
#include <linux/sched/signal.h>
#include "kd_rwsem.h"
#include "kd_lock.h"
#include "kd_mutex_local.h"

#define KD_RWSEM_LOCAL_WRITER (-1L)

/* Short holders often finish before a task can enqueue and be woken. Poll only
 * before publication, with at most 16384 condition probes. Writers remain
 * preemptible; the ordinary read slowpath pins only its abortable OSQ membership.
 * An individual predicate retains its existing atomic retry loop. Sleeping or
 * colocated holders still get the ordinary wait_event scheduling fallback.
 * A successful condition may acquire a reservation, so never evaluate it again
 * after success. The wait macro retains its enqueue/recheck ordering. */
#define kd_rwsem_poll(condition) ({ \
	unsigned int kd_rwsem_budget = 16384; \
	bool kd_rwsem_ready = false; \
	do { \
		if (condition) { \
			kd_rwsem_ready = true; \
			break; \
		} \
		if (need_resched()) \
			break; \
		cpu_relax(); \
	} while (--kd_rwsem_budget); \
	kd_rwsem_ready; \
})

#define kd_rwsem_wait(queue, condition) do { \
	if (!kd_rwsem_poll(condition)) \
		wait_event(queue, condition); \
} while (0)

/* Signalable callers stop spinning for any signal, but only the subsequent
 * wait decides whether that signal cancels this acquisition. Test the condition
 * first: it can consume the caller's one exact phase reservation. */
#define kd_rwsem_poll_state(condition, state) ({ \
	unsigned int kd_rwsem_budget = 16384; \
	bool kd_rwsem_ready = false; \
	do { \
		if (condition) { \
			kd_rwsem_ready = true; \
			break; \
		} \
		if (need_resched() || \
		    ((state) != TASK_UNINTERRUPTIBLE && signal_pending(current))) \
			break; \
		cpu_relax(); \
	} while (--kd_rwsem_budget); \
	kd_rwsem_ready; \
})

void kd_rwsem_init(struct kd_rwsem *sem)
{
	kd_mutex_init(&sem->gate);
	WRITE_ONCE(sem->prepared_writes, 0);
	atomic_long_set(&sem->readers, 0);
	atomic_long_set(&sem->admission, 0);
	init_waitqueue_head(&sem->phase_wait);
	init_waitqueue_head(&sem->reader_drain);
	osq_lock_init(&sem->reader_osq);
}
EXPORT_SYMBOL_GPL(kd_rwsem_init);

void __kd_init_rwsem(struct kd_rwsem *sem, const char *name, struct lock_class_key *key)
{
	/* The supported non-lockdep configuration has no dependency metadata. */
	(void)name;
	(void)key;
	kd_rwsem_init(sem);
}
EXPORT_SYMBOL_GPL(__kd_init_rwsem);

static void kd_rwsem_wake(wait_queue_head_t *queue)
{
	/* Call only after a full barrier or fully ordered count/phase RMW. Each
	 * predicate keeps its own queue: reader drainage cannot enable a closed
	 * admission phase. Ordering pairs with enqueue/recheck for this test. */
	if (waitqueue_active(queue))
		wake_up_all(queue);
}

void kd_up_read(struct kd_rwsem *sem)
{
	/* Trylock rollback and a matching read unlock may run under rq_lock.
	 * Never acquire a waitqueue/scheduler lock from that atomic context.
	 * Reader-drain waiters recheck on a timer, so omitting this wake cannot
	 * strand them. Check queue presence before reading caller context; the
	 * ordered decrement and enqueuer recheck cover an empty-queue race. No
	 * deferred reference outlives this decrement. */
	if (atomic_long_dec_and_test(&sem->readers) &&
	    waitqueue_active(&sem->reader_drain) &&
	    !irqs_disabled() && !in_atomic())
		kd_rwsem_wake(&sem->reader_drain);
}
EXPORT_SYMBOL_GPL(kd_up_read);

static int kd_rwsem_drain_readers(struct kd_rwsem *sem, unsigned int state)
{
	long ret;

	if (kd_rwsem_poll_state(!atomic_long_read_acquire(&sem->readers), state))
		return 0;
	/* An IRQ-disabled reader cannot safely wake a sleeping writer. Only
	 * schedulable, unpublished writers wait here; one-jiffy sleeps provide
	 * progress even when the last decrement omitted its wake. The timeout
	 * is a recheck, never permission to enter while a reader remains. */
	do {
		if (state == TASK_INTERRUPTIBLE)
			ret = wait_event_interruptible_timeout(sem->reader_drain,
				!atomic_long_read_acquire(&sem->readers), 1);
		else if (state == TASK_KILLABLE)
			ret = wait_event_killable_timeout(sem->reader_drain,
				!atomic_long_read_acquire(&sem->readers), 1);
		else
			ret = wait_event_timeout(sem->reader_drain,
				!atomic_long_read_acquire(&sem->readers), 1);
	} while (!ret);
	return ret < 0 ? -EINTR : 0;
}

int kd_down_read_trylock(struct kd_rwsem *sem)
{
	if (atomic_long_read(&sem->admission))
		return 0;
	/* Publish before checking the phase again. This full barrier and the
	 * writer's reservation RMW prohibit both missing each other's admission.
	 * A speculative count can overlap a writer, but cannot touch its payload. */
	atomic_long_inc_return(&sem->readers);
	if (!atomic_long_read_acquire(&sem->admission))
		return 1;
	kd_up_read(sem);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_trylock);

static bool kd_rwsem_spin_read(struct kd_rwsem *sem)
{
	struct kd_mutex_osq_node *node;
	bool acquired = false;

	/* Only the queue head retries shared reader admission. The other
	 * unpublished callers poll their own OSQ nodes instead of repeatedly
	 * invalidating the reader count when a writer closes the phase. Reuse
	 * a reserved mutex slot with independent OSQ links, never a delegation
	 * publication. Release it before scheduling or executing the read body. */
	preempt_disable();
	if (need_resched())
		goto out;
	node = kd_mutex_osq_node_get(&sem->gate);
	if (!node)
		goto out;
	if (kd_mutex_osq_lock(&sem->reader_osq, node)) {
		acquired = kd_rwsem_poll(kd_down_read_trylock(sem));
		kd_mutex_osq_unlock(&sem->reader_osq, node);
	}
	/* Abort also finishes all OSQ unlink accesses before returning. */
	kd_mutex_osq_node_put(node);
out:
	preempt_enable();
	/* Give the queued reader cohort a chance before starting another writer
	 * phase. The final unlink may enable writers sleeping on phase_wait, even
	 * when no writer phase changed. Pair the release-only OSQ tail update with
	 * their enqueue/recheck before testing the waitqueue. Never wake while a
	 * queue slot or the CPU pin is still held. */
	if (!atomic_read(&sem->reader_osq.tail)) {
		smp_mb();
		kd_rwsem_wake(&sem->phase_wait);
	}
	return acquired;
}

/* Keep wait-queue storage and its register/frame setup off the successful
 * first-attempt path. The caller already made the first of eight quick probes.
 * Its failed probe still gets the same reschedule check and PAUSE here. */
static noinline void kd_down_read_slowpath(struct kd_rwsem *sem)
{
	unsigned int retries = 7;

	if (need_resched())
		goto queued;
	cpu_relax();
	do {
		if (kd_down_read_trylock(sem))
			return;
		if (need_resched())
			break;
		cpu_relax();
	} while (--retries);
queued:
	if (kd_rwsem_spin_read(sem))
		return;
	wait_event(sem->phase_wait, kd_down_read_trylock(sem));
}

void kd_down_read(struct kd_rwsem *sem)
{
	might_sleep();
	if (likely(kd_down_read_trylock(sem)))
		return;
	kd_down_read_slowpath(sem);
}
EXPORT_SYMBOL_GPL(kd_down_read);

int kd_down_read_interruptible(struct kd_rwsem *sem)
{
	might_sleep();
	return wait_event_interruptible(sem->phase_wait, kd_down_read_trylock(sem)) ? -EINTR : 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_interruptible);

int kd_down_read_killable(struct kd_rwsem *sem)
{
	might_sleep();
	return wait_event_killable(sem->phase_wait, kd_down_read_trylock(sem)) ? -EINTR : 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_killable);

static bool kd_rwsem_reserve_local(struct kd_rwsem *sem)
{
	if (atomic_long_read(&sem->admission) ||
	    atomic_read(&sem->reader_osq.tail))
		return false;
	return atomic_long_cmpxchg(&sem->admission, 0, KD_RWSEM_LOCAL_WRITER) == 0;
}

static void kd_rwsem_release_local(struct kd_rwsem *sem)
{
	/* Every ordinary writer retains this exclusive phase until after its
	 * physical unlock. No delegated producer can have passed reader drain. */
	BUG_ON(atomic_long_xchg(&sem->admission, 0) != KD_RWSEM_LOCAL_WRITER);
	kd_rwsem_wake(&sem->phase_wait);
}

static __always_inline int kd_rwsem_wait_local(struct kd_rwsem *sem,
					      unsigned int state)
{
	if (kd_rwsem_poll_state(kd_rwsem_reserve_local(sem), state))
		return 0;
	if (state == TASK_INTERRUPTIBLE)
		return wait_event_interruptible(sem->phase_wait,
			kd_rwsem_reserve_local(sem)) ? -EINTR : 0;
	if (state == TASK_KILLABLE)
		return wait_event_killable(sem->phase_wait,
			kd_rwsem_reserve_local(sem)) ? -EINTR : 0;
	wait_event(sem->phase_wait, kd_rwsem_reserve_local(sem));
	return 0;
}

static __always_inline int kd_rwsem_lock_gate(struct kd_rwsem *sem,
					     unsigned int state)
{
	if (state == TASK_UNINTERRUPTIBLE) {
		kd_mutex_local_lock(&sem->gate);
		return 0;
	}
	/* Prepared local callers are still unpublished. Their phase-first order
	 * remains, while any pending signal can end gate spinning for both modes. */
	return kd_mutex_local_lock_signal(&sem->gate, state);
}

static __always_inline int kd_rwsem_down_write_state(struct kd_rwsem *sem,
						     unsigned int state)
{
	bool prepared = READ_ONCE(sem->prepared_writes);
	int ret;

	/* Preparation is quiescent and object-wide. Positive reservations need
	 * the gate, so only unprepared writers may queue at the gate first. */
	if (prepared) {
		ret = kd_rwsem_wait_local(sem, state);
		if (ret)
			return ret;
		ret = kd_rwsem_lock_gate(sem, state);
		if (ret)
			goto release_phase;
	} else {
		ret = kd_rwsem_lock_gate(sem, state);
		if (ret)
			return ret;
		ret = kd_rwsem_wait_local(sem, state);
		if (ret) {
			/* The gate may precede the prior writer's phase release.
			 * This caller has no phase to release until its own CAS. */
			kd_mutex_local_unlock(&sem->gate);
			return ret;
		}
	}
	ret = kd_rwsem_drain_readers(sem, state);
	if (!ret)
		return 0;
	kd_mutex_local_unlock(&sem->gate);
release_phase:
	/* Wait macros remove their waiter before rollback reopens admission. */
	kd_rwsem_release_local(sem);
	return ret;
}

void kd_down_write(struct kd_rwsem *sem)
{
	might_sleep();
	kd_rwsem_down_write_state(sem, TASK_UNINTERRUPTIBLE);
}
EXPORT_SYMBOL_GPL(kd_down_write);

int kd_down_write_interruptible(struct kd_rwsem *sem)
{
	might_sleep();
	return kd_rwsem_down_write_state(sem, TASK_INTERRUPTIBLE);
}
EXPORT_SYMBOL_GPL(kd_down_write_interruptible);

int kd_down_write_killable(struct kd_rwsem *sem)
{
	might_sleep();
	return kd_rwsem_down_write_state(sem, TASK_KILLABLE);
}
EXPORT_SYMBOL_GPL(kd_down_write_killable);

int kd_down_write_trylock(struct kd_rwsem *sem)
{
	if (!kd_rwsem_reserve_local(sem))
		return 0;
	if (kd_mutex_trylock(&sem->gate)) {
		if (!atomic_long_read_acquire(&sem->readers))
			return 1;
		kd_mutex_local_unlock(&sem->gate);
	}
	kd_rwsem_release_local(sem);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_write_trylock);

void kd_up_write(struct kd_rwsem *sem)
{
	/* Routing validates the exact successful physical/borrowed acquisition.
	 * A reservation is released only after this unlock has completed its ACK. */
	kd_mutex_api_unlock(&sem->gate);
	kd_rwsem_write_release(sem);
}
EXPORT_SYMBOL_GPL(kd_up_write);

void kd_downgrade_write(struct kd_rwsem *sem)
{
	BUG_ON(atomic_long_read(&sem->admission) != KD_RWSEM_LOCAL_WRITER ||
	       !kd_origin_mutex_owned(&sem->gate, current));
	/* Only the exclusive ordinary phase can downgrade. Publish this reader
	 * before reopening admission: any later D reservation must drain it while
	 * schedulable, before entering the legacy queue and pinning its producer. */
	atomic_long_inc(&sem->readers);
	kd_mutex_local_unlock(&sem->gate);
	kd_rwsem_release_local(sem);
}
EXPORT_SYMBOL_GPL(kd_downgrade_write);

/* Non-owner read release is explicit: the caller transfers the retained read
 * acquisition and object lifetime. This API does not infer transfer authority
 * from the aggregate reader count. Readers never delegate. */
void kd_down_read_non_owner(struct kd_rwsem *sem)
{
	kd_down_read(sem);
}
EXPORT_SYMBOL_GPL(kd_down_read_non_owner);

void kd_up_read_non_owner(struct kd_rwsem *sem)
{
	kd_up_read(sem);
}
EXPORT_SYMBOL_GPL(kd_up_read_non_owner);

int kd_rwsem_is_locked(struct kd_rwsem *sem)
{
	return atomic_long_read(&sem->readers) || atomic_long_read(&sem->admission);
}
EXPORT_SYMBOL_GPL(kd_rwsem_is_locked);

int kd_rwsem_is_contended(struct kd_rwsem *sem)
{
	/* An implementation-specific waiting hint, never admission/ownership. */
	return waitqueue_active(&sem->phase_wait) || waitqueue_active(&sem->reader_drain) ||
		atomic_read(&sem->reader_osq.tail) || READ_ONCE(sem->gate.wait_head) ||
		atomic_read(&sem->gate.osq.tail) || READ_ONCE(sem->gate.delegation_tail);
}
EXPORT_SYMBOL_GPL(kd_rwsem_is_contended);

void kd_rwsem_assert_held(const struct kd_rwsem *sem)
{
	WARN_ON(!atomic_long_read(&sem->readers) && !atomic_long_read(&sem->admission));
}
EXPORT_SYMBOL_GPL(kd_rwsem_assert_held);

void kd_rwsem_assert_held_write(const struct kd_rwsem *sem)
{
	/* Like the non-lockdep native assertion, this checks a writer state, not
	 * proof that the observing task owns an acquisition. */
	WARN_ON(!atomic_long_read(&sem->admission) ||
		!(atomic_long_read(&sem->gate.owner) & ~KD_MUTEX_OWNER_FLAGS));
}
EXPORT_SYMBOL_GPL(kd_rwsem_assert_held_write);

static bool kd_rwsem_reserve_delegate(struct kd_rwsem *sem)
{
	long phase = atomic_long_read(&sem->admission);

	while (phase >= 0 && phase < LONG_MAX) {
		/* Queue presence is a fairness hint, not ownership. A new cohort
		 * yields to queued local readers; an existing cohort keeps its exact
		 * reservation/ACK protocol. Recheck after CAS failure can reopen the
		 * phase. A racing enqueue still relies on the count/drain barriers. */
		if (!phase && atomic_read(&sem->reader_osq.tail))
			return false;
		/* Exact reservations also close reader/ordinary-writer admission.
		 * Use a full barrier before inspecting admitted readers. */
		if (atomic_long_try_cmpxchg(&sem->admission, &phase, phase + 1))
			return true;
	}
	return false;
}

void kd_rwsem_delegate_enter(struct kd_rwsem *sem)
{
	might_sleep();
	BUG_ON(!READ_ONCE(sem->prepared_writes));
	kd_rwsem_wait(sem->phase_wait, kd_rwsem_reserve_delegate(sem));
	/* No producer has published yet. A sleeping reader can resume even when
	 * it shares this CPU. Positive admission prevents new accepted readers or
	 * ordinary downgrades throughout every reservation in the cohort. */
	kd_rwsem_drain_readers(sem, TASK_UNINTERRUPTIBLE);
}
EXPORT_SYMBOL_GPL(kd_rwsem_delegate_enter);

void kd_rwsem_delegate_exit(struct kd_rwsem *sem)
{
	long remaining = atomic_long_dec_return(&sem->admission);

	BUG_ON(remaining < 0);
	if (!remaining)
		kd_rwsem_wake(&sem->phase_wait);
}
EXPORT_SYMBOL_GPL(kd_rwsem_delegate_exit);

void kd_rwsem_write_release(struct kd_rwsem *sem)
{
	/* The successful mutex unlock/ACK precedes this internal call. A local
	 * writer keeps -1 until release; a delegated origin retains its positive
	 * reservation through ACK. The phase selects the reservation to retire,
	 * and never substitutes for the mutex owner's exact acquisition record. */
	if (atomic_long_read(&sem->admission) == KD_RWSEM_LOCAL_WRITER)
		kd_rwsem_release_local(sem);
	else
		kd_rwsem_delegate_exit(sem);
}
EXPORT_SYMBOL_GPL(kd_rwsem_write_release);

bool kd_rwsem_is_idle(struct kd_rwsem *sem)
{
	return !atomic_long_read(&sem->admission) &&
		!atomic_long_read(&sem->readers) &&
		!waitqueue_active(&sem->phase_wait) &&
		!waitqueue_active(&sem->reader_drain) &&
		!atomic_read(&sem->reader_osq.tail) && kd_mutex_is_idle(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_rwsem_is_idle);
