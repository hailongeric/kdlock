#include <stddef.h>
/* SPDX-License-Identifier: GPL-2.0 */
/* Substitute primitives around production frame allocation, ledger and cleanup.
 * Compare complete failed packets and backend release order, not Linux locks
 * or post-JIT rollback. The exit observer uses substituted PID/RCU/time;
 * actual waiter exit and wrapper/GS execution require their separate gates. */
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

struct task_struct {
	int pid;
};
struct list_head {
	struct list_head *next, *prev;
};
/* List operations are substitutes; the production pop predicate, packet and
 * source-lease accounting remain under test. No waiter is executed here. */
#define INIT_LIST_HEAD(head)                         \
	do {                                        \
		(head)->next = (head)->prev = (head); \
	} while (0)
static bool list_empty(const struct list_head *head)
{
	return head->next == head;
}
#include <stdint.h>
typedef uint8_t u8;
typedef uint16_t u16;
static bool kd_hotlock_role_trace;
typedef uint64_t u64;
#include "frame_types.h"

static struct kd_exec_context kd_exec_context[2];
static struct task_struct owners[] = { { 11 }, { 12 } };
static struct task_struct waiters[KD_EXEC_MAX_NESTING];
static struct task_struct *current = &owners[0];
static unsigned int cpu, checks, failures;
static unsigned int fixture_preempt = 1;
static bool fixture_irq;
static unsigned long kd_exec_invariant_failures;
static char report[1024];
typedef unsigned int atomic_t;
static struct kd_spin_continuation_stack request_storage;
static struct kd_spin_continuation_stack *kd_spin_continuations = &request_storage;
#define request_pool request_storage.records
#define BUG_ON(x) do { if (x) { fprintf(stderr, "invalid continuation release\n"); __builtin_trap(); } } while (0)
#define atomic_read_acquire(p) (*(p))
#define atomic_set(p,v) (*(p) = (v))
#define atomic_dec(p) (--*(p))
#define atomic_dec_and_test(p) (--*(p) == 0)
struct qspinlock {
	atomic_t val;
};
typedef struct qspinlock raw_spinlock_t;
struct mutex {
	bool locked;
};
#define ATOMIC_INIT(value) (value)
#define atomic_read(p) (*(p))
#define raw_smp_processor_id() cpu
#define preempt_count() fixture_preempt
#define irqs_disabled() fixture_irq
#define pr_info(...) ((void)snprintf(report, sizeof(report), __VA_ARGS__))
#define KDLOCK_SELFTEST 1
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
#define PIDTYPE_PID 0
#define HZ 10
#define time_before(left, right) ((left) < (right))
#define rcu_read_lock() ((void)0)
#define rcu_read_unlock() ((void)0)

/* A PID ref is deliberately separate from its task link. Detachment can
 * occur while the observer still has this identity, without pinning a task. */
static struct {
	struct task_struct *task;
	unsigned int refs;
} exit_pid;
static unsigned long jiffies;
static unsigned int exit_behavior, exit_polls;
static struct kd_exec_frame *exit_frame;

static void *get_task_pid(struct task_struct *task, int type)
{
	(void)type;
	exit_pid.task = task;
	exit_pid.refs++;
	return &exit_pid;
}

static struct task_struct *pid_task(const void *pid, int type)
{
	(void)pid;
	(void)type;
	return exit_pid.task;
}

static void put_pid(const void *pid)
{
	(void)pid;
	if (!exit_pid.refs)
		failures++;
	else
		exit_pid.refs--;
}


static unsigned int atomic_cmpxchg(atomic_t *value, unsigned int old,
				   unsigned int replacement)
{
	unsigned int before = *value;

	if (before == old)
		*value = replacement;
	return before;
}

#define this_cpu_ptr(p) (&(*(p))[cpu])
#define READ_ONCE(x) (x)
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, value) (*(p) = (value))
#define atomic64_inc(p) (++*(p))
#define WARN_ON_ONCE(x) ((void)(x))
#define KD_PR_INFO(...)                      \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
static int kd_mutex_nested_unlock(struct mutex *lock);
static void kd_mutex_note_nested_abort_release(void);
static void kd_spin_debug_nested_unlock(raw_spinlock_t *lock);
static void origin_raw_spin_unlock(raw_spinlock_t *lock);
static int kd_spin_nested_unlock(struct qspinlock *lock);
static int kd_spin_nested_shadow_remove(struct qspinlock *lock);
static unsigned int probe_calls;
/* Count the real allocator's lease balance; module and retirement primitives
 * are exercised separately by test_source_lifetime, not emulated as frames. */
static unsigned int source_frames;
static bool source_open = true;
static bool kd_source_is_open(void) { return source_open; }
static bool kd_source_frame_get(void)
{
	if (!source_open)
		return false;
	source_frames++;
	return true;
}
static void kd_source_frame_put(void)
{
	if (!source_frames)
		failures++;
	else
		source_frames--;
}

static struct kd_exec_frame *
counted_frame_push(const struct pt_regs *regs, unsigned long entry,
		   unsigned long outer,
		   unsigned int held, unsigned long gs,
		   struct task_struct *task)
{
	probe_calls++;
	return kd_exec_frame_push(regs, entry, outer, held,
				  gs, task);
}

#include "frame_code.h"

#define CHECK(expr)                                                     \
	do {                                                            \
		checks++;                                               \
		if (!(expr)) {                                          \
			fprintf(stderr, "FAIL line %d: %s\n", __LINE__, \
				#expr);                                 \
			failures++;                                     \
		}                                                       \
	} while (0)

/* Refusals must preserve the entire context and its lease, not just depth. */
#define REJECTS(expr, error)                                                \
	do {                                                              \
		struct kd_exec_context saved = *kd_exec_current_context(); \
		unsigned int leases = source_frames;                       \
		CHECK((expr) == (error));                                  \
		CHECK(!memcmp(&saved, kd_exec_current_context(),            \
			      sizeof(saved)));                            \
		CHECK(source_frames == leases);                           \
	} while (0)



static unsigned long release_order[KD_EXEC_MAX_LOCK_DEPTH];
static unsigned long shadow_order[KD_EXEC_MAX_LOCK_DEPTH];
static unsigned int release_count, shadow_count, abort_notes, outer_releases;
static int unlock_error, shadow_error;

/* Record calls at the physical boundary. The production cleanup chooses the
 * order and must never ask these substitutes to release the outer lock. */
static void released(unsigned long address)
{
	CHECK(address != kd_exec_current_frame()->outer_lock_addr);
	CHECK(release_count < KD_EXEC_MAX_LOCK_DEPTH);
	if (release_count < KD_EXEC_MAX_LOCK_DEPTH)
		release_order[release_count++] = address;
}

static int kd_mutex_nested_unlock(struct mutex *lock)
{
	CHECK(lock->locked);
	if (unlock_error)
		return unlock_error;
	lock->locked = false;
	released((unsigned long)lock);
	return 0;
}

static void kd_mutex_note_nested_abort_release(void)
{
	abort_notes++;
}

static void kd_spin_debug_nested_unlock(raw_spinlock_t *lock)
{
	CHECK(lock->val == 1);
}

static void origin_raw_spin_unlock(raw_spinlock_t *lock)
{
	CHECK(lock->val == 1);
	lock->val = 0;
	released((unsigned long)lock);
}

static int kd_spin_nested_unlock(struct qspinlock *lock)
{
	if (unlock_error)
		return unlock_error;
	origin_raw_spin_unlock(lock);
	return KD_SPIN_NESTED_UNLOCK_OK;
}

static int kd_spin_nested_shadow_remove(struct qspinlock *lock)
{
	CHECK(!lock->val && shadow_count < KD_EXEC_MAX_LOCK_DEPTH);
	if (shadow_count < KD_EXEC_MAX_LOCK_DEPTH)
		shadow_order[shadow_count++] = (unsigned long)lock;
	return shadow_error;
}

static struct pt_regs registers(unsigned int seed)
{
	struct pt_regs regs;
	unsigned char *bytes = (unsigned char *)&regs;
	unsigned int i;

	for (i = 0; i < sizeof(regs); i++)
		bytes[i] = 1 + (seed + i) % 254;
	return regs;
}

static struct kd_exec_frame *push(unsigned int index)
{
	struct pt_regs regs = registers(index);
	struct kd_exec_context before = *kd_exec_current_context();
	struct kd_exec_frame *frame;

	waiters[index].pid = 100 + index;
	frame = kd_exec_frame_push(&regs, 0x1000 + index, 0x2000 + index, index + 1,
				   0x3000 + index, &waiters[index]);
	CHECK(frame == &kd_exec_current_context()->frames[index]);
	if (!frame)
		return NULL;
	CHECK(frame->parent ==
	      (index ? &kd_exec_current_context()->frames[index - 1] : NULL));
	CHECK(!memcmp(before.frames, kd_exec_current_context()->frames,
		      index * sizeof(*frame)));
	CHECK(!memcmp(&frame->regs, &regs, sizeof(regs)));
	CHECK(frame->depth == index && frame->held_lock_depth == index + 1);
	CHECK(frame->entry_ip == 0x1000 + index &&
	      frame->outer_lock_addr == 0x2000 + index);
	CHECK(frame->gsbase == 0x3000 + index &&
	      frame->logical_task == &waiters[index]);
	CHECK(frame->logical_pid == 100 + (int)index &&
	      !frame->request_frame && !frame->regs_ref);
	CHECK(!frame->batch_lease && !frame->delegated_lock_addr);
	CHECK(kd_exec_current_frame() == frame && !kd_exec_context_busy());
	CHECK(kd_exec_current_context()->owner == current);
	CHECK(kd_exec_context_validate(kd_exec_current_context()));
	/* Fields not interpreted by admission still must survive a full refusal. */
	memset(&frame->saved_combiner, 0x50 + index,
	       sizeof(frame->saved_combiner));
	return frame;
}

static void refused(const struct pt_regs *regs, unsigned long gs,
		    struct task_struct *task, unsigned int held)
{
	struct kd_exec_context before = *kd_exec_current_context();
	struct kd_exec_frame *frame = kd_exec_current_frame();
	unsigned int before_refs = source_frames;

	CHECK(!kd_exec_frame_push(regs, 0x1000, 0x2000, held, gs,
				  task));
	CHECK(!memcmp(&before, kd_exec_current_context(), sizeof(before)));
	CHECK(kd_exec_current_frame() == frame);
	CHECK(source_frames == before_refs);
}

static void refused_pop(struct kd_exec_frame *frame, int error)
{
	struct pt_regs output = registers(71), before = output;

	REJECTS(kd_exec_frame_pop(frame, &output), error);
	CHECK(!memcmp(&output, &before, sizeof(output)));
}

/* Terminal state is not proof that native routing has drained. Model the
 * producer's registration/request independently, then require pop to preserve
 * every byte and lease until both have gone. Actual ACK delivery is covered by
 * the remote/native protocol fixture and live borrowed-waiter cases. */
static bool refused_native_retirement(struct kd_exec_frame *frame)
{
	unsigned int backend, mask, before_failures = failures;
	bool original_backend = frame->mutex_backend;
	unsigned long request_cookie = 0x12345678;
	struct list_head routing;

	for (backend = 0; backend < 2; backend++) {
		frame->mutex_backend = backend;
		for (mask = 1; mask <= 3; mask++) {
			INIT_LIST_HEAD(&routing);
			INIT_LIST_HEAD(&frame->native_link);
			frame->native_request =
				mask & 1 ? (void *)&request_cookie : NULL;
			if (mask & 2) {
				routing.next = routing.prev = &frame->native_link;
				frame->native_link.next =
					frame->native_link.prev = &routing;
			}
			refused_pop(frame, -EBUSY);
			/* A bad pop may have cleared this frame and its lease.
			 * Stop before accessing the retired storage again. */
			if (failures != before_failures)
				return false;
			CHECK(request_cookie == 0x12345678);
			CHECK(routing.next ==
			      (mask & 2 ? &frame->native_link : &routing));
			CHECK(routing.prev == routing.next);
			frame->native_request = NULL;
			INIT_LIST_HEAD(&routing);
			INIT_LIST_HEAD(&frame->native_link);
			CHECK(list_empty(&frame->native_link));
		}
	}
	frame->mutex_backend = original_backend;
	return failures == before_failures;
}

static void exercise(unsigned int depth)
{
	struct pt_regs regs = registers(99), output;
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame;
	unsigned int i;

	kd_exec_context_reset(ctx);
	CHECK(!kd_exec_current_frame() && !kd_exec_context_busy());
	for (i = 0; i < depth; i++) {
		if (!push(i))
			return;
	}
	refused(NULL, 1, current, 1);
	refused(&regs, 0, current, 1);
	refused(&regs, 1, NULL, 1);
	source_open = false;
	refused(&regs, 1, current, 1);
	source_open = true;
	if (depth == KD_EXEC_MAX_NESTING) {
		for (i = 0; i < 4; i++)
			refused(&regs, 1, current, 1);
	} else {
		refused(&regs, 1, current, KD_EXEC_MAX_LOCK_DEPTH + 1);
	}
	if (depth) {
		current = &owners[1];
		CHECK(kd_exec_context_busy() && !kd_exec_current_frame());
		refused(&regs, 1, current, 1);
		refused_pop(&ctx->frames[depth - 1], -EINVAL);
		current = &owners[0];
		frame = kd_exec_current_frame();
		CHECK(frame == &ctx->frames[depth - 1]);
		/* Invalid lower state is a separate refusal, not pool exhaustion. */
		ctx->frames[0].gsbase = 0;
		refused(&regs, 1, current, 1);
		ctx->frames[0].gsbase = 0x3000;
		refused_pop(frame, -EBUSY);
		if (depth > 1)
			refused_pop(&ctx->frames[0], -EINVAL);
		/* A terminal state alone cannot free a live remote dependency. */
		kd_exec_frame_set_state(frame, KD_EXEC_FRAME_ERROR);
		frame->remote_result = KD_EXEC_REMOTE_WAITING;
		refused_pop(frame, -EBUSY);
		frame->remote_result = KD_EXEC_REMOTE_NATIVE;
		refused_pop(frame, -EBUSY);
		frame->remote_result = KD_EXEC_REMOTE_IDLE;
		frame->resume_target = &ctx->frames[0];
		refused_pop(frame, -EBUSY);
		frame->resume_target = NULL;
		frame->remote_request = (void *)&regs;
		refused_pop(frame, -EBUSY);
		frame->remote_request = NULL;
		if (!refused_native_retirement(frame))
			return;
	}
	while (ctx->depth) {
		struct kd_exec_context before;

		frame = kd_exec_current_frame();
		regs = frame->regs;
		kd_exec_frame_set_state(frame, KD_EXEC_FRAME_ERROR);
		before = *ctx;
		CHECK(kd_exec_frame_pop(frame, &output) == 0);
		CHECK(!memcmp(&regs, &output, sizeof(regs)));
		CHECK(!memcmp(before.frames, ctx->frames,
			      ctx->depth * sizeof(*frame)));
		CHECK(kd_exec_frame_state(frame) == KD_EXEC_FRAME_UNUSED &&
		      !kd_exec_frame_validate(frame));
		CHECK(kd_exec_context_validate(ctx));
	}
	CHECK(!ctx->owner && !kd_exec_current_frame());
	CHECK(source_frames == 0);
}

/* Exercise the real dense ledger with heterogeneous metadata. OOO nested pop
 * shifts all columns; an early outer unlock instead retains its ledger entry. */
static void ledger(void)
{
	struct kd_exec_frame *frame = push(0), before;
	unsigned long locks[KD_EXEC_MAX_LOCK_DEPTH], duplicate[2];
	enum kd_exec_lock_kind kinds[KD_EXEC_MAX_LOCK_DEPTH];
	void *nodes[KD_EXEC_MAX_LOCK_DEPTH];
	unsigned int i;

	if (!frame)
		return;
	for (i = 0; i < KD_EXEC_MAX_LOCK_DEPTH; i++) {
		locks[i] = frame->outer_lock_addr + i;
		kinds[i] = KD_EXEC_LOCK_FAST + i % KD_EXEC_LOCK_NATIVE;
		nodes[i] = &locks[i];
	}
	CHECK(kd_exec_frame_set_lock_stack(frame, locks, 1) == 0);
	duplicate[0] = duplicate[1] = locks[0];
	REJECTS(kd_exec_frame_set_lock_stack(frame, duplicate, 2), -EDEADLK);
	REJECTS(kd_exec_frame_set_lock_stack(frame, locks + 1, 2), -ENOENT);
	REJECTS(kd_exec_frame_set_lock_stack(frame, NULL, 1), -EINVAL);
	REJECTS(kd_exec_frame_set_lock_stack(frame, locks,
					   KD_EXEC_MAX_LOCK_DEPTH + 1), -E2BIG);
	duplicate[1] = 0;
	REJECTS(kd_exec_frame_set_lock_stack(frame, duplicate, 2), -EINVAL);
	kinds[1] = KD_EXEC_LOCK_NONE;
	REJECTS(kd_exec_frame_set_lock_entries(frame, locks, kinds, nodes,
					     NULL, 2), -EINVAL);
	kinds[1] = KD_EXEC_LOCK_QUEUE_OWNER;
	REJECTS(kd_exec_frame_lock_push(frame, locks[0], KD_EXEC_LOCK_NATIVE,
				      nodes[0]), -EDEADLK);
	REJECTS(kd_exec_frame_lock_push(frame, 0, KD_EXEC_LOCK_NATIVE, NULL),
		-EINVAL);
	REJECTS(kd_exec_frame_lock_push(frame, locks[1], KD_EXEC_LOCK_NONE, NULL),
		-EINVAL);
	if (failures)
		return;
	for (i = 1; i < KD_EXEC_MAX_LOCK_DEPTH; i++)
		CHECK(kd_exec_frame_lock_push(frame, locks[i], kinds[i],
					     nodes[i]) == 0);
	REJECTS(kd_exec_frame_lock_push(frame, 0xFFFF, KD_EXEC_LOCK_NATIVE,
				      NULL), -E2BIG);
	CHECK(kd_exec_frame_lock_mark_released(frame, locks[4]) == 0);
	/* A producer-prepared ledger still passes the same admission checks.
	 * Reusing its columns must preserve every byte, including owner metadata. */
	before = *frame;
	CHECK(kd_exec_frame_set_lock_entries(frame, frame->jit_lock_addr,
		frame->jit_lock_kind, frame->jit_lock_node,
		frame->jit_lock_released, frame->jit_lock_depth) == 0);
	CHECK(!memcmp(&before, frame, sizeof(before)));
	frame->jit_lock_addr[1] = frame->jit_lock_addr[0];
	REJECTS(kd_exec_frame_set_lock_entries(frame, frame->jit_lock_addr,
		frame->jit_lock_kind, frame->jit_lock_node,
		frame->jit_lock_released, frame->jit_lock_depth), -EDEADLK);
	frame->jit_lock_addr[1] = locks[1];
	before = *frame;
	CHECK(kd_exec_frame_lock_pop(frame, locks[3]) == 0);
	CHECK(frame->jit_lock_depth == KD_EXEC_MAX_LOCK_DEPTH - 1 &&
	      frame->held_lock_depth == KD_EXEC_MAX_LOCK_DEPTH - 1);
	for (i = 0; i < KD_EXEC_MAX_LOCK_DEPTH - 1; i++) {
		unsigned int from = i + (i >= 3);

		CHECK(frame->jit_lock_addr[i] == before.jit_lock_addr[from]);
		CHECK(frame->jit_lock_kind[i] == before.jit_lock_kind[from]);
		CHECK(frame->jit_lock_node[i] == before.jit_lock_node[from]);
		CHECK(frame->jit_lock_released[i] == before.jit_lock_released[from]);
	}
	CHECK(!frame->outer_lock_index && kd_exec_frame_validate(frame));
	/* A removed tail is outside the ledger, regardless of its stale bytes. */
	CHECK(!kd_exec_frame_lock_contains(frame, locks[3]));
	REJECTS(kd_exec_frame_lock_pop(frame, 0xFFFF), -ENOENT);

	/* Removing an inherited ancestor shifts the current outer's index too. */
	frame->outer_lock_addr = locks[2];
	frame->held_lock_depth = KD_EXEC_MAX_LOCK_DEPTH;
	frame->outer_lock_depth = 3;
	CHECK(kd_exec_frame_set_lock_entries(frame, locks, kinds, nodes, NULL,
					   KD_EXEC_MAX_LOCK_DEPTH) == 0);
	CHECK(frame->outer_lock_index == 2);
	CHECK(kd_exec_frame_lock_pop(frame, locks[0]) == 0);
	CHECK(frame->outer_lock_index == 1 && kd_exec_frame_validate(frame));
	before = *frame;
	CHECK(kd_exec_frame_abort(frame) == 0);
	before.state = KD_EXEC_FRAME_ERROR;
	before.role = KD_ROLE_DONE;
	CHECK(!memcmp(&before, frame, sizeof(before)));
	REJECTS(kd_exec_frame_abort(frame), -EALREADY);
	CHECK(kd_exec_frame_pop(frame, NULL) == 0 && !source_frames);
}

static int release_outer(struct kd_exec_frame *frame,
			 struct kd_exec_outer_unlock *hook)
{
	CHECK(frame->outer_unlock_seen && frame->jit_lock_released[0]);
	CHECK(kd_exec_frame_has_unreleased_nested(frame) && !hook->released);
	outer_releases++;
	return 0;
}

static void completion(void)
{
	struct kd_exec_frame *frame = push(0);
	struct kd_exec_outer_unlock hook = { .release = release_outer };
	unsigned long locks[] = { 0x2000, 0x2001, 0x2002 };
	struct pt_regs regs = registers(18);

	if (!frame)
		return;
	CHECK(kd_exec_frame_set_lock_stack(frame, locks, 3) == 0);
	frame->held_lock_depth = 3;
	frame->outer_unlock_hook = &hook;
	REJECTS(kd_exec_frame_complete(frame), -EINVAL);
	regs.di = locks[1];
	REJECTS(kd_exec_frame_record_event(frame, KD_EXEC_EVENT_OUTER_UNLOCK,
					 &regs), -EINVAL);
	regs.di = locks[0];
	CHECK(kd_exec_frame_record_event(frame, KD_EXEC_EVENT_OUTER_UNLOCK,
					 &regs) == 0);
	CHECK(frame->outer_unlock_seen && frame->jit_lock_released[0] &&
	      frame->jit_lock_depth == 3 && !frame->outer_lock_index);
	CHECK(hook.released && outer_releases == 1);
	REJECTS(kd_exec_frame_record_event(frame, KD_EXEC_EVENT_OUTER_UNLOCK,
					 &regs), -EINVAL);
	REJECTS(kd_exec_frame_complete(frame), -EINVAL);
	CHECK(kd_exec_frame_lock_mark_released(frame, locks[1]) == 0);
	REJECTS(kd_exec_frame_complete(frame), -EINVAL);
	CHECK(kd_exec_frame_lock_mark_released(frame, locks[2]) == 0);
	REJECTS(kd_exec_frame_lock_mark_released(frame, locks[2]), -EALREADY);
	REJECTS(kd_exec_frame_lock_mark_released(frame, 0xFFFF), -ENOENT);
	frame->remote_result = KD_EXEC_REMOTE_WAITING;
	REJECTS(kd_exec_frame_complete(frame), -EINVAL);
	frame->remote_result = KD_EXEC_REMOTE_NATIVE;
	REJECTS(kd_exec_frame_complete(frame), -EINVAL);
	frame->remote_result = KD_EXEC_REMOTE_DONE;
	CHECK(kd_exec_frame_complete(frame) == 0 && frame->completion_seen);
	REJECTS(kd_exec_frame_complete(frame), -EALREADY);
	REJECTS(kd_exec_frame_abort(frame), -EALREADY);
	CHECK(outer_releases == 1);
	if (!refused_native_retirement(frame))
		return;
	CHECK(kd_exec_frame_pop(frame, NULL) == 0 && !source_frames);
}

/* This is a direct helper contract, with no JIT body or physical owner. The
 * backends still forbid using cleanup to replay an already-executed section. */
static void cleanup(bool mutex, enum kd_exec_lock_kind kind, bool last_released)
{
	struct kd_exec_frame *frame = push(0);
	struct mutex mutexes[3] = { { true }, { true }, { !last_released } };
	struct qspinlock spins[3] = { { 1 }, { 1 }, { !last_released } };
	unsigned long locks[3];
	enum kd_exec_lock_kind kinds[3] = { KD_EXEC_LOCK_QUEUE_OWNER, kind, kind };
	void *nodes[3];
	int (*run)(struct kd_exec_frame *) = mutex ? kd_mutex_jit_abort_cleanup :
						   kd_spin_jit_abort_cleanup;
	unsigned int i;

	if (!frame)
		return;
	release_count = shadow_count = abort_notes = 0;
	unlock_error = shadow_error = 0;
	for (i = 0; i < 3; i++) {
		nodes[i] = mutex ? (void *)&mutexes[i] : (void *)&spins[i];
		locks[i] = (unsigned long)nodes[i];
	}
	frame->outer_lock_addr = locks[0];
	frame->held_lock_depth = 3;
	CHECK(kd_exec_frame_set_lock_entries(frame, locks, kinds, nodes, NULL, 3) == 0);
	if (last_released)
		CHECK(kd_exec_frame_lock_mark_released(frame, locks[2]) == 0);
	if (mutex) {
		frame->jit_lock_node[2] = NULL;
		REJECTS(run(frame), -EINVAL);
		frame->jit_lock_node[2] = nodes[2];
		frame->jit_lock_kind[2] = KD_EXEC_LOCK_FAST;
		REJECTS(run(frame), -EINVAL);
		frame->jit_lock_kind[2] = kind;
	}
	if (!last_released && (mutex || kind != KD_EXEC_LOCK_NATIVE)) {
		unlock_error = -EBUSY;
		REJECTS(run(frame), -EBUSY);
		CHECK(!release_count && !shadow_count && !abort_notes);
		unlock_error = 0;
	}
	/* An already absent shadow is accepted without a second physical unlock. */
	shadow_error = -ENOENT;
	CHECK(run(frame) == 0);
	CHECK(frame->jit_lock_depth == 1 && frame->held_lock_depth == 1 &&
	      frame->jit_lock_addr[0] == locks[0] && !frame->jit_lock_released[0]);
	CHECK(mutexes[0].locked && spins[0].val == 1);
	CHECK(release_count == 2U - last_released);
	if (release_count)
		CHECK(release_order[release_count - 1] == locks[1]);
	if (!last_released)
		CHECK(release_order[0] == locks[2]);
	if (mutex) {
		CHECK(abort_notes == release_count && !shadow_count);
		CHECK(!mutexes[1].locked && !mutexes[2].locked);
	} else {
		unsigned int expected = kind == KD_EXEC_LOCK_NATIVE ? 2 : last_released;

		CHECK(shadow_count == expected && !abort_notes);
		if (expected)
			CHECK(shadow_order[0] == locks[2]);
		CHECK(!spins[1].val && !spins[2].val);
	}
	CHECK(run(frame) == 0 && release_count == 2U - last_released);
	CHECK(kd_exec_frame_abort(frame) == 0);
	CHECK(kd_exec_frame_pop(frame, NULL) == 0 && !source_frames);
}

static void probe(unsigned int depth, unsigned int invalid)
{
	struct kd_exec_context *ctx;
	struct kd_exec_context before;
	struct kd_exec_frame *frame;
	unsigned int i;

	cpu = 0;
	current = &owners[0];
	ctx = kd_exec_current_context();
	kd_exec_context_reset(ctx);
	memset(&kd_capacity, 0, sizeof(kd_capacity));
	kd_capacity_claimed = 0;
	probe_calls = 0;
	for (i = 0; i < depth; i++) {
		if (!push(i))
			return;
	}
	frame = kd_exec_current_frame();
	if (invalid == 1)
		current = &owners[1];
	if (invalid == 2)
		ctx->frames[0].gsbase = 0;
	before = *ctx;
	kd_exec_selftest_capacity_probe(frame);
	kd_exec_selftest_capacity_report();
	CHECK(!memcmp(&before, ctx, sizeof(before)));
	CHECK(probe_calls ==
	      (unsigned int)(depth == KD_EXEC_MAX_NESTING && !invalid));
	if (depth < KD_EXEC_MAX_NESTING) {
		CHECK(!kd_capacity_claimed && !kd_capacity.attempted &&
		      !kd_capacity.ready);
		CHECK(strstr(report, "claimed=0 ready=0 attempted=0"));
	} else {
		CHECK(kd_capacity_claimed == 1 && kd_capacity.ready);
		CHECK(kd_capacity.attempted == !invalid);
		CHECK(kd_capacity.valid_before == !invalid);
		if (!invalid) {
			CHECK(kd_capacity.rejected && kd_capacity.unchanged &&
			      kd_capacity.valid_after);
			CHECK(!memcmp(&kd_capacity.before, &before,
				      sizeof(before)));
			CHECK(kd_capacity.depth == depth &&
			      kd_capacity.cpu == cpu);
			CHECK(kd_capacity.entry == frame->entry_ip &&
			      kd_capacity.outer == frame->outer_lock_addr);
			CHECK(kd_capacity.task == frame->logical_pid &&
			      kd_capacity.owner == current->pid);
			CHECK(strstr(
				report,
				"claimed=1 ready=1 attempted=1 rejected=1 unchanged=1"));
			/* A second callback must not overwrite the first probe's evidence. */
			ctx->frames[0].regs.ax = 0;
			kd_exec_selftest_capacity_probe(frame);
			CHECK(probe_calls == 1);
			CHECK(!memcmp(&kd_capacity.before, &before,
				      sizeof(before)));
			CHECK(kd_capacity.unchanged);
		}
	}
	current = &owners[0];
	/* Restore the deliberately invalid packet, then use the real release path
	 * instead of clearing live frames and hiding a leaked source lease. */
	if (depth)
		ctx->frames[0].gsbase = 0x3000;
	while (ctx->depth) {
		frame = kd_exec_current_frame();
		kd_exec_frame_set_state(frame, KD_EXEC_FRAME_ERROR);
		CHECK(kd_exec_frame_pop(frame, NULL) == 0);
	}
	CHECK(source_frames == 0);
}

/* Use the production allocator, ledger, completion and pop, with substituted
 * native-producer fields. The observer must leave an owned child armed at
 * finish, detect detach only after drain, and never turn timeout into success.
 * This does not supply kernel scheduling, native ACK or task-RCU evidence. */
static void waiter_exit_observer(bool after_ack, unsigned int behavior)
{
	struct kd_exec_frame *frame = push(0), remote = { 0 };
	struct list_head routing;
	struct pt_regs expected, output, shared;
	unsigned long locks[2] = { 0x6000, 0x2000 };
	bool successful = behavior == 0 || behavior == 2;
	bool incoming_irq = fixture_irq;

	if (!frame)
		return;
	/* Remote owners retain a pointer to the root packet, not an inline copy. */
	shared = frame->regs;
	if (after_ack)
		frame->regs_ref = &shared;
	exit_pid.refs = exit_polls = 0;
	jiffies = 0;
	fixture_preempt = 1;
	exit_behavior = behavior;
	exit_frame = frame;
	kd_relay_exit_claimed = 0;
	kd_relay_exit_after_ack = after_ack;
	kd_relay_exit_lock = frame->outer_lock_addr;
	CHECK(kd_exec_frame_set_lock_stack(frame, locks + !after_ack,
					 after_ack ? 2 : 1) == 0);
	frame->executed = true;
	if (after_ack) {
		frame->resume_target = &remote;
		frame->native_link.next = frame->native_link.prev = &routing;
	} else {
		CHECK(kd_exec_frame_record_event(
			      frame, KD_EXEC_EVENT_OUTER_UNLOCK, NULL) == 0);
		frame->control_call.phase = KD_CALL_COMPLETE;
		frame->remote_result = KD_EXEC_REMOTE_NATIVE;
	}
	kd_exec_selftest_relay_arm(frame, after_ack ? 1 : 0);
	CHECK(kd_relay_exit.valid && kd_relay_exit.frame == frame);
	CHECK(exit_pid.refs == 1 && exit_pid.task == frame->logical_task);
	CHECK(kd_relay_exit.after_ack == after_ack);
	kd_exec_selftest_relay_arm(frame, after_ack ? 1 : 0);
	CHECK(exit_pid.refs == 1);
	if (after_ack) {
		kd_exec_selftest_relay_finish(frame);
		CHECK(kd_relay_exit.frame == frame && exit_pid.refs == 1);
		CHECK(!exit_polls && !jiffies);
		if (failures)
			return;
		/* The real producer clears routing/parent before publishing ACK.
		 * This fixture supplies that boundary; mode 8 verifies its execution. */
		INIT_LIST_HEAD(&frame->native_link);
		frame->resume_target = NULL;
		CHECK(kd_exec_frame_record_event(
			      frame, KD_EXEC_EVENT_OUTER_UNLOCK, NULL) == 0);
	} else {
		frame->remote_result = KD_EXEC_REMOTE_DONE;
	}
	if (behavior == 1)
		exit_pid.task = NULL;
	if (behavior == 5)
		kd_exec_frame_regs(frame)->ax ^= 1;
	if (behavior == 3) fixture_preempt++;
	if (behavior == 4) kd_relay_exit.cpu ^= 1;
	if (behavior == 6) fixture_irq = !fixture_irq;
	/* Cached identity is all the terminal observer may use, even before the
	 * substituted RCU task link is detached. Never infer a live task from it. */
	frame->logical_task->pid = -99;
	expected = *kd_exec_frame_regs(frame);
	if (!after_ack)
		kd_exec_selftest_relay_finish(frame);
	CHECK(kd_exec_frame_complete(frame) == 0);
	CHECK(kd_exec_frame_pop(frame, &output) == 0);
	CHECK(!kd_relay_exit.frame && !kd_relay_exit.pid && !exit_pid.refs);
	CHECK(!source_frames && !kd_exec_current_frame());
	CHECK(strstr(report, "kd_spin retirement:") && strstr(report, "retired=1"));
	CHECK(strstr(report, "task=100 "));
	CHECK(strstr(report, successful ? "valid=1" : "valid=0"));
	CHECK(!exit_polls && !jiffies);
	CHECK(!memcmp(&expected, &output, sizeof(output)));
	fixture_preempt = 1;
	kd_relay_exit_lock = 0;
	fixture_irq = incoming_irq;
}

/* Reuse poisoned storage rather than zero-initialized fixtures. Only published
 * prefixes/phase-tagged payloads may be read, and each new invocation owns its
 * register packet even if the input node is immediately overwritten. */
static void reuse_single(void)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame;
	struct pt_regs input = registers(42), expected = input, output;
	unsigned long lock = 0x2000;

	CHECK(!ctx->depth && !ctx->owner && !source_frames);
	memset(ctx->frames, 0xa5, sizeof(ctx->frames));
	CHECK(kd_exec_context_validate(ctx));
	frame = kd_exec_frame_push(&input, 0x1000, lock, 1,
				   0x3000, &waiters[0]);
	CHECK(frame && kd_exec_frame_validate(frame));
	if (!frame)
		return;
	CHECK(!frame->executed && !frame->completion_seen &&
	      !frame->outer_unlock_seen && !frame->mutex_backend &&
	      !frame->spin_simple && !frame->resume_target &&
	      !frame->remote_request && !frame->native_request &&
	      !frame->remote_result && !frame->jit_lock_depth &&
	      !frame->outer_unlock_hook && list_empty(&frame->native_link) &&
	      frame->control_call.phase == KD_CALL_NONE);
	memset(&input, 0xcc, sizeof(input));
	CHECK(!memcmp(&expected, &frame->regs, sizeof(expected)));
	CHECK(kd_exec_frame_set_lock_stack(frame, &lock, 1) == 0);
	CHECK(frame->jit_lock_addr[0] == lock && !frame->jit_lock_node[0] &&
	      !frame->jit_lock_released[0]);
	frame->spin_simple = true;
	CHECK(kd_exec_frame_complete_single_spin(frame) == -EINVAL);
	frame->executed = true;
	frame->regs.di = lock;
	expected.di = lock;
	CHECK(kd_exec_frame_complete_single_spin(frame) == 0);
	CHECK(kd_exec_frame_validate(frame) && kd_exec_frame_can_complete(frame));
	CHECK(kd_exec_frame_complete_single_spin(frame) == -EINVAL);
	CHECK(kd_exec_frame_pop(frame, &output) == 0 && !source_frames);
	CHECK(!memcmp(&expected, &output, sizeof(expected)));
	CHECK(!kd_exec_current_frame() && kd_exec_context_validate(ctx));
}

/* A root can execute in the published packet without touching private regs.
 * Complex promotion must capture the last wrapper result before node reuse;
 * a nested physical frame must never borrow even when it has only one lock. */
static void borrowed_packets(void)
{
	struct kd_exec_frame *frame, *child;
	struct pt_regs packet = registers(17), expected, poison;
	unsigned long lock = 0x2000;

	for (unsigned int promote = 0; promote < 2; promote++) {
		memset(&kd_exec_current_context()->frames[0].regs, 0xa5,
		       sizeof(packet));
		poison = kd_exec_current_context()->frames[0].regs;
		packet.di = lock;
		frame = kd_exec_frame_push_borrowed(&packet, 0x1000, lock, 1, 0x3000, &waiters[0]);
		CHECK(frame && frame->borrowed_regs == &packet &&
		      kd_exec_frame_regs(frame) == &packet);
		if (!frame || failures)
			return;
		CHECK(!memcmp(&frame->regs, &poison, sizeof(poison)));
		CHECK(!kd_exec_frame_set_lock_stack(frame, &lock, 1));
		frame->spin_simple = true;
		frame->executed = true;
		packet.ax ^= 0xabcdef;
		expected = packet;
		if (promote) {
			kd_exec_frame_own_regs(frame);
			CHECK(!frame->regs_borrowed &&
			      !memcmp(&frame->regs, &expected, sizeof(expected)));
			memset(&packet, 0xcc, sizeof(packet));
			child = kd_exec_frame_push_borrowed(&expected, 0x1000, lock, 1, 0x3000, &waiters[1]);
			CHECK(child && child->parent == frame && !child->regs_borrowed);
			if (!child || failures)
				return;
			CHECK(!memcmp(&child->regs, &expected, sizeof(expected)));
			CHECK(!kd_exec_frame_abort(child) && !kd_exec_frame_pop(child, NULL));
		}
		CHECK(!kd_exec_frame_complete_single_spin(frame));
		CHECK(!kd_exec_frame_pop(frame, &packet));
		CHECK(!memcmp(&packet, &expected, sizeof(packet)) && !source_frames);
		if (!promote)
			CHECK(!memcmp(&frame->regs, &poison, sizeof(poison)));
		if (failures)
			return;
	}
}

/* A queue slot is not request storage. Exhaustion must preserve live bytes;
 * native owner/queue releases may arrive in either order; remote children keep
 * the root packet alive after the root execution frame is already unbound. */
static void shared_requests(void)
{
	struct kd_spin_continuation *live[KD_SPIN_CONT_SLOTS], *root, *child;
	struct pt_regs expected = registers(73);
	struct kd_exec_context before;

	cpu = 0;
	current = &owners[0];
	CHECK(!source_frames && !kd_exec_current_context()->depth);
	for (unsigned int i = 0; i < KD_SPIN_CONT_SLOTS; i++) {
		live[i] = kd_spin_continuation_reserve();
		CHECK(live[i] == &request_pool[i] && !live[i]->retired);
		live[i]->frame.regs = expected;
	}
	CHECK(!kd_spin_continuation_reserve());
	/* A hole is not reusable beneath an active top; capacity cannot move or
	 * overwrite the live continuation above it. */
	kd_spin_continuation_release(live[0]);
	CHECK(request_storage.top == KD_SPIN_CONT_SLOTS && !kd_spin_continuation_reserve());
	for (unsigned int i = 1; i < KD_SPIN_CONT_SLOTS; i++) {
		CHECK(!memcmp(&live[i]->frame.regs, &expected, sizeof(expected)));
		kd_spin_continuation_release(live[i]);
	}
	CHECK(!request_storage.top);
	root = kd_spin_continuation_reserve();
	root->frame.regs = expected;
	kd_exec_frame_prepare(&root->frame, 0x1000, 0, 0x3000, &waiters[0]);
	before = *kd_exec_current_context();
	source_open = false;
	CHECK(kd_exec_frame_bind(&root->frame, 0, true) == -EBUSY);
	CHECK(!memcmp(&before, kd_exec_current_context(), sizeof(before)));
	source_open = true;
	CHECK(kd_source_frame_get());
	CHECK(!kd_exec_frame_bind(&root->frame, 0, true));
	child = kd_spin_continuation_reserve();
	kd_exec_frame_prepare(&child->frame, 0x1000, 0, 0x3000, &waiters[0]);
	child->frame.regs_ref = &root->frame.regs;
	CHECK(!kd_exec_frame_bind(&child->frame, 0, true));
	kd_exec_frame_regs(&child->frame)->ax ^= 0x55;
	expected.ax ^= 0x55;
	CHECK(!memcmp(&root->frame.regs, &expected, sizeof(expected)));
	CHECK(!kd_exec_frame_abort(&child->frame));
	CHECK(!kd_exec_frame_pop(&child->frame, NULL));
	CHECK(!kd_exec_frame_validate(&child->frame));
	/* Remote native retirement marks a slot but never changes owner top. */
	smp_store_release(&child->retired, true);
	CHECK(request_storage.top == 2);
	CHECK(kd_spin_continuation_reserve() == child);
	kd_spin_continuation_release(child);
	CHECK(!kd_exec_frame_abort(&root->frame));
	CHECK(!kd_exec_frame_pop(&root->frame, NULL));
	CHECK(!kd_exec_frame_validate(&root->frame));
	kd_spin_continuation_release(root);
	CHECK(!request_storage.top);
	kd_source_frame_put();
	CHECK(!source_frames && !kd_exec_current_frame());
}

/* Poison all cold bytes: ordinary completion must neither initialize nor read
 * them. Promotion then constructs the exact single-lock owner ledger in place. */
static void lazy_single(void)
{
	struct kd_exec_frame frame, before;
	const size_t cold = offsetof(struct kd_exec_frame, continuation_ip);

	cpu = 0;
	current = &owners[0];
	for (unsigned int promote = 0; promote < 2; promote++) {
		memset(&frame, 0xa5, sizeof(frame));
		kd_exec_frame_prepare(&frame, 0x1000, 0x2000, 0x3000, &waiters[0]);
		frame.regs.di = 0x2000;
		before = frame;
		CHECK(kd_source_frame_get());
		CHECK(!kd_exec_frame_bind(&frame, 1, true));
		CHECK(frame.spin_simple && !frame.complex_ready);
		CHECK(kd_exec_frame_validate(&frame));
		frame.executed = true;
		if (promote) {
			kd_exec_frame_prepare_complex(&frame);
			CHECK(frame.complex_ready && frame.jit_lock_depth == 1 &&
			      frame.jit_lock_addr[0] == 0x2000 &&
			      frame.jit_lock_kind[0] == KD_EXEC_LOCK_QUEUE_OWNER &&
			      !frame.native_request && !frame.remote_request &&
			      frame.control_call.phase == KD_CALL_NONE);
		}
		CHECK(!kd_exec_frame_complete_single_spin(&frame));
		CHECK(!kd_exec_frame_pop(&frame, NULL));
		kd_source_frame_put();
		if (!promote)
			CHECK(!memcmp((char *)&frame + cold, (char *)&before + cold,
				      sizeof(frame) - cold));
	}
}

int main(void)
{
	unsigned int depth, cycle, last_released;
	enum kd_exec_lock_kind kind;

	CHECK(sizeof(struct pt_regs) == 168 &&
	      offsetof(struct kd_exec_frame, regs) == 72);
	lazy_single();
	shared_requests();
	if (failures)
		return 1;
	reuse_single();
	if (failures)
		return 1;
	borrowed_packets();
	if (failures)
		return 1;
	for (cycle = 0; cycle < 3; cycle++) {
		for (depth = 0; depth <= KD_EXEC_MAX_NESTING; depth++) {
			for (cpu = 0; cpu < 2; cpu++) {
				struct kd_exec_context other =
					kd_exec_context[1 - cpu];

				exercise(depth);
				if (failures)
					return 1;
				CHECK(!memcmp(&other, &kd_exec_context[1 - cpu],
					      sizeof(other)));
			}
		}
	}
	for (depth = 0; depth <= KD_EXEC_MAX_NESTING; depth++)
		probe(depth, 0);
	probe(KD_EXEC_MAX_NESTING, 1);
	probe(KD_EXEC_MAX_NESTING, 2);
	if (failures)
		return 1;
	ledger();
	if (failures)
		return 1;
	completion();
	if (failures)
		return 1;
	for (last_released = 0; last_released < 2; last_released++) {
		for (kind = KD_EXEC_LOCK_FAST; kind <= KD_EXEC_LOCK_NATIVE; kind++) {
			cleanup(false, kind, last_released);
			if (failures)
				return 1;
		}
		cleanup(true, KD_EXEC_LOCK_NATIVE, last_released);
		if (failures)
			return 1;
	}
	for (cycle = 0; cycle < 2; cycle++) {
		for (depth = 0; depth < 6; depth++) {
			waiter_exit_observer(cycle, depth);
			if (failures)
				return 1;
		}
	}
	/* The spin queue now holds IRQs masked across native/remote execution.
	 * Exercise the same actual ACK/exit predicates in that captured state. */
	fixture_irq = true;
	for (cycle = 0; cycle < 2; cycle++) {
		waiter_exit_observer(cycle, 0);
		waiter_exit_observer(cycle, 6);
	}
	fixture_irq = false;
	CHECK(kd_exec_invariant_failures == 0);
	printf("production frame capacity: checks=%u failures=%u regs=%zu frame=%zu context=%zu\n",
	       checks, failures, sizeof(struct pt_regs),
	       sizeof(struct kd_exec_frame), sizeof(struct kd_exec_context));
	return failures ? 1 : 0;
}
