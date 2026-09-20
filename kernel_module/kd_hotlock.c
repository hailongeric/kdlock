/* SPDX-License-Identifier: GPL-2.0 */
/* CPU-local Space-Saving candidates. Statistics grant admission only; stable
 * tickets and frames own requests independently of eviction and migration. */
#include <asm/tsc.h>
#include <linux/errno.h>
#include <linux/hash.h>
#include <linux/moduleparam.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include "kd_hotlock.h"

#define KD_HOTLOCK_CHECK_INTERVAL 10240U
#define KD_HOTLOCK_CPU_WINDOW 40000000000UL
#define KD_HOTLOCK_INITIAL_WINDOW 2500000000UL
#define KD_HOTLOCK_SAMPLE_TARGET 10000U
#define KD_HOTLOCK_BUCKETS 16
#define KD_HOTLOCK_CANDIDATES 6

struct kd_hotlock_candidate
{
  unsigned long address, begin;
  u64 score, error;
  u8 next;
};
struct kd_hotlock_table
{
  unsigned int busy, rate_samples, rate_hot;
  unsigned long rate_begin;
  u8 buckets[KD_HOTLOCK_BUCKETS], used;
  struct kd_hotlock_candidate slots[KD_HOTLOCK_CANDIDATES];
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
MODULE_PARM_DESC(hotlock_stats, "Print final CPU-local candidate scores after provider drain");

static unsigned int kd_hotlock_bucket(unsigned long address)
{
  return hash_long(address, 4);
}
static struct kd_hotlock_candidate *kd_hotlock_find(struct kd_hotlock_table *t,
                                                    unsigned long address)
{
  u8 link = t->buckets[kd_hotlock_bucket(address)];
  while (link)
  {
    struct kd_hotlock_candidate *slot = &t->slots[link - 1];
    if (slot->address == address)
      return slot;
    link = slot->next;
  }
  return NULL;
}
static struct kd_hotlock_candidate *kd_hotlock_insert(struct kd_hotlock_table *t,
                                                      unsigned long address)
{
  unsigned int i, victim = 0, bucket = kd_hotlock_bucket(address);
  u64 error = 0;
  struct kd_hotlock_candidate *slot;
  if (t->used < KD_HOTLOCK_CANDIDATES)
  {
    victim = t->used++;
  }
  else
  {
    u8 *link;
    /* Only a full miss scans scores. Remove the old address before reusing its
     * slot, including when both keys hash to the same bucket. */
    for (i = 1; i < KD_HOTLOCK_CANDIDATES; i++)
      if (t->slots[i].score < t->slots[victim].score)
        victim = i;
    slot = &t->slots[victim];
    error = slot->score;
    link = &t->buckets[kd_hotlock_bucket(slot->address)];
    while (*link != victim + 1)
      link = &t->slots[*link - 1].next;
    *link = slot->next;
  }
  slot = &t->slots[victim];
  slot->address = address;
  slot->begin = t->rate_begin;
  slot->score = slot->error = error;
  slot->next = t->buckets[bucket];
  t->buckets[bucket] = victim + 1;
  return slot;
}
/* All candidates share the CPU's batched clock. Reset both score and error;
 * retain bucket membership and never touch request or ownership storage. */
static bool kd_hotlock_clock(struct kd_hotlock_table *t)
{
  unsigned long now;
  unsigned int i;
  bool continuous;
  if (!t->rate_begin)
  {
    t->rate_begin = rdtsc_ordered() ?: 1;
    t->rate_samples = 1;
    return false;
  }
  if (++t->rate_samples < KD_HOTLOCK_CHECK_INTERVAL)
    return t->rate_hot;
  now = rdtsc_ordered();
  continuous = t->rate_hot;
  t->rate_hot = now >= t->rate_begin && now - t->rate_begin < KD_HOTLOCK_CPU_WINDOW;
  continuous &= t->rate_hot;
  t->rate_begin = now ?: 1;
  t->rate_samples = 0;
  for (i = 0; i < t->used; i++)
  {
    struct kd_hotlock_candidate *slot = &t->slots[i];
    if (!continuous || now < slot->begin || now - slot->begin >= KD_HOTLOCK_INITIAL_WINDOW)
    {
      slot->begin = now ?: 1;
      slot->score = slot->error = 0;
    }
  }
  return t->rate_hot;
}
static bool kd_hotlock_access(unsigned long address, unsigned int kind, bool record)
{
  struct kd_hotlock_table *t;
  struct kd_hotlock_candidate *slot;
  bool admitted = record && kd_hotlock_observe;
  bool pin;
  if (!address || !READ_ONCE(kd_hotlock_cpu))
    return false;
  /* Spin admission already owns its acquisition pin. Reuse it, including
   * on IRQ reentry; standalone observers and sleepable mutex callers pin
   * only this statistics access, never the later sleep/ACK interval. */
  pin = !preempt_count();
  if (pin)
    preempt_disable();
  t = &this_cpu_ptr(kd_hotlock_cpu)->tables[kind];
  if (this_cpu_cmpxchg(kd_hotlock_cpu->tables[kind].busy, 0, 1))
    goto unpin;
  if (record && !kd_hotlock_clock(t))
    goto out;
  if (!t->rate_hot)
    goto out;
  slot = kd_hotlock_find(t, address);
  if (!slot && record)
    slot = kd_hotlock_insert(t, address);
  if (slot)
  {
    /* Saturation preserves a conservative lower bound without wrapping. */
    if (record && slot->score != U64_MAX)
      slot->score++;
    admitted |= slot->score - slot->error >= KD_HOTLOCK_SAMPLE_TARGET;
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

int kd_hotlock_init(void)
{
  int cpu;
  if (!strcmp(hotlock_mode, "observe"))
    kd_hotlock_observe = true;
  else if (!strcmp(hotlock_mode, "adaptive"))
    kd_hotlock_observe = false;
  else
    return -EINVAL;
  kd_hotlock_cpu = alloc_percpu(struct kd_hotlock_cpu);
  if (!kd_hotlock_cpu)
    return -ENOMEM;
  for_each_possible_cpu(cpu) memset(per_cpu_ptr(kd_hotlock_cpu, cpu), 0, sizeof(struct kd_hotlock_cpu));
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
        struct kd_hotlock_candidate *s = &t->slots[i];
        pr_info("kd_hotlock final: cpu=%d type=%s address=%lx score=%llu error=%llu lower=%llu hot=%u role=DONE\n",
                cpu, kind ? "mutex" : "spin", s->address, s->score, s->error,
                s->score - s->error, t->rate_hot);
      }
    }
  free_percpu(kd_hotlock_cpu);
  kd_hotlock_cpu = NULL;
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/hotlock/lifetime_selftest.c"
#endif
