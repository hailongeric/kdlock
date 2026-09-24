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
#define KD_HOTLOCK_SPIN_SAMPLE_TARGET KD_HOTLOCK_SPIN_MCS_INTERVAL
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
  unsigned int busy, rate_samples, rate_hot;
  unsigned long rate_begin;
  u16 buckets[KD_HOTLOCK_BUCKETS], used;
  struct kd_hotlock_entry entries[KD_HOTLOCK_ENTRIES];
};
/* Previous CPU-local totals for the shared spin sampling interval. */
struct kd_hotlock_spin_ratio
{
  unsigned long entry_begin, mcs_begin;
};
struct kd_hotlock_cpu
{
  struct kd_hotlock_table tables[2];
} ____cacheline_aligned;
static struct kd_hotlock_cpu __percpu *kd_hotlock_cpu;
static DEFINE_PER_CPU(struct kd_hotlock_spin_ratio, kd_hotlock_spin_ratio);
DEFINE_PER_CPU(unsigned int *, kd_hotlock_spin_gate);
EXPORT_PER_CPU_SYMBOL_GPL(kd_hotlock_spin_gate);
DEFINE_PER_CPU(unsigned long, kd_hotlock_spin_entries);
DEFINE_PER_CPU(unsigned long, kd_hotlock_spin_mcs);
/* Count physical acquisition attempts on their executor CPU, including nested
 * acquisitions and outer reacquires. Root fallbacks retain their first count. */
static unsigned int spin_contention_pct = 100;
module_param(spin_contention_pct, uint, 0444);
MODULE_PARM_DESC(spin_contention_pct, "Minimum MCS publications per 100 spin entries; 0 disables ratio admission");
/* Immutable after load: observe records the same samples but fixes admission.
 * Reentry still drops only the sample; it must not change fixed admission. */
static char *hotlock_mode = "adaptive";
module_param(hotlock_mode, charp, 0444);
MODULE_PARM_DESC(hotlock_mode, "adaptive: local frequency admission; observe: fixed admission with statistics");
static bool kd_hotlock_observe;
static bool hotlock_stats;
module_param(hotlock_stats, bool, 0444);
MODULE_PARM_DESC(hotlock_stats, "Print final CPU-local exact lock counters after provider drain");

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
/* Spin compares its entry/publication deltas before reading the clock, once
 * per shared interval. Heat is advisory; missed/repeated IRQ boundaries need
 * no exact ownership accounting. A later comparison includes skipped events. */
static bool kd_hotlock_clock(struct kd_hotlock_table *t, unsigned long *sampled_now,
                             unsigned int interval, bool spin)
{
  struct kd_hotlock_spin_ratio *r = NULL;
  unsigned long now, entries = 0, mcs = 0;
  unsigned int i;
  bool was_hot, ratio_hot = true;

  if (!spin && ++t->rate_samples < interval)
    return t->rate_hot;
  if (spin)
  {
    unsigned long mcs_delta, entry_delta;

    r = raw_cpu_ptr(&kd_hotlock_spin_ratio);
    entries = this_cpu_read(kd_hotlock_spin_entries);
    mcs = this_cpu_read(kd_hotlock_spin_mcs);
    mcs_delta = mcs - r->mcs_begin;
    if (!mcs_delta)
      return t->rate_hot;
    entry_delta = entries - r->entry_begin;
    /* Prime the first snapshots without charging pre-contention warmup.
     * Unsigned subtraction tolerates wrap; a zero snapshot may re-prime. */
    if (r->mcs_begin && !kd_hotlock_observe && spin_contention_pct)
      ratio_hot = mcs_delta * 100UL >= entry_delta * spin_contention_pct;
  }
  now = rdtsc_ordered();
  if (sampled_now)
    *sampled_now = now;
  was_hot = t->rate_hot;
  t->rate_hot = ratio_hot && now >= t->rate_begin &&
                now - t->rate_begin < KD_HOTLOCK_CPU_WINDOW;
  if (spin)
  {
    r->entry_begin = entries;
    r->mcs_begin = mcs;
  }
  t->rate_begin = now;
  t->rate_samples = 0;
  if (!was_hot || !t->rate_hot)
  {
    for (i = 0; i < t->used; i++)
    {
      struct kd_hotlock_entry *slot = &t->entries[i];

      slot->begin = now;
      slot->count = 0;
      slot->hot = false;
    }
  }
  return t->rate_hot;
}
/* Specialize record/query and spin/mutex at the four fixed call sites; keep
 * the sampling, local reentry guard and pin semantics shared below. */
static __always_inline bool kd_hotlock_access(unsigned long address, unsigned int kind, bool record)
{
  struct kd_hotlock_table *t;
  struct kd_hotlock_entry *slot;
  unsigned long now = 0;
  bool admitted = record && kd_hotlock_observe;
  bool pin;
  /* Callers supply a valid lock identity between successful module init and
   * final drain. Do not repeat address/table readiness tests per acquisition. */
  /* Spin admission already owns its acquisition pin. Reuse it, including
   * on IRQ reentry; standalone observers and sleepable mutex callers pin
   * only this statistics access, never the later sleep/ACK interval. */
  pin = !preempt_count();
  if (pin)
    preempt_disable();
  t = &this_cpu_ptr(kd_hotlock_cpu)->tables[kind];
  if (this_cpu_cmpxchg(kd_hotlock_cpu->tables[kind].busy, 0, 1))
    goto unpin;
  /* Spin CPU heat advances only at MCS publication. Entry records retain the
   * cached CPU gate and original per-lock sampling; mutex keeps both clocks. */
  if (record && kind == 1 &&
      !kd_hotlock_clock(t, &now, KD_HOTLOCK_CHECK_INTERVAL, false))
    goto out;
  if (!t->rate_hot)
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
    admitted |= slot->hot;
  }
out:
  barrier();
  WRITE_ONCE(t->busy, 0);
unpin:
  if (pin)
    preempt_enable();
  return admitted;
}
bool kd_hotlock_record_spin(unsigned long address) { return kd_hotlock_access(address, 0, true); }
bool kd_hotlock_record_mutex(unsigned long address) { return kd_hotlock_access(address, 1, true); }
bool kd_hotlock_query_spin(unsigned long address) { return kd_hotlock_access(address, 0, false); }
bool kd_hotlock_query_mutex(unsigned long address) { return kd_hotlock_access(address, 1, false); }

/* Compare cold native and delegated publications on the same CPU. The table
 * guard protects lock-counter resets; a skipped comparison leaves both raw
 * snapshots for the next interval. No separate accepted-sample count is needed. */
void kd_hotlock_sample_spin_mcs_pinned(void)
{
  struct kd_hotlock_table *t = &this_cpu_ptr(kd_hotlock_cpu)->tables[0];

  if (this_cpu_cmpxchg(kd_hotlock_cpu->tables[0].busy, 0, 1))
    return;
  /* Mutex can reuse its timestamp for a coincident lock check; spin cannot. */
  kd_hotlock_clock(t, NULL, KD_HOTLOCK_SPIN_MCS_INTERVAL, true);
  barrier();
  WRITE_ONCE(t->busy, 0);
}

int kd_hotlock_init(void)
{
  int cpu;
  unsigned long now;
  if (spin_contention_pct > 100)
    return -EINVAL;
  if (!strcmp(hotlock_mode, "observe"))
    kd_hotlock_observe = true;
  else if (!strcmp(hotlock_mode, "adaptive"))
    kd_hotlock_observe = false;
  else
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
    struct kd_hotlock_spin_ratio *r = &per_cpu(kd_hotlock_spin_ratio, cpu);
    memset(local, 0, sizeof(*local));
    memset(r, 0, sizeof(*r));
    local->tables[0].rate_begin = local->tables[1].rate_begin = now;
    per_cpu(kd_hotlock_spin_gate, cpu) = &local->tables[0].rate_hot;
    per_cpu(kd_hotlock_spin_entries, cpu) = 0;
    per_cpu(kd_hotlock_spin_mcs, cpu) = 0;
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
      struct kd_hotlock_table *t = &per_cpu_ptr(kd_hotlock_cpu, cpu)->tables[kind];
      if (!kind && per_cpu(kd_hotlock_spin_entries, cpu))
      {
        pr_info("kd_hotlock ratio: cpu=%d entries=%lu mcs=%lu cpu_hot=%u threshold=%u window=%u role=DONE\n",
                cpu, per_cpu(kd_hotlock_spin_entries, cpu),
                per_cpu(kd_hotlock_spin_mcs, cpu), t->rate_hot, spin_contention_pct,
                KD_HOTLOCK_SPIN_MCS_INTERVAL);
      }
      for (i = 0; i < t->used; i++)
      {
        struct kd_hotlock_entry *s = &t->entries[i];
        pr_info("kd_hotlock final: cpu=%d type=%s address=%lx count=%u cpu_hot=%u lock_hot=%u role=DONE\n",
                cpu, kind ? "mutex" : "spin", s->address, s->count,
                t->rate_hot, s->hot);
      }
    }
  free_percpu(kd_hotlock_cpu);
  kd_hotlock_cpu = NULL;
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/hotlock/lifetime_selftest.c"
#endif
