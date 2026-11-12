/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_SOURCE_PROVIDER_H
#define KDLOCK_SOURCE_PROVIDER_H

#include <linux/module.h>
#include "source_epoch.h"

/* Selected initial provider lane. Every supplied source dependency remains
 * immutable from before capture through the final native/JIT/feedback user.
 * The caller excludes all text patching for these dependencies, including
 * tracing, static calls/branches, alternatives, probes and live replacement.
 * This is an explicit provider contract, not a hash-based mutation detector or
 * a claim that module_get alone freezes text. No text-patching lock is held
 * across sleeping execution. All source operations have declared boundaries.
 */
#define KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES 1U

struct kd_jit_source_load_region {
	unsigned long start;
	size_t length;
};

struct kd_jit_source_provider_args {
	unsigned int contract;
	const unsigned char *version;
	size_t version_length;
	const struct kd_jit_source_load_region *regions;
	unsigned int region_count;
	const void *configuration_identity;
	const void *load_identity;
	unsigned long current_task_gs_offset;
	/* Complete residency dependencies; NULL entries identify built-in text.
	 * The array and all input/control/configuration backing survive creation.
	 * configuration/load identity backing then survives provider destruction.
	 */
	struct module *const *modules;
	unsigned int module_count;
};

struct kd_jit_source_provider {
	struct kd_jit_source_epoch epoch;
	struct kd_jit_source_region *regions;
	unsigned char *version;
	struct module **modules;
	unsigned int region_count;
	unsigned int module_count;
};

/* Cold sleepable setup. Pin the complete module set, copy exact actual-address
 * bytes with nofault reads under the declared immutability contract, then build
 * the epoch from that coherent snapshot. Failure unwinds only new allocations
 * and references; success owns them until source shutdown and exact last use.
 * Explicit finite extents select no deployment/default source-cache capacity.
 */
int kd_jit_source_provider_create(const struct kd_jit_source_provider_args *args,
		struct kd_jit_source_provider **provider);
/* Close new source admission/builds independently before close. Remove/drain
 * all images and native scopes, archive/settle pending feedback, end every host
 * observer, then destroy. A busy result preserves all backing. Do not invoke the
 * embedded epoch's finalizer separately. Successful destroy frees the provider;
 * caller/callback code backing is independently retained through final return.
 */
int kd_jit_source_provider_close(struct kd_jit_source_provider *provider);
int kd_jit_source_provider_destroy(struct kd_jit_source_provider *provider);
/* Exact native source scope, covering suffix/return and its real last users.
 * Acquire cold before task_storage_start_current and pass the returned hold plus
 * kd_jit_source_native_release as its native lease. On setup failure with NULL
 * storage the caller still owns and releases it. New scopes require OPEN.
 */
int kd_jit_source_native_begin(struct kd_jit_source_provider *provider, void **lease);
void kd_jit_source_native_release(void *lease);

#endif
