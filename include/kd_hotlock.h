/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_HOTLOCK_H
#define KD_HOTLOCK_H
#include <linux/types.h>
#include <linux/percpu.h>
/* A view of the existing CPU gate, not a second heat flag. Initialized before
 * callers enter and valid until their final drain. The reader owns a CPU pin. */
DECLARE_PER_CPU(unsigned int *, kd_hotlock_spin_gate);
DECLARE_PER_CPU(unsigned long, kd_hotlock_spin_entries);
DECLARE_PER_CPU(unsigned long, kd_hotlock_spin_mcs);
/* A power-of-two batch keeps the publication boundary check division-free. */
#define KD_HOTLOCK_SPIN_MCS_INTERVAL 512U
/* Count once per physical acquisition, including the cold native route.
 * The direct native route counts after its first CAS, before contended work.
 * The acquisition pin keeps these approximate counts CPU-local. */
static __always_inline void kd_hotlock_spin_entry_pinned(void)
{
  this_cpu_inc(kd_hotlock_spin_entries);
}
static __always_inline bool kd_hotlock_spin_cpu_hot_pinned(void)
{
  return READ_ONCE(*this_cpu_read(kd_hotlock_spin_gate)) != 0;
}
int kd_hotlock_init(void);
void kd_hotlock_exit(void);
/* A valid identity and initialized provider are caller preconditions. Spin
 * compares CPU-local MCS/entry deltas every 512 publications, then reads one
 * timestamp for CPU frequency. The first interval primes the ratio snapshots.
 * Adaptive requires the configured percentage and a strict 40000000000-tick
 * CPU window; observe and percentage zero bypass the ratio. Observe record
 * returns true, while paired direct entries still follow the frequency gate.
 * Spin lock heat checks every 512 records against 1250000000 ticks. Mutex keeps
 * 1025 records and 2500000000 ticks. Combined CPU cooling/reheating resets lock
 * heat. Exact tables hold 256 identities per CPU/type without eviction.
 * Counters and IRQ sampling are approximate; delayed comparisons use raw
 * counter deltas. The table guard protects insertion and heat resets. Queries
 * neither count nor tick, and no admission result conveys lock ownership. */
bool kd_hotlock_record_spin(unsigned long address);
/* The caller must own an acquisition pin. This specialized entry omits the
 * generic preemption check while sharing all table and admission behavior. */
bool kd_hotlock_record_spin_pinned(unsigned long address);
/* One MCS publication on its physical CPU with preemption pinned. Queue-head
 * acquisition never samples again. No lock sample: new CPU heat applies only
 * to later entries, including when this acquisition finishes natively. */
void kd_hotlock_sample_spin_mcs_pinned(void);
static __always_inline void kd_hotlock_record_spin_mcs_pinned(void)
{
  /* Approximate cadence is sufficient for admission; IRQs may shift a check. */
  this_cpu_inc(kd_hotlock_spin_mcs);
  if (!(this_cpu_read(kd_hotlock_spin_mcs) &
        (KD_HOTLOCK_SPIN_MCS_INTERVAL - 1U)))
    kd_hotlock_sample_spin_mcs_pinned();
}
bool kd_hotlock_record_mutex(unsigned long address);
bool kd_hotlock_query_spin(unsigned long address);
bool kd_hotlock_query_mutex(unsigned long address);

#ifdef KDLOCK_SELFTEST
int kd_hotlock_lifetime_check(void);
#endif
#endif
