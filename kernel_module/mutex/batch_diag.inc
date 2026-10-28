/* SPDX-License-Identifier: GPL-2.0 */
/* Optional batch observations, included before the private combiner state.
 * No observation participates in ownership, admission, ACK or drain decisions.
 * Request updates touch only this invocation's stack. Finished batches merge
 * once into per-CPU totals; a live read can cross those independent additions.
 * Take deltas only around a stopped, joined and drained measurement cohort. */
#ifndef KDLOCK_MUTEX_DIAGNOSTICS
#define KDLOCK_MUTEX_DIAGNOSTICS 0
#endif
#if KDLOCK_MUTEX_DIAGNOSTICS != 0 && KDLOCK_MUTEX_DIAGNOSTICS != 1
#error "KDLOCK_MUTEX_DIAGNOSTICS must be 0 or 1"
#endif

MODULE_INFO(mutex_batch_diag, __stringify(KDLOCK_MUTEX_DIAGNOSTICS));

#if KDLOCK_MUTEX_DIAGNOSTICS
#include <linux/bitops.h>

/* Finished bodies cannot exceed the configured attempt cap. Deferred nodes
 * consume the combiner's non-refilling 64-entry scan budget. Keep only bins
 * covering those bounded values: unnecessary full-u32 histograms exceeded
 * the captured guest's reserved module per-CPU space before provider init.
 * Bin zero stores zero; the last bins cover 16384..32767 and 64..127. */
#define KD_MUTEX_DIAG_COMPLETED_BINS 16
#define KD_MUTEX_DIAG_DEFERRED_BINS 8
#if KDLOCK_MUTEX_BATCH <= 0 || \
    KDLOCK_MUTEX_BATCH >= (1U << (KD_MUTEX_DIAG_COMPLETED_BINS - 1))
#error "mutex diagnostic completed histogram does not cover KDLOCK_MUTEX_BATCH"
#endif
#define KD_MUTEX_DIAG_REASONS(X) \
	X(UNCLASSIFIED, unclassified) \
	X(INITIAL_UNEXECUTABLE, initial_unexecutable) \
	X(SOURCE_REFUSAL, source_refusal) \
	X(NUMA_BOUNDARY, numa_boundary) \
	X(NUMA_TAIL, numa_tail) \
	X(EXECUTION_REFUSAL, execution_refusal) \
	X(EARLY_OUTER_RELEASE, early_outer_release) \
	X(NATIVE_DONE, native_done) \
	X(OWNER_TRANSFER, owner_transfer) \
	X(TOTAL_CAP, total_cap) \
	X(EMPTY_TAIL, empty_tail) \
	X(UNSUPPORTED_TAIL, unsupported_tail)

enum kd_mutex_diag_reason {
#define KD_MUTEX_DIAG_ENUM(symbol, name) KD_MUTEX_DIAG_##symbol,
	KD_MUTEX_DIAG_REASONS(KD_MUTEX_DIAG_ENUM)
#undef KD_MUTEX_DIAG_ENUM
	KD_MUTEX_DIAG_REASON_COUNT
};

/* Keep request/result observations separate from the original attempt limit.
 * A native continuation completes on its requester, so it is not classified
 * as local/remote executor service. Accepted queue ownership transfers leave
 * the body unfinished, so they count neither completion nor refusal. JIT
 * locality compares the requester's
 * immutable node with the physical executor's node immediately before entry;
 * it is not a claim that a sleepable body cannot migrate later. */
struct kd_mutex_batch_diag {
	unsigned int attempts;
	unsigned int jit_completed;
	unsigned int native_completed;
	unsigned int owner_transfers;
	unsigned int execution_refusals;
	unsigned int jit_local;
	unsigned int jit_remote;
	unsigned int deferred_total;
	unsigned int peak_deferred;
	bool request_local;
	bool scan_exhausted;
	bool small_fifo;
	enum kd_mutex_diag_reason reason;
};

#define KD_MUTEX_DIAG_TOTALS(X) \
	X(batches) \
	X(attempts) \
	X(jit_completed) \
	X(native_completed) \
	X(owner_transfers) \
	X(execution_refusals) \
	X(jit_local) \
	X(jit_remote) \
	X(deferred_total) \
	X(scan_steps) \
	X(scan_exhausted_batches) \
	X(small_fifo_batches)

struct kd_mutex_batch_totals {
#define KD_MUTEX_DIAG_FIELD(name) u64 name;
	KD_MUTEX_DIAG_TOTALS(KD_MUTEX_DIAG_FIELD)
#undef KD_MUTEX_DIAG_FIELD
	u64 completed_hist[KD_MUTEX_DIAG_COMPLETED_BINS];
	u64 deferred_peak_hist[KD_MUTEX_DIAG_DEFERRED_BINS];
	u64 stop_reason[KD_MUTEX_DIAG_REASON_COUNT];
};
_Static_assert(sizeof(struct kd_mutex_batch_totals) <= 384,
	       "mutex batch observations exceed the reserved per-CPU budget");
static DEFINE_PER_CPU(struct kd_mutex_batch_totals, kd_mutex_batch_totals);

static bool kd_mutex_diag_condition(struct kd_mutex_batch_diag *diag,
				    bool condition,
				    enum kd_mutex_diag_reason reason)
{
	if (condition)
		diag->reason = reason;
	return condition;
}

static void kd_mutex_diag_deferred(struct kd_mutex_batch_diag *diag,
				   unsigned int count)
{
	diag->deferred_total++;
	if (count > diag->peak_deferred)
		diag->peak_deferred = count;
}

static void kd_mutex_diag_scan_end(struct kd_mutex_batch_diag *diag,
				   struct kd_mutex_node *node,
				   int numa_node, unsigned int scan_left)
{
	/* Count an exhausted budget only when it prevented another otherwise
	 * eligible deferral. A terminal remote waiter alone does not qualify. */
	if (!scan_left && node && node->numa_node != numa_node &&
	    smp_load_acquire(&node->next))
		diag->scan_exhausted = true;
}

static void kd_mutex_diag_request(struct kd_mutex_batch_diag *diag,
				  struct kd_mutex_node *node)
{
	diag->attempts++;
	diag->request_local = node->numa_node == numa_node_id();
}

static void kd_mutex_diag_result(struct kd_mutex_batch_diag *diag, int result)
{
	if (!result) {
		diag->jit_completed++;
		if (diag->request_local)
			diag->jit_local++;
		else
			diag->jit_remote++;
	} else if (result == KD_EXE_NATIVE_DONE) {
		diag->native_completed++;
	} else if (result == KD_MUTEX_EXEC_SWAPPED) {
		diag->owner_transfers++;
	} else {
		diag->execution_refusals++;
	}
}

static void kd_mutex_diag_finish(struct kd_mutex_batch_diag *diag)
{
	unsigned int completed = diag->jit_completed + diag->native_completed;

	/* Per-CPU additions remain valid if a sleepable executor has migrated.
	 * Never keep a per-CPU pointer across an addition or body execution. */
	this_cpu_inc(kd_mutex_batch_totals.batches);
#define KD_MUTEX_DIAG_ADD(name) \
	this_cpu_add(kd_mutex_batch_totals.name, diag->name)
	KD_MUTEX_DIAG_ADD(attempts);
	KD_MUTEX_DIAG_ADD(jit_completed);
	KD_MUTEX_DIAG_ADD(native_completed);
	KD_MUTEX_DIAG_ADD(owner_transfers);
	KD_MUTEX_DIAG_ADD(execution_refusals);
	KD_MUTEX_DIAG_ADD(jit_local);
	KD_MUTEX_DIAG_ADD(jit_remote);
	KD_MUTEX_DIAG_ADD(deferred_total);
#undef KD_MUTEX_DIAG_ADD
	this_cpu_add(kd_mutex_batch_totals.scan_steps, diag->deferred_total);
	this_cpu_add(kd_mutex_batch_totals.scan_exhausted_batches,
		     diag->scan_exhausted);
	this_cpu_add(kd_mutex_batch_totals.small_fifo_batches, diag->small_fifo);
	/* Bin 0 contains zero; bin i>0 contains [2^(i-1), 2^i-1]. */
	this_cpu_inc(kd_mutex_batch_totals.completed_hist[fls(completed)]);
	this_cpu_inc(kd_mutex_batch_totals.deferred_peak_hist[fls(diag->peak_deferred)]);
	this_cpu_inc(kd_mutex_batch_totals.stop_reason[diag->reason]);
}

static int kd_mutex_batch_stats_get(char *buffer, const struct kernel_param *kp)
{
	struct kd_mutex_batch_totals total = { 0 };
	unsigned int i;
	int cpu, length = 0;

	(void)kp;
	for_each_possible_cpu(cpu) {
#define KD_MUTEX_DIAG_READ(name) \
		total.name += READ_ONCE(per_cpu(kd_mutex_batch_totals, cpu).name);
		KD_MUTEX_DIAG_TOTALS(KD_MUTEX_DIAG_READ)
#undef KD_MUTEX_DIAG_READ
		for (i = 0; i < KD_MUTEX_DIAG_COMPLETED_BINS; i++)
			total.completed_hist[i] += READ_ONCE(
				per_cpu(kd_mutex_batch_totals, cpu).completed_hist[i]);
		for (i = 0; i < KD_MUTEX_DIAG_DEFERRED_BINS; i++)
			total.deferred_peak_hist[i] += READ_ONCE(
				per_cpu(kd_mutex_batch_totals, cpu).deferred_peak_hist[i]);
		for (i = 0; i < KD_MUTEX_DIAG_REASON_COUNT; i++)
			total.stop_reason[i] += READ_ONCE(
				per_cpu(kd_mutex_batch_totals, cpu).stop_reason[i]);
	}
#define KD_MUTEX_DIAG_PRINT(fmt, ...) \
	(length += scnprintf(buffer + length, PAGE_SIZE - length, fmt, ##__VA_ARGS__))
	KD_MUTEX_DIAG_PRINT("{\"schema\":3,\"compiled\":1,\"total_cap\":%u,"
		"\"numa_boundary\":%u,\"deferred_handoff\":8,\"scan_budget\":64,"
		"\"completed_hist_bins\":%u,\"deferred_peak_hist_bins\":%u,",
		kd_mutex_batch_size, (unsigned int)KDLOCK_MUTEX_NUMA_BOUNDARY,
		KD_MUTEX_DIAG_COMPLETED_BINS,
		KD_MUTEX_DIAG_DEFERRED_BINS);
#ifdef NUMA_AWARE
	KD_MUTEX_DIAG_PRINT("\"numa_aware\":1,");
#else
	KD_MUTEX_DIAG_PRINT("\"numa_aware\":0,");
#endif
#define KD_MUTEX_DIAG_PRINT_TOTAL(name) \
	KD_MUTEX_DIAG_PRINT("\"" #name "\":%llu,", (unsigned long long)total.name);
	KD_MUTEX_DIAG_TOTALS(KD_MUTEX_DIAG_PRINT_TOTAL)
#undef KD_MUTEX_DIAG_PRINT_TOTAL
	KD_MUTEX_DIAG_PRINT("\"completed_hist\":[");
	for (i = 0; i < KD_MUTEX_DIAG_COMPLETED_BINS; i++)
		KD_MUTEX_DIAG_PRINT("%s%llu", i ? "," : "",
			(unsigned long long)total.completed_hist[i]);
	KD_MUTEX_DIAG_PRINT("],\"deferred_peak_hist\":[");
	for (i = 0; i < KD_MUTEX_DIAG_DEFERRED_BINS; i++)
		KD_MUTEX_DIAG_PRINT("%s%llu", i ? "," : "",
			(unsigned long long)total.deferred_peak_hist[i]);
	KD_MUTEX_DIAG_PRINT("],\"stop_reason\":{");
#define KD_MUTEX_DIAG_PRINT_REASON(symbol, name) \
	KD_MUTEX_DIAG_PRINT("%s\"" #name "\":%llu", \
		KD_MUTEX_DIAG_##symbol ? "," : "", \
		(unsigned long long)total.stop_reason[KD_MUTEX_DIAG_##symbol]);
	KD_MUTEX_DIAG_REASONS(KD_MUTEX_DIAG_PRINT_REASON)
#undef KD_MUTEX_DIAG_PRINT_REASON
	KD_MUTEX_DIAG_PRINT("},\"legacy\":{\"combiner\":%llu,\"jit_success\":%llu,"
		"\"handoff\":%llu}}\n",
		(unsigned long long)KD_MUTEX_STAT_READ(kd_mutex_combiner_count),
		(unsigned long long)KD_MUTEX_STAT_READ(kd_mutex_jit_success_count),
		(unsigned long long)KD_MUTEX_STAT_READ(kd_mutex_handoff_count));
#undef KD_MUTEX_DIAG_PRINT
	return length;
}

static const struct kernel_param_ops kd_mutex_batch_stats_ops = {
	.get = kd_mutex_batch_stats_get,
};
module_param_cb(mutex_batch_stats, &kd_mutex_batch_stats_ops, NULL, 0444);
MODULE_PARM_DESC(mutex_batch_stats,
	"Diagnostic cumulative batch observations; take deltas only while quiescent");

#define KD_MUTEX_DIAG_MEMBER struct kd_mutex_batch_diag diag;
#define KD_MUTEX_DIAG_CONDITION(batch, condition, reason) \
	kd_mutex_diag_condition(&(batch)->diag, (condition), (reason))
#define KD_MUTEX_DIAG_DEFERRED(batch) \
	kd_mutex_diag_deferred(&(batch)->diag, (batch)->deferred_count)
#define KD_MUTEX_DIAG_SCAN_END(batch, node) \
	kd_mutex_diag_scan_end(&(batch)->diag, (node), (batch)->numa_node, (batch)->scan_left)
#define KD_MUTEX_DIAG_SMALL_FIFO(batch) ((batch)->diag.small_fifo = true)
#define KD_MUTEX_DIAG_REQUEST(batch, node) kd_mutex_diag_request(&(batch)->diag, (node))
#define KD_MUTEX_DIAG_RESULT(batch, result) kd_mutex_diag_result(&(batch)->diag, (result))
#define KD_MUTEX_DIAG_STOP(batch, why) ((batch)->diag.reason = (why))
#define KD_MUTEX_DIAG_FINISH(batch) kd_mutex_diag_finish(&(batch)->diag)
#else
/* Discard diagnostic arguments, including volatile node reads, at preprocessing
 * time. The condition wrapper preserves the original short-circuit expression. */
#define KD_MUTEX_DIAG_MEMBER
#define KD_MUTEX_DIAG_CONDITION(batch, condition, reason) (condition)
#define KD_MUTEX_DIAG_DEFERRED(batch) do { } while (0)
#define KD_MUTEX_DIAG_SCAN_END(batch, node) do { } while (0)
#define KD_MUTEX_DIAG_SMALL_FIFO(batch) do { } while (0)
#define KD_MUTEX_DIAG_REQUEST(batch, node) do { } while (0)
#define KD_MUTEX_DIAG_RESULT(batch, result) do { } while (0)
#define KD_MUTEX_DIAG_STOP(batch, reason) do { } while (0)
#define KD_MUTEX_DIAG_FINISH(batch) do { } while (0)
#endif
