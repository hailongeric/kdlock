// SPDX-License-Identifier: GPL-2.0-only
/* Ordinary-lock kernel mechanism fixture. */
#if defined(KD_FIXTURE_SPIN) || defined(KD_FIXTURE_RWLOCK)
#define KD_FIXTURE_ATOMIC
#endif
#if defined(KD_FIXTURE_RWSEM) || defined(KD_FIXTURE_RWLOCK)
#define KD_FIXTURE_READERS
#endif
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
#include <linux/poll.h>
#include <linux/limits.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <asm/msr.h>
#include <asm/msr-index.h>

#include "kernel/mutex.h"
#include "kernel/runtime.h"
#include "kernel/observation.h"
#include "kernel/task_state.h"
#if defined(KD_FIXTURE_ATOMIC) || defined(KD_FIXTURE_READERS)
#include <linux/cpu.h>
#include <linux/ktime.h>
static unsigned int holder_timeout_ms;
module_param(holder_timeout_ms, uint, 0444);
MODULE_PARM_DESC(holder_timeout_ms, "Explicit maximum holder gate wait in milliseconds");
#endif
#ifdef KD_FIXTURE_ATOMIC
#define FIXTURE_SPIN_CPU_COUNT 5U
#define FIXTURE_SPIN_MISS_MODE 3U
#define FIXTURE_SPIN_NATIVE_MODE 4U
static unsigned int spin_cpus[FIXTURE_SPIN_CPU_COUNT];
static unsigned int spin_cpu_count;
module_param_array(spin_cpus, uint, &spin_cpu_count, 0444);
MODULE_PARM_DESC(spin_cpus, "Distinct online CPUs for the five atomic roles");
#endif
#if defined(KD_FIXTURE_RWSEM)
#include "include/kd_rwsem_api.h"
typedef struct kd_rwsem fixture_lock_t;
#define fixture_lock_init kd_rwsem_init
#define fixture_lock_acquire kd_rwsem_down_write
#define fixture_lock_release kd_rwsem_up_write
#define fixture_read_acquire kd_rwsem_down_read
#define fixture_read_release kd_rwsem_up_read
#define fixture_downgrade kd_rwsem_downgrade_write
#define FIXTURE_NAME "kd_rwsem_runtime_fixture"
#define FIXTURE_MAX_MODE 12U
#define FIXTURE_FAMILY KD_LOCK_FAMILY_RWSEM
static const struct kd_jit_runtime_boundary reader_boundaries[] = {
 { (unsigned long)kd_rwsem_down_read_entry_asm, KD_JIT_RUNTIME_LOCK },
 { (unsigned long)kd_rwsem_up_read_entry_asm, KD_JIT_RUNTIME_UNLOCK },
 { (unsigned long)kd_rwsem_down_write_entry_asm, KD_JIT_RUNTIME_LOCK },
 { (unsigned long)kd_rwsem_up_write_entry_asm, KD_JIT_RUNTIME_UNLOCK },
 { (unsigned long)kd_rwsem_downgrade_write_entry_asm, KD_JIT_RUNTIME_MODE_CHANGE },
};
static struct kd_mutex *fixture_queue(fixture_lock_t *lock) { return &lock->core.queue; }
#elif defined(KD_FIXTURE_RWLOCK)
#include "include/kd_rwlock_api.h"
typedef struct kd_rwlock fixture_lock_t;
#define fixture_lock_init kd_rwlock_init
#define fixture_lock_acquire kd_rwlock_write_lock
#define fixture_lock_release kd_rwlock_write_unlock
#define fixture_read_acquire kd_rwlock_read_lock
#define fixture_read_release kd_rwlock_read_unlock
#define FIXTURE_NAME "kd_rwlock_runtime_fixture"
#define FIXTURE_MAX_MODE 12U
#define FIXTURE_FAMILY KD_LOCK_FAMILY_RWLOCK
static const struct kd_jit_runtime_boundary reader_boundaries[] = {
 { (unsigned long)kd_rwlock_read_lock_entry_asm, KD_JIT_RUNTIME_LOCK },
 { (unsigned long)kd_rwlock_read_unlock_entry_asm, KD_JIT_RUNTIME_UNLOCK },
 { (unsigned long)kd_rwlock_write_lock_entry_asm, KD_JIT_RUNTIME_LOCK },
 { (unsigned long)kd_rwlock_write_unlock_entry_asm, KD_JIT_RUNTIME_UNLOCK },
};
static struct kd_mutex *fixture_queue(fixture_lock_t *lock) { return &lock->core.queue; }
#else
#ifdef KD_FIXTURE_SPIN
#include "include/kd_spin_api.h"

static const struct kd_jit_runtime_boundary spin_boundaries[] = {
	{ (unsigned long)kd_spin_lock_entry_asm, KD_JIT_RUNTIME_LOCK },
	{ (unsigned long)kd_spin_unlock_entry_asm, KD_JIT_RUNTIME_UNLOCK },
};

typedef struct kd_spinlock fixture_lock_t;
#define fixture_lock_init kd_spin_init
#define fixture_lock_acquire kd_spin_lock
#define fixture_lock_release kd_spin_unlock
#define FIXTURE_NAME "kd_spin_runtime_fixture"
#define FIXTURE_MAX_MODE 4U


static struct kd_mutex *fixture_queue(fixture_lock_t *lock)
{
	return &lock->queue;
}
#else
#include "include/kd_mutex_api.h"

typedef struct kd_mutex fixture_lock_t;
#define fixture_lock_init kd_mutex_init
#define fixture_lock_acquire kd_mutex_lock
#define fixture_lock_release kd_mutex_unlock
#define FIXTURE_NAME "kd_runtime_fixture"
#define FIXTURE_MAX_MODE 2U

static struct kd_mutex *fixture_queue(fixture_lock_t *lock)
{
	return lock;
}
#endif

#endif

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
static unsigned long builtin_source_start;
static unsigned long builtin_source_size;
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
MODULE_PARM_DESC(gs_offset, "Actual running-target current_task GS offset, verified from its kernel ELF/source");
MODULE_PARM_DESC(gs_verified, "Operator supplied the exact running-target GS/configuration receipt");
MODULE_PARM_DESC(immutable_text, "Module/source dependencies remain unpatched through final source/native users");
MODULE_PARM_DESC(auxiliary_contract, "Operator admits this target's task-owned auxiliary stack/context contract");
MODULE_PARM_DESC(source_size, "Exact fixture_source_body ELF symbol size from this module binary");
MODULE_PARM_DESC(step_size, "Exact fixture_source_step ELF symbol size from this module binary");
MODULE_PARM_DESC(dependency_page_limit, "Explicit maximum module dependency pages and built-in spans");
MODULE_PARM_DESC(total_source_byte_limit, "Explicit maximum total copied body, callee and dependency bytes");
MODULE_PARM_DESC(builtin_source_start, "Optional exact built-in executable source span start");
MODULE_PARM_DESC(builtin_source_size, "Optional nonempty source span contained in one page");
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
	unsigned int role;
#ifdef KD_FIXTURE_ATOMIC
	unsigned int cpu;
	unsigned int ready_cpu;
	unsigned int preempt_base;
	unsigned long pin_checks;
	unsigned long pin_errors;
	unsigned long miss_checks;
#endif
#ifdef KD_FIXTURE_READERS
	unsigned long rw_effects, rw_post_effects, rw_native_checks, rw_errors, rw_read_attempts;
	bool rw_scene;
#endif
	bool scene;
	bool scene_ready;
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

static fixture_lock_t lock_a[FIXTURE_MAX_ITERATIONS];
static fixture_lock_t lock_b[FIXTURE_MAX_ITERATIONS];
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
	unsigned long builtin_source_start;
	unsigned long builtin_source_size;
	size_t source_bytes;
} configuration_identity;

static int notrace worker_main(void *argument);
static int notrace stop_workers(void);
static bool notrace fixture_locks_clear(void);
#ifdef KD_FIXTURE_ATOMIC
/* These samples run on the native task outside the supplied JIT regions. */
static void notrace fixture_spin_sample(struct fixture_worker *worker, unsigned int held)
{
	worker->pin_checks++;
	if (current != worker->expected_task || raw_smp_processor_id() != worker->cpu ||
	    irqs_disabled() || preempt_count() != worker->preempt_base + held * PREEMPT_OFFSET) {
		worker->pin_errors++;
		worker->error = -EUCLEAN;
	}
}
#endif

static void notrace fixture_wake_worker(struct fixture_worker *worker, unsigned int index)
{
#ifdef KD_FIXTURE_ATOMIC
	worker->cpu = spin_cpus[index];
	kthread_bind(worker->task, worker->cpu);
#endif
	wake_up_process(worker->task);
}

#ifdef KD_FIXTURE_READERS
static bool rw_scene_active;
static unsigned int rw_scene_mode;
static struct completion rw_go[3];
static bool rw_release[3], rw_convert;
static unsigned int rw_stage[3];
static bool rw_attempt[3], rw_inside[3];
static unsigned int rw_writer;
static bool rw_probe_needed, rw_probe_attempted, rw_downgraded;

static void notrace fixture_rw_probe_reader(struct fixture_worker *worker);
#endif
#include "runtime_fixture_observe.inc"

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

#ifdef KD_FIXTURE_READERS
#include "../rwsem/payload/reader_cases.inc"
#endif

#ifdef KD_FIXTURE_ATOMIC
void fixture_spin_miss_checkpoint(struct fixture_worker *worker);

/* A direct CALL outside the image source reaches this native target with A
 * still held. Count that actual call and sample the original task's pin.
 */
noinline notrace __visible void fixture_spin_miss_checkpoint(struct fixture_worker *worker)
{
	worker->miss_checks++;
	fixture_spin_sample(worker, 1);
}

static void notrace fixture_spin_native_body(struct fixture_worker *worker)
{
	unsigned int index = worker->index;

	fixture_spin_sample(worker, 0);
	fixture_lock_acquire(&lock_a[index]);
	fixture_spin_sample(worker, 1);
	fixture_lock_acquire(&lock_b[index]);
	fixture_spin_sample(worker, 2);
	protected_a[index]++;
	protected_b[index]++;
	worker->seen_before = current;
	fixture_source_step(worker);
	fixture_lock_release(&lock_a[index]);
	fixture_spin_sample(worker, 1);
	fixture_lock_release(&lock_b[index]);
	fixture_spin_sample(worker, 0);
}
#endif

/* Mode 2 closes A while B remains open. Source-operation CALL sites and
 * continuations come from the actual exported bytes.
 */
noinline notrace __visible void fixture_source_body(struct fixture_worker *worker)
{
	unsigned int spin, index = worker->index;
#ifdef KD_FIXTURE_READERS
	if (worker->mode >= RW_READ_READ) {
		fixture_rw_source(worker);
		return;
	}
#endif

	fixture_lock_acquire(&lock_a[index]);
	WRITE_ONCE(protected_a[index], READ_ONCE(protected_a[index]) + 1);
	worker->seen_before = current;
	for (spin = 0; spin < FIXTURE_HOLD_ITERATIONS; ++spin)
		barrier();
#ifdef KD_FIXTURE_ATOMIC
	if (worker->mode == FIXTURE_SPIN_MISS_MODE)
		fixture_spin_miss_checkpoint(worker);
#endif
	READ_ONCE(step_entry)(worker);
	if (worker->mode == 0
#ifdef KD_FIXTURE_ATOMIC
	    || worker->mode == FIXTURE_SPIN_MISS_MODE
#endif
	) {
		fixture_lock_release(&lock_a[index]);
		return;
	}
	fixture_lock_acquire(&lock_b[index]);
	WRITE_ONCE(protected_b[index], READ_ONCE(protected_b[index]) + 1);
	READ_ONCE(step_entry)(worker);
	if (worker->mode == 2) {
		fixture_lock_release(&lock_a[index]);
		WRITE_ONCE(protected_b[index], READ_ONCE(protected_b[index]) + 1);
		READ_ONCE(step_entry)(worker);
		fixture_lock_release(&lock_b[index]);
	} else {
		fixture_lock_release(&lock_b[index]);
		fixture_lock_release(&lock_a[index]);
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
#ifdef KD_FIXTURE_ATOMIC
	worker->ready_cpu = raw_smp_processor_id();
	if (worker->ready_cpu != worker->cpu || irqs_disabled()) {
		worker->error = -EUCLEAN;
		goto ready_parked;
	}
#endif
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
	smp_store_release(&worker->scene_ready, true);
	worker_ready();
	wait_for_completion(&start_gate);
	if (worker->scene)
		wait_for_completion(&scene_go[worker->role]);
#ifdef KD_FIXTURE_READERS
	if (worker->rw_scene)
		wait_for_completion(&rw_go[worker->role]);
#endif
	for (iteration = 0; !READ_ONCE(abort_start) && iteration < worker->iterations && !kthread_should_stop(); ++iteration) {
		worker->index = iteration;
#ifdef KD_FIXTURE_ATOMIC
		worker->preempt_base = preempt_count();
		if (worker->mode == FIXTURE_SPIN_NATIVE_MODE)
			fixture_spin_native_body(worker);
		else
#endif
#ifdef KD_FIXTURE_READERS
		if (worker->rw_scene)
			fixture_rw_native_scene(worker);
		else
#endif
		if (worker->scene && worker->role != SCENE_CA && worker->role != SCENE_W)
			scene_single(worker);
		else
			READ_ONCE(body_entry)(worker);
#ifdef KD_FIXTURE_ATOMIC
		fixture_spin_sample(worker, 0);
#endif
		worker->completed++;
		if (
#ifdef KD_FIXTURE_READERS
		    !worker->rw_scene &&
#endif
		    (!worker->scene || worker->role == SCENE_CA || worker->role == SCENE_W) &&
		    (worker->seen_before != worker->expected_task ||
		     worker->seen_inside != worker->expected_task ||
		     worker->seen_pointer != &pointer_value[iteration])) {
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
	WRITE_ONCE(scene_active, false);
#ifdef KD_FIXTURE_READERS
	WRITE_ONCE(rw_scene_active, false);
#endif
	return result;
}

static bool notrace fixture_locks_clear(void)
{
	unsigned int index;

	for (index = 0; index < FIXTURE_MAX_ITERATIONS; ++index) {
#ifdef KD_FIXTURE_READERS
		if (READ_ONCE(lock_a[index].core.readers) || READ_ONCE(lock_b[index].core.readers) ||
		    READ_ONCE(lock_a[index].core.writer) || READ_ONCE(lock_b[index].core.writer) ||
		    READ_ONCE(lock_a[index].core.writer_pending) || READ_ONCE(lock_b[index].core.writer_pending))
			return false;
#endif
		if (READ_ONCE(fixture_queue(&lock_a[index])->tail) || READ_ONCE(fixture_queue(&lock_a[index])->owner) ||
		    READ_ONCE(fixture_queue(&lock_b[index])->tail) || READ_ONCE(fixture_queue(&lock_b[index])->owner))
			return false;
	}
	return true;
}

static int notrace start_workers(unsigned int mode, unsigned int count, unsigned int iterations)
{
	unsigned int index;
	int result;

	if (!runtime || worker_count || mode > FIXTURE_MAX_MODE || !count ||
	    count > FIXTURE_MAX_WORKERS || !iterations || iterations > FIXTURE_MAX_ITERATIONS)
		return -EINVAL;
#ifdef KD_FIXTURE_ATOMIC
	if (count > spin_cpu_count || mode == FIXTURE_SPIN_MISS_MODE)
		return -EINVAL;
#endif
#ifdef KD_FIXTURE_READERS
#ifndef KD_FIXTURE_RWSEM
	if (mode >= RW_DOWNGRADE && mode <= RW_NESTED_DOWNGRADE)
		return -EINVAL;
#endif
#ifndef KD_FIXTURE_ATOMIC
	if (mode == 3 || mode == 4)
		return -EINVAL;
#endif
	rw_probe_needed = false; rw_probe_attempted = false; rw_downgraded = false;
#endif
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
#ifdef KD_FIXTURE_ATOMIC
		worker->task = kthread_create(worker_main, worker, "kd-fixture/%u", index);
#else
		worker->task = kthread_run(worker_main, worker, "kd-fixture/%u", index);
#endif
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
#ifdef KD_FIXTURE_ATOMIC
		fixture_wake_worker(worker, index);
#endif
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
#ifdef KD_FIXTURE_READERS
	char buffer[4096];
	unsigned long rw_effects = 0, rw_post = 0, rw_native = 0, rw_errors = 0;
#else
	char buffer[2048];
#endif
	unsigned int index, finished = 0;
	unsigned long trace_flags, queued, held, child, events, overflow, ready = 0;
	unsigned long completed = 0, calls = 0, errors = 0, core_errors = 0, origin_errors = 0;
	unsigned long total_a = 0, total_b = 0;
#ifdef KD_FIXTURE_ATOMIC
	unsigned long pin_checks = 0, pin_errors = 0, miss_checks = 0;
#endif
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
		if (smp_load_acquire(&workers[index].scene_ready))
			ready |= 1UL << index;
		completed += READ_ONCE(workers[index].completed);
		calls += READ_ONCE(workers[index].call_effects);
		core_errors += READ_ONCE(workers[index].core_errors);
		origin_errors += READ_ONCE(workers[index].origin_errors);
		errors += READ_ONCE(workers[index].error) != 0;
#ifdef KD_FIXTURE_READERS
		rw_effects += READ_ONCE(workers[index].rw_effects);
		rw_post += READ_ONCE(workers[index].rw_post_effects);
		rw_native += READ_ONCE(workers[index].rw_native_checks);
		rw_errors += READ_ONCE(workers[index].rw_errors);
#endif
#ifdef KD_FIXTURE_ATOMIC
		pin_checks += READ_ONCE(workers[index].pin_checks);
		pin_errors += READ_ONCE(workers[index].pin_errors);
		miss_checks += READ_ONCE(workers[index].miss_checks);
#endif
	}
	for (index = 0; index < FIXTURE_MAX_ITERATIONS; ++index) {
		total_a += READ_ONCE(protected_a[index]);
		total_b += READ_ONCE(protected_b[index]);
	}
	raw_spin_lock_irqsave(&event_guard, trace_flags);
	queued = scene_queued; held = scene_held; child = scene_child;
	events = event_count; overflow = event_overflow;
	raw_spin_unlock_irqrestore(&event_guard, trace_flags);
	length = scnprintf(buffer, sizeof(buffer),
		"evidence=kernel-mechanism mode=%u workers=%u finished=%u iterations=%u completed=%lu calls=%lu a=%lu b=%lu errors=%lu core_errors=%lu origin_errors=%lu source_start=%px source_size=%u step_start=%px step_size=%u locks_clear=%u runtime=%u self_pid=%d self_root=%016lx self_core=%016lx self_regs=%016lx self_binding=%016lx self_own=%u self_native=%u self_managed=%u scene=%u ready=%lx queued=%lx held=%lx child=%lx events=%lu overflow=%lu role0=%lx role1=%lx role2=%lx role3=%lx role4=%lx w_core=%lx w_regs=%lx object_a=%lx object_b=%lx\n",
		requested_mode, worker_count, finished, requested_iterations, completed, calls,
		total_a, total_b, errors, core_errors, origin_errors,
		fixture_source_body, source_size, fixture_source_step, step_size,
		fixture_locks_clear(), runtime != NULL, task_pid_nr(current), (unsigned long)self,
		self ? (unsigned long)&self->core : 0UL,
		self ? (unsigned long)&self->core.regs : 0UL, (unsigned long)binding,
		own, native, managed, scene_active, ready, queued, held, child, events, overflow,
		(unsigned long)workers[0].task, (unsigned long)workers[1].task,
		(unsigned long)workers[2].task, (unsigned long)workers[3].task,
		(unsigned long)workers[4].task, workers[4].core_address, workers[4].regs_address,
		(unsigned long)fixture_queue(&lock_a[0]), (unsigned long)fixture_queue(&lock_b[0]));
#ifdef KD_FIXTURE_ATOMIC
	length += scnprintf(buffer + length, sizeof(buffer) - length,
		"pin_checks=%lu pin_errors=%lu miss_checks=%lu w_miss_checks=%lu miss_target=%px cpu0=%u cpu1=%u cpu2=%u cpu3=%u cpu4=%u\n",
		pin_checks, pin_errors, miss_checks, READ_ONCE(workers[SCENE_W].miss_checks),
		fixture_spin_miss_checkpoint, READ_ONCE(workers[0].ready_cpu),
		READ_ONCE(workers[1].ready_cpu), READ_ONCE(workers[2].ready_cpu),
		READ_ONCE(workers[3].ready_cpu), READ_ONCE(workers[4].ready_cpu));
#endif
#ifdef KD_FIXTURE_READERS
	length += scnprintf(buffer + length, sizeof(buffer) - length,
		"rw_effects=%lu rw_post=%lu rw_native=%lu rw_errors=%lu rw_scene=%u rw_scene_mode=%u rw_stage0=%u rw_stage1=%u rw_stage2=%u rw_attempt0=%u rw_attempt1=%u rw_attempt2=%u rw_probe=%u rw_mode=%u w_read_attempts=%lu rw_miss_target=%px\n",
		rw_effects, rw_post, rw_native, rw_errors, rw_scene_active, rw_scene_mode,
		READ_ONCE(rw_stage[0]), READ_ONCE(rw_stage[1]), READ_ONCE(rw_stage[2]),
		READ_ONCE(rw_attempt[0]), READ_ONCE(rw_attempt[1]), READ_ONCE(rw_attempt[2]),
		READ_ONCE(rw_probe_attempted), READ_ONCE(rw_downgraded),
		READ_ONCE(workers[SCENE_W].rw_read_attempts), fixture_rw_native_checkpoint);
#endif
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
	else if (sscanf(buffer, "scene %u %n", &mode, &used) == 1 && used > 0 && !buffer[used])
		result = start_scene(mode);
	else if (sscanf(buffer, "go %u %n", &mode, &used) == 1 && used > 0 && !buffer[used] &&
		 scene_active && mode < SCENE_ROLES) {
		complete_all(&scene_go[mode]); result = 0;
	} else if (sscanf(buffer, "release %u %n", &mode, &used) == 1 && used > 0 && !buffer[used] &&
		 scene_active && (mode == SCENE_HA || mode == SCENE_HB)) {
		fixture_release_holder(mode); result = 0;
	}
#ifdef KD_FIXTURE_READERS
	else if (sscanf(buffer, "readscene %u %n", &mode, &used) == 1 && used > 0 && !buffer[used])
		result = start_rw_scene(mode);
	else if (sscanf(buffer, "readgo %u %n", &mode, &used) == 1 && used > 0 && !buffer[used] &&
		 rw_scene_active && mode < 3) {
		complete_all(&rw_go[mode]); result = 0;
	} else if (sscanf(buffer, "readrelease %u %n", &mode, &used) == 1 && used > 0 && !buffer[used] &&
		 rw_scene_active && mode < 3) {
		smp_store_release(&rw_release[mode], true); result = 0;
	} else if (sysfs_streq(buffer, "readconvert") && rw_scene_active && rw_scene_mode == 1) {
		smp_store_release(&rw_convert, true); result = 0;
	}
#endif
	else if (sysfs_streq(buffer, "enter"))
		result = control_enter(control);
	else if (sysfs_streq(buffer, "leave"))
		result = control_leave(control);
	else if (sysfs_streq(buffer, "stop"))
		result = (scene_active
#ifdef KD_FIXTURE_READERS
			  || rw_scene_active
#endif
			 ) && !scene_finished() ? -EBUSY : stop_workers();
	else if (sysfs_streq(buffer, "destroy")) {
		if (worker_count || !fixture_locks_clear()) {
			result = -EBUSY;
		} else {
			result = runtime ? kd_jit_runtime_destroy(runtime) : 0;
			if (!result) {
				runtime = NULL;
				result = provider ? kd_jit_source_provider_destroy(provider) : 0;
				if (!result) {
					provider = NULL;
					fixture_events_stop();
				}
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
	.minor = MISC_DYNAMIC_MINOR, .name = FIXTURE_NAME "_ctl",
	.fops = &control_operations, .mode = 0600,
};

#define SYMBOL_BYTES(text) { .data = (text), .length = sizeof(text) - 1 }

/* The target finalizes module-owned dependency pages before init. The
 * optional built-in span shares the caller's immutable-text contract and has
 * kernel residency. All regions supply ordinary bytes to the same compiler.
 */
static int __init notrace fixture_regions(struct kd_jit_source_load_region **out,
		unsigned int *out_count)
{
	struct kd_jit_source_load_region *regions;
	unsigned int pages = 0, dependencies, count, index, prior;
	size_t dependency_bytes, total;

	if (!dependency_page_limit || !total_source_byte_limit ||
	    !!builtin_source_start != !!builtin_source_size)
		return -EINVAL;
	if (builtin_source_size &&
	    (builtin_source_size - 1 > ~0UL - builtin_source_start ||
	     (builtin_source_start >> PAGE_SHIFT) !=
	     ((builtin_source_start + builtin_source_size - 1) >> PAGE_SHIFT)))
		return -EINVAL;
#ifdef CONFIG_MITIGATION_ITS
	if (THIS_MODULE->arch.its_pages.num < 0 ||
	    (THIS_MODULE->arch.its_pages.num && !THIS_MODULE->arch.its_pages.pages))
		return -EINVAL;
	pages = THIS_MODULE->arch.its_pages.num;
#endif
	if (check_add_overflow(pages, builtin_source_size ? 1U : 0U, &dependencies) ||
	    dependencies > dependency_page_limit || check_add_overflow(2U, dependencies, &count) ||
	    check_mul_overflow((size_t)pages, (size_t)PAGE_SIZE, &dependency_bytes) ||
	    check_add_overflow(dependency_bytes, (size_t)builtin_source_size, &dependency_bytes) ||
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
	if (builtin_source_size)
		regions[pages + 2] = (struct kd_jit_source_load_region) {
			builtin_source_start, builtin_source_size
		};
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
	configuration_identity.dependency_pages = dependencies;
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
	struct module *modules[] = { THIS_MODULE, NULL };
	struct kd_jit_source_provider_args source;
	struct kd_jit_runtime_config config;
	unsigned int index, region_count;
	int result;

#ifdef KD_FIXTURE_ATOMIC
	BUILD_BUG_ON(SCENE_ROLES != FIXTURE_SPIN_CPU_COUNT);
	if (!PREEMPT_OFFSET || spin_cpu_count != FIXTURE_SPIN_CPU_COUNT || !holder_timeout_ms)
		return -EINVAL;
	for (index = 0; index < spin_cpu_count; ++index) {
		unsigned int prior;

		if (spin_cpus[index] >= nr_cpu_ids || !cpu_online(spin_cpus[index]))
			return -EINVAL;
		for (prior = 0; prior < index; ++prior)
			if (spin_cpus[index] == spin_cpus[prior])
				return -EINVAL;
	}
#endif
#ifdef KD_FIXTURE_RWSEM
	if (!coordination_spins)
		return -EINVAL;
#endif
#ifdef KD_FIXTURE_READERS
	if (!holder_timeout_ms)
		return -EINVAL;
#endif
	if (!gs_verified || !immutable_text || !auxiliary_contract || !source_version ||
	    !*source_version || strnlen(source_version, 257) > 256 ||
	    !source_size || source_size > 65536 || !step_size || step_size > 65536)
		return -EINVAL;
	configuration_identity.gs_offset = gs_offset;
	configuration_identity.source_size = source_size;
	configuration_identity.step_size = step_size;
	configuration_identity.dependency_page_limit = dependency_page_limit;
	configuration_identity.total_source_byte_limit = total_source_byte_limit;
	configuration_identity.builtin_source_start = builtin_source_start;
	configuration_identity.builtin_source_size = builtin_source_size;
	result = fixture_regions(&regions, &region_count);
	if (result)
		return result;
	source = (struct kd_jit_source_provider_args) {
		.contract = KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES,
		.version = (const unsigned char *)source_version, .version_length = strlen(source_version),
		.regions = regions, .region_count = region_count,
		.configuration_identity = &configuration_identity, .load_identity = &load_identity,
		.current_task_gs_offset = gs_offset, .modules = modules,
		.module_count = builtin_source_size ? ARRAY_SIZE(modules) : 1,
	};
	result = fixture_events_start();
	if (result) {
		kfree(regions); return result;
	}
	result = kd_jit_source_provider_create(&source, &provider);
	kfree(regions);
	if (result)
		goto event_cleanup;
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
#ifdef KD_FIXTURE_READERS
		.family = FIXTURE_FAMILY,
		.boundaries = reader_boundaries, .boundary_count = ARRAY_SIZE(reader_boundaries),
#elif defined(KD_FIXTURE_ATOMIC)
		.boundaries = spin_boundaries, .boundary_count = ARRAY_SIZE(spin_boundaries),
#else
		.boundaries = NULL, .boundary_count = 0,
#endif
#ifdef KD_FIXTURE_ATOMIC
		.atomic_spin = true,
#endif
		.channel_name = FIXTURE_NAME, .owner = THIS_MODULE, .frame_capacity = 2 * 1024 * 1024,
		.request_capacity = FIXTURE_REQUESTS, .auxiliary_bytes = FIXTURE_AUXILIARY_BYTES,
		.required_control_bytes = FIXTURE_CONTROL_BYTES, .proxy_limit = 16,
	};
	for (index = 0; index < FIXTURE_MAX_ITERATIONS; ++index) {
		fixture_lock_init(&lock_a[index]);
		fixture_lock_init(&lock_b[index]);
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
	if (!result) {
		result = misc_register(&event_device);
		if (!result)
			return 0;
		misc_deregister(&control_device);
	}
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
event_cleanup:
	fixture_events_stop();
	kvfree(event_rows); event_rows = NULL;
	return result;
}

static void __exit notrace fixture_exit(void)
{
	/* Normal unload is possible only after explicit stop, channel archive/END
	 * and destroy. Provider/module and open-control refs keep earlier code live.
	 */
	BUG_ON(worker_count || runtime || provider);
	fixture_events_stop();
	misc_deregister(&event_device);
	misc_deregister(&control_device);
	kvfree(event_rows);
}

module_init(fixture_init);
module_exit(fixture_exit);
MODULE_LICENSE("GPL");
#ifdef KD_FIXTURE_RWSEM
MODULE_DESCRIPTION("Ordinary kdlock rwsem reader/writer mechanism fixture");
#elif defined(KD_FIXTURE_RWLOCK)
MODULE_DESCRIPTION("Plain kdlock rwlock reader/writer mechanism fixture");
#elif defined(KD_FIXTURE_ATOMIC)
MODULE_DESCRIPTION("Ordinary kdlock spin runtime kernel mechanism fixture");
#else
MODULE_DESCRIPTION("Ordinary kdlock mutex runtime kernel mechanism fixture (unrun source)");
#endif
