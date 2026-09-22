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
#define KD_HOTLOCK_SPIN_MCS_INTERVAL 4U
#define KD_HOTLOCK_CPU_WINDOW 4000000000UL
#define KD_HOTLOCK_INITIAL_WINDOW 2500000000UL
#define KD_HOTLOCK_SAMPLE_TARGET 32U
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
  unsigned int rate_samples, rate_hot;
  unsigned long rate_begin;
  u16 buckets[KD_HOTLOCK_BUCKETS], used;
  struct kd_hotlock_entry entries[KD_HOTLOCK_ENTRIES];
};
struct kd_hotlock_cpu
{
  struct kd_hotlock_table tables[2];
} ____cacheline_aligned;
static struct kd_hotlock_cpu __percpu *kd_hotlock_cpu;
DEFINE_PER_CPU(unsigned int *, kd_hotlock_spin_gate);
EXPORT_PER_CPU_SYMBOL_GPL(kd_hotlock_spin_gate);
/* Immutable after load: observe fixes admission even for dropped samples. */
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
/* Initialization supplies the first time origin. Ordinary records only count;
 * one TSC per CPU batch measures the whole batch since the previous check
 * (four spin MCS publications or 1024 mutex entries). A continuously hot CPU must
 * not restart the independent lock batches. Cooling/reheating resets them,
 * retaining bucket membership and leaving ownership storage untouched. */
static bool kd_hotlock_clock(struct kd_hotlock_table *t, unsigned long *sampled_now,
                             unsigned int interval)
{
  unsigned long now;
  unsigned int i;
  bool continuous;
  if (++t->rate_samples < interval)
    return t->rate_hot;
  now = rdtsc_ordered();
  *sampled_now = now;
  continuous = t->rate_hot;
  t->rate_hot = now >= t->rate_begin && now - t->rate_begin < KD_HOTLOCK_CPU_WINDOW;
  continuous &= t->rate_hot;
  t->rate_begin = now;
  t->rate_samples = 0;
  if (!continuous)
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
/* Specialize record/query and spin/mutex at the fixed call sites; keep
 * the best-effort sampling and pin semantics shared below. */
static __always_inline bool kd_hotlock_access(unsigned long address, unsigned int kind,
                                             bool record, bool pinned)
{
  struct kd_hotlock_table *t;
  struct kd_hotlock_entry *slot;
  unsigned long now = 0;
  bool admitted = record && kd_hotlock_observe;
  bool pin;
  /* Callers supply a valid lock identity between successful module init and
   * final drain. Do not repeat address/table readiness tests per acquisition. */
  /* Drop non-task samples: counters may be approximate, but an interrupt
   * must not reenter hash-chain insertion. Pinned task callers need neither
   * a busy RMW nor a barrier to serialize access to this CPU's table. */
  if (!in_task())
    return admitted;
  /* Spin admission already owns its acquisition pin. Standalone observers
   * and sleepable mutex callers pin only this statistics access, never the
   * later sleep/ACK interval. */
  pin = !pinned && !preempt_count();
  if (pin)
    preempt_disable();
  t = &this_cpu_ptr(kd_hotlock_cpu)->tables[kind];
  /* Spin CPU heat advances only at MCS publication. Entry records retain the
   * cached CPU gate and original per-lock sampling; mutex keeps both clocks. */
  if (record && kind == 1 &&
      !kd_hotlock_clock(t, &now, KD_HOTLOCK_CHECK_INTERVAL))
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
      /* Strictly greater than 32: the 33rd hit closes this batch. */
      if (++slot->count > KD_HOTLOCK_SAMPLE_TARGET)
      {
        /* Only a mutex entry can share its CPU timestamp with this lock.
         * Spin MCS sampled on a separate call, even when rate_samples is zero. */
        if (kind == 0 || t->rate_samples)
          now = rdtsc_ordered();
        slot->hot = now >= slot->begin &&
                    now - slot->begin < KD_HOTLOCK_INITIAL_WINDOW;
        slot->begin = now;
        slot->count = 0;
      }
    }
    admitted |= slot->hot;
  }
out:
  if (pin)
    preempt_enable();
  return admitted;
}
bool kd_hotlock_record_spin(unsigned long address) { return kd_hotlock_access(address, 0, true, false); }
bool kd_hotlock_record_mutex(unsigned long address) { return kd_hotlock_access(address, 1, true, false); }
bool kd_hotlock_query_spin(unsigned long address) { return kd_hotlock_access(address, 0, false, false); }
bool kd_hotlock_query_mutex(unsigned long address) { return kd_hotlock_access(address, 1, false, false); }

/* All spin producers reach this only when publishing an MCS tail. Native cold
 * acquisitions also count, so adaptive admission can warm without delegation.
 * Reuse the pin and drop non-task samples, just like entry statistics. */
void kd_hotlock_record_spin_mcs_pinned(void)
{
  struct kd_hotlock_table *t;
  unsigned long now;

  if (!in_task())
    return;
  t = &this_cpu_ptr(kd_hotlock_cpu)->tables[0];
  kd_hotlock_clock(t, &now, KD_HOTLOCK_SPIN_MCS_INTERVAL);
}

/* Specialize the shared sampler for the acquisition pin. No extra public
 * wrapper CALL or preempt_count query is needed; non-task filtering remains. */
bool kd_hotlock_record_spin_pinned(unsigned long address)
{
  return kd_hotlock_access(address, 0, true, true);
}

int kd_hotlock_init(void)
{
  int cpu;
  unsigned long now;
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
    memset(local, 0, sizeof(*local));
    local->tables[0].rate_begin = local->tables[1].rate_begin = now;
    per_cpu(kd_hotlock_spin_gate, cpu) = &local->tables[0].rate_hot;
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
