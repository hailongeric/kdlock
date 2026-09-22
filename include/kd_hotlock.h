/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_HOTLOCK_H
#define KD_HOTLOCK_H
#include <linux/types.h>
#include <linux/percpu.h>
/* A view of the existing CPU gate, not a second heat flag. Initialized before
 * callers enter and valid until their final drain. The reader owns a CPU pin. */
DECLARE_PER_CPU(unsigned int *, kd_hotlock_spin_gate);
extern bool kd_spin_cold_fastpath;
extern unsigned int kd_spin_hot_min_queue;
static __always_inline bool kd_hotlock_spin_cpu_hot_pinned(void)
{
  return READ_ONCE(*this_cpu_read(kd_hotlock_spin_gate)) != 0;
}
/* This is a sampled-pressure policy, not a thread count or ownership cookie.
 * Remember it before publication: a hot publication that cools the CPU must
 * not also count its later queue-head acquisition in the same MCS operation. */
static __always_inline unsigned int kd_hotlock_spin_cold_queue_min_pinned(void)
{
  if (!kd_spin_cold_fastpath || !kd_spin_hot_min_queue ||
      kd_hotlock_spin_cpu_hot_pinned())
    return 0;
  return kd_spin_hot_min_queue;
}
int kd_hotlock_init(void);
void kd_hotlock_exit(void);
/* A valid lock identity and successful initialization are caller preconditions;
 * all callers must drain before exit. Reuse an existing CPU pin; otherwise pin
 * only this call (including sleepable mutex callers). Spin CPU rate is checked
 * at every eligible MCS event; cold-fastpath CPUs with a nonzero queue
 * minimum count qualifying queue-head acquisitions, while hot CPUs and the
 * original policy count publications. Mutex still uses 1024 entry records.
 * Both CPU clocks require a batch shorter than 40000000000 TSC ticks.
 * Each exact lock counter counts entries and checks when it exceeds 32.
 * Tables are preallocated (256 entries per CPU/type), with no ranked eviction.
 * Unknown locks at capacity remain cold; queries neither count nor tick.
 * Statistics are best-effort: non-task calls skip table access (queries are
 * cold), so pinned task callers need no busy flag or statistics barrier.
 * record returns policy admission (fixed true in observe); query reports only
 * cached local CPU/lock heat. No returned value conveys ownership. */
/* Caller already owns the acquisition pin; shared sampler reuses it. */
bool kd_hotlock_record_spin_pinned(unsigned long address);
/* One eligible MCS event on its physical CPU with preemption pinned. Producers
 * select publication or a qualifying cold queue head, never both for one
 * operation. No lock sample: new CPU heat applies only to later entries. */
void kd_hotlock_record_spin_mcs_pinned(void);
bool kd_hotlock_record_spin(unsigned long address);
bool kd_hotlock_record_mutex(unsigned long address);
bool kd_hotlock_query_spin(unsigned long address);
bool kd_hotlock_query_mutex(unsigned long address);

#ifdef KDLOCK_SELFTEST
int kd_hotlock_lifetime_check(void);
#endif
#endif
