/* SPDX-License-Identifier: GPL-2.0 */
/* Production native registration/control packets with substituted lock APIs.
 * Exercise late outer release and checked post-CALL exits without hardware
 * register restoration, real kernel locks or generated instructions. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
typedef uint8_t u8;
typedef uint16_t u16;
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "kd_source_api.h"

#include "../../../include/kd_regs.h"
struct task_struct {
	int pid;
	void *stack;
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

#define THREAD_SIZE 1024UL
static unsigned long waiter_stack[THREAD_SIZE / sizeof(unsigned long)];
static struct task_struct executor = { .pid = 11 };
static struct task_struct waiter = { .pid = 12, .stack = waiter_stack };
static struct task_struct *current = &executor;
static struct kd_exec_frame *active;
static unsigned long kd_exec_invariant_failures, kd_native_started;
static unsigned long kd_mutex_stack_equal, kd_mutex_stack_changed;
static unsigned long kd_mutex_stack_unavailable;
static unsigned char *control_mutation;
static int stack_read_error;
static unsigned long spin_owner;
static unsigned int spin_word;
static struct list_head kd_native_frames;
static int kd_native_lock, borrowed, published, unlocked, nested_jit;
static int failures, checks;
static unsigned long raw_spin_lock_addr = 0x100, raw_spin_unlock_addr = 0x200;
static unsigned long pinned_spin_lock_addr = 0x120, cold_spin_unlock_addr = 0x220;
static unsigned long clobber_spin_lock_addr = 0x110, clobber_spin_unlock_addr = 0x210;
static unsigned long clobber_mutex_lock_addr = 0x310, clobber_mutex_unlock_addr = 0x410;
static unsigned long direct_mutex_lock_addr = 0x320, direct_mutex_unlock_addr = 0x420;
static unsigned long mutex_lock_addr = 0x300, mutex_unlock_addr = 0x400;
static struct mutex a, b;
static struct task_struct native_peer = { .pid = 13 }, *nested_owner;
static bool track_nested_owner;
static unsigned int nested_acquires, nested_waits;
static int kd_jit_fail_pending_lock;

/* Primitive observations only; the live case verifies real owner-side ACKs. */
static unsigned long kd_spin_debug_owner(raw_spinlock_t *lock)
{
	return lock == (raw_spinlock_t *)&b ? spin_owner : 0;
}

static unsigned int kd_spin_debug_word(raw_spinlock_t *lock)
{
	return lock == (raw_spinlock_t *)&b ? spin_word : 0;
}

#define READ_ONCE(x) (x)
#define unlikely(x) (x)
#define cmpxchg(p, old, value) __sync_val_compare_and_swap(p, old, value)
#define BUG_ON(expr)                                                    \
	do {                                                           \
		if (expr) {                                            \
			fprintf(stderr, "FAIL line %d: BUG_ON(%s)\n",   \
				__LINE__, #expr);                       \
			exit(1);                                       \
		}                                                      \
	} while (0)
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

static void *task_stack_page(struct task_struct *task)
{
	return task->stack;
}

static int copy_from_kernel_nofault(void *dst, const void *src, size_t size)
{
	unsigned long base = (unsigned long)waiter_stack;
	unsigned long address = (unsigned long)src;

	/* This fixture's bounded array stands in for a live task stack. Fault
	 * injection tests refusal, not Linux nofault or task-stack lifetime. */
	if (stack_read_error || address < base ||
	    address > base + THREAD_SIZE || size > base + THREAD_SIZE - address)
		return -EFAULT;
	memcpy(dst, src, size);
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
	if (track_nested_owner) {
		if (nested_owner != current)
			return -EPERM;
		nested_owner = NULL;
	}
	if (control_mutation)
		*control_mutation ^= 0x5a;
	unlocked++;
	return 0;
}
static void kd_mutex_note_nested_jit(void)
{
	nested_jit++;
}
static int kd_mutex_nested_lock(struct mutex *lock);
static int kd_spin_jit_nested_lock_ctx(raw_spinlock_t *lock,
				       struct kd_regs *regs,
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
					    struct kd_regs *regs,
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

/* The native wait is deterministic. The actual nested-call producer must not
 * publish B or consume its CALL until this substituted acquisition returns. */
static int kd_mutex_nested_lock(struct mutex *lock)
{
	CHECK(track_nested_owner && lock == &b && current == &executor);
	CHECK(active->control_call.phase == KD_CALL_ENTERED);
	CHECK((active->regs.ip == mutex_lock_addr ||
	       active->regs.ip == clobber_mutex_lock_addr ||
	       active->regs.ip == direct_mutex_lock_addr) &&
	      active->regs.sp == (unsigned long)&waiter_stack[32]);
	CHECK(!kd_exec_frame_lock_contains(active, (unsigned long)lock));
	if (nested_owner) {
		CHECK(nested_owner == &native_peer);
		nested_owner = NULL;
		nested_waits++;
	}
	nested_owner = current;
	nested_acquires++;
	return 0;
}

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
	const int phases[] = { KD_CALL_ENTERED,
			       KD_CALL_ACQUIRED,
			       KD_CALL_COMPLETE,
			       KD_CALL_STACK_CHANGED,
			       KD_CALL_SPIN_NATIVE,
			       KD_CALL_SPIN_NATIVE + 1,
			       -1 };
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
	struct kd_regs staged;
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
	unsigned long *return_ip = &waiter_stack[32];
	struct kd_regs regs = { .ip = mutex_unlock_addr,
				.sp = (unsigned long)return_ip,
				.di = (unsigned long)&a };
	int ret;

	*return_ip = 0x800;
	active = &f;
	ret = handle_known_call(&regs, f.outer_lock_addr);
	CHECK(ret == 1);
	CHECK(f.outer_unlock_seen && f.jit_lock_released[0]);
	CHECK(!kd_exec_frame_can_complete(&f));
	CHECK(regs.ip == *return_ip &&
	      regs.sp == (unsigned long)(return_ip + 1));
	CHECK(unlocked == 0);
	/* Isolate final B handling so it also reports against the old A handler. */
	f = frame(true);
	CHECK(kd_exec_frame_record_event(&f, KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	regs = (struct kd_regs){ .ip = mutex_unlock_addr,
				 .sp = (unsigned long)return_ip,
				 .di = (unsigned long)&b };
	ret = handle_known_call(&regs, f.outer_lock_addr);
	CHECK(ret == KD_EXE_KNOWN_OUTER_UNLOCK);
	CHECK(unlocked == 1 && nested_jit == 1);
	/* Final unlock's CALL is consumed by the real waiter return trampoline. */
	CHECK(regs.ip == mutex_unlock_addr &&
	      regs.sp == (unsigned long)return_ip);
	CHECK(kd_exec_frame_can_complete(&f));
	CHECK(kd_exec_frame_complete(&f) == 0);
	CHECK(kd_exec_frame_complete(&f) == -EALREADY);
	CHECK(kd_mutex_jit_nested_unlock_ctx(&b, &f) == -ENOENT);
	CHECK(unlocked == 1);
}

static void check_mutex_stack_changes(void)
{
	unsigned long *word = &waiter_stack[32];
	unsigned char *window = (unsigned char *)(word + 1);

	/* Mutate each checked byte inside the primitive while the production
	 * unlock dispatcher is running. No saved memory is written back. This
	 * exercises the handoff marker/ledger, not actual Linux concurrency. */
	for (int offset = -8; offset <= KD_MUTEX_CALL_STACK_BYTES; offset++) {
		struct kd_exec_frame f = frame(true);
		struct kd_regs expected;
		int before = unlocked, result;
		bool token = offset < 0;
		bool changed = !token && offset < KD_MUTEX_CALL_STACK_BYTES;

		memset(waiter_stack, 0, sizeof(waiter_stack));
		*word = 0x900;
		f.regs.ip = mutex_unlock_addr;
		f.regs.sp = (unsigned long)word;
		f.regs.di = (unsigned long)&b;
		f.regs.bx = 0xabcd;
		f.regs.bp = 0xcdef;
		expected = f.regs;
		expected.ip = *word;
		expected.sp += sizeof(*word);
		active = &f;
		control_mutation = window + offset;
		result = handle_known_call(&f.regs, f.outer_lock_addr);
		control_mutation = NULL;
		CHECK(unlocked == before + 1);
		CHECK(window[offset] !=
		      (token ? ((unsigned char *)&expected.ip)[offset + 8] :
			       0));
		CHECK(!f.outer_unlock_seen && !f.completion_seen);
		CHECK(f.jit_lock_depth == 1);
		if (token) {
			CHECK(result < 0);
			CHECK(kd_exec_native_begin(&f, true) == -EINVAL);
			continue;
		}
		CHECK(memcmp(&f.regs, &expected, sizeof(expected)) == 0);
		CHECK(result == (changed ? KD_EXE_KNOWN_NATIVE : 1));
		CHECK(f.control_call.phase ==
		      (changed ? KD_CALL_STACK_CHANGED : KD_CALL_COMPLETE));
		CHECK(kd_exec_native_begin(&f, true) ==
		      (changed ? 0 : -EINVAL));
	}
}

static void check_mutex_stack_refusals(void)
{
	struct kd_mutex_call_stack saved;
	unsigned long *word = &waiter_stack[32];
	struct kd_exec_frame f;
	struct kd_regs expected;
	int before;

	/* Valid CALL, insufficient window: no unlock has happened and the waiter
	 * must continue at that CALL, retaining every original physical owner. */
	f = frame(true);
	f.regs.ip = mutex_unlock_addr;
	f.regs.sp = (unsigned long)(waiter_stack +
				    sizeof(waiter_stack) / sizeof(*word) - 1);
	*(unsigned long *)f.regs.sp = 0x900;
	f.regs.di = (unsigned long)&b;
	expected = f.regs;
	active = &f;
	before = unlocked;
	CHECK(handle_known_call(&f.regs, f.outer_lock_addr) ==
	      KD_EXE_KNOWN_NATIVE);
	CHECK(unlocked == before && f.jit_lock_depth == 2);
	CHECK(memcmp(&f.regs, &expected, sizeof(expected)) == 0);
	CHECK(f.control_call.phase == KD_CALL_PENDING);
	CHECK(kd_exec_native_begin(&f, true) == 0);
	CHECK(kd_mutex_stack_unavailable == 1);

	for (int bad = 0; bad < 9; bad++) {
		f = frame(true);
		*word = 0x900;
		f.regs.ip = mutex_lock_addr;
		f.regs.sp = (unsigned long)word;
		CHECK(kd_mutex_stack_prepare(&f, &f.regs, &saved) == 0);
		f.control_call.phase = KD_CALL_COMPLETE;
		f.regs.ip = *word;
		f.regs.sp += sizeof(*word);
		switch (bad) {
		case 0:
			f.regs.ip++;
			break;
		case 1:
			f.regs.sp++;
			break;
		case 2:
			f.control_call.target++;
			break;
		case 3:
			f.control_call.stack++;
			break;
		case 4:
			f.control_call.return_ip++;
			break;
		case 5:
			f.control_call.phase = KD_CALL_ACQUIRED;
			break;
		case 6:
			*word ^= 1;
			break;
		case 7:
			stack_read_error = 1;
			break;
		case 8:
			f.control_call.phase = KD_CALL_STACK_CHANGED;
			break;
		}
		CHECK(kd_mutex_stack_finish(&f, &f.regs, &saved) < 0);
		stack_read_error = 0;
	}
	for (int bad = 0; bad < 5; bad++) {
		f = frame(true);
		f.regs.ip = mutex_lock_addr;
		f.regs.sp = (unsigned long)word;
		*word = bad == 3 ? 0 : 0x900;
		if (bad == 0)
			f.regs.sp = (unsigned long)waiter_stack - 1;
		if (bad == 1)
			f.regs.sp = (unsigned long)waiter_stack + THREAD_SIZE;
		if (bad == 2)
			f.mutex_backend = false;
		if (bad == 4)
			stack_read_error = 1;
		CHECK(kd_mutex_stack_prepare(&f, &f.regs, &saved) < 0);
		stack_read_error = 0;
	}
}

static void check_completed_mutex_native(void)
{
	/* Test both retained-A and early-A-release ledgers. A post-control marker
	 * never authorizes spin, a wrong packet, COMPLETE, or an empty owner set. */
	for (int released = 0; released < 2; released++) {
		for (int bad = 0; bad < 7; bad++) {
			struct kd_exec_frame f = frame(true);
			if (released)
				CHECK(kd_exec_frame_record_event(
					      &f, KD_EXEC_EVENT_OUTER_UNLOCK,
					      NULL) == 0);
			CHECK(kd_call_begin(&f.control_call, mutex_lock_addr,
					    0x1000, 0x900) == 0);
			f.control_call.phase = KD_CALL_STACK_CHANGED;
			f.regs.ip = 0x900;
			f.regs.sp = 0x1008;
			switch (bad) {
			case 1:
				f.mutex_backend = false;
				break;
			case 2:
				f.control_call.phase = KD_CALL_COMPLETE;
				break;
			case 3:
				f.regs.sp++;
				break;
			case 4:
				f.regs.ip++;
				break;
			case 5:
				f.control_call.target = 0;
				break;
			case 6:
				f.control_call.stack = ~0UL - 3;
				f.regs.sp = 4;
				break;
			}
			CHECK(kd_exec_native_begin(&f, f.mutex_backend) ==
			      (bad ? -EINVAL : 0));
		}
	}
}

static void check_call_register_preservation(void)
{
	unsigned long stack[] = { 0x1234, 0x5678 };
	unsigned long words[sizeof(struct kd_regs) / sizeof(unsigned long)];
	struct kd_exec_frame f = frame(false);
	struct kd_regs regs, expected;

	for (unsigned int i = 0; i < sizeof(words) / sizeof(words[0]); i++)
		words[i] = 0x100 + i;
	for (int helper = 0; helper < 2; helper++) {
		memcpy(&regs, words, sizeof(regs));
		regs.sp = (unsigned long)stack;
		expected = regs;
		expected.ip = stack[0];
		expected.sp += sizeof(stack[0]);
		/* These are extracted production functions, not a second model of
		 * the CALL ABI. Only IP/SP may change; memory effects of arbitrary
		 * callees or remote child instructions are not covered by this test. */
		if (helper == 0) {
			CHECK(kd_jit_advance_call(&f, &regs) == 0);
			CHECK(memcmp(&f.regs, &expected, sizeof(regs)) == 0);
		} else {
			CHECK(advance_after_known_call(&regs) == 1);
		}
		CHECK(memcmp(&regs, &expected, sizeof(regs)) == 0);
		CHECK(stack[0] == 0x1234 && stack[1] == 0x5678);
		regs.sp = 0;
		expected = regs;
		CHECK((helper == 0 ?
			       kd_jit_advance_call(&f, &regs) :
			       advance_after_known_call(&regs)) == -EINVAL);
		CHECK(memcmp(&regs, &expected, sizeof(regs)) == 0);
	}
}

static void check_acquired_spin_native(void)
{
	/* Exercise the real post-acquisition validator, keeping all GPRs and the
	 * entire bounded waiter stack unchanged. Rejection must not publish a
	 * native frame or turn a partial acquisition into an entry replay. */
	for (int released = 0; released < 2; released++) {
		for (int queued = 0; queued < 2; queued++) {
			for (int bad = 0; bad < 23; bad++) {
				struct kd_exec_frame f = frame(false), before;
				unsigned long words[sizeof(f.regs) /
						    sizeof(unsigned long)];
				unsigned long
					stack_before[THREAD_SIZE /
						     sizeof(unsigned long)];
				unsigned long *word = &waiter_stack[32];
				int publications = published,
				    references = borrowed;
				int error = -EIO;

				memset(waiter_stack, 0xa5,
				       sizeof(waiter_stack));
				*word = 0x900;
				for (unsigned int i = 0;
				     i < sizeof(words) / sizeof(words[0]); i++)
					words[i] = 0x100 + i;
				memcpy(&f.regs, words, sizeof(f.regs));
				f.regs.ip = *word;
				f.regs.sp = (unsigned long)(word + 1);
				f.regs.di = (unsigned long)&b;
				f.jit_lock_kind[1] =
					queued ? KD_EXEC_LOCK_QUEUE_OWNER :
						 KD_EXEC_LOCK_FAST;
				f.jit_lock_node[1] = NULL;
				CHECK(kd_call_begin(&f.control_call,
						    raw_spin_lock_addr,
						    (unsigned long)word,
						    *word) == 0);
				f.control_call.phase = KD_CALL_ACQUIRED;
				if (released)
					CHECK(kd_exec_frame_record_event(
						      &f,
						      KD_EXEC_EVENT_OUTER_UNLOCK,
						      NULL) == 0);
				spin_owner = (unsigned long)current;
				spin_word = 1;
				switch (bad) {
				case 1:
					error = -ENOMEM;
					break;
				case 2:
					f.mutex_backend = true;
					break;
				case 3:
					f.control_call.phase = KD_CALL_ENTERED;
					break;
				case 4:
					f.control_call.phase = KD_CALL_COMPLETE;
					break;
				case 5:
					f.control_call.target++;
					break;
				case 6:
					f.regs.ip++;
					break;
				case 7:
					f.regs.sp++;
					break;
				case 8:
					f.regs.di = (unsigned long)&a;
					break;
				case 9:
					f.jit_lock_kind[1] =
						KD_EXEC_LOCK_NATIVE;
					break;
				case 10:
					f.jit_lock_node[1] = &b;
					break;
				case 11:
					f.jit_lock_released[1] = true;
					break;
				case 12:
					spin_owner = (unsigned long)&waiter;
					break;
				case 13:
					spin_word = 0x100;
					break;
				case 14:
					*word ^= 1;
					break;
				case 15:
					stack_read_error = 1;
					break;
				case 16:
					waiter.stack = NULL;
					break;
				case 17:
					waiter.stack = (void *)(~0UL - 3);
					break;
				case 18:
					f.remote_request =
						(struct kd_remote_request *)&f;
					break;
				case 19:
					f.remote_result =
						KD_EXEC_REMOTE_WAITING;
					break;
				case 20:
					f.logical_task = current;
					break;
				case 21:
					f.state = KD_EXEC_FRAME_ERROR;
					break;
				case 22:
					f.control_call.stack =
						(unsigned long)waiter_stack - 8;
					f.regs.sp = f.control_call.stack + 8;
					break;
				}
				before = f;
				memcpy(stack_before, waiter_stack,
				       sizeof(stack_before));
				CHECK(finish_known_lock_call(&f, &f.regs,
							     error) ==
				      (bad ? error : KD_EXE_KNOWN_NATIVE));
				CHECK(memcmp(&f.regs, &before.regs,
					     sizeof(f.regs)) == 0);
				CHECK(memcmp(waiter_stack, stack_before,
					     sizeof(stack_before)) == 0);
				CHECK(published == publications &&
				      borrowed == references);
				if (bad) {
					CHECK(memcmp(&f, &before, sizeof(f)) ==
					      0);
				} else {
					CHECK(f.control_call.phase ==
					      KD_CALL_SPIN_NATIVE);
					CHECK(f.continuation_ip == f.regs.ip &&
					      f.continuation_sp == f.regs.sp);
					CHECK(kd_exec_native_begin(&before,
								   false) ==
					      -EINVAL);
					CHECK(kd_exec_native_begin(&f, false) ==
					      0);
					CHECK(published == publications + 1 &&
					      borrowed == references + 1);
					before = f;
					before.regs.sp--;
					CHECK(kd_exec_native_begin(&before,
								   false) ==
					      -EINVAL);
					before = f;
					before.mutex_backend = true;
					CHECK(kd_exec_native_begin(&before,
								   true) ==
					      -EINVAL);
				}
				stack_read_error = 0;
				waiter.stack = waiter_stack;
			}
		}
	}
}

/* The current mutex backend acquires B on A's executor, including after a
 * native peer wait. It resumes after lock(B), never after a remote unlock(B). */
static void check_mutex_call_pair(void)
{
	/* Original Linux, captured kernel bridge and explicit module endpoints
	 * must preserve the same ownership/continuation contract through FULL. */
	const unsigned long locks[] = { mutex_lock_addr, clobber_mutex_lock_addr, direct_mutex_lock_addr };
	const unsigned long unlocks[] = { mutex_unlock_addr, clobber_mutex_unlock_addr, direct_mutex_unlock_addr };
	for (unsigned int endpoint = 0; endpoint < 3; endpoint++)
	for (unsigned int contended = 0; contended < 2; contended++) {
		struct kd_exec_frame f = frame(true);
		struct kd_regs expected;
		unsigned long *word = &waiter_stack[32];
		int before_unlock = unlocked;

		/* Start from an A-only fixture ledger, then use the real B producer. */
		CHECK(kd_exec_frame_lock_pop(&f, (unsigned long)&b) == 0);
		memset(waiter_stack, 0, sizeof(waiter_stack));
		*word = 0x900;
		memset(&f.regs, 0x5A, sizeof(f.regs));
		f.regs.ip = locks[endpoint];
		f.regs.sp = (unsigned long)word;
		f.regs.di = (unsigned long)&b;
		expected = f.regs;
		expected.ip = *word;
		expected.sp += sizeof(*word);
		active = &f;
		track_nested_owner = true;
		nested_owner = contended ? &native_peer : NULL;
		nested_acquires = nested_waits = 0;
		CHECK(handle_known_call(&f.regs, f.outer_lock_addr) == 1);
		CHECK(!memcmp(&f.regs, &expected, sizeof(expected)));
		CHECK(nested_owner == current && nested_acquires == 1 &&
		      nested_waits == contended && unlocked == before_unlock);
		CHECK(f.jit_lock_depth == 2 && f.jit_lock_kind[1] == KD_EXEC_LOCK_NATIVE &&
		      f.jit_lock_node[1] == &b && f.jit_lock_addr[1] == (unsigned long)&b);
		CHECK(f.control_call.phase == KD_CALL_COMPLETE && !f.resume_target &&
		      f.logical_task == &waiter && !f.outer_unlock_seen);

		*word = 0x901;
		f.regs.ip = unlocks[endpoint];
		f.regs.sp = (unsigned long)word;
		expected = f.regs;
		expected.ip = *word;
		expected.sp += sizeof(*word);
		CHECK(handle_known_call(&f.regs, f.outer_lock_addr) == 1);
		CHECK(!memcmp(&f.regs, &expected, sizeof(expected)));
		CHECK(!nested_owner && unlocked == before_unlock + 1 && f.jit_lock_depth == 1);
		CHECK(f.jit_lock_addr[0] == f.outer_lock_addr && !f.jit_lock_released[0]);
		CHECK(f.control_call.phase == KD_CALL_COMPLETE);

		f.regs.ip = unlocks[endpoint];
		f.regs.sp = (unsigned long)word;
		f.regs.di = f.outer_lock_addr;
		expected = f.regs;
		CHECK(handle_known_call(&f.regs, f.outer_lock_addr) == KD_EXE_KNOWN_OUTER_UNLOCK);
		CHECK(!memcmp(&f.regs, &expected, sizeof(expected)));
		f.regs.ip = 0xDEAD;
		expected = f.regs;
		CHECK(handle_known_call(&f.regs, f.outer_lock_addr) == 0);
		CHECK(!memcmp(&f.regs, &expected, sizeof(expected)));
		track_nested_owner = false;
	}
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
	check_call_register_preservation();
	check_mutex_stack_changes();
	check_mutex_stack_refusals();
	check_completed_mutex_native();
	check_acquired_spin_native();
	check_mutex_call_pair();
	CHECK(kd_exec_invariant_failures == 0);
	printf("after-outer production functions: %d checks, %d failures\n",
	       checks, failures);
	return failures != 0;
}
