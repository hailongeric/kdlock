// SPDX-License-Identifier: GPL-2.0
/* SELFTEST only: join actual JIT progress to unpublished virtual-ticket cancel.
 * A matching explicit KD workload must supply A/B owners and a KD contender. Only the
 * request-pool/node views are injected. Kind 3 observes a genuinely full ticket
 * pool without changing it; no lock word, queue link or code is modified.
 */
static int kd_virtual_refusal_once;
module_param_named(spin_selftest_virtual_refusal, kd_virtual_refusal_once, int,
		   0444);
MODULE_PARM_DESC(
	spin_selftest_virtual_refusal,
	"selftest-only: 1=missing request storage, 2=full node count, 3=observe real ticket exhaustion");

/* Keep snapshots off the small combiner stack and out of the default module. */
static struct {
	struct kd_exec_frame frame;
	struct kd_regs regs;
	struct kd_spin_node nodes[MAX_NODES];
	struct kd_spin_continuation_stack requests;
	struct kd_spin_continuation_stack *request_base;
	struct kd_combiner_state shadow;
	struct qspinlock *lock;
	unsigned long return_ip;
	int kind;
	int cpu;
	int initial_preempt;
	u32 word;
} kd_virtual_test;

/* Do not return a corrupted ticket/packet to native code just to finish a test. */
#define KD_VIRTUAL_REQUIRE(condition)                                                      \
	do {                                                                               \
		if (unlikely(!(condition))) {                                              \
			pr_err("kd_spin virtual refusal error: cpu=%d line=%d check=%s\n", \
			       raw_smp_processor_id(), __LINE__, #condition);              \
			BUG();                                                             \
		}                                                                          \
	} while (0)

static bool kd_spin_selftest_virtual_begin(
	struct qspinlock *lock, const struct kd_spin_ref *request,
	const struct kd_regs *regs, const struct kd_exec_frame *parent,
	struct kd_spin_continuation_stack **requests, int initial_preempt)
{
	struct kd_spin_node *base = this_cpu_ptr(&kd_spin_nodes[0]);
	struct kd_spin_ref found = { 0 };
	int kind = READ_ONCE(kd_virtual_refusal_once);

	/* Single-thread warmup cannot reach this busy-S branch. Never combine this
	 * synthetic count with the trace of real reservations or shadow pressure.
	 */
	if ((kind < 1 || kind > 3) || (kind == 3) != !request ||
	    !parent->executed ||
	    cmpxchg(&kd_virtual_refusal_once, kind, 0) != kind)
		return false;
	KD_VIRTUAL_REQUIRE(!preempt_model_preemptible() && !kd_node_trace &&
			   !kd_shadow_fill_once);
	KD_VIRTUAL_REQUIRE(kd_exec_frame_validate(parent) && *requests);
	KD_VIRTUAL_REQUIRE(parent->control_call.phase == KD_CALL_PENDING);
	KD_VIRTUAL_REQUIRE(kd_exec_frame_lock_depth(parent) == 1 &&
			   !parent->remote_request &&
			   parent->remote_result == KD_EXEC_REMOTE_IDLE);
	KD_VIRTUAL_REQUIRE(this_cpu_ptr(&kd_spin_cpu)->node_count == 0 &&
			   preempt_count() == initial_preempt + (kind != 3));
	if (kind == 3) {
		/* The workload holds 31 distinct physical locks; A is ticket 32.
		 * Snapshot before allocation to catch any failed-attempt mutation.
		 */
		KD_VIRTUAL_REQUIRE(initial_preempt == KD_SPIN_ENTRY_SLOTS &&
				   !kd_spin_entry_find((void *)lock, &found));
	} else {
		KD_VIRTUAL_REQUIRE(kd_spin_entry_find((void *)lock, &found) &&
				   found.entry == request->entry &&
				   found.sequence == request->sequence);
	}
	KD_VIRTUAL_REQUIRE(raw_spin_is_locked((raw_spinlock_t *)lock) &&
			   READ_ONCE(lock->locked) == 1);
	KD_VIRTUAL_REQUIRE(
		raw_spin_is_locked((raw_spinlock_t *)parent->outer_lock_addr) &&
		READ_ONCE(((struct qspinlock *)parent->outer_lock_addr)
				  ->locked) == _Q_LOCKED_COMBINER_VAL);
	KD_VIRTUAL_REQUIRE(regs->ip == parent->control_call.return_ip &&
			   regs->sp ==
				   parent->control_call.stack + sizeof(long));

	kd_virtual_test.kind = kind;
	kd_virtual_test.cpu = smp_processor_id();
	kd_virtual_test.initial_preempt = initial_preempt;
	kd_virtual_test.lock = lock;
	kd_virtual_test.word = atomic_read(&lock->val);
	kd_virtual_test.regs = *regs;
	kd_virtual_test.frame = *parent;
	kd_virtual_test.return_ip =
		READ_ONCE(*(unsigned long *)parent->control_call.stack);
	kd_virtual_test.request_base = *requests;
	memcpy(&kd_virtual_test.requests, *requests,
	       sizeof(kd_virtual_test.requests));
	memcpy(kd_virtual_test.nodes, base, sizeof(kd_virtual_test.nodes));
	kd_spin_capture_combiner_state(&kd_virtual_test.shadow,
				       this_cpu_ptr(&kd_spin_cpu));
	/* Use the existing error branches, not an early artificial return. Count
	 * four is an injected refusal input, never evidence of four live requests.
	 */
	if (kind == 1)
		*requests = NULL;
	else if (kind == 2)
		this_cpu_ptr(&kd_spin_cpu)->node_count = MAX_NODES;
	return true;
}

static void kd_spin_selftest_virtual_end(const struct kd_spin_ref *request,
					 const struct kd_regs *regs,
					 const struct kd_exec_frame *parent,
					 int result)
{
	struct kd_spin_node *base = this_cpu_ptr(&kd_spin_nodes[0]);
	struct kd_spin_ref found = { 0 };
	bool retired, pin, nodes, contexts, packet, frame, owner;

	KD_VIRTUAL_REQUIRE(smp_processor_id() == kd_virtual_test.cpu);
	KD_VIRTUAL_REQUIRE(result ==
			   (kd_virtual_test.kind == 1 ? -ENOMEM : -E2BIG));
	KD_VIRTUAL_REQUIRE(this_cpu_ptr(&kd_spin_cpu)->node_count ==
			   (kd_virtual_test.kind == 2 ? MAX_NODES : 0));
	/* Undo only the synthetic count, after production has decremented its own
	 * overflow attempt and retired its real ticket. A must remain owned.
	 */
	if (kd_virtual_test.kind == 2)
		this_cpu_ptr(&kd_spin_cpu)->node_count = 0;
	retired = !request->entry && !request->sequence &&
		  !kd_spin_entry_find((void *)kd_virtual_test.lock, &found);
	pin = preempt_count() == kd_virtual_test.initial_preempt;
	nodes = !memcmp(base, kd_virtual_test.nodes,
			sizeof(kd_virtual_test.nodes));
	contexts = *this_cpu_ptr(&kd_spin_continuations) ==
			   kd_virtual_test.request_base &&
		   !memcmp(kd_virtual_test.request_base,
			   &kd_virtual_test.requests,
			   sizeof(kd_virtual_test.requests));
	packet = !memcmp(regs, &kd_virtual_test.regs, sizeof(*regs)) &&
		 READ_ONCE(*(unsigned long *)parent->control_call.stack) ==
			 kd_virtual_test.return_ip;
	frame = !memcmp(parent, &kd_virtual_test.frame, sizeof(*parent)) &&
		kd_spin_combiner_state_matches(
			&kd_virtual_test.shadow,
			this_cpu_ptr(&kd_spin_cpu));
	owner = raw_spin_is_locked((raw_spinlock_t *)kd_virtual_test.lock) &&
		atomic_read(&kd_virtual_test.lock->val) ==
			kd_virtual_test.word &&
		raw_spin_is_locked((raw_spinlock_t *)parent->outer_lock_addr) &&
		READ_ONCE(((struct qspinlock *)parent->outer_lock_addr)
				  ->locked) == _Q_LOCKED_COMBINER_VAL;
	KD_VIRTUAL_REQUIRE(retired && pin && nodes && contexts && packet &&
			   frame && owner);
	pr_info("kd_spin virtual refusal: task=%d entry=%lx outer=%lx lock=%lx target=%lx cpu=%d kind=%d ret=%d phase=%u retired=%u pin=%u nodes=%u contexts=%u packet=%u frame=%u owner=%u executed=%u allocated=%u injected=%u\n",
		parent->logical_task->pid, parent->entry_ip,
		parent->outer_lock_addr, (unsigned long)kd_virtual_test.lock,
		parent->control_call.target, kd_virtual_test.cpu,
		kd_virtual_test.kind, result, parent->control_call.phase,
		retired, pin, nodes, contexts, packet, frame, owner,
		parent->executed, kd_virtual_test.kind != 3,
		kd_virtual_test.kind != 3);
}

#undef KD_VIRTUAL_REQUIRE
