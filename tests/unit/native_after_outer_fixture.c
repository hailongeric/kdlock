/* SPDX-License-Identifier: GPL-2.0 */
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

struct pt_regs {
	unsigned long ip, sp, di;
};
struct task_struct {
	int pid;
};
struct list_head {
	struct list_head *next, *prev;
};
typedef struct {
	int value;
} raw_spinlock_t;
struct mutex {
	int value;
};

#include "frame_types.h"

static struct task_struct executor = { 11 }, waiter = { 12 };
static struct task_struct *current = &executor;
static struct kd_exec_frame *active;
static unsigned long kd_exec_invariant_failures, kd_native_started;
static struct list_head kd_native_frames;
static int kd_native_lock, borrowed, published, unlocked, nested_jit;
static int failures, checks;
static unsigned long raw_spin_lock_addr = 0x100, raw_spin_unlock_addr = 0x200;
static unsigned long mutex_lock_addr = 0x300, mutex_unlock_addr = 0x400;
static struct mutex a, b;

#define READ_ONCE(x) (x)
#define INIT_LIST_HEAD(p)        \
	do {                     \
		(p)->next = (p); \
		(p)->prev = (p); \
	} while (0)
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, value) (*(p) = (value))
#define atomic64_inc(p) (++*(p))
#define WARN_ON_ONCE(x) ((void)(x))
#define pr_info(...)                         \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
#define pr_warn_ratelimited(...) pr_info(__VA_ARGS__)
#define raw_spin_lock_irqsave(lock, flags) \
	do {                               \
		(void)(lock);              \
		(flags) = 0;               \
	} while (0)
#define raw_spin_unlock_irqrestore(lock, flags) \
	do {                                    \
		(void)(lock);                   \
		(void)(flags);                  \
	} while (0)

static unsigned int raw_smp_processor_id(void)
{
	return 0;
}
static void list_add(struct list_head *node, struct list_head *head)
{
	(void)node;
	(void)head;
	published++;
}
static int kd_spin_entry_borrow_get(const struct kd_spin_ref *ref)
{
	(void)ref;
	borrowed++;
	return 0;
}
struct kd_exec_frame *kd_exec_current_frame(void)
{
	return active;
}
static int kd_mutex_nested_unlock(struct mutex *lock)
{
	if (lock != &b)
		return -EINVAL;
	unlocked++;
	return 0;
}
static void kd_mutex_note_nested_jit(void)
{
	nested_jit++;
}
static int kd_mutex_jit_nested_lock_ctx(struct mutex *lock,
					struct pt_regs *regs,
					struct kd_exec_frame *frame)
{
	(void)lock;
	(void)regs;
	(void)frame;
	return -EOPNOTSUPP;
}
static int kd_spin_jit_nested_lock_ctx(raw_spinlock_t *lock,
				       struct pt_regs *regs,
				       struct kd_exec_frame *frame)
{
	(void)lock;
	(void)regs;
	(void)frame;
	return -EOPNOTSUPP;
}
static int kd_spin_jit_nested_unlock_ctx(raw_spinlock_t *lock,
					 struct kd_exec_frame *frame)
{
	(void)lock;
	(void)frame;
	return -EOPNOTSUPP;
}
static int kd_spin_jit_outer_unlock_ooo_ctx(raw_spinlock_t *lock,
					    struct pt_regs *regs,
					    struct kd_exec_frame *frame)
{
	(void)lock;
	(void)regs;
	(void)frame;
	return -EOPNOTSUPP;
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

static struct kd_exec_frame frame(bool mutex)
{
	return (struct kd_exec_frame){
		.regs = { .ip = 0x500, .sp = 0x600 },
		.entry_ip = 0x700,
		.outer_lock_addr = (unsigned long)&a,
		.gsbase = 1,
		.logical_task = &waiter,
		.jit_lock_addr = { (unsigned long)&a, (unsigned long)&b },
		.jit_lock_kind = { KD_EXEC_LOCK_QUEUE_OWNER,
				   KD_EXEC_LOCK_NATIVE },
		.jit_lock_node = { &a, &b },
		.held_lock_depth = 2,
		.outer_lock_depth = 1,
		.outer_lock_index = 0,
		.jit_lock_depth = 2,
		.state = KD_EXEC_FRAME_RUNNING,
		.executed = true,
		.mutex_backend = mutex,
	};
}

static void check_native(bool mutex)
{
	struct kd_exec_frame f = frame(mutex);
	struct kd_exec_frame late, bad;
	int before;

	CHECK(kd_exec_native_begin(&f, mutex) == 0);
	CHECK(kd_exec_frame_record_event(&f, KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	late = f;
	before = published;
	CHECK(kd_exec_native_begin(&f, mutex) == 0);
	CHECK(published == before + 1);
	for (int phase = KD_CALL_PENDING; phase <= KD_CALL_COMPLETE; phase++) {
		bad = late;
		bad.control_call.phase = phase;
		bad.control_call.target = bad.regs.ip;
		bad.control_call.stack = bad.regs.sp;
		CHECK(kd_exec_native_begin(&bad, mutex) == -EINVAL);
	}
	bad = late;
	bad.jit_lock_released[0] = false;
	CHECK(kd_exec_native_begin(&bad, mutex) == -EINVAL);
	bad = late;
	bad.jit_lock_released[1] = true;
	CHECK(kd_exec_native_begin(&bad, mutex) == -EINVAL);
	CHECK(kd_exec_frame_complete(&bad) == 0);
	CHECK(kd_exec_native_begin(&bad, mutex) == -EINVAL);
	bad = late;
	bad.state = KD_EXEC_FRAME_ERROR;
	CHECK(kd_exec_native_begin(&bad, mutex) == -EINVAL);
	bad = late;
	bad.logical_task = current;
	CHECK(kd_exec_native_begin(&bad, mutex) == -EINVAL);
	CHECK(kd_exec_native_begin(&late, !mutex) == -EINVAL);
	bad = late;
	bad.outer_lock_index = 1;
	CHECK(kd_exec_native_begin(&bad, mutex) == -EINVAL);
	bad = late;
	bad.regs.sp = 0;
	CHECK(kd_exec_native_begin(&bad, mutex) == -EINVAL);
	CHECK(published == before + 1);

	/* Before A unlock, the existing pristine PENDING CALL remains resumable. */
	f = frame(mutex);
	f.control_call.phase = KD_CALL_PENDING;
	f.control_call.target = f.regs.ip;
	f.control_call.stack = f.regs.sp;
	f.control_call.return_ip = 0x700;
	CHECK(kd_exec_native_begin(&f, mutex) == 0);
	f.regs.sp++;
	CHECK(kd_exec_native_begin(&f, mutex) == -EINVAL);
}

static void check_native_phase_rejection(bool mutex)
{
	const int phases[] = { KD_CALL_ENTERED, KD_CALL_ACQUIRED,
			       KD_CALL_COMPLETE, KD_CALL_COMPLETE + 1, -1 };
	unsigned int phase;
	int released;

	for (released = 0; released < 2; released++) {
		for (phase = 0; phase < sizeof(phases) / sizeof(phases[0]);
		     phase++) {
			struct kd_exec_frame f = frame(mutex), before;
			unsigned long started = kd_native_started;
			int publications = published, references = borrowed;

			if (released)
				CHECK(kd_exec_frame_record_event(
					      &f, KD_EXEC_EVENT_OUTER_UNLOCK,
					      NULL) == 0);
			/* A valid packet must not make an unsupported phase resumable. */
			f.control_call.target = f.regs.ip;
			f.control_call.stack = f.regs.sp;
			f.control_call.return_ip = 0x900;
			f.control_call.phase = phases[phase];
			before = f;
			CHECK(kd_exec_native_begin(&f, mutex) == -EINVAL);
			CHECK(memcmp(&f, &before, sizeof(f)) == 0);
			CHECK(kd_native_started == started);
			CHECK(published == publications &&
			      borrowed == references);
		}
	}
}

static void check_pending_after_outer(bool mutex)
{
	const int errors[] = { -ENOMEM, -E2BIG, -EIO, -EINVAL, -EDEADLK };
	unsigned long return_ip = 0x900;
	struct kd_exec_frame f;
	struct pt_regs staged;
	int phase, ret, before;

	for (phase = KD_CALL_PENDING; phase <= KD_CALL_COMPLETE; phase++) {
		for (unsigned int e = 0; e < sizeof(errors) / sizeof(errors[0]);
		     e++) {
			f = frame(mutex);
			CHECK(kd_exec_frame_record_event(
				      &f, KD_EXEC_EVENT_OUTER_UNLOCK, NULL) ==
			      0);
			CHECK(kd_call_begin(&f.control_call, 0x800,
					    (unsigned long)&return_ip,
					    return_ip) == 0);
			f.control_call.phase = phase;
			f.regs.ip = mutex ? 0x800 : return_ip;
			f.regs.sp = (unsigned long)&return_ip +
				    (mutex ? 0 : sizeof(return_ip));
			staged = f.regs;
			ret = finish_known_lock_call(&f, &f.regs, errors[e]);
			if (phase == KD_CALL_PENDING && e < 2) {
				CHECK(ret == KD_EXE_KNOWN_NATIVE);
				CHECK(f.regs.ip == 0x800 &&
				      f.regs.sp == (unsigned long)&return_ip);
				CHECK(f.continuation_ip == f.regs.ip &&
				      f.continuation_sp == f.regs.sp);
				before = published;
				CHECK(kd_exec_native_begin(&f, mutex) == 0);
				CHECK(published == before + 1);
			} else {
				CHECK(ret == errors[e]);
				CHECK(memcmp(&f.regs, &staged,
					     sizeof(staged)) == 0);
			}
			CHECK(return_ip == 0x900);
			CHECK(f.outer_unlock_seen && !f.jit_lock_released[1] &&
			      !f.completion_seen);
		}
	}
	/* A retired suffix or inconsistent outer ledger must not consume the CALL. */
	for (int broken = 0; broken < 3; broken++) {
		f = frame(mutex);
		CHECK(kd_exec_frame_record_event(&f, KD_EXEC_EVENT_OUTER_UNLOCK,
						 NULL) == 0);
		CHECK(kd_call_begin(&f.control_call, 0x800,
				    (unsigned long)&return_ip, return_ip) == 0);
		if (broken == 0)
			f.jit_lock_released[1] = true;
		else if (broken == 1)
			f.jit_lock_released[0] = false;
		else
			f.state = KD_EXEC_FRAME_ERROR;
		staged = f.regs;
		CHECK(finish_known_lock_call(&f, &f.regs, -E2BIG) == -E2BIG);
		CHECK(memcmp(&f.regs, &staged, sizeof(staged)) == 0);
	}
}

static void check_mutex_ooo(void)
{
	struct kd_exec_frame f = frame(true);
	unsigned long return_ip = 0x800;
	struct pt_regs regs = { .ip = mutex_unlock_addr,
				.sp = (unsigned long)&return_ip,
				.di = (unsigned long)&a };
	int ret;

	active = &f;
	ret = handle_known_call(&regs, f.outer_lock_addr);
	CHECK(ret == 1);
	CHECK(f.outer_unlock_seen && f.jit_lock_released[0]);
	CHECK(!kd_exec_frame_can_complete(&f));
	CHECK(regs.ip == return_ip &&
	      regs.sp == (unsigned long)(&return_ip + 1));
	CHECK(unlocked == 0);
	/* Isolate final B handling so it also reports against the old A handler. */
	f = frame(true);
	CHECK(kd_exec_frame_record_event(&f, KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	regs = (struct pt_regs){ .ip = mutex_unlock_addr,
				 .sp = (unsigned long)&return_ip,
				 .di = (unsigned long)&b };
	ret = handle_known_call(&regs, f.outer_lock_addr);
	CHECK(ret == KD_EXE_KNOWN_OUTER_UNLOCK);
	CHECK(unlocked == 1 && nested_jit == 1);
	/* Final unlock's CALL is consumed by the real waiter return trampoline. */
	CHECK(regs.ip == mutex_unlock_addr &&
	      regs.sp == (unsigned long)&return_ip);
	CHECK(kd_exec_frame_can_complete(&f));
	CHECK(kd_exec_frame_complete(&f) == 0);
	CHECK(kd_exec_frame_complete(&f) == -EALREADY);
	CHECK(kd_mutex_jit_nested_unlock_ctx(&b, &f) == -ENOENT);
	CHECK(unlocked == 1);
}

int main(void)
{
	check_native(false);
	check_native(true);
	check_native_phase_rejection(false);
	check_native_phase_rejection(true);
	check_pending_after_outer(false);
	check_pending_after_outer(true);
	check_mutex_ooo();
	CHECK(kd_exec_invariant_failures == 0);
	printf("after-outer production functions: %d checks, %d failures\n",
	       checks, failures);
	return failures != 0;
}
