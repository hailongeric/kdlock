// SPDX-License-Identifier: GPL-2.0
/* Included only in KDLOCK_SELFTEST builds; record the real task-stack RSP. */
#include <linux/sched/task_stack.h>
#include <linux/moduleparam.h>

static bool kd_frame_trace;
module_param_named(spin_selftest_trace_frames, kd_frame_trace, bool, 0444);
MODULE_PARM_DESC(
	spin_selftest_trace_frames,
	"selftest-only: sample combiner task-stack bounds and physical frame depth");

static bool kd_frame_capacity_probe;
module_param_named(spin_selftest_probe_frames, kd_frame_capacity_probe, bool,
		   0444);
MODULE_PARM_DESC(
	spin_selftest_probe_frames,
	"selftest-only: probe the real full frame context without changing capacity");

#define KD_FRAME_TRACE_EVENTS 64
static atomic_t kd_frame_event_count = ATOMIC_INIT(0);
static struct kd_frame_trace_event {
	unsigned long entry, outer, parent, used, left;
	unsigned int depth, local;
	int cpu, task, ret;
	bool valid, executed, returned;
} kd_frame_events[KD_FRAME_TRACE_EVENTS];

/* Observe the natural full held-lock ledger at the deepest CALL. Physical
 * frames inherit ancestor entries, so the logical ledger rejects before the
 * separate local-shadow check. Never fill locks or enlarge the shadow stack.
 */
static atomic_t kd_full_shadow_claimed = ATOMIC_INIT(0);
static struct {
	struct kd_exec_frame expected;
	struct kd_combiner_state shadow;
	struct pt_regs regs;
	raw_spinlock_t *lock;
	unsigned long return_ip;
	unsigned int preempt;
	int cpu, nodes, result;
	bool irq, valid_before, ready, packet, frame, combiner, physical,
		pending, context;
} kd_full_shadow;

static bool kd_spin_selftest_full_shadow_owned(void)
{
	const struct kd_exec_frame *frame = kd_exec_current_frame();
	unsigned int depth = KD_EXEC_MAX_LOCK_DEPTH;

	/* Match each genuine parent to the CPU ledger and its physical owner.
	 * Only the owner byte is stable: peers may still publish queue tails.
	 */
	while (frame && depth) {
		raw_spinlock_t *lock =
			(void *)kd_full_shadow.shadow.lock_addr[--depth];

		if (!lock || frame->depth != depth ||
		    frame->outer_lock_addr != (unsigned long)lock ||
		    kd_exec_frame_lock_depth(frame) != depth + 1 ||
		    !kd_exec_frame_validate(frame) ||
		    !raw_spin_is_locked(lock) ||
		    kd_spin_debug_owner(lock) != (unsigned long)current ||
		    READ_ONCE(kd_spin_word((void *)lock)->locked) !=
			    _Q_LOCKED_COMBINER_VAL)
			return false;
		frame = frame->parent;
	}
	return !frame && !depth;
}

static bool kd_spin_selftest_full_shadow_pending(void)
{
	struct kd_spin_ref ref = { 0 };

	/* B is uncontended in this workload and must not acquire even a ticket. */
	return atomic_read(&((struct qspinlock *)kd_full_shadow.lock)->val) ==
		       0 &&
	       !kd_spin_entry_find(kd_full_shadow.lock, &ref);
}

static bool kd_spin_selftest_full_shadow_begin(raw_spinlock_t *lock,
					       struct pt_regs *regs,
					       struct kd_exec_frame *frame)
{
	struct kd_spin_cpu_state *stack = this_cpu_ptr(&kd_spin_cpu);

	if (!frame || !frame->executed || !lock || !regs || !regs->sp ||
	    kd_spin_lock_stack_depth(stack) != KD_EXEC_MAX_LOCK_DEPTH ||
	    atomic_cmpxchg(&kd_full_shadow_claimed, 0, 1))
		return false;

	kd_full_shadow.regs = *regs;
	kd_full_shadow.expected = *frame;
	kd_full_shadow.lock = lock;
	kd_full_shadow.return_ip = READ_ONCE(*(unsigned long *)regs->sp);
	kd_full_shadow.preempt = preempt_count();
	kd_full_shadow.irq = irqs_disabled();
	kd_full_shadow.cpu = raw_smp_processor_id();
	kd_full_shadow.nodes = this_cpu_ptr(&kd_spin_cpu)->node_count;
	kd_spin_capture_combiner_state(&kd_full_shadow.shadow, stack);
	kd_full_shadow.valid_before =
		kd_full_shadow.preempt && kd_full_shadow.irq &&
		!kd_full_shadow.nodes && kd_exec_current_frame() == frame &&
		kd_spin_selftest_full_shadow_owned() &&
		kd_spin_selftest_full_shadow_pending() &&
		!kd_exec_frame_lock_contains(frame, (unsigned long)lock);
	/* Beginning the CALL is the only allowed frame change. Modify the private
	 * expected snapshot, never the live frame or the waiter's return word.
	 */
	kd_full_shadow.valid_before &=
		!kd_call_begin(&kd_full_shadow.expected.control_call, regs->ip,
			       regs->sp, kd_full_shadow.return_ip);
	return true;
}

static void kd_spin_selftest_full_shadow_end(const struct pt_regs *regs,
					     const struct kd_exec_frame *frame,
					     int result)
{
	kd_full_shadow.result = result;
	kd_full_shadow.packet =
		!memcmp(regs, &kd_full_shadow.regs, sizeof(*regs)) &&
		READ_ONCE(*(unsigned long *)kd_full_shadow.regs.sp) ==
			kd_full_shadow.return_ip;
	kd_full_shadow.frame =
		!memcmp(frame, &kd_full_shadow.expected, sizeof(*frame)) &&
		frame->control_call.phase == KD_CALL_PENDING;
	kd_full_shadow.combiner = kd_spin_combiner_state_matches(
		&kd_full_shadow.shadow, this_cpu_ptr(&kd_spin_cpu));
	kd_full_shadow.physical = kd_spin_selftest_full_shadow_owned();
	kd_full_shadow.pending = kd_spin_selftest_full_shadow_pending();
	kd_full_shadow.context = kd_exec_current_frame() == frame &&
				 kd_full_shadow.cpu == raw_smp_processor_id() &&
				 kd_full_shadow.preempt == preempt_count() &&
				 kd_full_shadow.irq == irqs_disabled() &&
				 kd_full_shadow.nodes ==
					 this_cpu_ptr(&kd_spin_cpu)->node_count;
	/* Drain-time reporting keeps printk off the full physical frame chain. */
	smp_store_release(&kd_full_shadow.ready, true);
}

static void kd_spin_selftest_full_shadow_report(void)
{
	if (!atomic_read(&kd_full_shadow_claimed))
		return;
	pr_info("kd_frame held refusal: ready=%u valid_before=%u cpu=%d task=%d entry=%lx outer=%lx lock=%lx target=%lx sp=%lx return=%lx depth=%u recorded=%u local=%u error=%d packet=%u frame=%u combiner=%u physical=%u pending=%u context=%u\n",
		smp_load_acquire(&kd_full_shadow.ready),
		kd_full_shadow.valid_before, kd_full_shadow.cpu,
		kd_full_shadow.expected.logical_pid,
		kd_full_shadow.expected.entry_ip,
		kd_full_shadow.expected.outer_lock_addr,
		(unsigned long)kd_full_shadow.lock, kd_full_shadow.regs.ip,
		kd_full_shadow.regs.sp, kd_full_shadow.return_ip,
		kd_full_shadow.expected.depth + 1,
		kd_exec_frame_lock_depth(&kd_full_shadow.expected),
		kd_full_shadow.shadow.lock_depth, kd_full_shadow.result,
		kd_full_shadow.packet, kd_full_shadow.frame,
		kd_full_shadow.combiner, kd_full_shadow.physical,
		kd_full_shadow.pending, kd_full_shadow.context);
}

static noinline int
kd_spin_selftest_frame_begin(const struct kd_exec_frame *frame)
{
	struct kd_spin_cpu_state *stack;
	struct kd_frame_trace_event *event;
	const struct kd_exec_frame *parent;
	unsigned long sp, top;
	unsigned int depth;
	int index;

	if (!kd_frame_trace)
		return -1;
	index = atomic_inc_return(&kd_frame_event_count) - 1;
	if (index >= KD_FRAME_TRACE_EVENTS)
		return -1;
	event = &kd_frame_events[index];
	stack = this_cpu_ptr(&kd_spin_cpu);
	asm volatile("mov %%rsp, %0" : "=r"(sp));
	top = (unsigned long)task_stack_page(current) + THREAD_SIZE;
	event->used = top - sp;
	event->left = sp - (top - THREAD_SIZE);
	event->entry = frame->entry_ip;
	event->outer = frame->outer_lock_addr;
	event->parent = frame->parent ? frame->parent->outer_lock_addr : 0;
	event->depth = frame->depth + 1;
	event->local = kd_spin_lock_stack_depth(stack);
	event->cpu = raw_smp_processor_id();
	event->task = frame->logical_task->pid;
	event->valid = kd_exec_current_frame() == frame && sp <= top &&
		       sp >= top - THREAD_SIZE;
	depth = event->depth;
	for (parent = frame; parent; parent = parent->parent) {
		if (!depth || parent->depth != --depth ||
		    !kd_exec_frame_validate(parent)) {
			event->valid = false;
			break;
		}
	}
	event->valid &= depth == 0;
	if (kd_frame_capacity_probe)
		kd_exec_selftest_capacity_probe(frame);
	return index;
}

static void kd_spin_selftest_frame_end(int index,
				       const struct kd_exec_frame *frame,
				       int ret)
{
	struct kd_frame_trace_event *event;

	if (index < 0)
		return;
	event = &kd_frame_events[index];
	event->valid &= kd_exec_current_frame() == frame &&
			frame->outer_lock_addr == event->outer &&
			frame->depth + 1 == event->depth;
	event->executed = frame->executed;
	event->ret = ret;
	event->returned = true;
}

static void kd_spin_selftest_frames_report(void)
{
	int i, count = atomic_read(&kd_frame_event_count);
	unsigned int failures = count > KD_FRAME_TRACE_EVENTS;
	unsigned int max_depth = 0;
	unsigned long min_left = THREAD_SIZE;
#ifdef NUMA_AWARE
	const unsigned int numa = 1;
#else
	const unsigned int numa = 0;
#endif

	if (!kd_frame_trace)
		return;
	kd_spin_selftest_full_shadow_report();
	if (kd_frame_capacity_probe)
		kd_exec_selftest_capacity_report();
	for (i = 0; i < min(count, KD_FRAME_TRACE_EVENTS); i++) {
		const struct kd_frame_trace_event *event = &kd_frame_events[i];

		failures += !event->valid || !event->executed ||
			    !event->returned;
		max_depth = max(max_depth, event->depth);
		min_left = min(min_left, event->left);
		pr_info("kd_frame trace: event=%d cpu=%d task=%d depth=%u local=%u entry=%lx outer=%lx parent=%lx used=%lu left=%lu valid=%u executed=%u returned=%u ret=%d\n",
			i, event->cpu, event->task, event->depth, event->local,
			event->entry, event->outer, event->parent, event->used,
			event->left, event->valid, event->executed,
			event->returned, event->ret);
	}
	pr_info("kd_frame summary: events=%d max_depth=%u sampled_min_left=%lu failures=%u numa=%u stack_size=%ld stack_kind=1\n",
		count, max_depth, min_left, failures, numa,
		THREAD_SIZE);
	/* Task stacks cannot be repainted or dereferenced after their tasks exit.
	 * Report sampled bounds only; do not claim an overwritten-byte watermark. */
}
