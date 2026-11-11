// SPDX-License-Identifier: GPL-2.0-only
/* Immutable provider snapshots and independent native-source retention. */
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/overflow.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

#include "source_provider.h"

static void release_snapshot(void *context)
{
	struct kd_jit_source_provider *provider = context;
	struct module **modules = provider->modules;
	unsigned int count = provider->module_count, index;

	for (index = 0; index < provider->region_count; ++index)
		kvfree(provider->regions[index].bytes);
	kvfree(provider->regions);
	kvfree(provider->version);
	provider->regions = NULL;
	provider->version = NULL;
	provider->modules = NULL;
	provider->region_count = 0;
	provider->module_count = 0;
	/* Only separately retained local control remains after residency puts. */
	for (index = 0; index < count; ++index)
		module_put(modules[index]);
	kvfree(modules);
}

int kd_jit_source_provider_create(const struct kd_jit_source_provider_args *args,
		struct kd_jit_source_provider **out)
{
	struct kd_jit_source_provider_args inputs;
	struct kd_jit_source_provider *provider;
	struct kd_jit_source_description description;
	unsigned int index;
	int result;

	if (!out)
		return -EINVAL;
	*out = NULL;
	if (!args)
		return -EINVAL;
	inputs = *args;
	if (inputs.contract != KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES ||
	    !inputs.version || !inputs.version_length || !inputs.regions || !inputs.region_count ||
	    !inputs.configuration_identity || !inputs.load_identity ||
	    (inputs.module_count && !inputs.modules))
		return -EINVAL;
	provider = kmalloc(sizeof(*provider), GFP_KERNEL);
	if (!provider)
		return -ENOMEM;
	provider->regions = NULL;
	provider->version = NULL;
	provider->modules = NULL;
	provider->region_count = 0;
	provider->module_count = 0;
	provider->regions = kvmalloc_array(inputs.region_count, sizeof(*provider->regions), GFP_KERNEL);
	provider->version = kvmalloc(inputs.version_length, GFP_KERNEL);
	if (inputs.module_count)
		provider->modules = kvmalloc_array(inputs.module_count, sizeof(*provider->modules), GFP_KERNEL);
	if (!provider->regions || !provider->version || (inputs.module_count && !provider->modules)) {
		result = -ENOMEM;
		goto fail;
	}
	memcpy(provider->version, inputs.version, inputs.version_length);
	for (index = 0; index < inputs.module_count; ++index) {
		if (!try_module_get(inputs.modules[index])) {
			result = -ENODEV;
			goto fail;
		}
		provider->modules[provider->module_count++] = inputs.modules[index];
	}
	for (index = 0; index < inputs.region_count; ++index) {
		unsigned long start = inputs.regions[index].start;
		size_t length = inputs.regions[index].length;
		unsigned char *bytes;

		if (!length || length - 1 > ~0UL - start) {
			result = -EINVAL;
			goto fail;
		}
		bytes = kvmalloc(length, GFP_KERNEL);
		if (!bytes) {
			result = -ENOMEM;
			goto fail;
		}
		provider->regions[index].start = start;
		provider->regions[index].length = length;
		provider->regions[index].bytes = bytes;
		++provider->region_count;
		result = copy_from_kernel_nofault(bytes, (const void *)start, length);
		if (result)
			goto fail;
	}
	description.version = provider->version;
	description.version_length = inputs.version_length;
	description.regions = provider->regions;
	description.region_count = provider->region_count;
	description.configuration_identity = inputs.configuration_identity;
	description.load_identity = inputs.load_identity;
	description.current_task_gs_offset = inputs.current_task_gs_offset;
	result = kd_jit_source_epoch_init(&provider->epoch, &description, provider, release_snapshot);
	if (result)
		goto fail;
	*out = provider;
	return 0;
fail:
	release_snapshot(provider);
	kfree(provider);
	return result;
}

int kd_jit_source_provider_close(struct kd_jit_source_provider *provider)
{
	return provider ? kd_jit_source_epoch_close(&provider->epoch) : -EINVAL;
}

int kd_jit_source_provider_destroy(struct kd_jit_source_provider *provider)
{
	int result;

	if (!provider)
		return -EINVAL;
	result = kd_jit_source_epoch_try_release(&provider->epoch);
	if (result)
		return result;
	kfree(provider);
	return 0;
}

int kd_jit_source_native_begin(struct kd_jit_source_provider *provider, void **lease)
{
	struct kd_jit_source_use *use;
	int result;

	if (!provider || !lease)
		return -EINVAL;
	*lease = NULL;
	use = kmalloc(sizeof(*use), GFP_KERNEL);
	if (!use)
		return -ENOMEM;
	kd_jit_source_use_init(use);
	result = kd_jit_source_use_get(&provider->epoch, use, use, KD_JIT_SOURCE_USE_NATIVE);
	if (result) {
		kfree(use);
		return result;
	}
	*lease = use;
	return 0;
}

void kd_jit_source_native_release(void *lease)
{
	struct kd_jit_source_use *use = lease;
	int result = kd_jit_source_use_put(use, use);

	BUG_ON(result);
	kfree(use);
}
