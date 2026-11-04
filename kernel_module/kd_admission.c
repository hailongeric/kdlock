// SPDX-License-Identifier: GPL-2.0
/* Canonical physical acquisition and exact selected rwsem phase custody. */
#include <linux/errno.h>
#include <linux/limits.h>
#include <linux/sched/signal.h>
#include "kd_admission.h"
#include "kd_mutex.h"
#include "kd_mutex_local.h"
#include "kd_rwsem.h"

#define KD_ADMISSION_SPIN_BUDGET 16384U
#define KD_ADMISSION_WAITERS 1UL
#define KD_ADMISSION_HANDOFF 2UL
#define KD_ADMISSION_PICKUP 4UL
#define KD_ADMISSION_FLAGS 7UL

static void kd_admission_assert_object(struct kd_admission *a)
{
	lockdep_assert_held(&a->gate->wait_lock);
	BUG_ON(a->request->generation != a->request_generation ||
	       a->request->admission != a);
}

static bool kd_admission_phase_matches(struct kd_admission *a)
{
	struct kd_rwsem *sem = a->sem;

	return a->phase_held && sem->selected_kind == a->phase_kind &&
		sem->selected_owner == a->phase_owner &&
		sem->selected_identity == a->phase_identity &&
		sem->phase_generation == a->phase_generation &&
		atomic_long_read(&sem->admission) == -1;
}

static void kd_admission_uncondition_locked(struct kd_admission *a)
{
	struct kd_wait_queue queue;

	if (!a->condition.queue_head)
		return;
	queue = kd_wait_queue_view(&a->gate->wait_lock, a->condition.queue_head);
	kd_wait_unlink_locked(&queue, &a->condition);
}

static void kd_admission_condition_locked(struct kd_admission *a)
{
	struct kd_wait_queue queue;
	struct kd_wait_node **head;

	if (!a->sem || !a->gate_held)
		return;
	head = a->phase_held ? &a->sem->reader_drain.head : &a->sem->phase_wait.head;
	if (a->condition.queue_head == head)
		return;
	kd_admission_uncondition_locked(a);
	queue = kd_wait_queue_view(&a->gate->wait_lock, head);
	kd_wait_link_locked(&queue, &a->condition);
}

void kd_admission_init(struct kd_admission *a, struct kd_wait_request *request,
		       enum kd_admission_kind kind, void *object,
		       raw_spinlock_t *retained_guard)
{
	BUG_ON(!a || !request || !object || request->state != KD_WAIT_PRIVATE ||
	       request->admission || (kind != KD_ADMISSION_MUTEX &&
				      kind != KD_ADMISSION_RWSEM_WRITE));
	a->request = request;
	a->kind = kind;
	a->object = object;
	a->sem = kind == KD_ADMISSION_RWSEM_WRITE ? object : NULL;
	a->gate = a->sem ? &a->sem->gate : object;
	a->physical_owner = NULL;
	a->phase_owner = NULL;
	a->phase_identity = NULL;
	a->phase_generation = 0;
	a->request_generation = request->generation;
	a->phase_kind = KD_RWSEM_PHASE_NONE;
	a->read_state = KD_ADMISSION_READ_NONE;
	a->gate_held = false;
	a->pickup_pending = false;
	a->phase_held = false;
	a->phase_release_pending = false;
	a->cleanup_prepared = false;
	a->scheduling_gate_held = false;
	a->committed = false;
	a->selection.request = NULL;
	a->selection.generation = 0;
	a->selection.executor = NULL;
	a->cleanup.request = NULL;
	a->cleanup.generation = 0;
	a->cleanup.owner = NULL;
	raw_spin_lock_init(&a->local_guard);
	a->retained_guard = retained_guard ? retained_guard : &a->local_guard;
	BUG_ON(a->retained_guard == &a->gate->wait_lock);
	request->admission = a;
	request->terminal_guard = a->retained_guard;
	request->guard = &a->gate->wait_lock;
	kd_wait_node_init(&a->member, request, KD_WAIT_ACQUISITION);
	kd_wait_node_init(&a->condition, request, KD_WAIT_CONDITION);
}

void kd_admission_publish_locked(struct kd_admission *a)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(a->gate);

	kd_admission_assert_object(a);
	kd_wait_publish_locked(&queue, &a->member);
	atomic_long_or(KD_ADMISSION_WAITERS, &a->gate->owner);
}

static bool kd_admission_ready(struct kd_wait_request *request, void *argument)
{
	struct kd_admission *a = argument;
	struct kd_wait_queue queue = kd_mutex_wait_queue(a->gate);
	struct kd_rwsem *sem = a->sem;

	BUG_ON(request != a->request);
	if (!a->gate_held) {
		/* A selected origin/worker pair is one public request. No later
		 * canonical member may bypass the head through this adapter. */
		if (a->gate->wait_head != &a->member)
			return false;
		if (request->selection && request->selection->executor != current)
			return false;
		if (!request->selection && request->state == KD_WAIT_QUEUED &&
		    !kd_wait_select_locked(&queue, request, &a->selection, current))
			return false;
		if (!kd_mutex_admission_trylock_locked(a->gate, request))
			return false;
		a->gate_held = true;
		a->physical_owner = current;
		kd_wait_cleanup_take_locked(request, &a->cleanup, a);
	} else if (a->physical_owner != current) {
		/* Only the actual owner's explicit transfer/release service can
		 * change this custody; the selector never steals a real owner. */
		return false;
	}
	if (a->pickup_pending && !kd_admission_owner_pickup_locked(a))
		return false;
	BUG_ON((atomic_long_read(&a->gate->owner) & ~KD_ADMISSION_FLAGS) !=
	       (unsigned long)current ||
	       (atomic_long_read(&a->gate->owner) & KD_ADMISSION_PICKUP));
	if (sem) {
		if (!a->phase_held) {
			/* Keep an existing local-reader cohort's admission open until
			 * its exact condition memberships acquire or cancel. No credit
			 * is granted here; a new phase still freshly drains real readers. */
			if (sem->phase_wait.readers_waiting ||
			    atomic_long_cmpxchg(&sem->admission, 0, -1) != 0) {
				kd_admission_condition_locked(a);
				return false;
			}
			BUG_ON(sem->selected_kind != KD_RWSEM_PHASE_NONE ||
			       sem->selected_owner || sem->selected_identity ||
			       sem->phase_generation == U64_MAX);
			++sem->phase_generation;
			sem->selected_kind = KD_RWSEM_PHASE_ADMISSION;
			sem->selected_owner = current;
			sem->selected_identity = request->identity;
			a->phase_kind = KD_RWSEM_PHASE_ADMISSION;
			a->phase_owner = current;
			a->phase_identity = request->identity;
			a->phase_generation = sem->phase_generation;
			a->phase_held = true;
		}
		BUG_ON(!kd_admission_phase_matches(a));
		/* The full phase RMW and speculative reader RMW force at least
		 * one side to observe the other. Only active credits are drained. */
		if (atomic_long_read_acquire(&sem->readers)) {
			kd_admission_condition_locked(a);
			return false;
		}
	}
	kd_admission_uncondition_locked(a);
	a->committed = true;
	return true;
}

enum kd_wait_decision kd_admission_step_locked(struct kd_admission *a)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(a->gate);
	enum kd_wait_decision decision;

	kd_admission_assert_object(a);
	decision = kd_wait_decide_locked(&queue, a->request,
			a->request_generation, kd_admission_ready, a);
	if (decision == KD_WAIT_GRANTED || decision == KD_WAIT_CLEANUP_REQUIRED ||
	    decision == KD_WAIT_CANCELED) {
		if (!a->gate->wait_head)
			atomic_long_andnot(KD_ADMISSION_WAITERS | KD_ADMISSION_HANDOFF,
					   &a->gate->owner);
		/* A withdrawn head cannot leave a legacy captured successor polling
		 * a notification which only the departed head could have published. */
		if (decision != KD_WAIT_GRANTED)
			kd_mutex_wake_head_locked(a->gate);
	}
	return decision;
}

void kd_admission_transfer_owned_locked(struct kd_admission *a)
{
	kd_admission_assert_object(a);
	BUG_ON(!a->committed || !a->gate_held ||
	       (a->request->state != KD_WAIT_ACQUIRED &&
		a->request->state != KD_WAIT_EXECUTING) || a->condition.queue_head);
	if (a->cleanup.request)
		kd_wait_cleanup_drop_locked(a->request, &a->cleanup);
	if (a->request->selection) {
		BUG_ON(a->request->selection != &a->selection);
		kd_wait_selection_drop_locked(a->request, &a->selection);
	}
}

bool kd_admission_owner_transfer_locked(struct kd_admission *a,
				       struct task_struct *target)
{
	kd_admission_assert_object(a);
	if (!a->gate_held || a->physical_owner != current ||
	    !kd_mutex_admission_transfer_locked(a->gate, target))
		return false;
	a->physical_owner = target;
	a->pickup_pending = true;
	/* phase_owner changes only when target consumes its exact PICKUP. */
	return true;
}

bool kd_admission_owner_pickup_locked(struct kd_admission *a)
{
	kd_admission_assert_object(a);
	if (!a->gate_held || !a->pickup_pending || a->physical_owner != current ||
	    !kd_mutex_admission_trylock_locked(a->gate, a->request))
		return false;
	a->pickup_pending = false;
	if (a->request->selection) {
		BUG_ON(a->request->selection != &a->selection);
		a->selection.executor = current;
	}
	if (a->phase_held) {
		BUG_ON(!kd_admission_phase_matches(a));
		a->sem->selected_owner = current;
		a->phase_owner = current;
	}
	return true;
}

void kd_admission_select_executor_locked(struct kd_admission *a,
					struct task_struct *executor)
{
	struct kd_wait_request *request = a->request;

	kd_admission_assert_object(a);
	BUG_ON(!executor || a->gate_held || a->committed ||
	       (request->state != KD_WAIT_QUEUED &&
		request->state != KD_WAIT_SELECTED_DRAINING));
	if (request->selection) {
		BUG_ON(request->selection != &a->selection);
		a->selection.executor = executor;
	}
}

void kd_admission_owner_release(struct kd_admission *a)
{
	BUG_ON(!a->gate_held || a->pickup_pending || a->physical_owner != current);
	/* The actual owner performs the physical release. The phase remains
	 * closed until the controller observes this exact release completion. */
	if (a->scheduling_gate_held)
		kd_mutex_api_unlock(a->gate);
	else
		kd_mutex_local_unlock(a->gate);
	a->scheduling_gate_held = false;
	a->physical_owner = NULL;
	smp_store_release(&a->gate_held, false);
}

bool kd_admission_finish_cleanup_locked(struct kd_admission *a,
				       struct wake_q_head *wake)
{
	struct kd_wait_queue phase;

	kd_admission_assert_object(a);
	BUG_ON(a->cleanup_prepared || a->pickup_pending);
	if (a->phase_held) {
		BUG_ON(!kd_admission_phase_matches(a));
		a->sem->selected_kind = KD_RWSEM_PHASE_NONE;
		a->sem->selected_owner = NULL;
		a->sem->selected_identity = NULL;
		a->phase_held = false;
		a->phase_release_pending = true;
		phase = kd_wait_queue_view(&a->gate->wait_lock, &a->sem->phase_wait.head);
		kd_wait_collect_wake_locked(&phase, wake);
	}
	kd_admission_uncondition_locked(a);
	if (a->cleanup.request && !a->phase_release_pending && !a->gate_held)
		kd_wait_cleanup_drop_locked(a->request, &a->cleanup);
	if (a->request->selection) {
		BUG_ON(a->request->selection != &a->selection);
		kd_wait_selection_drop_locked(a->request, &a->selection);
	}
	a->cleanup_prepared = true;
	return true;
}

void kd_admission_complete_cleanup(struct kd_admission *a)
{
	unsigned long flags;
	struct kd_wait_request *request = a->request;

	if (!a->cleanup.request || a->gate_held || a->phase_held ||
	    a->phase_release_pending)
		return;
	BUG_ON(!a->cleanup_prepared || request->guard != a->retained_guard ||
	       request->state != KD_WAIT_CANCELING);
	flags = _raw_spin_lock_irqsave(a->retained_guard);
	if (a->cleanup.request)
		kd_wait_cleanup_drop_locked(request, &a->cleanup);
	_raw_spin_unlock_irqrestore(a->retained_guard, flags);
}

void kd_admission_complete_phase_release(struct kd_admission *a)
{
	if (a->phase_release_pending) {
		BUG_ON(!a->cleanup_prepared || a->gate_held);
		/* The selected -1 remains closed after its exact metadata retires.
		 * No next writer selects before this final fully ordered release. */
		BUG_ON(atomic_long_xchg(&a->sem->admission, 0) != -1);
		a->phase_release_pending = false;
	}
	/* No object access follows. A canceled invocation retained its token
	 * through the object guard handover and both actual release ACKs. */
	kd_admission_complete_cleanup(a);
}

raw_spinlock_t *kd_admission_terminal_cancel_locked(struct kd_admission *a)
{
	kd_admission_assert_object(a);
	BUG_ON(!a->cleanup_prepared || a->phase_held || a->committed);
	return kd_wait_cancel_rebind_locked(a->request, a->retained_guard);
}

int kd_admission_wait(struct kd_admission *a,
		      void (*service)(void *argument), void *argument)
{
	unsigned int budget = KD_ADMISSION_SPIN_BUDGET;
	struct kd_wait_request *request = a->request;
	unsigned long flags;
	enum kd_wait_decision decision;
	DEFINE_WAKE_Q(wake);
	raw_spinlock_t *old_guard;

	might_sleep();
	flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	if (request->state == KD_WAIT_PRIVATE)
		kd_admission_publish_locked(a);
	for (;;) {
		decision = kd_admission_step_locked(a);
		if (decision == KD_WAIT_GRANTED) {
			_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
			__set_current_state(TASK_RUNNING);
			return 0;
		}
		BUG_ON(decision == KD_WAIT_STALE || decision == KD_WAIT_CANCELED);
		if (decision == KD_WAIT_CLEANUP_REQUIRED) {
			if (kd_admission_finish_cleanup_locked(a, &wake)) {
				old_guard = kd_admission_terminal_cancel_locked(a);
				_raw_spin_unlock_irqrestore(old_guard, flags);
				__set_current_state(TASK_RUNNING);
				/* This adapter's physical waiter is its executing task.
				 * Cross-task owner transfer uses the transport's explicit
				 * command/ACK, never polling an approximate owner flag. */
				BUG_ON(a->gate_held && a->physical_owner != current);
				if (a->gate_held)
					kd_admission_owner_release(a);
				kd_admission_complete_phase_release(a);
				wake_up_q(&wake);
				flags = _raw_spin_lock_irqsave(request->guard);
				BUG_ON(!kd_wait_cancel_ack_locked(request));
				_raw_spin_unlock_irqrestore(request->guard, flags);
				__set_current_state(TASK_RUNNING);
				return -EINTR;
			}
		}
		/* The task state is published before the next predicate decision.
		 * Timed rechecks observe remote-origin signals and atomic up_read. */
		set_current_state(request->logical_origin == current ?
				  request->wait_state : TASK_UNINTERRUPTIBLE);
		_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
		if (service)
			service(argument);
		/* A service can publish the origin's fatal signal. Re-enter the
		 * actual-ready-first election before any scheduler delay. */
		if (signal_pending_state(request->wait_state, request->logical_origin)) {
			__set_current_state(TASK_RUNNING);
			flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
			continue;
		}
		if (budget && !need_resched() &&
		    !signal_pending(request->logical_origin)) {
			--budget;
			cpu_relax();
		} else {
			schedule_timeout(1);
			budget = KD_ADMISSION_SPIN_BUDGET;
		}
		__set_current_state(TASK_RUNNING);
		flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	}
}

void kd_admission_detach_local_locked(struct kd_admission *a)
{
	kd_admission_assert_object(a);
	BUG_ON(a->physical_owner != current || !a->committed);
	kd_admission_transfer_owned_locked(a);
	if (a->phase_held) {
		BUG_ON(!kd_admission_phase_matches(a));
		a->sem->selected_kind = KD_RWSEM_PHASE_LOCAL;
		a->phase_held = false;
	}
	/* The object owner word and selected LOCAL phase now retain custody.
	 * No pointer to this stack descriptor is retained in the object. */
	a->gate_held = false;
	kd_wait_finish_local_locked(a->request);
	kd_wait_set_state_locked(a->request, KD_WAIT_RETIRED);
}

void kd_admission_move_owned_locked(struct kd_admission *source,
				    struct kd_admission *destination)
{
	kd_admission_assert_object(source);
	BUG_ON(!destination || source == destination ||
	       source->object != destination->object || source->kind != destination->kind ||
	       source->gate != destination->gate || source->sem != destination->sem ||
	       source->physical_owner != current || source->pickup_pending ||
	       !source->committed || !source->gate_held || source->phase_release_pending ||
	       source->cleanup_prepared ||
	       source->read_state != KD_ADMISSION_READ_NONE ||
	       destination->committed || destination->gate_held || destination->phase_held ||
	       destination->phase_release_pending || destination->condition.queue_head ||
	       destination->selection.request || destination->cleanup.request);
	kd_admission_assert_object(destination);
	if (source->phase_held)
		BUG_ON(!kd_admission_phase_matches(source));
	kd_admission_transfer_owned_locked(source);
	destination->physical_owner = source->physical_owner;
	destination->phase_owner = source->phase_owner;
	destination->phase_identity = source->phase_identity;
	destination->phase_generation = source->phase_generation;
	destination->phase_kind = source->phase_kind;
	destination->gate_held = true;
	destination->phase_held = source->phase_held;
	destination->scheduling_gate_held = source->scheduling_gate_held;
	destination->committed = true;
	source->gate_held = false;
	source->phase_held = false;
	source->scheduling_gate_held = false;
	source->physical_owner = NULL;
	kd_wait_move_acquired_locked(source->request, destination->request);
}

void kd_admission_release(struct kd_admission *a)
{
	unsigned long flags;
	DEFINE_WAKE_Q(wake);

	BUG_ON(!a->committed || a->request->guard != a->retained_guard ||
	       a->request->selection || a->request->cleanup ||
	       a->request->memberships || a->request->acquisition);
	if (a->sem) {
		flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
		BUG_ON(!kd_admission_finish_cleanup_locked(a, &wake));
		_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
	}
	kd_admission_owner_release(a);
	kd_admission_complete_phase_release(a);
	wake_up_q(&wake);
}

void kd_admission_downgrade(struct kd_admission *a)
{
	unsigned long flags;

	BUG_ON(!a->committed || !a->sem || a->physical_owner != current ||
	       a->read_state != KD_ADMISSION_READ_NONE);
	flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	BUG_ON(!kd_admission_phase_matches(a));
	atomic_long_inc_return(&a->sem->readers);
	smp_store_release(&a->read_state, KD_ADMISSION_READ_LIVE);
	_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
	kd_admission_release(a);
}

void kd_admission_finish_read(struct kd_admission *a)
{
	struct kd_rwsem *sem = a->sem;

	BUG_ON(!sem || a->request->generation != a->request_generation ||
	       cmpxchg(&a->read_state, KD_ADMISSION_READ_LIVE,
		       KD_ADMISSION_READ_CONSUMING) != KD_ADMISSION_READ_LIVE);
	/* No object access, guard acquisition or delayed notification follows
	 * the final decrement: another writer can retire the object immediately. */
	BUG_ON(atomic_long_dec_return(&sem->readers) < 0);
	smp_store_release(&a->read_state, KD_ADMISSION_READ_RELEASED);
}
