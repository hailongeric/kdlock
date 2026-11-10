/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_SOURCE_EPOCH_H
#define KDLOCK_SOURCE_EPOCH_H

#include <linux/list.h>
#include <linux/spinlock.h>
#include <linux/types.h>

/* Private source-retention records; no executable or register-packet layout. */
struct kd_jit_source_region {
	unsigned long start;
	const unsigned char *bytes;
	size_t length;
};

/*
 * The constructor copies this small description, not its pointed-to backing.
 * version is an exact nonempty byte sequence, without an implied trailing NUL.
 * Regions name actual source load addresses and retained immutable snapshot
 * bytes. configuration_identity and load_identity name exact retained objects,
 * including the configuration and load incarnation used by the decoder/GS
 * lowering. current_task_gs_offset is that configuration's lowering input, not
 * an origin task's freshly captured hardware GS base.
 *
 * Keep all backing and identities immutable under the transferred lease. A
 * version, hash or address comparison does not establish that lease or prevent
 * later live-text changes. Numeric range and overlap checks validate supplied
 * input consistency only; no live kernel/source read or snapshot is made here.
 */
struct kd_jit_source_description {
	const unsigned char *version;
	size_t version_length;
	const struct kd_jit_source_region *regions;
	unsigned int region_count;
	const void *configuration_identity;
	const void *load_identity;
	unsigned long current_task_gs_offset;
};

typedef void (*kd_jit_source_release_fn)(void *lease);

struct kd_jit_source_epoch;

enum kd_jit_source_use_kind {
	KD_JIT_SOURCE_USE_UNUSED,
	KD_JIT_SOURCE_USE_BUILD,
	KD_JIT_SOURCE_USE_IMAGE,
	KD_JIT_SOURCE_USE_FEEDBACK,
};

enum kd_jit_source_phase {
	KD_JIT_SOURCE_OPEN,
	KD_JIT_SOURCE_CLOSED,
	/* Final callback claimed once; the phase alone does not prove its return. */
	KD_JIT_SOURCE_RELEASE_CLAIMED,
};

/* Exact caller-preallocated membership, never an aggregate activity estimate.
 * Initialize private storage before use. Its holder identifies this reservation;
 * keep both addresses valid and unreused through all old API/metadata observers.
 * The caller serializes creation/reuse of each record. While linked, fields are
 * read-only to callers and its description/payload may be accessed under the
 * already-established lease. Finish every payload access before the final put.
 */
struct kd_jit_source_use {
	struct list_head epoch_link;
	struct kd_jit_source_epoch *epoch;
	const void *holder;
	enum kd_jit_source_use_kind kind;
	bool linked;
};

/*
 * One caller-owned epoch and exact retained dependencies, independent of image
 * generation and feedback revision. guard protects membership/phase metadata
 * only; no provider callback, source work or allocation runs under it.
 * description remains immutable after successful construction. Access its
 * backing only under a live exact use or the separately retained provider's
 * construction/finalization ownership, never via an unretained raw pointer.
 */
struct kd_jit_source_epoch {
	raw_spinlock_t guard;
	struct list_head users;
	struct kd_jit_source_description description;
	void *lease;
	kd_jit_source_release_fn release;
	enum kd_jit_source_phase phase;
};

/*
 * Private constructor, once per unreused epoch. The caller already established
 * a coherent immutable source lease and retains all supplied backing while this
 * call validates numeric spans and matching bytes in overlapping regions. There
 * must be at least one nonempty region; a region's last byte may be ULONG_MAX.
 * Success transfers exactly the supplied lease/release duty; failure leaves the
 * epoch untouched and that duty with the caller. No provider/module reference,
 * live-text mutation interlock, allocator or source-admission policy is created.
 */
int kd_jit_source_epoch_init(struct kd_jit_source_epoch *epoch,
		const struct kd_jit_source_description *description,
		void *lease, kd_jit_source_release_fn release);
void kd_jit_source_use_init(struct kd_jit_source_use *use);

/* New direct memberships require OPEN. They grant retention only, never new
 * execution/publication admission. An IMAGE user must outlive its actual image
 * code/metadata users and RCU retirement; a FEEDBACK user need not pin that code.
 */
int kd_jit_source_use_get(struct kd_jit_source_epoch *epoch,
		struct kd_jit_source_use *use, const void *holder,
		enum kd_jit_source_use_kind kind);
/* Reserve a same-epoch child from an exact live parent before dropping it.
 * Allowed while CLOSED to finish already-retained dependencies. This is lifetime
 * extension only, not permission to build/publish/execute new source after close.
 */
int kd_jit_source_use_extend(struct kd_jit_source_use *parent,
		const void *parent_holder, struct kd_jit_source_use *child,
		const void *child_holder, enum kd_jit_source_use_kind kind);
/* No callback on put. Success ends all use/payload accesses by this caller;
 * finalizer eligibility is not source-execution, publication or feedback ACK.
 */
int kd_jit_source_use_put(struct kd_jit_source_use *use, const void *holder);

/* Close only NEW DIRECT RETENTION memberships. Image/root lookup is separate:
 * before source mutation/unload the provider must close/remove every bound image
 * slot, drain exact execution/return/source users and old RCU readers, and retain
 * arbitrary native suffix/return text through its actual independent last users.
 * BUILD/IMAGE/FEEDBACK records do not replace those enclosing provider holds.
 */
int kd_jit_source_epoch_close(struct kd_jit_source_epoch *epoch);
/*
 * Serialized sleepable finalizer, outside source execution and every metadata
 * guard/RCU read-side section. CLOSED with no users claims the callback once,
 * clears its retained binding, unlocks, then invokes cached release(lease).
 * -EBUSY leaves ownership intact; -EALREADY says another finalizer claimed it,
 * not that its callback has returned. No epoch/description/payload access follows
 * callback invocation. No reinitialization until every old observer has ended.
 *
 * Epoch header, its containing allocation, callback code and callback execution
 * backing must be retained SEPARATELY through the finalizer's actual return;
 * the callback may release leased payload, never that active control backing or
 * mutate these records. Successful return proves only this callback completed,
 * not an enforceable live-text freeze or complete native-execution quiescence.
 */
int kd_jit_source_epoch_try_release(struct kd_jit_source_epoch *epoch);

#endif
