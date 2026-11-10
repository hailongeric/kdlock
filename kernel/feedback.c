// SPDX-License-Identifier: GPL-2.0-only
/* Finite copied-exit retention, independent of executable-slot activity. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/overflow.h>

#include "feedback.h"

static bool has_image_locked(struct kd_jit_feedback_producer *producer)
{
	struct kd_jit_feedback_producer_use *use;

	list_for_each_entry(use, &producer->users, link)
		if (use->kind == KD_JIT_FEEDBACK_PRODUCER_IMAGE)
			return true;
	return false;
}

void kd_jit_feedback_producer_use_init(struct kd_jit_feedback_producer_use *use)
{
	INIT_LIST_HEAD(&use->link);
	use->producer = NULL;
	use->holder = NULL;
	use->kind = KD_JIT_FEEDBACK_PRODUCER_FACT;
	use->linked = false;
}

int kd_jit_feedback_producer_init(struct kd_jit_feedback_producer *producer,
		const void *identity, const struct kd_jit_image *image,
		struct kd_jit_source_use *build, const void *build_holder)
{
	struct kd_jit_source_epoch *epoch;
	bool valid;
	int result;

	if (!producer || !identity || !image || image->feedback_producer != producer ||
	    !build || build == &producer->source_use || !build_holder)
		return -EINVAL;
	epoch = READ_ONCE(build->epoch);
	if (!epoch)
		return -ESTALE;
	raw_spin_lock(&epoch->guard);
	valid = build->linked && build->epoch == epoch && build->holder == build_holder &&
		build->kind == KD_JIT_SOURCE_USE_BUILD && image->source_identity == epoch;
	raw_spin_unlock(&epoch->guard);
	if (!valid)
		return -ESTALE;
	kd_jit_source_use_init(&producer->source_use);
	result = kd_jit_source_use_extend(build, build_holder, &producer->source_use,
					 producer, KD_JIT_SOURCE_USE_FEEDBACK);
	if (result)
		return result;
	raw_spin_lock_init(&producer->guard);
	INIT_LIST_HEAD(&producer->users);
	producer->identity = identity;
	producer->image_identity = (unsigned long)image;
	producer->closed = false;
	producer->released = false;
	return 0;
}

int kd_jit_feedback_producer_use_get(struct kd_jit_feedback_producer *producer,
		struct kd_jit_feedback_producer_use *use, const void *holder,
		enum kd_jit_feedback_producer_use_kind kind,
		const struct kd_jit_image *image)
{
	int result = 0;

	if (!producer || !use || !holder || !image ||
	    (kind != KD_JIT_FEEDBACK_PRODUCER_IMAGE && kind != KD_JIT_FEEDBACK_PRODUCER_FACT))
		return -EINVAL;
	raw_spin_lock(&producer->guard);
	if (use->linked || use->producer)
		result = -EBUSY;
	else if (producer->closed || producer->released ||
		 producer->image_identity != (unsigned long)image ||
		 image->feedback_producer != producer ||
		 image->source_identity != producer->source_use.epoch ||
		 (kind == KD_JIT_FEEDBACK_PRODUCER_FACT && !has_image_locked(producer)))
		result = -ESTALE;
	else {
		use->producer = producer;
		use->holder = holder;
		use->kind = kind;
		use->linked = true;
		list_add_tail(&use->link, &producer->users);
	}
	raw_spin_unlock(&producer->guard);
	return result;
}

int kd_jit_feedback_producer_use_put(struct kd_jit_feedback_producer_use *use,
		const void *holder)
{
	struct kd_jit_feedback_producer *producer;
	int result = 0;

	if (!use || !holder)
		return -EINVAL;
	producer = READ_ONCE(use->producer);
	if (!producer)
		return -ESTALE;
	raw_spin_lock(&producer->guard);
	if (!use->linked || use->producer != producer || use->holder != holder)
		result = -ESTALE;
	else {
		list_del_init(&use->link);
		use->linked = false;
		use->producer = NULL;
		use->holder = NULL;
	}
	raw_spin_unlock(&producer->guard);
	return result;
}

int kd_jit_feedback_producer_close(struct kd_jit_feedback_producer *producer)
{
	int result = 0;

	if (!producer)
		return -EINVAL;
	raw_spin_lock(&producer->guard);
	if (producer->released)
		result = -EALREADY;
	else if (has_image_locked(producer))
		result = -EBUSY;
	else
		producer->closed = true;
	raw_spin_unlock(&producer->guard);
	return result;
}

int kd_jit_feedback_producer_release(struct kd_jit_feedback_producer *producer)
{
	int result = 0;

	if (!producer)
		return -EINVAL;
	raw_spin_lock(&producer->guard);
	if (producer->released)
		result = -EALREADY;
	else if (!producer->closed || !list_empty(&producer->users))
		result = -EBUSY;
	else
		producer->released = true;
	raw_spin_unlock(&producer->guard);
	if (result)
		return result;
	/* Independent control backing outlives this final API return. */
	return kd_jit_source_use_put(&producer->source_use, producer);
}

int kd_jit_feedback_pool_init(struct kd_jit_feedback_pool *pool,
		struct kd_jit_feedback_record *records, unsigned int capacity)
{
	unsigned long low = (unsigned long)records, high, pool_high;
	size_t bytes;
	unsigned int index;

	if (!pool || !records || !capacity ||
	    (unsigned long)pool % __alignof__(*pool) || low % __alignof__(*records))
		return -EINVAL;
	if (check_mul_overflow((size_t)capacity, sizeof(*records), &bytes) ||
	    check_add_overflow(low, (unsigned long)bytes, &high) ||
	    check_add_overflow((unsigned long)pool, sizeof(*pool), &pool_high))
		return -EOVERFLOW;
	if (low < pool_high && (unsigned long)pool < high)
		return -EINVAL;
	raw_spin_lock_init(&pool->guard);
	INIT_LIST_HEAD(&pool->free);
	INIT_LIST_HEAD(&pool->pending);
	pool->records = records;
	pool->capacity = capacity;
	for (index = 0; index < capacity; ++index) {
		struct kd_jit_feedback_record *record = &records[index];

		record->pool = pool;
		record->claim = NULL;
		record->phase = KD_JIT_FEEDBACK_FREE;
		record->incarnation = 0;
		kd_jit_feedback_producer_use_init(&record->producer_use);
		kd_jit_source_use_init(&record->source_use);
		list_add_tail(&record->link, &pool->free);
	}
	return 0;
}

static void recycle(struct kd_jit_feedback_record *record)
{
	struct kd_jit_feedback_pool *pool = record->pool;

	raw_spin_lock(&pool->guard);
	record->claim = NULL;
	record->phase = KD_JIT_FEEDBACK_FREE;
	list_add_tail(&record->link, &pool->free);
	raw_spin_unlock(&pool->guard);
	/* No record access after it becomes reservable. */
}

int kd_jit_feedback_record_exit(struct kd_jit_feedback_pool *pool,
		const struct kd_jit_image *image, unsigned long cursor,
		int entry_result, const struct kd_jit_io *io,
		enum kd_jit_feedback_target_class classification)
{
	struct kd_jit_feedback_producer *producer;
	struct kd_jit_feedback_record *record;
	struct kd_jit_source_epoch *epoch;
	int result, drop;

	if (!pool || !image || !io || io->kind != KD_JIT_EXIT_COVERAGE_MISS ||
	    !image->feedback_producer ||
	    (classification != KD_JIT_FEEDBACK_UNCLASSIFIED &&
	     classification != KD_JIT_FEEDBACK_ORDINARY && classification != KD_JIT_FEEDBACK_SOURCE_API))
		return -EINVAL;
	producer = image->feedback_producer;
	raw_spin_lock(&pool->guard);
	if (list_empty(&pool->free)) {
		raw_spin_unlock(&pool->guard);
		return -ENOSPC;
	}
	record = list_first_entry(&pool->free, struct kd_jit_feedback_record, link);
	if (record->incarnation == ~0UL) {
		raw_spin_unlock(&pool->guard);
		return -EOVERFLOW;
	}
	++record->incarnation;
	list_del_init(&record->link);
	record->phase = KD_JIT_FEEDBACK_RECORDING;
	raw_spin_unlock(&pool->guard);
	result = kd_jit_feedback_producer_use_get(producer, &record->producer_use,
			record, KD_JIT_FEEDBACK_PRODUCER_FACT, image);
	if (result)
		goto unused;
	result = kd_jit_source_use_extend(&producer->source_use, producer,
		&record->source_use, record, KD_JIT_SOURCE_USE_FEEDBACK);
	if (result) {
		drop = kd_jit_feedback_producer_use_put(&record->producer_use, record);
		if (drop)
			return drop;
		goto unused;
	}
	epoch = record->source_use.epoch;
	record->fact.identity = &record->identity;
	record->fact.incarnation = record->incarnation;
	record->fact.producer_identity = producer->identity;
	record->fact.producer_image_identity = producer->image_identity;
	record->fact.epoch = epoch;
	record->fact.version = epoch->description.version;
	record->fact.version_length = epoch->description.version_length;
	record->fact.kind = io->kind;
	record->fact.detail = io->detail;
	record->fact.source_ip = io->source_ip;
	record->fact.target = io->target;
	record->fact.cursor = cursor;
	record->fact.phase = io->phase;
	record->fact.classification = classification;
	record->fact.entry_result = entry_result;
	raw_spin_lock(&pool->guard);
	record->phase = KD_JIT_FEEDBACK_PENDING;
	list_add_tail(&record->link, &pool->pending);
	raw_spin_unlock(&pool->guard);
	return 0;
unused:
	recycle(record);
	return result;
}

void kd_jit_feedback_claim_init(struct kd_jit_feedback_claim *claim)
{
	claim->pool = NULL;
	claim->epoch = NULL;
	claim->items = NULL;
	claim->count = 0;
	claim->next = 0;
	claim->holder = NULL;
	claim->linked = false;
	claim->ending = false;
}

int kd_jit_feedback_claim_begin(struct kd_jit_feedback_pool *pool,
		struct kd_jit_source_epoch *epoch, struct kd_jit_feedback_claim *claim,
		struct kd_jit_feedback_claim_item *items, unsigned int capacity,
		const void *holder)
{
	struct kd_jit_feedback_record *record;
	unsigned int count = 0;

	if (!pool || !epoch || !claim || !items || !capacity || !holder)
		return -EINVAL;
	raw_spin_lock(&pool->guard);
	if (claim->linked || claim->pool) {
		raw_spin_unlock(&pool->guard);
		return -EBUSY;
	}
	list_for_each_entry(record, &pool->pending, link) {
		if (record->phase != KD_JIT_FEEDBACK_PENDING || record->claim || record->fact.epoch != epoch)
			continue;
		items[count].record = record;
		items[count].identity = record->fact.identity;
		items[count].incarnation = record->fact.incarnation;
		record->claim = claim;
		if (++count == capacity)
			break;
	}
	claim->pool = pool;
	claim->epoch = epoch;
	claim->items = items;
	claim->count = count;
	claim->next = 0;
	claim->holder = holder;
	claim->linked = true;
	raw_spin_unlock(&pool->guard);
	return 0;
}

static bool member_locked(struct kd_jit_feedback_claim *claim,
		const struct kd_jit_feedback_claim_item *item, bool pending_only)
{
	struct kd_jit_feedback_record *record;
	unsigned int index;

	/* Find exact retained membership before dereferencing an input record. */
	for (index = 0; index < claim->count; ++index)
		if (claim->items[index].record == item->record &&
		    claim->items[index].identity == item->identity &&
		    claim->items[index].incarnation == item->incarnation)
			break;
	if (index == claim->count)
		return false;
	record = claim->items[index].record;
	return record->pool == claim->pool && record->claim == claim &&
		record->fact.identity == item->identity &&
		record->fact.incarnation == item->incarnation && record->fact.epoch == claim->epoch &&
		(record->phase == KD_JIT_FEEDBACK_PENDING ||
		 (!pending_only && (record->phase == KD_JIT_FEEDBACK_ACKNOWLEDGED ||
				 record->phase == KD_JIT_FEEDBACK_SETTLED)));
}

static int check_locked(struct kd_jit_feedback_claim *claim, const void *holder,
		const struct kd_jit_feedback_claim_item *items, unsigned int count,
		bool pending_only)
{
	unsigned int index, other;

	if (!claim->linked || claim->ending || claim->holder != holder || count > claim->count)
		return -ESTALE;
	for (index = 0; index < count; ++index) {
		if (!member_locked(claim, &items[index], pending_only))
			return -ESTALE;
		for (other = 0; other < index; ++other)
			if (items[index].record == items[other].record)
				return -EINVAL;
	}
	return 0;
}

int kd_jit_feedback_claim_check(struct kd_jit_feedback_claim *claim,
		const void *holder, const struct kd_jit_feedback_claim_item *items,
		unsigned int count)
{
	struct kd_jit_feedback_pool *pool;
	int result;

	if (!claim || !holder || (count && !items))
		return -EINVAL;
	pool = READ_ONCE(claim->pool);
	if (!pool)
		return -ESTALE;
	raw_spin_lock(&pool->guard);
	result = check_locked(claim, holder, items, count, false);
	raw_spin_unlock(&pool->guard);
	return result;
}

int kd_jit_feedback_claim_ack(struct kd_jit_feedback_claim *claim,
		const void *holder, const struct kd_jit_feedback_claim_item *items,
		unsigned int count)
{
	struct kd_jit_feedback_pool *pool;
	unsigned int index;
	int result;

	if (!claim || !holder || (count && !items))
		return -EINVAL;
	pool = READ_ONCE(claim->pool);
	if (!pool)
		return -ESTALE;
	raw_spin_lock(&pool->guard);
	result = check_locked(claim, holder, items, count, true);
	if (!result)
		for (index = 0; index < count; ++index)
			items[index].record->phase = KD_JIT_FEEDBACK_ACKNOWLEDGED;
	raw_spin_unlock(&pool->guard);
	return result;
}

int kd_jit_feedback_claim_end(struct kd_jit_feedback_claim *claim,
		const void *holder)
{
	struct kd_jit_feedback_pool *pool;
	unsigned int index;
	int result;

	if (!claim || !holder)
		return -EINVAL;
	pool = READ_ONCE(claim->pool);
	if (!pool || !claim->linked || claim->holder != holder)
		return -ESTALE;
	claim->ending = true;
	/* Caller has ended all publication, compiler and transport observers.
	 * No other operation on this claim may run until this call returns.
	 */
	for (index = claim->next; index < claim->count; ++index) {
		struct kd_jit_feedback_record *record = claim->items[index].record;

		raw_spin_lock(&pool->guard);
		if (record->claim != claim || record->fact.identity != claim->items[index].identity ||
		    record->fact.incarnation != claim->items[index].incarnation) {
			raw_spin_unlock(&pool->guard);
			return -ESTALE;
		}
		if (record->phase == KD_JIT_FEEDBACK_PENDING) {
			claim->next = index + 1;
			record->claim = NULL;
			raw_spin_unlock(&pool->guard);
			continue;
		}
		if (record->phase == KD_JIT_FEEDBACK_ACKNOWLEDGED ||
		    record->phase == KD_JIT_FEEDBACK_SETTLED) {
			record->phase = KD_JIT_FEEDBACK_RELEASING;
			list_del_init(&record->link);
		} else if (record->phase != KD_JIT_FEEDBACK_RELEASING) {
			raw_spin_unlock(&pool->guard);
			return -ESTALE;
		}
		raw_spin_unlock(&pool->guard);
		if (record->source_use.linked) {
			result = kd_jit_source_use_put(&record->source_use, record);
			if (result)
				return result;
		}
		if (record->producer_use.linked) {
			result = kd_jit_feedback_producer_use_put(&record->producer_use, record);
			if (result)
				return result;
		}
		claim->next = index + 1;
		recycle(record);
	}
	kd_jit_feedback_claim_init(claim);
	return 0;
}

void kd_jit_feedback_settlement_init(struct kd_jit_feedback_settlement *receipt)
{
	receipt->identity = NULL;
	receipt->archive = NULL;
	receipt->claim = NULL;
	receipt->claim_holder = NULL;
	receipt->items = NULL;
	receipt->count = 0;
}

static bool source_shutdown_ready(struct kd_jit_source_epoch *epoch)
{
	struct kd_jit_source_use *use;
	bool ready = true;

	raw_spin_lock(&epoch->guard);
	if (epoch->phase != KD_JIT_SOURCE_CLOSED)
		ready = false;
	list_for_each_entry(use, &epoch->users, epoch_link)
		if (use->kind != KD_JIT_SOURCE_USE_FEEDBACK) {
			ready = false;
			break;
		}
	raw_spin_unlock(&epoch->guard);
	return ready;
}

int kd_jit_feedback_claim_settle(struct kd_jit_feedback_claim *claim,
		const void *holder, const struct kd_jit_feedback_archive *archive,
		struct kd_jit_feedback_settlement *receipt)
{
	struct kd_jit_feedback_pool *pool;
	unsigned int index;
	int result;

	if (!claim || !holder || !archive || !receipt || archive->claim != claim ||
	    archive->claim_holder != holder || archive->epoch != claim->epoch ||
	    (archive->count && !archive->items))
		return -EINVAL;
	if (receipt->identity)
		return receipt->identity == receipt && receipt->archive == archive &&
		       receipt->claim == claim && receipt->claim_holder == holder ? 0 : -ESTALE;
	result = kd_jit_feedback_claim_check(claim, holder, archive->items, archive->count);
	if (result)
		return result;
	if (!source_shutdown_ready(archive->epoch))
		return -EBUSY;
	for (index = 0; index < archive->count; ++index) {
		struct kd_jit_feedback_producer *producer =
			archive->items[index].record->producer_use.producer;
		bool closed;

		if (!producer)
			return -ESTALE;
		raw_spin_lock(&producer->guard);
		closed = producer->closed && !producer->released && !has_image_locked(producer);
		raw_spin_unlock(&producer->guard);
		if (!closed)
			return -EBUSY;
	}
	pool = claim->pool;
	raw_spin_lock(&pool->guard);
	result = check_locked(claim, holder, archive->items, archive->count, true);
	if (!result)
		for (index = 0; index < archive->count; ++index)
			archive->items[index].record->phase = KD_JIT_FEEDBACK_SETTLED;
	raw_spin_unlock(&pool->guard);
	if (result)
		return result;
	receipt->archive = archive;
	receipt->claim = claim;
	receipt->claim_holder = holder;
	receipt->items = archive->items;
	receipt->count = archive->count;
	receipt->identity = receipt;
	return 0;
}
