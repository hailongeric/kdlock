/* SPDX-License-Identifier: GPL-2.0 */
/*
 * CPU-local exact-key lock counters. Statistics grant admission only; stable
 * tickets and frames own requests independently of heat and migration.
 */
#include <asm/tsc.h>
#include <linux/errno.h>
#include <linux/export.h>
#include <linux/hash.h>
#include <linux/moduleparam.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include "kd_hotlock.h"

#define KD_HOTLOCK_CHECK_INTERVAL 1024U
#define KD_HOTLOCK_CPU_WINDOW 40000000000UL
#define KD_HOTLOCK_INITIAL_WINDOW 2500000000UL
#define KD_HOTLOCK_SPIN_INITIAL_WINDOW 1250000000UL
#define KD_HOTLOCK_SAMPLE_TARGET 1024U
/* CPU profiling cadence must not change per-lock promotion frequency. */
#define KD_HOTLOCK_SPIN_SAMPLE_TARGET 512U
#define KD_HOTLOCK_HASH_BITS 8
#define KD_HOTLOCK_BUCKETS (1U << KD_HOTLOCK_HASH_BITS)
#define KD_HOTLOCK_ENTRIES 256

/*
 * Fixed storage is reserved at init, never allocated while acquiring a lock.
 * Entries are exact identities, not ranked candidates: no score, replacement
 * or inherited counts. A full table declines unknown identities.
 */
struct kd_hotlock_entry {
	unsigned long address, begin;
	u16 count, next;
	u8 hot;
};

struct kd_hotlock_table {
	unsigned int busy, rate_samples;
	unsigned long rate_begin;
	u16 buckets[KD_HOTLOCK_BUCKETS], used;
	struct kd_hotlock_entry entries[KD_HOTLOCK_ENTRIES];
};

struct kd_hotlock_cpu {
	struct kd_hotlock_table table;
} ____cacheline_aligned;

static struct kd_hotlock_cpu __percpu *kd_hotlock_cpu;
DEFINE_PER_CPU(unsigned int, kd_hotlock_spin_gate);
EXPORT_PER_CPU_SYMBOL_GPL(kd_hotlock_spin_gate);
/*
 * Count physical attempts on their executor CPU, including nested acquisitions
 * and outer reacquires. Root fallbacks retain their first count.
 */
DEFINE_PER_CPU(unsigned long, kd_hotlock_spin_entries);
EXPORT_PER_CPU_SYMBOL_GPL(kd_hotlock_spin_entries);
DEFINE_PER_CPU(unsigned long, kd_hotlock_spin_mcs);
/*
 * Compare shifted entry count at the MCS boundary, then reset both counts.
 * Zero bypasses only the ratio; the compare adds no division or multiplication.
 */
static unsigned int spin_entry_ratio_limit = 2;
module_param(spin_entry_ratio_limit, uint, 0444);
MODULE_PARM_DESC(spin_entry_ratio_limit,
		 "Exclusive (spin entries >> 10) limit per 1024 MCS publications; 0 or a power of two >= 2");
static bool hotlock_stats;
module_param(hotlock_stats, bool, 0444);
MODULE_PARM_DESC(hotlock_stats,
		 "Print final CPU-local exact lock counters after provider drain");

/*
 * Callers are CPU-pinned and never sleep while busy. IRQs finish before the
 * interrupted caller resumes; barriers keep table work inside this guard.
 */
static __always_inline bool kd_hotlock_try_enter(struct kd_hotlock_table *t)
{
	if (READ_ONCE(t->busy))
		return false;
	WRITE_ONCE(t->busy, 1);
	barrier();
	return true;
}

static unsigned int kd_hotlock_bucket(unsigned long address)
{
	return hash_long(address, KD_HOTLOCK_HASH_BITS);
}

static struct kd_hotlock_entry *kd_hotlock_find(struct kd_hotlock_table *t,
                                                    unsigned long address)
{
	u16 link = t->buckets[kd_hotlock_bucket(address)];

	while (link) {
		struct kd_hotlock_entry *slot = &t->entries[link - 1];

		if (slot->address == address)
			return slot;
		link = slot->next;
	}
	return NULL;
}

static struct kd_hotlock_entry *kd_hotlock_insert(struct kd_hotlock_table *t,
                                                      unsigned long address)
{
	unsigned int bucket = kd_hotlock_bucket(address);
	struct kd_hotlock_entry *slot;

	/*
	 * Exact lookup precedes insertion. Never evict a recorded lock or borrow
	 * another address's count/heat on hash collision or capacity exhaustion.
	 */
	if (t->used == KD_HOTLOCK_ENTRIES)
		return NULL;
	slot = &t->entries[t->used++];
	slot->address = address;
	slot->begin = t->rate_begin;
	slot->count = 0;
	slot->hot = false;
	slot->next = t->buckets[bucket];
	t->buckets[bucket] = t->used;
	return slot;
}

/*
 * Spin compares its current entry count before reading the clock, once per
 * MCS batch. Reset the existing counters instead of retaining old snapshots.
 * This is approximate admission state, not ownership or lossless accounting.
 */
static bool kd_hotlock_clock(struct kd_hotlock_table *t, unsigned int *rate_hot,
                             unsigned long *sampled_now)
{
	unsigned long now;
	unsigned int i;
	bool was_hot, ratio_hot = true;

	ratio_hot =
		!spin_entry_ratio_limit ||
		(this_cpu_read(kd_hotlock_spin_entries) >> KD_HOTLOCK_SPIN_RATIO_SHIFT) <
                spin_entry_ratio_limit;
	this_cpu_write(kd_hotlock_spin_entries, 0);
	this_cpu_write(kd_hotlock_spin_mcs, 0);
	now = rdtsc_ordered();
	if (sampled_now)
		*sampled_now = now;
	was_hot = *rate_hot;
	*rate_hot = ratio_hot && now >= t->rate_begin &&
		    now - t->rate_begin < KD_HOTLOCK_CPU_WINDOW;
	t->rate_begin = now;
	t->rate_samples = 0;
	if (!was_hot || !*rate_hot) {
		for (i = 0; i < t->used; i++) {
			struct kd_hotlock_entry *slot = &t->entries[i];

			slot->begin = now;
			slot->count = 0;
			slot->hot = false;
		}
	}
	return *rate_hot;
}

/*
 * Specialize record/query and the caller's pin contract at fixed
 * call sites. Sampling and the structural table guard remain shared.
 */
static __always_inline bool kd_hotlock_access(unsigned long address,
                                             bool record, bool already_pinned)
{
	struct kd_hotlock_cpu *local;
	struct kd_hotlock_table *t;
	struct kd_hotlock_entry *slot;
	unsigned int *rate_hot;
	unsigned long now = 0;
	bool admitted = false;
	bool pin;

	/*
	 * Callers supply a valid lock identity between successful module init and
	 * final drain. Do not repeat address/table readiness tests per acquisition.
	 *
	 * Root spin admission already owns a pin.
	 * Generic callers retain their existing pin handling,
	 * which covers only this access, never the later sleep/ACK interval.
	 */
	pin = !already_pinned && !preempt_count();
	if (pin)
		preempt_disable();
	local = this_cpu_ptr(kd_hotlock_cpu);
	t = &local->table;
	rate_hot = raw_cpu_ptr(&kd_hotlock_spin_gate);
	if (!kd_hotlock_try_enter(t))
		goto unpin;
	/* CPU heat advances only at MCS publication. */
	if (!*rate_hot)
		goto out;
	slot = kd_hotlock_find(t, address);
	if (!slot && record)
		slot = kd_hotlock_insert(t, address);
	if (slot) {
		if (record) {
			if (++slot->count >= KD_HOTLOCK_SPIN_SAMPLE_TARGET) {
				const unsigned long window = KD_HOTLOCK_SPIN_INITIAL_WINDOW;

				now = rdtsc_ordered();
				slot->hot = now >= slot->begin &&
					    now - slot->begin < window;
				slot->begin = now;
				slot->count = 0;
			}
		}
		admitted = slot->hot;
	}
out:
	barrier();
	WRITE_ONCE(t->busy, 0);
unpin:
	if (pin)
		preempt_enable();
	return admitted;
}

bool kd_hotlock_record_spin(unsigned long address)
{
	return kd_hotlock_access(address, true, false);
}

bool kd_hotlock_record_spin_pinned(unsigned long address)
{
	return kd_hotlock_access(address, true, true);
}



bool kd_hotlock_query_spin(unsigned long address)
{
	return kd_hotlock_access(address, false, false);
}


/*
 * Compare cold native and delegated publications on the same CPU. The guard
 * protects table/heat resets, not profiling accuracy. A busy skip keeps both
 * counts; the next publication retries the batch threshold without a new flag.
 */
void kd_hotlock_sample_spin_mcs_pinned(void)
{
	struct kd_hotlock_table *t = &this_cpu_ptr(kd_hotlock_cpu)->table;

	if (!kd_hotlock_try_enter(t))
		return;
	kd_hotlock_clock(t, raw_cpu_ptr(&kd_hotlock_spin_gate), NULL);
	barrier();
	WRITE_ONCE(t->busy, 0);
}

#include "owned_mutex/admission.inc"

int kd_hotlock_init(void)
{
	int cpu, ret;
	unsigned long now;

	if (spin_entry_ratio_limit == 1 ||
	    (spin_entry_ratio_limit & (spin_entry_ratio_limit - 1)))
		return -EINVAL;
	kd_hotlock_cpu = alloc_percpu(struct kd_hotlock_cpu);
	if (!kd_hotlock_cpu)
		return -ENOMEM;
	ret = kd_owned_hotlock_init();
	if (ret) {
		free_percpu(kd_hotlock_cpu);
		kd_hotlock_cpu = NULL;
		return ret;
	}
	/*
	 * Establish the spin CPU clock before any caller can enter. The first
	 * batch includes startup/idle time, so it may conservatively remain cold.
	 */
	now = rdtsc_ordered();
	for_each_possible_cpu(cpu) {
		struct kd_hotlock_cpu *local = per_cpu_ptr(kd_hotlock_cpu, cpu);

		memset(local, 0, sizeof(*local));
		local->table.rate_begin = now;
		per_cpu(kd_hotlock_spin_gate, cpu) = 0;
		per_cpu(kd_hotlock_spin_entries, cpu) = 0;
		per_cpu(kd_hotlock_spin_mcs, cpu) = 0;
	}
	return 0;
}

void kd_hotlock_exit(void)
{
	int cpu;
	unsigned int i;

	/* Final snapshot only: no in-flight caller, table writer or request remains. */
	if (hotlock_stats && kd_hotlock_cpu)
		for_each_possible_cpu(cpu) {
			struct kd_hotlock_cpu *local = per_cpu_ptr(kd_hotlock_cpu, cpu);
			struct kd_hotlock_table *t = &local->table;
			unsigned int rate_hot = per_cpu(kd_hotlock_spin_gate, cpu);

			if (per_cpu(kd_hotlock_spin_entries, cpu)) {
				/* Residuals of the unfinished batch. */
				pr_info("kd_hotlock ratio: cpu=%d entries=%lu mcs=%lu cpu_hot=%u entry_ratio_limit=%u window=%u scope=unfinished_batch role=DONE\n",
					cpu, per_cpu(kd_hotlock_spin_entries, cpu),
					per_cpu(kd_hotlock_spin_mcs, cpu), rate_hot,
					spin_entry_ratio_limit,
					KD_HOTLOCK_SPIN_MCS_INTERVAL);
			}
			for (i = 0; i < t->used; i++) {
				struct kd_hotlock_entry *s = &t->entries[i];

				pr_info("kd_hotlock final: cpu=%d type=%s address=%lx count=%u cpu_hot=%u lock_hot=%u role=DONE\n",
					cpu, "spin", s->address, s->count,
					rate_hot, s->hot);
			}
		}
	kd_owned_hotlock_exit();
	free_percpu(kd_hotlock_cpu);
	kd_hotlock_cpu = NULL;
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/hotlock/lifetime_selftest.c"
#endif
