/* SPDX-License-Identifier: GPL-2.0 */
/* Current runtime binding for the two unchanged nano bodies. */
#include <linux/hash.h>
#include <linux/mm.h>
#include <linux/overflow.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <asm/msr.h>
#include <asm/msr-index.h>

static struct kd_jit_runtime *rb_runtime;
static struct kd_jit_source_provider *rb_provider;
static bool rb_listening;
static unsigned long gs_offset, builtin_source_start, builtin_source_size;
static unsigned int source_size, step_size, dependency_page_limit;
static unsigned long total_source_byte_limit;
static bool gs_verified, immutable_text, auxiliary_contract;
static char *source_version;
module_param(gs_offset, ulong, 0444);
module_param(gs_verified, bool, 0444);
module_param(immutable_text, bool, 0444);
module_param(auxiliary_contract, bool, 0444);
module_param(source_size, uint, 0444);
module_param(step_size, uint, 0444);
module_param(dependency_page_limit, uint, 0444);
module_param(total_source_byte_limit, ulong, 0444);
module_param(builtin_source_start, ulong, 0444);
module_param(builtin_source_size, ulong, 0444);
module_param(source_version, charp, 0444);
MODULE_PARM_DESC(immutable_text, "Complete source dependencies remain immutable through all native and generated users");
MODULE_PARM_DESC(auxiliary_contract, "Explicit bounded control-stack premise for this workload and target");

static struct {
	unsigned long gs_offset, source_size, step_size, builtin_start, builtin_size;
	unsigned int family, requests, auxiliary_bytes, control_bytes, proxy_limit;
} rb_configuration;
static const unsigned char rb_load_identity;

#include "evidence.inc"

#ifdef RB_RWSEM
static const struct kd_jit_runtime_boundary rb_boundaries[] = {
	{ (unsigned long)kd_rwsem_down_read_entry_asm, KD_JIT_RUNTIME_LOCK },
	{ (unsigned long)kd_rwsem_up_read_entry_asm, KD_JIT_RUNTIME_UNLOCK },
	{ (unsigned long)kd_rwsem_down_write_entry_asm, KD_JIT_RUNTIME_LOCK },
	{ (unsigned long)kd_rwsem_up_write_entry_asm, KD_JIT_RUNTIME_UNLOCK },
};
#endif

static void rb_listen_stop(void)
{
	if (!rb_listening)
		return;
	unregister_trace_kdlock_observe_tp(rb_observe, NULL);
	tracepoint_synchronize_unregister();
	rb_listening = false;
}

static int rb_runtime_destroy(void)
{
	struct rw_bench_snapshot snap = { 0 };
	int error;
	rb_lock_snapshot(&snap);
	if (snap.gate || snap.cnts)
		return -EBUSY;
	error = rb_runtime ? kd_jit_runtime_destroy(rb_runtime) : 0;
	if (error)
		return error;
	rb_runtime = NULL;
	error = rb_provider ? kd_jit_source_provider_destroy(rb_provider) : 0;
	if (error)
		return error;
	rb_provider = NULL;
	rb_listen_stop();
	return 0;
}

static int rb_runtime_init(void)
{
	struct kd_jit_source_load_region *regions;
	struct module *modules[] = { THIS_MODULE, NULL };
	struct kd_jit_source_provider_args source;
	struct kd_jit_runtime_config config;
	unsigned int pages = 0, count, i, j;
	size_t bytes;
	int error;

	if (!gs_verified || !immutable_text || !auxiliary_contract || !source_version ||
	    !*source_version || strnlen(source_version, 257) > 256 ||
	    !source_size || source_size > 65536 || !step_size || step_size > 65536 ||
	    !dependency_page_limit || !total_source_byte_limit ||
	    !builtin_source_start || !builtin_source_size ||
	    builtin_source_size - 1 > ~0UL - builtin_source_start ||
	    (builtin_source_start >> PAGE_SHIFT) !=
	    ((builtin_source_start + builtin_source_size - 1) >> PAGE_SHIFT))
		return -EINVAL;
#ifdef CONFIG_MITIGATION_ITS
	if (THIS_MODULE->arch.its_pages.num < 0 ||
	    (THIS_MODULE->arch.its_pages.num && !THIS_MODULE->arch.its_pages.pages))
		return -EINVAL;
	pages = THIS_MODULE->arch.its_pages.num;
#endif
	if (pages >= dependency_page_limit || check_add_overflow(pages, 3U, &count) ||
	    check_mul_overflow((size_t)pages, (size_t)PAGE_SIZE, &bytes) ||
	    check_add_overflow(bytes, (size_t)source_size, &bytes) ||
	    check_add_overflow(bytes, (size_t)step_size, &bytes) ||
	    check_add_overflow(bytes, (size_t)builtin_source_size, &bytes) ||
	    bytes > total_source_byte_limit)
		return -E2BIG;
	regions = kcalloc(count, sizeof(*regions), GFP_KERNEL);
	if (!regions)
		return -ENOMEM;
	regions[0] = (struct kd_jit_source_load_region) { (unsigned long)rb_write, source_size };
	regions[1] = (struct kd_jit_source_load_region) { (unsigned long)rb_read, step_size };
#ifdef CONFIG_MITIGATION_ITS
	for (i = 0; i < pages; ++i)
		regions[2 + i] = (struct kd_jit_source_load_region) {
			(unsigned long)THIS_MODULE->arch.its_pages.pages[i], PAGE_SIZE };
#endif
	regions[2 + pages] = (struct kd_jit_source_load_region) { builtin_source_start, builtin_source_size };
	for (i = 0; i < count; ++i) {
		unsigned long last;
		if (!regions[i].start || !regions[i].length ||
		    check_add_overflow(regions[i].start, regions[i].length - 1, &last)) {
			error = -EINVAL;
			goto regions_out;
		}
		for (j = 0; j < i; ++j)
			if (regions[i].start < regions[j].start + regions[j].length &&
			    regions[j].start <= last) {
				error = -EINVAL;
				goto regions_out;
			}
	}
	rb_configuration.gs_offset = gs_offset;
	rb_configuration.source_size = source_size;
	rb_configuration.step_size = step_size;
	rb_configuration.builtin_start = builtin_source_start;
	rb_configuration.builtin_size = builtin_source_size;
	rb_configuration.family = RB_FAMILY;
	rb_configuration.requests = RB_REQUESTS;
	rb_configuration.auxiliary_bytes = 128 * 1024;
	rb_configuration.control_bytes = 64 * 1024;
	rb_configuration.proxy_limit = 16;
	source = (struct kd_jit_source_provider_args) {
		.contract = KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES,
		.version = (const unsigned char *)source_version, .version_length = strlen(source_version),
		.regions = regions, .region_count = count,
		.configuration_identity = &rb_configuration, .load_identity = &rb_load_identity,
		.current_task_gs_offset = gs_offset, .modules = modules, .module_count = 2,
	};
	error = kd_jit_source_provider_create(&source, &rb_provider);
	if (error)
		goto regions_out;
	config = (struct kd_jit_runtime_config) {
		.source = rb_provider, .feedback_capacity = 4096, .cycle_capacity = 32,
		.image_capacity = 16, .claim_capacity = 4096,
		.compiled = { .code_capacity = 128 * 1024, .artifact_capacity = 3 * 512 * 1024,
			.flat_capacity = 256 * 1024, .entry_capacity = 64, .source_capacity = 4096,
			.observation_capacity = 4096 },
#define RB_SYMBOL(s) { .data = (s), .length = sizeof(s) - 1 }
		.symbols = { .descriptor = RB_SYMBOL("kd_nano_image"), .source = RB_SYMBOL("kd_nano_epoch"),
			.producer = RB_SYMBOL("kd_nano_producer"), .entry = RB_SYMBOL("kd_nano_entry") },
#undef RB_SYMBOL
		.family = RB_FAMILY,
#ifdef RB_RWSEM
		.boundaries = rb_boundaries, .boundary_count = ARRAY_SIZE(rb_boundaries),
#endif
		.channel_name = "kd_nano_source", .owner = THIS_MODULE,
		.frame_capacity = 2 * 1024 * 1024, .request_capacity = RB_REQUESTS,
		.auxiliary_bytes = 128 * 1024, .required_control_bytes = 64 * 1024, .proxy_limit = 16,
	};
	error = kd_jit_runtime_create(&config, &rb_runtime);
	if (error)
		goto source_out;
	rb_evidence = kvcalloc(RB_MAX_WORKERS, sizeof(*rb_evidence), GFP_KERNEL);
	if (!rb_evidence) {
		error = -ENOMEM;
		goto runtime_out;
	}
	rb_evidence_reset();
	error = register_trace_kdlock_observe_tp(rb_observe, NULL);
	if (!error) {
		rb_listening = true;
		goto regions_out;
	}
	kvfree(rb_evidence);
	rb_evidence = NULL;
runtime_out:
	BUG_ON(kd_jit_runtime_destroy(rb_runtime));
	rb_runtime = NULL;
source_out:
	if (rb_runtime) {
		BUG_ON(kd_jit_runtime_destroy(rb_runtime));
		rb_runtime = NULL;
	}
	{
		int closed = kd_jit_source_provider_close(rb_provider);
		BUG_ON(closed && closed != -EALREADY);
	}
	BUG_ON(kd_jit_source_provider_destroy(rb_provider));
	rb_provider = NULL;
regions_out:
	kfree(regions);
	return error;
}

static int rb_copy_evidence(void __user *user)
{
	struct rb_evidence_snapshot *snap;
	unsigned int i;
	int error;
	snap = kvzalloc(sizeof(*snap), GFP_KERNEL);
	if (!snap)
		return -ENOMEM;
	snap->version = 1;
	snap->workers = rb_config.workers;
	for (i = 0; i < RB_MAX_WORKERS; ++i)
		snap->rows[i] = rb_evidence[i].row;
	error = copy_to_user(user, snap, sizeof(*snap)) ? -EFAULT : 0;
	kvfree(snap);
	return error;
}
