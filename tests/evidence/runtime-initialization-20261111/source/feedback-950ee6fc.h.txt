/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_FEEDBACK_H
#define KDLOCK_FEEDBACK_H

#include "jit.h"
#include "source_epoch.h"

struct kd_jit_feedback_producer;

enum kd_jit_feedback_producer_use_kind {
	KD_JIT_FEEDBACK_PRODUCER_IMAGE,
	KD_JIT_FEEDBACK_PRODUCER_FACT,
};

struct kd_jit_feedback_producer_use {
	struct list_head link;
	struct kd_jit_feedback_producer *producer;
	const void *holder;
	enum kd_jit_feedback_producer_use_kind kind;
	bool linked;
};

/* Durable provider metadata, outside executable payload and both task stacks.
 * identity names this exact construction, not just its source version. The
 * numeric image identity is compared only; no descriptor dereference is allowed
 * after its code hold ends. This control and identity stay unreused through all
 * IMAGE/FACT users and API observers. Pending facts retain source, not old code.
 */
struct kd_jit_feedback_producer {
	raw_spinlock_t guard;
	struct list_head users;
	struct kd_jit_source_use source_use;
	const void *identity;
	unsigned long image_identity;
	bool closed;
	bool released;
};

/* Fresh private producer, initialized before image_owner_init. Derive source
 * FEEDBACK retention from the live BUILD; no code hold is transferred. Keep its
 * control/identity backing independently through producer_release return.
 */
int kd_jit_feedback_producer_init(struct kd_jit_feedback_producer *producer,
		const void *identity, const struct kd_jit_image *image,
		struct kd_jit_source_use *build, const void *build_holder);
void kd_jit_feedback_producer_use_init(struct kd_jit_feedback_producer_use *use);
int kd_jit_feedback_producer_use_get(struct kd_jit_feedback_producer *producer,
		struct kd_jit_feedback_producer_use *use, const void *holder,
		enum kd_jit_feedback_producer_use_kind kind,
		const struct kd_jit_image *image);
int kd_jit_feedback_producer_use_put(struct kd_jit_feedback_producer_use *use,
		const void *holder);
/* Closing is refused while any IMAGE use lives: admitted execution must remain
 * able to record its exits. FACT users can finish after close. Release is a
 * serialized final source put, with no provider callback or code access.
 */
int kd_jit_feedback_producer_close(struct kd_jit_feedback_producer *producer);
int kd_jit_feedback_producer_release(struct kd_jit_feedback_producer *producer);

enum kd_jit_feedback_target_class {
	KD_JIT_FEEDBACK_UNCLASSIFIED,
	KD_JIT_FEEDBACK_ORDINARY,
	KD_JIT_FEEDBACK_SOURCE_API,
};

/* Immutable copied scalars only, never a second S_W or source continuation.
 * Exact epoch/version and producer identity survive every disposition. Pointer
 * identities have meaning only while their retained claim/provider holds live;
 * transport must preserve their exact mapping including record incarnation,
 * not dereference numeric tokens.
 */
struct kd_jit_feedback_fact {
	const void *identity;
	unsigned long incarnation;
	const void *producer_identity;
	unsigned long producer_image_identity;
	struct kd_jit_source_epoch *epoch;
	const unsigned char *version;
	size_t version_length;
	unsigned long kind;
	unsigned long detail;
	unsigned long source_ip;
	unsigned long target;
	unsigned long cursor;
	unsigned long phase;
	enum kd_jit_feedback_target_class classification;
	int entry_result;
};

struct kd_jit_feedback_pool;
struct kd_jit_feedback_claim;

enum kd_jit_feedback_record_phase {
	KD_JIT_FEEDBACK_FREE,
	KD_JIT_FEEDBACK_RECORDING,
	KD_JIT_FEEDBACK_PENDING,
	KD_JIT_FEEDBACK_ACKNOWLEDGED,
	KD_JIT_FEEDBACK_SETTLED,
	KD_JIT_FEEDBACK_RELEASING,
};

struct kd_jit_feedback_record {
	struct list_head link;
	struct kd_jit_feedback_pool *pool;
	struct kd_jit_feedback_fact fact;
	struct kd_jit_feedback_producer_use producer_use;
	struct kd_jit_source_use source_use;
	struct kd_jit_feedback_claim *claim;
	enum kd_jit_feedback_record_phase phase;
	char identity;
	unsigned long incarnation;
};

/* Caller-sized finite storage, shared by admitted tasks if desired. capacity is
 * the actual explicit record-array extent, with no implicit/default count. The
 * supported workload guarantees a free record at each reached coverage miss.
 * No pending fact is overwritten; pending/compiling facts never close admission.
 * A record identity is (address, exact incarnation); each 64-bit incarnation
 * advances on reservation and never wraps in the supported workload. This
 * identity sequence grants no ownership and is not an activity counter.
 * Every record/control is outside source/auxiliary stacks and retained through
 * all producers, consumers and final API accesses. No allocation or source work
 * runs under this metadata guard. Constructors require exclusive fresh storage.
 */
struct kd_jit_feedback_pool {
	raw_spinlock_t guard;
	struct list_head free;
	struct list_head pending;
	struct kd_jit_feedback_record *records;
	unsigned int capacity;
};

int kd_jit_feedback_pool_init(struct kd_jit_feedback_pool *pool,
		struct kd_jit_feedback_record *records, unsigned int capacity);
/* Current source actor, actual retained producing image and copied current IO.
 * Call once for a reached coverage miss before consuming/staging this exit; no
 * source effects are performed. Nonobservation misses remain pending too.
 * A violated storage/lifetime precondition returns an error without consuming
 * the pending exit. There is no saturation fallback, replay or admission gate.
 */
int kd_jit_feedback_record_exit(struct kd_jit_feedback_pool *pool,
		const struct kd_jit_image *image, unsigned long cursor,
		int entry_result, const struct kd_jit_io *io,
		enum kd_jit_feedback_target_class classification);

struct kd_jit_feedback_claim_item {
	struct kd_jit_feedback_record *record;
	const void *identity;
	unsigned long incarnation;
};

/* One serialized consumer per claimed record. Caller supplies immutable bounded
 * item storage; a claim freezes only the selected existing facts. Later facts
 * remain pending. Retain claim/items/holder through compiler/publication and all
 * transport observers. claim_end begins after all such observers end; it can
 * release individual records before returning. After an end error, only retry
 * end is legal: earlier items may already be reused/unclaimed. Pending
 * nonobservations/uncovered facts are unclaimed, never discarded, by claim_end.
 */
struct kd_jit_feedback_claim {
	struct kd_jit_feedback_pool *pool;
	struct kd_jit_source_epoch *epoch;
	struct kd_jit_feedback_claim_item *items;
	unsigned int count;
	unsigned int next;
	const void *holder;
	bool linked;
	bool ending;
};

void kd_jit_feedback_claim_init(struct kd_jit_feedback_claim *claim);
int kd_jit_feedback_claim_begin(struct kd_jit_feedback_pool *pool,
		struct kd_jit_source_epoch *epoch, struct kd_jit_feedback_claim *claim,
		struct kd_jit_feedback_claim_item *items, unsigned int capacity,
		const void *holder);
/* This validates exact immutable membership, not emission or publication. */
int kd_jit_feedback_claim_check(struct kd_jit_feedback_claim *claim,
		const void *holder, const struct kd_jit_feedback_claim_item *items,
		unsigned int count);
/* Publication bridge only, after exact successful publication validation. Mark
 * precisely the included emitted subset atomically; no release/reuse yet. Raw
 * fact presence, compiler input or construction alone never authorizes this API.
 */
int kd_jit_feedback_claim_ack(struct kd_jit_feedback_claim *claim,
		const void *holder, const struct kd_jit_feedback_claim_item *items,
		unsigned int count);
int kd_jit_feedback_claim_end(struct kd_jit_feedback_claim *claim,
		const void *holder);

/* Actual host archival result, distinct from emitted coverage. The caller has
 * durably stored the exact copied claim facts and source/producer provenance;
 * content_id is the 32-byte identity of those stored bytes. Its immutable
 * backing and all claim/control observers remain retained through settlement.
 */
struct kd_jit_feedback_archive {
	unsigned char content_id[32];
	struct kd_jit_feedback_claim *claim;
	const void *claim_holder;
	struct kd_jit_source_epoch *epoch;
	const struct kd_jit_feedback_claim_item *items;
	unsigned int count;
};

struct kd_jit_feedback_settlement {
	const void *identity;
	const struct kd_jit_feedback_archive *archive;
	struct kd_jit_feedback_claim *claim;
	const void *claim_holder;
	const struct kd_jit_feedback_claim_item *items;
	unsigned int count;
};

/* Private fresh receipt; not proof of a completed archive or settlement. */
void kd_jit_feedback_settlement_init(struct kd_jit_feedback_settlement *receipt);
/* Shutdown only: source admission is independently closed, epoch is CLOSED
 * with no BUILD/IMAGE/NATIVE users, and every selected producer is closed after
 * its images retired. Validate exact archived pending reservations, then mark
 * SETTLED atomically and return a distinct actual settlement receipt. This is
 * never a coverage ACK and admits no execution. Other/later records survive.
 * Caller serializes source shutdown, archive/receipt storage and claim APIs.
 * Actual durable archival is a host duty; identities alone do not perform it.
 * claim_end later releases settled holds after every archive/transport observer
 * ends. No mutation/provider backing is released by this metadata operation.
 */
int kd_jit_feedback_claim_settle(struct kd_jit_feedback_claim *claim,
		const void *holder, const struct kd_jit_feedback_archive *archive,
		struct kd_jit_feedback_settlement *receipt);

#endif
