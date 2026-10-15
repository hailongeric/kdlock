// SPDX-License-Identifier: GPL-2.0
/* Separate, intrusive diagnostic module. Load after workload warmup on the
 * collector CPU; unload after worker drain and before retiring the workload.
 * Target storage and the provider's per-CPU counter must remain resident. */
#include <linux/cpu.h>
#include <linux/hrtimer.h>
#include <linux/kprobes.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/percpu.h>
#include <linux/string.h>

static unsigned long target_lock, success_counter;
static bool kd, spin, owned, preflight, local_first;
module_param(target_lock, ulong, 0444);
module_param(success_counter, ulong, 0444);
module_param(kd, bool, 0444);
module_param(spin, bool, 0444);
module_param(owned, bool, 0444);
module_param(preflight, bool, 0444);
module_param(local_first, bool, 0444);
MODULE_PARM_DESC(preflight, "Observe owned C-ABI preflight returns; intrusive diagnostics only");
MODULE_PARM_DESC(local_first, "Observe ABI4 local-first helper returns; intrusive diagnostics only");

struct profile_counts {
	u64 native_calls, native_slow, spin_slow, admitted, declined;
	u64 native_unlocks, owned_calls, owned_slow, owned_wait;
	u64 gate_self, gate_capture;
	u64 optimistic_acquired, optimistic_busy, optimistic_self, optimistic_other;
	u64 local_first_acquired, local_first_failed;
	u64 batches, batch_packets, histogram[12];
};
/* Diagnostic modules share a small reserved static per-CPU arena with the
 * provider. Allocate counters dynamically before exposing any callback. */
static struct profile_counts __percpu *counts;
static struct hrtimer owner_timer;
static unsigned long last_owner;
static u64 owner_samples, owner_zero, owner_changes;

static enum hrtimer_restart sample_owner(struct hrtimer *timer)
{
	/* Both supported mutex layouts put the atomic owner word at offset zero.
	 * Owned mutexes also reserve bit 3 for delegation protection. Flag-only
	 * changes are not owner transitions, including an ownerless D word.
	 * Sampling never calls either mutex API or dereferences the owner task. */
	unsigned long owner = atomic_long_read((atomic_long_t *)target_lock) &
			      (owned ? ~15UL : ~7UL);

	owner_samples++;
	if (!owner)
		owner_zero++;
	else {
		owner_changes += last_owner && owner != last_owner;
		last_owner = owner;
	}
	hrtimer_forward_now(timer, ns_to_ktime(100000));
	return HRTIMER_RESTART;
}

static int native_entry(struct kprobe *probe, struct pt_regs *regs)
{
	struct profile_counts *c = this_cpu_ptr(counts);

	if (regs->di != target_lock)
		return 0;
	if (!strcmp(probe->symbol_name, "mutex_lock"))
		c->native_calls++;
	else if (!strcmp(probe->symbol_name, "mutex_unlock"))
		c->native_unlocks++;
	else if (!strcmp(probe->symbol_name, "kd_owned_mutex_lock_self"))
		c->owned_calls++;
	else if (!strcmp(probe->symbol_name, "kd_owned_mutex_lock_slow"))
		c->owned_slow++;
	else if (!strcmp(probe->symbol_name, "kd_owned_mutex_lock_self_wait"))
		c->owned_wait++;
	else if (spin)
		c->spin_slow++;
	else
		c->native_slow++;
	return 0;
}

static int admission_entry(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	return regs->di != target_lock;
}

static int admission_return(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct profile_counts *c = this_cpu_ptr(counts);

	/* x86 bool results define AL; the upper return-register bits are not ABI. */
	if (regs_return_value(regs))
		c->admitted++;
	else
		c->declined++;
	return 0;
}

/* The gate may sleep/migrate; aggregate return counts across all CPUs.
 * Only AL belongs to a bool result. The optimistic helper returns a C enum,
 * so consume EAX; undefined upper return-register bits are never a result. */
static int preflight_return(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct profile_counts *c = this_cpu_ptr(counts);

	if (regs_return_value(regs) & 0xff)
		c->gate_self++;
	else
		c->gate_capture++;
	return 0;
}

static int optimistic_return(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct profile_counts *c = this_cpu_ptr(counts);

	/* enum kd_owned_mutex_preflight_result: ACQUIRED=0, BUSY=1, SELF=2.
	 * Unknown values remain visible and invalidate diagnostic attribution. */
	switch ((unsigned int)regs_return_value(regs)) {
	case 0: c->optimistic_acquired++; break;
	case 1: c->optimistic_busy++; break;
	case 2: c->optimistic_self++; break;
	default: c->optimistic_other++; break;
	}
	return 0;
}

static int local_first_return(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct profile_counts *c = this_cpu_ptr(counts);

	/* The fused gate returns an unsigned-long physical acquisition cookie,
	 * or zero after local optimism fails. Inspect the full pointer width. */
	if (regs_return_value(regs))
		c->local_first_acquired++;
	else
		c->local_first_failed++;
	return 0;
}

struct batch_sample { u64 before; unsigned int cpu; };
static u64 successes(unsigned int cpu)
{
	return READ_ONCE(*(u64 *)(success_counter + __per_cpu_offset[cpu]));
}

static int batch_entry(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct batch_sample *s = (void *)instance->data;

	s->cpu = raw_smp_processor_id();
	s->before = successes(s->cpu);
	return 0;
}

static int batch_return(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct batch_sample *s = (void *)instance->data;
	struct profile_counts *c = this_cpu_ptr(counts);
	u64 n = successes(s->cpu) - s->before;
	unsigned int bucket = n ? min_t(unsigned int, fls64(n), 11) : 0;

	/* One pinned benchmark worker per CPU; count completed packets in this
 * combiner invocation. The runner records actual returned JIT independently. */
	c->batches++;
	c->batch_packets += n;
	c->histogram[bucket]++;
	return 0;
}

static struct kprobe native_probe = { .symbol_name = "mutex_lock", .pre_handler = native_entry };
static struct kprobe slow_probe = { .symbol_name = "__mutex_lock_slowpath", .pre_handler = native_entry };
/* Keep Linux probes installed for owned runs: any call on the target address
 * violates object exclusivity, even if the workload result remains correct. */
static struct kprobe unlock_probe = { .symbol_name = "mutex_unlock", .pre_handler = native_entry };
static struct kprobe owned_entry_probe = { .symbol_name = "kd_owned_mutex_lock_self", .pre_handler = native_entry };
static struct kprobe owned_slow_probe = { .symbol_name = "kd_owned_mutex_lock_slow", .pre_handler = native_entry };
static struct kprobe owned_wait_probe = { .symbol_name = "kd_owned_mutex_lock_self_wait", .pre_handler = native_entry };
static struct kprobe *owned_probes[] = { &unlock_probe, &owned_entry_probe, &owned_slow_probe, &owned_wait_probe };
static struct kretprobe admission_probe = {
	.kp.symbol_name = "kd_hotlock_record_owned_mutex_pinned", .maxactive = 128,
	.entry_handler = admission_entry, .handler = admission_return,
};
static struct kretprobe batch_probe = {
	.kp.symbol_name = "kd_owned_mutex_run_batch", .maxactive = 128,
	.data_size = sizeof(struct batch_sample), .entry_handler = batch_entry, .handler = batch_return,
};

/* Entry filtering applies to both probes: other owned objects are excluded.
 * No probe or counter is added to the scored provider's ordinary fast path. */
static struct kretprobe preflight_probe = {
	.kp.symbol_name = "kd_owned_mutex_outer_preflight_v1", .maxactive = 128,
	.entry_handler = admission_entry, .handler = preflight_return,
};
static struct kretprobe optimistic_probe = {
	.kp.symbol_name = "kd_owned_mutex_try_optimistic_pinned", .maxactive = 128,
	.entry_handler = admission_entry, .handler = optimistic_return,
};
static struct kretprobe local_first_probe = {
	.kp.symbol_name = "kd_owned_mutex_outer_cabi_gate", .maxactive = 128,
	.entry_handler = admission_entry, .handler = local_first_return,
};

static int __init profile_init(void)
{
	int ret;

	if (!target_lock || (kd && (!success_counter || spin)) ||
	    (owned != kd) || ((preflight || local_first) && !owned) ||
	    (preflight && local_first))
		return -EINVAL;
	counts = alloc_percpu(struct profile_counts);
	if (!counts)
		return -ENOMEM;
	if (spin)
		slow_probe.symbol_name = "native_queued_spin_lock_slowpath";
	else {
		ret = register_kprobe(&native_probe);
		if (ret)
			goto free_counts;
	}
	ret = register_kprobe(&slow_probe);
	if (ret)
		goto native;
	if (owned) {
		ret = register_kprobes(owned_probes, ARRAY_SIZE(owned_probes));
		if (ret)
			goto slow;
	}
	if (kd) {
		ret = register_kretprobe(&admission_probe);
		if (ret)
			goto owned_out;
		ret = register_kretprobe(&batch_probe);
		if (ret)
			goto admission;
	}
	if (preflight) {
		ret = register_kretprobe(&preflight_probe);
		if (ret)
			goto batch;
		ret = register_kretprobe(&optimistic_probe);
		if (ret)
			goto preflight_gate;
	}
	if (local_first) {
		ret = register_kretprobe(&local_first_probe);
		if (ret)
			goto batch;
	}
	if (!spin) {
		hrtimer_init(&owner_timer, CLOCK_MONOTONIC, HRTIMER_MODE_REL_PINNED);
		owner_timer.function = sample_owner;
		hrtimer_start(&owner_timer, ns_to_ktime(100000), HRTIMER_MODE_REL_PINNED);
	}
	return 0;
preflight_gate:
	unregister_kretprobe(&preflight_probe);
batch:
	unregister_kretprobe(&batch_probe);
admission:
	unregister_kretprobe(&admission_probe);
owned_out:
	if (owned)
		unregister_kprobes(owned_probes, ARRAY_SIZE(owned_probes));
slow:
	unregister_kprobe(&slow_probe);
native:
	if (!spin)
		unregister_kprobe(&native_probe);
free_counts:
	free_percpu(counts);
	counts = NULL;
	return ret;
}

static void __exit profile_exit(void)
{
	struct profile_counts total = {};
	int cpu, i;

	if (!spin)
		hrtimer_cancel(&owner_timer);
	if (local_first)
		unregister_kretprobe(&local_first_probe);
	if (preflight) {
		unregister_kretprobe(&optimistic_probe);
		unregister_kretprobe(&preflight_probe);
	}
	if (kd) {
		unregister_kretprobe(&batch_probe);
		unregister_kretprobe(&admission_probe);
	}
	if (owned)
		unregister_kprobes(owned_probes, ARRAY_SIZE(owned_probes));
	unregister_kprobe(&slow_probe);
	if (!spin)
		unregister_kprobe(&native_probe);
	for_each_possible_cpu(cpu) {
		struct profile_counts *c = per_cpu_ptr(counts, cpu);
		total.native_calls += c->native_calls;
		total.native_slow += c->native_slow;
		total.spin_slow += c->spin_slow;
		total.native_unlocks += c->native_unlocks;
		total.owned_calls += c->owned_calls;
		total.owned_slow += c->owned_slow;
		total.owned_wait += c->owned_wait;
		total.gate_self += c->gate_self;
		total.gate_capture += c->gate_capture;
		total.optimistic_acquired += c->optimistic_acquired;
		total.optimistic_busy += c->optimistic_busy;
		total.optimistic_self += c->optimistic_self;
		total.optimistic_other += c->optimistic_other;
		total.local_first_acquired += c->local_first_acquired;
		total.local_first_failed += c->local_first_failed;
		total.admitted += c->admitted;
		total.declined += c->declined;
		total.batches += c->batches;
		total.batch_packets += c->batch_packets;
		for (i = 0; i < 12; i++)
			total.histogram[i] += c->histogram[i];
	}
	/* Unregistration has drained callbacks; aggregation is the last reader. */
	free_percpu(counts);
	counts = NULL;
	pr_info("kd_mutex_profile: native_calls=%llu native_slow=%llu spin_slow=%llu admitted=%llu declined=%llu batches=%llu batch_packets=%llu owner_samples=%llu owner_zero=%llu owner_changes=%llu missed=%lu\n",
		total.native_calls, total.native_slow, total.spin_slow, total.admitted, total.declined,
		total.batches, total.batch_packets, owner_samples, owner_zero, owner_changes,
		native_probe.nmissed + slow_probe.nmissed + admission_probe.nmissed + batch_probe.nmissed);
	if (owned)
		pr_info("kd_mutex_profile owned: linux_target_unlocks=%llu self_calls=%llu self_slow=%llu self_wait=%llu missed=%lu\n",
			total.native_unlocks, total.owned_calls, total.owned_slow, total.owned_wait,
			unlock_probe.nmissed + owned_entry_probe.nmissed + owned_slow_probe.nmissed + owned_wait_probe.nmissed);
	if (preflight)
		pr_info("kd_mutex_profile ownedpreflight: gate_self=%llu gate_capture=%llu optimistic_acquired=%llu optimistic_busy=%llu optimistic_self=%llu optimistic_other=%llu missed=%lu\n",
			total.gate_self, total.gate_capture, total.optimistic_acquired,
			total.optimistic_busy, total.optimistic_self, total.optimistic_other,
			preflight_probe.nmissed + preflight_probe.kp.nmissed +
			optimistic_probe.nmissed + optimistic_probe.kp.nmissed);
	if (local_first)
		pr_info("kd_mutex_profile ownedlocalfirst: acquired=%llu failed=%llu missed=%lu\n",
			total.local_first_acquired, total.local_first_failed,
			local_first_probe.nmissed + local_first_probe.kp.nmissed);
	for (i = 0; i < 12; i++)
		pr_info("kd_mutex_profile histogram: bucket=%d batches=%llu\n", i, total.histogram[i]);
}
module_init(profile_init);
module_exit(profile_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Intrusive c01 admission/native/owner/batch observations, excluded from performance acceptance");
