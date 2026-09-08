/* SPDX-License-Identifier: GPL-2.0 */
/* Production protocol with deterministic CPU switches, not a memory-model test. */
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
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
struct qspinlock {
	unsigned int owner;
	bool held;
};
typedef struct qspinlock raw_spinlock_t;
struct mutex {
	int unused;
};
struct kd_spin_node {
	struct pt_regs regs;
};
#include "remote_types.h"

enum { CPUS = KD_EXEC_MAX_LOCK_DEPTH, WAITER_CPU = CPUS };
static unsigned int cpu, checks, failures, wrong_owner, released;
static unsigned int borrows, borrow_puts, ends, refs, polls, stages;
static unsigned long kd_exec_invariant_failures;
static unsigned long kd_native_started, kd_native_completed, kd_native_unlocks;
static int kd_native_lock;
static struct list_head kd_native_frames;
static struct task_struct logical = { 10 }, executors[CPUS];
static struct task_struct *current;
static struct kd_exec_frame frames[CPUS];
static struct kd_exec_outer_unlock hooks[CPUS];
static raw_spinlock_t locks[CPUS];
static unsigned int live_frames;
static unsigned long stack[2];
static void (*native_step)(void);

#define CHECK(c)                                                             \
	do {                                                                 \
		checks++;                                                    \
		if (!(c)) {                                                  \
			failures++;                                          \
			fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #c); \
		}                                                            \
	} while (0)
#define BUG_ON(c)                                                           \
	do {                                                                \
		if (c) {                                                    \
			fprintf(stderr, "BUG line=%d: %s\n", __LINE__, #c); \
			abort();                                            \
		}                                                           \
	} while (0)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, v) (*(p) = (v))
#define atomic64_inc(p) (++*(p))
#define WARN_ON_ONCE(c) ((void)(c))
#define cmpxchg(p, old, value)                  \
	({                                      \
		__typeof__(*(p)) result = *(p); \
		if (result == (old)) {          \
			*(p) = (value);         \
		}                               \
		result;                         \
	})
#define pr_info(...)                         \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
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
#define KD_EXE_KNOWN_OUTER_UNLOCK 3
#define INIT_LIST_HEAD(p)        \
	do {                     \
		(p)->next = (p); \
		(p)->prev = (p); \
	} while (0)
#define list_entry(p, type, member) \
	((type *)((char *)(p) - offsetof(type, member)))
#define list_for_each_entry(pos, head, member)                         \
	for (pos = list_entry((head)->next, __typeof__(*pos), member); \
	     &(pos)->member != (head);                                 \
	     pos = list_entry((pos)->member.next, __typeof__(*pos), member))

static bool list_empty(struct list_head *head)
{
	return head->next == head;
}
static void list_add(struct list_head *node, struct list_head *head)
{
	node->prev = head;
	node->next = head->next;
	head->next->prev = node;
	head->next = node;
}
static void list_del_init(struct list_head *node)
{
	node->prev->next = node->next;
	node->next->prev = node->prev;
	INIT_LIST_HEAD(node);
}
static void select_cpu(unsigned int next)
{
	cpu = next;
	current = next == WAITER_CPU ? &logical : &executors[next];
}
static unsigned int raw_smp_processor_id(void)
{
	return cpu;
}
static bool need_resched(void)
{
	return false;
}
static void cond_resched(void)
{
	BUG_ON(true);
}
static void preempt_enable(void)
{
	BUG_ON(true);
}
static void preempt_disable(void)
{
	BUG_ON(true);
}
static void kd_mutex_task_put(struct task_struct *task)
{
	(void)task;
	BUG_ON(true);
}
static int kd_mutex_jit_nested_unlock_ctx(struct mutex *lock,
					  struct kd_exec_frame *frame)
{
	(void)lock;
	(void)frame;
	BUG_ON(true);
	return -EINVAL;
}
static int kd_spin_entry_borrow_get(const struct kd_spin_ref *ref)
{
	(void)ref;
	borrows++;
	refs++;
	return 0;
}
static int kd_spin_entry_borrow_put(const struct kd_spin_ref *ref, bool *last)
{
	(void)ref;
	CHECK(refs > 0);
	borrow_puts++;
	refs--;
	*last = refs == 0;
	return 0;
}
static int kd_spin_entry_end(const struct kd_spin_ref *ref)
{
	(void)ref;
	CHECK(cpu == WAITER_CPU && refs == 0);
	ends++;
	return 0;
}
struct kd_exec_frame *kd_exec_current_frame(void)
{
	return cpu < live_frames ? &frames[cpu] : NULL;
}
static void kd_spin_debug_nested_unlock(raw_spinlock_t *lock)
{
	(void)lock;
}
static void origin_raw_spin_unlock(raw_spinlock_t *lock)
{
	if (lock->owner != cpu) {
		wrong_owner++;
		return;
	}
	CHECK(lock->held);
	lock->held = false;
	released++;
}
static int kd_spin_nested_shadow_remove(struct qspinlock *lock)
{
	(void)lock;
	return 0;
}
static int kd_spin_nested_unlock(struct qspinlock *lock)
{
	if (lock->owner != cpu) {
		wrong_owner++;
		return KD_SPIN_NESTED_UNLOCK_OOO;
	}
	origin_raw_spin_unlock(lock);
	return 0;
}
static int release_outer(struct kd_exec_frame *frame,
			 struct kd_exec_outer_unlock *hook)
{
	(void)hook;
	CHECK(frame == &frames[cpu]);
	origin_raw_spin_unlock((raw_spinlock_t *)frame->outer_lock_addr);
	return 0;
}
int kd_spin_jit_nested_unlock_ctx(raw_spinlock_t *lock,
				  struct kd_exec_frame *frame);
static void cpu_relax(void);
#include "remote_code.h"

/* Nested polling models C -> B -> A while all requests remain on live stacks. */
static void cpu_relax(void)
{
	unsigned int saved = cpu;
	BUG_ON(++polls > 100);
	for (unsigned int i = 0; i < live_frames; i++) {
		if (i == saved || !frames[i].remote_request)
			continue;
		select_cpu(i);
		kd_exec_remote_poll(&frames[i]);
		select_cpu(saved);
		return;
	}
	if (native_step) {
		native_step();
		select_cpu(saved);
		return;
	}
	BUG_ON(true);
}

static void setup(unsigned int count)
{
	memset(frames, 0, sizeof(frames));
	wrong_owner = released = borrows = borrow_puts = ends = refs = polls =
		stages = 0;
	kd_native_started = kd_native_completed = kd_native_unlocks = 0;
	native_step = NULL;
	live_frames = count;
	logical.pid = 10;
	INIT_LIST_HEAD(&kd_native_frames);
	stack[0] = 0x300;
	stack[1] = 0x400;
	for (unsigned int i = 0; i < count; i++) {
		executors[i].pid = 11 + i;
		locks[i] = (raw_spinlock_t){ .owner = i, .held = true };
		hooks[i] =
			(struct kd_exec_outer_unlock){ .release =
							       release_outer };
		frames[i] = (struct kd_exec_frame){
			.regs = { .ip = 0x100,
				  .sp = (unsigned long)stack,
				  .di = i + 1 < count ?
						(unsigned long)&locks[i + 1] :
						0 },
			.entry_ip = 0x100,
			.outer_lock_addr = (unsigned long)&locks[i],
			.gsbase = 1,
			.logical_task = &logical,
			.logical_pid = logical.pid,
			.held_lock_depth = i + 1,
			.outer_lock_depth = i + 1,
			.outer_lock_index = i,
			.jit_lock_depth = i + 1,
			.state = KD_EXEC_FRAME_RUNNING,
			.executed = true,
			.outer_unlock_hook = &hooks[i],
			.resume_target = i ? &frames[i - 1] : NULL,
			.remote_result = i + 1 < count ?
						 KD_EXEC_REMOTE_WAITING :
						 KD_EXEC_REMOTE_IDLE,
		};
		if (i + 1 < count) {
			frames[i].control_call.phase = KD_CALL_ENTERED;
			frames[i].control_call.return_ip = 0x300;
		}
		for (unsigned int j = 0; j <= i; j++) {
			frames[i].jit_lock_addr[j] = (unsigned long)&locks[j];
			frames[i].jit_lock_kind[j] = KD_EXEC_LOCK_QUEUE_OWNER;
		}
		CHECK(kd_exec_frame_validate(&frames[i]));
	}
	select_cpu(count - 1);
}

static void check_remote_chain(unsigned int count, bool reverse)
{
	setup(count);
	for (unsigned int ordinal = 0; ordinal + 1 < count; ordinal++) {
		unsigned int i = reverse ? count - 2 - ordinal : ordinal;
		CHECK(kd_spin_jit_nested_unlock_ctx(&locks[i],
						    &frames[count - 1]) == 0);
		CHECK(!wrong_owner && !locks[i].held && locks[count - 1].held);
		for (unsigned int j = i; j < count; j++)
			CHECK(frames[j].jit_lock_released[i]);
		CHECK(frames[i].outer_unlock_seen && hooks[i].released);
		CHECK(kd_exec_frame_locks_released(&frames[i]));
		CHECK(!kd_exec_frame_can_complete(&frames[i]));
		CHECK(kd_exec_frame_complete(&frames[i]) == -EINVAL);
		CHECK(kd_exec_remote_complete(&frames[count - 1]) == -EINVAL);
		CHECK(kd_spin_jit_nested_unlock_ctx(
			      &locks[i], &frames[count - 1]) == -EALREADY);
	}
	CHECK(released == count - 1);
	CHECK(kd_exec_frame_record_event(&frames[count - 1],
					 KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	for (unsigned int j = count; j > 0; j--) {
		CHECK(kd_exec_frame_can_complete(&frames[j - 1]));
		CHECK(kd_exec_remote_complete(&frames[j - 1]) == 0);
		CHECK(!frames[j - 1].resume_target);
		CHECK(kd_exec_frame_complete(&frames[j - 1]) == 0);
	}
}

static void check_final_call(void)
{
	struct kd_spin_node node;
	struct pt_regs regs;
	setup(2);
	node.regs = frames[1].regs;
	CHECK(kd_spin_finish_remote_node(&node, &regs, &frames[0]) == -EINVAL);
	CHECK(kd_exec_frame_record_event(&frames[1], KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	CHECK(kd_exec_remote_complete(&frames[1]) == 0);
	CHECK(kd_spin_finish_remote_node(&node, &regs, &frames[0]) ==
	      KD_SPIN_NESTED_DELEGATED);
	CHECK(regs.ip == stack[0] && regs.sp == (unsigned long)(stack + 1));
	CHECK(!frames[0].outer_unlock_seen);
	setup(2);
	node.regs = frames[1].regs;
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == 0);
	CHECK(kd_exec_frame_record_event(&frames[1], KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	CHECK(kd_exec_remote_complete(&frames[1]) == 0);
	CHECK(kd_spin_finish_remote_node(&node, &regs, &frames[0]) ==
	      KD_SPIN_NESTED_PARENT_OOO);
	CHECK(regs.ip == node.regs.ip && regs.sp == (unsigned long)stack);
	CHECK(stack[0] == 0x300 && stack[1] == 0x400);
}

static void check_refusals(void)
{
	struct kd_exec_frame parent, child;
	setup(2);
	parent = frames[0];
	child = frames[1];
	frames[1].resume_target = NULL;
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == -EINVAL);
	frames[1] = child;
	frames[0].logical_task = &executors[0];
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == -EINVAL);
	frames[0] = parent;
	frames[0].regs.di = 0;
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == -EINVAL);
	frames[0] = parent;
	frames[0].control_call.phase = KD_CALL_COMPLETE;
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == -EINVAL);
	frames[0] = parent;
	frames[0].remote_result = KD_EXEC_REMOTE_NATIVE;
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == -EINVAL);
	frames[0] = parent;
	frames[0].remote_request = (void *)1;
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == -EBUSY);
	CHECK(kd_exec_remote_native(&frames[1]) == -EINVAL);
	frames[0] = parent;
	frames[1].outer_lock_index = KD_EXEC_MAX_LOCK_DEPTH + 1;
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == -EINVAL);
	frames[1] = child;
	frames[1].mutex_backend = true;
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == -EINVAL);
	frames[1] = child;
	select_cpu(0);
	CHECK(kd_exec_remote_unlock(&frames[1], (unsigned long)&locks[0]) ==
	      -EINVAL);
	CHECK(released == 0 && polls == 0 && !wrong_owner);
	select_cpu(1);
	frames[1].executed = false;
	kd_exec_remote_cancel(&frames[1]);
	CHECK(frames[0].remote_result == KD_EXEC_REMOTE_WAITING &&
	      !frames[1].resume_target);
	CHECK(!kd_exec_frame_remote_pending(NULL));
}

/* A's executor waits after its last local ACK. W can return only after B's ACK. */
static void finish_native_b(void)
{
	if (stages++ == 0) {
		CHECK(cpu == 0 && refs == 1 && !locks[0].held && locks[1].held);
		CHECK(list_empty(&frames[0].native_link));
		CHECK(!kd_exec_frame_can_complete(&frames[0]));
		select_cpu(WAITER_CPU);
		CHECK(kd_exec_native_unlock((unsigned long)&locks[1], false));
		CHECK(ends == 1 && refs == 0 && borrow_puts == borrows);
		logical.pid =
			-999; /* Delayed relay log must use the saved PID. */
		return;
	}
	CHECK(stages == 2 && cpu == WAITER_CPU);
	select_cpu(1);
	CHECK(kd_exec_native_wait(&frames[1]) == 0);
	CHECK(!frames[1].resume_target &&
	      frames[0].remote_result == KD_EXEC_REMOTE_DONE);
}

static void check_native_chain(bool early_outer)
{
	struct kd_native_request a = { .lock_addr = (unsigned long)&locks[0] };
	setup(2);
	if (early_outer)
		CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) ==
		      0);
	CHECK(kd_exec_native_begin(&frames[1], false) == 0);
	CHECK(kd_exec_remote_native(&frames[1]) == 0);
	frames[0].control_call.phase = KD_CALL_COMPLETE;
	select_cpu(0);
	CHECK(kd_exec_native_begin(&frames[0], false) == 0);
	CHECK(refs == (early_outer ? 1U : 2U));
	CHECK(kd_native_started == 2 && kd_native_completed == 0);
	if (!early_outer)
		frames[0].native_request = &a;
	else
		CHECK(list_empty(&frames[0].native_link));
	native_step = finish_native_b;
	CHECK(kd_exec_native_wait(&frames[0]) == 0);
	CHECK(kd_native_completed == 2 &&
	      kd_native_unlocks == (early_outer ? 1UL : 2UL));
	CHECK(frames[0].logical_pid == 10 && list_empty(&kd_native_frames));
	CHECK(kd_exec_frame_can_complete(&frames[0]) &&
	      kd_exec_frame_can_complete(&frames[1]));
	CHECK(!wrong_owner && released == 1 && ends == 1);
	if (!early_outer)
		CHECK(a.done && !a.spin_last && !a.result);
}

static void check_relay_refusals(void)
{
	struct kd_exec_frame bad;
	setup(2);
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == 0);
	CHECK(kd_exec_remote_native(&frames[1]) == 0);
	frames[0].control_call.phase = KD_CALL_COMPLETE;
	select_cpu(0);
	bad = frames[0];
	bad.jit_lock_depth = 0;
	bad.outer_lock_index = KD_EXEC_MAX_LOCK_DEPTH;
	memset(bad.jit_lock_addr, 0, sizeof(bad.jit_lock_addr));
	memset(bad.jit_lock_kind, 0, sizeof(bad.jit_lock_kind));
	memset(bad.jit_lock_released, 0, sizeof(bad.jit_lock_released));
	CHECK(kd_exec_frame_validate(&bad));
	CHECK(kd_exec_native_begin(&bad, false) == -EINVAL);
	bad = frames[0];
	bad.remote_result = KD_EXEC_REMOTE_WAITING;
	CHECK(kd_exec_native_begin(&bad, false) == -EINVAL);
	bad = frames[0];
	bad.control_call.phase = KD_CALL_ENTERED;
	CHECK(kd_exec_native_begin(&bad, false) == -EINVAL);
	bad = frames[0];
	bad.mutex_backend = true;
	CHECK(kd_exec_native_begin(&bad, true) == -EINVAL);
	CHECK(borrows == 0 && kd_native_started == 0 &&
	      list_empty(&kd_native_frames));
}

static void finish_three_native(void)
{
	unsigned int stage = stages++;

	if (stage == 0) {
		CHECK(cpu == 0 && refs == 1 &&
		      !kd_exec_frame_can_complete(&frames[0]));
		select_cpu(1);
		CHECK(kd_exec_native_wait(&frames[1]) == 0);
		CHECK(frames[0].remote_result == KD_EXEC_REMOTE_DONE);
	} else if (stage == 1) {
		CHECK(cpu == 1 && list_empty(&frames[1].native_link));
		select_cpu(WAITER_CPU);
		CHECK(kd_exec_native_unlock((unsigned long)&locks[2], false));
		CHECK(ends == 1 && refs == 0);
		logical.pid = -999;
	} else {
		CHECK(stage == 2 && cpu == WAITER_CPU);
		select_cpu(2);
		CHECK(kd_exec_native_wait(&frames[2]) == 0);
		CHECK(frames[1].remote_result == KD_EXEC_REMOTE_DONE);
	}
}

static void check_three_native(void)
{
	setup(3);
	/* Unlock the nearer ancestor first as well as testing A-before-B above. */
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[1], &frames[2]) == 0);
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[2]) == 0);
	for (unsigned int i = 3; i > 0; i--) {
		select_cpu(i - 1);
		if (i < 3)
			frames[i - 1].control_call.phase = KD_CALL_COMPLETE;
		CHECK(kd_exec_native_begin(&frames[i - 1], false) == 0);
		CHECK(kd_exec_remote_native(&frames[i - 1]) == 0);
	}
	CHECK(borrows == 1 && kd_native_started == 3);
	native_step = finish_three_native;
	CHECK(kd_exec_native_wait(&frames[0]) == 0);
	CHECK(kd_native_completed == 3 && kd_native_unlocks == 1);
	CHECK(borrow_puts == 1 && ends == 1 && list_empty(&kd_native_frames));
	for (unsigned int i = 0; i < 3; i++) {
		CHECK(!frames[i].resume_target &&
		      kd_exec_frame_can_complete(&frames[i]));
		CHECK(frames[i].logical_pid == 10);
	}
	CHECK(!wrong_owner && released == 2);
}

static void finish_deep_native(void)
{
	unsigned int saved = cpu, last = live_frames - 1;

	if (cpu < last - 1) {
		CHECK(refs == 1 && list_empty(&frames[cpu].native_link));
		select_cpu(cpu + 1);
		CHECK(kd_exec_native_wait(&frames[cpu]) == 0);
		CHECK(frames[saved].remote_result == KD_EXEC_REMOTE_DONE);
	} else if (cpu == last - 1) {
		select_cpu(WAITER_CPU);
		CHECK(kd_exec_native_unlock((unsigned long)&locks[last],
					    false));
		CHECK(ends == 1 && refs == 0);
		logical.pid = -999;
	} else {
		CHECK(cpu == WAITER_CPU);
		select_cpu(last);
		CHECK(kd_exec_native_wait(&frames[last]) == 0);
	}
}

static void check_deep_native(unsigned int count)
{
	setup(count);
	for (unsigned int i = count - 1; i > 0; i--)
		CHECK(kd_spin_jit_nested_unlock_ctx(&locks[i - 1],
						    &frames[count - 1]) == 0);
	for (unsigned int i = count; i > 0; i--) {
		select_cpu(i - 1);
		if (i < count)
			frames[i - 1].control_call.phase = KD_CALL_COMPLETE;
		CHECK(kd_exec_native_begin(&frames[i - 1], false) == 0);
		CHECK(kd_exec_remote_native(&frames[i - 1]) == 0);
	}
	CHECK(borrows == 1 && kd_native_started == count);
	native_step = finish_deep_native;
	CHECK(kd_exec_native_wait(&frames[0]) == 0);
	CHECK(kd_native_completed == count && kd_native_unlocks == 1);
	CHECK(borrow_puts == 1 && ends == 1 && list_empty(&kd_native_frames));
	CHECK(!wrong_owner && released == count - 1);
	for (unsigned int i = 0; i < count; i++)
		CHECK(!frames[i].resume_target && frames[i].logical_pid == 10 &&
		      kd_exec_frame_can_complete(&frames[i]));
}

int main(void)
{
	for (unsigned int i = 2; i <= CPUS; i++) {
		check_remote_chain(i, false);
		check_remote_chain(i, true);
	}
	check_final_call();
	check_refusals();
	check_native_chain(false);
	check_native_chain(true);
	check_relay_refusals();
	check_three_native();
	for (unsigned int i = 4; i <= CPUS; i++)
		check_deep_native(i);
	printf("remote outer production: %u checks, %u failures\n", checks,
	       failures);
	return failures != 0;
}
