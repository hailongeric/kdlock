// SPDX-License-Identifier: GPL-2.0
/* General captured sleeping-lock execution. Included after kd_mutex.c so the
 * ordinary reservation uses its packet, shadow stack and exact slot lifetime.
 * The dispatch queue schedules invocations; it never grants a public lock. */
#include <linux/kthread.h>
#include <linux/delay.h>
#include <linux/sched/signal.h>
#include "kd_rwsem.h"
#include "kd_exec_cont.h"
#include "kd_comm.h"

extern struct kd_comm_key kd_spin_target;

enum kd_service_actor {
	KD_SERVICE_ORIGIN,
	KD_SERVICE_ORIGIN_BUSY,
	KD_SERVICE_EXECUTOR,
	KD_SERVICE_FINISHED,
};
enum kd_service_transport {
	KD_SERVICE_WAITING,
	KD_SERVICE_PIN,
	KD_SERVICE_STACK_READY,
	KD_SERVICE_RESULT,
};
enum kd_service_owner_command {
	KD_SERVICE_OWNER_NONE,
	KD_SERVICE_OWNER_TRANSFER,
	KD_SERVICE_OWNER_RELEASE,
	KD_SERVICE_OWNER_PICKUP,
	KD_SERVICE_OWNER_ACK,
};

struct kd_service_owner {
	struct list_head link;
	struct kd_wait_request request;
	struct kd_admission admission;
	void *parent_identity;
	u64 parent_generation;
	u64 root_generation;
	unsigned int depth;
	bool released;
};
struct kd_service_scope {
	struct list_head owners;
	struct kd_service_owner *outer;
	struct kd_exec_continuation *continuation;
};
struct kd_service_root {
	struct kd_mutex_node *node;
	/* Used only when no preallocated reservation is available. */
	struct kd_mutex_node spill_node;
	struct kd_service_owner owner;
	struct kd_service_scope scope;
	struct kd_exec_continuation continuation;
	struct kd_exec_outer_unlock hook;
	struct kd_exe_info *exe;
	const struct kd_jit_image *image;
	struct cpumask *worker_allowed;
	raw_spinlock_t lifecycle_guard;
	struct kd_wait_request dispatch_request;
	struct kd_wait_node dispatch_member;
	struct list_head active_link;
	struct task_struct *worker;
	enum kd_service_actor actor;
	enum kd_service_transport transport;
	enum kd_service_owner_command command;
	int origin_cpu;
	int result;
	bool pooled;
	bool work_notified;
};

static DEFINE_RAW_SPINLOCK(kd_service_dispatch_guard);
static struct kd_wait_node *kd_service_dispatch_head;
static LIST_HEAD(kd_service_active);
static DECLARE_WAIT_QUEUE_HEAD(kd_service_work);
static struct task_struct **kd_service_workers;
static unsigned int kd_service_worker_count;
static atomic64_t kd_service_work_sequence = ATOMIC64_INIT(0);
static bool kd_service_trace;
module_param_named(service_trace, kd_service_trace, bool, 0644);
MODULE_PARM_DESC(service_trace, "Focused request, executor and returned completion records");

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_service_resume_packet(struct kd_service_root *root, const struct kd_regs *saved);

static void kd_service_trace_event(const char *event,
	struct kd_service_root *root, const struct kd_service_owner *owner)
{
	if (unlikely(READ_ONCE(kd_service_trace)))
		pr_info("kd_service event=%s origin=%d executor=%d identity=%px generation=%llu object=%px depth=%u entry=%lx may_delegate=%u\n",
			event, owner->request.logical_origin->pid, current->pid,
			owner->request.identity, (unsigned long long)owner->request.generation,
			owner->admission.object, owner->depth, root->node->saved_ret_addr,
			owner->request.may_delegate);
}

static struct kd_wait_queue kd_service_dispatch_queue(void)
{
	return kd_wait_queue_view(&kd_service_dispatch_guard,
				  &kd_service_dispatch_head);
}

static bool kd_service_owner_live(const struct kd_service_owner *owner)
{
	return !owner->released && owner->admission.committed &&
		(owner->admission.gate_held ||
		 owner->admission.read_state == KD_ADMISSION_READ_LIVE);
}

static unsigned int kd_service_scope_depth(const void *argument)
{
	const struct kd_service_scope *scope = argument;
	const struct kd_service_owner *owner;
	unsigned int count = 0;

	list_for_each_entry(owner, &scope->owners, link)
		count += kd_service_owner_live(owner);
	return count;
}

static bool kd_service_scope_released(const void *scope)
{
	return !kd_service_scope_depth(scope);
}

static bool kd_service_scope_outer_released(const void *argument)
{
	const struct kd_service_scope *scope = argument;

	return scope->outer->released;
}

static bool kd_service_scope_nested(const void *argument)
{
	const struct kd_service_scope *scope = argument;
	const struct kd_service_owner *owner;

	list_for_each_entry(owner, &scope->owners, link)
		if (owner != scope->outer && kd_service_owner_live(owner))
			return true;
	return false;
}

static bool kd_service_scope_valid(const void *argument,
				   const struct kd_exec_continuation *cont)
{
	const struct kd_service_scope *scope = argument;
	const struct kd_service_owner *owner;

	if (scope->continuation != cont || cont->request != &scope->outer->request)
		return false;
	list_for_each_entry(owner, &scope->owners, link) {
		if (owner->root_generation != cont->generation ||
		    owner->admission.request != &owner->request ||
		    owner->request.logical_origin != cont->request->logical_origin)
			return false;
		if (!owner->released && owner->admission.gate_held &&
		    owner->admission.physical_owner != current)
			return false;
	}
	return true;
}

static const struct kd_exec_service_ops kd_service_scope_ops = {
	.validate = kd_service_scope_valid,
	.all_released = kd_service_scope_released,
	.outer_released = kd_service_scope_outer_released,
	.has_nested = kd_service_scope_nested,
	.depth = kd_service_scope_depth,
};

static void kd_service_dispatch_remove(struct kd_service_root *root)
{
	struct kd_wait_queue queue = kd_service_dispatch_queue();
	unsigned long flags = _raw_spin_lock_irqsave(queue.guard);

	if (root->dispatch_member.queue_head)
		kd_wait_unlink_locked(&queue, &root->dispatch_member);
	_raw_spin_unlock_irqrestore(queue.guard, flags);
}

/* Caller owns the actor token. No other actor may cache the old object guard
 * until pending is published again. Cancellation acknowledgment follows removal
 * of notification membership and the old guard's final unlock. */
static enum kd_wait_decision kd_service_admission_step(struct kd_service_root *root)
{
	struct kd_admission *a = &root->owner.admission;
	struct kd_wait_request *request = a->request;
	raw_spinlock_t *old_guard;
	unsigned long flags;
	enum kd_wait_decision decision;
	DEFINE_WAKE_Q(wake);

	flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	decision = kd_admission_step_locked(a);
	if (decision != KD_WAIT_CLEANUP_REQUIRED) {
		_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
		return decision;
	}
	BUG_ON(!kd_admission_finish_cleanup_locked(a, &wake));
	old_guard = kd_admission_terminal_cancel_locked(a);
	_raw_spin_unlock_irqrestore(old_guard, flags);
	if (a->gate_held)
		kd_admission_owner_release(a);
	kd_admission_complete_phase_release(a);
	kd_admission_complete_cleanup(a);
	wake_up_q(&wake);
	kd_service_dispatch_remove(root);
	flags = _raw_spin_lock_irqsave(request->guard);
	BUG_ON(!kd_wait_cancel_ack_locked(request));
	_raw_spin_unlock_irqrestore(request->guard, flags);
	return KD_WAIT_CANCELED;
}

/* Physical owner service is used only before the source body starts. Origin
 * never unlocks an executor-owned mutex, and a worker never unlocks origin's. */
static void kd_service_origin_command(struct kd_service_root *root)
{
	struct kd_admission *a = &root->owner.admission;
	unsigned int command = smp_load_acquire(&root->command);
	unsigned long flags;

	if (command == KD_SERVICE_OWNER_TRANSFER) {
		flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
		BUG_ON(!kd_admission_owner_transfer_locked(a, root->worker));
		_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
		smp_store_release(&root->command, KD_SERVICE_OWNER_ACK);
	} else if (command == KD_SERVICE_OWNER_RELEASE) {
		kd_admission_owner_release(a);
		smp_store_release(&root->command, KD_SERVICE_OWNER_ACK);
	} else if (command == KD_SERVICE_OWNER_PICKUP) {
		flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
		BUG_ON(!kd_admission_owner_pickup_locked(a));
		_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
		smp_store_release(&root->command, KD_SERVICE_OWNER_ACK);
	}
}

static void kd_service_acquired_rebind(struct kd_service_owner *owner,
				       raw_spinlock_t *retained)
{
	struct kd_admission *a = &owner->admission;
	unsigned long flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	raw_spinlock_t *old;

	kd_admission_transfer_owned_locked(a);
	old = kd_wait_rebind_locked(&owner->request, retained);
	_raw_spin_unlock_irqrestore(old, flags);
}

static void kd_service_retire_child(struct kd_service_owner *owner)
{
	struct kd_wait_request *request = &owner->request;
	unsigned long flags = _raw_spin_lock_irqsave(request->guard);

	if (request->state == KD_WAIT_ACQUIRED)
		kd_wait_finish_local_locked(request);
	if (request->state == KD_WAIT_RETURN_ACK || request->state == KD_WAIT_CANCEL_ACK)
		kd_wait_set_state_locked(request, KD_WAIT_RETIRED);
	BUG_ON(request->state != KD_WAIT_RETIRED);
	_raw_spin_unlock_irqrestore(request->guard, flags);
}

static struct kd_service_owner *
kd_service_find_owner(struct kd_service_scope *scope, unsigned long object)
{
	struct kd_service_owner *owner;

	list_for_each_entry_reverse(owner, &scope->owners, link)
		if ((unsigned long)owner->admission.object == object &&
		    kd_service_owner_live(owner))
			return owner;
	return NULL;
}

/* Unbind before enabling scheduling, then bind this same task on its current
 * CPU. No CPU-local frame or image admission decision spans a blocking wait. */
static void kd_service_unpin(struct kd_exec_continuation *cont)
{
	BUG_ON(kd_exec_cont_suspend(cont, KD_CONT_WAIT_SERVICE));
	preempt_enable();
	migrate_enable();
}

/* A protocol origin must be able to reach STACK_READY. Do not reserve a CPU
 * on which any captured origin still needs to run. This is stricter than
 * merely avoiding this request's own origin and closes reciprocal pin waits.
 * The nonoversubscribed validation scope leaves executor CPUs available. */
static void kd_service_pin_cpu(struct kd_service_root *root)
{
	for (;;) {
		struct kd_service_root *origin;
		unsigned long flags;
		bool valid = true;

		flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);
		cpumask_copy(root->worker_allowed, cpu_online_mask);
		list_for_each_entry(origin, &kd_service_active, active_link)
			cpumask_clear_cpu(origin->origin_cpu, root->worker_allowed);
		_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
		if (cpumask_empty(root->worker_allowed)) {
			schedule_timeout_uninterruptible(1);
			continue;
		}
		BUG_ON(set_cpus_allowed_ptr(current, root->worker_allowed));
		migrate_disable();
		preempt_disable();
		flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);
		list_for_each_entry(origin, &kd_service_active, active_link)
			if (origin->origin_cpu == smp_processor_id()) {
				valid = false;
				break;
			}
		_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
		if (valid && !kd_exec_context_busy())
			return;
		preempt_enable();
		migrate_enable();
		cond_resched();
	}
}

static void kd_service_pin_resume(struct kd_exec_continuation *cont)
{
	struct kd_service_root *root = container_of(cont, struct kd_service_root,
						  continuation);

	kd_service_pin_cpu(root);
	BUG_ON(!kd_exec_cont_resume(cont));
}

static int kd_service_run_scope(struct kd_service_root *root, int status);

/* The child record remains on the executor's C stack until the entire root
 * finishes. Releases may occur in any order; list membership is not LIFO
 * ownership. A child needs no root slot or additional service worker. */
static int kd_service_acquire_into(struct kd_service_root *root,
				   struct kd_service_owner *child)
{
	struct kd_exec_continuation *cont = &root->continuation;
	struct kd_exec_service_call call = cont->service_call;
	struct kd_service_owner *parent;
	enum kd_admission_kind kind;
	int result, status;
	unsigned long flags;

	kind = call.api == KD_SERVICE_MUTEX_LOCK ||
		call.api == KD_SERVICE_MUTEX_LOCK_INTERRUPTIBLE ||
		call.api == KD_SERVICE_MUTEX_LOCK_KILLABLE ?
		KD_ADMISSION_MUTEX : KD_ADMISSION_RWSEM_WRITE;
	parent = root->scope.outer;
	{
		struct kd_service_owner *candidate;

		list_for_each_entry_reverse(candidate, &root->scope.owners, link)
			if (candidate != child && kd_service_owner_live(candidate)) {
				parent = candidate;
				break;
			}
	}
	child->parent_identity = parent->request.identity;
	child->parent_generation = parent->request.generation;
	child->depth = parent->depth + 1;
	child->root_generation = cont->generation;
	child->released = false;
	kd_wait_request_init(&child->request, NULL, 0,
		cont->request->logical_origin, current, call.wait_state,
		call.may_delegate, child);
	kd_admission_init(&child->admission, &child->request, kind,
		(void *)call.object, NULL);
	kd_service_unpin(cont);
	BUG_ON(kd_exec_cont_service_child(cont, &child->request));
	result = kd_admission_wait(&child->admission, NULL, NULL);
	if (!result) {
		kd_service_acquired_rebind(child, &child->admission.local_guard);
		flags = _raw_spin_lock_irqsave(child->request.guard);
		kd_wait_finish_local_locked(&child->request);
		_raw_spin_unlock_irqrestore(child->request.guard, flags);
	}
	kd_service_pin_resume(cont);
	status = kd_exec_cont_service_complete(cont, &child->request, result);
	BUG_ON(status);
	kd_service_trace_event(result ? "child_cancel" : "child_grant", root, child);
	/* The result CALL is consumed before retiring failed admission storage. */
	if (result) {
		child->released = true;
		kd_service_retire_child(child);
	}
	return kd_exe_resume_retained(&cont->frame);
}

static noinline int kd_service_nested(struct kd_service_root *root)
{
	struct kd_service_owner child;
	int status;

	INIT_LIST_HEAD(&child.link);
	child.released = true;
	list_add_tail(&child.link, &root->scope.owners);
	status = kd_service_acquire_into(root, &child);
	status = kd_service_run_scope(root, status);
	BUG_ON(!child.released);
	list_del_init(&child.link);
	kd_service_retire_child(&child);
	return status;
}

static int kd_service_release_call(struct kd_service_root *root)
{
	struct kd_exec_continuation *cont = &root->continuation;
	struct kd_exec_service_call *call = &cont->service_call;
	struct kd_service_owner *owner = kd_service_find_owner(&root->scope, call->object);

	BUG_ON(!owner);
	switch (call->api) {
	case KD_SERVICE_RWSEM_DOWNGRADE:
		kd_admission_downgrade(&owner->admission);
		kd_service_trace_event("downgrade", root, owner);
		break;
	case KD_SERVICE_RWSEM_UP_READ:
		/* Retained metadata is committed before the last object access. */
		owner->released = true;
		kd_admission_finish_read(&owner->admission);
		kd_service_trace_event("read_release", root, owner);
		break;
	case KD_SERVICE_MUTEX_UNLOCK:
	case KD_SERVICE_RWSEM_UP_WRITE:
		owner->released = true;
		kd_admission_release(&owner->admission);
		kd_service_trace_event("release", root, owner);
		break;
	default:
		BUG();
	}
	if (owner->released && owner != root->scope.outer)
		kd_service_retire_child(owner);
	return kd_exec_cont_service_complete(cont, NULL, 0);
}

static int kd_service_run_scope(struct kd_service_root *root, int status)
{
	struct kd_exec_continuation *cont = &root->continuation;

	for (;;) {
		if (status == KD_EXE_RUN_TO_UNLOCK)
			return status;
		if (status == KD_EXE_RUN_SERVICE) {
			if (cont->service_call.acquire) {
				struct kd_service_owner *owner, *reusable = NULL;

				list_for_each_entry(owner, &root->scope.owners, link)
					if (owner != root->scope.outer && owner->released) {
						reusable = owner;
						break;
					}
				status = reusable ? kd_service_acquire_into(root, reusable) :
					kd_service_nested(root);
			} else {
				status = kd_service_release_call(root);
				if (!status)
					status = kd_exe_resume_retained(&cont->frame);
			}
			continue;
		}
		if (status == KD_EXE_RUN_YIELD) {
			kd_service_unpin(cont);
			cond_resched();
			kd_service_pin_resume(cont);
			status = kd_exe_resume_retained(&cont->frame);
			continue;
		}
		/* No origin suffix is a valid completion of this retained protocol.
		 * Report the reached point; broader helper/context support remains
		 * an explicit integration gate, not successful proxy evidence. */
		pr_err("kd_service unsupported continuation: origin=%d executor=%d entry=%lx ip=%lx status=%d\n",
			cont->request->logical_origin->pid, current->pid,
			cont->frame.entry_ip, cont->packet->ip, status);
		BUG();
	}
}

static void kd_service_execute(struct kd_service_root *root)
{
	struct kd_admission *a = &root->owner.admission;
	struct kd_exec_continuation *cont = &root->continuation;
	unsigned long flags;
	int status;
	enum kd_wait_decision decision;

	/* Actor custody was transferred under dispatcher guard. Until this task
	 * publishes RESULT, origin only reads retained fields/owner commands. */
	flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	if (a->gate_held && a->physical_owner != current) {
		_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
		smp_store_release(&root->command, KD_SERVICE_OWNER_TRANSFER);
		while (smp_load_acquire(&root->command) != KD_SERVICE_OWNER_ACK)
			cond_resched();
		flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
		BUG_ON(!kd_admission_owner_pickup_locked(a));
		WRITE_ONCE(root->command, KD_SERVICE_OWNER_NONE);
	} else if (!a->gate_held) {
		kd_admission_select_executor_locked(a, current);
	}
	_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
	if (!a->committed) {
		decision = kd_service_admission_step(root);
		if (decision == KD_WAIT_CANCELED) {
			BUG_ON(kd_exec_cont_return(cont, -EINTR));
			kd_service_trace_event("cancel", root, &root->owner);
			root->result = -EINTR;
			smp_store_release(&root->transport, KD_SERVICE_RESULT);
			return;
		}
		if (decision == KD_WAIT_PENDING) {
			struct kd_wait_queue queue = kd_service_dispatch_queue();

			flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
			if (a->gate_held) {
				BUG_ON(!kd_admission_owner_transfer_locked(a,
					root->owner.request.logical_origin));
				_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
				smp_store_release(&root->command, KD_SERVICE_OWNER_PICKUP);
				while (smp_load_acquire(&root->command) != KD_SERVICE_OWNER_ACK)
					cond_resched();
				flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
			} else {
				kd_admission_select_executor_locked(a,
					root->owner.request.logical_origin);
			}
			_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
			WRITE_ONCE(root->command, KD_SERVICE_OWNER_NONE);
			/* A pending root consumes no worker across another body's run. */
			flags = _raw_spin_lock_irqsave(queue.guard);
			kd_wait_link_locked(&queue, &root->dispatch_member);
			smp_store_release(&root->actor, KD_SERVICE_ORIGIN);
			_raw_spin_unlock_irqrestore(queue.guard, flags);
			atomic64_inc(&kd_service_work_sequence);
			wake_up_all(&kd_service_work);
			return;
		}
		BUG_ON(decision != KD_WAIT_GRANTED);
	}
	kd_service_acquired_rebind(&root->owner, &root->lifecycle_guard);
	kd_service_pin_cpu(root);
	smp_store_release(&root->transport, KD_SERVICE_PIN);
	while (smp_load_acquire(&root->transport) != KD_SERVICE_STACK_READY) {
		cpu_relax();
		if (need_resched()) {
			preempt_enable();
			migrate_enable();
			cond_resched();
			kd_service_pin_cpu(root);
		}
	}
	BUG_ON(!kd_exec_cont_bind(cont, a->gate, &root->hook));
	kd_service_trace_event("enter", root, &root->owner);
	flags = _raw_spin_lock_irqsave(&root->lifecycle_guard);
	kd_wait_set_state_locked(&root->owner.request, KD_WAIT_EXECUTING);
	_raw_spin_unlock_irqrestore(&root->lifecycle_guard, flags);
	status = kd_exe_on_retained_entry(&cont->frame, root->exe, root->image);
	status = kd_service_run_scope(root, status);
	BUG_ON(status != KD_EXE_RUN_TO_UNLOCK || !kd_service_scope_released(&root->scope));
	flags = _raw_spin_lock_irqsave(&root->lifecycle_guard);
	kd_wait_set_state_locked(&root->owner.request, KD_WAIT_RELEASED);
	_raw_spin_unlock_irqrestore(&root->lifecycle_guard, flags);
	BUG_ON(kd_exec_cont_return(cont, 0));
	kd_service_trace_event("returned", root, &root->owner);
	preempt_enable();
	migrate_enable();
	root->node->packet_state = KD_PACKET_FULL;
	root->result = 0;
	/* Final worker access. Origin may consume, ACK and reuse immediately. */
	smp_store_release(&root->transport, KD_SERVICE_RESULT);
}

static struct kd_service_root *kd_service_claim(void)
{
	struct kd_wait_queue queue = kd_service_dispatch_queue();
	struct kd_wait_node *member;
	struct kd_service_root *root = NULL;
	unsigned long flags = _raw_spin_lock_irqsave(queue.guard);

	member = kd_wait_first_locked(&queue);
	while (member) {
		struct kd_service_root *candidate = member->request->context;

		if (candidate->actor == KD_SERVICE_ORIGIN &&
		    candidate->owner.admission.committed) {
			root = candidate;
			root->worker = current;
			smp_store_release(&root->actor, KD_SERVICE_EXECUTOR);
			kd_wait_unlink_locked(&queue, member);
			break;
		}
		member = kd_wait_next_locked(&queue, member);
	}
	_raw_spin_unlock_irqrestore(queue.guard, flags);
	return root;
}

static int kd_service_worker(void *unused)
{
	cpumask_var_t allowed;
	u64 sequence;

	(void)unused;
	if (!alloc_cpumask_var(&allowed, GFP_KERNEL | __GFP_NOFAIL))
		return -ENOMEM;
	while (!kthread_should_stop()) {
		struct kd_service_root *root;

		sequence = atomic64_read(&kd_service_work_sequence);
		root = kd_service_claim();

		if (root) {
			root->worker_allowed = allowed;
			cpumask_copy(allowed, cpu_online_mask);
			cpumask_clear_cpu(root->origin_cpu, allowed);
			BUG_ON(cpumask_empty(allowed));
			/* Exclude origin before publishing PIN, while it can schedule. */
			BUG_ON(set_cpus_allowed_ptr(current, allowed));
			kd_service_execute(root);
			set_cpus_allowed_ptr(current, cpu_online_mask);
		} else {
			wait_event(kd_service_work, kthread_should_stop() ||
				atomic64_read(&kd_service_work_sequence) != sequence);
		}
	}
	free_cpumask_var(allowed);
	return 0;
}

static struct kd_service_root *kd_service_reserve(void)
{
	struct kd_service_root *root;
	struct kd_mutex_node *node;

	preempt_disable();
	node = kd_mutex_reserve_node();
	if (node) {
		root = kd_mutex_wait_record(node)->service;
		BUG_ON(!root);
		root->node = node;
		root->pooled = true;
		preempt_enable();
		return root;
	}
	preempt_enable();
	return NULL;
}

static struct kd_service_root *kd_service_spill(void)
{
	struct kd_service_root *root;

	/* Capacity spill is obtained only after a stack request actually commits.
	 * Before that point the canonical killable election remains operational. */
	root = kzalloc(sizeof(*root), GFP_KERNEL | __GFP_NOFAIL);
	root->node = &root->spill_node;
	do {
		root->node->shadow_stack_base = vzalloc(KD_MUTEX_SHADOW_STACK_SIZE);
		if (!root->node->shadow_stack_base)
			schedule_timeout_uninterruptible(1);
	} while (!root->node->shadow_stack_base);
	root->node->shadow_stack_ptr = (unsigned long)root->node->shadow_stack_base +
		KD_MUTEX_SHADOW_STACK_SIZE - 8;
	root->pooled = false;
	return root;
}

static void kd_service_free(struct kd_service_root *root)
{
	unsigned long flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);

	BUG_ON(root->dispatch_member.queue_head);
	list_del_init(&root->active_link);
	_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
	if (root->pooled) {
		preempt_disable();
		kd_mutex_release_node(root->node);
		preempt_enable();
	} else {
		vfree(root->node->shadow_stack_base);
		kfree(root);
	}
}

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_service_shadow_wait(struct kd_service_root *root)
{
	struct kd_regs packet;
	unsigned long flags, restore_sp;

	/* This function is entered on independent storage before source execution
	 * can overwrite any Native capture-helper frame. It never returns there. */
	smp_store_release(&root->transport, KD_SERVICE_STACK_READY);
	while (smp_load_acquire(&root->transport) != KD_SERVICE_RESULT)
		cpu_relax();
	BUG_ON(root->result);
	packet = root->node->regs;
	/* Reuse the Native helper's established stack depth when the source has
	 * already unwound above it. Do not invent an extra 512-byte gap below
	 * the live source SP. The return CALL word at packet.sp remains intact. */
	restore_sp = min_t(unsigned long, root->node->rsp, packet.sp);
	BUG_ON(restore_sp < root->continuation.stack_base + 512 ||
	       restore_sp > root->continuation.stack_base + THREAD_SIZE);
	flags = _raw_spin_lock_irqsave(&root->lifecycle_guard);
	kd_wait_set_state_locked(&root->owner.request, KD_WAIT_RETURN_ACK);
	_raw_spin_unlock_irqrestore(&root->lifecycle_guard, flags);
	BUG_ON(kd_exec_cont_retire(&root->continuation));
	flags = _raw_spin_lock_irqsave(&root->lifecycle_guard);
	kd_wait_set_state_locked(&root->owner.request, KD_WAIT_RETIRED);
	_raw_spin_unlock_irqrestore(&root->lifecycle_guard, flags);
	/* Resume below both source and protocol stacks before freeing either. */
	/* The protocol stack cannot be freed while it is current. The final
	 * trampoline below moves to the captured stack before root retirement. */
	asm volatile("movq %[stack], %%rsp\n\t"
		     "andq $-16, %%rsp\n\t"
		     "callq %P[resume]\n\t"
		     "ud2\n\t"
		     : : [stack] "r"(restore_sp), "D"(root), "S"(&packet),
			 [resume] "i"(kd_service_resume_packet)
		     : "memory");
	__builtin_unreachable();
}

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_service_resume_packet(struct kd_service_root *root, const struct kd_regs *saved)
{
	struct kd_regs packet = *saved;

	preempt_enable();
	kd_service_free(root);
	migrate_enable();
	jump_to_saved_regs(&packet);
	BUG();
}

static int kd_service_local_acquire(void *object, enum kd_admission_kind kind,
				     unsigned int state)
{
	if (kind == KD_ADMISSION_MUTEX)
		return kd_mutex_local_lock_signal(object, state);
	return state == TASK_KILLABLE ? (kd_down_write_killable)(object) :
		state == TASK_INTERRUPTIBLE ? (kd_down_write_interruptible)(object) :
		((kd_down_write)(object), 0);
}

int kd_service_capture(void *object, enum kd_admission_kind kind,
	unsigned int state, unsigned long sp, unsigned long ip, unsigned long bp)
{
	struct kd_service_root *root;
	struct kd_wait_queue dispatch = kd_service_dispatch_queue();
	struct kd_admission *a;
	struct kd_wait_request pending_request;
	struct kd_admission pending;
	struct kd_exec_capture_lease pending_lease;
	struct kd_exe_info *exe;
	const struct kd_jit_image *image;
	bool moved = false;
	unsigned long flags;
	enum kd_wait_decision decision;
	int result;

	might_sleep();
	/* Closed source admission and ordinary nonselected callers retain the
	 * conventional API. No already published or committed body uses this. */
	if (!kd_source_is_open() || kd_service_worker_count < 2 ||
	    !kd_comm_matches(&kd_spin_target, current->comm)) {
		return kd_service_local_acquire(object, kind, state);
	}
	result = kd_exec_capture_lease_get(&pending_lease, current);
	if (result)
		return kd_service_local_acquire(object, kind, state);
	kd_exe_add_abi(0, ip, KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	exe = kd_exe_find_ready(0, ip);
	image = kd_exe_capture_image(exe, ip);
	if (!image) {
		/* This invocation has not published a delegated request. Its local
		 * C adapter records may_delegate=false and preserves Native results.
		 * Published invocations never switch to an origin suffix. */
		if (unlikely(READ_ONCE(kd_service_trace)))
			pr_info("kd_service event=local_image origin=%d entry=%lx\n",
				current->pid, ip);
		kd_exec_capture_lease_put(&pending_lease);
		return kd_service_local_acquire(object, kind, state);
	}
	migrate_disable();
	root = kd_service_reserve();
	if (!root) {
		/* No capacity wait may conceal a pending cancellation. This stack
		 * descriptor remains intact until the real acquisition commits. */
		kd_wait_request_init(&pending_request, NULL, 0, current, current,
			state, true, &pending);
		kd_admission_init(&pending, &pending_request, kind, object, NULL);
		result = kd_admission_wait(&pending, NULL, NULL);
		if (result) {
			flags = _raw_spin_lock_irqsave(pending_request.guard);
			kd_wait_set_state_locked(&pending_request, KD_WAIT_RETIRED);
			_raw_spin_unlock_irqrestore(pending_request.guard, flags);
			kd_exec_capture_lease_put(&pending_lease);
			migrate_enable();
			return result;
		}
		root = kd_service_spill();
		moved = true;
	}
	raw_spin_lock_init(&root->lifecycle_guard);
	root->origin_cpu = raw_smp_processor_id();
	root->worker = NULL;
	root->exe = exe;
	root->image = image;
	root->actor = KD_SERVICE_ORIGIN_BUSY;
	root->transport = KD_SERVICE_WAITING;
	root->command = KD_SERVICE_OWNER_NONE;
	root->result = 0;
	root->work_notified = false;
	INIT_LIST_HEAD(&root->active_link);
	INIT_LIST_HEAD(&root->scope.owners);
	root->scope.outer = &root->owner;
	root->scope.continuation = &root->continuation;
	root->owner.parent_identity = NULL;
	root->owner.parent_generation = 0;
	root->owner.depth = 0;
	root->owner.released = false;
	INIT_LIST_HEAD(&root->owner.link);
	kd_wait_request_init(&root->owner.request,
		moved ? pending_request.identity : NULL,
		moved ? pending_request.generation : 0, current, current,
		state, true, root);
	root->owner.root_generation = root->owner.request.generation;
	a = &root->owner.admission;
	kd_admission_init(a, &root->owner.request, kind, object, &root->lifecycle_guard);
	root->node->regs.sp = sp;
	root->node->regs.ip = ip;
	root->node->regs.bp = bp;
	root->node->saved_ret_addr = ip;
	root->node->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	root->node->gsbase = kd_read_kernel_gsbase();
	root->node->lock = a->gate;
	root->node->task_struct_ptr = current;
	root->continuation.state = KD_CONT_UNUSED;
	if (moved) {
		flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
		kd_admission_move_owned_locked(&pending, a);
		_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
	}
	result = kd_exec_cont_adopt_acquired(&root->continuation,
		&root->owner.request, &root->node->regs, ip,
		(unsigned long)a->gate, root->node->gsbase,
		KD_ENTRY_ABI_MUTEX_CLOBBER_V1, &pending_lease);
	/* Capture leases are a prepublication capability. A selected prepared
	 * caller cannot proceed with a partial source/task-stack lifetime. */
	BUG_ON(result);
	list_add_tail(&root->owner.link, &root->scope.owners);
	BUG_ON(kd_exec_cont_set_service(&root->continuation, &root->scope,
		&kd_service_scope_ops));
	root->hook.release = NULL;
	root->hook.released = false;
	kd_wait_request_init(&root->dispatch_request, NULL, 0, current, current,
		TASK_UNINTERRUPTIBLE, false, root);
	kd_wait_node_init(&root->dispatch_member, &root->dispatch_request, KD_WAIT_CONDITION);
	flags = _raw_spin_lock_irqsave(dispatch.guard);
	list_add_tail(&root->active_link, &kd_service_active);
	kd_wait_link_locked(&dispatch, &root->dispatch_member);
	_raw_spin_unlock_irqrestore(dispatch.guard, flags);
	flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	if (!moved)
		kd_admission_publish_locked(a);
	_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
	for (;;) {
		bool arbitrate;
		bool notify = false;

		/* Claim on every iteration: an executor may hand custody back
		 * between the previous poll and this one. A notification read alone
		 * never authorizes caching the object's old guard. */
		flags = _raw_spin_lock_irqsave(dispatch.guard);
		arbitrate = root->actor == KD_SERVICE_ORIGIN ||
			root->actor == KD_SERVICE_ORIGIN_BUSY;
		if (arbitrate)
			root->actor = KD_SERVICE_ORIGIN_BUSY;
		_raw_spin_unlock_irqrestore(dispatch.guard, flags);
		if (arbitrate) {
			decision = kd_service_admission_step(root);
			if (decision == KD_WAIT_CANCELED) {
				BUG_ON(kd_exec_cont_return(&root->continuation, -EINTR));
				kd_service_trace_event("cancel", root, &root->owner);
				result = -EINTR;
				break;
			}
			BUG_ON(decision != KD_WAIT_PENDING && decision != KD_WAIT_GRANTED);
			flags = _raw_spin_lock_irqsave(dispatch.guard);
			root->actor = KD_SERVICE_ORIGIN;
			if (decision == KD_WAIT_GRANTED && !root->work_notified) {
				root->work_notified = true;
				notify = true;
			}
			_raw_spin_unlock_irqrestore(dispatch.guard, flags);
			if (notify) {
				atomic64_inc(&kd_service_work_sequence);
				wake_up_all(&kd_service_work);
			}
		}
		kd_service_origin_command(root);
		if (smp_load_acquire(&root->transport) == KD_SERVICE_RESULT) {
			result = root->result;
			BUG_ON(result != -EINTR);
			break;
		}
		if (smp_load_acquire(&root->transport) == KD_SERVICE_PIN) {
			preempt_disable();
			asm volatile("movq %%rsp, %c[saved](%[node])\n\t"
				     "movq %[stack], %%rsp\n\t"
				     "andq $-16, %%rsp\n\t"
				     "movq %[root], %%rdi\n\t"
				     "xorq %%rbp, %%rbp\n\t"
				     "callq %P[wait]\n\t"
				     "ud2\n\t"
				     : : [stack] "r"(root->node->shadow_stack_ptr),
					 [node] "r"(root->node),
					 [saved] "i"(offsetof(struct kd_mutex_node, rsp)),
					 [root] "r"(root), [wait] "i"(kd_service_shadow_wait)
				     : "memory");
			__builtin_unreachable();
		}
		cond_resched();
		cpu_relax();
	}
	BUG_ON(kd_exec_cont_retire(&root->continuation));
	flags = _raw_spin_lock_irqsave(&root->lifecycle_guard);
	kd_wait_set_state_locked(&root->owner.request, KD_WAIT_RETIRED);
	_raw_spin_unlock_irqrestore(&root->lifecycle_guard, flags);
	kd_service_free(root);
	migrate_enable();
	return result;
}

bool kd_service_idle(void)
{
	unsigned long flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);
	bool idle = list_empty(&kd_service_active) && !kd_service_dispatch_head;

	_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
	return idle;
}

int kd_service_init(void)
{
	int cpu, slot;
	unsigned int i;

	for_each_possible_cpu(cpu)
		for (slot = 0; slot < KD_MUTEX_MAX_NODES; slot++) {
			struct kd_mutex_node *node = per_cpu_ptr(&kd_mutex_nodes[slot], cpu);
			struct kd_mutex_wait_record *record = kd_mutex_wait_record(node);

			record->service = kzalloc_node(sizeof(*record->service),
				GFP_KERNEL, cpu_to_node(cpu));
			if (!record->service)
				goto fail;
		}
	kd_service_worker_count = num_online_cpus();
	kd_service_workers = kcalloc(kd_service_worker_count,
		sizeof(*kd_service_workers), GFP_KERNEL);
	if (!kd_service_workers)
		goto fail;
	for (i = 0; i < kd_service_worker_count; i++) {
		struct task_struct *worker = kthread_run(kd_service_worker, NULL,
			"kd_service/%u", i);

		if (IS_ERR(worker))
			goto fail;
		kd_service_workers[i] = worker;
	}
	return 0;
fail:
	kd_service_exit();
	return -ENOMEM;
}

void kd_service_exit(void)
{
	int cpu, slot;
	unsigned int i;

	BUG_ON(!kd_service_idle());
	if (kd_service_workers) {
		for (i = 0; i < kd_service_worker_count; i++)
			if (kd_service_workers[i])
				kthread_stop(kd_service_workers[i]);
		kfree(kd_service_workers);
		kd_service_workers = NULL;
	}
	for_each_possible_cpu(cpu)
		for (slot = 0; slot < KD_MUTEX_MAX_NODES; slot++) {
			struct kd_mutex_node *node = per_cpu_ptr(&kd_mutex_nodes[slot], cpu);
			struct kd_mutex_wait_record *record = kd_mutex_wait_record(node);

			kfree(record->service);
			record->service = NULL;
		}
	kd_service_worker_count = 0;
}
