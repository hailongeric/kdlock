/* SPDX-License-Identifier: GPL-2.0 */
/* CPU-local exact-key lock counters. Statistics grant admission only; stable
 * tickets and frames own requests independently of heat and migration. */
#include <asm/tsc.h>
#include <linux/errno.h>
#include <linux/hash.h>
#include <linux/moduleparam.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include "kd_hotlock.h"

#define KD_HOTLOCK_CHECK_INTERVAL 1024U
#define KD_HOTLOCK_CPU_WINDOW 40000000000UL
#define KD_HOTLOCK_INITIAL_WINDOW 2500000000UL
#define KD_HOTLOCK_SAMPLE_TARGET 1024U
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
struct kd_hotlock_cpu
{
  struct kd_hotlock_table tables[2];
} ____cacheline_aligned;
static struct kd_hotlock_cpu __percpu *kd_hotlock_cpu;
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
/* Initialization supplies the first time origin. Ordinary records only count;
 * one TSC per CPU batch updates its cached rate. A continuously hot CPU must
 * not restart the independent lock batches. Cooling/reheating resets them,
 * retaining bucket membership and leaving ownership storage untouched. */
static bool kd_hotlock_clock(struct kd_hotlock_table *t, unsigned long *sampled_now)
{
  unsigned long now;
  unsigned int i;
  bool continuous;
  if (++t->rate_samples < KD_HOTLOCK_CHECK_INTERVAL)
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
  if (record && !kd_hotlock_clock(t, &now))
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
      /* Strictly greater than 1024: the 1025th hit closes this batch. */
      if (++slot->count > KD_HOTLOCK_SAMPLE_TARGET)
      {
        /* A zero CPU batch count means this call already sampled TSC. This
         * also handles a genuine zero timestamp without a sentinel reread. */
        if (t->rate_samples)
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

/* Acquisition-pinned callers reuse the verified sampler. Its preempt_count
 * check does not add another pin; keep this API stable across the rollback. */
bool kd_hotlock_record_spin_pinned(unsigned long address)
{
  return kd_hotlock_record_spin(address);
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
