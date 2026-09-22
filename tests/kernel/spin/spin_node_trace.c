// SPDX-License-Identifier: GPL-2.0
/* Included after kd_spin_nodes in SELFTEST builds; reporting requires drain. */
#include <linux/moduleparam.h>

static bool kd_node_trace;
module_param_named(spin_selftest_trace_nodes, kd_node_trace, bool, 0444);
MODULE_PARM_DESC(
	spin_selftest_trace_nodes,
	"selftest-only: observe per-CPU node reservations without changing capacity");

enum kd_node_event {
	KD_NODE_NATIVE_RESERVE,
	KD_NODE_VIRTUAL_RESERVE,
	KD_NODE_NATIVE_FULL,
	KD_NODE_VIRTUAL_FULL,
	KD_NODE_CONTEXT_MISSING,
	KD_NODE_PREPARE_CANCEL,
	KD_NODE_NATIVE_RETURN,
	KD_NODE_REMOTE_RETURN,
	KD_NODE_COMBINER_ENTER,
	KD_NODE_HEAD_RETURN,
	KD_NODE_REMOTE_POLL,
	KD_NODE_COMBINER_RESERVE,
	KD_NODE_RELEASE,
	KD_NODE_EVENT_COUNT,
};

struct kd_node_observation {
	unsigned long events[KD_NODE_EVENT_COUNT];
	int live, peak, peak_task;
	unsigned int peak_preempt;
	int first_event, first_count, first_expected, first_task;
	unsigned int first_preempt;
	bool peak_irq, first_irq;
};

/* Keep the module loader's small reserved per-CPU region unchanged. */
static struct kd_node_observation __percpu *kd_node_records;

static int kd_spin_selftest_nodes_init(void)
{
	if (!kd_node_trace)
		return 0;
	kd_node_records = alloc_percpu(struct kd_node_observation);
	if (!kd_node_records) {
		pr_err("kd_node: cannot allocate selftest observation records\n");
		return -ENOMEM;
	}
	return 0;
}

static void kd_spin_selftest_nodes_free(void)
{
	free_percpu(kd_node_records);
	kd_node_records = NULL;
}

static __always_inline void
kd_spin_selftest_node_event(enum kd_node_event event)
{
	struct kd_node_observation *record;
	int count, expected;
	bool valid;

	if (!kd_node_trace)
		return;
	record = this_cpu_ptr(kd_node_records);
	count = READ_ONCE(this_cpu_ptr(&kd_spin_cpu)->node_count);
	expected = record->live;
	if (event <= KD_NODE_VIRTUAL_RESERVE || event == KD_NODE_COMBINER_RESERVE)
		expected++;
	else if (event == KD_NODE_PREPARE_CANCEL ||
		 event == KD_NODE_COMBINER_ENTER || event == KD_NODE_RELEASE)
		expected--;
	valid = count == expected && count >= 0 && count <= MAX_NODES &&
		in_task() && (preempt_count() & PREEMPT_MASK);
	if (event == KD_NODE_NATIVE_FULL || event == KD_NODE_VIRTUAL_FULL)
		valid &= count >= MAX_NODES;
	if (event == KD_NODE_REMOTE_POLL)
		valid &= count > 0;
	if (!valid && !record->first_event) {
		record->first_event = event + 1;
		record->first_count = count;
		record->first_expected = expected;
		record->first_task = current->pid;
		record->first_preempt = preempt_count();
		record->first_irq = irqs_disabled();
	}
	record->events[event]++;
	record->live = count;
	/* Failed overflow attempts are never counted as successful high-water. */
	if (event <= KD_NODE_VIRTUAL_RESERVE && count > record->peak) {
		record->peak = count;
		record->peak_task = current->pid;
		record->peak_preempt = preempt_count();
		record->peak_irq = irqs_disabled();
	}
}

static void kd_spin_selftest_nodes_report(void)
{
	int cpu, cpus = 0;

	if (!kd_node_trace || !kd_node_records)
		return;
	/* No producer can still be active; only scalar state is read here. */
	for_each_possible_cpu(cpu) {
		const struct kd_node_observation *r =
			per_cpu_ptr(kd_node_records, cpu);

		cpus++;
		pr_info("kd_node trace: cpu=%d native=%lu virtual=%lu native_full=%lu virtual_full=%lu context_missing=%lu prepare_cancel=%lu native_return=%lu remote_return=%lu combiner=%lu head=%lu poll=%lu reacquire=%lu release=%lu live=%d actual=%d peak=%d peak_task=%d peak_preempt=%u peak_irq=%u first_event=%d first_count=%d first_expected=%d first_task=%d first_preempt=%u first_irq=%u\n",
			cpu, r->events[KD_NODE_NATIVE_RESERVE],
			r->events[KD_NODE_VIRTUAL_RESERVE],
			r->events[KD_NODE_NATIVE_FULL],
			r->events[KD_NODE_VIRTUAL_FULL],
			r->events[KD_NODE_CONTEXT_MISSING],
			r->events[KD_NODE_PREPARE_CANCEL],
			r->events[KD_NODE_NATIVE_RETURN],
			r->events[KD_NODE_REMOTE_RETURN],
			r->events[KD_NODE_COMBINER_ENTER],
			r->events[KD_NODE_HEAD_RETURN],
			r->events[KD_NODE_REMOTE_POLL],
			r->events[KD_NODE_COMBINER_RESERVE],
			r->events[KD_NODE_RELEASE], r->live,
			READ_ONCE(per_cpu_ptr(&kd_spin_cpu, cpu)->node_count),
			r->peak, r->peak_task, r->peak_preempt, r->peak_irq,
			r->first_event, r->first_count, r->first_expected,
			r->first_task, r->first_preempt, r->first_irq);
	}
	pr_info("kd_node summary: cpus=%d capacity=%d record_bytes=%zu\n", cpus,
		MAX_NODES, sizeof(struct kd_node_observation));
}
