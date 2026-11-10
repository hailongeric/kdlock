// SPDX-License-Identifier: GPL-2.0-only
/* Exact source-lease users independent of executable image-slot memberships. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/string.h>

#include "source_epoch.h"

static bool span_valid(unsigned long start, size_t length)
{
	/* Inclusive ends also permit a final byte at ULONG_MAX without wrapping. */
	return length && length - 1 <= ~0UL - start;
}

static bool retained_bytes_valid(const void *bytes, size_t length)
{
	return bytes && span_valid((unsigned long)bytes, length);
}

static bool description_valid(const struct kd_jit_source_description *description)
{
	unsigned int index, other;
	size_t array_bytes;

	if (!description || !description->configuration_identity ||
	    !description->load_identity || !description->region_count ||
	    !retained_bytes_valid(description->version, description->version_length) ||
	    (size_t)description->region_count >
			(size_t)-1 / sizeof(*description->regions))
		return false;
	array_bytes = (size_t)description->region_count * sizeof(*description->regions);
	if (!retained_bytes_valid(description->regions, array_bytes))
		return false;
	for (index = 0; index < description->region_count; index++) {
		const struct kd_jit_source_region *region = &description->regions[index];

		if (!span_valid(region->start, region->length) ||
		    !retained_bytes_valid(region->bytes, region->length))
			return false;
	}
	/* Compare only already-retained snapshots, never live kernel text. The
	 * finite caller-supplied region set need not be sorted or nonoverlapping.
	 */
	for (index = 0; index < description->region_count; index++) {
		const struct kd_jit_source_region *region = &description->regions[index];
		unsigned long last = region->start + (region->length - 1);

		for (other = 0; other < index; other++) {
			const struct kd_jit_source_region *previous = &description->regions[other];
			unsigned long previous_last = previous->start + (previous->length - 1);
			unsigned long first, common_last;
			size_t count;

			if (region->start > previous_last || previous->start > last)
				continue;
			first = region->start > previous->start ? region->start : previous->start;
			common_last = last < previous_last ? last : previous_last;
			/* This overlap cannot exceed either validated nonempty region. */
			count = common_last - first + 1;
			if (memcmp(region->bytes + (first - region->start),
				   previous->bytes + (first - previous->start), count))
				return false;
		}
	}
	return true;
}

int kd_jit_source_epoch_init(struct kd_jit_source_epoch *epoch,
		const struct kd_jit_source_description *description,
		void *lease, kd_jit_source_release_fn release)
{
	if (!epoch || !lease || !release || !description_valid(description))
		return -EINVAL;
	/* All fallible checks precede the sole transfer of this existing lease. */
	raw_spin_lock_init(&epoch->guard);
	INIT_LIST_HEAD(&epoch->users);
	epoch->description = *description;
	epoch->lease = lease;
	epoch->release = release;
	epoch->phase = KD_JIT_SOURCE_OPEN;
	return 0;
}

void kd_jit_source_use_init(struct kd_jit_source_use *use)
{
	INIT_LIST_HEAD(&use->epoch_link);
	use->epoch = NULL;
	use->holder = NULL;
	use->kind = KD_JIT_SOURCE_USE_UNUSED;
	use->linked = false;
}

static bool kind_valid(enum kd_jit_source_use_kind kind)
{
	return kind == KD_JIT_SOURCE_USE_BUILD || kind == KD_JIT_SOURCE_USE_IMAGE ||
	       kind == KD_JIT_SOURCE_USE_FEEDBACK || kind == KD_JIT_SOURCE_USE_NATIVE;
}

static int link_use_locked(struct kd_jit_source_epoch *epoch,
		struct kd_jit_source_use *use, const void *holder,
		enum kd_jit_source_use_kind kind)
{
	if (use->epoch || use->linked || !list_empty(&use->epoch_link))
		return -EALREADY;
	use->epoch = epoch;
	use->holder = holder;
	use->kind = kind;
	use->linked = true;
	list_add_tail(&use->epoch_link, &epoch->users);
	return 0;
}

int kd_jit_source_use_get(struct kd_jit_source_epoch *epoch,
		struct kd_jit_source_use *use, const void *holder,
		enum kd_jit_source_use_kind kind)
{
	int result;

	if (!epoch || !use || !holder || !kind_valid(kind))
		return -EINVAL;
	raw_spin_lock(&epoch->guard);
	if (epoch->phase != KD_JIT_SOURCE_OPEN)
		result = -ESHUTDOWN;
	else
		result = link_use_locked(epoch, use, holder, kind);
	raw_spin_unlock(&epoch->guard);
	return result;
}

int kd_jit_source_use_extend(struct kd_jit_source_use *parent,
		const void *parent_holder, struct kd_jit_source_use *child,
		const void *child_holder, enum kd_jit_source_use_kind kind)
{
	struct kd_jit_source_epoch *epoch;
	int result;

	if (!parent || !parent_holder || !child || child == parent ||
	    !child_holder || !kind_valid(kind))
		return -EINVAL;
	epoch = READ_ONCE(parent->epoch);
	if (!epoch)
		return -ESTALE;
	raw_spin_lock(&epoch->guard);
	if (parent->epoch != epoch || !parent->linked ||
	    parent->holder != parent_holder || !kind_valid(parent->kind) ||
	    (epoch->phase != KD_JIT_SOURCE_OPEN && epoch->phase != KD_JIT_SOURCE_CLOSED))
		result = -ESTALE;
	else
		result = link_use_locked(epoch, child, child_holder, kind);
	raw_spin_unlock(&epoch->guard);
	return result;
}

int kd_jit_source_use_put(struct kd_jit_source_use *use, const void *holder)
{
	struct kd_jit_source_epoch *epoch;
	int result = 0;

	if (!use || !holder)
		return -EINVAL;
	epoch = READ_ONCE(use->epoch);
	if (!epoch)
		return -ESTALE;
	raw_spin_lock(&epoch->guard);
	if (use->epoch != epoch || !use->linked || use->holder != holder) {
		result = -ESTALE;
	} else {
		list_del_init(&use->epoch_link);
		use->linked = false;
		use->holder = NULL;
		use->kind = KD_JIT_SOURCE_USE_UNUSED;
		WRITE_ONCE(use->epoch, NULL);
		/* No use or leased payload access follows successful final unlink. */
	}
	raw_spin_unlock(&epoch->guard);
	return result;
}

int kd_jit_source_epoch_close(struct kd_jit_source_epoch *epoch)
{
	int result = 0;

	if (!epoch)
		return -EINVAL;
	raw_spin_lock(&epoch->guard);
	if (epoch->phase == KD_JIT_SOURCE_OPEN)
		epoch->phase = KD_JIT_SOURCE_CLOSED;
	else
		result = -EALREADY;
	raw_spin_unlock(&epoch->guard);
	return result;
}

int kd_jit_source_epoch_try_release(struct kd_jit_source_epoch *epoch)
{
	kd_jit_source_release_fn release;
	void *lease;
	int result = 0;

	if (!epoch)
		return -EINVAL;
	raw_spin_lock(&epoch->guard);
	if (epoch->phase == KD_JIT_SOURCE_RELEASE_CLAIMED)
		result = -EALREADY;
	else if (epoch->phase != KD_JIT_SOURCE_CLOSED || !list_empty(&epoch->users))
		result = -EBUSY;
	else if (!epoch->lease || !epoch->release)
		result = -EUCLEAN;
	if (result) {
		raw_spin_unlock(&epoch->guard);
		return result;
	}
	release = epoch->release;
	lease = epoch->lease;
	epoch->release = NULL;
	epoch->lease = NULL;
	epoch->phase = KD_JIT_SOURCE_RELEASE_CLAIMED;
	raw_spin_unlock(&epoch->guard);

	/* Caller separately retains active header/callback backing through return.
	 * The provider may now release every leased description/payload allocation.
	 */
	release(lease);
	return 0;
}
