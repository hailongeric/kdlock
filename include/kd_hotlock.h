/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_HOTLOCK_H
#define KD_HOTLOCK_H
#include <linux/types.h>
#include <linux/percpu.h>
/* The sole spin CPU gate, read directly without a dynamic-table pointer.
 * Initialized before callers enter; the reader owns a CPU pin. */
DECLARE_PER_CPU(unsigned int, kd_hotlock_spin_gate);
/* Approximate current-batch counts; a completed comparison clears both. */
DECLARE_PER_CPU(unsigned long, kd_hotlock_spin_entries);
DECLARE_PER_CPU(unsigned long, kd_hotlock_spin_mcs);
/* Mutex uses its own native-attempt/failed-CAS window. Spin queue events must
 * never influence mutex admission or consume its observations. */
DECLARE_PER_CPU(unsigned long, kd_hotlock_mutex_entries);
DECLARE_PER_CPU(unsigned long, kd_hotlock_mutex_contentions);
#define KD_HOTLOCK_MUTEX_RATIO_LIMIT 256U
static __always_inline void kd_hotlock_mutex_entry_pinned(void)
{
  this_cpu_inc(kd_hotlock_mutex_entries);
}
/* CPU sampling cadence and entry-ratio precision are independent constants.
 * Keep the MCS interval a power of two for the native-head boundary mask. */
#define KD_HOTLOCK_SPIN_MCS_INTERVAL 1024U
#define KD_HOTLOCK_SPIN_RATIO_SHIFT 10U
/* Count once per physical acquisition, including the cold native route.
 * The direct native route counts after its first CAS, before contended work.
 * The acquisition pin keeps these approximate counts CPU-local. */
static __always_inline void kd_hotlock_spin_entry_pinned(void)
{
  this_cpu_inc(kd_hotlock_spin_entries);
}
static __always_inline bool kd_hotlock_spin_cpu_hot_pinned(void)
{
  return this_cpu_read(kd_hotlock_spin_gate) != 0;
}
/* A pinned native queue head may veto future CPU admission. Existing MCS
 * sampling retries; no owner, counter or timestamp changes here. */
static __always_inline void kd_hotlock_cool_spin_pinned(void)
{
  this_cpu_write(kd_hotlock_spin_gate, 0);
}
int kd_hotlock_init(void);
void kd_hotlock_exit(void);
/* A valid identity and initialized provider are caller preconditions. Spin
 * compares the CPU-local entry count after 1024 MCS publications, then reads one
 * timestamp for CPU frequency. With the default limit 2, (entries >> 10) < 2
 * admits at most 2047 entries per batch. Both counters restart at comparison;
 * the first batch includes startup entries. Limit zero bypasses only the ratio,
 * retaining the strict 40000000000-tick CPU window and per-lock heat gates.
 * Spin lock heat checks every 512 records against 1250000000 ticks. Mutex keeps
 * 1025 records and 2500000000 ticks. Combined CPU cooling/reheating resets lock
 * heat. Exact tables hold 256 identities per CPU/type without eviction.
 * Counters and IRQ sampling are approximate; a busy table delays comparison
 * without clearing the counters. The guard protects insertion and heat resets.
 * Queries neither count nor tick; admission never conveys lock ownership. */
bool kd_hotlock_record_spin(unsigned long address);
/* The caller must own an acquisition pin. This specialized entry omits the
 * generic preemption check while sharing all table and admission behavior. */
bool kd_hotlock_record_spin_pinned(unsigned long address);
/* One MCS publication on its physical CPU with preemption pinned. The raw
 * count/clock does not repeat at queue head; a native head can veto admission.
 * No lock sample: new CPU heat applies only
 * to later entries, including when this acquisition finishes natively. */
void kd_hotlock_sample_spin_mcs_pinned(void);
static __always_inline void kd_hotlock_record_spin_mcs_pinned(void)
{
  /* Approximate cadence is sufficient for admission; IRQs may shift a check. */
  this_cpu_inc(kd_hotlock_spin_mcs);
  if (this_cpu_read(kd_hotlock_spin_mcs) >= KD_HOTLOCK_SPIN_MCS_INTERVAL)
    kd_hotlock_sample_spin_mcs_pinned();
}
/* One failed native CAS; samples every 1024 contentions with the exclusive
 * (entries >> 10) < 256 gate, then clears both counts and updates the clock.
 * The initial limit 2 prevented promotion: native mutex owner bursts produced
 * 49k–183k entries per 1024 failed CASes in the measured 16-worker case. */
bool kd_hotlock_record_mutex(unsigned long address);
bool kd_hotlock_query_spin(unsigned long address);
bool kd_hotlock_query_mutex(unsigned long address);

#ifdef KDLOCK_SELFTEST
int kd_hotlock_lifetime_check(void);
#endif
#endif
