/* SPDX-License-Identifier: GPL-2.0 */
/* Mode 2 uses one preallocated dynamic per-CPU diagnostic record. The module
 * loader's reserved per-CPU chunk remains dedicated to the ordinary runtime.
 * Counts never authorize acquisition, stack access, cancellation or retirement.
 * Merge executor totals at finished-batch boundaries and origin totals once at
 * the end of the initial pinned phase. Read only quiescent deltas.
 * Schema 4 describes one exact current claim and an independent bounded READY
 * candidate observation. Schemas 1..3 retain their historical window meanings. */
#ifndef KDLOCK_MUTEX_PIN_TSC_SHIFT
#define KDLOCK_MUTEX_PIN_TSC_SHIFT 0
#endif
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
#error "READY claims have no ACK wait; mutex pin TSC sampling is retired"
#endif
MODULE_INFO(mutex_pin_tsc_shift, __stringify(KDLOCK_MUTEX_PIN_TSC_SHIFT));

#if KDLOCK_MUTEX_DIAGNOSTICS == 2
#define KD_MUTEX_PIN_REASONS(X) \
	X(CLAIMED, claimed) \
	X(SELF_CURRENT, self_current) \
	X(CURRENT_NOT_READY, current_not_ready)
enum kd_mutex_pin_reason {
#define KD_MUTEX_PIN_ENUM(symbol, name) KD_MUTEX_PIN_##symbol,
	KD_MUTEX_PIN_REASONS(KD_MUTEX_PIN_ENUM)
#undef KD_MUTEX_PIN_ENUM
	KD_MUTEX_PIN_REASON_COUNT
};
#define KD_MUTEX_PIN_READY_LIMIT 8
#define KD_MUTEX_PIN_EXECUTOR_COUNTERS(X) \
	X(batches) X(selections) X(claims) X(retired_claims) X(cancelled_claims) \
	X(drain_calls) X(drain_nonempty) X(retain_current_calls) X(full_resumes) \
	X(epoch_admission_attempts) X(epoch_admission_refusals)
#define KD_MUTEX_PIN_ORIGIN_COUNTERS(X) \
	X(wait_episodes) X(initial_pin_retained) X(initial_pin_dropped) \
	X(initial_budget_completed) X(budget_expired_episodes) X(expiry_checks) \
	X(withdrawals) X(forced_cancellations) X(withdrawal_reservations)
#define KD_MUTEX_PIN_COUNTERS(X) \
	KD_MUTEX_PIN_EXECUTOR_COUNTERS(X) \
	KD_MUTEX_PIN_ORIGIN_COUNTERS(X)
struct kd_mutex_pin_diag {
#define KD_MUTEX_PIN_FIELD(name) u64 name;
	KD_MUTEX_PIN_COUNTERS(KD_MUTEX_PIN_FIELD)
#undef KD_MUTEX_PIN_FIELD
	u64 occupancy_before[KD_MUTEX_CLAIM_SLOTS + 1];
	u64 occupancy_after[KD_MUTEX_CLAIM_SLOTS + 1];
	u64 selection_result[KD_MUTEX_PIN_REASON_COUNT];
	u64 epoch_ready_candidates[KD_MUTEX_PIN_READY_LIMIT + 1];
	enum kd_mutex_pin_reason reason;
};
struct kd_mutex_pin_cpu {
	struct kd_mutex_pin_diag totals;
};
/* Schema 4 uses 296 dynamic bytes per CPU, including the bounded READY
 * histogram. Mode 1 retains its separate 384-byte static per-CPU record. */
_Static_assert(sizeof(struct kd_mutex_pin_cpu) <= 304,
	       "mutex pin observations exceed the bounded per-CPU footprint");
static struct kd_mutex_pin_cpu __percpu *kd_mutex_pin_cpus;
/* These are dynamic per-CPU address operands, not physical per_cpu_ptr results.
 * Keep this_cpu operations atomic against preemption/interrupt nesting; never
 * retain a physical CPU pointer across a wait, body, or possible migration. */
#define kd_mutex_pin_totals (kd_mutex_pin_cpus->totals)

static int kd_mutex_pin_diag_init(void)
{
	struct kd_mutex_pin_cpu __percpu *storage;
	int cpu;

	storage = alloc_percpu(struct kd_mutex_pin_cpu);
	if (!storage)
		return -ENOMEM;
	for_each_possible_cpu(cpu)
		memset(per_cpu_ptr(storage, cpu), 0, sizeof(*storage));
	/* param_attr_show holds this same target-kernel mutex while calling
	 * the getter. Publish only fully initialized storage. */
	kernel_param_lock(THIS_MODULE);
	BUG_ON(kd_mutex_pin_cpus);
	WRITE_ONCE(kd_mutex_pin_cpus, storage);
	kernel_param_unlock(THIS_MODULE);
	return 0;
}

static void kd_mutex_pin_diag_exit(void)
{
	struct kd_mutex_pin_cpu __percpu *storage;

	/* Ordinary exact caller/source/frame drain precedes this teardown.
	 * Serialize the remaining sysfs readers, detach first, then free. A
	 * later getter sees ENODEV, even before sysfs removes its attribute. */
	kernel_param_lock(THIS_MODULE);
	storage = kd_mutex_pin_cpus;
	WRITE_ONCE(kd_mutex_pin_cpus, NULL);
	kernel_param_unlock(THIS_MODULE);
	if (storage)
		free_percpu(storage);
}
#define KD_MUTEX_PIN_DIAG_INIT() kd_mutex_pin_diag_init()
#define KD_MUTEX_PIN_DIAG_EXIT() kd_mutex_pin_diag_exit()

static void kd_mutex_pin_origin_finish(const struct kd_mutex_pin_origin *origin,
				       bool retained)
{
	/* The origin is still pinned at this merge. No per-poll shared writes,
	 * timestamps, or observational checks participate in gate/state decisions. */
	this_cpu_inc(kd_mutex_pin_totals.wait_episodes);
	this_cpu_add(kd_mutex_pin_totals.initial_pin_retained, retained);
	this_cpu_add(kd_mutex_pin_totals.initial_pin_dropped, !retained);
	this_cpu_add(kd_mutex_pin_totals.initial_budget_completed,
		     retained && !origin->budget_expired);
	this_cpu_add(kd_mutex_pin_totals.budget_expired_episodes, origin->budget_expired);
	this_cpu_add(kd_mutex_pin_totals.expiry_checks, origin->expiry_checks);
	this_cpu_add(kd_mutex_pin_totals.withdrawals, origin->withdrawn);
	this_cpu_add(kd_mutex_pin_totals.forced_cancellations, origin->forced_cancel);
	this_cpu_add(kd_mutex_pin_totals.withdrawal_reservations, origin->withdrawal_reservations);
}

static __always_inline bool
kd_mutex_pin_diag_condition(struct kd_mutex_pin_diag *diag, bool condition,
			    enum kd_mutex_pin_reason reason)
{
	if (condition)
		diag->reason = reason;
	return condition;
}

/* Called once after successful epoch admission, before any current claim.
 * The gate excludes withdrawal and this owner retains the linked queue. Count
 * only an already-published compatible prefix; never wait for a link or READY,
 * inspect a stack/image, or use this observation to authorize an invocation.
 * The final bin is a lower bound, not a promise of future body execution. */
static void kd_mutex_pin_diag_epoch_ready(struct kd_mutex_pin_diag *diag,
					struct kd_mutex *lock,
					struct kd_mutex_node *node)
{
	int cpus[KD_MUTEX_PIN_READY_LIMIT];
	unsigned int count = 0, i;
	unsigned long entry = 0;

	while (node && count < KD_MUTEX_PIN_READY_LIMIT) {
		u64 generation;
		unsigned long ip;
		int cpu;

		if (smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_READY)
			break;
		generation = READ_ONCE(node->count_seq);
		if ((generation & 1) || READ_ONCE(node->counted_lock) != lock ||
		    READ_ONCE(node->entry_abi) != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
		    READ_ONCE(node->packet_state) != KD_PACKET_MINIMAL)
			break;
		ip = READ_ONCE(node->regs.ip);
		if (!ip || (count && ip != entry))
			break;
		cpu = (node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;
		if (cpu == raw_smp_processor_id())
			break;
		for (i = 0; i < count && cpus[i] != cpu; i++)
			;
		if (i != count || READ_ONCE(node->count_seq) != generation ||
		    READ_ONCE(node->counted_lock) != lock)
			break;
		cpus[count++] = cpu;
		entry = ip;
		if (count == KD_MUTEX_PIN_READY_LIMIT)
			break;
		node = smp_load_acquire(&node->next);
	}
	diag->epoch_ready_candidates[count]++;
}

static void kd_mutex_pin_diag_finish(struct kd_mutex_pin_diag *diag)
{
	unsigned int i;

	diag->batches++;
#define KD_MUTEX_PIN_ADD(name) this_cpu_add(kd_mutex_pin_totals.name, diag->name);
	KD_MUTEX_PIN_EXECUTOR_COUNTERS(KD_MUTEX_PIN_ADD)
#undef KD_MUTEX_PIN_ADD
	for (i = 0; i <= KD_MUTEX_CLAIM_SLOTS; i++) {
		this_cpu_add(kd_mutex_pin_totals.occupancy_before[i], diag->occupancy_before[i]);
		this_cpu_add(kd_mutex_pin_totals.occupancy_after[i], diag->occupancy_after[i]);
	}
	for (i = 0; i < KD_MUTEX_PIN_REASON_COUNT; i++)
		this_cpu_add(kd_mutex_pin_totals.selection_result[i], diag->selection_result[i]);
	for (i = 0; i <= KD_MUTEX_PIN_READY_LIMIT; i++)
		this_cpu_add(kd_mutex_pin_totals.epoch_ready_candidates[i], diag->epoch_ready_candidates[i]);
}

static int kd_mutex_pin_stats_get(char *buffer, const struct kernel_param *kp)
{
	struct kd_mutex_pin_diag total = { 0 };
	struct kd_mutex_pin_cpu __percpu *storage = kd_mutex_pin_cpus;
	unsigned int i;
	int cpu, length = 0;

	/* kernel/params.c calls get under kernel_param_lock(THIS_MODULE),
	 * which also serializes publication and final detach above. */
	(void)kp;
	if (!storage)
		return -ENODEV;
	for_each_possible_cpu(cpu) {
		struct kd_mutex_pin_diag *local = &per_cpu_ptr(storage, cpu)->totals;
#define KD_MUTEX_PIN_READ(name) total.name += READ_ONCE(local->name);
		KD_MUTEX_PIN_COUNTERS(KD_MUTEX_PIN_READ)
#undef KD_MUTEX_PIN_READ
		for (i = 0; i <= KD_MUTEX_CLAIM_SLOTS; i++) {
			total.occupancy_before[i] += READ_ONCE(local->occupancy_before[i]);
			total.occupancy_after[i] += READ_ONCE(local->occupancy_after[i]);
		}
		for (i = 0; i < KD_MUTEX_PIN_REASON_COUNT; i++)
			total.selection_result[i] += READ_ONCE(local->selection_result[i]);
		for (i = 0; i <= KD_MUTEX_PIN_READY_LIMIT; i++)
			total.epoch_ready_candidates[i] += READ_ONCE(local->epoch_ready_candidates[i]);
	}
#define KD_MUTEX_PIN_PRINT(fmt, ...) \
	(length += scnprintf(buffer + length, PAGE_SIZE - length, fmt, ##__VA_ARGS__))
	KD_MUTEX_PIN_PRINT("{\"schema\":4,\"compiled\":2,\"claim_slots\":%u,\"ready_policy\":\"epoch\",\"total_cap\":%u,"
		"\"numa_boundary\":%u,\"initial_spin_budget\":%u,",
		(unsigned int)KD_MUTEX_CLAIM_SLOTS, (unsigned int)kd_mutex_batch_size,
		(unsigned int)KDLOCK_MUTEX_NUMA_BOUNDARY, (unsigned int)KDLOCK_MUTEX_SPIN_BUDGET);
#define KD_MUTEX_PIN_PRINT_COUNTER(name) \
	KD_MUTEX_PIN_PRINT("\"" #name "\":%llu,", (unsigned long long)total.name);
	KD_MUTEX_PIN_COUNTERS(KD_MUTEX_PIN_PRINT_COUNTER)
#undef KD_MUTEX_PIN_PRINT_COUNTER
	KD_MUTEX_PIN_PRINT("\"occupancy_before\":[");
	for (i = 0; i <= KD_MUTEX_CLAIM_SLOTS; i++)
		KD_MUTEX_PIN_PRINT("%s%llu", i ? "," : "", (unsigned long long)total.occupancy_before[i]);
	KD_MUTEX_PIN_PRINT("],\"occupancy_after\":[");
	for (i = 0; i <= KD_MUTEX_CLAIM_SLOTS; i++)
		KD_MUTEX_PIN_PRINT("%s%llu", i ? "," : "", (unsigned long long)total.occupancy_after[i]);
	KD_MUTEX_PIN_PRINT("],\"selection_result\":{");
#define KD_MUTEX_PIN_PRINT_REASON(symbol, name) \
	KD_MUTEX_PIN_PRINT("%s\"" #name "\":%llu", KD_MUTEX_PIN_##symbol ? "," : "", \
		(unsigned long long)total.selection_result[KD_MUTEX_PIN_##symbol]);
	KD_MUTEX_PIN_REASONS(KD_MUTEX_PIN_PRINT_REASON)
#undef KD_MUTEX_PIN_PRINT_REASON
	KD_MUTEX_PIN_PRINT("},\"epoch_ready_candidates\":[");
	for (i = 0; i <= KD_MUTEX_PIN_READY_LIMIT; i++)
		KD_MUTEX_PIN_PRINT("%s%llu", i ? "," : "", (unsigned long long)total.epoch_ready_candidates[i]);
	KD_MUTEX_PIN_PRINT("]}\n");
#undef KD_MUTEX_PIN_PRINT
	return length;
}
static const struct kernel_param_ops kd_mutex_pin_stats_ops = {
	.get = kd_mutex_pin_stats_get,
};
module_param_cb(mutex_pin_stats, &kd_mutex_pin_stats_ops, NULL, 0444);
MODULE_PARM_DESC(mutex_pin_stats, "Single-current claim, READY candidates and initial spin observations; schema 4, quiescent deltas only");
#undef KD_MUTEX_DIAG_MEMBER
#define KD_MUTEX_DIAG_MEMBER struct kd_mutex_pin_diag diag;
#undef KD_MUTEX_DIAG_FINISH
#define KD_MUTEX_DIAG_FINISH(batch) kd_mutex_pin_diag_finish(&(batch)->diag)
#define KD_MUTEX_PIN_INC(batch, name) ((batch)->diag.name++)
#define KD_MUTEX_PIN_EPOCH_RESULT(batch, accepted) do { \
	(batch)->diag.epoch_admission_attempts++; \
	(batch)->diag.epoch_admission_refusals += !(accepted); \
} while (0)
#define KD_MUTEX_PIN_EPOCH_READY(batch, head) \
	kd_mutex_pin_diag_epoch_ready(&(batch)->diag, (batch)->lock, (head))
#define KD_MUTEX_PIN_BEGIN(batch) do { \
	BUG_ON((batch)->nr_pins > KD_MUTEX_CLAIM_SLOTS); \
	(batch)->diag.selections++; \
	(batch)->diag.occupancy_before[(batch)->nr_pins]++; \
} while (0)
#define KD_MUTEX_PIN_END(batch) do { \
	BUG_ON((batch)->nr_pins > KD_MUTEX_CLAIM_SLOTS); \
	(batch)->diag.occupancy_after[(batch)->nr_pins]++; \
	BUG_ON((unsigned int)(batch)->diag.reason >= KD_MUTEX_PIN_REASON_COUNT); \
	(batch)->diag.selection_result[(batch)->diag.reason]++; \
} while (0)
#define KD_MUTEX_PIN_STOP(batch, why) ((batch)->diag.reason = (why))
#define KD_MUTEX_PIN_CONDITION(batch, condition, why) \
	kd_mutex_pin_diag_condition(&(batch)->diag, (condition), (why))
#define KD_MUTEX_PIN_ASSERT(batch, node) kd_mutex_batch_pin_assert(batch, node)
#define KD_MUTEX_PIN_DRAIN(batch, keep) do { \
	(batch)->diag.drain_calls++; \
	if ((batch)->nr_pins > (keep)) { \
		(batch)->diag.drain_nonempty++; \
	} \
	(batch)->diag.retain_current_calls += !!(keep); \
} while (0)
#else
#define KD_MUTEX_PIN_DIAG_INIT() (0)
#define KD_MUTEX_PIN_DIAG_EXIT() do { } while (0)
#define KD_MUTEX_PIN_INC(batch, name) do { } while (0)
#define KD_MUTEX_PIN_EPOCH_RESULT(batch, accepted) do { } while (0)
#define KD_MUTEX_PIN_EPOCH_READY(batch, head) do { } while (0)
#define KD_MUTEX_PIN_BEGIN(batch) do { } while (0)
#define KD_MUTEX_PIN_END(batch) do { } while (0)
#define KD_MUTEX_PIN_STOP(batch, why) do { } while (0)
#define KD_MUTEX_PIN_CONDITION(batch, condition, why) (condition)
#define KD_MUTEX_PIN_ASSERT(batch, node) kd_mutex_batch_pin_assert(batch, node)
#define KD_MUTEX_PIN_DRAIN(batch, keep) do { } while (0)
#endif
