// SPDX-License-Identifier: GPL-2.0
/*
 * KD physical exclusion. Ordinary non-RT mutex and OSQ algorithms derived from
 * captured Linux 6.1.159 kernel/locking/mutex.c; see mutex/linux-source.json.
 * This owns no Linux mutex and calls no Linux mutex API. Delegation admission
 * shares the guarded request queue with local admission.
 *
 * WAITERS/HANDOFF/PICKUP serialize sleeping callers and prevent a designated
 * handoff from being stolen or cancelled without pickup. wait_lock orders
 * cancellation against unlock, and the wake queue retains the task reference.
 */
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/kallsyms.h>
#include <linux/sched/task.h>
#include <linux/sched/wake_q.h>
#include "kd_mutex.h"
#include "kd_mutex_local.h"

#define KD_WAITERS 1UL
#define KD_HANDOFF 2UL
#define KD_PICKUP 4UL
#define KD_FLAGS 7UL
static_assert(__alignof__(struct task_struct) >= 8);

void kd_mutex_init(struct kd_mutex *lock)
{
	atomic_long_set(&lock->owner, 0);
	osq_lock_init(&lock->osq);
	raw_spin_lock_init(&lock->wait_lock);
	lock->wait_head = NULL;
	atomic_set(&lock->delegation_state, 0);
	lock->delegation_tail = 0;
}
EXPORT_SYMBOL_GPL(kd_mutex_init);

void __kd_mutex_init(struct kd_mutex *lock, const char *name,
		     struct lock_class_key *key)
{
	/* Lockdep is not enabled in the supported configuration. */
	(void)name;
	(void)key;
	kd_mutex_init(lock);
}
EXPORT_SYMBOL_GPL(__kd_mutex_init);

/* Scheduler helpers are not exports in the captured external-module kernel.
 * Resolve once during provider initialization, before publishing any caller.
 * These are I/O accounting helpers, not mutex operations or object adapters.
 */
static int (*kd_io_prepare)(void);
static void (*kd_io_finish)(int);
int kd_mutex_local_runtime_init(void)
{
	kd_io_prepare = (void *)kallsyms_lookup_name("io_schedule_prepare");
	kd_io_finish = (void *)kallsyms_lookup_name("io_schedule_finish");
	return kd_io_prepare && kd_io_finish ? 0 : -ENOENT;
}

void kd_mutex_local_runtime_exit(void)
{
	/* The shared preallocated node pool belongs to mutex lifecycle. */
}

/* The queue node has no execution authority. Local storage stays on the
 * submitter's stack until guarded unlink/ACK; captured storage is retained by
 * its independently reserved slot. Both use the same mutex head and guard. */
static struct task_struct *kd_owner(struct kd_mutex *lock)
{
	return (void *)(atomic_long_read(&lock->owner) & ~KD_FLAGS);
}

static __always_inline struct task_struct *kd_try_common(struct kd_mutex *lock, bool handoff)
{
	unsigned long owner = atomic_long_read(&lock->owner);
	unsigned long curr = (unsigned long)current;

	for (;;) {
		unsigned long flags = owner & KD_FLAGS;
		unsigned long task = owner & ~KD_FLAGS;

		if (task) {
			if (flags & KD_PICKUP) {
				if (task != curr)
					break;
				flags &= ~KD_PICKUP;
			} else if (handoff) {
				if (flags & KD_HANDOFF)
					break;
				flags |= KD_HANDOFF;
			} else {
				break;
			}
		} else {
			BUG_ON(flags & (KD_HANDOFF | KD_PICKUP));
			task = curr;
		}
		if (atomic_long_try_cmpxchg_acquire(&lock->owner, &owner, task | flags)) {
			if (task == curr)
				return NULL;
			break;
		}
	}
	return (void *)(owner & ~KD_FLAGS);
}

bool kd_mutex_local_trylock_locked(struct kd_mutex *lock, bool handoff)
{
	return !kd_try_common(lock, handoff);
}

void kd_mutex_wake_head_locked(struct kd_mutex *lock)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(lock);
	struct kd_wait_node *head = kd_wait_first_locked(&queue);
	struct kd_wait_request *request;
	struct kd_mutex_node *node;

	if (!head || atomic_read(&lock->delegation_state) == KD_MUTEX_GATE_COMBINER)
		return;
	request = head->request;
	if (!request->may_delegate || request->state != KD_WAIT_QUEUED)
		return;
	node = request->context;
	BUG_ON(!node || node->lock != lock);
	BUG_ON(!kd_wait_select_locked(&queue, request, &request->local_selection,
				     request->physical_waiter));
	/* The origin polls retained notification only. Selection prevents a
	 * combiner from dispatching the same request while it acquires locally. */
	smp_store_release(&node->locked, 0);
}

/* schedule_preempt_disabled and wake_q_add are not module exports. */
static void kd_local_schedule(void)
{
	barrier();
	preempt_count_dec();
	schedule();
	preempt_disable();
}

static void kd_local_wake_add(struct wake_q_head *head, struct task_struct *task)
{
	struct wake_q_node *node = &task->wake_q;

	smp_mb__before_atomic();
	if (cmpxchg_relaxed(&node->next, NULL, WAKE_Q_TAIL))
		return;
	get_task_struct(task);
	*head->lastp = node;
	head->lastp = &node->next;
}

static __always_inline bool kd_local_spin_common(struct kd_mutex *lock, bool waiter,
						struct kd_mutex_node *borrowed,
						bool stop_signals)
{
	struct task_struct *owner;
	struct kd_mutex_osq_node *node = NULL;
	bool acquired = false;

	if (!waiter) {
		if (need_resched() || (stop_signals && signal_pending(current)))
			goto fail;
		owner = kd_owner(lock);
		if (owner && !owner_on_cpu(owner))
			goto fail;
		node = borrowed ? &borrowed->osq : kd_mutex_osq_node_get(lock);
		if (!node)
			goto fail;
		if (!(stop_signals ? kd_mutex_osq_lock_signal(&lock->osq, node) :
		      kd_mutex_osq_lock(&lock->osq, node)))
			goto release;
	}
	for (;;) {
		owner = kd_try_common(lock, false);
		if (!owner) {
			acquired = true;
			break;
		}
		if (stop_signals && signal_pending(current))
			goto done;
		while (kd_owner(lock) == owner) {
			/* Preemption pins the RCU lifetime; recheck before dereference. */
			barrier();
			if (!owner_on_cpu(owner) || need_resched() ||
			    (stop_signals && signal_pending(current)))
				goto done;
			cpu_relax();
		}
		/* Match the captured legacy optimistic-spin retry: after the owner
		 * changes, relax before trying the shared owner word again. */
		cpu_relax();
	}
done:
	if (!waiter)
		kd_mutex_osq_unlock(&lock->osq, node);
release:
	/* A cancellation-false return has also finished every queue access.
	 * Release only temporary native reservations, before any scheduling. */
	if (node && !borrowed)
		kd_mutex_osq_node_put(node);
	if (acquired)
		return true;
fail:
	if (need_resched()) {
		__set_current_state(TASK_RUNNING);
		kd_local_schedule();
	}
	return false;
}

/* These are internal wait-list spinlocks. Use native raw-spin functions,
 * bypassing the captured kernel's public caller-clobber macro wrappers. */
static bool kd_local_grant(struct kd_wait_request *request, void *argument)
{
	struct kd_mutex *lock = argument;

	BUG_ON(request->physical_waiter != current);
	return !kd_try_common(lock, lock->wait_head == request->acquisition);
}

static __always_inline int
kd_local_lock_slow_common(struct kd_mutex *lock, unsigned int state,
			  struct kd_mutex_node *borrowed, bool stop_signals)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(lock);
	struct kd_wait_request local_request;
	struct kd_wait_node local_member;
	struct kd_wait_node *member;
	struct kd_wait_request *request;
	unsigned long irq_flags;
	int ret = 0;

	preempt_disable();
	member = borrowed ? kd_mutex_request_member(borrowed) : &local_member;
	if (!borrowed) {
		if (!kd_try_common(lock, false) ||
		    kd_local_spin_common(lock, false, NULL, stop_signals))
			goto out;
		kd_wait_request_init(&local_request, NULL, 0, current,
				     current, state, false, NULL);
		kd_wait_node_init(member, &local_request, KD_WAIT_ACQUISITION);
	}
	request = member->request;
	BUG_ON(request->physical_waiter != current);
	irq_flags = _raw_spin_lock_irqsave(&lock->wait_lock);
	if (!member->queue_head) {
		kd_wait_publish_locked(&queue, member);
		atomic_long_or(KD_WAITERS, &lock->owner);
	}
	for (;;) {
		enum kd_wait_decision decision;
		bool first = lock->wait_head == member;

		/* HANDOFF/PICKUP is an actual acquisition opportunity and wins
		 * over a pending origin signal in the common election. */
		decision = kd_wait_decide_locked(&queue, request,
						request->generation, kd_local_grant, lock);
		if (decision == KD_WAIT_GRANTED)
			break;
		if (decision == KD_WAIT_CANCELED) {
			ret = -EINTR;
			break;
		}
		if (decision == KD_WAIT_CLEANUP_REQUIRED &&
		    request->selection == &request->local_selection) {
			/* Promotion owns no physical gate before this ready callback
			 * wins. Retire its exact selection before acknowledging failure. */
			kd_wait_selection_drop_locked(request, &request->local_selection);
			BUG_ON(!kd_wait_cancel_ack_locked(request));
			ret = -EINTR;
			break;
		}
		BUG_ON(decision != KD_WAIT_PENDING);
		set_current_state(state);
		_raw_spin_unlock_irqrestore(&lock->wait_lock, irq_flags);

		/* A queued head may poll a running owner without entering another
		 * queue. The actual grant always returns through the guard above. */
		if (first && !need_resched() &&
		    !(stop_signals && signal_pending(request->logical_origin))) {
			struct task_struct *owner = kd_owner(lock);
			unsigned int budget = 65536;

			while (owner && kd_owner(lock) == owner && budget-- &&
			       owner_on_cpu(owner) && !need_resched() &&
			       !(stop_signals && signal_pending(request->logical_origin)))
				cpu_relax();
		}
		/* Do not sleep after observing availability or a pickup for us. */
		if (kd_owner(lock) && kd_owner(lock) != current)
			kd_local_schedule();
		__set_current_state(TASK_RUNNING);
		irq_flags = _raw_spin_lock_irqsave(&lock->wait_lock);
	}
	__set_current_state(TASK_RUNNING);
	if (member->queue_head)
		kd_wait_unlink_locked(&queue, member);
	if (request->selection) {
		BUG_ON(request->selection != &request->local_selection ||
		       request->selection->executor != current);
		kd_wait_selection_drop_locked(request, &request->local_selection);
	}
	if (!borrowed || ret)
		kd_mutex_wake_head_locked(lock);
	if (!lock->wait_head)
		atomic_long_andnot(KD_FLAGS, &lock->owner);
	if (!borrowed) {
		if (!ret)
			kd_wait_finish_local_locked(request);
		kd_wait_set_state_locked(request, KD_WAIT_RETIRED);
	}
	_raw_spin_unlock_irqrestore(&lock->wait_lock, irq_flags);
out:
	preempt_enable();
	return ret;
}

/* Ordinary mutex/delegation callers retain their original spin policy. */
static noinline int kd_local_lock_slow(struct kd_mutex *lock, unsigned int state,
				      struct kd_mutex_node *node)
{
	return kd_local_lock_slow_common(lock, state, node, false);
}

static noinline int kd_local_lock_slow_signal(struct kd_mutex *lock,
					     unsigned int state)
{
	return kd_local_lock_slow_common(lock, state, NULL, true);
}

static int kd_local_lock_state(struct kd_mutex *lock, unsigned int state,
			       struct kd_mutex_node *node)
{
	unsigned long zero = 0;

	might_sleep();
	BUG_ON(kd_owner(lock) == current);
	if (!atomic_long_read(&lock->owner) &&
	    atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, (unsigned long)current))
		return 0;
	return kd_local_lock_slow(lock, state, node);
}

/* Private signalable rwsem gate entry; no new public lock ABI or symbol export.
 * The fast acquisition wins before signals. Only failed optimistic spinning
 * yields for any signal; the wait-list state still decides cancellation. */
int kd_mutex_local_lock_signal(struct kd_mutex *lock, unsigned int state)
{
	unsigned long zero = 0;

	might_sleep();
	BUG_ON(kd_owner(lock) == current);
	if (!atomic_long_read(&lock->owner) &&
	    atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, (unsigned long)current))
		return 0;
	return kd_local_lock_slow_signal(lock, state);
}

void kd_mutex_local_lock(struct kd_mutex *lock)
{
	kd_local_lock_state(lock, TASK_UNINTERRUPTIBLE, NULL);
}
EXPORT_SYMBOL_GPL(kd_mutex_local_lock);

/* An indirect call cannot advertise the clobber ABI at its caller. Preserve
 * the conventional C ABI and acquire physically on that task instead. */
void kd_mutex_api_lock(struct kd_mutex *lock)
{
	kd_mutex_local_lock(lock);
}
EXPORT_SYMBOL_GPL(kd_mutex_api_lock);

void kd_mutex_local_lock_node(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	BUG_ON(node && (node->lock != lock || node->task_struct_ptr != current));
	if (node)
		kd_local_lock_slow_common(lock, TASK_UNINTERRUPTIBLE, node, false);
	else
		kd_local_lock_state(lock, TASK_UNINTERRUPTIBLE, NULL);
}

int kd_mutex_lock_interruptible(struct kd_mutex *lock)
{
	return kd_local_lock_state(lock, TASK_INTERRUPTIBLE, NULL);
}
EXPORT_SYMBOL_GPL(kd_mutex_lock_interruptible);

int kd_mutex_lock_killable(struct kd_mutex *lock)
{
	return kd_local_lock_state(lock, TASK_KILLABLE, NULL);
}
EXPORT_SYMBOL_GPL(kd_mutex_lock_killable);

void kd_mutex_lock_io(struct kd_mutex *lock)
{
	int old = kd_io_prepare();

	kd_mutex_local_lock(lock);
	kd_io_finish(old);
}
EXPORT_SYMBOL_GPL(kd_mutex_lock_io);

int kd_atomic_dec_and_mutex_lock(atomic_t *count, struct kd_mutex *lock)
{
	if (atomic_add_unless(count, -1, 1))
		return 0;
	kd_mutex_local_lock(lock);
	if (atomic_dec_and_test(count))
		return 1;
	kd_mutex_local_unlock(lock);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_atomic_dec_and_mutex_lock);

int kd_mutex_trylock(struct kd_mutex *lock)
{
	return !kd_try_common(lock, false);
}
EXPORT_SYMBOL_GPL(kd_mutex_trylock);

/* This is a continuation of an already acquired mutex, not a fresh lock.
 * Keep the owner nonzero throughout, including when ordinary local waiters
 * requested handoff. wait_lock serializes cancellation/list flag changes;
 * the CAS preserves concurrent optimistic updates to the owner flags. */
int kd_mutex_transfer_owner(struct kd_mutex *lock, struct task_struct *next)
{
	unsigned long owner;
	int ret = 0;

	if (!next || next == current)
		return -EINVAL;
	_raw_spin_lock(&lock->wait_lock);
	owner = atomic_long_read(&lock->owner);
	for (;;) {
		unsigned long transferred;

		if ((owner & ~KD_FLAGS) != (unsigned long)current ||
		    (owner & KD_PICKUP)) {
			ret = -EPERM;
			break;
		}
		transferred = (unsigned long)next | (owner & KD_FLAGS) | KD_PICKUP;
		if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, transferred))
			break;
	}
	_raw_spin_unlock(&lock->wait_lock);
	return ret;
}

int kd_mutex_transfer_pickup(struct kd_mutex *lock)
{
	unsigned long owner = atomic_long_read(&lock->owner);

	if ((owner & ~KD_FLAGS) != (unsigned long)current || !(owner & KD_PICKUP))
		return -EPERM;
	/* kd_try_common consumes this task's PICKUP with acquire ordering. */
	return kd_try_common(lock, false) ? -EPERM : 0;
}

static noinline void kd_local_unlock_slow(struct kd_mutex *lock)
{
	unsigned long owner = atomic_long_read(&lock->owner);
	struct task_struct *next = NULL;
	DEFINE_WAKE_Q(wake_q);

	for (;;) {
		BUG_ON((owner & ~KD_FLAGS) != (unsigned long)current || (owner & KD_PICKUP));
		if (owner & KD_HANDOFF)
			break;
		if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, owner & KD_FLAGS)) {
			if (owner & KD_WAITERS)
				break;
			return;
		}
	}
	_raw_spin_lock(&lock->wait_lock);
	kd_mutex_wake_head_locked(lock);
	if (lock->wait_head) {
		next = lock->wait_head->request->physical_waiter;
		kd_local_wake_add(&wake_q, next);
	}
	/* Use the saved releasing owner: a new acquirer may already own the word. */
	if (owner & KD_HANDOFF) {
		owner = atomic_long_read(&lock->owner);
		for (;;) {
			unsigned long new = (owner & KD_WAITERS) | (unsigned long)next;

			BUG_ON((owner & ~KD_FLAGS) != (unsigned long)current);
			if (next)
				new |= KD_PICKUP;
			if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, new))
				break;
		}
	}
	_raw_spin_unlock(&lock->wait_lock);
	wake_up_q(&wake_q);
}

void kd_mutex_local_unlock(struct kd_mutex *lock)
{
	unsigned long owner = (unsigned long)current;

	if (!atomic_long_try_cmpxchg_release(&lock->owner, &owner, 0))
		kd_local_unlock_slow(lock);
}
EXPORT_SYMBOL_GPL(kd_mutex_local_unlock);

bool kd_mutex_is_locked(struct kd_mutex *lock)
{
	return kd_owner(lock) != NULL;
}
EXPORT_SYMBOL_GPL(kd_mutex_is_locked);

/* Call only after callers have stopped and joined, never as admission. */
bool kd_mutex_is_idle(struct kd_mutex *lock)
{
	return !atomic_long_read(&lock->owner) && !atomic_read(&lock->osq.tail) &&
		!READ_ONCE(lock->wait_head) && !raw_spin_is_locked(&lock->wait_lock) &&
		!atomic_read(&lock->delegation_state) && !READ_ONCE(lock->delegation_tail) &&
		kd_mutex_waiters_idle(lock);
}
EXPORT_SYMBOL_GPL(kd_mutex_is_idle);

void kd_mutex_destroy(struct kd_mutex *lock)
{
	WARN_ON_ONCE(!kd_mutex_is_idle(lock));
}
EXPORT_SYMBOL_GPL(kd_mutex_destroy);
