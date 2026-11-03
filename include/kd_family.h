/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_FAMILY_H
#define KD_FAMILY_H

#include <linux/list.h>
#include <linux/spinlock.h>
#include <linux/types.h>

/* Per-root decoded-source cache. These are instruction bytes and metadata,
 * not executable JIT images. Capacity never controls public acquisition. */
#define KD_FAMILY_CACHE_ENTRIES 16U
#define KD_FAMILY_INSN_BYTES 15U

enum kd_family_state {
	KD_FAMILY_ACTIVE,
	KD_FAMILY_DRAINING,
	KD_FAMILY_RETIRED,
};

enum kd_family_artifact_kind {
	KD_FAMILY_ARTIFACT_NONE,
	KD_FAMILY_ARTIFACT_KD_CALL,
	KD_FAMILY_ARTIFACT_NATIVE_CALL,
	KD_FAMILY_ARTIFACT_MEMORY,
};

struct kd_family;

/* Each live owner has a concrete retained reference node. References may
 * retire in any order; a count is never the ownership authority. */
struct kd_family_ref {
	struct list_head link;
	struct kd_family *family;
	u64 family_generation;
	const void *request_identity;
	u64 request_generation;
	u64 sequence;
	bool held;
};

struct kd_family_instruction {
	unsigned long source_ip;
	u64 generation;
	u8 length;
	u8 bytes[KD_FAMILY_INSN_BYTES];
};

struct kd_family {
	raw_spinlock_t guard;
	struct list_head references;
	const void *identity;
	u64 generation;
	u64 source_epoch;
	unsigned long entry_ip;
	unsigned int entry_abi;
	unsigned int state;
	unsigned int cached;
	u64 cache_hits;
	u64 cache_misses;
	struct kd_family_instruction instructions[KD_FAMILY_CACHE_ENTRIES];
};

/* The service owns this record until its actual completion ACK. The fifteen
 * source bytes are immutable instruction metadata, never a packet/stack copy.
 * Even when the optional cache is full, this record retains the exact bytes. */
struct kd_family_artifact {
	struct kd_family_ref reference;
	unsigned long source_ip;
	u64 source_epoch;
	u64 sequence;
	unsigned int kind;
	u8 length;
	u8 bytes[KD_FAMILY_INSN_BYTES];
};

/* Initialization is allowed only for fresh or completely retired storage.
 * The caller already owns a source/task-stack lease for this exact request.
 * The source session cannot reopen; its root request generation is the epoch. */
int kd_family_init(struct kd_family *family, const void *identity,
	u64 generation, u64 source_epoch, unsigned long entry_ip,
	unsigned int entry_abi);
void kd_family_ref_init(struct kd_family_ref *reference);
int kd_family_ref_get(struct kd_family *family,
	struct kd_family_ref *reference, const struct kd_family_ref *parent,
	const void *request_identity, u64 request_generation, u64 sequence);
int kd_family_ref_put(struct kd_family_ref *reference);
bool kd_family_ref_valid(const struct kd_family_ref *reference);
int kd_family_begin_retire(struct kd_family *family, const void *identity,
	u64 generation);
int kd_family_finish_retire(struct kd_family *family, const void *identity,
	u64 generation);
unsigned int kd_family_live_refs(struct kd_family *family);

/* Callers must freshly retain/read the complete reached instruction before
 * lookup; cached bytes alone are never source freshness or residency proof.
 * Returned records remain immutable while the authority reference is held.
 * A NULL lookup/publication leaves allocation-independent cold execution. */
const struct kd_family_instruction *kd_family_cache_find(
	const struct kd_family_ref *authority, unsigned long source_ip,
	const u8 *observed, unsigned int length);
const struct kd_family_instruction *kd_family_cache_publish(
	const struct kd_family_ref *authority, unsigned long source_ip,
	const u8 *observed, unsigned int length);

void kd_family_artifact_init(struct kd_family_artifact *artifact);
int kd_family_artifact_get(struct kd_family_artifact *artifact,
	const struct kd_family_ref *parent, unsigned int kind,
	unsigned long source_ip, const u8 *bytes, unsigned int length,
	u64 sequence);
/* parent is an optional retained-identity comparison, not the artifact's
 * lifetime authority. Its reference can retire first; the artifact owns its
 * own concrete family reference until the completion ACK. */
bool kd_family_artifact_valid(const struct kd_family_artifact *artifact,
	const struct kd_family_ref *parent, u64 sequence);
int kd_family_artifact_put(struct kd_family_artifact *artifact);

#endif
