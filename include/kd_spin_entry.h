/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_ENTRY_H
#define KD_SPIN_ENTRY_H

#include "kd_spin_gate.h"

#define KD_SPIN_ENTRY_SLOTS 32

struct kd_spin_entry;

enum kd_spin_entry_kind {
	KD_SPIN_ENTRY_HOOK,
	KD_SPIN_ENTRY_VIRTUAL,
};

/* Stable pool storage plus a generation, not a pointer into an MCS node.
 * A virtual B request has its own ref and separately carries the original
 * hook waiter's ref in its eventual queue/frame metadata.
 */
struct kd_spin_ref {
	struct kd_spin_entry *entry;
	unsigned long sequence;
};

int kd_spin_entries_init(void);
void kd_spin_entries_exit(void);
int kd_spin_entries_check_idle(void);
int kd_spin_entry_begin(raw_spinlock_t *origin, enum kd_spin_entry_kind kind,
			struct kd_spin_ref *ref);
bool kd_spin_entry_find(raw_spinlock_t *origin, struct kd_spin_ref *ref);
bool kd_spin_entry_task_active(void);
bool kd_spin_entry_native_active(void);
struct kd_spin_gate *kd_spin_entry_gate(const struct kd_spin_ref *ref);

/* The caller owns the private word. Claim is idempotent for this live ticket;
 * release_origin releases only L. The scheduler must publish its word release
 * before ending an owned request. Neither operation consumes the entry pin.
 */
int kd_spin_entry_claim(const struct kd_spin_ref *ref);
int kd_spin_entry_release_origin(const struct kd_spin_ref *ref);
/* An early-release batch keeps its ticket/pin alive. After reclaiming private
 * S, only that original task/CPU may reacquire L with the released ticket. */
int kd_spin_entry_reclaim(const struct kd_spin_ref *ref);

/* Begin adds one preemption pin on success. Only its task/CPU may end it.
 * End a waiting ticket only after cancellation/dequeue or delegated completion.
 * Copy all needed per-CPU registers/metadata before end: it may reschedule.
 */
int kd_spin_entry_end(struct kd_spin_ref *ref);

/* Executors register every native frame before waking the original waiter.
 * Put never unpins a remote CPU. The waiter marks native and consumes its pin
 * only after receiving the last frame's completion acknowledgment.
 */
int kd_spin_entry_borrow_get(const struct kd_spin_ref *ref);
int kd_spin_entry_mark_native(const struct kd_spin_ref *ref);
int kd_spin_entry_borrow_put(const struct kd_spin_ref *ref, bool *last);

#ifdef KDLOCK_SELFTEST
int kd_spin_entry_selftest(void);
#endif

#endif
