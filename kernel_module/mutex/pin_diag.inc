/* SPDX-License-Identifier: GPL-2.0 */
/* Mode 2 replaces mode 1 observations to stay within the module per-CPU budget.
 * Counts never authorize acquisition, stack access, cancellation or retirement.
 * Merge only at the existing finished-batch boundaries; read quiescent deltas.
 * The optional ordered-TSC sample includes timestamp overhead and the first ACK
 * cacheline load. A zero-iteration ACK is not a zero-latency load. */
#ifndef KDLOCK_MUTEX_PIN_TSC_SHIFT
#define KDLOCK_MUTEX_PIN_TSC_SHIFT 0
#endif
#if KDLOCK_MUTEX_PIN_TSC_SHIFT != 0 && KDLOCK_MUTEX_PIN_TSC_SHIFT != 6
#error "KDLOCK_MUTEX_PIN_TSC_SHIFT must be 0 (off) or 6 (one in 64)"
#endif
#if KDLOCK_MUTEX_PIN_TSC_SHIFT && KDLOCK_MUTEX_DIAGNOSTICS != 2
#error "mutex pin TSC sampling requires diagnostics mode 2"
#endif
MODULE_INFO(mutex_pin_tsc_shift, __stringify(KDLOCK_MUTEX_PIN_TSC_SHIFT));

#if KDLOCK_MUTEX_DIAGNOSTICS == 2
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
#include <asm/tsc.h>
#endif
#define KD_MUTEX_PIN_REASONS(X) \
	X(SELF_CURRENT, self_current) \
	X(SINGLE, single) \
	X(BUDGET, budget) \
	X(WINDOW_FULL, window) \
	X(NO_LINK, no_link) \
	X(ENTRY, entry) \
	X(NUMA, numa) \
	X(DEFERRED_TAIL, deferred_tail) \
	X(DUPLICATE_CPU, duplicate_cpu) \
	X(SELF_FUTURE, self_future)
enum kd_mutex_pin_reason {
#define KD_MUTEX_PIN_ENUM(symbol, name) KD_MUTEX_PIN_##symbol,
	KD_MUTEX_PIN_REASONS(KD_MUTEX_PIN_ENUM)
#undef KD_MUTEX_PIN_ENUM
	KD_MUTEX_PIN_REASON_COUNT
};
#define KD_MUTEX_PIN_COUNTERS(X) \
	X(batches) X(selections) X(requested) X(consumed) X(cancelled) \
	X(drain_calls) X(drain_nonempty) X(drain_keep_current) \
	X(current_ack_immediate) X(current_ack_stalled) X(current_ack_loops) \
	X(cancel_ack_immediate) X(cancel_ack_stalled) X(cancel_ack_loops) \
	X(full_resumes) X(tsc_samples) X(tsc_cycles)
struct kd_mutex_pin_diag {
#define KD_MUTEX_PIN_FIELD(name) u64 name;
	KD_MUTEX_PIN_COUNTERS(KD_MUTEX_PIN_FIELD)
#undef KD_MUTEX_PIN_FIELD
	u64 occupancy_before[KD_MUTEX_PIN_WINDOW + 1];
	u64 occupancy_after[KD_MUTEX_PIN_WINDOW + 1];
	u64 refill_stop[KD_MUTEX_PIN_REASON_COUNT];
	enum kd_mutex_pin_reason reason;
};
_Static_assert(sizeof(struct kd_mutex_pin_diag) + sizeof(u64) <= 384,
	       "mutex pin observations exceed the reserved per-CPU budget");
static DEFINE_PER_CPU(struct kd_mutex_pin_diag, kd_mutex_pin_totals);
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
/* Approximate sampling ordinal, never an ownership or invocation identity.
 * Each CPU-local increment is atomic against interrupt nesting. No per-CPU
 * pointer survives a wait, body, or possible migration. */
static DEFINE_PER_CPU(u64, kd_mutex_pin_sample_seq);
static __always_inline u64 kd_mutex_pin_stamp(void)
{
	u64 value;

	/* The target rdtsc_ordered() orders older loads, but its asm has no
	 * compiler memory clobber and does not fence younger loads. Bracket
	 * both sides explicitly; the measured delta includes fence overhead. */
	asm volatile("lfence" ::: "memory");
	value = rdtsc_ordered();
	asm volatile("lfence" ::: "memory");
	return value;
}
#endif

static __always_inline bool
kd_mutex_pin_diag_condition(struct kd_mutex_pin_diag *diag, bool condition,
			    enum kd_mutex_pin_reason reason)
{
	if (condition)
		diag->reason = reason;
	return condition;
}

static __always_inline void
kd_mutex_pin_diag_wait(struct kd_mutex_pin_diag *diag,
		       struct kd_mutex_node *node, bool cancel)
{
	u64 loops = 0;
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
	bool sample = !cancel && !(this_cpu_inc_return(kd_mutex_pin_sample_seq) &
		((1ULL << KDLOCK_MUTEX_PIN_TSC_SHIFT) - 1));
	u64 begin = sample ? kd_mutex_pin_stamp() : 0;
#endif

	/* Keep exactly the same acquire-load/PAUSE protocol as the ordinary
	 * helper. Accumulate in a local register, then update private state. */
	while (smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_PINNED) {
		cpu_relax();
		loops++;
	}
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
	if (sample) {
		diag->tsc_cycles += kd_mutex_pin_stamp() - begin;
		diag->tsc_samples++;
	}
#endif
	if (cancel) {
		diag->cancel_ack_immediate += !loops;
		diag->cancel_ack_stalled += !!loops;
		diag->cancel_ack_loops += loops;
	} else {
		diag->current_ack_immediate += !loops;
		diag->current_ack_stalled += !!loops;
		diag->current_ack_loops += loops;
	}
}

static void kd_mutex_pin_diag_finish(struct kd_mutex_pin_diag *diag)
{
	unsigned int i;

	diag->batches++;
#define KD_MUTEX_PIN_ADD(name) this_cpu_add(kd_mutex_pin_totals.name, diag->name);
	KD_MUTEX_PIN_COUNTERS(KD_MUTEX_PIN_ADD)
#undef KD_MUTEX_PIN_ADD
	for (i = 0; i <= KD_MUTEX_PIN_WINDOW; i++) {
		this_cpu_add(kd_mutex_pin_totals.occupancy_before[i], diag->occupancy_before[i]);
		this_cpu_add(kd_mutex_pin_totals.occupancy_after[i], diag->occupancy_after[i]);
	}
	for (i = 0; i < KD_MUTEX_PIN_REASON_COUNT; i++)
		this_cpu_add(kd_mutex_pin_totals.refill_stop[i], diag->refill_stop[i]);
}

static int kd_mutex_pin_stats_get(char *buffer, const struct kernel_param *kp)
{
	struct kd_mutex_pin_diag total = { 0 };
	unsigned int i;
	int cpu, length = 0;

	(void)kp;
	for_each_possible_cpu(cpu) {
#define KD_MUTEX_PIN_READ(name) total.name += READ_ONCE(per_cpu(kd_mutex_pin_totals, cpu).name);
		KD_MUTEX_PIN_COUNTERS(KD_MUTEX_PIN_READ)
#undef KD_MUTEX_PIN_READ
		for (i = 0; i <= KD_MUTEX_PIN_WINDOW; i++) {
			total.occupancy_before[i] += READ_ONCE(per_cpu(kd_mutex_pin_totals, cpu).occupancy_before[i]);
			total.occupancy_after[i] += READ_ONCE(per_cpu(kd_mutex_pin_totals, cpu).occupancy_after[i]);
		}
		for (i = 0; i < KD_MUTEX_PIN_REASON_COUNT; i++)
			total.refill_stop[i] += READ_ONCE(per_cpu(kd_mutex_pin_totals, cpu).refill_stop[i]);
	}
#define KD_MUTEX_PIN_PRINT(fmt, ...) \
	(length += scnprintf(buffer + length, PAGE_SIZE - length, fmt, ##__VA_ARGS__))
	KD_MUTEX_PIN_PRINT("{\"schema\":1,\"compiled\":2,\"window\":%u,\"total_cap\":%u,"
		"\"numa_boundary\":%u,\"tsc_sample_shift\":%u,",
		(unsigned int)KD_MUTEX_PIN_WINDOW, (unsigned int)kd_mutex_batch_size,
		(unsigned int)KDLOCK_MUTEX_NUMA_BOUNDARY, (unsigned int)KDLOCK_MUTEX_PIN_TSC_SHIFT);
#define KD_MUTEX_PIN_PRINT_COUNTER(name) \
	KD_MUTEX_PIN_PRINT("\"" #name "\":%llu,", (unsigned long long)total.name);
	KD_MUTEX_PIN_COUNTERS(KD_MUTEX_PIN_PRINT_COUNTER)
#undef KD_MUTEX_PIN_PRINT_COUNTER
	KD_MUTEX_PIN_PRINT("\"occupancy_before\":[");
	for (i = 0; i <= KD_MUTEX_PIN_WINDOW; i++)
		KD_MUTEX_PIN_PRINT("%s%llu", i ? "," : "", (unsigned long long)total.occupancy_before[i]);
	KD_MUTEX_PIN_PRINT("],\"occupancy_after\":[");
	for (i = 0; i <= KD_MUTEX_PIN_WINDOW; i++)
		KD_MUTEX_PIN_PRINT("%s%llu", i ? "," : "", (unsigned long long)total.occupancy_after[i]);
	KD_MUTEX_PIN_PRINT("],\"refill_stop\":{");
#define KD_MUTEX_PIN_PRINT_REASON(symbol, name) \
	KD_MUTEX_PIN_PRINT("%s\"" #name "\":%llu", KD_MUTEX_PIN_##symbol ? "," : "", \
		(unsigned long long)total.refill_stop[KD_MUTEX_PIN_##symbol]);
	KD_MUTEX_PIN_REASONS(KD_MUTEX_PIN_PRINT_REASON)
#undef KD_MUTEX_PIN_PRINT_REASON
	KD_MUTEX_PIN_PRINT("}}\n");
#undef KD_MUTEX_PIN_PRINT
	return length;
}
static const struct kernel_param_ops kd_mutex_pin_stats_ops = {
	.get = kd_mutex_pin_stats_get,
};
module_param_cb(mutex_pin_stats, &kd_mutex_pin_stats_ops, NULL, 0444);
MODULE_PARM_DESC(mutex_pin_stats, "Selected pin observations; quiescent deltas only");
#undef KD_MUTEX_DIAG_MEMBER
#define KD_MUTEX_DIAG_MEMBER struct kd_mutex_pin_diag diag;
#undef KD_MUTEX_DIAG_FINISH
#define KD_MUTEX_DIAG_FINISH(batch) kd_mutex_pin_diag_finish(&(batch)->diag)
#define KD_MUTEX_PIN_INC(batch, name) ((batch)->diag.name++)
#define KD_MUTEX_PIN_BEGIN(batch) do { \
	BUG_ON((batch)->nr_pins > KD_MUTEX_PIN_WINDOW); \
	(batch)->diag.selections++; \
	(batch)->diag.occupancy_before[(batch)->nr_pins]++; \
} while (0)
#define KD_MUTEX_PIN_END(batch) do { \
	BUG_ON((batch)->nr_pins > KD_MUTEX_PIN_WINDOW); \
	(batch)->diag.occupancy_after[(batch)->nr_pins]++; \
	(batch)->diag.refill_stop[(batch)->diag.reason]++; \
} while (0)
#define KD_MUTEX_PIN_STOP(batch, why) ((batch)->diag.reason = (why))
#define KD_MUTEX_PIN_CONDITION(batch, condition, why) \
	kd_mutex_pin_diag_condition(&(batch)->diag, (condition), (why))
#define KD_MUTEX_PIN_WAIT(batch, node, cancel) kd_mutex_pin_diag_wait(&(batch)->diag, node, cancel)
#define KD_MUTEX_PIN_DRAIN(batch, keep) do { \
	(batch)->diag.drain_calls++; \
	if ((batch)->nr_pins > (keep)) { \
		(batch)->diag.drain_nonempty++; \
		(batch)->diag.drain_keep_current += !!(keep); \
	} \
} while (0)
#else
#define KD_MUTEX_PIN_INC(batch, name) do { } while (0)
#define KD_MUTEX_PIN_BEGIN(batch) do { } while (0)
#define KD_MUTEX_PIN_END(batch) do { } while (0)
#define KD_MUTEX_PIN_STOP(batch, why) do { } while (0)
#define KD_MUTEX_PIN_CONDITION(batch, condition, why) (condition)
#define KD_MUTEX_PIN_WAIT(batch, node, cancel) kd_mutex_proxy_wait_pinned(node)
#define KD_MUTEX_PIN_DRAIN(batch, keep) do { } while (0)
#endif
