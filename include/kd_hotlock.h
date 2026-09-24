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
#define KD_HOTLOCK_SPIN_MCS_INTERVAL 128U
/* Count once per physical acquisition, including the cold native route.
 * The direct native route counts after its first CAS, before contended work.
 * The acquisition pin stabilizes the CPU; a per-CPU instruction also avoids
 * losing an update if an interrupt enters another lock on this CPU. */
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
/* A valid lock identity and successful initialization are caller preconditions;
 * all callers must drain before exit. Reuse an existing CPU pin; otherwise pin
 * only this call (including sleepable mutex callers). Spin CPU rate counts
 * actual MCS publications, independent of CPU heat and queue depth, and checks
 * every 128 against a strict 40000000000 TSC tick window. Adaptive additionally
 * requires the configured MCS/entry percentage over an independent 512-MCS
 * window. Initial optimism allows lock warmup after a successful frequency check.
 * Two consecutive low windows withdraw admission, including during startup;
 * a high window resets that streak. Rejection then suppresses admission for
 * eight further ratio windows before retry. Observe bypasses ratio/cooldown
 * filtering and record returns true; paired direct entries still follow the
 * CPU-frequency gate.
 * Ratio-only suppression pauses lock count/heat/time while admission is closed;
 * reopening retains only epochs younger than the strict per-lock time window.
 * Frequency cooling/reheating still resets every lock epoch. Reopening uses
 * the already sampled CPU time, with no additional clock on ordinary entries.
 * Fast/pending acquisitions contribute entries but no MCS publication.
 * Mutex uses 1024 entry records and the same time window, without the ratio.
 * Exact spin lock counters check on the 513th entry against a strict 1250000000
 * TSC tick window; mutex retains 1025 entries and a strict 2500000000-tick window.
 * Tables are preallocated (256 entries per CPU/type), with no ranked eviction.
 * Unknown locks at capacity remain cold; queries neither count nor tick.
 * Statistics are best-effort: a CPU-local busy guard drops reentrant table
 * batches; raw acquisition/publication counters use per-CPU instructions.
 * Rejected MCS batches remain in the denominator, conservatively lowering
 * the sampled ratio, while final raw publication statistics retain them.
 * record returns policy admission (fixed true in observe); query reports only
 * cached local CPU/lock heat. No returned value conveys ownership. */
/* Caller already owns the acquisition pin; shared sampler reuses it. */
bool kd_hotlock_record_spin_pinned(unsigned long address);
/* One MCS publication on its physical CPU with preemption pinned. Queue-head
 * acquisition never samples again. No lock sample: new CPU heat applies only
 * to later entries, including when this acquisition finishes natively. */
void kd_hotlock_sample_spin_mcs_pinned(void);
static __always_inline void kd_hotlock_record_spin_mcs_pinned(void)
{
  /* The returned CPU-local count owns this boundary even if an IRQ publishes
   * between increment and test. Only complete batches touch guarded tables. */
  unsigned long count = this_cpu_inc_return(kd_hotlock_spin_mcs);

  if (!(count & (KD_HOTLOCK_SPIN_MCS_INTERVAL - 1U)))
    kd_hotlock_sample_spin_mcs_pinned();
}
bool kd_hotlock_record_spin(unsigned long address);
bool kd_hotlock_record_mutex(unsigned long address);
bool kd_hotlock_query_spin(unsigned long address);
bool kd_hotlock_query_mutex(unsigned long address);

#ifdef KDLOCK_SELFTEST
int kd_hotlock_lifetime_check(void);
#endif
#endif
