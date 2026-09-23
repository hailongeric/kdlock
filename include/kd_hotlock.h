/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_HOTLOCK_H
#define KD_HOTLOCK_H
#include <linux/types.h>
#include <linux/percpu.h>
/* A view of the existing CPU gate, not a second heat flag. Initialized before
 * callers enter and valid until their final drain. The reader owns a CPU pin. */
DECLARE_PER_CPU(unsigned int *, kd_hotlock_spin_gate);
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
 * every eight against a strict 4000000 TSC tick window. Fast/pending acquisition
 * does not count. Mutex uses 1024 entry records and a 40000000000 tick window.
 * Each exact lock counter counts entries and checks when it exceeds 32.
 * Tables are preallocated (256 entries per CPU/type), with no ranked eviction.
 * Unknown locks at capacity remain cold; queries neither count nor tick.
 * Statistics are best-effort: non-task calls skip table access (queries are
 * cold), so pinned task callers need no busy flag or statistics barrier.
 * record returns policy admission (fixed true in observe); query reports only
 * cached local CPU/lock heat. No returned value conveys ownership. */
/* Caller already owns the acquisition pin; shared sampler reuses it. */
bool kd_hotlock_record_spin_pinned(unsigned long address);
/* One MCS publication on its physical CPU with preemption pinned. Queue-head
 * acquisition never samples again. No lock sample: new CPU heat applies only
 * to later entries, including when this acquisition finishes natively. */
void kd_hotlock_record_spin_mcs_pinned(void);
bool kd_hotlock_record_spin(unsigned long address);
bool kd_hotlock_record_mutex(unsigned long address);
bool kd_hotlock_query_spin(unsigned long address);
bool kd_hotlock_query_mutex(unsigned long address);

#ifdef KDLOCK_SELFTEST
int kd_hotlock_lifetime_check(void);
#endif
#endif
