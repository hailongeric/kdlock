// SPDX-License-Identifier: GPL-2.0-only
/* Ordinary-mutex kernel mechanism evidence; no real-world API/performance claim. */
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/fs.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mm.h>
#include <linux/overflow.h>
#include <linux/mutex.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <asm/msr.h>
#include <asm/msr-index.h>

#include "kernel/mutex.h"
#include "kernel/runtime.h"
#include "kernel/task_state.h"
#include "include/kd_mutex_api.h"

#define FIXTURE_MAX_WORKERS 8U
#define FIXTURE_MAX_ITERATIONS 64U
#define FIXTURE_REQUESTS 256U
#define FIXTURE_AUXILIARY_BYTES (128UL * 1024)
#define FIXTURE_CONTROL_BYTES (32UL * 1024)
#define FIXTURE_HOLD_ITERATIONS 65536U

static unsigned long gs_offset;
static bool gs_verified;
static bool immutable_text;
static bool auxiliary_contract;
static unsigned int source_size;
static unsigned int step_size;
static unsigned int dependency_page_limit;
static unsigned long total_source_byte_limit;
static char *source_version;
module_param(gs_offset, ulong, 0444);
module_param(gs_verified, bool, 0444);
module_param(immutable_text, bool, 0444);
module_param(auxiliary_contract, bool, 0444);
module_param(source_size, uint, 0444);
module_param(step_size, uint, 0444);
module_param(dependency_page_limit, uint, 0444);
module_param(total_source_byte_limit, ulong, 0444);
module_param(source_version, charp, 0444);
MODULE_PARM_DESC(gs_offset, "Actual running-target current_task GS offset, verified from its kernel ELF/source");
MODULE_PARM_DESC(gs_verified, "Operator supplied the exact running-target GS/configuration receipt");
MODULE_PARM_DESC(immutable_text, "Module/source dependencies remain unpatched through final source/native users");
MODULE_PARM_DESC(auxiliary_contract, "Operator admits this target's task-owned auxiliary stack/context contract");
MODULE_PARM_DESC(source_size, "Exact fixture_source_body ELF symbol size from this module binary");
MODULE_PARM_DESC(step_size, "Exact fixture_source_step ELF symbol size from this module binary");
MODULE_PARM_DESC(dependency_page_limit, "Explicit maximum retained module-owned executable dependency pages");
MODULE_PARM_DESC(total_source_byte_limit, "Explicit maximum total copied body, callee and dependency bytes");
MODULE_PARM_DESC(source_version, "Explicit module/kernel/configuration identity for this mechanism run");

struct fixture_worker {
	struct task_struct *task;
	struct task_struct *expected_task;
	struct task_struct *seen_before;
	struct task_struct *seen_inside;
	unsigned long *seen_pointer;
	struct kd_task_storage *storage;
	unsigned long core_address;
	unsigned long regs_address;
	unsigned long call_effects;
	unsigned long origin_errors;
	unsigned long core_errors;
	unsigned long completed;
	unsigned int mode;
	unsigned int iterations;
	unsigned int index;
	int error;
	bool finished;
};

/* Each round has stable distinct objects. No worker reacquires an object
 * whose earlier deferred physical release may still be outstanding.
 */
/* The open control keeps only its exact opener task alive. Managed task storage
 * belongs to the real lifecycle, so release must never dereference a stale
 * storage/root after the opener's do_exit has already reclaimed it.
 */
struct fixture_control {
	struct task_struct *owner;
	bool entered;
};

static struct kd_mutex lock_a[FIXTURE_MAX_ITERATIONS];
static struct kd_mutex lock_b[FIXTURE_MAX_ITERATIONS];
static unsigned long protected_a[FIXTURE_MAX_ITERATIONS];
static unsigned long protected_b[FIXTURE_MAX_ITERATIONS];
static unsigned long pointer_value[FIXTURE_MAX_ITERATIONS];
static struct fixture_worker workers[FIXTURE_MAX_WORKERS];
static unsigned int worker_count;
static unsigned int requested_iterations;
static unsigned int requested_mode;
static struct completion start_gate;
static atomic_t ready_count = ATOMIC_INIT(0);
static unsigned int ready_goal;
static bool abort_start;
static DEFINE_MUTEX(control_mutex);
static struct kd_jit_source_provider *provider;
static struct kd_jit_runtime *runtime;
static char load_identity;
static struct {
	unsigned long gs_offset;
	unsigned int source_size;
	unsigned int step_size;
	unsigned int dependency_page_limit;
	unsigned long total_source_byte_limit;
	unsigned int dependency_pages;
	size_t source_bytes;
} configuration_identity;

void fixture_source_body(struct fixture_worker *worker);
void fixture_source_step(struct fixture_worker *worker);
static void (*volatile step_entry)(struct fixture_worker *) = fixture_source_step;

/* Ordinary C callee, translated by the same backend or handed back at its actual
 * compiler-generated frontier. Its counter detects duplicate CALL effects.
 */
noinline notrace __visible void fixture_source_step(struct fixture_worker *worker)
{
	worker->call_effects++;
	worker->seen_inside = current;
	worker->seen_pointer = &pointer_value[worker->index];
}

/* No case-specific runtime adapter, raw MCS use or extracted kernel body. All
 * cases execute the real ordinary pair. Mode 2 ends A's logical scope while B
 * remains open, exercising retained-owner deferral without reacquiring A.
 * The source operation CALL sites/root continuations are discovered from the
 * actual exported bytes; no instruction offsets are embedded in this fixture.
 */
noinline notrace __visible void fixture_source_body(struct fixture_worker *worker)
{
	unsigned int spin, index = worker->index;

	kd_mutex_lock(&lock_a[index]);
	WRITE_ONCE(protected_a[index], READ_ONCE(protected_a[index]) + 1);
	worker->seen_before = current;
	for (spin = 0; spin < FIXTURE_HOLD_ITERATIONS; ++spin)
		barrier();
	READ_ONCE(step_entry)(worker);
	if (worker->mode == 0) {
		kd_mutex_unlock(&lock_a[index]);
		return;
	}
	kd_mutex_lock(&lock_b[index]);
	WRITE_ONCE(protected_b[index], READ_ONCE(protected_b[index]) + 1);
	READ_ONCE(step_entry)(worker);
	if (worker->mode == 2) {
		kd_mutex_unlock(&lock_a[index]);
		WRITE_ONCE(protected_b[index], READ_ONCE(protected_b[index]) + 1);
		READ_ONCE(step_entry)(worker);
		kd_mutex_unlock(&lock_b[index]);
	} else {
		kd_mutex_unlock(&lock_b[index]);
		kd_mutex_unlock(&lock_a[index]);
	}
}

static void (*volatile body_entry)(struct fixture_worker *) = fixture_source_body;

static void notrace worker_ready(void)
{
	unsigned int index;

	if (atomic_inc_return(&ready_count) != READ_ONCE(ready_goal))
		return;
	for (index = 0; index < READ_ONCE(ready_goal); ++index)
		if (READ_ONCE(workers[index].error))
			WRITE_ONCE(abort_start, true);
	complete_all(&start_gate);
}

static int notrace worker_main(void *argument)
{
	struct fixture_worker *worker = argument;
	struct kd_task_root_context *root;
	struct kd_execution_binding *binding;
	unsigned long origin_gs;
	unsigned int iteration;
	bool pending;
	bool ready_reported = false;
	int result;

	worker->expected_task = current;
	preempt_disable();
	rdmsrl(MSR_GS_BASE, origin_gs);
	preempt_enable();
	result = kd_jit_runtime_enter_current(runtime, origin_gs, &worker->storage);
	if (result) {
		worker->error = result;
		/* A retained setup error must not exit/free its task stack. */
		if (worker->storage)
			goto leave;
		goto ready_parked;
	}
	root = kd_task_storage_root(worker->storage);
	worker->core_address = (unsigned long)&root->core;
	worker->regs_address = (unsigned long)&root->core.regs;
	ready_reported = true;
	worker_ready();
	wait_for_completion(&start_gate);
	for (iteration = 0; !READ_ONCE(abort_start) && iteration < worker->iterations && !kthread_should_stop(); ++iteration) {
		worker->index = iteration;
		READ_ONCE(body_entry)(worker);
		worker->completed++;
		if (worker->seen_before != worker->expected_task ||
		    worker->seen_inside != worker->expected_task ||
		    worker->seen_pointer != &pointer_value[iteration]) {
			worker->origin_errors++;
			worker->error = -EUCLEAN;
		}
		if (READ_ONCE(current->kd_root_context) != root || root->core.origin != current ||
		    (unsigned long)&root->core != worker->core_address ||
		    (unsigned long)&root->core.regs != worker->regs_address) {
			worker->core_errors++;
			worker->error = -EUCLEAN;
		}
		cond_resched();
	}
leave:
	for (;;) {
		root = kd_task_storage_root(worker->storage);
		/* Existing retained current-native endpoint, not a guessed initial one. */
		binding = smp_load_acquire(&root->core.binding);
		result = kd_jit_runtime_leave_current(worker->storage, binding, &pending);
		if (!result) {
			worker->storage = NULL;
			break;
		}
		if (result != -EBUSY && result != -EAGAIN)
			worker->error = result;
		/* Metadata-only progress/refusal; never force source/context retirement. */
		cond_resched();
	}
	if (ready_reported)
		goto parked;
ready_parked:
	worker_ready();
parked:
	smp_store_release(&worker->finished, true);
	/* Keep a live joined task until control explicitly stops it. Module/source
	 * residency remains held, and no task/source backing is inferred from done.
	 */
	while (!kthread_should_stop())
		schedule_timeout_interruptible(HZ / 10);
	return worker->error;
}

static int notrace stop_workers(void)
{
	unsigned int index;
	int result = 0;

	complete_all(&start_gate);
	for (index = 0; index < worker_count; ++index) {
		int stopped = kthread_stop(workers[index].task);

		if (stopped && !result)
			result = stopped;
		put_task_struct(workers[index].task);
		workers[index].task = NULL;
	}
	worker_count = 0;
	return result;
}

static bool notrace fixture_locks_clear(void)
{
	unsigned int index;

	for (index = 0; index < FIXTURE_MAX_ITERATIONS; ++index)
		if (READ_ONCE(lock_a[index].tail) || READ_ONCE(lock_a[index].owner) ||
		    READ_ONCE(lock_b[index].tail) || READ_ONCE(lock_b[index].owner))
			return false;
	return true;
}

static int notrace start_workers(unsigned int mode, unsigned int count, unsigned int iterations)
{
	unsigned int index;
	int result;

	if (!runtime || worker_count || mode > 2 || !count || count > FIXTURE_MAX_WORKERS ||
	    !iterations || iterations > FIXTURE_MAX_ITERATIONS)
		return -EINVAL;
	if (!fixture_locks_clear())
		return -EBUSY;
	for (index = 0; index < FIXTURE_MAX_ITERATIONS; ++index) {
		protected_a[index] = 0;
		protected_b[index] = 0;
		pointer_value[index] = 0;
	}
	requested_mode = mode; requested_iterations = iterations;
	reinit_completion(&start_gate);
	atomic_set(&ready_count, 0);
	WRITE_ONCE(ready_goal, count);
	WRITE_ONCE(abort_start, false);
	for (index = 0; index < count; ++index) {
		struct fixture_worker *worker = &workers[index];

		/* This metadata contains no source packet and has no remaining users. */
		*worker = (struct fixture_worker) { .mode = mode, .iterations = iterations };
		worker->task = kthread_run(worker_main, worker, "kd-fixture/%u", index);
		if (IS_ERR(worker->task)) {
			result = PTR_ERR(worker->task);
			worker->task = NULL;
			WRITE_ONCE(abort_start, true);
			stop_workers();
			return result;
		}
		/* Workers park until joined even after a private setup error. */
		get_task_struct(worker->task);
		worker_count++;
	}
	return 0;
}

static int notrace control_open(struct inode *inode, struct file *file)
{
	struct fixture_control *control;

	(void)inode;
	control = kzalloc(sizeof(*control), GFP_KERNEL);
	if (!control)
		return -ENOMEM;
	control->owner = current;
	get_task_struct(current);
	file->private_data = control;
	return 0;
}

static int notrace control_release(struct inode *inode, struct file *file)
{
	struct fixture_control *control = file->private_data;

	(void)inode;
	/* The normal do_exit hook owns automatic native/storage drain. An fd may
	 * be inherited by a child and finally closed after its opener has exited.
	 * Neither this scalar flag nor this task ref is storage ownership.
	 */
	put_task_struct(control->owner);
	kfree(control);
	return 0;
}

static int notrace control_enter(struct fixture_control *control)
{
	struct kd_task_storage *storage = NULL;
	unsigned long origin_gs;
	int result;

	if (!runtime || worker_count || control->entered ||
	    smp_load_acquire(&current->kd_root_context))
		return -EBUSY;
	preempt_disable();
	rdmsrl(MSR_GS_BASE, origin_gs);
	preempt_enable();
	result = kd_jit_runtime_enter_current(runtime, origin_gs, &storage);
	/* Non-NULL failed setup is still retained for exact leave/real do_exit. */
	control->entered = storage != NULL;
	return result;
}

static int notrace control_leave(struct fixture_control *control)
{
	struct kd_task_root_context *root = smp_load_acquire(&current->kd_root_context);
	struct kd_execution_binding *binding;
	bool pending;
	int result;

	if (!control->entered || !root || !root->attached || root->task != current ||
	    !root->storage || !root->lifecycle || root->aux_entry)
		return -EPERM;
	binding = smp_load_acquire(&root->core.binding);
	result = kd_jit_runtime_leave_current(root->storage, binding, &pending);
	if (!result)
		control->entered = false;
	/* No root/storage/binding access after successful lifecycle reclamation. */
	return result;
}

static ssize_t notrace control_read(struct file *file, char __user *output, size_t size, loff_t *position)
{
	char buffer[2048];
	unsigned int index, finished = 0;
	unsigned long completed = 0, calls = 0, errors = 0, core_errors = 0, origin_errors = 0;
	unsigned long total_a = 0, total_b = 0;
	struct kd_task_root_context *self;
	struct kd_execution_binding *binding = NULL;
	bool own = false, native = false, managed = false;
	int length;

	(void)file;
	mutex_lock(&control_mutex);
	/* This is the actual calling task on its ordinary native stack. Snapshot
	 * only identities; no source GPR/cursor or packet contents are copied.
	 */
	self = smp_load_acquire(&current->kd_root_context);
	if (self && self->attached && self->task == current && !self->aux_entry) {
		own = self->core.origin == current;
		managed = self->lifecycle && self->storage;
		binding = smp_load_acquire(&self->core.binding);
		native = own && binding && binding->state == &self->core &&
			binding->task == current && binding->kind == KD_EXECUTION_NATIVE;
	}
	for (index = 0; index < worker_count; ++index) {
		finished += smp_load_acquire(&workers[index].finished);
		completed += READ_ONCE(workers[index].completed);
		calls += READ_ONCE(workers[index].call_effects);
		core_errors += READ_ONCE(workers[index].core_errors);
		origin_errors += READ_ONCE(workers[index].origin_errors);
		errors += READ_ONCE(workers[index].error) != 0;
	}
	for (index = 0; index < FIXTURE_MAX_ITERATIONS; ++index) {
		total_a += READ_ONCE(protected_a[index]);
		total_b += READ_ONCE(protected_b[index]);
	}
	length = scnprintf(buffer, sizeof(buffer),
		"evidence=kernel-mechanism mode=%u workers=%u finished=%u iterations=%u completed=%lu calls=%lu a=%lu b=%lu errors=%lu core_errors=%lu origin_errors=%lu source_start=%px source_size=%u step_start=%px step_size=%u locks_clear=%u runtime=%u self_pid=%d self_root=%016lx self_core=%016lx self_regs=%016lx self_binding=%016lx self_own=%u self_native=%u self_managed=%u\n",
		requested_mode, worker_count, finished, requested_iterations, completed, calls,
		total_a, total_b, errors, core_errors, origin_errors,
		fixture_source_body, source_size, fixture_source_step, step_size,
		fixture_locks_clear(), runtime != NULL, task_pid_nr(current), (unsigned long)self,
		self ? (unsigned long)&self->core : 0UL,
		self ? (unsigned long)&self->core.regs : 0UL, (unsigned long)binding,
		own, native, managed);
	mutex_unlock(&control_mutex);
	return simple_read_from_buffer(output, size, position, buffer, length);
}

static ssize_t notrace control_write(struct file *file, const char __user *input, size_t size, loff_t *position)
{
	char buffer[96];
	struct fixture_control *control = file->private_data;
	unsigned int mode, count, iterations;
	int used = 0, result = -EINVAL;

	(void)position;
	if (!control || control->owner != current)
		return -EPERM;
	if (!size || size >= sizeof(buffer) || copy_from_user(buffer, input, size))
		return -EINVAL;
	buffer[size] = 0;
	mutex_lock(&control_mutex);
	if (sscanf(buffer, "start %u %u %u %n", &mode, &count, &iterations, &used) == 3 &&
	    used > 0 && !buffer[used])
		result = start_workers(mode, count, iterations);
	else if (sysfs_streq(buffer, "enter"))
		result = control_enter(control);
	else if (sysfs_streq(buffer, "leave"))
		result = control_leave(control);
	else if (sysfs_streq(buffer, "stop"))
		result = stop_workers();
	else if (sysfs_streq(buffer, "destroy")) {
		if (worker_count || !fixture_locks_clear()) {
			result = -EBUSY;
		} else {
			result = runtime ? kd_jit_runtime_destroy(runtime) : 0;
			if (!result) {
				runtime = NULL;
				result = provider ? kd_jit_source_provider_destroy(provider) : 0;
				if (!result)
					provider = NULL;
			}
		}
	}
	mutex_unlock(&control_mutex);
	return result ? result : size;
}

static const struct file_operations control_operations = {
	.owner = THIS_MODULE, .open = control_open, .release = control_release,
	.read = control_read, .write = control_write, .llseek = default_llseek,
};
static struct miscdevice control_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_runtime_fixture_ctl",
	.fops = &control_operations, .mode = 0600,
};

#define SYMBOL_BYTES(text) { .data = (text), .length = sizeof(text) - 1 }

/* The target finalizes module-owned executable dependency pages before init.
 * Copy those exact ordinary bytes under the same immutable-text/module hold as
 * the two ELF-sized source regions. No dependency instruction is modeled here.
 */
static int __init notrace fixture_regions(struct kd_jit_source_load_region **out,
		unsigned int *out_count)
{
	struct kd_jit_source_load_region *regions;
	unsigned int pages = 0, count, index, prior;
	size_t dependency_bytes, total;

	if (!dependency_page_limit || !total_source_byte_limit)
		return -EINVAL;
#ifdef CONFIG_MITIGATION_ITS
	if (THIS_MODULE->arch.its_pages.num < 0 ||
	    (THIS_MODULE->arch.its_pages.num && !THIS_MODULE->arch.its_pages.pages))
		return -EINVAL;
	pages = THIS_MODULE->arch.its_pages.num;
#endif
	if (pages > dependency_page_limit || check_add_overflow(2U, pages, &count) ||
	    check_mul_overflow((size_t)pages, (size_t)PAGE_SIZE, &dependency_bytes) ||
	    check_add_overflow((size_t)source_size, (size_t)step_size, &total) ||
	    check_add_overflow(total, dependency_bytes, &total) || total > total_source_byte_limit)
		return -E2BIG;
	regions = kcalloc(count, sizeof(*regions), GFP_KERNEL);
	if (!regions)
		return -ENOMEM;
	regions[0] = (struct kd_jit_source_load_region) { (unsigned long)fixture_source_body, source_size };
	regions[1] = (struct kd_jit_source_load_region) { (unsigned long)fixture_source_step, step_size };
#ifdef CONFIG_MITIGATION_ITS
	for (index = 0; index < pages; ++index) {
		unsigned long start = (unsigned long)THIS_MODULE->arch.its_pages.pages[index];

		if (!start || !PAGE_ALIGNED(start))
			goto invalid;
		regions[index + 2] = (struct kd_jit_source_load_region) { start, PAGE_SIZE };
	}
#endif
	for (index = 0; index < count; ++index) {
		unsigned long start = regions[index].start, last;
		size_t length = regions[index].length;

		if (!length || length - 1 > ~0UL - start)
			goto invalid;
		last = start + length - 1;
		if (index < 2 && (!within_module_mem_type(start, THIS_MODULE, MOD_TEXT) ||
				  !within_module_mem_type(last, THIS_MODULE, MOD_TEXT)))
			goto invalid;
		for (prior = 0; prior < index; ++prior) {
			unsigned long other = regions[prior].start;
			unsigned long other_last = other + regions[prior].length - 1;

			if (start <= other_last && other <= last)
				goto invalid;
		}
	}
	configuration_identity.dependency_pages = pages;
	configuration_identity.source_bytes = total;
	*out = regions;
	*out_count = count;
	return 0;
invalid:
	kfree(regions);
	return -EINVAL;
}

static int __init notrace fixture_init(void)
{
	struct kd_jit_source_load_region *regions;
	struct module *modules[] = { THIS_MODULE };
	struct kd_jit_source_provider_args source;
	struct kd_jit_runtime_config config;
	unsigned int index, region_count;
	int result;

	if (!gs_verified || !immutable_text || !auxiliary_contract || !source_version ||
	    !*source_version || strnlen(source_version, 257) > 256 ||
	    !source_size || source_size > 65536 || !step_size || step_size > 65536)
		return -EINVAL;
	configuration_identity.gs_offset = gs_offset;
	configuration_identity.source_size = source_size;
	configuration_identity.step_size = step_size;
	configuration_identity.dependency_page_limit = dependency_page_limit;
	configuration_identity.total_source_byte_limit = total_source_byte_limit;
	result = fixture_regions(&regions, &region_count);
	if (result)
		return result;
	source = (struct kd_jit_source_provider_args) {
		.contract = KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES,
		.version = (const unsigned char *)source_version, .version_length = strlen(source_version),
		.regions = regions, .region_count = region_count,
		.configuration_identity = &configuration_identity, .load_identity = &load_identity,
		.current_task_gs_offset = gs_offset, .modules = modules, .module_count = ARRAY_SIZE(modules),
	};
	result = kd_jit_source_provider_create(&source, &provider);
	kfree(regions);
	if (result)
		return result;
	config = (struct kd_jit_runtime_config) {
		.source = provider, .feedback_capacity = 4096, .cycle_capacity = 32, .image_capacity = 16,
		.claim_capacity = 4096,
		.compiled = { .code_capacity = 128 * 1024, .artifact_capacity = 512 * 1024,
			.flat_capacity = 256 * 1024, .entry_capacity = 64, .source_capacity = 4096,
			.observation_capacity = 4096 },
		.symbols = { .descriptor = SYMBOL_BYTES("kd_fixture_image"),
			.source = SYMBOL_BYTES("kd_fixture_epoch"), .producer = SYMBOL_BYTES("kd_fixture_producer"),
			.entry = SYMBOL_BYTES("kd_fixture_entry") },
		/* Runtime exports its exact ordinary API entry addresses. The generic
		 * host scanner annotates actual source CALL sites before publication.
		 */
		.boundaries = NULL, .boundary_count = 0,
		.channel_name = "kd_runtime_fixture", .owner = THIS_MODULE, .frame_capacity = 2 * 1024 * 1024,
		.request_capacity = FIXTURE_REQUESTS, .auxiliary_bytes = FIXTURE_AUXILIARY_BYTES,
		.required_control_bytes = FIXTURE_CONTROL_BYTES, .proxy_limit = 16,
	};
	for (index = 0; index < FIXTURE_MAX_ITERATIONS; ++index) {
		kd_mutex_init(&lock_a[index]);
		kd_mutex_init(&lock_b[index]);
	}
	init_completion(&start_gate);
	result = kd_jit_runtime_create(&config, &runtime);
	if (result) {
		if (runtime) {
			BUG_ON(kd_jit_runtime_destroy(runtime));
			runtime = NULL;
		}
		goto source_cleanup;
	}
	result = misc_register(&control_device);
	if (!result)
		return 0;
	/* No task, code image or host observer has entered this private setup. */
	BUG_ON(kd_jit_runtime_destroy(runtime));
	runtime = NULL;
source_cleanup:
	{
		int closed = kd_jit_source_provider_close(provider);

		BUG_ON(closed && closed != -EALREADY);
	}
	BUG_ON(kd_jit_source_provider_destroy(provider));
	provider = NULL;
	return result;
}

static void __exit notrace fixture_exit(void)
{
	/* Normal unload is possible only after explicit stop, channel archive/END
	 * and destroy. Provider/module and open-control refs keep earlier code live.
	 */
	BUG_ON(worker_count || runtime || provider);
	misc_deregister(&control_device);
}

module_init(fixture_init);
module_exit(fixture_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Ordinary kdlock mutex runtime kernel mechanism fixture (unrun source)");
