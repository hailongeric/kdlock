// SPDX-License-Identifier: GPL-2.0
/* Read-only queue observations; compiled out of the production module. */
#include <linux/moduleparam.h>

static unsigned long kd_deferred_trace_lock;
module_param_named(spin_selftest_deferred_lock, kd_deferred_trace_lock, ulong,
		   0644);
MODULE_PARM_DESC(
	spin_selftest_deferred_lock,
	"selftest-only public spinlock address to trace, armed after JIT publication");

#define KD_DEFER_TRACE_LOCKS 8
static unsigned long kd_deferred_trace_locks[KD_DEFER_TRACE_LOCKS];
static unsigned int kd_deferred_trace_lock_count;
module_param_array_named(spin_selftest_deferred_locks, kd_deferred_trace_locks,
			 ulong, &kd_deferred_trace_lock_count, 0644);
MODULE_PARM_DESC(
	spin_selftest_deferred_locks,
	"selftest-only additional locks; set before arming the workload");

static bool kd_deferred_selected(const struct qspinlock *lock)
{
	unsigned long address = (unsigned long)lock;
	unsigned int i, count = READ_ONCE(kd_deferred_trace_lock_count);

	if (!address)
		return false;
	if (address == READ_ONCE(kd_deferred_trace_lock))
		return true;
	for (i = 0; i < min(count, (unsigned int)KD_DEFER_TRACE_LOCKS); i++)
		if (address == READ_ONCE(kd_deferred_trace_locks[i]))
			return true;
	return false;
}

static noinline void kd_spin_selftest_link(const struct kd_spin_node *node,
					   const struct kd_spin_node *previous,
					   int previous_task, int previous_cpu)
{
	/* The holder's userspace gate needs these live, even in buffered mode. */
	if (!kd_deferred_selected(((struct qspinlock *)node->execution->frame.outer_lock_addr)))
		return;
	pr_info("kd_defer link: lock=%lx node=%lx task=%d cpu=%u previous=%lx previous_task=%d previous_cpu=%u\n",
		(unsigned long)((struct qspinlock *)node->execution->frame.outer_lock_addr), (unsigned long)node,
		node->execution->frame.logical_task->pid, node->cpuid,
		(unsigned long)previous, previous_task, previous_cpu);
}

#ifdef NUMA_AWARE
static bool kd_deferred_buffered;
module_param_named(spin_selftest_deferred_buffered, kd_deferred_buffered, bool,
		   0444);
MODULE_PARM_DESC(spin_selftest_deferred_buffered,
		 "selftest-only: buffer combiner events until callers drain");

#define KD_DEFER_TRACE_EVENTS 256
enum kd_deferred_event_kind {
	KD_DEFER_APPEND = 1,
	KD_DEFER_SPLICE,
	KD_DEFER_RESTORE,
	KD_DEFER_SAVE,
	KD_DEFER_RESUME,
};

/* Only scalars survive publication: neither nodes nor tasks may be inspected
 * when this buffer is printed after their owners have returned or exited. */
struct kd_deferred_trace_event {
	unsigned long lock, request, node, head, tail, next, first, last,
		parent;
	int owner, request_task, task, head_task, next_task, result;
	unsigned int cpu, socket, request_cpu, node_cpu, node_socket;
	unsigned int head_cpu, next_cpu, depth;
	enum kd_deferred_event_kind kind;
	bool outer, linked, ready;
};
static struct kd_deferred_trace_event kd_deferred_events[KD_DEFER_TRACE_EVENTS];
static atomic_t kd_deferred_event_count = ATOMIC_INIT(0);
static atomic_t kd_deferred_overflow = ATOMIC_INIT(0);

static noinline struct kd_deferred_trace_event *
kd_deferred_event(enum kd_deferred_event_kind kind, struct qspinlock *lock)
{
	struct kd_deferred_trace_event *event;
	int index;

	/* Saturate instead of wrapping the counter after the buffer fills. */
	for (;;) {
		index = atomic_read(&kd_deferred_event_count);
		if (index >= KD_DEFER_TRACE_EVENTS) {
			atomic_set(&kd_deferred_overflow, 1);
			return NULL;
		}
		if (atomic_cmpxchg(&kd_deferred_event_count, index,
				   index + 1) == index)
			break;
	}
	event = &kd_deferred_events[index];
	event->kind = kind;
	event->lock = (unsigned long)lock;
	event->owner = current->pid;
	event->cpu = raw_smp_processor_id();
	event->socket = numa_node_id();
	event->depth =
		kd_spin_lock_stack_depth(this_cpu_ptr(&kd_spin_cpu));
	return event;
}

static void kd_spin_selftest_deferred_report(void)
{
	int i, count, incomplete = 0;

	if (!kd_deferred_buffered)
		return;
	/* Only module teardown, after all callers and producers have drained. */
	count = atomic_read(&kd_deferred_event_count);
	for (i = 0; i < count; i++) {
		const struct kd_deferred_trace_event *event =
			&kd_deferred_events[i];

		if (!smp_load_acquire(&event->ready)) {
			incomplete++;
			continue;
		}
		pr_info("kd_defer buffered: event=%d kind=%u lock=%lx owner=%d cpu=%u depth=%u socket=%u request=%lx request_task=%d request_cpu=%u node=%lx task=%d node_cpu=%u node_socket=%u head=%lx head_task=%d head_cpu=%u tail=%lx next=%lx next_task=%d next_cpu=%u first=%lx last=%lx parent=%lx result=%d outer=%u linked=%u\n",
			i, event->kind, event->lock, event->owner, event->cpu,
			event->depth, event->socket, event->request,
			event->request_task, event->request_cpu, event->node,
			event->task, event->node_cpu, event->node_socket,
			event->head, event->head_task, event->head_cpu,
			event->tail, event->next, event->next_task,
			event->next_cpu, event->first, event->last,
			event->parent, event->result, event->outer,
			event->linked);
	}
	pr_info("kd_defer buffer summary: events=%d capacity=%u overflow=%d incomplete=%d\n",
		count, KD_DEFER_TRACE_EVENTS,
		atomic_read(&kd_deferred_overflow), incomplete);
}

static noinline void kd_spin_selftest_queue_context(struct qspinlock *lock,
						    bool entering)
{
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);
	struct kd_spin_node *head = ptr->local_queue_head;
	struct kd_spin_node *tail = ptr->local_queue_tail;
	struct kd_deferred_trace_event *event;
	unsigned int depth;
	struct qspinlock *parent;

	if (!kd_deferred_buffered)
		return;
	depth = kd_spin_lock_stack_depth(ptr);
	parent = depth ? (struct qspinlock *)(unsigned long)
				 ptr->lock_addr[depth - 1] :
			 NULL;
	if (!kd_deferred_selected(lock) && !kd_deferred_selected(parent))
		return;
	event = kd_deferred_event(entering ? KD_DEFER_SAVE : KD_DEFER_RESUME,
				  lock);
	if (!event)
		return;
	event->head = (unsigned long)head;
	event->tail = (unsigned long)tail;
	/* A child may have published an ancestor's queue. Do not dereference
	 * these saved identities on return, even for diagnostic selection. */
	event->parent = (unsigned long)parent;
	smp_store_release(&event->ready, true);
}

static noinline void kd_spin_selftest_defer(const struct kd_spin_node *request,
					    const struct kd_spin_node *node)
{
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);

	if (!kd_deferred_selected(((struct qspinlock *)node->execution->frame.outer_lock_addr)))
		return;
	if (kd_deferred_buffered) {
		struct kd_deferred_trace_event *event =
			kd_deferred_event(KD_DEFER_APPEND, ((struct qspinlock *)node->execution->frame.outer_lock_addr));

		if (!event)
			return;
		event->request = (unsigned long)request;
		event->request_task = request->execution->frame.logical_task->pid;
		event->request_cpu = request->cpuid;
		event->node = (unsigned long)node;
		event->task = node->execution->frame.logical_task->pid;
		event->node_cpu = node->cpuid;
		event->node_socket = node->socket_id;
		event->head = (unsigned long)ptr->local_queue_head;
		event->tail = (unsigned long)ptr->local_queue_tail;
		smp_store_release(&event->ready, true);
		return;
	}
	pr_info("kd_defer append: lock=%lx owner=%d cpu=%u socket=%u request=%lx request_task=%d request_cpu=%u node=%lx task=%d node_cpu=%u node_socket=%u head=%lx tail=%lx\n",
		(unsigned long)((struct qspinlock *)node->execution->frame.outer_lock_addr), current->pid, raw_smp_processor_id(),
		numa_node_id(), (unsigned long)request,
		request->execution->frame.logical_task->pid, request->cpuid,
		(unsigned long)node, node->execution->frame.logical_task->pid, node->cpuid,
		node->socket_id, (unsigned long)ptr->local_queue_head,
		(unsigned long)ptr->local_queue_tail);
}

static noinline void kd_spin_selftest_splice(struct qspinlock *lock,
					     const struct kd_spin_node *next,
					     bool outer)
{
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);
	struct kd_spin_node *head = ptr->local_queue_head;
	struct kd_spin_node *tail = ptr->local_queue_tail;

	if (!kd_deferred_selected(lock))
		return;
	if (kd_deferred_buffered) {
		struct kd_deferred_trace_event *event =
			kd_deferred_event(KD_DEFER_SPLICE, lock);

		if (!event)
			return;
		event->head = (unsigned long)head;
		event->head_task = head->execution->frame.logical_task->pid;
		event->head_cpu = head->cpuid;
		event->tail = (unsigned long)tail;
		event->next = (unsigned long)next;
		event->next_task = next->execution->frame.logical_task->pid;
		event->next_cpu = next->cpuid;
		event->outer = outer;
		event->linked = READ_ONCE(tail->next) == next;
		smp_store_release(&event->ready, true);
		return;
	}
	pr_info("kd_defer splice: lock=%lx owner=%d cpu=%u outer=%u head=%lx head_task=%d head_cpu=%u tail=%lx next=%lx next_task=%d next_cpu=%u linked=%u\n",
		(unsigned long)lock, current->pid, raw_smp_processor_id(),
		outer, (unsigned long)head, head->execution->frame.logical_task->pid,
		head->cpuid, (unsigned long)tail, (unsigned long)next,
		next->execution->frame.logical_task->pid, next->cpuid,
		READ_ONCE(tail->next) == next);
}

static noinline void
kd_spin_selftest_restore(struct qspinlock *lock,
			 const struct kd_spin_node *request,
			 const struct kd_spin_node *discarded_tail, int result)
{
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);
	struct kd_spin_node *tail = ptr->local_queue_tail;
	struct kd_spin_node *first = tail ? tail->next : request->next;

	if (!kd_deferred_selected(lock))
		return;
	if (kd_deferred_buffered) {
		struct kd_deferred_trace_event *event =
			kd_deferred_event(KD_DEFER_RESTORE, lock);

		if (!event)
			return;
		event->request = (unsigned long)request;
		event->request_task = request->execution->frame.logical_task->pid;
		event->request_cpu = request->cpuid;
		event->first = (unsigned long)first;
		event->last = (unsigned long)discarded_tail;
		event->head = (unsigned long)ptr->local_queue_head;
		event->tail = (unsigned long)tail;
		event->next = (unsigned long)request->next;
		event->result = result;
		smp_store_release(&event->ready, true);
		return;
	}
	pr_info("kd_defer restore: lock=%lx owner=%d cpu=%u request=%lx request_task=%d request_cpu=%u first=%lx last=%lx head=%lx tail=%lx next=%lx result=%d\n",
		(unsigned long)lock, current->pid, raw_smp_processor_id(),
		(unsigned long)request, request->execution->frame.logical_task->pid,
		request->cpuid, (unsigned long)first,
		(unsigned long)discarded_tail,
		(unsigned long)ptr->local_queue_head, (unsigned long)tail,
		(unsigned long)request->next, result);
}
#endif
