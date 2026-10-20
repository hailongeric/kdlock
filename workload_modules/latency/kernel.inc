/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Included only in a private copy of the synthetic runner, after its existing
 * snapshot helpers. It uses the original quiescent control gate. The lock,
 * bodies, frame storage, ownership and admission implementation are unchanged.
 */
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include "operation_latency.h"

static bool latency_sample;
module_param(latency_sample, bool, 0400);
static struct kd_latency_slot *sc_latency;

static int sc_latency_register(struct miscdevice *device)
{
	int error;

	/* Preallocate outside warmup and timing. Reset only slot metadata between
	 * phases; old records are overwritten individually before publication. */
	sc_latency = vzalloc(array_size(SC_TIMED_MAX_WORKERS, sizeof(*sc_latency)));
	if (!sc_latency)
		return -ENOMEM;
	error = misc_register(device);
	if (error) {
		vfree(sc_latency);
		sc_latency = NULL;
	}
	return error;
}

static void sc_latency_configure(unsigned int workers)
{
	unsigned int i;

	for (i = 0; i < workers; i++)
		kd_latency_reset(&sc_latency[i], i);
}

static long sc_latency_read(void __user *user)
{
	struct {
		__u32 version, worker, first, capacity;
	} request;
	struct kd_latency_chunk *chunk;
	struct kd_latency_slot *slot;
	size_t bytes;
	unsigned int count;
	long error = 0;

	if (copy_from_user(&request, user, sizeof(request)))
		return -EFAULT;
	if (request.version != KD_LATENCY_VERSION ||
	    request.capacity != KD_LATENCY_CHUNK ||
	    request.first > KD_LATENCY_CAPACITY)
		return -EINVAL;
	chunk = kmalloc(sizeof(*chunk), GFP_KERNEL);
	if (!chunk)
		return -ENOMEM;
	if (!sc_snapshot_begin()) {
		error = -EBUSY;
		goto free;
	}
	if (!sc_timed.started_ns || request.worker >= sc_timed.workers) {
		error = -EINVAL;
		goto release;
	}
	slot = &sc_latency[request.worker];
	count = min_t(u64, slot->selected, KD_LATENCY_CAPACITY);
	if (request.first > count) {
		error = -EINVAL;
		goto release;
	}
	count = min_t(unsigned int, count - request.first, KD_LATENCY_CHUNK);
	chunk->version = KD_LATENCY_VERSION;
	chunk->worker = request.worker;
	chunk->first = request.first;
	chunk->capacity = KD_LATENCY_CHUNK;
	chunk->started_ns = sc_timed.started_ns;
	chunk->completed = slot->completed;
	chunk->selected = slot->selected;
	chunk->dropped = slot->dropped;
	chunk->count = count;
	chunk->enabled = latency_sample;
	chunk->reserved = 0;
	memcpy(chunk->samples, slot->samples + request.first,
	       count * sizeof(*chunk->samples));
	/* The uninitialized unused tail never crosses into userspace. */
	bytes = offsetof(struct kd_latency_chunk, samples) +
		count * sizeof(*chunk->samples);
	if (copy_to_user(user, chunk, bytes))
		error = -EFAULT;
release:
	sc_snapshot_end();
free:
	kfree(chunk);
	return error;
}
