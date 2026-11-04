// SPDX-License-Identifier: GPL-2.0
/* Local readers and one exact selected writer phase around KD exclusion. */
#include <linux/module.h>
#include <linux/limits.h>
#include <linux/sched/signal.h>
#include "kd_rwsem.h"
#include "kd_lock.h"
#include "kd_mutex_local.h"
#include "kd_admission.h"

#define KD_RWSEM_LOCAL_WRITER (-1L)

static_assert(sizeof(struct kd_rwsem) == 320);
static_assert(offsetof(struct kd_rwsem, selected_kind) == 36);
static_assert(offsetof(struct kd_rwsem, selected_owner) == 40);
static_assert(offsetof(struct kd_rwsem, selected_identity) == 48);
static_assert(offsetof(struct kd_rwsem, phase_generation) == 56);
static_assert(offsetof(struct kd_rwsem, readers) == 64);
static_assert(offsetof(struct kd_rwsem, admission) == 128);

/* Short holders often finish before a task can enqueue and be woken. Poll only
 * before publication, with at most 16384 condition probes. Writers remain
 * preemptible; the ordinary read slowpath pins only its abortable OSQ membership.
 * An individual predicate retains its existing atomic retry loop. Sleeping or
 * colocated holders still get the condition-channel scheduling fallback.
 * A successful condition may acquire a reservation, so never evaluate it again
 * after success. The condition adapter retains enqueue/recheck ordering. */
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

enum kd_rwsem_condition_kind {
	KD_RWSEM_CONDITION_READ,
};

static int
kd_rwsem_try_read(struct kd_rwsem *sem, bool notify);

static bool kd_rwsem_condition_ready(struct kd_rwsem *sem,
				     enum kd_rwsem_condition_kind kind,
				     bool guarded)
{
	switch (kind) {
	case KD_RWSEM_CONDITION_READ:
		/* A speculative rollback under wait_lock cannot notify a drain queue
		 * using that same guard. Its timed recheck provides progress instead. */
		return kd_rwsem_try_read(sem, !guarded);
	}
	BUG();
}

/* This short-lived reader descriptor owns condition membership only. It never
 * elects a writer acquisition or captures a continuation. Selected writers use
 * their canonical admission's distinct phase/drain condition membership.
 * Every node access finishes under the object's guard before this wait returns. */
static long kd_rwsem_wait_condition(struct kd_rwsem *sem,
				    struct kd_rwsem_condition *condition,
				    enum kd_rwsem_condition_kind kind,
				    unsigned int state, bool timed)
{
	struct kd_wait_queue queue = kd_wait_queue_view(&sem->gate.wait_lock,
						       &condition->head);
	struct kd_wait_request request;
	struct kd_wait_node node;
	unsigned long flags;
	long remaining = 1, result = 0;

	if (kd_rwsem_condition_ready(sem, kind, false))
		return timed ? 1 : 0;
	flags = _raw_spin_lock_irqsave(queue.guard);
	kd_wait_request_init(&request, NULL, 0,
			     current, current, state, false, sem);
	kd_wait_node_init(&node, &request, KD_WAIT_CONDITION);
	kd_wait_link_locked(&queue, &node);
	BUG_ON(condition != &sem->phase_wait ||
	       condition->readers_waiting == U64_MAX);
	++condition->readers_waiting;
	for (;;) {
		/* Publish the state before checking signals. A signal between the
		 * predicate and schedule then either sets RUNNING or is observed here. */
		set_current_state(state);
		if (kd_rwsem_condition_ready(sem, kind, true)) {
			result = timed ? 1 : 0;
			break;
		}
		if (signal_pending_state(state, current)) {
			result = -ERESTARTSYS;
			break;
		}
		if (timed && !remaining)
			break;
		_raw_spin_unlock_irqrestore(queue.guard, flags);
		if (timed)
			remaining = schedule_timeout(remaining);
		else
			/* Phase reopening is the final object RMW after wake collection.
			 * A reader can link in that interval; retry its real predicate
			 * on a timer even if it missed that earlier notification. */
			schedule_timeout(1);
		flags = _raw_spin_lock_irqsave(queue.guard);
	}
	__set_current_state(TASK_RUNNING);
	BUG_ON(!condition->readers_waiting);
	--condition->readers_waiting;
	kd_wait_unlink_locked(&queue, &node);
	BUG_ON(request.memberships || request.acquisition || request.selection);
	kd_wait_set_state_locked(&request, KD_WAIT_RETIRED);
	_raw_spin_unlock_irqrestore(queue.guard, flags);
	return result;
}

void kd_rwsem_init(struct kd_rwsem *sem)
{
	kd_mutex_init(&sem->gate);
	WRITE_ONCE(sem->prepared_writes, 0);
	sem->selected_kind = KD_RWSEM_PHASE_NONE;
	sem->selected_owner = NULL;
	sem->selected_identity = NULL;
	sem->phase_generation = 0;
	atomic_long_set(&sem->readers, 0);
	atomic_long_set(&sem->admission, 0);
	sem->phase_wait.head = NULL;
	sem->phase_wait.readers_waiting = 0;
	sem->phase_wait.reserved = 0;
	sem->reader_drain.head = NULL;
	sem->reader_drain.readers_waiting = 0;
	sem->reader_drain.reserved = 0;
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

static void kd_rwsem_wake(struct kd_rwsem *sem,
			  struct kd_rwsem_condition *condition)
{
	struct kd_wait_queue queue = kd_wait_queue_view(&sem->gate.wait_lock,
						       &condition->head);
	DEFINE_WAKE_Q(wake);
	unsigned long flags;

	/* Call only after a full barrier or fully ordered count/phase RMW. Each
	 * predicate keeps its own queue: reader drainage cannot enable a closed
	 * admission phase. Ordering pairs with enqueue/recheck for this test. */
	if (!READ_ONCE(condition->head))
		return;
	flags = _raw_spin_lock_irqsave(queue.guard);
	kd_wait_collect_wake_locked(&queue, &wake);
	_raw_spin_unlock_irqrestore(queue.guard, flags);
	/* Collection owns task references only; canceled stack nodes can already
	 * have retired when scheduler delivery runs after releasing the guard. */
	wake_up_q(&wake);
}

void kd_up_read(struct kd_rwsem *sem)
{
	/* Trylock rollback and a matching read unlock may run under rq_lock.
	 * Never acquire a waitqueue/scheduler lock from that atomic context.
	 * Every reader-drain waiter rechecks on a timer. The final credit may
	 * let a writer retire the object immediately, so no object access or
	 * deferred notification can follow this fully ordered decrement. */
	(void)atomic_long_dec_and_test(&sem->readers);
}
EXPORT_SYMBOL_GPL(kd_up_read);

static int kd_rwsem_try_read(struct kd_rwsem *sem, bool notify)
{
	if (atomic_long_read(&sem->admission))
		return 0;
	/* Publish before checking the phase again. This full barrier and the
	 * writer's reservation RMW prohibit both missing each other's admission.
	 * A speculative count can overlap a writer, but cannot touch its payload. */
	atomic_long_inc_return(&sem->readers);
	if (!atomic_long_read_acquire(&sem->admission))
		return 1;
	if (notify) {
		kd_up_read(sem);
	} else {
		(void)atomic_long_dec_and_test(&sem->readers);
	}
	return 0;
}

int kd_down_read_trylock(struct kd_rwsem *sem)
{
	return kd_rwsem_try_read(sem, true);
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
		kd_rwsem_wake(sem, &sem->phase_wait);
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
	kd_rwsem_wait_condition(sem, &sem->phase_wait,
		KD_RWSEM_CONDITION_READ, TASK_UNINTERRUPTIBLE, false);
}
EXPORT_SYMBOL_GPL(kd_down_read);

int kd_down_read_interruptible(struct kd_rwsem *sem)
{
	might_sleep();
	return kd_rwsem_wait_condition(sem, &sem->phase_wait,
		KD_RWSEM_CONDITION_READ, TASK_INTERRUPTIBLE, false) ? -EINTR : 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_interruptible);

int kd_down_read_killable(struct kd_rwsem *sem)
{
	might_sleep();
	return kd_rwsem_wait_condition(sem, &sem->phase_wait,
		KD_RWSEM_CONDITION_READ, TASK_KILLABLE, false) ? -EINTR : 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_killable);

static void kd_rwsem_release_local(struct kd_rwsem *sem)
{
	struct kd_wait_queue queue = kd_wait_queue_view(&sem->gate.wait_lock,
						       &sem->phase_wait.head);
	DEFINE_WAKE_Q(wake);
	unsigned long flags;

	/* The physical release has completed, but -1 still retains this exact
	 * logical writer phase. A later gate owner must wait for the final RMW. */
	flags = _raw_spin_lock_irqsave(queue.guard);
	BUG_ON(sem->selected_kind != KD_RWSEM_PHASE_LOCAL ||
	       sem->selected_owner != current || !sem->selected_identity ||
	       atomic_long_read(&sem->admission) != KD_RWSEM_LOCAL_WRITER);
	sem->selected_kind = KD_RWSEM_PHASE_NONE;
	sem->selected_owner = NULL;
	sem->selected_identity = NULL;
	kd_wait_collect_wake_locked(&queue, &wake);
	_raw_spin_unlock_irqrestore(queue.guard, flags);
	/* No object access follows reopening admission. Collected task references
	 * are independent of object/stack membership lifetime. */
	BUG_ON(atomic_long_xchg(&sem->admission, 0) != KD_RWSEM_LOCAL_WRITER);
	wake_up_q(&wake);
}

static __always_inline int kd_rwsem_down_write_state(struct kd_rwsem *sem,
						     unsigned int state)
{
	struct kd_wait_request request;
	struct kd_admission admission;
	unsigned long flags;
	int ret;

	kd_wait_request_init(&request, NULL, 0, current, current, state, false, NULL);
	kd_admission_init(&admission, &request, KD_ADMISSION_RWSEM_WRITE, sem, NULL);
	ret = kd_admission_wait(&admission, NULL, NULL);
	if (!ret) {
		flags = _raw_spin_lock_irqsave(&sem->gate.wait_lock);
		kd_admission_detach_local_locked(&admission);
		_raw_spin_unlock_irqrestore(&sem->gate.wait_lock, flags);
	} else {
		flags = _raw_spin_lock_irqsave(request.guard);
		kd_wait_set_state_locked(&request, KD_WAIT_RETIRED);
		_raw_spin_unlock_irqrestore(request.guard, flags);
	}
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
	struct kd_wait_request request;
	unsigned long flags;
	bool gate_held = false;
	int acquired = 0;

	/* Trylock is bounded and does not publish, allocate, sleep or alter the
	 * caller's IRQ/preemption state. No partial phase is visible on failure. */
	kd_wait_request_init(&request, NULL, 0, current, current,
			     TASK_UNINTERRUPTIBLE, false, NULL);
	local_irq_save(flags);
	if (!_raw_spin_trylock(&sem->gate.wait_lock))
		goto restore;
	if (sem->gate.wait_head || sem->phase_wait.readers_waiting ||
	    atomic_long_read(&sem->admission))
		goto unlock;
	gate_held = kd_mutex_admission_trylock_locked(&sem->gate, &request);
	if (!gate_held)
		goto unlock;
	if (atomic_long_cmpxchg(&sem->admission, 0, KD_RWSEM_LOCAL_WRITER))
		goto unlock;
	if (!atomic_long_read_acquire(&sem->readers)) {
		BUG_ON(sem->selected_kind != KD_RWSEM_PHASE_NONE ||
		       sem->phase_generation == U64_MAX);
		++sem->phase_generation;
		sem->selected_kind = KD_RWSEM_PHASE_LOCAL;
		sem->selected_owner = current;
		sem->selected_identity = request.identity;
		acquired = 1;
	} else {
		BUG_ON(atomic_long_xchg(&sem->admission, 0) != KD_RWSEM_LOCAL_WRITER);
	}
unlock:
	_raw_spin_unlock(&sem->gate.wait_lock);
	/* No public acquisition occurred on failure. The tentative physical
	 * owner must still retire its gate before returning false. */
	if (gate_held && !acquired)
		kd_mutex_local_unlock(&sem->gate);
restore:
	local_irq_restore(flags);
	return acquired;
}
EXPORT_SYMBOL_GPL(kd_down_write_trylock);

void kd_up_write(struct kd_rwsem *sem)
{
	BUG_ON(READ_ONCE(sem->selected_kind) != KD_RWSEM_PHASE_LOCAL ||
	       READ_ONCE(sem->selected_owner) != current);
	kd_mutex_api_unlock(&sem->gate);
	kd_rwsem_release_local(sem);
}
EXPORT_SYMBOL_GPL(kd_up_write);

void kd_downgrade_write(struct kd_rwsem *sem)
{
	BUG_ON(READ_ONCE(sem->selected_kind) != KD_RWSEM_PHASE_LOCAL ||
	       READ_ONCE(sem->selected_owner) != current ||
	       atomic_long_read(&sem->admission) != KD_RWSEM_LOCAL_WRITER ||
	       !kd_origin_mutex_owned(&sem->gate, current));
	/* Read credit is fully ordered before physical/phase release. A later
	 * writer obtains a new selected phase and freshly drains this exact tail. */
	atomic_long_inc_return(&sem->readers);
	kd_mutex_api_unlock(&sem->gate);
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
	return READ_ONCE(sem->phase_wait.head) || READ_ONCE(sem->reader_drain.head) ||
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

bool kd_rwsem_is_idle(struct kd_rwsem *sem)
{
	return !atomic_long_read(&sem->admission) &&
		!atomic_long_read(&sem->readers) &&
		READ_ONCE(sem->selected_kind) == KD_RWSEM_PHASE_NONE &&
		!READ_ONCE(sem->selected_owner) && !READ_ONCE(sem->selected_identity) &&
		!READ_ONCE(sem->phase_wait.head) &&
		!READ_ONCE(sem->reader_drain.head) &&
		!atomic_read(&sem->reader_osq.tail) && kd_mutex_is_idle(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_rwsem_is_idle);
