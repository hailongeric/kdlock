/* SPDX-License-Identifier: GPL-2.0 */
/* Optional cumulative capture/lifecycle observations. Read only after drain.
 * CPU-local updates add no guard or decision to the execution protocol. */
#include <linux/ktime.h>
#include <linux/percpu.h>

#define KD_SERVICE_OBSERVE_ROOTS 2
enum kd_service_observe_stat {
	KD_SERVICE_OBSERVE_SELECTED,
	KD_SERVICE_OBSERVE_LOCAL,
	KD_SERVICE_OBSERVE_LOCAL_NO_IMAGE,
	KD_SERVICE_OBSERVE_LOCAL_SUCCESS,
	KD_SERVICE_OBSERVE_LOCAL_CANCEL,
	KD_SERVICE_OBSERVE_PREPUBLICATION_CANCEL,
	KD_SERVICE_OBSERVE_SUBMITTED,
	KD_SERVICE_OBSERVE_BOUND,
	KD_SERVICE_OBSERVE_JIT_ENTERED,
	KD_SERVICE_OBSERVE_HANDBACK,
	KD_SERVICE_OBSERVE_RETURNED,
	KD_SERVICE_OBSERVE_HANDBACK_FINISHED,
	KD_SERVICE_OBSERVE_CANCELED,
	KD_SERVICE_OBSERVE_LOCAL_NS,
	KD_SERVICE_OBSERVE_DISPATCH_SAMPLES,
	KD_SERVICE_OBSERVE_DISPATCH_NS,
	KD_SERVICE_OBSERVE_SHADOW_SAMPLES,
	KD_SERVICE_OBSERVE_SHADOW_NS,
	KD_SERVICE_OBSERVE_INVALID_CLOCK,
	KD_SERVICE_OBSERVE_COUNT,
};
static bool kd_service_observe;
static char kd_service_observe_comm[TASK_COMM_LEN];
static unsigned long kd_service_observe_entries[KD_SERVICE_OBSERVE_ROOTS];
static unsigned int kd_service_observe_entry_count;
module_param_named(service_observe, kd_service_observe, bool, 0444);
module_param_string(service_observe_comm, kd_service_observe_comm,
		    sizeof(kd_service_observe_comm), 0444);
module_param_array_named(service_observe_entries, kd_service_observe_entries,
			 ulong, &kd_service_observe_entry_count, 0444);
MODULE_PARM_DESC(service_observe, "Collect selected origin capture and lifecycle totals");
MODULE_PARM_DESC(service_observe_comm, "Exact origin task name for observations");
MODULE_PARM_DESC(service_observe_entries, "At most two source entries for observations");

struct kd_service_observe_cpu {
	u64 value[KD_SERVICE_OBSERVE_ROOTS][KD_SERVICE_OBSERVE_COUNT];
};
static DEFINE_PER_CPU(struct kd_service_observe_cpu, kd_service_observed);

static void kd_service_observe_add(int index, enum kd_service_observe_stat stat, u64 value)
{
	if (unlikely(index >= 0))
		this_cpu_add(kd_service_observed.value[index][stat], value);
}

static int kd_service_observe_select(unsigned long ip, const char *comm)
{
	unsigned int i;

	if (likely(!kd_service_observe) || !kd_service_observe_comm[0] ||
	    strncmp(comm, kd_service_observe_comm, TASK_COMM_LEN))
		return -1;
	for (i = 0; i < kd_service_observe_entry_count; ++i) {
		if (kd_service_observe_entries[i] != ip)
			continue;
		kd_service_observe_add(i, KD_SERVICE_OBSERVE_SELECTED, 1);
		return i;
	}
	return -1;
}

static u64 kd_service_observe_start(int index)
{
	return unlikely(index >= 0) ? ktime_get_ns() : 0;
}

static void kd_service_observe_elapsed(int index, enum kd_service_observe_stat ns,
	enum kd_service_observe_stat samples, u64 start)
{
	u64 end;

	if (likely(index < 0))
		return;
	end = ktime_get_ns();
	kd_service_observe_add(index, samples, 1);
	if (end < start)
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_INVALID_CLOCK, 1);
	else
		kd_service_observe_add(index, ns, end - start);
}

static void kd_service_observe_shadow_end(struct kd_service_root *root)
{
	kd_service_observe_elapsed(root->observe_index, KD_SERVICE_OBSERVE_SHADOW_NS,
		KD_SERVICE_OBSERVE_SHADOW_SAMPLES, root->observe_shadow_start);
}

static void kd_service_observe_event(int index, const char *event)
{
	if (likely(index < 0))
		return;
	if (!strcmp(event, "enter"))
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_BOUND, 1);
	else if (!strcmp(event, "cancel"))
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_CANCELED, 1);
	else if (!strcmp(event, "handoff_ready"))
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_HANDBACK, 1);
	else if (!strcmp(event, "returned"))
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_RETURNED, 1);
	else if (!strcmp(event, "handoff_finished"))
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_HANDBACK_FINISHED, 1);
}

static int kd_service_observe_stats_get(char *buffer, const struct kernel_param *kp)
{
	static const char * const names[KD_SERVICE_OBSERVE_COUNT] = {
		"selected", "local", "local_no_image", "local_success", "local_cancel",
		"prepublication_cancel", "submitted", "bound", "jit_entered", "handback",
		"returned", "handback_finished", "canceled", "local_ns", "dispatch_samples",
		"dispatch_ns", "shadow_samples", "shadow_ns", "invalid_clock",
	};
	unsigned int i, stat;
	int cpu, used = 0;

	(void)kp;
	for (i = 0; i < kd_service_observe_entry_count; ++i) {
		used += scnprintf(buffer + used, PAGE_SIZE - used, "entry=%lx", kd_service_observe_entries[i]);
		for (stat = 0; stat < KD_SERVICE_OBSERVE_COUNT; ++stat) {
			u64 total = 0;

			for_each_possible_cpu(cpu)
				total += READ_ONCE(per_cpu(kd_service_observed, cpu).value[i][stat]);
			used += scnprintf(buffer + used, PAGE_SIZE - used, " %s=%llu",
				names[stat], (unsigned long long)total);
		}
		used += scnprintf(buffer + used, PAGE_SIZE - used, "\n");
	}
	return used;
}
static const struct kernel_param_ops kd_service_observe_stats_ops = {
	.get = kd_service_observe_stats_get,
};
module_param_cb(service_observe_stats, &kd_service_observe_stats_ops, NULL, 0444);
