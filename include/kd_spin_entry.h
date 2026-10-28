/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_ENTRY_H
#define KD_SPIN_ENTRY_H

#include <linux/spinlock.h>
#include "kd_spin_type.h"

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
unsigned long kd_spin_entry_owner(raw_spinlock_t *origin);
int kd_spin_entry_begin(raw_spinlock_t *origin, enum kd_spin_entry_kind kind,
			struct kd_spin_ref *ref);
/* Contended root: transfer exactly one existing pin
 * to the ticket on success. On failure caller still owns/balances its pin. */
int kd_spin_entry_begin_pinned(raw_spinlock_t *origin,
			       struct kd_spin_ref *ref);
bool kd_spin_entry_find(raw_spinlock_t *origin, struct kd_spin_ref *ref);
bool kd_spin_entry_task_active(void);
bool kd_spin_entry_native_active(void);
kd_spinlock_t *kd_spin_entry_word(const struct kd_spin_ref *ref);

/* The caller owns the KD word. Claim is idempotent for this live ticket;
 * release_origin retires only ownership metadata. The scheduler publishes one release
 * before ending an owned request. Neither operation consumes the entry pin.
 */
int kd_spin_entry_claim(const struct kd_spin_ref *ref);
int kd_spin_entry_release_origin(const struct kd_spin_ref *ref);
/* An early-release batch keeps its ticket/pin alive. After acquiring the KD
 * word again, only the original task/CPU may reclaim the released ticket. */
int kd_spin_entry_reclaim(const struct kd_spin_ref *ref);

/* Begin adds one preemption pin on success. Only its task/CPU may end it.
 * End a waiting ticket only after cancellation/dequeue or delegated completion.
 * Copy all needed per-CPU registers/metadata before end: it may reschedule.
 */
int kd_spin_entry_end(struct kd_spin_ref *ref);
/* Retire ticket metadata while retaining the caller pin for final restoration.
 * On success the caller must unpin after its final per-CPU/packet access. */
int kd_spin_entry_end_pinned(struct kd_spin_ref *ref);
/* Exact ticket, one physical CAS, no pending bit or queue on failure. */
int kd_spin_nested_try_once(raw_spinlock_t *lock, struct kd_spin_ref *ref);
int kd_spin_nested_release_exact(raw_spinlock_t *lock,
				struct kd_spin_ref *ref);

/* Executors register every native frame before waking the original waiter.
 * Put never unpins a remote CPU. The waiter marks native and consumes its pin
 * only after physical ACKs and all frame borrows have retired.
 */
int kd_spin_entry_borrow_get(const struct kd_spin_ref *ref);
int kd_spin_entry_mark_native(const struct kd_spin_ref *ref);
int kd_spin_entry_borrow_wait(const struct kd_spin_ref *ref);
int kd_spin_entry_borrow_put(const struct kd_spin_ref *ref, bool *last);

#ifdef KDLOCK_SELFTEST
int kd_spin_entry_selftest(void);
#endif

#endif
