/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_REQUEST_POOL_H
#define KDLOCK_REQUEST_POOL_H

#include "jit.h"
#include "native_entry.h"
#include "owner_progress.h"

struct kd_request_pool;
struct kd_request_slot;

/* The pool guard protects only these referring-control metadata fields. */
enum kd_request_slot_phase {
	KD_REQUEST_SLOT_FREE,
	KD_REQUEST_SLOT_RESERVED,
	KD_REQUEST_SLOT_PREPARING,
	KD_REQUEST_SLOT_LIVE,
	KD_REQUEST_SLOT_DISCARDING,
};

enum kd_request_user_kind {
	KD_REQUEST_USER_UNUSED,
	KD_REQUEST_USER_CONTROL,
	KD_REQUEST_USER_BINDING,
	KD_REQUEST_USER_RETURN,
	KD_REQUEST_USER_AUXILIARY,
	KD_REQUEST_USER_NOTIFIER,
	KD_REQUEST_USER_IMAGE,
	KD_REQUEST_USER_OWNER,
	/* Managed only by set_parent/drop_parent, never generic hold/put. */
	KD_REQUEST_USER_PARENT,
};

/*
 * Preallocated exact membership, not an activity count. Retain this record and
 * its containing allocation through every API and observer. A claim/identity
 * comparison is not a storage reference. No identity or record may be reused
 * while an old observer could still present it. Before first hold, initialize
 * private storage; creation and reuse of an unlinked record are serialized by
 * its caller. A successful put/finish ends every access to that user and
 * its old slot unless another explicit user independently retains them.
 */
struct kd_request_user {
	struct list_head link;
	struct kd_request_slot *slot;
	const void *identity;
	enum kd_request_user_kind kind;
	bool linked;
};

/*
 * Persistent task-provisioned control, never another source packet. Exactly
 * call.node.state points to original W's canonical S_W, including when another
 * physical task reserves/serves this record. Simultaneously live requests use
 * distinct slots. Every source, image, auxiliary, binding, return, notifier and
 * controller actor holds an exact user through its final API/access. In
 * particular, an image actor drops its slot user only AFTER the image API has
 * returned and its last metadata access has ended. An actual owner-progress
 * producer is covered by final node.retirable publication and its no-later-
 * access contract; any additional owner observer still needs its own user.
 *
 * Reserve -> optional set_parent -> prepare precedes request publication. Only
 * the serialized private controller prepares/cancels/discards a request. A
 * parent is already LIVE when attached to a RESERVED child, so parent links
 * cannot create cycles; a LIVE child is never reparented. Its embedded exact
 * parent_user retains the parent until explicit drop after final parent access.
 *
 * Subrecords are private construction inputs or belong to their own component.
 * Hold a slot user across their use. pool and claim are immutable while the
 * reservation is retained; other mutable pool metadata belongs to these APIs.
 * Native-return freshness is not relaxed: a
 * retirable record whose native_return is CURRENT remains occupied. Out-of-slot
 * endpoints whose control refers here need exact users through final observers.
 */
struct kd_request_slot {
	struct list_head pool_link;
	struct kd_request_pool *pool;
	const void *claim;
	enum kd_request_slot_phase phase;
	struct list_head users;
	struct kd_request_slot *parent;
	struct kd_request_user parent_user;

	struct kd_jit_mutex_call call;
	struct kd_jit_mutex_driver driver;
	struct kd_execution_binding capture;
	struct kd_execution_binding native_return;
	struct kd_jit_image_use execution_use;
	struct kd_jit_image_use exit_use;
	struct kd_jit_image_use return_use;
	struct kd_jit_image_use source_use;
	struct kd_mutex_entry entry;
	struct kd_owner_batch owner_batch;
};

/*
 * Caller-owned storage initialized before task lock use/publication. The array,
 * pool, core and task backing outlive every API and escaped observer. The array
 * has exactly the supplied extent, does not overlap those other objects, and
 * contains only fresh/private records. Capacity bounds ALL occupied records,
 * including completed requests awaiting physical retirement or a last current
 * endpoint; it is not merely a nesting-depth bound. Zero capacity is explicit
 * and permitted. There is no allocator, refill, wait or default capacity.
 *
 * This pool belongs to original W, not the physical executor's own root. The
 * immutable state pointer supplies O(1) identity; root attachment binds the pool
 * to state.requests. This component neither selects that attachment nor turns
 * private -ENOSPC admission into a public void mutex_lock error or native route.
 * No source execution, waiting, image/release guard or task-ref drop runs while
 * guard is held. The exact lists, never returned statistics, establish users.
 */
struct kd_request_pool {
	raw_spinlock_t guard;
	struct kd_thread_state *state;
	struct kd_request_slot *slots;
	unsigned int capacity;
	struct list_head free_slots;
	struct list_head live_slots;
};

int kd_request_pool_init(struct kd_request_pool *pool,
			 struct kd_thread_state *state,
			 struct kd_request_slot *slots, unsigned int capacity);
/* Exact list inspection only; empty alone is not a task detach/free proof. */
bool kd_request_pool_empty(struct kd_request_pool *pool);
/* Nonblocking metadata collection of LIVE, fully finished unreferenced slots.
 * No raw claim grants an actor permission to access a collected record. Close
 * every actor with put/finish before allowing collection; do not revisit an old
 * slot afterward. The returned count is a statistic, not an ownership proof.
 */
unsigned int kd_request_pool_collect(struct kd_request_pool *pool);

/*
 * Reserve under exact current W binding. Fresh non-NULL claim is caller-retained
 * through all possible observers, and is not a reference. RESERVED storage is
 * private to its controller and cannot be collected. Before prepare or escaped
 * publication, register every referring actor with user_hold. An exhausted pool
 * returns private -ENOSPC before any source/queue effect; no ancestor is waited
 * on to manufacture space. Capture/native_return are fresh small records only.
 */
int kd_request_slot_reserve(struct kd_request_pool *pool,
			    struct kd_execution_binding *binding, const void *claim,
			    struct kd_request_slot **slot);
/* Same reservation, with claim = &slot->call.acquisition_identity selected
 * while private. Read slot->claim before publication. Its address becomes fresh
 * again only after the complete old-user/observer reuse proof, just like this
 * slot's other embedded endpoints. This needs no separate claim allocator.
 */
int kd_request_slot_reserve_owned(struct kd_request_pool *pool,
				  struct kd_execution_binding *binding,
				  struct kd_request_slot **slot);
/* Copies the small immutable callback descriptor into slot.driver. It retains
 * no packet. All callback/context/stack/native-endpoint dependencies remain
 * caller-held. Failure takes no node task reference and leaves RESERVED; after
 * successful initialization, discard is the only never-enqueued unwind path.
 */
int kd_request_slot_prepare(struct kd_request_slot *slot, const void *claim,
			    struct kd_execution_binding *binding,
			    const struct kd_jit_mutex_driver *driver, bool ready);
int kd_request_slot_cancel(struct kd_request_slot *slot, const void *claim);
int kd_request_slot_discard(struct kd_request_slot *slot, const void *claim);
/* Final quiescent visit, serialized by caller against collect and other APIs.
 * Requires every exact user ended. Prefer user_finish for a concurrently
 * collectable controller: dropping a last user and then revisiting its raw slot
 * is invalid. Success permits reuse; no subsequent slot access is allowed.
 */
int kd_request_slot_release(struct kd_request_slot *slot, const void *claim);

void kd_request_user_init(struct kd_request_user *user);
int kd_request_user_hold(struct kd_request_slot *slot, const void *claim,
			 struct kd_request_user *user, const void *identity,
			 enum kd_request_user_kind kind);
int kd_request_user_put(struct kd_request_user *user, const void *identity);
/* Consume this user and try final reuse atomically under the pool guard. Zero
 * means the user ended, even if some other completion proof keeps the slot LIVE
 * for later collect. Do not inspect that user/slot after successful return.
 */
int kd_request_user_finish(struct kd_request_user *user, const void *identity);
int kd_request_slot_set_parent(struct kd_request_slot *child,
			       const void *child_claim,
			       struct kd_request_slot *parent,
			       const void *parent_claim);
int kd_request_slot_drop_parent(struct kd_request_slot *child,
				const void *child_claim);

/*
 * Complete caller drain is mandatory: close source admission, end all escaped
 * users/APIs and source/return/image/auxiliary controls, collect grants and drain
 * actual owner duties. Both calls require current original W on its retained
 * exact NATIVE endpoint. They inspect metadata only, never mutable S_W values.
 * All remaining occupied slots must otherwise be finished and contain precisely
 * that endpoint as native_return. A stable external endpoint requires an empty
 * pool. RESERVED/no-node records and actual retirable LIVE records qualify only
 * after all their independent users/subrecords have ended.
 *
 * can_detach is preflight, not a quiescence proof or reservation. detach repeats
 * all checks and CASes exact_native -> NULL under the same pool guard, then
 * reclaims those slots using only infallible metadata moves. A failed CAS has
 * no slot effects. No fallible operation follows successful revocation. Success
 * ends every access to embedded endpoints/slots; caller may then detach backing
 * under its full-drain proof. This does not clear/copy the canonical packet.
 */
int kd_request_pool_can_detach(struct kd_request_pool *pool,
			       struct kd_execution_binding *exact_native);
int kd_request_pool_detach(struct kd_request_pool *pool,
			   struct kd_execution_binding *exact_native);

#endif
