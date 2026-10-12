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
static bool kd, spin;
module_param(target_lock, ulong, 0444);
module_param(success_counter, ulong, 0444);
module_param(kd, bool, 0444);
module_param(spin, bool, 0444);

struct profile_counts {
	u64 native_calls, native_slow, spin_slow, admitted, declined;
	u64 batches, batch_packets, histogram[12];
};
static DEFINE_PER_CPU(struct profile_counts, counts);
static struct hrtimer owner_timer;
static unsigned long last_owner;
static u64 owner_samples, owner_zero, owner_changes;

static enum hrtimer_restart sample_owner(struct hrtimer *timer)
{
	unsigned long owner = atomic_long_read(&((struct mutex *)target_lock)->owner) & ~7UL;

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
	struct profile_counts *c = this_cpu_ptr(&counts);

	if (regs->di != target_lock)
		return 0;
	if (!strcmp(probe->symbol_name, "mutex_lock"))
		c->native_calls++;
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
	struct profile_counts *c = this_cpu_ptr(&counts);

	/* x86 bool results define AL; the upper return-register bits are not ABI. */
	if (regs_return_value(regs) & 0xff)
		c->admitted++;
	else
		c->declined++;
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
	struct profile_counts *c = this_cpu_ptr(&counts);
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
static struct kretprobe admission_probe = {
	.kp.symbol_name = "kd_hotlock_record_mutex_pinned", .maxactive = 128,
	.entry_handler = admission_entry, .handler = admission_return,
};
static struct kretprobe batch_probe = {
	.kp.symbol_name = "kd_mutex_run_combiner", .maxactive = 128,
	.data_size = sizeof(struct batch_sample), .entry_handler = batch_entry, .handler = batch_return,
};

static int __init profile_init(void)
{
	int ret;

	if (!target_lock || (kd && (!success_counter || spin)))
		return -EINVAL;
	if (spin)
		slow_probe.symbol_name = "native_queued_spin_lock_slowpath";
	else {
		ret = register_kprobe(&native_probe);
		if (ret)
			return ret;
	}
	ret = register_kprobe(&slow_probe);
	if (ret)
		goto native;
	if (kd) {
		ret = register_kretprobe(&admission_probe);
		if (ret)
			goto slow;
		ret = register_kretprobe(&batch_probe);
		if (ret)
			goto admission;
	}
	if (!spin) {
		hrtimer_init(&owner_timer, CLOCK_MONOTONIC, HRTIMER_MODE_REL_PINNED);
		owner_timer.function = sample_owner;
		hrtimer_start(&owner_timer, ns_to_ktime(100000), HRTIMER_MODE_REL_PINNED);
	}
	return 0;
admission:
	unregister_kretprobe(&admission_probe);
slow:
	unregister_kprobe(&slow_probe);
native:
	if (!spin)
		unregister_kprobe(&native_probe);
	return ret;
}

static void __exit profile_exit(void)
{
	struct profile_counts total = {};
	int cpu, i;

	if (!spin)
		hrtimer_cancel(&owner_timer);
	if (kd) {
		unregister_kretprobe(&batch_probe);
		unregister_kretprobe(&admission_probe);
	}
	unregister_kprobe(&slow_probe);
	if (!spin)
		unregister_kprobe(&native_probe);
	for_each_possible_cpu(cpu) {
		struct profile_counts *c = &per_cpu(counts, cpu);
		total.native_calls += c->native_calls;
		total.native_slow += c->native_slow;
		total.spin_slow += c->spin_slow;
		total.admitted += c->admitted;
		total.declined += c->declined;
		total.batches += c->batches;
		total.batch_packets += c->batch_packets;
		for (i = 0; i < 12; i++)
			total.histogram[i] += c->histogram[i];
	}
	pr_info("kd_mutex_profile: native_calls=%llu native_slow=%llu spin_slow=%llu admitted=%llu declined=%llu batches=%llu batch_packets=%llu owner_samples=%llu owner_zero=%llu owner_changes=%llu missed=%lu\n",
		total.native_calls, total.native_slow, total.spin_slow, total.admitted, total.declined,
		total.batches, total.batch_packets, owner_samples, owner_zero, owner_changes,
		native_probe.nmissed + slow_probe.nmissed + admission_probe.nmissed + batch_probe.nmissed);
	for (i = 0; i < 12; i++)
		pr_info("kd_mutex_profile histogram: bucket=%d batches=%llu\n", i, total.histogram[i]);
}
module_init(profile_init);
module_exit(profile_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Intrusive c01 admission/native/owner/batch observations, excluded from performance acceptance");
