// SPDX-License-Identifier: GPL-2.0-only
/* Concrete finite compiler runtime over immutable source and executable images. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/overflow.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <asm/cpufeature.h>

#include "runtime.h"
#include "mutex_api.h"
#include "episode.h"
#include "lifecycle.h"

struct runtime_cycle {
	struct kd_jit_control_storage storage;
	struct kd_jit_feedback_archive archive;
	struct kd_jit_feedback_settlement settlement;
	bool used;
	bool active;
	bool archival;
};

struct runtime_native {
	struct list_head link;
	struct kd_jit_runtime *runtime;
	void *source_lease;
};

struct kd_jit_runtime {
	struct kd_jit_runtime_config config;
	struct kd_jit_feedback_pool feedback;
	struct kd_jit_feedback_record *records;
	struct kd_jit_image_slot slot;
	struct kd_jit_control_session session;
	struct kd_jit_channel channel;
	struct kd_task_lifecycle_context lifecycle;
	struct runtime_cycle *cycles;
	struct kd_jit_feedback_claim_item *items;
	struct kd_jit_compiled_image **images;
	bool *private_released;
	struct kd_jit_control_image *published_image;
	unsigned int cycles_used;
	unsigned int images_used;
	struct kd_jit_source_use source_hold;
	struct kd_jit_source_use feedback_hold;
	bool source_live;
	bool feedback_live;
	bool closing;
	bool shutdown_complete;
	bool channel_live;
	raw_spinlock_t native_guard;
	struct list_head native_users;
	struct kd_jit_image_update shutdown_update;
	struct kd_jit_image_owner_use shutdown_baseline;
	struct kd_jit_control_image *shutdown_old;
	const struct kd_jit_image *shutdown_retired;
	bool shutdown_baseline_live;
	bool shutdown_started;
	bool shutdown_prepared;
	bool shutdown_committed;
	bool shutdown_finished;
};

static int extension(void *context, struct kd_jit_control_session *session,
		unsigned long op, const void *input, size_t input_length,
		void *output, size_t output_capacity, size_t *output_length);

static struct runtime_cycle *cycle_of(struct kd_jit_control_storage *storage)
{
	return container_of(storage, struct runtime_cycle, storage);
}

static int allocate_cycle(void *context, struct kd_jit_control_storage **out)
{
	struct kd_jit_runtime *runtime = context;
	struct runtime_cycle *cycle;

	if (runtime->cycles_used >= runtime->config.cycle_capacity)
		return -ENOSPC;
	cycle = &runtime->cycles[runtime->cycles_used++];
	cycle->used = true;
	cycle->active = true;
	*out = &cycle->storage;
	return 0;
}

static void collect_images(struct kd_jit_runtime *runtime)
{
	unsigned int index;

	for (index = 0; index < runtime->images_used; ++index) {
		struct kd_jit_control_image *image;

		if (!runtime->images[index])
			continue;
		image = kd_jit_compiled_image_control(runtime->images[index]);

		if (!image->published_live && image->owner_initialized)
			kd_jit_control_image_collect(image);
	}
}

static void release_cycle(void *context, struct kd_jit_control_storage *storage)
{
	struct kd_jit_runtime *runtime = context;
	unsigned int index;

	/* Controller addresses remain reserved until final host-history shutdown. */
	if (storage->reserved && !storage->candidate.control->owner_initialized &&
	    !storage->candidate.code_lease)
		for (index = 0; index < runtime->images_used; ++index)
			if (kd_jit_compiled_image_control(runtime->images[index]) == storage->candidate.control)
				runtime->private_released[index] = true;
	cycle_of(storage)->active = false;
	collect_images(runtime);
}

static struct kd_jit_control_image *current_image(void *context, struct kd_jit_image_slot *slot)
{
	struct kd_jit_runtime *runtime = context;

	return slot == &runtime->slot ? runtime->published_image : NULL;
}

static int reserve_image(void *context, struct kd_jit_source_epoch *epoch,
		struct kd_jit_control_candidate *candidate)
{
	struct kd_jit_runtime *runtime = context;
	struct kd_jit_compiled_image *image;
	int result;

	if (READ_ONCE(runtime->closing) || epoch != &runtime->config.source->epoch)
		return -ESHUTDOWN;
	if (runtime->images_used >= runtime->config.image_capacity)
		return -ENOSPC;
	result = kd_jit_compiled_image_reserve(epoch, &runtime->config.compiled,
		&runtime->config.symbols, &image, candidate);
	if (result)
		return result;
	runtime->images[runtime->images_used++] = image;
	return 0;
}

static int load_image(void *context, const struct kd_jit_control_candidate *candidate,
		const struct kd_jit_control_bytes *assembly, const struct kd_jit_control_bytes *metadata,
		const struct kd_jit_control_bytes *manifest, const struct kd_jit_control_bytes *machine,
		const struct kd_jit_control_bytes *flat)
{
	struct kd_jit_runtime *runtime = context;
	unsigned int index;

	if (READ_ONCE(runtime->closing))
		return -ESHUTDOWN;
	for (index = 0; index < runtime->images_used; ++index)
		if (kd_jit_compiled_image_control(runtime->images[index]) == candidate->control)
			return kd_jit_compiled_image_load(runtime->images[index], assembly, metadata,
				manifest, machine, flat);
	return -ESTALE;
}

static void published_image(void *context, struct kd_jit_image_slot *slot,
		struct kd_jit_control_image *old, struct kd_jit_control_image *candidate)
{
	struct kd_jit_runtime *runtime = context;

	(void)slot;
	(void)old;
	runtime->published_image = candidate;
}

static void retired_image(void *context, struct kd_jit_control_image *old)
{
	(void)context;
	/* Code is released first; late FACT users keep only durable source controls. */
	kd_jit_control_image_collect(old);
}

static bool native_empty(struct kd_jit_runtime *runtime)
{
	bool empty;

	raw_spin_lock(&runtime->native_guard);
	empty = list_empty(&runtime->native_users);
	raw_spin_unlock(&runtime->native_guard);
	return empty;
}

static bool runtime_idle(void *context)
{
	struct kd_jit_runtime *runtime = context;
	unsigned int index;
	bool pending;

	if (!runtime->shutdown_complete || runtime->source_live || !native_empty(runtime))
		return false;
	for (index = 0; index < runtime->cycles_used; ++index)
		if (runtime->cycles[index].active)
			return false;
	for (index = 0; index < runtime->images_used; ++index) {
		struct kd_jit_control_image *image;

		if (!runtime->images[index])
			continue;
		image = kd_jit_compiled_image_control(runtime->images[index]);

		if (image->published_live ||
		    (image->owner_initialized ? !image->owner_released : !runtime->private_released[index]) ||
		    (image->producer_initialized && !image->producer_released))
			return false;
	}
	raw_spin_lock(&runtime->feedback.guard);
	pending = !list_empty(&runtime->feedback.pending);
	raw_spin_unlock(&runtime->feedback.guard);
	return !pending;
}

static int admit_publish(void *context)
{
	struct kd_jit_runtime *runtime = context;

	return READ_ONCE(runtime->closing) ? -ESHUTDOWN : 0;
}

static const struct kd_jit_control_provider_ops provider_ops = {
	.allocate = allocate_cycle, .release = release_cycle, .get_published = current_image,
	.reserve = reserve_image, .load = load_image, .published = published_image,
	.retired = retired_image, .idle = runtime_idle, .admit_publish = admit_publish,
	.command = extension,
};

static enum kd_jit_feedback_target_class classify_target(void *context, unsigned long target)
{
	struct kd_jit_runtime *runtime = context;
	const struct kd_jit_source_description *source = &runtime->config.source->epoch.description;
	unsigned int index;

	if (kd_mutex_resolve_entry_operation(NULL, target) != KD_OPERATION_NONE)
		return KD_JIT_FEEDBACK_SOURCE_API;
	for (index = 0; index < runtime->config.boundary_count; ++index)
		if (target == runtime->config.boundaries[index].site)
			return runtime->config.boundaries[index].kind == KD_JIT_RUNTIME_SPECIAL ?
				KD_JIT_FEEDBACK_UNCLASSIFIED : KD_JIT_FEEDBACK_SOURCE_API;
	for (index = 0; index < source->region_count; ++index)
		if (target >= source->regions[index].start &&
		    target - source->regions[index].start < source->regions[index].length)
			return KD_JIT_FEEDBACK_ORDINARY;
	return KD_JIT_FEEDBACK_UNCLASSIFIED;
}

static void report_exit(void *context, const struct kd_jit_image *image,
		unsigned long source_ip, int result, const struct kd_jit_io *io)
{
	/* Automatic retained facts are recorded by episode.c for coverage misses.
	 * Other typed exits keep their existing immediate handback, without a claim
	 * that this pool records every possible exit or completion.
	 */
	(void)context; (void)image; (void)source_ip; (void)result; (void)io;
}

void kd_jit_runtime_native_release(void *lease)
{
	struct runtime_native *native = lease;
	struct kd_jit_runtime *runtime = native->runtime;

	kd_jit_source_native_release(native->source_lease);
	raw_spin_lock(&runtime->native_guard);
	list_del(&native->link);
	raw_spin_unlock(&runtime->native_guard);
	/* No runtime/source access after the final exact runtime user is unlinked. */
	kfree(native);
}

int kd_jit_runtime_native_begin(void *context, void **lease)
{
	struct kd_jit_runtime *runtime = context;
	struct runtime_native *native;
	int result;

	if (!runtime || !lease)
		return -EINVAL;
	*lease = NULL;
	if (READ_ONCE(runtime->closing))
		return -ESHUTDOWN;
	native = kmalloc(sizeof(*native), GFP_KERNEL);
	if (!native)
		return -ENOMEM;
	result = kd_jit_source_native_begin(runtime->config.source, &native->source_lease);
	if (result) {
		kfree(native);
		return result;
	}
	native->runtime = runtime;
	raw_spin_lock(&runtime->native_guard);
	if (READ_ONCE(runtime->closing)) {
		raw_spin_unlock(&runtime->native_guard);
		kd_jit_source_native_release(native->source_lease);
		kfree(native);
		return -ESHUTDOWN;
	}
	list_add_tail(&native->link, &runtime->native_users);
	raw_spin_unlock(&runtime->native_guard);
	*lease = native;
	return 0;
}

int kd_jit_runtime_episode_config(struct kd_jit_runtime *runtime, struct kd_episode_config *config)
{
	if (!runtime || !config)
		return -EINVAL;
	*config = (struct kd_episode_config) {
		.image_slot = &runtime->slot, .feedback = &runtime->feedback, .stack = NULL,
		.resolve = kd_mutex_resolve_entry_operation, .resolve_context = NULL,
		.classify_target = classify_target, .classify_context = runtime,
		.proxy_limit = runtime->config.proxy_limit, .report = report_exit, .report_context = runtime,
	};
	return 0;
}

int kd_jit_runtime_enter_current(struct kd_jit_runtime *runtime,
		unsigned long origin_gs, struct kd_task_storage **storage)
{
	if (!runtime || !storage)
		return -EINVAL;
	return kd_task_lifecycle_start_current(&runtime->lifecycle, origin_gs, storage);
}

int kd_jit_runtime_leave_current(struct kd_task_storage *storage,
		struct kd_execution_binding *expected_native, bool *pending)
{
	return kd_task_storage_stop_current(storage, expected_native, pending);
}

int kd_jit_runtime_create(const struct kd_jit_runtime_config *config,
		struct kd_jit_runtime **out)
{
	struct kd_jit_runtime *runtime;
	struct kd_episode_config episode;
	size_t cells, total;
	unsigned int index, other;
	int result;

	if (!config || !out || !config->source || !config->feedback_capacity ||
	    !config->cycle_capacity || !config->image_capacity || !config->claim_capacity ||
	    !config->channel_name || !config->frame_capacity || !config->request_capacity ||
	    !config->auxiliary_bytes || !config->required_control_bytes ||
	    (config->boundary_count && !config->boundaries))
		return -EINVAL;
	*out = NULL;
	/* The active call-depth return thunk changes native-escape flags. */
	if (cpu_feature_enabled(X86_FEATURE_CALL_DEPTH))
		return -EOPNOTSUPP;
	if (check_mul_overflow((size_t)config->cycle_capacity, (size_t)config->claim_capacity, &cells) ||
	    check_mul_overflow(cells, (size_t)3, &total))
		return -EOVERFLOW;
	for (index = 0; index < config->boundary_count; ++index) {
		if (config->boundaries[index].kind < KD_JIT_RUNTIME_LOCK ||
		    config->boundaries[index].kind > KD_JIT_RUNTIME_SPECIAL)
			return -EINVAL;
		if ((config->boundaries[index].site == (unsigned long)kd_mutex_lock_entry_asm &&
		     config->boundaries[index].kind != KD_JIT_RUNTIME_LOCK) ||
		    (config->boundaries[index].site == (unsigned long)kd_mutex_unlock_entry_asm &&
		     config->boundaries[index].kind != KD_JIT_RUNTIME_UNLOCK))
			return -EINVAL;
		for (other = 0; other < index; ++other)
			if (config->boundaries[other].site == config->boundaries[index].site)
				return -EINVAL;
	}
	runtime = kzalloc(sizeof(*runtime), GFP_KERNEL);
	if (!runtime)
		return -ENOMEM;
	runtime->config = *config;
	/* Cold arrays need stable virtual storage, not contiguous physical pages. */
	runtime->records = kvcalloc(config->feedback_capacity, sizeof(*runtime->records), GFP_KERNEL);
	runtime->cycles = kvcalloc(config->cycle_capacity, sizeof(*runtime->cycles), GFP_KERNEL);
	runtime->items = kvcalloc(total, sizeof(*runtime->items), GFP_KERNEL);
	runtime->images = kvcalloc(config->image_capacity, sizeof(*runtime->images), GFP_KERNEL);
	runtime->private_released = kvcalloc(config->image_capacity, sizeof(*runtime->private_released), GFP_KERNEL);
	if (!runtime->records || !runtime->cycles || !runtime->items || !runtime->images || !runtime->private_released) {
		result = -ENOMEM;
		goto free;
	}
	raw_spin_lock_init(&runtime->native_guard);
	INIT_LIST_HEAD(&runtime->native_users);
	kd_jit_source_use_init(&runtime->source_hold);
	kd_jit_source_use_init(&runtime->feedback_hold);
	kd_jit_image_update_init(&runtime->shutdown_update);
	kd_jit_image_owner_use_init(&runtime->shutdown_baseline);
	for (index = 0; index < config->cycle_capacity; ++index)
		kd_jit_control_storage_init(&runtime->cycles[index].storage,
			&runtime->items[(size_t)index * config->claim_capacity],
			&runtime->items[cells + (size_t)index * config->claim_capacity],
			&runtime->items[2 * cells + (size_t)index * config->claim_capacity], config->claim_capacity);
	result = kd_jit_feedback_pool_init(&runtime->feedback, runtime->records, config->feedback_capacity);
	if (result)
		goto free;
	kd_jit_image_slot_init(&runtime->slot, NULL);
	result = kd_jit_source_use_get(&config->source->epoch, &runtime->source_hold,
		runtime, KD_JIT_SOURCE_USE_BUILD);
	if (result)
		goto free;
	runtime->source_live = true;
	result = kd_jit_source_use_get(&config->source->epoch, &runtime->feedback_hold,
		runtime, KD_JIT_SOURCE_USE_FEEDBACK);
	if (result)
		goto drop;
	runtime->feedback_live = true;
	result = kd_jit_control_session_init(&runtime->session, &runtime->feedback,
		&config->source->epoch, &runtime->slot, &provider_ops, runtime);
	if (result)
		goto drop;
	result = kd_jit_runtime_episode_config(runtime, &episode);
	if (result)
		goto drop;
	result = kd_task_lifecycle_context_init(&runtime->lifecycle, &episode,
		config->request_capacity, config->auxiliary_bytes, config->required_control_bytes,
		runtime, kd_jit_runtime_native_begin, kd_jit_runtime_native_release);
	if (result)
		goto drop;
	result = kd_jit_channel_register(&runtime->channel, config->channel_name, config->owner,
		&runtime->session, config->frame_capacity);
	if (result)
		goto drop;
	runtime->channel_live = true;
	*out = runtime;
	return 0;
drop:
	if (runtime->source_live) {
		int dropped = kd_jit_source_use_put(&runtime->source_hold, runtime);

		if (dropped) {
			*out = runtime;
			return dropped;
		}
		runtime->source_live = false;
	}
	if (runtime->feedback_live) {
		int dropped = kd_jit_source_use_put(&runtime->feedback_hold, runtime);

		if (dropped) {
			*out = runtime;
			return dropped;
		}
		runtime->feedback_live = false;
	}
free:
	kvfree(runtime->private_released); kvfree(runtime->images); kvfree(runtime->items);
	kvfree(runtime->cycles); kvfree(runtime->records); kfree(runtime);
	return result;
}

struct rt_reader { const unsigned char *data; size_t left; };
struct rt_writer { unsigned char *data; size_t used; };
static u64 rt_decode(const unsigned char *bytes)
{
	u64 value = 0; unsigned int index;
	for (index = 0; index < 8; ++index) value |= (u64)bytes[index] << (8 * index);
	return value;
}
static bool rt_take(struct rt_reader *reader, u64 *value)
{
	if (reader->left < 8) return false;
	*value = rt_decode(reader->data); reader->data += 8; reader->left -= 8;
	return true;
}
static void rt_put(struct rt_writer *writer, u64 value)
{
	unsigned int index;
	for (index = 0; index < 8; ++index) writer->data[writer->used++] = value >> (8 * index);
}
static void rt_start(struct rt_writer *writer, void *output, unsigned long op, unsigned int count)
{
	writer->data = output; writer->used = 0;
	rt_put(writer, KD_JIT_CONTROL_ABI); rt_put(writer, op); rt_put(writer, 0); rt_put(writer, count);
}
static void rt_finish(struct rt_writer *writer, size_t *length)
{
	struct rt_writer total = { .data = writer->data, .used = 16 };
	rt_put(&total, writer->used); *length = writer->used;
}
static bool rt_add(size_t *total, size_t bytes)
{
	if (bytes > (size_t)-1 - *total) return false;
	*total += bytes; return true;
}
static void rt_blob(struct rt_writer *writer, const void *data, size_t length)
{
	rt_put(writer, length);
	if (length) memcpy(writer->data + writer->used, data, length);
	writer->used += length;
}

static int export_source(struct kd_jit_runtime *runtime, struct rt_reader *input, u64 rows,
		void *output, size_t capacity, size_t *length)
{
	const struct kd_jit_source_description *source = &runtime->config.source->epoch.description;
	struct rt_writer writer;
	size_t total = 32 + 7 * 8;
	const struct kd_jit_image *lookup_image;
	unsigned int index;
	unsigned int boundaries = runtime->config.boundary_count;
	bool lock_present = false, unlock_present = false;

	if (rows || input->left) return -EINVAL;
	for (index = 0; index < runtime->config.boundary_count; ++index) {
		lock_present |= runtime->config.boundaries[index].site == (unsigned long)kd_mutex_lock_entry_asm;
		unlock_present |= runtime->config.boundaries[index].site == (unsigned long)kd_mutex_unlock_entry_asm;
	}
	if (boundaries > ~0U - (!lock_present + !unlock_present)) return -EOVERFLOW;
	boundaries += !lock_present + !unlock_present;
	for (index = 0; index < source->region_count; ++index)
		if (!rt_add(&total, 16) || !rt_add(&total, source->regions[index].length)) return -EOVERFLOW;
	if (!rt_add(&total, (size_t)boundaries * 16) ||
	    !rt_add(&total, 8) || !rt_add(&total, source->version_length)) return -EOVERFLOW;
	if (total > capacity) return -EMSGSIZE;
	rt_start(&writer, output, KD_JIT_CONTROL_SOURCE, source->region_count);
	rt_put(&writer, (unsigned long)&runtime->config.source->epoch);
	rt_put(&writer, (unsigned long)source->configuration_identity);
	rt_put(&writer, (unsigned long)source->load_identity);
	rt_put(&writer, source->current_task_gs_offset);
	rt_put(&writer, boundaries);
	raw_spin_lock(&runtime->slot.guard);
	lookup_image = rcu_dereference_protected(runtime->slot.image,
					       lockdep_is_held(&runtime->slot.guard));
	raw_spin_unlock(&runtime->slot.guard);
	rt_put(&writer, (unsigned long)&runtime->slot);
	rt_put(&writer, (unsigned long)lookup_image);
	for (index = 0; index < source->region_count; ++index) {
		rt_put(&writer, source->regions[index].start);
		rt_blob(&writer, source->regions[index].bytes, source->regions[index].length);
	}
	for (index = 0; index < runtime->config.boundary_count; ++index) {
		rt_put(&writer, runtime->config.boundaries[index].site);
		rt_put(&writer, runtime->config.boundaries[index].kind);
	}
	if (!lock_present) {
		rt_put(&writer, (unsigned long)kd_mutex_lock_entry_asm); rt_put(&writer, KD_JIT_RUNTIME_LOCK);
	}
	if (!unlock_present) {
		rt_put(&writer, (unsigned long)kd_mutex_unlock_entry_asm); rt_put(&writer, KD_JIT_RUNTIME_UNLOCK);
	}
	rt_blob(&writer, source->version, source->version_length);
	rt_finish(&writer, length);
	return 0;
}

static int shutdown_runtime(struct kd_jit_runtime *runtime)
{
	unsigned int index;
	int result;

	WRITE_ONCE(runtime->closing, true);
	result = kd_jit_source_provider_close(runtime->config.source);
	if (result && result != -EALREADY) return result;
	if (runtime->session.storage) return -EBUSY;
	if (!runtime->shutdown_started && runtime->published_image) {
		runtime->shutdown_old = runtime->published_image;
		if (!runtime->shutdown_baseline_live) {
			result = kd_jit_image_owner_use_get(&runtime->shutdown_old->owner,
				&runtime->shutdown_baseline, runtime, KD_JIT_IMAGE_OWNER_USE_BASELINE);
			if (result) return result;
			runtime->shutdown_baseline_live = true;
		}
		result = kd_jit_image_update_begin(&runtime->slot, &runtime->shutdown_update,
			runtime->shutdown_old->owner.image, NULL, runtime);
		if (result) return result;
		runtime->shutdown_started = true;
	}
	if (runtime->shutdown_started && !runtime->shutdown_prepared) {
		result = kd_jit_image_owner_retire_prepare(&runtime->shutdown_old->published,
			runtime->shutdown_old, &runtime->shutdown_update, runtime);
		if (result) return result;
		runtime->shutdown_prepared = true;
	}
	if (runtime->shutdown_started && !runtime->shutdown_committed) {
		result = kd_jit_image_update_try_commit(&runtime->shutdown_update, runtime,
			&runtime->shutdown_retired);
		if (result) return result;
		runtime->shutdown_committed = true;
	}
	if (runtime->shutdown_started && !runtime->shutdown_finished) {
		result = kd_jit_image_owner_retire_finish(&runtime->shutdown_old->published,
			runtime->shutdown_old, &runtime->shutdown_update, runtime, runtime->shutdown_retired);
		if (result) return result;
		runtime->shutdown_old->published_live = false;
		runtime->published_image = NULL;
		runtime->shutdown_finished = true;
	}
	if (runtime->shutdown_baseline_live) {
		result = kd_jit_image_owner_use_put(&runtime->shutdown_baseline, runtime);
		if (result) return result;
		runtime->shutdown_baseline_live = false;
	}
	collect_images(runtime);
	for (index = 0; index < runtime->images_used; ++index) {
		struct kd_jit_control_image *image;
		if (!runtime->images[index]) continue;
		image = kd_jit_compiled_image_control(runtime->images[index]);
		if (image->published_live || (image->owner_initialized && !image->owner_released) ||
		    (image->producer_initialized && !image->producer_closed)) return -EBUSY;
	}
	if (!native_empty(runtime)) return -EBUSY;
	if (runtime->source_live) {
		result = kd_jit_source_use_put(&runtime->source_hold, runtime);
		if (result) return result;
		runtime->source_live = false;
	}
	runtime->shutdown_complete = true;
	return 0;
}

static int archive_claim(struct kd_jit_runtime *runtime, struct rt_reader *input, u64 rows,
		void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = runtime->session.storage;
	struct runtime_cycle *cycle;
	const struct kd_jit_source_description *source = &runtime->config.source->epoch.description;
	struct rt_writer writer;
	u64 epoch, holder, maximum;
	size_t total;
	unsigned int index;
	int result;

	if (!runtime->shutdown_complete || rows || !rt_take(input, &epoch) ||
	    !rt_take(input, &holder) || !rt_take(input, &maximum) || input->left ||
	    epoch != (unsigned long)&runtime->config.source->epoch || !holder || !maximum ||
	    maximum > runtime->config.claim_capacity) return -EINVAL;
	total = 32 + 3 * 8;
	if (maximum > ((size_t)-1 - total) / (12 * 8)) return -EOVERFLOW;
	total += maximum * 12 * 8;
	if (!rt_add(&total, 8) || !rt_add(&total, source->version_length)) return -EOVERFLOW;
	if (total > capacity) return -EMSGSIZE;
	if (!storage) {
		result = allocate_cycle(runtime, &storage);
		if (result) return result;
		runtime->session.storage = storage;
		cycle_of(storage)->archival = true;
	}
	cycle = cycle_of(storage);
	if (!cycle->archival || storage->ending) return -ESTALE;
	if (!storage->claim_live) {
		result = kd_jit_feedback_claim_begin(&runtime->feedback, &runtime->config.source->epoch,
			&storage->claim, storage->claim_items, maximum, (const void *)(unsigned long)holder);
		if (result) return result;
		storage->claim_holder = (const void *)(unsigned long)holder;
		storage->claim_live = true;
		/* Enables explicit END without implying coverage ACK or settlement. */
		storage->aborted = true;
	}
	if ((unsigned long)storage->claim_holder != holder || storage->claim.count > maximum) return -ESTALE;
	rt_start(&writer, output, KD_JIT_CONTROL_ARCHIVE_CLAIM, storage->claim.count);
	rt_put(&writer, (unsigned long)&storage->claim); rt_put(&writer, holder); rt_put(&writer, epoch);
	for (index = 0; index < storage->claim.count; ++index) {
		const struct kd_jit_feedback_fact *fact = &storage->claim_items[index].record->fact;
		rt_put(&writer, (unsigned long)fact->identity); rt_put(&writer, fact->incarnation);
		rt_put(&writer, (unsigned long)fact->producer_identity); rt_put(&writer, fact->producer_image_identity);
		rt_put(&writer, fact->kind); rt_put(&writer, fact->detail); rt_put(&writer, fact->source_ip);
		rt_put(&writer, fact->target); rt_put(&writer, fact->cursor); rt_put(&writer, fact->phase);
		rt_put(&writer, fact->classification); rt_put(&writer, (u64)(s64)fact->entry_result);
	}
	rt_blob(&writer, source->version, source->version_length);
	rt_finish(&writer, length);
	return 0;
}

static int settle_claim(struct kd_jit_runtime *runtime, struct rt_reader *input, u64 rows,
		void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = runtime->session.storage;
	struct runtime_cycle *cycle;
	struct rt_writer writer;
	u64 claim, holder, identity, incarnation, digest_length;
	unsigned int index, member;
	int result;

	if (!runtime->shutdown_complete || !storage || !cycle_of(storage)->archival ||
	    !storage->claim_live || !rt_take(input, &claim) || !rt_take(input, &holder) ||
	    claim != (unsigned long)&storage->claim || holder != (unsigned long)storage->claim_holder ||
	    rows > storage->capacity) return -EINVAL;
	cycle = cycle_of(storage);
	if ((size_t)rows > ((size_t)-1 - (32 + 3 * 8)) / 16 || 32 + 3 * 8 + rows * 16 > capacity)
		return -EMSGSIZE;
	for (index = 0; index < rows; ++index) {
		if (!rt_take(input, &identity) || !rt_take(input, &incarnation)) return -EINVAL;
		for (member = 0; member < storage->claim.count; ++member)
			if (identity == (unsigned long)storage->claim_items[member].identity &&
			    incarnation == storage->claim_items[member].incarnation) break;
		if (member == storage->claim.count) return -ESTALE;
		if (cycle->settlement.identity) {
			if (index >= cycle->archive.count || storage->included[index].identity != (const void *)(unsigned long)identity ||
			    storage->included[index].incarnation != incarnation) return -ESTALE;
		} else storage->included[index] = storage->claim_items[member];
	}
	if (!rt_take(input, &digest_length) || digest_length != 32 || input->left != 32) return -EINVAL;
	if (cycle->settlement.identity) {
		if (cycle->archive.count != rows || memcmp(cycle->archive.content_id, input->data, 32)) return -ESTALE;
	} else {
		memcpy(cycle->archive.content_id, input->data, 32);
		cycle->archive.claim = &storage->claim;
		cycle->archive.claim_holder = storage->claim_holder;
		cycle->archive.epoch = &runtime->config.source->epoch;
		cycle->archive.items = storage->included;
		cycle->archive.count = rows;
		result = kd_jit_feedback_claim_settle(&storage->claim, storage->claim_holder,
			&cycle->archive, &cycle->settlement);
		if (result) return result;
	}
	rt_start(&writer, output, KD_JIT_CONTROL_SETTLE, cycle->settlement.count);
	rt_put(&writer, (unsigned long)cycle->settlement.identity); rt_put(&writer, claim); rt_put(&writer, holder);
	for (index = 0; index < cycle->settlement.count; ++index) {
		rt_put(&writer, (unsigned long)cycle->settlement.items[index].identity);
		rt_put(&writer, cycle->settlement.items[index].incarnation);
	}
	rt_finish(&writer, length);
	return 0;
}

static int extension(void *context, struct kd_jit_control_session *session,
		unsigned long op, const void *input, size_t input_length,
		void *output, size_t output_capacity, size_t *output_length)
{
	struct kd_jit_runtime *runtime = context;
	struct rt_reader reader = { .data = input, .left = input_length };
	struct rt_writer writer;
	u64 abi, encoded_op, total, rows;
	int result;

	if (session != &runtime->session || !rt_take(&reader, &abi) || !rt_take(&reader, &encoded_op) ||
	    !rt_take(&reader, &total) || !rt_take(&reader, &rows) || abi != KD_JIT_CONTROL_ABI ||
	    encoded_op != op || total != input_length) return -EINVAL;
	switch (op) {
	case KD_JIT_CONTROL_SOURCE:
		return export_source(runtime, &reader, rows, output, output_capacity, output_length);
	case KD_JIT_CONTROL_SHUTDOWN:
		if (rows || reader.left) return -EINVAL;
		if (output_capacity < 40) return -EMSGSIZE;
		result = shutdown_runtime(runtime);
		if (result) return result;
		rt_start(&writer, output, op, 0); rt_put(&writer, (unsigned long)&runtime->config.source->epoch);
		rt_finish(&writer, output_length); return 0;
	case KD_JIT_CONTROL_ARCHIVE_CLAIM:
		return archive_claim(runtime, &reader, rows, output, output_capacity, output_length);
	case KD_JIT_CONTROL_SETTLE:
		return settle_claim(runtime, &reader, rows, output, output_capacity, output_length);
	default:
		return -EINVAL;
	}
}

int kd_jit_runtime_destroy(struct kd_jit_runtime *runtime)
{
	unsigned int index;
	int result;

	if (!runtime) return -EINVAL;
	result = shutdown_runtime(runtime);
	if (result) return result;
	collect_images(runtime);
	if (!kd_jit_control_session_idle(&runtime->session)) return -EBUSY;
	if (runtime->channel_live) {
		result = kd_jit_channel_unregister(&runtime->channel);
		if (result) return result;
		runtime->channel_live = false;
	}
	for (index = 0; index < runtime->images_used; ++index) {
		if (!runtime->images[index]) continue;
		result = kd_jit_compiled_image_destroy(runtime->images[index]);
		if (result) return result;
		runtime->images[index] = NULL;
	}
	if (runtime->feedback_live) {
		result = kd_jit_source_use_put(&runtime->feedback_hold, runtime);
		if (result) return result;
		runtime->feedback_live = false;
	}
	/* No source provider/payload access follows the final cold controller put. */
	kvfree(runtime->private_released); kvfree(runtime->images); kvfree(runtime->items);
	kvfree(runtime->cycles); kvfree(runtime->records); kfree(runtime);
	return 0;
}
