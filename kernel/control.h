/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_CONTROL_H
#define KDLOCK_CONTROL_H

#include "feedback_publish.h"

#define KD_JIT_CONTROL_ABI 1UL

enum kd_jit_control_operation {
	KD_JIT_CONTROL_CLAIM = 1,
	KD_JIT_CONTROL_BUILD_START = 2,
	KD_JIT_CONTROL_STAGE_LOAD = 3,
	KD_JIT_CONTROL_PUBLISH = 4,
	KD_JIT_CONTROL_ACK = 5,
	KD_JIT_CONTROL_CLAIM_END = 6,
	KD_JIT_CONTROL_ABORT = 7,
	KD_JIT_CONTROL_SOURCE = 8,
	KD_JIT_CONTROL_SHUTDOWN = 9,
	KD_JIT_CONTROL_ARCHIVE_CLAIM = 10,
	KD_JIT_CONTROL_SETTLE = 11,
};

struct kd_jit_control_bytes {
	const void *data;
	size_t length;
};

/* Durable construction controls are separate from executable payload. The
 * provider retains this allocation and identity through published-slot, FACT,
 * compiler, channel and host-history observers, even after code is released.
 */
struct kd_jit_control_image {
	struct kd_jit_feedback_producer producer;
	struct kd_jit_image_owner owner;
	struct kd_jit_image_owner_use published;
	bool producer_initialized;
	bool owner_initialized;
	bool published_live;
	bool owner_released;
	bool producer_closed;
	bool producer_released;
};

/* reserve supplies ACTUAL stable planned metadata addresses before host build.
 * load must install the exact descriptor/inputs/emission at those addresses,
 * with image.feedback_producer == &control->producer. Symbols are exact ASCII C
 * identifiers with no implied NUL; the host exporter still validates them.
 * The already-owned code hold is transferred only when reserve returns success.
 */
struct kd_jit_control_candidate {
	struct kd_jit_control_image *control;
	const struct kd_jit_image *image;
	const struct kd_jit_image_inputs *inputs;
	const struct kd_jit_feedback_emission_receipt *emission;
	unsigned long code_base;
	size_t code_capacity;
	struct kd_jit_control_bytes descriptor_symbol;
	struct kd_jit_control_bytes source_symbol;
	struct kd_jit_control_bytes producer_symbol;
	struct kd_jit_control_bytes entry_symbol;
	void *code_lease;
	kd_jit_image_code_release_fn code_release;
};

/* One fresh compiler cycle; allocate supplies these arrays at explicit capacity
 * and calls storage_init before returning. No source execution packet lives here.
 * Do not recycle actual control/claim/update/receipt addresses while old host
 * identity mappings/history observers remain. The provider owns that retention.
 */
struct kd_jit_control_storage {
	struct kd_jit_feedback_claim claim;
	struct kd_jit_feedback_claim_item *claim_items;
	struct kd_jit_feedback_claim_item *included;
	struct kd_jit_feedback_claim_item *ack_items;
	unsigned int capacity;
	unsigned int included_count;
	const void *claim_holder;
	struct kd_jit_source_use build;
	struct kd_jit_image_owner_use baseline;
	struct kd_jit_image_owner_use candidate_use;
	struct kd_jit_image_update update;
	struct kd_jit_feedback_publication publication;
	struct kd_jit_control_candidate candidate;
	struct kd_jit_control_image *old;
	const struct kd_jit_image *expected_old;
	const struct kd_jit_image *retired;
	bool build_live;
	bool claim_live;
	bool reserved;
	bool baseline_live;
	bool candidate_live;
	bool loaded;
	bool update_started;
	bool old_prepared;
	bool publication_prepared;
	bool committed;
	bool new_bound;
	bool old_finished;
	bool current_set;
	bool old_reported;
	bool published;
	bool acknowledged;
	bool aborted;
	bool ending;
};

struct kd_jit_control_session;

/* Real provider operations, called in serialized sleepable controller context,
 * outside all metadata guards. They perform actual source/code/storage I/O;
 * no allocator, executable-memory mechanism or text-mutation policy is chosen.
 * The enclosing provider already holds coherent immutable source/config/load
 * and native/JIT return lifetimes. Module residency alone is insufficient.
 *
 * allocate/release govern cycle control storage, not published image controls.
 * current/published/retired govern this exact slot's retained provider bindings;
 * the single configured session is its exclusive controller. published/retired
 * are nonfailing metadata handoffs, never source execution. retired retains old
 * controls until image_collect and every independent observer have finished.
 *
 * reserve failure transfers nothing. load owns isolated staging for this exact
 * reservation; it retains/compares complete artifact inputs across retries and
 * returns success again only for identical input, without loading twice. Error
 * leaves the original reservation/code hold intact for explicit abort/retry.
 * Code release is synchronous/nonfailing under image_owner.h. No callback can
 * release active session/control/callback backing. idle proves ALL separate
 * retired provider controls/holds have ended, not an estimated activity count.
 */
struct kd_jit_control_provider_ops {
	int (*allocate)(void *context, struct kd_jit_control_storage **storage);
	void (*release)(void *context, struct kd_jit_control_storage *storage);
	struct kd_jit_control_image *(*current)(void *context, struct kd_jit_image_slot *slot);
	int (*reserve)(void *context, struct kd_jit_source_epoch *epoch,
		struct kd_jit_control_candidate *candidate);
	int (*load)(void *context, const struct kd_jit_control_candidate *candidate,
		const struct kd_jit_control_bytes *assembly,
		const struct kd_jit_control_bytes *metadata,
		const struct kd_jit_control_bytes *manifest,
		const struct kd_jit_control_bytes *machine,
		const struct kd_jit_control_bytes *flat_metadata);
	void (*published)(void *context, struct kd_jit_image_slot *slot,
		struct kd_jit_control_image *old, struct kd_jit_control_image *candidate);
	void (*retired)(void *context, struct kd_jit_control_image *old);
	bool (*idle)(void *context);
	int (*admit_publish)(void *context);
	int (*command)(void *context, struct kd_jit_control_session *session,
		unsigned long op, const void *input, size_t input_length,
		void *output, size_t output_capacity, size_t *output_length);
};

struct kd_jit_control_session {
	struct kd_jit_feedback_pool *feedback;
	struct kd_jit_source_epoch *epoch;
	struct kd_jit_image_slot *slot;
	const struct kd_jit_control_provider_ops *ops;
	void *context;
	struct kd_jit_control_storage *storage;
};

void kd_jit_control_image_init(struct kd_jit_control_image *image);
void kd_jit_control_storage_init(struct kd_jit_control_storage *storage,
		struct kd_jit_feedback_claim_item *claim_items,
		struct kd_jit_feedback_claim_item *included,
		struct kd_jit_feedback_claim_item *ack_items, unsigned int capacity);
int kd_jit_control_session_init(struct kd_jit_control_session *session,
		struct kd_jit_feedback_pool *feedback, struct kd_jit_source_epoch *epoch,
		struct kd_jit_image_slot *slot, const struct kd_jit_control_provider_ops *ops,
		void *context);
/* Kernel buffers only. Payload is LE u64 [ABI,op,total_bytes,item_count], then
 * fixed scalars, item rows, then length-prefixed raw blobs without padding.
 * The channel owns usercopy, its sequence/replay cache and disconnect retention.
 * -EBUSY/-EAGAIN preserve exact progress; a fresh channel sequence may retry.
 * Stage/publish/ACK flags prevent repeating successful effects. Claim_end is an
 * explicit host-observers-ended receipt; it never discards pending leftovers.
 */
int kd_jit_control_command(struct kd_jit_control_session *session, unsigned long op,
		const void *input, size_t input_length, void *output,
		size_t output_capacity, size_t *output_length);
/* False while any session cycle, published slot or separate provider controls
 * survive. File close alone cannot discard/unload a pending controller.
 */
bool kd_jit_control_session_idle(struct kd_jit_control_session *session);
/* Provider-serialized metadata collection after exact published retirement.
 * Release code before waiting for late FACT users; -EBUSY retains controls only.
 * No source cursor or execution state is read or restored.
 */
int kd_jit_control_image_collect(struct kd_jit_control_image *image);

#endif
