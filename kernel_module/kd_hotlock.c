/* SPDX-License-Identifier: GPL-2.0 */
/* CPU-local exact-key lock counters. Statistics grant admission only; stable
 * tickets and frames own requests independently of heat and migration. */
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

/* Fixed storage is reserved at init, never allocated while acquiring a lock.
 * Entries are exact identities, not ranked candidates: no score, replacement
 * or inherited counts. A full table declines unknown identities. */
struct kd_hotlock_entry
{
  unsigned long address, begin;
  u16 count, next;
  u8 hot;
};
struct kd_hotlock_table
{
  unsigned int busy, rate_samples;
  unsigned long rate_begin;
  u16 buckets[KD_HOTLOCK_BUCKETS], used;
  struct kd_hotlock_entry entries[KD_HOTLOCK_ENTRIES];
};
struct kd_hotlock_cpu
{
  struct kd_hotlock_table tables[2];
  /* Spin heat lives in its directly addressed static per-CPU gate. Keep
   * only mutex heat here; neither table holds a second copy of either gate. */
  unsigned int mutex_rate_hot;
} ____cacheline_aligned;
static struct kd_hotlock_cpu __percpu *kd_hotlock_cpu;
DEFINE_PER_CPU(unsigned int, kd_hotlock_spin_gate);
EXPORT_PER_CPU_SYMBOL_GPL(kd_hotlock_spin_gate);
/* Count physical attempts on their executor CPU, including nested acquisitions
 * and outer reacquires. Root fallbacks retain their first count. */
DEFINE_PER_CPU(unsigned long, kd_hotlock_spin_entries);
EXPORT_PER_CPU_SYMBOL_GPL(kd_hotlock_spin_entries);
DEFINE_PER_CPU(unsigned long, kd_hotlock_spin_mcs);
DEFINE_PER_CPU(unsigned long, kd_hotlock_mutex_entries);
DEFINE_PER_CPU(unsigned long, kd_hotlock_mutex_contentions);
static DEFINE_PER_CPU(unsigned long, kd_hotlock_mutex_last_entries);
static DEFINE_PER_CPU(unsigned long, kd_hotlock_mutex_checks);
/* Compare shifted entry count at the MCS boundary, then reset both counts.
 * Zero bypasses only the ratio; the compare adds no division or multiplication. */
static unsigned int spin_entry_ratio_limit = 2;
module_param(spin_entry_ratio_limit, uint, 0444);
MODULE_PARM_DESC(spin_entry_ratio_limit, "Exclusive (spin entries >> 10) limit per 1024 MCS publications; 0 or a power of two >= 2");
static bool hotlock_stats;
module_param(hotlock_stats, bool, 0444);
MODULE_PARM_DESC(hotlock_stats, "Print final CPU-local exact lock counters after provider drain");

/* Callers are CPU-pinned and never sleep while busy. IRQs finish before the
 * interrupted caller resumes; barriers keep table work inside this guard. */
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
  while (link)
  {
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
  /* Exact lookup precedes insertion. Never evict a recorded lock or borrow
   * another address's count/heat on hash collision or capacity exhaustion. */
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
/* Spin compares its current entry count before reading the clock, once per
 * MCS batch. Reset the existing counters instead of retaining old snapshots.
 * This is approximate admission state, not ownership or lossless accounting. */
static bool kd_hotlock_clock(struct kd_hotlock_table *t, unsigned int *rate_hot,
                             unsigned long *sampled_now,
                             unsigned int interval, bool spin)
{
  unsigned long now;
  unsigned int i;
  bool was_hot, ratio_hot = true;

  if (!spin)
  {
    t->rate_samples = this_cpu_read(kd_hotlock_mutex_contentions);
    if (t->rate_samples < interval)
      return *rate_hot;
    this_cpu_write(kd_hotlock_mutex_last_entries,
                   this_cpu_read(kd_hotlock_mutex_entries));
    this_cpu_inc(kd_hotlock_mutex_checks);
    ratio_hot = (this_cpu_read(kd_hotlock_mutex_entries) >> 10) <
                KD_HOTLOCK_MUTEX_RATIO_LIMIT;
    this_cpu_write(kd_hotlock_mutex_entries, 0);
    this_cpu_write(kd_hotlock_mutex_contentions, 0);
  }
  if (spin)
  {
    ratio_hot = !spin_entry_ratio_limit ||
                (this_cpu_read(kd_hotlock_spin_entries) >> KD_HOTLOCK_SPIN_RATIO_SHIFT) <
                spin_entry_ratio_limit;
    this_cpu_write(kd_hotlock_spin_entries, 0);
    this_cpu_write(kd_hotlock_spin_mcs, 0);
  }
  now = rdtsc_ordered();
  if (sampled_now)
    *sampled_now = now;
  was_hot = *rate_hot;
  *rate_hot = ratio_hot && now >= t->rate_begin &&
              now - t->rate_begin < KD_HOTLOCK_CPU_WINDOW;
  t->rate_begin = now;
  t->rate_samples = 0;
  if (!was_hot || !*rate_hot)
  {
    for (i = 0; i < t->used; i++)
    {
      struct kd_hotlock_entry *slot = &t->entries[i];

      slot->begin = now;
      slot->count = 0;
      slot->hot = false;
    }
  }
  return *rate_hot;
}
/* Specialize record/query, lock kind and the caller's pin contract at fixed
 * call sites. Sampling and the structural table guard remain shared. */
static __always_inline bool kd_hotlock_access(unsigned long address, unsigned int kind,
                                             bool record, bool already_pinned)
{
  struct kd_hotlock_cpu *local;
  struct kd_hotlock_table *t;
  struct kd_hotlock_entry *slot;
  unsigned int *rate_hot;
  unsigned long now = 0;
  bool admitted = false;
  bool pin;
  /* Callers supply a valid lock identity between successful module init and
   * final drain. Do not repeat address/table readiness tests per acquisition. */
  /* Root spin admission already owns a pin and needs no runtime pin check.
   * Generic spin and mutex callers retain their existing pin handling,
   * which covers only this access, never the later sleep/ACK interval. */
  pin = !already_pinned && !preempt_count();
  if (pin)
    preempt_disable();
  local = this_cpu_ptr(kd_hotlock_cpu);
  t = &local->tables[kind];
  rate_hot = kind ? &local->mutex_rate_hot : raw_cpu_ptr(&kd_hotlock_spin_gate);
  /* Count even a guarded skip; a later contention retries the boundary. */
  if (record && kind == 1)
    this_cpu_inc(kd_hotlock_mutex_contentions);
  if (!kd_hotlock_try_enter(t))
    goto unpin;
  /* Spin CPU heat advances only at MCS publication. Entry records retain the
   * cached CPU gate and original per-lock sampling; mutex keeps both clocks. */
  if (record && kind == 1 &&
      !kd_hotlock_clock(t, rate_hot, &now, KD_HOTLOCK_CHECK_INTERVAL, false))
    goto out;
  if (!*rate_hot)
    goto out;
  slot = kd_hotlock_find(t, address);
  if (!slot && record)
    slot = kd_hotlock_insert(t, address);
  if (slot)
  {
    if (record)
    {
      /* Spin checks at the shared 512-entry interval; mutex keeps 1025. */
      const unsigned int target = kind ? KD_HOTLOCK_SAMPLE_TARGET + 1U :
                                        KD_HOTLOCK_SPIN_SAMPLE_TARGET;
      if (++slot->count >= target)
      {
        /* Halve the spin batch's time bound as well as its sample target to
         * shorten warmup while preserving approximately the same frequency. */
        const unsigned long window = kind ? KD_HOTLOCK_INITIAL_WINDOW :
                                            KD_HOTLOCK_SPIN_INITIAL_WINDOW;
        /* Only a mutex entry can share its CPU timestamp with this lock.
         * Spin MCS sampled on a separate call, even when rate_samples is zero. */
        if (kind == 0 || t->rate_samples)
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
bool kd_hotlock_record_spin(unsigned long address) { return kd_hotlock_access(address, 0, true, false); }
bool kd_hotlock_record_spin_pinned(unsigned long address) { return kd_hotlock_access(address, 0, true, true); }
bool kd_hotlock_record_mutex(unsigned long address) { return kd_hotlock_access(address, 1, true, false); }
bool kd_hotlock_query_spin(unsigned long address) { return kd_hotlock_access(address, 0, false, false); }
bool kd_hotlock_query_mutex(unsigned long address) { return kd_hotlock_access(address, 1, false, false); }

/* Compare cold native and delegated publications on the same CPU. The guard
 * protects table/heat resets, not profiling accuracy. A busy skip keeps both
 * counts; the next publication retries the batch threshold without a new flag. */
void kd_hotlock_sample_spin_mcs_pinned(void)
{
  struct kd_hotlock_table *t = &this_cpu_ptr(kd_hotlock_cpu)->tables[0];

  if (!kd_hotlock_try_enter(t))
    return;
  /* Mutex can reuse its timestamp for a coincident lock check; spin cannot. */
  kd_hotlock_clock(t, raw_cpu_ptr(&kd_hotlock_spin_gate), NULL,
                   KD_HOTLOCK_SPIN_MCS_INTERVAL, true);
  barrier();
  WRITE_ONCE(t->busy, 0);
}

int kd_hotlock_init(void)
{
  int cpu;
  unsigned long now;
  if (spin_entry_ratio_limit == 1 ||
      (spin_entry_ratio_limit & (spin_entry_ratio_limit - 1)))
    return -EINVAL;
  kd_hotlock_cpu = alloc_percpu(struct kd_hotlock_cpu);
  if (!kd_hotlock_cpu)
    return -ENOMEM;
  /* Establish both typed CPU clocks before any caller can enter. The first
   * batch includes startup/idle time, so it may conservatively remain cold. */
  now = rdtsc_ordered();
  for_each_possible_cpu(cpu)
  {
    struct kd_hotlock_cpu *local = per_cpu_ptr(kd_hotlock_cpu, cpu);
    memset(local, 0, sizeof(*local));
    local->tables[0].rate_begin = local->tables[1].rate_begin = now;
    per_cpu(kd_hotlock_spin_gate, cpu) = 0;
    per_cpu(kd_hotlock_spin_entries, cpu) = 0;
    per_cpu(kd_hotlock_spin_mcs, cpu) = 0;
    per_cpu(kd_hotlock_mutex_entries, cpu) = 0;
    per_cpu(kd_hotlock_mutex_contentions, cpu) = 0;
    per_cpu(kd_hotlock_mutex_last_entries, cpu) = 0;
    per_cpu(kd_hotlock_mutex_checks, cpu) = 0;
  }
  return 0;
}
void kd_hotlock_exit(void)
{
  int cpu;
  unsigned int kind, i;
  /* Final snapshot only: no in-flight caller, table writer or request remains. */
  if (hotlock_stats && kd_hotlock_cpu)
    for_each_possible_cpu(cpu) for (kind = 0; kind < 2; kind++)
    {
      struct kd_hotlock_cpu *local = per_cpu_ptr(kd_hotlock_cpu, cpu);
      struct kd_hotlock_table *t = &local->tables[kind];
      unsigned int rate_hot = kind ? local->mutex_rate_hot :
                                    per_cpu(kd_hotlock_spin_gate, cpu);
      if (kind && per_cpu(kd_hotlock_mutex_entries, cpu))
        pr_info("kd_hotlock mutex ratio: cpu=%d entries=%lu contentions=%lu last_entries=%lu checks=%lu cpu_hot=%u window=%u scope=unfinished_batch role=DONE\n",
                cpu, per_cpu(kd_hotlock_mutex_entries, cpu),
                per_cpu(kd_hotlock_mutex_contentions, cpu),
                per_cpu(kd_hotlock_mutex_last_entries, cpu),
                per_cpu(kd_hotlock_mutex_checks, cpu), rate_hot,
                KD_HOTLOCK_CHECK_INTERVAL);
      if (!kind && per_cpu(kd_hotlock_spin_entries, cpu))
      {
        /* These are the unfinished batch's residuals, not lifetime totals. */
        pr_info("kd_hotlock ratio: cpu=%d entries=%lu mcs=%lu cpu_hot=%u entry_ratio_limit=%u window=%u scope=unfinished_batch role=DONE\n",
                cpu, per_cpu(kd_hotlock_spin_entries, cpu),
                per_cpu(kd_hotlock_spin_mcs, cpu), rate_hot, spin_entry_ratio_limit,
                KD_HOTLOCK_SPIN_MCS_INTERVAL);
      }
      for (i = 0; i < t->used; i++)
      {
        struct kd_hotlock_entry *s = &t->entries[i];
        pr_info("kd_hotlock final: cpu=%d type=%s address=%lx count=%u cpu_hot=%u lock_hot=%u role=DONE\n",
                cpu, kind ? "mutex" : "spin", s->address, s->count,
                rate_hot, s->hot);
      }
    }
  free_percpu(kd_hotlock_cpu);
  kd_hotlock_cpu = NULL;
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/hotlock/lifetime_selftest.c"
#endif
