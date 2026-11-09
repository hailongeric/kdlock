/* SPDX-License-Identifier: GPL-2.0 */
/* One exact context instruction on O, with the source packet/stack held by its
 * retained transaction until the original task's actual completion ACK. */
#include <asm/cpufeature.h>
static void kd_service_memory_trace(const char *stage, struct kd_service_root *root)
{
	struct kd_origin_memory *operation = &root->continuation.origin_memory;
	bool output = !strcmp(stage, "done") || !strcmp(stage, "resume") ||
		!strcmp(stage, "complete");

	if (unlikely(READ_ONCE(kd_service_trace)))
		pr_info("kd_service memory: stage=%s origin=%d executor=%d task=%d identity=%px generation=%llu sequence=%llu image_generation=%lu ip=%lx next=%lx sp=%lx offset=%lx width=%u operation=%u preempt_operand=%u input_flags=%lx output_flags=%lx preempt_seq=%llu preempt_object=%lx destination=%u value=%lx read=%u family_generation=%llu artifact_sequence=%llu source_value=%lx aux_value=%lx\n",
			stage, operation->origin->pid, operation->executor->pid, current->pid,
			operation->identity, (unsigned long long)operation->generation,
			(unsigned long long)operation->sequence,
			operation->image ? operation->image->generation : 0,
			operation->site->ip, operation->site->next_ip, operation->source_sp,
			operation->effective_offset, operation->site->width,
			operation->site->operation, operation->preempt_operand,
			operation->input_flags, output ? operation->result_flags : 0,
			operation->preempt_owner ? (unsigned long long)operation->preempt_owner->sequence : 0,
			operation->preempt_owner ? operation->preempt_owner->object : 0,
			operation->destination, output ? operation->result_value : 0,
			!!(operation->site->flags & KD_ORIGIN_MEMORY_READ),
			(unsigned long long)root->continuation.root_generation,
			(unsigned long long)operation->artifact_sequence,
			operation->source_value, output ? operation->result_aux : 0);
}

static int kd_service_memory_prepare(struct kd_service_root *root)
{
	struct kd_origin_memory *operation = &root->continuation.origin_memory;
	struct kd_native_owner *owner;
	unsigned long address = operation->gsbase + operation->effective_offset;
	unsigned long count_address = (unsigned long)per_cpu_ptr(&__preempt_count,
		root->origin_cpu);
	unsigned int bytes = operation->site->operation == KD_ORIGIN_MEMORY_LOAD_SIGNED ?
		4 : operation->site->width / 8;
	bool available = false;
	bool reading = operation->site->flags & KD_ORIGIN_MEMORY_READ;

	operation->preempt_owner = NULL;
	operation->preempt_operand = false;
	operation->servicing = false;
	if (!(operation->executor_irq_flags & X86_EFLAGS_IF) || preempt_count() != 1 ||
	    address > ~0UL - bytes)
		return -EOPNOTSUPP;
	if (operation->site->operation == KD_ORIGIN_MEMORY_TASK_READ) {
		operation->executor_pinned = !!kd_service_native_pins(root);
		return boot_cpu_has(X86_FEATURE_OSPKE) && !operation->source_value &&
			!(u32)operation->packet->cx ? 0 : -EOPNOTSUPP;
	}
	if (address < count_address + sizeof(int) && address + bytes > count_address) {
		if (!reading && (address != count_address || operation->site->width != 32 ||
		    operation->site->operation > KD_ORIGIN_MEMORY_DEC))
			return -EOPNOTSUPP;
		operation->preempt_operand = true;
	}
	/* Other ordinary GS reads run on the same origin CPU with its actual
	 * source context. Only the preempt-count operand needs the special
	 * runtime-pin normalization/ownership classification above. */
	operation->executor_pinned = kd_service_native_pins(root) ||
		operation->preempt_operand;
	if (!operation->preempt_operand || reading)
		return 0;
	if (operation->site->operation == KD_ORIGIN_MEMORY_DEC) {
		operation->preempt_owner = kd_service_native_find(root,
			KD_NATIVE_OWNER_PREEMPT, count_address);
		return operation->preempt_owner ? 0 : -EINVAL;
	}
	list_for_each_entry(owner, &root->native_owners, link)
		available |= owner->kind == KD_NATIVE_OWNER_FREE;
	if (!available)
		return -EAGAIN;
	operation->preempt_owner = kd_service_native_reserve(root,
		KD_NATIVE_OWNER_PREEMPT, count_address, operation->sequence);
	return 0;
}

__attribute__((noipa)) noinline notrace void
kd_service_memory_context_begin(struct kd_origin_memory *operation)
{
	struct kd_exec_continuation *cont = container_of(operation,
		struct kd_exec_continuation, origin_memory);
	struct kd_service_root *root = container_of(cont, struct kd_service_root,
		continuation);
	unsigned long stack_here;

	asm volatile("movq %%rsp, %0" : "=r"(stack_here));
	BUG_ON(current != operation->origin || !operation->servicing ||
	    READ_ONCE(operation->phase) != KD_ORIGIN_MEMORY_RUNNING ||
	    stack_here < cont->stack_base || stack_here >= operation->source_sp ||
	    preempt_count() != operation->baseline_preempt + 1 ||
	    kd_service_origin_rcu_depth() != operation->baseline_rcu || irqs_disabled());
	kd_service_memory_trace("enter", root);
	/* The helper is already on O's task stack. Remove exactly the runtime
	 * pin so preempt-count DEC computes the Native zero/need-resched flags. */
	barrier();
	preempt_count_dec();
}

__attribute__((noipa)) noinline notrace void
kd_service_memory_context_end(struct kd_origin_memory *operation)
{
	unsigned int expected = operation->baseline_preempt;
	struct kd_native_owner *owner = operation->preempt_owner;

	BUG_ON(current != operation->origin || !operation->servicing ||
		READ_ONCE(operation->phase) != KD_ORIGIN_MEMORY_RUNNING);
	if (operation->preempt_operand && operation->site->operation <= KD_ORIGIN_MEMORY_DEC) {
		BUG_ON(!owner || owner->origin != current ||
		    owner->identity != operation->identity ||
		    owner->generation != operation->generation ||
		    owner->kind != KD_NATIVE_OWNER_PREEMPT);
		if (operation->site->operation == KD_ORIGIN_MEMORY_INC) {
			BUG_ON(owner->held || owner->sequence != operation->sequence);
			++expected;
		} else {
			BUG_ON(!owner->held || !expected);
			--expected;
		}
	}
	BUG_ON(preempt_count() != expected ||
		kd_service_origin_rcu_depth() != operation->baseline_rcu || irqs_disabled());
	if (owner) {
		owner->held = operation->site->operation == KD_ORIGIN_MEMORY_INC;
		if (!owner->held)
			owner->kind = KD_NATIVE_OWNER_FREE;
	}
	preempt_disable();
	WRITE_ONCE(operation->servicing, false);
}

static void kd_service_origin_memory(struct kd_service_root *root)
{
	struct kd_exec_continuation *cont = &root->continuation;
	struct kd_origin_memory *operation = &cont->origin_memory;
	unsigned long flags;

	if (smp_load_acquire(&operation->phase) != KD_ORIGIN_MEMORY_REQUESTED)
		return;
	BUG_ON(current != root->owner.request.logical_origin ||
	    operation->origin != current || operation->executor != root->worker ||
	    operation->identity != root->owner.request.identity ||
	    operation->generation != root->owner.request.generation ||
	    (operation->artifact_sequence ?
	     (!cont->reached_active || operation->artifact_sequence != cont->reached_artifact_sequence ||
	      operation->image || operation->site != &operation->reached_site) :
	     (cont->reached_active || !operation->image || operation->image != root->image)) ||
	    cont->state != KD_CONT_SUSPENDED ||
	    cont->resume_executor != operation->executor || operation->packet != cont->packet ||
	    operation->packet->sp != operation->source_sp ||
	    operation->packet->ip != operation->site->ip ||
	    operation->source_sp < cont->stack_base + 512 ||
	    operation->source_sp > cont->stack_base + THREAD_SIZE || irqs_disabled() ||
	    operation->gsbase != kd_read_kernel_gsbase() ||
	    root->origin_cpu != smp_processor_id());
	operation->baseline_preempt = kd_service_native_pins(root);
	operation->baseline_rcu = kd_service_native_depth(root, KD_NATIVE_OWNER_RCU);
	BUG_ON(preempt_count() != operation->baseline_preempt + 1 ||
		kd_service_origin_rcu_depth() != operation->baseline_rcu);
	local_save_flags(flags);
	BUG_ON((flags ^ operation->executor_irq_flags) & X86_EFLAGS_IF);
	operation->native_sp = round_down(operation->source_sp - sizeof(unsigned long), 16UL);
	BUG_ON(operation->native_sp < cont->stack_base + 512);
	WRITE_ONCE(operation->servicing, true);
	smp_store_release(&operation->phase, KD_ORIGIN_MEMORY_RUNNING);
	kd_service_memory_bridge(operation);
	BUG_ON(operation->servicing || irqs_disabled() ||
		preempt_count() != kd_service_native_pins(root) + 1 ||
		kd_service_origin_rcu_depth() != kd_service_native_depth(root, KD_NATIVE_OWNER_RCU));
	kd_service_memory_trace("done", root);
	smp_store_release(&operation->phase, KD_ORIGIN_MEMORY_DONE);
}

static int kd_service_memory_call(struct kd_service_root *root);

static noinline int kd_service_memory_spill(struct kd_service_root *root)
{
	struct kd_native_owner owner;
	int status;

	owner.kind = KD_NATIVE_OWNER_FREE;
	owner.held = false;
	owner.native_custody = false;
	INIT_LIST_HEAD(&owner.link);
	list_add_tail(&owner.link, &root->native_owners);
	status = kd_service_memory_call(root);
	status = kd_service_run_scope(root, status);
	BUG_ON((owner.held || owner.kind != KD_NATIVE_OWNER_FREE) && !owner.native_custody);
	list_del_init(&owner.link);
	return status;
}

static int kd_service_memory_call(struct kd_service_root *root)
{
	struct kd_exec_continuation *cont = &root->continuation;
	struct kd_origin_memory *operation = &cont->origin_memory;
	u64 sequence = operation->sequence;
	int result;

	BUG_ON(operation->phase != KD_ORIGIN_MEMORY_PREPARED ||
		operation->executor != current || cont->service_call.api != KD_SERVICE_NONE);
	result = kd_service_memory_prepare(root);
	if (result == -EAGAIN)
		return kd_service_memory_spill(root);
	if (result) {
		pr_err("kd_service memory context: origin=%d executor=%d ip=%lx result=%d\n",
			operation->origin->pid, current->pid, operation->site->ip, result);
		BUG();
	}
	kd_service_memory_trace("request", root);
	if (operation->executor_pinned)
		BUG_ON(kd_exec_cont_suspend(cont, KD_CONT_WAIT_SERVICE));
	else
		kd_service_unpin(cont);
	smp_store_release(&operation->phase, KD_ORIGIN_MEMORY_REQUESTED);
	while (smp_load_acquire(&operation->phase) != KD_ORIGIN_MEMORY_DONE) {
		cpu_relax();
		if (!operation->executor_pinned && need_resched())
			cond_resched();
	}
	if (operation->executor_pinned)
		BUG_ON(!kd_exec_cont_resume(cont));
	else
		kd_service_pin_resume(cont);
	result = kd_exec_cont_memory_complete(cont, sequence);
	BUG_ON(result != 0 && result != KD_EXE_RUN_TO_UNLOCK);
	kd_service_memory_trace(result ? "complete" : "resume", root);
	/* The exact context release is already committed. Retained owner storage
	 * remains alive through this final receipt, before a spill frame can retire. */
	operation->preempt_owner = NULL;
	return result ? result : kd_exe_resume_retained(&cont->frame);
}
