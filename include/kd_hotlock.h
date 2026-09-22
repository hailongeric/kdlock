/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_HOTLOCK_H
#define KD_HOTLOCK_H
#include <linux/types.h>
int kd_hotlock_init(void);
void kd_hotlock_exit(void);
/* A valid lock identity and successful initialization are caller preconditions;
 * all callers must drain before exit. Reuse an existing CPU pin; otherwise pin
 * only this call (including sleepable mutex callers). Spin CPU rate is checked
 * at every MCS publication; mutex CPU rate still uses 1024 entry records.
 * Each exact lock counter counts entries and checks when it exceeds 32.
 * Tables are preallocated (256 entries per CPU/type), with no ranked eviction.
 * Unknown locks at capacity remain cold; queries neither count nor tick.
 * Statistics are best-effort: non-task calls skip table access (queries are
 * cold), so pinned task callers need no busy flag or statistics barrier.
 * record returns policy admission (fixed true in observe); query reports only
 * cached local CPU/lock heat. No returned value conveys ownership. */
/* Caller already owns the acquisition pin; shared sampler reuses it. */
bool kd_hotlock_record_spin_pinned(unsigned long address);
/* Actual MCS publication only, on the publishing CPU with preemption pinned.
 * No lock sample or policy decision: new CPU heat applies to later entries. */
void kd_hotlock_record_spin_mcs_pinned(void);
bool kd_hotlock_record_spin(unsigned long address);
bool kd_hotlock_record_mutex(unsigned long address);
bool kd_hotlock_query_spin(unsigned long address);
bool kd_hotlock_query_mutex(unsigned long address);

#ifdef KDLOCK_SELFTEST
int kd_hotlock_lifetime_check(void);
#endif
#endif
