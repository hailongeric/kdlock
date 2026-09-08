// SPDX-License-Identifier: GPL-2.0
/* Included only in KDLOCK_SELFTEST builds; never print on a deep shadow stack. */
#include <linux/moduleparam.h>

static bool kd_frame_trace;
module_param_named(spin_selftest_trace_frames, kd_frame_trace, bool, 0444);
MODULE_PARM_DESC(
	spin_selftest_trace_frames,
	"selftest-only: record frame RSP and drained shadow-stack write watermark");

static bool kd_frame_capacity_probe;
module_param_named(spin_selftest_probe_frames, kd_frame_capacity_probe, bool,
		   0444);
MODULE_PARM_DESC(
	spin_selftest_probe_frames,
	"selftest-only: probe the real full frame context without changing capacity");

#define KD_STACK_WATERMARK_BYTE 0xa5

static void kd_spin_selftest_stack_init(void *base)
{
	/* Hooks are not installed yet; never repaint a live or suspended stack. */
	if (kd_frame_trace)
		memset(base, KD_STACK_WATERMARK_BYTE, SIZE_OF_SHADOW_STACK);
}

static unsigned long kd_spin_selftest_stack_untouched(const void *base)
{
	const unsigned char *bytes = base;
	unsigned long untouched = 0;

	while (untouched < SIZE_OF_SHADOW_STACK &&
	       bytes[untouched] == KD_STACK_WATERMARK_BYTE)
		untouched++;
	return untouched;
}

#define KD_FRAME_TRACE_EVENTS 64
static atomic_t kd_frame_event_count = ATOMIC_INIT(0);
static struct kd_frame_trace_event {
	unsigned long entry, outer, parent, used, left;
	unsigned int depth, local;
	int cpu, task, ret;
	bool valid, executed, returned;
} kd_frame_events[KD_FRAME_TRACE_EVENTS];

static noinline int
kd_spin_selftest_frame_begin(const struct kd_exec_frame *frame)
{
	struct shadow_stack *stack;
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
	stack = this_cpu_ptr(&local_shadow_stack);
	asm volatile("mov %%rsp, %0" : "=r"(sp));
	top = (unsigned long)stack->ptr;
	event->used = top - sp;
	event->left = sp - (top - SIZE_OF_SHADOW_STACK);
	event->entry = frame->entry_ip;
	event->outer = frame->outer_lock_addr;
	event->parent = frame->parent ? frame->parent->outer_lock_addr : 0;
	event->depth = frame->depth + 1;
	event->local = kd_spin_lock_stack_depth(stack);
	event->cpu = raw_smp_processor_id();
	event->task = frame->logical_task->pid;
	event->valid = kd_exec_current_frame() == frame && sp <= top &&
		       sp >= top - SIZE_OF_SHADOW_STACK;
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
	int cpu, i, count = atomic_read(&kd_frame_event_count);
	unsigned int failures = count > KD_FRAME_TRACE_EVENTS;
	unsigned int max_depth = 0;
	unsigned long min_left = SIZE_OF_SHADOW_STACK;
#ifdef NUMA_AWARE
	const unsigned int numa = 1;
#else
	const unsigned int numa = 0;
#endif

	if (!kd_frame_trace)
		return;
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
	pr_info("kd_frame summary: events=%d max_depth=%u sampled_min_left=%lu failures=%u numa=%u stack_size=%ld\n",
		count, max_depth, min_left, failures, numa,
		SIZE_OF_SHADOW_STACK);
	/* Callers are drained before unload. This is an overwritten-byte bound,
	 * not minimum RSP: untouched holes or writes of 0xa5 can hide stack use. */
	for_each_possible_cpu(cpu) {
		const struct shadow_stack *stack =
			per_cpu_ptr(&local_shadow_stack, cpu);
		unsigned long untouched = 0;

		if (stack->ptr)
			untouched = kd_spin_selftest_stack_untouched(
				(char *)stack->ptr - SIZE_OF_SHADOW_STACK);
		pr_info("kd_stack watermark: cpu=%d size=%ld untouched=%lu written=%lu valid=%u\n",
			cpu, SIZE_OF_SHADOW_STACK, untouched,
			SIZE_OF_SHADOW_STACK - untouched, !!stack->ptr);
	}
}
