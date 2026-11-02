// SPDX-License-Identifier: GPL-2.0
/* Exact selected writer phases and read credits around an unchanged KD mutex. */
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
	WRITE_ONCE(sem->selected_kind, KD_RWSEM_SELECTED_NONE);
	WRITE_ONCE(sem->selected_executor, NULL);
	WRITE_ONCE(sem->selected_request, NULL);
	WRITE_ONCE(sem->phase_generation, 0);
	atomic_long_set(&sem->readers, 0);
	atomic_long_set(&sem->admission, 0);
	atomic_long_set(&sem->queued, 0);
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
	 * strand them. No deferred reference outlives this ordered decrement. */
	if (atomic_long_dec_and_test(&sem->readers) &&
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

void kd_down_read(struct kd_rwsem *sem)
{
	unsigned int retries = 8;

	might_sleep();
	/* Avoid a queue round trip when a brief writer phase is about to end.
	 * Longer contention uses one optimistic admission head, not an entire
	 * cohort retrying the shared count for the full polling budget. */
	do {
		if (kd_down_read_trylock(sem))
			return;
		if (need_resched())
			break;
		cpu_relax();
	} while (--retries);
	if (kd_rwsem_spin_read(sem))
		return;
	wait_event(sem->phase_wait, kd_down_read_trylock(sem));
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
	/* Clear the selected identity before opening admission. A gate successor
	 * can already be waiting for this phase and must never erase its own record
	 * with a previous writer's delayed cleanup. Generation is not reset. */
	WRITE_ONCE(sem->selected_kind, KD_RWSEM_SELECTED_NONE);
	WRITE_ONCE(sem->selected_executor, NULL);
	WRITE_ONCE(sem->selected_request, NULL);
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
	/* A fast acquisition wins before signals. Only failed optimistic spinning
	 * yields for any signal; the native wait state still decides cancellation. */
	return kd_mutex_local_lock_signal(&sem->gate, state);
}

void kd_rwsem_request_init(struct kd_rwsem_request *request,
			   struct kd_rwsem *sem, struct task_struct *origin,
			   void *identity, u64 sequence)
{
	unsigned int previous = READ_ONCE(request->state);

	BUG_ON(!sem || !origin || !identity ||
	       (previous != KD_RWSEM_REQUEST_IDLE &&
		previous != KD_RWSEM_REQUEST_RELEASED));
	request->sem = sem;
	request->origin = origin;
	request->executor = NULL;
	request->generation = 0;
	request->identity = identity;
	request->sequence = sequence;
	BUG_ON(atomic_long_inc_return(&sem->queued) <= 0);
	/* The transport publishes its node only after this exact record exists. */
	smp_store_release(&request->state, KD_RWSEM_REQUEST_QUEUED);
}

void kd_rwsem_request_unqueue(struct kd_rwsem_request *request)
{
	struct kd_rwsem *sem = request->sem;

	/* A native handoff or canceled publication must already be unlinked. This
	 * operation cannot retire a selected writer or a downgraded reader. */
	BUG_ON(!sem || cmpxchg(&request->state, KD_RWSEM_REQUEST_QUEUED,
			       KD_RWSEM_REQUEST_CONSUMING) != KD_RWSEM_REQUEST_QUEUED);
	BUG_ON(atomic_long_dec_return(&sem->queued) < 0);
	smp_store_release(&request->state, KD_RWSEM_REQUEST_RELEASED);
}

int kd_rwsem_select_write(struct kd_rwsem *sem,
			  struct kd_rwsem_request *request,
			  unsigned int state, bool *selected)
{
	unsigned long generation;
	int ret;

	BUG_ON(!selected || !kd_origin_mutex_owned(&sem->gate, current));
	BUG_ON(request && (request->sem != sem || !request->origin ||
		READ_ONCE(request->state) != KD_RWSEM_REQUEST_QUEUED));
	*selected = false;
	ret = kd_rwsem_wait_local(sem, state);
	if (ret)
		return ret;
	BUG_ON(READ_ONCE(sem->selected_kind) != KD_RWSEM_SELECTED_NONE ||
	       READ_ONCE(sem->selected_executor) || READ_ONCE(sem->selected_request));
	generation = READ_ONCE(sem->phase_generation);
	BUG_ON(generation == ULONG_MAX);
	WRITE_ONCE(sem->phase_generation, ++generation);
	WRITE_ONCE(sem->selected_executor, current);
	WRITE_ONCE(sem->selected_request, request);
	WRITE_ONCE(sem->selected_kind, request ? KD_RWSEM_SELECTED_REQUEST :
						KD_RWSEM_SELECTED_LOCAL);
	if (request) {
		request->executor = current;
		request->generation = generation;
		/* The exact selected slot replaces, rather than duplicates, this
		 * node's queued reservation. No queue counter survives into READ. */
		BUG_ON(atomic_long_dec_return(&sem->queued) < 0);
		smp_store_release(&request->state, KD_RWSEM_REQUEST_WRITE);
	}
	*selected = true;
	/* Selection never reuses another request's drain observation. Signalable
	 * state here belongs to current; published-origin cancellation is a
	 * separate transport protocol and must not inspect executor signals. */
	return kd_rwsem_drain_readers(sem, state);
}

static void kd_rwsem_check_selected(struct kd_rwsem *sem,
				   struct kd_rwsem_request *request)
{
	BUG_ON(atomic_long_read(&sem->admission) != KD_RWSEM_LOCAL_WRITER ||
	       READ_ONCE(sem->selected_executor) != current ||
	       READ_ONCE(sem->selected_request) != request ||
	       READ_ONCE(sem->selected_kind) !=
		(request ? KD_RWSEM_SELECTED_REQUEST : KD_RWSEM_SELECTED_LOCAL));
	BUG_ON(request && (request->sem != sem || request->executor != current ||
		request->generation != READ_ONCE(sem->phase_generation)));
}

void kd_rwsem_release_write(struct kd_rwsem *sem,
			    struct kd_rwsem_request *request)
{
	kd_rwsem_check_selected(sem, request);
	if (request)
		BUG_ON(cmpxchg(&request->state, KD_RWSEM_REQUEST_WRITE,
			       KD_RWSEM_REQUEST_CONSUMING) != KD_RWSEM_REQUEST_WRITE);
	/* A pure delegated endpoint may retain physical gate custody. Opening the
	 * phase admits readers, so even that same executor must select and freshly
	 * drain before its next writer body. Local physical unlock precedes here. */
	kd_rwsem_release_local(sem);
	if (request)
		smp_store_release(&request->state, KD_RWSEM_REQUEST_RELEASED);
}

void kd_rwsem_begin_downgrade(struct kd_rwsem *sem,
			      struct kd_rwsem_request *request)
{
	kd_rwsem_check_selected(sem, request);
	BUG_ON(!kd_origin_mutex_owned(&sem->gate, current));
	BUG_ON(request && READ_ONCE(request->state) != KD_RWSEM_REQUEST_WRITE);
	/* This fully ordered publication precedes both the physical gate release
	 * and admission reopening: no writer can pass between WRITE and READ. */
	atomic_long_inc_return(&sem->readers);
	if (request)
		smp_store_release(&request->state, KD_RWSEM_REQUEST_READ);
}

void kd_rwsem_finish_downgrade(struct kd_rwsem *sem,
			       struct kd_rwsem_request *request)
{
	kd_rwsem_check_selected(sem, request);
	BUG_ON(request && READ_ONCE(request->state) != KD_RWSEM_REQUEST_READ);
	/* The runtime has completed physical unlock/ACK. The request retains its
	 * read credit, continuation and source; reopening is not body completion. */
	kd_rwsem_release_local(sem);
}

void kd_rwsem_finish_read(struct kd_rwsem_request *request)
{
	struct kd_rwsem *sem = request->sem;

	BUG_ON(!sem || request->executor != current || !request->generation ||
	       cmpxchg(&request->state, KD_RWSEM_REQUEST_READ,
		       KD_RWSEM_REQUEST_CONSUMING) != KD_RWSEM_REQUEST_READ);
	/* A later selected writer may already own admission while draining this
	 * credit. Neither its generation nor its phase belongs to this release.
	 * Do not touch the object after the fully ordered final decrement. Timed
	 * writer drainage also progresses when an atomic release omits a wake. */
	BUG_ON(atomic_long_dec_return(&sem->readers) < 0);
	smp_store_release(&request->state, KD_RWSEM_REQUEST_RELEASED);
}

static __always_inline int kd_rwsem_down_write_state(struct kd_rwsem *sem,
						     unsigned int state)
{
	bool selected;
	int ret;

	/* All writers acquire the gate before closing their selected phase. Queued
	 * publications never hold admission, so prepared callers cannot self-wait
	 * on a positive cohort while a downgraded read tail remains active. */
	ret = kd_rwsem_lock_gate(sem, state);
	if (ret)
		return ret;
	ret = kd_rwsem_select_write(sem, NULL, state, &selected);
	if (!ret)
		return 0;
	kd_mutex_local_unlock(&sem->gate);
	/* Wait macros remove their waiter before rollback reopens admission. A
	 * failed prior-phase wait never owns the preceding writer's reservation. */
	if (selected)
		kd_rwsem_release_write(sem, NULL);
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
	bool selected = false;
	unsigned long generation;

	if (!kd_mutex_trylock(&sem->gate))
		return 0;
	if (kd_rwsem_reserve_local(sem)) {
		BUG_ON(READ_ONCE(sem->selected_kind) != KD_RWSEM_SELECTED_NONE);
		generation = READ_ONCE(sem->phase_generation);
		BUG_ON(generation == ULONG_MAX);
		WRITE_ONCE(sem->phase_generation, ++generation);
		WRITE_ONCE(sem->selected_executor, current);
		WRITE_ONCE(sem->selected_request, NULL);
		WRITE_ONCE(sem->selected_kind, KD_RWSEM_SELECTED_LOCAL);
		selected = true;
		if (!atomic_long_read_acquire(&sem->readers))
			return 1;
	}
	kd_mutex_local_unlock(&sem->gate);
	if (selected)
		kd_rwsem_release_write(sem, NULL);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_write_trylock);

void kd_up_write(struct kd_rwsem *sem)
{
	/* Routing validates the exact successful physical/borrowed acquisition.
	 * Callable/native-body writers retain their exact local selected phase
	 * through this physical unlock/ACK. Delegated endpoints use their record. */
	kd_mutex_api_unlock(&sem->gate);
	kd_rwsem_release_write(sem, NULL);
}
EXPORT_SYMBOL_GPL(kd_up_write);

void kd_downgrade_write(struct kd_rwsem *sem)
{
	kd_rwsem_begin_downgrade(sem, NULL);
	/* Typed continuation entry can own the scheduling gate and task reference;
	 * exact public routing retires those as well as the physical primitive. */
	kd_mutex_api_unlock(&sem->gate);
	kd_rwsem_finish_downgrade(sem, NULL);
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
	WARN_ON(atomic_long_read(&sem->admission) != KD_RWSEM_LOCAL_WRITER ||
		READ_ONCE(sem->selected_kind) == KD_RWSEM_SELECTED_NONE);
}
EXPORT_SYMBOL_GPL(kd_rwsem_assert_held_write);

bool kd_rwsem_is_idle(struct kd_rwsem *sem)
{
	return !atomic_long_read(&sem->admission) &&
		!atomic_long_read(&sem->readers) &&
		!atomic_long_read(&sem->queued) &&
		READ_ONCE(sem->selected_kind) == KD_RWSEM_SELECTED_NONE &&
		!READ_ONCE(sem->selected_executor) && !READ_ONCE(sem->selected_request) &&
		!waitqueue_active(&sem->phase_wait) &&
		!waitqueue_active(&sem->reader_drain) &&
		!atomic_read(&sem->reader_osq.tail) && kd_mutex_is_idle(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_rwsem_is_idle);
