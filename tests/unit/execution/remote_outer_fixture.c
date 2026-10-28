/* SPDX-License-Identifier: GPL-2.0 */
/* Production protocol with deterministic CPU switches, not a memory-model test.
 * Full kd_regs comparisons include software flags only, not hardware restore. */
#include <errno.h>
#include <stdint.h>
typedef uint8_t u8;
typedef uint16_t u16;
#include <pthread.h>
#include <sched.h>
#include <unistd.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned long long u64;
typedef long long s64;
typedef s64 atomic64_t;
typedef int atomic_t;
#define S64_MAX LLONG_MAX
#define likely(x) (x)
#define unlikely(x) (x)
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
#define atomic64_set(p, v) (*(p) = (v))
#define atomic64_read(p) (*(p))
#define atomic_set(p, v) (*(p) = (v))
#define atomic_read(p) (*(p))

/* Deterministic clock/atomic primitives, not concurrent counter or CPU-time
 * evidence. The included production timer must leave owner packets unchanged. */
static unsigned int timing_reads, mutex_puts;
static u64 ktime_get_ns(void)
{
	return timing_reads++ * 10ULL;
}
static bool atomic64_try_cmpxchg(atomic64_t *ptr, s64 *old, s64 value)
{
	if (*ptr != *old) {
		*old = *ptr;
		return false;
	}
	*ptr = value;
	return true;
}

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
struct kd_mutex {
	int unused;
};
#include "remote_types.h"

/* These scenarios never transfer queued mutex ownership. The dedicated custody
 * fixture validates that admission; keep this unrelated terminal route closed. */
static bool kd_exec_mutex_custody_accepted(const struct kd_exec_frame *frame)
{
	(void)frame;
	return false;
}
struct kd_spin_continuation { struct { struct kd_regs *regs_ref; } frame; };
struct kd_spin_node { struct kd_spin_continuation *execution; };

_Static_assert(sizeof(struct kd_regs) == 168, "guest x86-64 kd_regs size");
_Static_assert(offsetof(struct kd_regs, ip) == 0, "guest RIP offset");
_Static_assert(offsetof(struct kd_regs, sp) == 8, "guest RSP offset");

enum { CPUS = KD_EXEC_MAX_LOCK_DEPTH, WAITER_CPU = CPUS };
static _Thread_local unsigned int cpu;
static unsigned int checks, failures, wrong_owner, released;
static bool threaded_native;
static bool mixed_native, transferred_native, mixed_early;
static _Thread_local unsigned int logical_spin_pins;
static unsigned int release_entered, release_go;
static unsigned int borrows, borrow_puts, ends, refs, polls, stages;
static unsigned long kd_exec_invariant_failures;
static unsigned long kd_native_started, kd_native_completed, kd_native_unlocks;
static pthread_mutex_t kd_native_lock = PTHREAD_MUTEX_INITIALIZER;
static struct list_head kd_native_frames;
static struct task_struct logical = { 10 }, executors[CPUS];
static _Thread_local struct task_struct *current;
static struct kd_exec_frame frames[CPUS];
static struct kd_regs packets[CPUS];
static struct kd_exec_outer_unlock hooks[CPUS];
static raw_spinlock_t locks[CPUS];
static unsigned int live_frames;
static unsigned long stack[2];
static void (*native_step)(void);
static bool reuse_parent;
static unsigned int done_publications, packet_checks;
static struct kd_exec_frame reused_parent;
static void check_packets(void);
static void publish_before(const void *address, unsigned long value);
static void publish_after(const void *address);

#ifdef KD_REMOTE_MUTATION
#define STOP_MUTATION() exit(1)
#else
#define STOP_MUTATION() ((void)0)
#endif
#define CHECK(c)                                                             \
	do {                                                                 \
		__atomic_add_fetch(&checks, 1, __ATOMIC_RELAXED);                                                    \
		if (!(c)) {                                                  \
			__atomic_add_fetch(&failures, 1, __ATOMIC_RELAXED);                                          \
			fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #c); \
			STOP_MUTATION();                                     \
		}                                                            \
	} while (0)
#define BUG_ON(c)                                                           \
	do {                                                                \
		if (c) {                                                    \
			fprintf(stderr, "BUG line=%d: %s\n", __LINE__, #c); \
			exit(2);                                            \
		}                                                           \
	} while (0)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x, v) __atomic_store_n(&(x), (v), __ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define smp_store_release(p, v)                                   \
	do {                                                     \
		__auto_type publish_ptr = (p);                    \
		__typeof__(*publish_ptr) publish_value = (v);      \
		publish_before(publish_ptr,                       \
			       (unsigned long)publish_value);    \
		__atomic_store_n(publish_ptr, publish_value, __ATOMIC_RELEASE);                     \
		publish_after(publish_ptr);                       \
	} while (0)
#define atomic64_inc(p) __atomic_add_fetch((p), 1, __ATOMIC_RELAXED)
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
#define KD_PR_INFO(...) pr_info(__VA_ARGS__)
#define raw_spin_lock_irqsave(lock, flags) \
	do {                               \
		pthread_mutex_lock(lock); \
		(flags) = 0;               \
	} while (0)
#define raw_spin_unlock_irqrestore(lock, flags) \
	do {                                    \
		pthread_mutex_unlock(lock); \
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
static unsigned int preempt_count(void)
{
	return logical_spin_pins;
}
static void cond_resched(void)
{
	BUG_ON(!mixed_native && !transferred_native);
	BUG_ON(logical_spin_pins);
	sched_yield();
}
static void preempt_enable(void)
{
	BUG_ON(!mixed_native || cpu != WAITER_CPU || !logical_spin_pins);
	logical_spin_pins--;
}
static void preempt_disable(void)
{
	BUG_ON(true);
}
static void kd_mutex_task_put(struct task_struct *task)
{
	CHECK(task == &logical && list_empty(&kd_native_frames));
	mutex_puts++;
}
static int kd_mutex_jit_nested_unlock_ctx(struct kd_mutex *lock,
					  struct kd_exec_frame *frame)
{
	(void)lock;
	(void)frame;
	BUG_ON(true);
	return -EINVAL;
}
static int kd_mutex_jit_spin_unlock_ctx(raw_spinlock_t *lock,
				      struct kd_exec_frame *frame)
{
	BUG_ON(!mixed_native || cpu || frame != &frames[0] || lock != &locks[1]);
	CHECK(lock->owner == cpu && lock->held && frame->jit_lock_depth == 2);
	CHECK(frame->jit_lock_kind[1] == KD_EXEC_LOCK_MUTEX_SPIN);
	lock->held = false;
	__atomic_add_fetch(&released, 1, __ATOMIC_RELAXED);
	return kd_exec_frame_lock_pop(frame, (unsigned long)lock);
}
static int _kd_mutex_unlock_checked(struct kd_mutex *lock)
{
	raw_spinlock_t *physical = (raw_spinlock_t *)lock;
	BUG_ON(!transferred_native || cpu != WAITER_CPU || current != &logical);
	CHECK(physical == &locks[0] && physical->held && physical->owner == cpu);
	__atomic_store_n(&release_entered, 1, __ATOMIC_RELEASE);
	while (!__atomic_load_n(&release_go, __ATOMIC_ACQUIRE))
		sched_yield();
	physical->held = false;
	__atomic_add_fetch(&released, 1, __ATOMIC_RELAXED);
	return 0;
}
static int kd_spin_entry_borrow_get(const struct kd_spin_ref *ref)
{
	(void)ref;
	__atomic_add_fetch(&borrows, 1, __ATOMIC_RELAXED);
	__atomic_add_fetch(&refs, 1, __ATOMIC_RELAXED);
	return 0;
}
static int kd_spin_entry_borrow_put(const struct kd_spin_ref *ref, bool *last)
{
	(void)ref;
	CHECK(refs > 0);
	__atomic_add_fetch(&borrow_puts, 1, __ATOMIC_RELAXED);
	*last = __atomic_sub_fetch(&refs, 1, __ATOMIC_RELEASE) == 0;
	return 0;
}
void kd_spin_native_retire(struct kd_spin_ref *ref)
{
	(void)ref;
	CHECK(threaded_native && cpu == WAITER_CPU);
	while (__atomic_load_n(&refs, __ATOMIC_ACQUIRE))
		sched_yield();
	for (unsigned int i = 0; i < live_frames; i++)
		CHECK(!kd_exec_frame_validate(&frames[i]));
	ends++;
}
int kd_exec_frame_pop(struct kd_exec_frame *frame, struct kd_regs *regs)
{
	CHECK(!regs && frame == &frames[cpu] && frame->completion_seen);
	CHECK(!frame->resume_target && !frame->native_request &&
	      !kd_exec_frame_remote_pending(frame) && list_empty(&frame->native_link));
	frame->state = KD_EXEC_FRAME_UNUSED;
	frame->role = KD_ROLE_DONE;
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
	__atomic_add_fetch(&released, 1, __ATOMIC_RELAXED);
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
#include "timing_code.h"
#include "remote_code.h"

/* Every scheduler/RPC step must leave non-control registers and CALL words
 * intact. RIP/RSP changes are checked separately when a return is consumed. */
static void check_packets(void)
{
	for (unsigned int i = 0; i < live_frames; i++) {
		CHECK(!memcmp(&frames[i].regs, &packets[i], sizeof(packets[i])));
		packet_checks++;
	}
	CHECK(stack[0] == 0x300 && stack[1] == 0x400);
}

/* A parent can retire as soon as it sees DONE. Observe the link before the
 * store, not just the final detached state after the publishing call returns. */
static void publish_before(const void *address, unsigned long value)
{
	if (threaded_native) {
		for (unsigned int i = 0; i + 1 < live_frames; i++)
			if (address == &frames[i].remote_result && value == KD_EXEC_REMOTE_DONE)
				CHECK(frames[i + 1].state == KD_EXEC_FRAME_UNUSED);
		return;
	}
	for (unsigned int i = 0; i + 1 < live_frames; i++) {
		if (address != &frames[i].remote_result ||
		    value != KD_EXEC_REMOTE_DONE)
			continue;
		CHECK(!frames[i + 1].resume_target);
		CHECK(kd_exec_frame_can_complete(&frames[i + 1]));
		check_packets();
		done_publications++;
	}
}

static void publish_after(const void *address)
{
	if (threaded_native) return;
	if (!reuse_parent || address != &frames[0].remote_result)
		return;
	CHECK(frames[0].remote_result == KD_EXEC_REMOTE_DONE);
	CHECK(kd_exec_frame_can_complete(&frames[0]));
	/* Only an all-unlocked parent is reusable here. No task/lock reference
	 * is added; the poison makes a late publisher write directly observable. */
	frames[0] = reused_parent;
}

/* Nested polling models C -> B -> A while all requests remain on live stacks. */
static void cpu_relax(void)
{
	if (threaded_native) { sched_yield(); return; }
	unsigned int saved = cpu;
	BUG_ON(++polls > 100);
	for (unsigned int i = 0; i < live_frames; i++) {
		if (i == saved || !frames[i].remote_request)
			continue;
		select_cpu(i);
		kd_exec_remote_poll(&frames[i]);
		check_packets();
		select_cpu(saved);
		return;
	}
	if (native_step) {
		native_step();
		check_packets();
		select_cpu(saved);
		return;
	}
	BUG_ON(true);
}

static void setup(unsigned int count)
{
	kd_jit_timing_reset();
	timing_reads = mutex_puts = 0;
	memset(frames, 0, sizeof(frames));
	wrong_owner = released = borrows = borrow_puts = ends = refs = polls =
		stages = 0;
	kd_native_started = kd_native_completed = kd_native_unlocks = 0;
	native_step = NULL;
	reuse_parent = false;
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
		/* Distinct nonzero bytes expose accidental partial packet copies.
		 * Keep only the three control fields needed by the scripted calls. */
		memset(&frames[i].regs, 0x21 + i, sizeof(frames[i].regs));
		frames[i].regs.ip = 0x100;
		frames[i].regs.sp = (unsigned long)stack;
		frames[i].regs.di = i + 1 < count ?
					 (unsigned long)&locks[i + 1] : 0;
		packets[i] = frames[i].regs;
		if (i + 1 < count) {
			frames[i].delegated_lock_addr = frames[i].regs.di;
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
		select_cpu(j - 1);
		CHECK(kd_exec_frame_can_complete(&frames[j - 1]));
		CHECK(kd_exec_remote_complete(&frames[j - 1]) == 0);
		CHECK(!frames[j - 1].resume_target);
		CHECK(kd_exec_frame_complete(&frames[j - 1]) == 0);
	}
	check_packets();
}

static void check_final_call(void)
{
	struct kd_spin_node node;
	struct kd_regs regs;
	struct kd_regs expected;

	setup(2);
	regs = frames[1].regs;
	node.execution = &(struct kd_spin_continuation){ .frame.regs_ref = &regs };
	expected = regs;
	/* Refusal must leave both packets untouched, including non-control state. */
	CHECK(kd_spin_finish_remote_node(&node, &regs, &frames[0]) == -EINVAL);
	CHECK(!memcmp(&regs, &expected, sizeof(regs)));
	CHECK(!memcmp(node.execution->frame.regs_ref, &packets[1], sizeof(*node.execution->frame.regs_ref)));
	CHECK(kd_exec_frame_record_event(&frames[1], KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	CHECK(kd_exec_remote_complete(&frames[1]) == 0);
	select_cpu(0);
	expected = *node.execution->frame.regs_ref;
	expected.ip = stack[0];
	expected.sp += sizeof(unsigned long);
	CHECK(kd_spin_finish_remote_node(&node, &regs, &frames[0]) ==
	      KD_SPIN_NESTED_DELEGATED);
	CHECK(regs.ip == stack[0] && regs.sp == (unsigned long)(stack + 1));
	CHECK(!memcmp(&regs, &expected, sizeof(regs)));
	CHECK(!memcmp(node.execution->frame.regs_ref, &expected, sizeof(*node.execution->frame.regs_ref)));
	check_packets();
	CHECK(!frames[0].outer_unlock_seen);
	setup(2);
	regs = frames[1].regs;
	node.execution = &(struct kd_spin_continuation){ .frame.regs_ref = &regs };
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == 0);
	CHECK(kd_exec_frame_record_event(&frames[1], KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	CHECK(kd_exec_remote_complete(&frames[1]) == 0);
	select_cpu(0);
	CHECK(kd_spin_finish_remote_node(&node, &regs, &frames[0]) ==
	      KD_SPIN_NESTED_PARENT_OOO);
	CHECK(regs.ip == node.execution->frame.regs_ref->ip && regs.sp == (unsigned long)stack);
	CHECK(!memcmp(&regs, &packets[1], sizeof(regs)));
	CHECK(!memcmp(node.execution->frame.regs_ref, &packets[1], sizeof(*node.execution->frame.regs_ref)));
	CHECK(stack[0] == 0x300 && stack[1] == 0x400);
	check_packets();
}

/* DONE permits a no-lock ancestor to disappear before the child returns from
 * publication. Keep that boundary separate from borrowed native unlock ACK. */
static void check_done_reuse(void)
{
	setup(2);
	CHECK(kd_spin_jit_nested_unlock_ctx(&locks[0], &frames[1]) == 0);
	CHECK(kd_exec_frame_record_event(&frames[1], KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	CHECK(!kd_exec_frame_can_complete(&frames[0]));
	memset(&reused_parent, 0xa5, sizeof(reused_parent));
	reuse_parent = true;
	CHECK(kd_exec_remote_complete(&frames[1]) == 0);
	reuse_parent = false;
	CHECK(!memcmp(&frames[0], &reused_parent, sizeof(reused_parent)));
	CHECK(!frames[1].resume_target);
	CHECK(!memcmp(&frames[1].regs, &packets[1], sizeof(packets[1])));
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
	frames[0].delegated_lock_addr = 0;
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
	check_packets();
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

/* Execute real native routing and retirement concurrently. Final unlock must
 * wait for every frame, even an ancestor with zero remaining physical locks. */
static void *native_owner(void *argument)
{
	unsigned int index = (uintptr_t)argument;
	struct kd_spin_ref origin = frames[index].spin_origin;
	raw_spinlock_t *owned = &locks[index];
	bool last, retired = false;

	select_cpu(index);
	CHECK(kd_exec_native_wait(&frames[index]) == 0);
	/* Widen the physical ACK -> pop interval without altering any protocol
	 * state. The waiter must keep its ticket and packet throughout. */
	usleep(1000);
	CHECK(!ends);
	CHECK(kd_exec_frame_complete(&frames[index]) == 0);
	CHECK(kd_exec_spin_retire(&frames[index], &retired) == 0 && retired);
	/* The enclosing physical batch eventually releases its retained word. */
	if (owned->held) origin_raw_spin_unlock(owned);
	CHECK(kd_spin_entry_borrow_put(&origin, &last) == 0);
	return NULL;
}

static void check_native_chain(unsigned int count, bool early, bool reverse)
{
	pthread_t owners[CPUS];

	setup(count);
	kd_jit_timing = false;
	if (early)
		for (unsigned int i = count - 1; i > 0; i--)
			CHECK(kd_spin_jit_nested_unlock_ctx(&locks[i - 1], &frames[count - 1]) == 0);
	for (unsigned int i = count; i > 0; i--) {
		select_cpu(i - 1);
		frames[i - 1].complex_ready = true;
		frames[i - 1].regs_ref = &frames[0].regs;
		if (i < count)
			frames[i - 1].control_call.phase = KD_CALL_COMPLETE;
		CHECK(kd_exec_native_begin(&frames[i - 1], false) == 0);
		CHECK(kd_exec_remote_native(&frames[i - 1]) == 0);
	}
	CHECK(refs == count && borrows == count);
	threaded_native = true;
	for (unsigned int i = 0; i < count; i++)
		CHECK(!pthread_create(&owners[i], NULL, native_owner, (void *)(uintptr_t)i));
	select_cpu(WAITER_CPU);
	for (unsigned int i = early ? count - 1 : 0; i < count; i++)
		CHECK(kd_exec_native_unlock((unsigned long)&locks[reverse ? count - 1 - i : i], false));
	CHECK(ends == 1 && !refs && borrow_puts == count);
	for (unsigned int i = 0; i < count; i++)
		CHECK(!pthread_join(owners[i], NULL));
	threaded_native = false;
	CHECK(kd_native_started == count && kd_native_completed == count);
	CHECK(kd_native_unlocks == (early ? 1U : count) && released == count);
	CHECK(list_empty(&kd_native_frames) && !wrong_owner);
	check_packets();
}

static void check_empty_native(void)
{
	pthread_t owner;

	setup(1);
	kd_jit_timing = false;
	frames[0].complex_ready = true;
	CHECK(!kd_exec_frame_record_event(&frames[0], KD_EXEC_EVENT_OUTER_UNLOCK, NULL));
	frames[0].remote_result = KD_EXEC_REMOTE_NATIVE;
	frames[0].control_call.phase = KD_CALL_COMPLETE;
	CHECK(!kd_exec_native_begin(&frames[0], false) && refs == 1);
	CHECK(!kd_exec_native_pending(&logical));
	frames[0].remote_result = KD_EXEC_REMOTE_DONE;
	threaded_native = true;
	CHECK(!pthread_create(&owner, NULL, native_owner, NULL));
	select_cpu(WAITER_CPU);
	/* Same pre-restore barrier used when NATIVE_READY has no lock routes. */
	kd_spin_native_retire(&frames[0].spin_origin);
	CHECK(!pthread_join(owner, NULL));
	threaded_native = false;
	CHECK(ends == 1 && !refs && borrow_puts == 1 && !kd_native_unlocks);
}

/* Exercise production family matching and the request lifetime in both mixed
 * modes. Physical ticket operations and mutex owner exchange are independently
 * covered by test_mutex_mixed; these substitutes observe who performs unlock. */
static void *mixed_native_waiter(void *unused)
{
	(void)unused;
	select_cpu(WAITER_CPU);
	if (mixed_native) {
		logical_spin_pins = 1;
		if (mixed_early)
			CHECK(kd_exec_native_unlock((unsigned long)&locks[0], true));
		CHECK(!kd_exec_native_unlock((unsigned long)&locks[1], true));
		CHECK(kd_exec_native_unlock((unsigned long)&locks[1], false));
		CHECK(!logical_spin_pins && !locks[1].held);
	}
	if (!mixed_early)
		CHECK(kd_exec_native_unlock((unsigned long)&locks[0], true));
	CHECK(list_empty(&kd_native_frames) && mutex_puts == 1);
	return NULL;
}

static void *delay_transferred_release(void *unused)
{
	(void)unused;
	while (!__atomic_load_n(&release_entered, __ATOMIC_ACQUIRE))
		sched_yield();
	/* W is stopped inside its physical unlock. C may neither acknowledge it
	 * nor mark the ledger released merely because the request was published. */
	for (unsigned int i = 0; i < 1000; i++) {
		struct kd_native_request *request = smp_load_acquire(&frames[0].native_request);
		CHECK(request && !READ_ONCE(request->done));
		CHECK(!READ_ONCE(frames[0].outer_unlock_seen) && !READ_ONCE(hooks[0].released));
		sched_yield();
	}
	__atomic_store_n(&release_go, 1, __ATOMIC_RELEASE);
	return NULL;
}

static void check_mixed_native(bool transfer, bool early)
{
	pthread_t waiter, delayed;
	struct kd_exec_frame *frame = &frames[0];

	setup(1);
	kd_jit_timing = false;
	frame->mutex_backend = true;
	frame->complex_ready = true;
	frame->mutex_mixed.transferred = transfer;
	frame->mutex_mixed.picked_up = transfer;
	if (transfer) {
		locks[0].owner = WAITER_CPU;
	} else {
		locks[1] = (raw_spinlock_t){ .owner = 0, .held = true };
		frame->jit_lock_depth = frame->held_lock_depth = 2;
		frame->jit_lock_addr[1] = (unsigned long)&locks[1];
		frame->jit_lock_kind[1] = KD_EXEC_LOCK_MUTEX_SPIN;
		frame->jit_lock_node[1] = &locks[1];
	}
	CHECK(!kd_exec_native_begin(frame, true));
	mixed_native = !transfer;
	transferred_native = transfer;
	mixed_early = early;
	threaded_native = true;
	release_entered = release_go = 0;
	if (transfer)
		CHECK(!pthread_create(&delayed, NULL, delay_transferred_release, NULL));
	CHECK(!pthread_create(&waiter, NULL, mixed_native_waiter, NULL));
	CHECK(!kd_exec_native_wait(frame));
	CHECK(!pthread_join(waiter, NULL));
	if (transfer)
		CHECK(!pthread_join(delayed, NULL));
	threaded_native = mixed_native = transferred_native = mixed_early = false;
	CHECK(kd_exec_frame_can_complete(frame));
	CHECK(kd_native_unlocks == (transfer ? 1U : 2U));
	CHECK(kd_native_started == 1 && kd_native_completed == 1 && mutex_puts == 1);
	CHECK(!frame->native_request && list_empty(&kd_native_frames));
	CHECK(locks[0].held == !(transfer || early) && hooks[0].released == (transfer || early));
	CHECK(released == (early ? 2U : 1U) && !wrong_owner && !refs && !ends);
	check_packets();
}

/* Nested waits enclose one another. N deterministic calls consume 2*N clock
 * samples and N*N ticks, rather than N independent elapsed intervals. */
static void check_native_timing(unsigned int count, bool mutex)
{
	unsigned int wanted = mutex ? KD_JIT_TIME_NATIVE_MUTEX_WAIT :
				      KD_JIT_TIME_NATIVE_SPIN_WAIT;

	CHECK(timing_reads == (kd_jit_timing ? 2 * count : 0));
	for (unsigned int i = 0; i < KD_JIT_TIME_COUNT; i++) {
		bool selected = kd_jit_timing && i == wanted;
		CHECK(kd_jit_times[i].samples == (selected ? count : 0));
		CHECK(kd_jit_times[i].ns == (selected ? count * count * 10 : 0));
		CHECK(!kd_jit_times[i].invalid);
	}
	check_packets();
}

/* Exercise the shared wait's mutex completion and rejected unlock as well as
 * spin relays. Errors must stay errors even when observation is enabled. This
 * substitutes task-release/lock primitives, not Linux mutex ownership. */
static void check_wait_returns(bool mutex, bool rejected)
{
	struct kd_native_request request;

	setup(1);
	frames[0].mutex_backend = mutex;
	/* This manually constructed native fixture has generic routing state. */
	if (mutex)
		frames[0].complex_ready = true;
	CHECK(kd_exec_native_begin(&frames[0], mutex) == 0);
	if (mutex) {
		struct task_struct *executor = current;
		struct qspinlock physical = locks[0];
		unsigned int retained = refs, puts = mutex_puts;
		struct kd_exec_frame before = frames[0];

		/* A task's unrelated native C unlock cannot request borrowed A.
		 * Exercise the production matcher before the existing owner ACK. */
		current = &logical;
		CHECK(!kd_exec_native_unlock((unsigned long)&locks[1], true));
		CHECK(!kd_exec_native_unlock(frames[0].outer_lock_addr, false));
		current = executor;
		CHECK(current != &logical);
		CHECK(!kd_exec_native_unlock(frames[0].outer_lock_addr, true));
		CHECK(!memcmp(&before, &frames[0], sizeof(before)) &&
		      !memcmp(&physical, &locks[0], sizeof(physical)));
		CHECK(!list_empty(&kd_native_frames) && !frames[0].native_request &&
		      refs == retained && mutex_puts == puts && kd_native_started == 1 &&
		      !kd_native_completed && !kd_native_unlocks && !polls);
	}
	if (rejected)
		frames[0].state = KD_EXEC_FRAME_ERROR;
	request = (struct kd_native_request){ .lock_addr = frames[0].outer_lock_addr };
	frames[0].native_request = &request;
	CHECK(kd_exec_native_wait(&frames[0]) == (rejected ? -EALREADY : 0));
	CHECK(request.done && request.result == (rejected ? -EALREADY : 0));
	CHECK(!frames[0].native_request && list_empty(&kd_native_frames));
	CHECK(kd_native_started == 1 && kd_native_completed == !rejected);
	CHECK(kd_native_unlocks == 1 && mutex_puts == (mutex && !rejected));
	CHECK(!wrong_owner && !polls);
	check_native_timing(1, mutex);
}

int main(void)
{
#ifdef KD_REMOTE_BUG_ONLY
	BUG_ON(true);
#endif
	for (unsigned int i = 2; i <= CPUS; i++) {
		check_remote_chain(i, false);
		check_remote_chain(i, true);
	}
	check_final_call();
	check_refusals();
	check_relay_refusals();
	check_done_reuse();
	for (unsigned int count = 2; count <= CPUS; count++) {
		check_native_chain(count, false, false);
		check_native_chain(count, false, true);
		check_native_chain(count, true, false);
	}
	check_empty_native();
	check_mixed_native(false, false);
	check_mixed_native(false, true);
	check_mixed_native(true, false);
	for (unsigned int enabled = 0; enabled < 2; enabled++) {
		kd_jit_timing = enabled;
		for (unsigned int mutex = 0; mutex < 2; mutex++) {
			check_wait_returns(mutex, false);
			check_wait_returns(mutex, true);
		}
	}
	printf("remote outer production: %u checks, %u failures\n", checks,
	       failures);
	printf("remote packet/publication: regs=%zu packet_checks=%u done=%u\n",
	       sizeof(struct kd_regs), packet_checks, done_publications);
	return failures != 0;
}
