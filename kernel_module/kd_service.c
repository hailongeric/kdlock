// SPDX-License-Identifier: GPL-2.0
/* General captured sleeping-lock execution. Included after kd_mutex.c so the
 * ordinary reservation uses its packet, shadow stack and exact slot lifetime.
 * The dispatch queue schedules invocations; it never grants a public lock. */
#include <linux/kthread.h>
#include <linux/delay.h>
#include <linux/sched/signal.h>
#include <linux/cpu.h>
#include <linux/workqueue.h>
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
	KD_SERVICE_NATIVE_READY,
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
#define KD_SERVICE_NATIVE_RECORDS 8
struct kd_service_root {
	struct kd_mutex_node *node;
	/* Used only when no preallocated reservation is available. */
	struct kd_mutex_node spill_node;
	struct kd_service_owner owner;
	struct kd_service_scope scope;
	struct kd_exec_continuation continuation;
	struct kd_exec_outer_unlock hook;
	struct kd_service_completion completion;
	struct list_head native_owners;
	struct kd_native_owner native_storage[KD_SERVICE_NATIVE_RECORDS];
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
	bool native_handoff;
	/* Observation only; neither field participates in protocol decisions. */
	int observe_index;
	u64 observe_shadow_start;
};

#include "kd_service_observe.inc"

static DEFINE_RAW_SPINLOCK(kd_service_dispatch_guard);
static struct kd_wait_node *kd_service_dispatch_head;
static LIST_HEAD(kd_service_active);
static DECLARE_WAIT_QUEUE_HEAD(kd_service_work);
static struct task_struct **kd_service_workers;
static unsigned int kd_service_worker_count;
static char kd_service_cpus[128];
static cpumask_t kd_service_cpu_pool;
module_param_string(service_cpus, kd_service_cpus, sizeof(kd_service_cpus), 0444);
MODULE_PARM_DESC(service_cpus, "Executor CPU list; empty uses online CPUs");
static void kd_service_online_pool(struct cpumask *allowed)
{
	if (kd_service_cpus[0])
		cpumask_and(allowed, &kd_service_cpu_pool, cpu_online_mask);
	else
		cpumask_copy(allowed, cpu_online_mask);
}
static atomic64_t kd_service_work_sequence = ATOMIC64_INIT(0);
module_param_named(service_trace, kd_service_trace, bool, 0644);
MODULE_PARM_DESC(service_trace, "Focused request, executor and returned completion records");

/* The dispatch guard retains root/worker storage. Execution fields can change
 * concurrently; this view is diagnostic and never grants packet custody. */
static int kd_service_progress_get(char *buffer, const struct kernel_param *kp)
{
	struct kd_service_root *root;
	unsigned int total = 0, shown = 0;
	unsigned long flags;
	int used = 0;

	(void)kp;
	flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);
	list_for_each_entry(root, &kd_service_active, active_link) {
		struct kd_exec_continuation *cont = &root->continuation;
		struct kd_regs *packet = READ_ONCE(cont->packet);
		struct task_struct *worker = root->worker;

		++total;
		if (shown == 8)
			continue;
		++shown;
		used += scnprintf(buffer + used, PAGE_SIZE - used,
			"origin=%d executor=%d origin_cpu=%d executor_cpu=%d identity=%px generation=%llu entry=%lx transport=%u state=%u ip=%lx call_phase=%u call_target=%lx instruction_phase=%u instruction=%u\n",
			root->owner.request.logical_origin->pid, worker ? worker->pid : 0,
			root->origin_cpu, worker ? task_cpu(worker) : -1,
			root->owner.request.identity,
			(unsigned long long)root->owner.request.generation,
			root->node->saved_ret_addr, (unsigned int)READ_ONCE(root->transport),
			(unsigned int)READ_ONCE(cont->state), packet ? (unsigned long)READ_ONCE(packet->ip) : 0,
			(unsigned int)READ_ONCE(cont->origin_call.phase), READ_ONCE(cont->origin_call.target),
			(unsigned int)READ_ONCE(cont->origin_memory.phase),
			(unsigned int)READ_ONCE(cont->origin_memory.reached_site.operation));
	}
	_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
	used += scnprintf(buffer + used, PAGE_SIZE - used, "total=%u shown=%u\n", total, shown);
	return used;
}
static const struct kernel_param_ops kd_service_progress_ops = { .get = kd_service_progress_get };
module_param_cb(service_progress, &kd_service_progress_ops, NULL, 0444);


static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_service_resume_packet(struct kd_service_root *root, const struct kd_regs *saved);
static void kd_service_free(struct kd_service_root *root);
static void kd_service_finish_handoff(struct kd_service_root *root);

static void kd_service_trace_event(const char *event,
	struct kd_service_root *root, const struct kd_service_owner *owner)
{
	if (owner == &root->owner)
		kd_service_observe_event(root->observe_index, event);
	if (unlikely(READ_ONCE(kd_service_trace)))
		pr_info("kd_service event=%s origin=%d executor=%d identity=%px generation=%llu object=%px depth=%u entry=%lx may_delegate=%u family_generation=%llu ip=%lx sp=%lx image_generation=%lu\n",
			event, owner->request.logical_origin->pid, current->pid,
			owner->request.identity, (unsigned long long)owner->request.generation,
			owner->admission.object, owner->depth, root->node->saved_ret_addr,
			owner->request.may_delegate,
			root->continuation.reached_active ? root->continuation.generation : 0,
			(unsigned long)root->continuation.packet->ip,
			(unsigned long)root->continuation.packet->sp,
			root->image->generation);
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
	const struct kd_service_scope *s = scope;
	const struct kd_service_root *root = container_of(s->continuation,
		struct kd_service_root, continuation);
	const struct kd_native_owner *owner;

	if (kd_service_scope_depth(scope))
		return false;
	list_for_each_entry(owner, &root->native_owners, link)
		if (owner->held)
			return false;
	return true;
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
	const struct kd_service_root *root = container_of(scope->continuation,
		struct kd_service_root, continuation);
	const struct kd_native_owner *native;

	list_for_each_entry(owner, &scope->owners, link)
		if (owner != scope->outer && kd_service_owner_live(owner))
			return true;
	list_for_each_entry(native, &root->native_owners, link)
		if (native->held)
			return true;
	return false;
}

static bool kd_service_scope_valid(const void *argument,
				   const struct kd_exec_continuation *cont)
{
	const struct kd_service_scope *scope = argument;
	const struct kd_service_owner *owner;
	const struct kd_service_root *root = container_of(cont,
		struct kd_service_root, continuation);
	const struct kd_native_owner *native;

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
	list_for_each_entry(native, &root->native_owners, link)
		if (native->kind != KD_NATIVE_OWNER_FREE &&
		    (native->origin != cont->request->logical_origin ||
		     native->identity != cont->request->identity ||
		     native->generation != cont->generation || !native->sequence))
			return false;
	return true;
}

static unsigned int kd_service_native_depth(struct kd_service_root *root,
	unsigned int kind)
{
	struct kd_native_owner *owner;
	unsigned int count = 0;

	list_for_each_entry(owner, &root->native_owners, link)
		count += owner->held && owner->kind == kind;
	return count;
}

static unsigned int kd_service_native_pins(struct kd_service_root *root)
{
	return kd_service_native_depth(root, KD_NATIVE_OWNER_SPIN) +
		kd_service_native_depth(root, KD_NATIVE_OWNER_PREEMPT);
}

static struct kd_native_owner *kd_service_native_find(struct kd_service_root *root,
	unsigned int kind, unsigned long object)
{
	struct kd_native_owner *owner, *found = NULL;

	list_for_each_entry(owner, &root->native_owners, link) {
		if (!owner->held || owner->kind != kind ||
		    (kind != KD_NATIVE_OWNER_RCU &&
		     owner->object != object))
			continue;
		BUG_ON(owner->origin != root->owner.request.logical_origin ||
		    owner->identity != root->owner.request.identity ||
		    owner->generation != root->owner.request.generation);
		/* Anonymous RCU releases consume the latest exact read acquisition.
		 * Named Native releases match their exact object and need not be LIFO. */
		if (!found || owner->sequence > found->sequence)
			found = owner;
	}
	return found;
}

static unsigned int kd_service_origin_rcu_depth(void)
{
#ifdef CONFIG_PREEMPT_RCU
	return READ_ONCE(current->rcu_read_lock_nesting);
#else
	return 0;
#endif
}

static bool kd_service_native_match(const void *scope, unsigned long object,
	enum kd_exec_native_operation operation, struct kd_exec_native_route *route);
static int kd_service_native_release(void *scope,
	const struct kd_exec_native_route *route);
static bool kd_service_native_finished(const void *scope);

static const struct kd_exec_service_ops kd_service_scope_ops = {
	.validate = kd_service_scope_valid,
	.all_released = kd_service_scope_released,
	.outer_released = kd_service_scope_outer_released,
	.has_nested = kd_service_scope_nested,
	.depth = kd_service_scope_depth,
	.native_match = kd_service_native_match,
	.native_release = kd_service_native_release,
	.native_finished = kd_service_native_finished,
};

/* O can enter ordinary local lock APIs from a returning Native primitive.
 * This token is valid only while E is suspended and the exact transaction
 * owns the packet; it never changes the parent's physical lock owner. */
static struct kd_service_root *kd_service_origin_scope(void)
{
	struct kd_service_root *root, *found = NULL;
	unsigned long flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);

	list_for_each_entry(root, &kd_service_active, active_link) {
		struct kd_origin_call *call = &root->continuation.origin_call;

		if (root->owner.request.logical_origin == current &&
		    READ_ONCE(call->phase) == KD_ORIGIN_CALL_RUNNING &&
		    READ_ONCE(call->servicing) && call->origin == current &&
		    call->identity == root->owner.request.identity &&
		    call->generation == root->owner.request.generation &&
		    root->continuation.state == KD_CONT_SUSPENDED) {
			found = root;
			break;
		}
	}
	_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
	return found;
}

bool kd_service_write_owned(void *object, struct task_struct *task)
{
	struct kd_exec_frame *frame;
	struct kd_exec_continuation *cont;
	struct kd_service_root *root = NULL;
	struct kd_service_owner *owner;
	bool owned = false;

	if (!object || task != current)
		return false;
	preempt_disable();
	frame = kd_exec_current_frame();
	cont = frame ? kd_exec_frame_continuation(frame) : NULL;
	if (cont && cont->service_ops == &kd_service_scope_ops &&
	    cont->executor == current && cont->state == KD_CONT_BOUND)
		root = container_of(cont, struct kd_service_root, continuation);
	else
		root = kd_service_origin_scope();
	if (!root) {
		preempt_enable();
		return kd_exec_native_service_owned((unsigned long)object);
	}
	cont = &root->continuation;
	if (cont->request != &root->owner.request || cont->generation != cont->request->generation ||
	    READ_ONCE(cont->request->state) != KD_WAIT_EXECUTING)
		goto out;
	/* On E these records are task-private. During O service E is suspended,
	 * so O's exact transaction token also excludes owner-list mutation. */
	list_for_each_entry(owner, &root->scope.owners, link) {
		struct kd_admission *a = &owner->admission;
		unsigned long physical;

		if (a->object != object || owner->released || !a->committed || !a->gate_held ||
		    a->pickup_pending || !a->physical_owner)
			continue;
		physical = atomic_long_read(&a->gate->owner);
		if ((physical & 4UL) || (physical & ~7UL) != (unsigned long)a->physical_owner)
			break;
		if (a->sem && (!a->phase_held || a->sem->selected_kind != a->phase_kind ||
		    a->sem->selected_owner != a->phase_owner ||
		    a->sem->selected_identity != a->phase_identity ||
		    a->sem->phase_generation != a->phase_generation ||
		    atomic_long_read(&a->sem->admission) != -1))
			break;
		owned = true;
		break;
	}
out:
	preempt_enable();
	return owned;
}

static void kd_service_primitive_trace(const char *stage, struct kd_service_root *root)
{
	struct kd_origin_call *call = &root->continuation.origin_call;
	bool output = !strcmp(stage, "done") || !strcmp(stage, "resume") ||
		!strcmp(stage, "complete");

	if (unlikely(READ_ONCE(kd_service_trace)))
		pr_info("kd_service primitive: stage=%s origin=%d executor=%d task=%d identity=%px generation=%llu sequence=%llu target=%lx return=%lx image_generation=%lu ax=%lx flags=%lx execution_target=%lx family_generation=%llu artifact_sequence=%llu context_kind=%u argument0=%lx\n",
			stage, call->origin->pid, call->executor->pid, current->pid,
			call->identity, (unsigned long long)call->generation,
			(unsigned long long)call->sequence, call->target, call->call.return_ip,
			root->image ? root->image->generation : 0, output ? call->packet->ax : 0,
			output ? call->packet->flags : 0,
			call->execution_target ? call->execution_target : call->target,
			root->continuation.reached_active ? root->continuation.generation : 0,
			call->artifact_sequence, call->context_kind, call->object);
}

#include "service_native.inc"

__attribute__((noipa)) noinline notrace void
kd_service_origin_context_begin(struct kd_origin_call *call)
{
	struct kd_exec_continuation *cont = container_of(call, struct kd_exec_continuation, origin_call);
	struct kd_service_root *root = container_of(cont, struct kd_service_root, continuation);
	unsigned long stack_here;

	asm volatile("movq %%rsp, %0" : "=r"(stack_here));
	BUG_ON(current != call->origin || !call->servicing ||
	    (cont->reached_active ? (!call->artifact_sequence ||
	     call->artifact_sequence != cont->reached_artifact_sequence) : call->artifact_sequence) ||
	    READ_ONCE(call->phase) != KD_ORIGIN_CALL_RUNNING ||
	    stack_here < cont->stack_base || stack_here >= call->call.stack ||
	    preempt_count() != call->baseline_preempt + 1 ||
	    kd_service_origin_rcu_depth() != call->baseline_rcu || irqs_disabled());
	kd_service_primitive_trace("enter", root);
	/* This change can schedule. The assembly already moved onto task->stack. */
	if (call->context_kind == KD_SERVICE_CALL_NONRETURNING_ORIGIN) {
		/* Preserve the terminal's source context without introducing a new
		 * reschedule before its Native diagnostic consumes the CALL word. */
		barrier();
		preempt_count_dec();
	} else {
		preempt_enable();
	}
}

__attribute__((noipa, noreturn)) noinline notrace void
kd_service_origin_terminal_restore(struct kd_origin_call *call)
{
	struct kd_exec_continuation *cont = container_of(call, struct kd_exec_continuation, origin_call);
	struct kd_service_root *root = container_of(cont, struct kd_service_root, continuation);
	unsigned long return_ip;

	BUG_ON(current != call->origin || !call->servicing ||
	    (cont->reached_active ? (!call->artifact_sequence ||
	     call->artifact_sequence != cont->reached_artifact_sequence) : call->artifact_sequence) ||
	    call->context_kind != KD_SERVICE_CALL_NONRETURNING_ORIGIN ||
	    call->phase != KD_ORIGIN_CALL_RUNNING ||
	    cont->state != KD_CONT_SUSPENDED || call->executor != root->worker ||
	    call->packet->sp != call->call.stack || call->packet->ip != call->target ||
	    !kd_service_call_invocation_matches(call->entry, call->target, call->execution_target) ||
	    copy_from_kernel_nofault(&return_ip, (void *)call->call.stack, sizeof(return_ip)) ||
	    return_ip != call->call.return_ip ||
	    preempt_count() != call->baseline_preempt ||
	    kd_service_origin_rcu_depth() != call->baseline_rcu || irqs_disabled());
	/* No completion is published. The exact acquisitions, image and source
	 * remain retained while the Native nonreturning target runs on O. */
	kd_service_primitive_trace("terminal", root);
	call->packet->orig_ax = KD_REG_ORIGIN_SUFFIX_TAG;
	jump_to_saved_regs_in_cs(call->packet);
	BUG();
}

__attribute__((noipa)) noinline notrace void
kd_service_origin_context_end(struct kd_origin_call *call)
{
	struct kd_exec_continuation *cont = container_of(call, struct kd_exec_continuation, origin_call);
	struct kd_service_root *root = container_of(cont, struct kd_service_root, continuation);

	BUG_ON(current != call->origin || !call->servicing ||
	    READ_ONCE(call->phase) != KD_ORIGIN_CALL_RUNNING);
	/* The bridge saved Native volatile outputs/flags before entering here. */
	kd_service_native_finish(root);
	preempt_disable();
	WRITE_ONCE(call->servicing, false);
}

static void kd_service_origin_primitive(struct kd_service_root *root)
{
	struct kd_exec_continuation *cont = &root->continuation;
	struct kd_origin_call *call = &cont->origin_call;
	unsigned long return_ip, irq_flags;

	if (smp_load_acquire(&call->phase) != KD_ORIGIN_CALL_REQUESTED)
		return;
	BUG_ON(current != root->owner.request.logical_origin || call->origin != current ||
	    (cont->reached_active ? (!call->artifact_sequence ||
	     call->artifact_sequence != cont->reached_artifact_sequence) : call->artifact_sequence) ||
	    call->executor != root->worker || call->identity != root->owner.request.identity ||
	    call->generation != root->owner.request.generation ||
	    cont->state != KD_CONT_SUSPENDED || cont->resume_executor != call->executor ||
	    call->packet != cont->packet || call->packet->sp != call->call.stack ||
	    call->packet->ip != call->target ||
	    !kd_service_call_invocation_matches(call->entry, call->target, call->execution_target) ||
	    call->call.stack < cont->stack_base + 512 ||
	    call->call.stack > cont->stack_base + THREAD_SIZE - sizeof(return_ip) ||
	    copy_from_kernel_nofault(&return_ip, (void *)call->call.stack, sizeof(return_ip)) ||
	    return_ip != call->call.return_ip || irqs_disabled());
	call->baseline_preempt = kd_service_native_pins(root);
	call->baseline_rcu = kd_service_native_depth(root, KD_NATIVE_OWNER_RCU);
	BUG_ON(preempt_count() != call->baseline_preempt + 1 ||
		kd_service_origin_rcu_depth() != call->baseline_rcu);
	local_save_flags(call->irq_flags);
	irq_flags = call->irq_flags ^ call->executor_irq_flags;
	BUG_ON(irq_flags & X86_EFLAGS_IF);
	call->native_sp = round_down(call->call.stack - sizeof(unsigned long), 16UL);
	BUG_ON(call->native_sp < cont->stack_base + 512);
	WRITE_ONCE(call->servicing, true);
	smp_store_release(&call->phase, KD_ORIGIN_CALL_RUNNING);
	if (call->context_kind == KD_SERVICE_CALL_NONRETURNING_ORIGIN)
		kd_service_origin_terminal_bridge(call);
	kd_service_origin_bridge(call);
	/* The Native helper and bridge frames have left the source task stack.
	 * Only now can a resumed E overwrite that lower stack with JIT frames. */
	BUG_ON(call->servicing || irqs_disabled() ||
		preempt_count() != kd_service_native_pins(root) + 1 ||
		kd_service_origin_rcu_depth() != kd_service_native_depth(root, KD_NATIVE_OWNER_RCU));
	kd_service_primitive_trace("done", root);
	smp_store_release(&call->phase, KD_ORIGIN_CALL_DONE);
}

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

/* Registry queries hold E's stack anchors, not object locks. Actual release is
 * performed later on E through the exact selected owner and generation. */
static bool kd_service_native_match(const void *argument, unsigned long object,
	enum kd_exec_native_operation operation, struct kd_exec_native_route *route)
{
	const struct kd_service_scope *scope = argument;
	struct kd_service_root *root = container_of(scope->continuation,
		struct kd_service_root, continuation);
	struct kd_service_owner *owner;

	if (!root->native_handoff || scope->continuation->state != KD_CONT_SUSPENDED)
		return false;
	list_for_each_entry_reverse(owner, &scope->owners, link) {
		struct kd_admission *a = &owner->admission;
		unsigned long physical;

		if ((unsigned long)a->object != object || owner->released || !a->committed ||
		    !a->gate_held || a->pickup_pending || a->physical_owner != root->worker ||
		    owner->root_generation != scope->continuation->generation ||
		    owner->request.generation != a->request_generation)
			continue;
		if (operation == KD_NATIVE_OPERATION_MUTEX_UNLOCK) {
			if (a->kind != KD_ADMISSION_MUTEX)
				continue;
		} else if (operation == KD_NATIVE_OPERATION_RWSEM_UP_WRITE ||
			   operation == KD_NATIVE_OPERATION_RWSEM_DOWNGRADE ||
			   operation == KD_NATIVE_OPERATION_WRITE_OWNED) {
			if (a->kind != KD_ADMISSION_RWSEM_WRITE)
				continue;
		} else {
			return false;
		}
		physical = atomic_long_read(&a->gate->owner);
		if ((physical & 4UL) ||
		    (physical & ~KD_MUTEX_OWNER_FLAGS) != (unsigned long)a->physical_owner)
			return false;
		if (a->sem && (!a->phase_held ||
		    READ_ONCE(a->sem->selected_kind) != a->phase_kind ||
		    READ_ONCE(a->sem->selected_owner) != a->phase_owner ||
		    READ_ONCE(a->sem->selected_identity) != a->phase_identity ||
		    READ_ONCE(a->sem->phase_generation) != a->phase_generation ||
		    atomic_long_read(&a->sem->admission) != -1))
			return false;
		*route = (struct kd_exec_native_route) {
			.owner = owner, .identity = owner->request.identity,
			.generation = owner->request.generation,
			.object = object, .operation = operation,
		};
		return true;
	}
	return false;
}

static int kd_service_native_release(void *argument,
	const struct kd_exec_native_route *route)
{
	struct kd_service_scope *scope = argument;
	struct kd_service_root *root = container_of(scope->continuation,
		struct kd_service_root, continuation);
	struct kd_service_owner *owner;

	if (!root->native_handoff || root->worker != current)
		return -EINVAL;
	list_for_each_entry(owner, &scope->owners, link) {
		struct kd_admission *a = &owner->admission;

		if (owner != route->owner)
			continue;
		if (owner->released || owner->request.identity != route->identity ||
		    owner->request.generation != route->generation ||
		    (unsigned long)a->object != route->object ||
		    a->request_generation != route->generation || !a->gate_held ||
		    !a->committed || a->physical_owner != current || a->pickup_pending)
			return -EINVAL;
		if (route->operation == KD_NATIVE_OPERATION_RWSEM_DOWNGRADE) {
			if (a->kind != KD_ADMISSION_RWSEM_WRITE)
				return -EINVAL;
			kd_admission_downgrade(a);
			kd_admission_read_to_native(a);
			kd_service_trace_event("native_read_custody", root, owner);
		} else if ((route->operation == KD_NATIVE_OPERATION_MUTEX_UNLOCK &&
			    a->kind == KD_ADMISSION_MUTEX) ||
			   (route->operation == KD_NATIVE_OPERATION_RWSEM_UP_WRITE &&
			    a->kind == KD_ADMISSION_RWSEM_WRITE)) {
			kd_admission_release(a);
			owner->released = true;
			kd_service_trace_event("native_release", root, owner);
		} else {
			return -EINVAL;
		}
		return 0;
	}
	return -ENOENT;
}

static bool kd_service_native_finished(const void *argument)
{
	const struct kd_service_scope *scope = argument;
	const struct kd_service_root *root = container_of(scope->continuation,
		struct kd_service_root, continuation);
	const struct kd_service_owner *owner;
	const struct kd_native_owner *native;

	if (!root->native_handoff)
		return false;
	list_for_each_entry(owner, &scope->owners, link)
		if (!owner->released &&
		    (owner->admission.read_state != KD_ADMISSION_READ_NATIVE ||
		     owner->admission.gate_held || owner->admission.phase_held))
			return false;
	list_for_each_entry(native, &root->native_owners, link)
		if (native->held && !native->native_custody)
			return false;
	return true;
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
		kd_service_online_pool(root->worker_allowed);
			list_for_each_entry(origin, &kd_service_active, active_link)
				if (origin->actor != KD_SERVICE_FINISHED)
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
				if (origin->actor != KD_SERVICE_FINISHED &&
				    origin->origin_cpu == smp_processor_id()) {
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
static int kd_service_primitive_call(struct kd_service_root *root);

/* Reserve before Native side effects. A cold-stack extension has no fixed
 * public depth limit and needs no sleeping allocation while NativeSpin lives.
 * Keep its storage through root completion, including non-LIFO releases. */
static noinline int kd_service_native_spill(struct kd_service_root *root)
{
	struct kd_native_owner owner;
	int status;

	owner.kind = KD_NATIVE_OWNER_FREE;
	owner.held = false;
	owner.native_custody = false;
	INIT_LIST_HEAD(&owner.link);
	list_add_tail(&owner.link, &root->native_owners);
	status = kd_service_primitive_call(root);
	status = kd_service_run_scope(root, status);
	BUG_ON((owner.held || owner.kind != KD_NATIVE_OWNER_FREE) && !owner.native_custody);
	list_del_init(&owner.link);
	return status;
}

static int kd_service_primitive_call(struct kd_service_root *root)
{
	struct kd_exec_continuation *cont = &root->continuation;
	struct kd_origin_call *call = &cont->origin_call;
	u64 sequence = call->sequence;
	int result;

	BUG_ON(call->phase != KD_ORIGIN_CALL_PREPARED || call->executor != current ||
	       !call->entry || cont->service_call.api != KD_SERVICE_NONE);
	result = kd_service_native_prepare(root);
	if (result == -EAGAIN)
		return kd_service_native_spill(root);
	if (result) {
		pr_err("kd_service Native context: origin=%d executor=%d target=%lx context=%u result=%d\n",
			call->origin->pid, current->pid, call->target,
			call->context_kind, result);
		BUG();
	}
	kd_service_primitive_trace("request", root);
	if (call->executor_pinned)
		BUG_ON(kd_exec_cont_suspend(cont, KD_CONT_WAIT_SERVICE));
	else
		kd_service_unpin(cont);
	smp_store_release(&call->phase, KD_ORIGIN_CALL_REQUESTED);
	/* Paired APIs and held NativeSpin keep E's immediate execution capacity.
	 * Other calls may schedule E. Both paths unbind before O owns the packet
	 * and source task stack, and both resume this same physical executor. */
	while (smp_load_acquire(&call->phase) != KD_ORIGIN_CALL_DONE) {
		cpu_relax();
		if (!call->executor_pinned && need_resched())
			cond_resched();
	}
	if (call->executor_pinned)
		BUG_ON(!kd_exec_cont_resume(cont));
	else
		kd_service_pin_resume(cont);
	result = kd_exec_cont_native_complete(cont, sequence);
	BUG_ON(result != 0 && result != KD_EXE_RUN_TO_UNLOCK);
	kd_service_primitive_trace(result ? "complete" : "resume", root);
	if (result)
		return result;
	return kd_exe_resume_retained(&cont->frame);
}

#include "service_memory.inc"

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
	BUG_ON(!child.released && child.admission.read_state != KD_ADMISSION_READ_NATIVE);
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

static int kd_service_handoff(struct kd_service_root *root)
{
	struct kd_exec_continuation *cont = &root->continuation;
	struct kd_service_owner *owner;
	struct kd_native_owner *native;

	BUG_ON(root->native_handoff || cont->service_call.api != KD_SERVICE_NONE ||
	       cont->packet->orig_ax != KD_REG_ORIGIN_SUFFIX_TAG);
	/* Remove the physical CPU activation before the Native registry is live.
	 * E keeps every remaining gate and its stack-local ownership anchors. */
	kd_service_unpin(cont);
	list_for_each_entry(owner, &root->scope.owners, link)
		if (!owner->released && owner->admission.read_state == KD_ADMISSION_READ_LIVE) {
			kd_admission_read_to_native(&owner->admission);
			kd_service_trace_event("native_read_custody", root, owner);
		}
	list_for_each_entry(native, &root->native_owners, link)
		if (native->held) {
			BUG_ON(native->origin != cont->request->logical_origin ||
			       native->identity != cont->request->identity ||
			       native->generation != cont->generation);
			/* O already owns the real Native lock/context. Drop only E's
			 * borrowed ledger custody; never claim a physical release. */
			native->native_custody = true;
		}
	root->native_handoff = true;
	/* Independent worker reference: O's initial restoration must not make
	 * outstanding E-owned frames or their final cleanup depend on O's life. */
	__module_get(THIS_MODULE);
	BUG_ON(kd_exec_native_service_begin(&cont->frame));
	kd_service_trace_event("handoff_ready", root, &root->owner);
	smp_store_release(&root->transport, KD_SERVICE_NATIVE_READY);
	BUG_ON(kd_exec_native_wait(&cont->frame));
	return KD_EXE_RUN_HANDOFF;
}

static int kd_service_run_scope(struct kd_service_root *root, int status)
{
	struct kd_exec_continuation *cont = &root->continuation;

	for (;;) {
		if (status == KD_EXE_RUN_HANDOFF)
			return root->native_handoff ? status : kd_service_handoff(root);
		if (status == KD_EXE_RUN_TO_UNLOCK)
			return status;
		if (status == KD_EXE_RUN_SERVICE) {
			if (cont->service_call.acquire) {
				struct kd_service_owner *owner, *reusable = NULL;

				/* A sleeping KD acquisition is not a legal Native atomic
				 * interval operation. Refuse before touching its object. */
				BUG_ON(kd_service_native_pins(root) ||
				       kd_service_native_depth(root, KD_NATIVE_OWNER_RCU));

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
			if (!kd_service_native_pins(root)) {
				kd_service_unpin(cont);
				cond_resched();
				kd_service_pin_resume(cont);
			}
			status = kd_exe_resume_retained(&cont->frame);
			continue;
		}
		if (status == KD_EXE_RUN_ORIGIN_CALL) {
			status = kd_service_primitive_call(root);
			continue;
		}
		if (status == KD_EXE_RUN_ORIGIN_MEMORY) {
			status = kd_service_memory_call(root);
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
	u64 observe_start;
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
			wake_up(&kd_service_work);
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
	BUG_ON(cont->reached_active);
	observe_start = kd_service_observe_start(root->observe_index);
	status = kd_exe_on_retained_entry(&cont->frame, root->exe, root->image);
	kd_service_observe_elapsed(root->observe_index, KD_SERVICE_OBSERVE_DISPATCH_NS,
		KD_SERVICE_OBSERVE_DISPATCH_SAMPLES, observe_start);
	if (cont->frame.executed)
		kd_service_observe_add(root->observe_index, KD_SERVICE_OBSERVE_JIT_ENTERED, 1);
	status = kd_service_run_scope(root, status);
	if (status == KD_EXE_RUN_HANDOFF) {
		BUG_ON(!root->native_handoff || !kd_service_native_finished(&root->scope));
		flags = _raw_spin_lock_irqsave(&root->lifecycle_guard);
		kd_wait_handoff_locked(&root->owner.request);
		_raw_spin_unlock_irqrestore(&root->lifecycle_guard, flags);
		BUG_ON(kd_exec_cont_handoff(cont));
		kd_service_trace_event("handoff_finished", root, &root->owner);
		kd_service_finish_handoff(root);
		return;
	}
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
			kd_service_online_pool(allowed);
			cpumask_clear_cpu(root->origin_cpu, allowed);
			BUG_ON(cpumask_empty(allowed));
			/* Exclude origin before publishing PIN, while it can schedule. */
			BUG_ON(set_cpus_allowed_ptr(current, allowed));
			kd_service_execute(root);
			set_cpus_allowed_ptr(current, kd_service_cpus[0] ?
				&kd_service_cpu_pool : cpu_online_mask);
		} else {
			DEFINE_WAIT(wait);

			for (;;) {
				prepare_to_wait_exclusive(&kd_service_work, &wait,
					TASK_UNINTERRUPTIBLE);
				if (kthread_should_stop() ||
				    atomic64_read(&kd_service_work_sequence) != sequence)
					break;
				schedule();
			}
			finish_wait(&kd_service_work, &wait);
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

/* Source/task references still exist while diagnostics can inspect this root.
 * The encoded node identity is immutable across all uses of its home slot. */
static void kd_service_check_pooled_root(struct kd_service_root *root)
{
	struct kd_mutex_node *node = root->node;
	int cpu = root->origin_cpu;
	int slot;

	BUG_ON(!root->pooled || cpu < 0 || cpu >= nr_cpu_ids || !cpu_possible(cpu) || !node);
	slot = node->slot;
	BUG_ON(slot < 0 || slot >= KD_MUTEX_MAX_NODES ||
	       node->osq.tail != kd_mutex_encode_tail(cpu, slot) ||
	       node != per_cpu_ptr(&kd_mutex_nodes[slot], cpu) ||
	       kd_mutex_wait_record(node)->service != root ||
	       kd_mutex_wait_record(node)->request_live);
	BUG_ON(!(READ_ONCE(per_cpu(kd_mutex_shadows, cpu).node_slots) & BIT(slot)));
}

/* cpus_read_lock spans the caller and this entire operation. Offline CPUs have
 * no local producers, but simultaneous remote cleanups still need this guard.
 * A service record never enters the legacy request-retirement branch. */
static void kd_service_release_offline_node(struct kd_service_root *root)
{
	struct kd_mutex_cpu_state *shadow;
	struct kd_mutex_node *node;
	unsigned long slots, bit;
	unsigned long flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);
	int cpu;
	int reserved;

	kd_service_check_pooled_root(root);
	cpu = root->origin_cpu;
	node = root->node;
	BUG_ON(cpu_online(cpu) || root->owner.request.state != KD_WAIT_RETIRED);
	shadow = per_cpu_ptr(&kd_mutex_shadows, cpu);
	slots = READ_ONCE(shadow->node_slots);
	bit = BIT(node->slot);
	BUG_ON(!(slots & bit));
	kd_mutex_check_node_retirement(node);
	kd_mutex_clear_retired_node(node);
	reserved = READ_ONCE(per_cpu(kd_mutex_reserved_nodes, cpu));
	BUG_ON(reserved <= 0);
	WRITE_ONCE(per_cpu(kd_mutex_reserved_nodes, cpu), reserved - 1);
	/* Slot reuse is the final root/node-associated access. */
	WRITE_ONCE(shadow->node_slots, slots & ~bit);
	_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
}

static long kd_service_retire_handoff(void *argument)
{
	struct kd_service_root *root = argument;
	struct kd_mutex_node *node = root->node;
	bool pooled = root->pooled;
	int cpu = root->origin_cpu;
	unsigned long flags;

	BUG_ON(!root->native_handoff || root->actor != KD_SERVICE_FINISHED ||
	       root->continuation.state != KD_CONT_HANDED_OFF ||
	       root->owner.request.state != KD_WAIT_RETURN_ACK);
	if (pooled)
		kd_service_check_pooled_root(root);
	flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);
	BUG_ON(root->dispatch_member.queue_head || list_empty(&root->active_link));
	list_del_init(&root->active_link);
	_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
	/* Observation is gone before the final retained task/source reference. No
	 * dispatch guard spans these callbacks or the spill's sleeping free. */
	BUG_ON(kd_exec_cont_retire(&root->continuation));
	flags = _raw_spin_lock_irqsave(&root->lifecycle_guard);
	kd_wait_set_state_locked(&root->owner.request, KD_WAIT_RETIRED);
	_raw_spin_unlock_irqrestore(&root->lifecycle_guard, flags);
	if (!pooled) {
		vfree(node->shadow_stack_base);
		kfree(root);
	} else if (cpu_online(cpu)) {
		preempt_disable();
		BUG_ON(raw_smp_processor_id() != (unsigned int)cpu);
		kd_mutex_release_node(node);
		preempt_enable();
	} else {
		kd_service_release_offline_node(root);
	}
	/* No root/node access follows either slot reuse or kfree. */
	return 0;
}

static void kd_service_finish_handoff(struct kd_service_root *root)
{
	struct module *capture_owner = root->completion.owner;
	bool pooled = root->pooled;
	int cpu = root->origin_cpu;
	unsigned long flags = _raw_spin_lock_irqsave(&kd_service_dispatch_guard);

	BUG_ON(root->actor != KD_SERVICE_EXECUTOR);
	root->actor = KD_SERVICE_FINISHED;
	_raw_spin_unlock_irqrestore(&kd_service_dispatch_guard, flags);
	if (pooled) {
		BUG_ON(cpu < 0 || cpu >= nr_cpu_ids || !cpu_possible(cpu));
		cpus_read_lock();
		if (cpu_online(cpu))
			BUG_ON(work_on_cpu(cpu, kd_service_retire_handoff, root));
		else
			BUG_ON(kd_service_retire_handoff(root));
		cpus_read_unlock();
	} else {
		BUG_ON(kd_service_retire_handoff(root));
	}
	/* The callback can publish reuse before returning. Only local reference
	 * values are legal here; module exit joins this synchronous service worker. */
	if (capture_owner)
		module_put(capture_owner);
	module_put(THIS_MODULE);
}

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_service_native_resume(struct kd_service_root *root, const struct kd_regs *saved)
{
	struct kd_regs packet = *saved;
	struct kd_service_completion completion = root->completion;
	struct kd_exec_frame *frame = &root->continuation.frame;

	BUG_ON(current != root->owner.request.logical_origin ||
	       preempt_count() != kd_service_native_pins(root) + 1 || irqs_disabled() ||
	       kd_service_origin_rcu_depth() != kd_service_native_depth(root, KD_NATIVE_OWNER_RCU));
	/* This temporary restore reference is separate from the original capture
	 * reference retained by E through all remaining actual owner releases. */
	if (completion.owner)
		__module_get(completion.owner);
	kd_service_observe_shadow_end(root);
	asm volatile("" : : "m"(packet), "m"(completion) : "memory");
	BUG_ON(kd_exec_native_accept(frame));
	/* No root, saved-packet or frame access after acceptance. E may free them. */
	preempt_enable();
	migrate_enable();
	if (completion.resume)
		completion.resume(completion.owner, &packet);
	jump_to_saved_regs_in_cs(&packet);
	BUG();
}

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_service_shadow_wait(struct kd_service_root *root)
{
	struct kd_regs *packet = &root->node->regs;
	unsigned long flags, restore_sp;

	/* This function is entered on independent storage before source execution
	 * can overwrite any Native capture-helper frame. It never returns there. */
	root->observe_shadow_start = kd_service_observe_start(root->observe_index);
	smp_store_release(&root->transport, KD_SERVICE_STACK_READY);
	while (smp_load_acquire(&root->transport) != KD_SERVICE_RESULT) {
		if (smp_load_acquire(&root->transport) == KD_SERVICE_NATIVE_READY) {
			restore_sp = min_t(unsigned long, root->node->rsp, packet->sp);
			BUG_ON(restore_sp < root->continuation.stack_base + 512 ||
			       restore_sp > root->continuation.stack_base + THREAD_SIZE);
			/* Acceptance runs on O's source stack; only then can E retire
			 * the independent waiting stack and canonical packet. */
			asm volatile("movq %[stack], %%rsp\n\t"
				     "andq $-16, %%rsp\n\t"
				     "callq %P[resume]\n\t"
				     "ud2\n\t"
				     : : [stack] "r"(restore_sp), "D"(root), "S"(packet),
					 [resume] "i"(kd_service_native_resume)
				     : "memory");
			__builtin_unreachable();
		}
		kd_service_origin_primitive(root);
		kd_service_origin_memory(root);
		cpu_relax();
	}
	BUG_ON(root->result);
	/* Reuse the Native helper's established stack depth when the source has
	 * already unwound above it. Do not invent an extra 512-byte gap below
	 * the live source SP. The return CALL word at packet.sp remains intact. */
	restore_sp = min_t(unsigned long, root->node->rsp, packet->sp);
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
		     : : [stack] "r"(restore_sp), "D"(root), "S"(packet),
			 [resume] "i"(kd_service_resume_packet)
		     : "memory");
	__builtin_unreachable();
}

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_service_resume_packet(struct kd_service_root *root, const struct kd_regs *saved)
{
	struct kd_regs packet = *saved;
	struct kd_service_completion completion = root->completion;

	kd_service_observe_shadow_end(root);
	preempt_enable();
	kd_service_free(root);
	migrate_enable();
	if (completion.resume)
		completion.resume(completion.owner, &packet);
	if (packet.orig_ax == KD_REG_ORIGIN_SUFFIX_TAG)
		jump_to_saved_regs_in_cs(&packet);
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

static int kd_service_observe_local(int index, bool no_image, void *object,
	enum kd_admission_kind kind, unsigned int state)
{
	u64 start = kd_service_observe_start(index);
	int result = kd_service_local_acquire(object, kind, state);

	kd_service_observe_elapsed(index, KD_SERVICE_OBSERVE_LOCAL_NS,
		KD_SERVICE_OBSERVE_LOCAL, start);
	if (no_image)
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_LOCAL_NO_IMAGE, 1);
	kd_service_observe_add(index, result ? KD_SERVICE_OBSERVE_LOCAL_CANCEL :
		KD_SERVICE_OBSERVE_LOCAL_SUCCESS, 1);
	return result;
}

static int kd_service_capture_internal(void *object, enum kd_admission_kind kind,
	unsigned int state, unsigned long sp, unsigned long ip, unsigned long bp,
	const struct kd_service_completion *completion, bool bound)
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
	unsigned int native_index;
	int observe_index = kd_service_observe_select(ip, current->comm);

	might_sleep();
	/* A Native primitive owns only this helper's conventional task execution.
	 * Its nested lock calls must not recursively capture the service machinery. */
	if (kd_exec_native_service_active(current) || kd_service_origin_scope())
		return kd_service_observe_local(observe_index, false, object, kind, state);
	/* Closed source admission and ordinary nonselected callers retain the
	 * conventional API. No already published or committed body uses this. */
	if (!kd_source_is_open() || kd_service_worker_count < 2 ||
	    (!bound && !kd_comm_matches(&kd_spin_target, current->comm))) {
		BUG_ON(bound);
		return kd_service_observe_local(observe_index, false, object, kind, state);
	}
	result = kd_exec_capture_lease_get(&pending_lease, current);
	if (result) {
		BUG_ON(bound);
		return kd_service_observe_local(observe_index, false, object, kind, state);
	}
	kd_exe_add_abi(0, ip, KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	exe = kd_exe_find_ready(0, ip);
	image = kd_exe_capture_image(exe, ip);
	if (!image) {
		/* No source instruction has executed and no delegated request was
		 * published. Ordinary C admission keeps cancellation and returns to
		 * this first untranslated source position; the daemon learns later. */
		if (unlikely(READ_ONCE(kd_service_trace)))
			pr_info("kd_service event=untranslated_entry origin=%d entry=%lx\n",
				current->pid, ip);
		kd_exec_capture_lease_put(&pending_lease);
		return kd_service_observe_local(observe_index, true, object, kind, state);
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
			kd_service_observe_add(observe_index, KD_SERVICE_OBSERVE_PREPUBLICATION_CANCEL, 1);
			return result;
		}
		root = kd_service_spill();
		moved = true;
	}
	raw_spin_lock_init(&root->lifecycle_guard);
	root->origin_cpu = raw_smp_processor_id();
	root->worker = NULL;
	root->completion = completion ? *completion : (struct kd_service_completion){ };
	root->exe = exe;
	root->image = image;
	root->actor = KD_SERVICE_ORIGIN_BUSY;
	root->transport = KD_SERVICE_WAITING;
	root->command = KD_SERVICE_OWNER_NONE;
	root->result = 0;
	root->work_notified = false;
	root->native_handoff = false;
	root->observe_index = observe_index;
	root->observe_shadow_start = 0;
	INIT_LIST_HEAD(&root->active_link);
	INIT_LIST_HEAD(&root->scope.owners);
	INIT_LIST_HEAD(&root->native_owners);
	for (native_index = 0; native_index < KD_SERVICE_NATIVE_RECORDS; ++native_index) {
		struct kd_native_owner *native = &root->native_storage[native_index];

		native->kind = KD_NATIVE_OWNER_FREE;
		native->held = false;
		native->native_custody = false;
		INIT_LIST_HEAD(&native->link);
		list_add_tail(&native->link, &root->native_owners);
	}
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
	kd_service_observe_add(observe_index, KD_SERVICE_OBSERVE_SUBMITTED, 1);
	flags = _raw_spin_lock_irqsave(dispatch.guard);
	list_add_tail(&root->active_link, &kd_service_active);
	kd_wait_link_locked(&dispatch, &root->dispatch_member);
	_raw_spin_unlock_irqrestore(dispatch.guard, flags);
	flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	if (!moved)
		kd_admission_publish_locked(a);
	_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
	for (;;) {
		bool arbitrate = false;
		bool notify = false;

		/* Executor custody is only a negative hint. A return to origin
		 * is reconsidered next iteration; every actual claim still uses
		 * the dispatcher guard before touching admission or its guard. */
		if (smp_load_acquire(&root->actor) != KD_SERVICE_EXECUTOR) {
			flags = _raw_spin_lock_irqsave(dispatch.guard);
			arbitrate = root->actor == KD_SERVICE_ORIGIN ||
				root->actor == KD_SERVICE_ORIGIN_BUSY;
			if (arbitrate && a->committed) {
				/* Commitment ends arbitration. Keep the request ready
				 * until a worker actually claims its custody. */
				root->actor = KD_SERVICE_ORIGIN;
				arbitrate = false;
				if (!root->work_notified) {
					root->work_notified = true;
					notify = true;
				}
			} else if (arbitrate) {
				root->actor = KD_SERVICE_ORIGIN_BUSY;
			}
			_raw_spin_unlock_irqrestore(dispatch.guard, flags);
		}
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
		}
		if (notify) {
			atomic64_inc(&kd_service_work_sequence);
			wake_up(&kd_service_work);
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

int kd_service_capture(void *object, enum kd_admission_kind kind,
	unsigned int state, unsigned long sp, unsigned long ip, unsigned long bp)
{
	return kd_service_capture_internal(object, kind, state, sp, ip, bp, NULL, false);
}

int kd_service_capture_bound(void *object, enum kd_admission_kind kind,
	unsigned int state, unsigned long sp, unsigned long ip, unsigned long bp,
	const struct kd_service_completion *completion)
{
	BUG_ON(!completion || !completion->owner || !completion->resume);
	return kd_service_capture_internal(object, kind, state, sp, ip, bp, completion, true);
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
	int result;

	BUILD_BUG_ON(offsetof(struct kd_origin_call, packet) != KD_ORIGIN_CALL_PACKET);
	BUILD_BUG_ON(offsetof(struct kd_origin_call, target) != KD_ORIGIN_CALL_TARGET);
	BUILD_BUG_ON(offsetof(struct kd_origin_call, native_sp) != KD_ORIGIN_CALL_NATIVE_SP);
	BUILD_BUG_ON(offsetof(struct kd_origin_call, shadow_sp) != KD_ORIGIN_CALL_SHADOW_SP);
	BUILD_BUG_ON(offsetof(struct kd_origin_call, shadow_bp) != KD_ORIGIN_CALL_SHADOW_BP);
	BUILD_BUG_ON(offsetof(struct kd_origin_call, execution_target) != KD_ORIGIN_CALL_EXECUTION_TARGET);
	BUILD_BUG_ON(offsetof(struct kd_origin_call, execution_arguments) != KD_ORIGIN_CALL_ARGUMENTS);
	BUILD_BUG_ON(offsetof(struct kd_origin_memory, packet) != KD_ORIGIN_MEMORY_PACKET);
	BUILD_BUG_ON(offsetof(struct kd_origin_memory, native_sp) != KD_ORIGIN_MEMORY_NATIVE_SP);
	BUILD_BUG_ON(offsetof(struct kd_origin_memory, shadow_sp) != KD_ORIGIN_MEMORY_SHADOW_SP);
	BUILD_BUG_ON(offsetof(struct kd_origin_memory, shadow_bp) != KD_ORIGIN_MEMORY_SHADOW_BP);
	if (kd_service_cpus[0]) {
		result = cpulist_parse(kd_service_cpus, &kd_service_cpu_pool);
		if (result)
			return result;
		cpumask_and(&kd_service_cpu_pool, &kd_service_cpu_pool, cpu_online_mask);
		/* A captured origin cannot also supply its executor's CPU. */
		if (cpumask_weight(&kd_service_cpu_pool) < 2)
			return -EINVAL;
	} else {
		cpumask_copy(&kd_service_cpu_pool, cpu_online_mask);
	}
	result = kd_service_calls_init();
	if (result)
		return result;
	result = kd_service_observe_init();
	if (result)
		goto fail;

	for_each_possible_cpu(cpu)
		for (slot = 0; slot < KD_MUTEX_MAX_NODES; slot++) {
			struct kd_mutex_node *node = per_cpu_ptr(&kd_mutex_nodes[slot], cpu);
			struct kd_mutex_wait_record *record = kd_mutex_wait_record(node);

			record->service = kzalloc_node(sizeof(*record->service),
				GFP_KERNEL, cpu_to_node(cpu));
			if (!record->service)
				goto fail;
		}
	kd_service_worker_count = cpumask_weight(&kd_service_cpu_pool);
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
	kd_service_observe_exit();
	kd_service_calls_exit();
}
