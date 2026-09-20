/* SPDX-License-Identifier: GPL-2.0 */
/* Compile actual mutex combiner/outer-event code with deterministic peers.
 * Track retained owner and exactly-once suffix decisions, not Linux scheduling. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct {
	int counter;
} atomic_t;
struct task_struct {
	int pid;
};
struct list_head {
	struct list_head *next, *prev;
};
struct pt_regs {
	unsigned long ip, sp, di, bx, r12, r13, r14, r15, bp;
};
struct mutex {
	struct task_struct *owner;
};
#include "mutex_outer_types.h"

static struct task_struct executor = { 1 }, waiter = { 2 }, other = { 3 };
static struct task_struct *current = &executor;
static struct mutex a, b;
static struct kd_mutex gate;
static struct kd_mutex_node request, successor;
static struct kd_exec_frame active;
static unsigned long kd_exec_invariant_failures;
static unsigned long kd_mutex_origin_acquires, kd_mutex_origin_releases;
static unsigned long kd_mutex_frame_failure_count, kd_mutex_jit_not_ready_count;
static unsigned long kd_mutex_context_busy_count, kd_mutex_jit_failure_count;
static unsigned long kd_mutex_combiner_count, kd_mutex_handoff_count;
static unsigned long kd_mutex_jit_success_count;
static unsigned int checks, failures, mode, wakes, scripts, native_waits, pops;
static unsigned int release_traces;
static unsigned int routine_traces;
static int preempt = 1;
static bool other_holds;
static int kd_mutex_batch_size = 16;
static unsigned int queue_finishes;
static unsigned int handoff_starts, handoff_ends;

/* CPU appears only in diagnostics; this fixture does not model scheduling. */
static unsigned int raw_smp_processor_id(void)
{
	return 0;
}

#define CHECK(c)                                                            \
	do {                                                                \
		checks++;                                                   \
		if (!(c)) {                                                 \
			failures++;                                         \
			fprintf(stderr, "FAIL mode=%u line=%d: %s\n", mode, \
				__LINE__, #c);                              \
		}                                                           \
	} while (0)
#define BUG_ON(c)                    \
	do {                         \
		if (c) {             \
			CHECK(!(c)); \
			exit(2);     \
		}                    \
	} while (0)
#define BUG() BUG_ON(true)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define unlikely(x) (x)
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, v)                                   \
	do {                                                      \
		if ((void *)(p) == &successor.locked && (v) == 0) \
			wakes++;                                  \
		*(p) = (v);                                       \
	} while (0)
#define atomic64_inc(p) (++*(p))
#define WARN_ON_ONCE(c) ((void)(c))
#define pr_info(fmt, ...)                                              \
	do {                                                           \
		if (!strncmp(fmt, "kd_mutex outer release:",           \
			     sizeof("kd_mutex outer release:") - 1)) { \
			release_traces++;                              \
			CHECK(a.owner == current &&                    \
			      gate.physical_owner == current);         \
			CHECK(gate.locked == _Q_LOCKED_COMBINER_VAL);  \
			CHECK(successor.locked &&                      \
			      successor.task_struct_ptr == &other);    \
		}                                                      \
		if (0)                                                 \
			printf(fmt, ##__VA_ARGS__);                    \
	} while (0)
#define KD_PR_DEBUG(...) pr_info(__VA_ARGS__)
#define KD_PR_ERR(...) pr_info(__VA_ARGS__)
#define smp_processor_id() raw_smp_processor_id()
/* Substitute only the printk sink, not the production severity/format macro.
 * The disabled-trace mutant intentionally leaves this sink unused. */
static int __attribute__((unused)) routine_printk(const char *format, ...)
{
	char text[256];
	va_list args;
	int length;

	va_start(args, format);
	length = vsnprintf(text, sizeof(text), format, args);
	va_end(args);
	CHECK(length > 0 && (size_t)length < sizeof(text));
	CHECK(!strncmp(text, KERN_INFO, strlen(KERN_INFO)));
	CHECK(strstr(text, "[0] [1] kd_mutex (execute_cs)") != NULL);
	CHECK(strstr(text, "JIT exec waiter cpu 0 ip 800 sp ") != NULL);
	routine_traces++;
	return length;
}
#define printk(...) routine_printk(__VA_ARGS__)
#define _Q_LOCKED_VAL 1
#define _Q_LOCKED_COMBINER_VAL 3
#define _RET_IP_ 0x900
#define KD_EXE_LOCK_MUTEX 2
#define container_of(p, type, member) \
	((type *)((char *)(p) - offsetof(type, member)))

/* Observe the queue metadata at the real producer boundary. Actual timing
 * accumulation/off-mode behavior is covered by the executor consumer unit. */
static u64 kd_exe_queue_timing_start(void)
{
	return 100;
}
static void kd_exe_queue_timing_end(bool mutex, uint64_t *queued_at, u64 end)
{
	CHECK(mutex && queued_at == &request.queued_at_ns && end == 100);
	CHECK(*queued_at == 50 && active.executed && scripts == 1);
	CHECK(request.locked && !request.native_resume && !pops && !native_waits);
	*queued_at = 0;
	queue_finishes++;
}

/* Observe the real producer's envelope without sampling a test wall clock.
 * After owner wait returns, the timing consumer must not depend on the node. */
static u64 kd_exe_native_timing_start(void)
{
	CHECK(request.locked && !request.native_resume && !native_waits && !pops);
	handoff_starts++;
	return 150;
}
static void kd_exe_native_handoff_timing_end(bool mutex, u64 start)
{
	CHECK(mutex && start == 150 && native_waits == 1 && !pops);
	handoff_ends++;
}

#define cmpxchg(p, old, value)                \
	({                                    \
		__typeof__(*(p)) seen = *(p); \
		if (seen == (old))            \
			*(p) = (value);       \
		seen;                         \
	})

static void preempt_enable(void)
{
	preempt--;
}
static void preempt_disable(void)
{
	preempt++;
}
static void cpu_relax(void)
{
	CHECK(other_holds && current == &executor);
	current = &other;
	CHECK(_kd_mutex_unlock_checked(&gate) == 0);
	current = &executor;
	other_holds = false;
}
static void kd_origin_mutex_lock(struct mutex *lock)
{
	CHECK(!lock->owner);
	lock->owner = current;
}
static void kd_origin_mutex_unlock(struct mutex *lock, unsigned long ip)
{
	(void)ip;
	CHECK(lock->owner == current);
	lock->owner = NULL;
}
static bool kd_origin_mutex_owned(struct mutex *lock, struct task_struct *task)
{
	return lock->owner == task;
}
static void clear_locked_set_completed(struct kd_mutex_node *node)
{
	node->completed = 1;
	smp_store_release(&node->locked, 0);
}
static void set_locked(struct kd_mutex *lock)
{
	smp_store_release(&lock->locked, _Q_LOCKED_VAL);
}
bool kd_mutex_jit_is_enabled(void)
{
	return true;
}
/* Opaque lookup token: the production backend must pass this exact slot. */
static struct kd_exe_info ready_entry;
static struct kd_exe_info *kd_exe_find_ready(int pid, unsigned long ip)
{
	(void)pid;
	(void)ip;
	return mode != 4 ? &ready_entry : NULL;
}
static void kd_exe_add_abi(int pid, unsigned long ip, int kind, unsigned int abi)
{
	(void)pid;
	(void)ip;
	CHECK(kind == KD_EXE_LOCK_MUTEX);
	CHECK(abi == KD_ENTRY_ABI_LEGACY);
}
bool kd_exec_context_busy(void)
{
	return false;
}

struct kd_exec_frame *kd_exec_frame_push(const struct pt_regs *regs,
					 unsigned long ip, unsigned long lock,
					 unsigned int depth, unsigned long gs,
					 struct task_struct *task)
{
	memset(&active, 0, sizeof(active));
	active.regs = *regs;
	active.entry_ip = ip;
	active.outer_lock_addr = lock;
	active.gsbase = gs;
	active.logical_task = task;
	active.state = KD_EXEC_FRAME_RUNNING;
	active.held_lock_depth = active.outer_lock_depth = depth;
	active.outer_lock_index = KD_EXEC_MAX_LOCK_DEPTH;
	return &active;
}
/* This fixture drives legacy packets; preserve the alternate API's signature. */
struct kd_exec_frame *kd_exec_frame_push_borrowed(struct pt_regs *regs,
 unsigned long ip, unsigned long lock, unsigned int depth, unsigned long gs,
 struct task_struct *task)
{
 return kd_exec_frame_push(regs, ip, lock, depth, gs, task);
}
int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)
{
	CHECK(frame == &active && frame->completion_seen);
	if (regs)
		*regs = frame->regs;
	pops++;
	return 0;
}
static int kd_mutex_jit_abort_cleanup(struct kd_exec_frame *frame)
{
	(void)frame;
	return 0;
}
static void successor_progress(void)
{
	/* A's independent C owner must be able to enter before B is released. */
	CHECK(!a.owner && gate.locked == 0 && successor.locked == 0);
	CHECK(b.owner == &executor);
	if (a.owner || gate.locked || successor.locked)
		return;
	current = &other;
	gate.locked = 1;
	kd_origin_mutex_lock(&a);
	gate.physical_owner = current;
	kd_mutex_origin_acquires++;
	current = &executor;
	other_holds = true;
	/* The successor can reuse its node while the old frame is still live. */
	successor.locked = 1;
}
static void release_b(void)
{
	CHECK(kd_exec_frame_lock_mark_released(&active, (unsigned long)&b) ==
	      0);
	kd_origin_mutex_unlock(&b, 0);
}
static void early_unlock_a(void)
{
	CHECK(kd_exec_frame_record_event(&active, KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == 0);
	CHECK(kd_exec_frame_record_event(&active, KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == -EINVAL);
	successor_progress();
}
static int kd_exe_on_call_hl_entry(struct kd_exe_info *exe,
				   struct pt_regs *regs, unsigned long ip,
				   unsigned long lock)
{
	CHECK(exe == &ready_entry);
	CHECK(regs == &active.regs && ip == 0x800 && lock == (unsigned long)&a);
	scripts++;
	active.executed = true;
	active.jit_lock_depth = active.held_lock_depth = 2;
	active.jit_lock_addr[1] = (unsigned long)&b;
	active.jit_lock_kind[1] = KD_EXEC_LOCK_NATIVE;
	b.owner = &executor;
	if (mode == 1 || mode == 3)
		early_unlock_a();
	if (mode == 2 || mode == 3)
		return KD_EXE_RUN_NATIVE;
	release_b();
	regs->di = mode == 1 ? (unsigned long)&b : (unsigned long)&a;
	return KD_EXE_RUN_TO_UNLOCK;
}
int kd_exec_native_begin(struct kd_exec_frame *frame, bool mutex)
{
	CHECK(frame == &active && mutex && b.owner == &executor);
	CHECK(handoff_starts == 1 && !handoff_ends);
	return 0;
}
int kd_exec_native_wait(struct kd_exec_frame *frame)
{
	CHECK(frame == &active && request.native_resume && !request.locked);
	native_waits++;
	if (mode == 2)
		early_unlock_a();
	release_b();
	/* The waiter may already have returned its queue slot to its CPU. */
	request.next = NULL;
	return 0;
}

#include "mutex_outer_production.h"

int main(void)
{
	for (mode = 0; mode < 5; mode++) {
		unsigned long stack[8] = { [7] = 0x800 };
		unsigned int expected = mode == 4 ? 0 : 1;
		bool early = mode >= 1 && mode <= 3;

		memset(&gate, 0, sizeof(gate));
		memset(&request, 0, sizeof(request));
		memset(&successor, 0, sizeof(successor));
		a.owner = NULL;
		b.owner = NULL;
		gate.origin_mutex_addr = (unsigned long)&a;
		request.tail = 1U << KD_MUTEX_TAIL_CPU_OFFSET;
		request.next = &successor;
		successor.task_struct_ptr = &other;
		request.locked = successor.locked = 1;
		request.regs.sp = (unsigned long)stack;
		request.queued_at_ns = 50;
		queue_finishes = 0;
		handoff_starts = handoff_ends = 0;
		request.gsbase = 1;
		request.task_struct_ptr = &waiter;
		request.saved_ret_addr = 0x800;
		kd_mutex_origin_acquires = 0;
		kd_mutex_origin_releases = wakes = scripts = pops =
			native_waits = 0;
		release_traces = 0;
		other_holds = false;
		preempt = 1;
		kd_mutex_wait_and_lock(&gate);
		gate.locked = 3;
		run_combiner(&gate, &request);
		CHECK(scripts == expected && pops == expected);
		CHECK(queue_finishes == expected);
		CHECK(request.queued_at_ns == (expected ? 0 : 50));
		CHECK(native_waits == (mode == 2 || mode == 3));
		CHECK(handoff_starts == native_waits && handoff_ends == native_waits);
		CHECK(gate.physical_owner == &executor && a.owner == &executor);
		CHECK(!b.owner && preempt == 1 && !other_holds);
		CHECK(kd_mutex_origin_acquires == (early ? 3 : 1));
		CHECK(kd_mutex_origin_releases == (early ? 2 : 0));
		CHECK(wakes == (mode == 4 ? 0 : 1));
		CHECK(successor.locked == (early || mode == 4));
		CHECK(request.completed == (mode == 0 || mode == 1));
		CHECK(release_traces == early);
		CHECK(_kd_mutex_unlock_checked(&gate) == 0);
		CHECK(!gate.locked && !a.owner && !gate.physical_owner);
		CHECK(kd_mutex_origin_acquires == kd_mutex_origin_releases);
	}
	CHECK(!kd_exec_invariant_failures && !kd_mutex_frame_failure_count);
	CHECK(routine_traces == 5);
	printf("mutex outer production progress: %u checks, %u failures, 5 scenarios\n",
	       checks, failures);
	printf("mutex routine INFO traces retained: %u\n", routine_traces);
	return failures != 0;
}
