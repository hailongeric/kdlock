/* SPDX-License-Identifier: GPL-2.0 */
/* Deterministic substitutes around real batch/readiness/statistics helpers.
 * Keep virtual packet aliases distinct to detect prefetching unused storage. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <sys/mman.h>
#include <unistd.h>
#include <errno.h>
#define L1_CACHE_BYTES 64
#define __aligned(n) __attribute__((aligned(n)))
#define ____cacheline_aligned_in_smp __attribute__((aligned(64)))
typedef uint64_t u64;
typedef int64_t s64;
typedef uint8_t u8;
typedef uint16_t u16;
typedef struct { int counter; } atomic_t;
typedef struct { long counter; } atomic_long_t;
struct list_head { struct list_head *next, *prev; };
struct qspinlock { int unused; };
typedef struct qspinlock raw_spinlock_t;
struct task_struct { void *stack; };
#include "spin_batch_types.h"

/* Inject a completed request between two live-observation reads. */
static void (*read_hook)(const void *);
#define READ_ONCE(x) ({ __auto_type p = &(x); __auto_type value = *p; \
	if (read_hook) { read_hook(p); } value; })
#define smp_load_acquire(p) (*(p))
#define atomic_read(p) ((p)->counter)
#define atomic_read_acquire(p) atomic_read(p)
#define atomic_long_read(p) atomic_read(p)
#define atomic_inc(p) (++(p)->counter)
#define atomic_dec_return(p) (--(p)->counter)
#define atomic_set(p, v) ((p)->counter = (v))
#define unlikely(x) (x)
#define WARN_ON_ONCE(x) ((void)(x))
#define IRQ_NUMA_NODE 255
#define THREAD_SIZE 16384
#define task_stack_page(task) ((task)->stack)
#define min_t(type, a, b) ({ type left = (a), right = (b); \
	left < right ? left : right; })
#define DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
#define CHECK(x) assert(x)

static unsigned int cpu;
static struct kd_spin_diag_cpu cpu_stats[3];
static struct kd_spin_diag_slot kd_spin_diag_slots[KD_SPIN_DIAG_SLOTS];
#define kd_spin_diag_cpu (&cpu_stats[cpu])
#define this_cpu_inc(x) (++(x))
#define this_cpu_read(x) (x)
#define per_cpu_ptr(p, i) (&cpu_stats[i])
/* CPU 2 has recorded work but is now offline. Shutdown must still include it. */
#define for_each_possible_cpu(i) for ((i) = 0; (i) < 3; (i)++)
static long atomic_long_cmpxchg(atomic_long_t *p, long old, long value)
{
	long before = p->counter;
	if (before == old)
		p->counter = value;
	return before;
}
static bool interrupt_max;
static int local_cmpxchg(int *p, int old, int value)
{
	if (interrupt_max) {
		interrupt_max = false;
		*p = 8; /* IRQ records a deeper frame before this interrupted CAS. */
	}
	int before = *p;
	if (before == old)
		*p = value;
	return before;
}
#define this_cpu_cmpxchg(x, old, value) local_cmpxchg(&(x), old, value)

static bool source_open = true;
static unsigned int lookups;
static struct kd_exe_info entries[2];
static bool kd_source_is_open(void) { return source_open; }
static struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip)
{
	CHECK(pid == 0);
	lookups++;
	for (unsigned int i = 0; i < 2; i++)
		if (entries[i].RIP == ip)
			return &entries[i];
	return NULL;
}
static const void *hints[16];
static unsigned int hint_count;
static unsigned int kd_spin_prefetch_mode = 1;
static void prefetchw(const void *p)
{
	CHECK(hint_count < 16);
	hints[hint_count++] = p;
}
/* Only physical CPU/task accessors are substitutes for real root retirement. */
static struct task_struct physical_task, other_task;
#define current (&physical_task)
static struct kd_exec_context {
	struct kd_exec_frame *top;
	struct task_struct *owner;
	unsigned int depth;
} context;
static struct kd_exec_context *kd_exec_current_context(void) { return &context; }
static struct kd_regs *kd_exec_frame_regs(struct kd_exec_frame *f)
{ return f->regs_ref ? f->regs_ref : &f->regs; }
static void kd_exec_frame_set_state(struct kd_exec_frame *f, int state)
{ f->state = state; }
static const unsigned int kd_combiner_batch_size = 512;
#ifdef NUMA_AWARE
static struct { struct kd_spin_node *local_queue_head; } kd_spin_cpu;
#endif
static unsigned int refill_pauses, refill_after;
static struct kd_spin_node *refill_node, *refill_following;
static void cpu_relax(void)
{
	if (++refill_pauses == refill_after)
		refill_node->next = refill_following;
}
#include "spin_batch_production.h"

/* Publish at every retry boundary, or never. A bounded grace cannot retain
 * the lock indefinitely, cross the body cap, or delegate a native node. */
static void test_batch_refill(void)
{
	struct kd_spin_node node = { 0 }, following = { 0 };

	refill_node = &node;
	refill_following = &following;
	for (unsigned int at = 0; at <= 9; at++) {
		for (unsigned int native = 0; native < 2; native++) {
			node.next = NULL;
			following.socket_id = native ? IRQ_NUMA_NODE : 0;
			refill_after = at;
			refill_pauses = 0;
			CHECK(kd_spin_batch_can_continue(&node, 511) ==
			      (at >= 1 && at <= 8 && !native));
			CHECK(refill_pauses == (at >= 1 && at <= 8 ? at : 8));
		}
	}
	refill_pauses = 0;
	node.next = &following;
	following.socket_id = 0;
	CHECK(kd_spin_batch_can_continue(&node, 1));
	CHECK(!refill_pauses);
	CHECK(!kd_spin_batch_can_continue(NULL, 1));
	CHECK(!kd_spin_batch_can_continue(&node, 512));
	node.socket_id = IRQ_NUMA_NODE;
	node.next = (void *)1; /* Native boundary must not follow this pointer. */
	CHECK(!kd_spin_batch_can_continue(&node, 1));
	CHECK(!refill_pauses);
#ifdef NUMA_AWARE
	/* A deferred chain does not bypass the bounded refill. Exercise every
	 * publication boundary, including timeout and a native successor. */
	node.socket_id = 0;
	kd_spin_cpu.local_queue_head = &following;
	for (unsigned int at = 0; at <= 9; at++) {
		for (unsigned int native = 0; native < 2; native++) {
			node.next = NULL;
			following.socket_id = native ? IRQ_NUMA_NODE : 0;
			refill_after = at;
			refill_pauses = 0;
			CHECK(kd_spin_batch_can_continue(&node, 127) ==
			      (at >= 1 && at <= 8 && !native));
			CHECK(refill_pauses == (at >= 1 && at <= 8 ? at : 8));
		}
	}
	refill_pauses = 0;
	following.socket_id = 0;
	node.next = &following;
	CHECK(kd_spin_batch_can_continue(&node, 1));
	CHECK(!refill_pauses);
	CHECK(kd_spin_batch_can_continue(&node, 511));
	node.next = NULL;
	CHECK(!kd_spin_batch_can_continue(&node, 128));
	CHECK(!refill_pauses);
	node.next = &following;
	kd_spin_cpu.local_queue_head = NULL;
	CHECK(kd_spin_batch_can_continue(&node, 511));
#endif
}

static void test_cache(void)
{
	struct kd_spin_batch batch = { 0 }, next_batch = { 0 };
	for (unsigned int i = 0; i < 2; i++)
		entries[i] = (struct kd_exe_info){ .RIP = 0x800 + i * 0x100,
			.lock_kind = KD_EXE_LOCK_SPIN, .code_block = &entries[i],
			.status_code = KD_EXE_NORMAL };
	for (unsigned int i = 0; i < 100; i++)
		CHECK(kd_spin_batch_find_ready(&batch, 0x800) == &entries[0]);
	CHECK(lookups == 1);
	/* A pointer hit must not cache OPEN, NORMAL, key or code publication. */
	source_open = false;
	CHECK(!kd_spin_batch_find_ready(&batch, 0x800));
	source_open = true;
	int statuses[] = {KD_EXE_UNINIT, KD_EXE_CALL_MISS, KD_EXE_NATIVE_ONLY};
	for (unsigned int i = 0; i < sizeof(statuses) / sizeof(statuses[0]); i++) {
		entries[0].status_code = statuses[i];
		CHECK(!kd_spin_batch_find_ready(&batch, 0x800));
	}
	entries[0].status_code = KD_EXE_NORMAL;
	entries[0].code_block = NULL;
	CHECK(!kd_spin_batch_find_ready(&batch, 0x800));
	entries[0].code_block = &entries[1];
	entries[0].pid = 1;
	CHECK(!kd_spin_batch_find_ready(&batch, 0x800));
	entries[0].pid = 0;
	entries[0].RIP++;
	CHECK(!kd_spin_batch_find_ready(&batch, 0x800));
	entries[0].RIP--;
	CHECK(kd_spin_batch_find_ready(&batch, 0x800) == &entries[0]);
	CHECK(lookups == 2 && batch.exe->code_block == &entries[1]);
	CHECK(kd_spin_batch_find_ready(&batch, 0x900) == &entries[1]);
	CHECK(lookups == 3);
	CHECK(kd_spin_batch_find_ready(&next_batch, 0x900) == &entries[1]);
	CHECK(lookups == 4);
	/* Foreign backends are never hits; unchanged dispatcher rejects them. */
	entries[1].lock_kind = KD_EXE_LOCK_OWNED_MUTEX;
	CHECK(kd_spin_batch_find_ready(&batch, 0x900) == &entries[1]);
	CHECK(lookups == 5);
	CHECK(!kd_spin_batch_find_ready(&batch, 0xa00));
}

static void test_stats(void)
{
	struct qspinlock lock;
	unsigned long addr = (unsigned long)&lock;
	struct kd_spin_diag_slot *slot = kd_spin_diag_find(addr);
	unsigned int index = slot - kd_spin_diag_slots;
	struct kd_spin_diag_counts sum;
	kd_spin_diag_waiter_enter(slot);
	CHECK(kd_spin_diag_waiter_balance(slot - kd_spin_diag_slots) == 1);
	CHECK(offsetof(struct kd_spin_diag_counts, max_depth) == 72 &&
	      offsetof(struct kd_spin_diag_counts, waiter_enter) == 80 &&
	      offsetof(struct kd_spin_diag_counts, waiter_exit) == 88 &&
	      sizeof(struct kd_spin_diag_counts) == 96);
	for (cpu = 0; cpu < 3; cpu++) {
		for (unsigned int e = 0; e < KD_SPIN_DIAG_EVENT_COUNT; e++)
			for (unsigned int n = 0; n <= cpu; n++)
				kd_spin_diag_record_addr(addr, e, cpu + 1);
		CHECK(cpu_stats[cpu].slot[index].event[0] == cpu + 1);
		CHECK(kd_spin_diag_waiter_balance(slot - kd_spin_diag_slots) == 1);
	}
	cpu = 0;
	interrupt_max = true;
	kd_spin_diag_record_addr(addr, KD_SPIN_DIAG_SLOWPATH, 4);
	cpu = 2; /* Exit on another CPU; a local negative difference is valid. */
	kd_spin_diag_waiter_exit(slot);
	CHECK(!kd_spin_diag_waiter_balance(slot - kd_spin_diag_slots));
	slot->jit_disabled.counter = 1;
	cpu = 1;
	CHECK(kd_spin_jit_is_disabled(slot));
	kd_spin_diag_sum(index, &sum);
	CHECK(sum.max_depth == 8 && sum.waiter_enter == 1 && sum.waiter_exit == 1);
	CHECK(!cpu_stats[2].slot[index].waiter_enter &&
	      cpu_stats[2].slot[index].waiter_exit == 1);
	for (unsigned int e = 0; e < KD_SPIN_DIAG_EVENT_COUNT; e++)
		CHECK(sum.event[e] == (e == KD_SPIN_DIAG_SLOWPATH ? 7 : 6));
	CHECK(cpu_stats[2].slot[index].max_depth == 3);
	/* Bad events/null keys must not create accounting records. */
	kd_spin_diag_record_addr(addr, KD_SPIN_DIAG_EVENT_COUNT, 99);
	kd_spin_diag_record_addr(0, KD_SPIN_DIAG_SLOWPATH, 99);
	kd_spin_diag_sum(index, &sum);
	CHECK(sum.max_depth == 8 && sum.event[0] == 7);
	kd_spin_diag_invariant_failure();
	CHECK(cpu_stats[1].invariant_failures == 1 && !cpu_stats[0].invariant_failures);
}

static void test_simple_success(void)
{
	static struct qspinlock lock;
	struct kd_spin_diag_slot *slot = kd_spin_diag_find((unsigned long)&lock);
	unsigned int index = slot - kd_spin_diag_slots;
	unsigned int saved_cpu = cpu;
	struct kd_spin_diag_counts expected, sum;
	__typeof__(cpu_stats[0]) saved;

	CHECK(slot);
	for (cpu = 0; cpu < 3; cpu++) {
		/* Each pinned combiner establishes the maximum before simple bodies. */
		kd_spin_debug_combiner(slot, 1);
		memcpy(&expected, &cpu_stats[cpu].slot[index], sizeof(expected));
		CHECK(expected.max_depth == 1);
		for (unsigned int n = 0; n < 3; n++)
			kd_spin_debug_jit_success_simple(slot);
		expected.event[KD_SPIN_DIAG_JIT_SUCCESS] += 3;
		CHECK(!memcmp(&expected, &cpu_stats[cpu].slot[index], sizeof(expected)));

		/* Complex success still raises depth; later simple bodies preserve it. */
		kd_spin_debug_jit_success(slot, cpu + 4);
		CHECK(cpu_stats[cpu].slot[index].max_depth == (int)cpu + 4);
		memcpy(&expected, &cpu_stats[cpu].slot[index], sizeof(expected));
		kd_spin_debug_jit_success_simple(slot);
		expected.event[KD_SPIN_DIAG_JIT_SUCCESS]++;
		CHECK(!memcmp(&expected, &cpu_stats[cpu].slot[index], sizeof(expected)));

		memcpy(&saved, &cpu_stats[cpu], sizeof(saved));
		kd_spin_debug_jit_success_simple(NULL);
		CHECK(!memcmp(&saved, &cpu_stats[cpu], sizeof(saved)));
	}
	kd_spin_diag_sum(index, &sum);
	CHECK(sum.event[KD_SPIN_DIAG_COMBINER] == 3 &&
	      sum.event[KD_SPIN_DIAG_JIT_SUCCESS] == 15 && sum.max_depth == 6);
	cpu = saved_cpu;
}

static struct kd_spin_diag_slot *scan_slot;
static void complete_during_scan(const void *address)
{
	unsigned int index = scan_slot - kd_spin_diag_slots;

	if (address != &cpu_stats[0].slot[index].waiter_enter)
		return;
	read_hook = NULL;
	cpu = 0; kd_spin_diag_waiter_enter(scan_slot);
	cpu = 2; kd_spin_diag_waiter_exit(scan_slot);
}

static void test_waiter_observations(void)
{
	struct qspinlock lock;
	scan_slot = kd_spin_diag_find((unsigned long)&lock);
	CHECK(scan_slot && kd_spin_debug_waiter_count(NULL) == -EINVAL);
	CHECK(!kd_spin_debug_waiter_count(&lock));
	u64 failures = cpu_stats[2].invariant_failures;
	read_hook = complete_during_scan;
	CHECK(kd_spin_debug_waiter_count(&lock) == -1);
	CHECK(!read_hook && !kd_spin_debug_waiter_count(&lock));
	CHECK(cpu_stats[2].invariant_failures == failures);
	CHECK(!kd_spin_diag_waiter_mismatches());
	/* Only quiescent mismatches are failures; never silently clamp them. */
	kd_spin_diag_waiter_enter(scan_slot);
	CHECK(kd_spin_debug_waiter_count(&lock) == 1);
	CHECK(kd_spin_diag_waiter_mismatches() == 1);
	kd_spin_diag_waiter_exit(scan_slot);
	kd_spin_diag_waiter_exit(scan_slot);
	CHECK(kd_spin_debug_waiter_count(&lock) == -1);
	CHECK(kd_spin_diag_waiter_mismatches() == 1);
	kd_spin_diag_waiter_enter(scan_slot);
	CHECK(!kd_spin_debug_waiter_count(&lock) && !kd_spin_diag_waiter_mismatches());
}

/* Retained identities must keep observing mutable latches/counts, including
 * table exhaustion; neither a missing slot nor a new lock aliases an old one. */
static void test_retained_slot(void)
{
	struct kd_spin_diag_slot *slot = kd_spin_diag_find(0x400000);
	CHECK(slot);
	CHECK(_Alignof(struct kd_spin_diag_slot) == 2 * L1_CACHE_BYTES);
	CHECK(sizeof(struct kd_spin_diag_slot) == 2 * L1_CACHE_BYTES);
	CHECK((uintptr_t)slot % (2 * L1_CACHE_BYTES) == 0);
	for (unsigned long a = 0x800000; a < 0x800000 + 64 * 64; a += 64)
		kd_spin_diag_find(a);
	CHECK(!kd_spin_diag_find(0xdead000));
	CHECK(kd_spin_debug_waiter_count((void *)0xdead000) == -ENOSPC);
	kd_spin_diag_waiter_enter(NULL);
	kd_spin_diag_waiter_exit(NULL);
	CHECK(kd_spin_diag_find(0x400000) == slot);
	/* Reuse still accounts exactly when the identity table is full. */
	u64 overflow = cpu_stats[cpu].overflow;
	kd_spin_diag_waiter_enter(slot);
	CHECK(kd_spin_diag_waiter_balance(slot - kd_spin_diag_slots) == 1);
	kd_spin_diag_waiter_exit(slot);
	CHECK(!kd_spin_diag_waiter_balance(slot - kd_spin_diag_slots) && cpu_stats[cpu].overflow == overflow);
	CHECK(!kd_spin_jit_is_disabled(slot));
	slot->jit_disabled.counter = 1;
	CHECK(kd_spin_jit_is_disabled(slot));
	kd_spin_diag_record_slot(slot, KD_SPIN_DIAG_JIT_SUCCESS, 1);
	CHECK(cpu_stats[cpu].slot[slot-kd_spin_diag_slots].event[KD_SPIN_DIAG_JIT_SUCCESS] == 1);
}

static void test_root_retirement(void)
{
	struct kd_spin_continuation request = { 0 };
	struct kd_exec_frame *f = &request.frame;
	CHECK(sizeof(request) == 704 && _Alignof(struct kd_spin_continuation) == 64);
	CHECK(offsetof(struct kd_spin_continuation, frame.packet_state) < 128);
	for (int abi = 0; abi < 2; abi++) {
		*f = (struct kd_exec_frame){ .spin_simple = true, .executed = true,
			.batch_lease = true, .request_frame = true, .state = KD_EXEC_FRAME_RUNNING,
			.entry_abi = abi, .packet_state = abi ? KD_PACKET_COMPLETE : KD_PACKET_FULL,
			.outer_lock_addr = 0x9000, .regs.di = 0x9000 };
		context = (struct kd_exec_context){ .top = f, .owner = current, .depth = 1 };
		struct kd_exec_frame before = *f;
		context.owner = &other_task;
		CHECK(kd_exec_frame_retire_single_spin(f) == -EINVAL && !memcmp(f, &before, sizeof(*f)));
		context.owner = current;
		context.depth = 2;
		CHECK(kd_exec_frame_retire_single_spin(f) == -EINVAL);
		context.depth = 1;
		f->complex_ready = true;
		CHECK(kd_exec_frame_retire_single_spin(f) == -EINVAL);
		f->complex_ready = false;
		f->batch_lease = false;
		CHECK(kd_exec_frame_retire_single_spin(f) == -EINVAL);
		f->batch_lease = true;
		f->packet_state = KD_PACKET_MINIMAL;
		CHECK(kd_exec_frame_retire_single_spin(f) == -EINVAL);
		f->packet_state = before.packet_state;
		CHECK(!kd_exec_frame_retire_single_spin(f));
		CHECK(f->completion_seen && f->state == KD_EXEC_FRAME_UNUSED);
		CHECK(!context.top && !context.owner && !context.depth);
		CHECK(kd_exec_frame_retire_single_spin(f) == -EINVAL);
	}
}

static void test_prefetch(void)
{
	char stack[THREAD_SIZE];
	struct task_struct task = { .stack = stack };
	struct kd_spin_continuation request = { 0 }, before;
	struct kd_regs root = { .sp = (unsigned long)(stack + 128) }, saved = root;
	struct kd_spin_node node = { .execution = &request, .locked = 1 };
	request.frame.regs_ref = &root;
	request.frame.logical_task = &task;
	request.frame.spin_kind = KD_SPIN_CONT_VIRTUAL;
	before = request;
	kd_spin_prefetch_request(&node);
	for (unsigned int i = 0; i < 3; i++)
		CHECK(hints[i + 2] == (char *)&root + i * L1_CACHE_BYTES);
	CHECK(hints[hint_count - 2] == stack + 128);
	CHECK(hints[hint_count - 1] == stack + 120);
	CHECK(!memcmp(&request, &before, sizeof(request)));
	CHECK(!memcmp(&root, &saved, sizeof(root)));
	CHECK(node.locked && !node.completed);
	unsigned int with_stack = hint_count;
	/* Stack-edge and non-stack SP never issue outside-stack hints. */
	unsigned long invalid[] = {0, (unsigned long)stack,
		(unsigned long)(stack + THREAD_SIZE)};
	for (unsigned int i = 0; i < 3; i++) {
		hint_count = 0;
		root.sp = invalid[i];
		kd_spin_prefetch_request(&node);
		CHECK(hint_count == with_stack - 2);
	}
	hint_count = 0;
	node.socket_id = IRQ_NUMA_NODE;
	kd_spin_prefetch_request(&node);
	kd_spin_prefetch_request(NULL);
	CHECK(!hint_count);
	node.socket_id = 0;
	node.execution = NULL;
	kd_spin_prefetch_request(&node);
	CHECK(!hint_count);
	/* A physical packet uses its own regs, with identical bounded hints. */
	node.execution = &request;
	request.frame.regs_ref = &request.frame.regs;
	request.frame.spin_kind = KD_SPIN_CONT_ROOT;
	request.frame.regs_ref->sp = saved.sp;
	kd_spin_prefetch_request(&node);
	CHECK(hints[0] == &request.frame && hints[1] == &request.frame.regs_ref &&
	      hints[2] == request.frame.regs_ref && hint_count == with_stack);
}

static bool hint_has_line(const void *const *list, unsigned int count,
			  const void *target)
{
	for (unsigned int i = 0; i < count; i++)
		if ((uintptr_t)list[i] / L1_CACHE_BYTES ==
		    (uintptr_t)target / L1_CACHE_BYTES)
			return true;
	return false;
}

/* Prepared hints preserve warmed lines and overwrite stale node hints before
 * each publication. Production MINIMAL is inline; borrowed packets are FULL. */
static void test_prepared_prefetch(void)
{
	char stack[THREAD_SIZE] __aligned(L1_CACHE_BYTES);
	struct task_struct task = { .stack = stack };
	struct kd_spin_continuation request = { 0 };
	struct kd_regs borrowed = { 0 };
	struct kd_spin_node node = { .execution = &request, .locked = 1 };
	const void *lookup[16];
	CHECK(sizeof(node) == 2 * L1_CACHE_BYTES);
	request.frame.logical_task = &task;
	for (unsigned int alias = 0; alias < 2; alias++) {
		struct kd_regs *regs = alias ? &borrowed : &request.frame.regs;
		request.frame.regs_ref = regs;
		request.frame.spin_kind = alias ? KD_SPIN_CONT_VIRTUAL : KD_SPIN_CONT_ROOT;
		for (unsigned int full = 0; full < 2; full++) {
			if (alias && !full)
				continue;
			request.frame.packet_state = full ? KD_PACKET_FULL : KD_PACKET_MINIMAL;
			for (unsigned int complex = 0; complex < 2; complex++) {
				request.frame.complex_ready = complex;
				unsigned long offsets[] = { 0, 7, 8, 16, 32, 48, 64, 128,
					THREAD_SIZE - 193, THREAD_SIZE - 192,
					THREAD_SIZE - 129, THREAD_SIZE - 128,
					THREAD_SIZE - 65, THREAD_SIZE - 64,
					THREAD_SIZE - 1, THREAD_SIZE };
				for (unsigned int j = 0; j < sizeof(offsets)/sizeof(offsets[0]); j++) {
					regs->sp = (unsigned long)stack + offsets[j];
					kd_spin_prefetch_mode = 1; hint_count = 0;
					kd_spin_prefetch_request(&node);
					unsigned int expected = hint_count;
					memcpy(lookup, hints, sizeof(lookup));
					kd_spin_prefetch_mode = 2;
					kd_spin_prepare_prefetch(&node, regs);
					struct kd_spin_continuation before = request;
					struct kd_regs saved = *regs;
					hint_count = 0;
					kd_spin_prefetch_request(&node);
					unsigned int old_stack = node.prefetch_sp ? 2 : 0;
					unsigned int new_stack = node.prefetch_sp ?
						1 + node.prefetch_stack_lines : 0;
					unsigned int old_packet = expected - old_stack;
					unsigned int new_packet = hint_count - new_stack;
					if (full) {
						CHECK(new_packet == old_packet);
						/* FULL packet targets stay identical, including borrowed packets. */
						for (unsigned int h = 0; h < old_packet; h++) {
							unsigned int a = 0, b = 0;
							for (unsigned int k = 0; k < old_packet; k++) {
								a += hints[k] == lookup[h];
								b += lookup[k] == lookup[h];
							}
							CHECK(a == b);
						}
					} else {
						/* Identity, frame state and the entire continuation triple
						 * share line zero; virtual GPRs and provenance need one
						 * line each. Complex ledgers retain their own hints. */
						CHECK(new_packet == old_packet);
						CHECK(new_packet == 3 + complex * 3);
						CHECK((uintptr_t)&request.frame % L1_CACHE_BYTES == 0);
						const void *hot[] = { &request.frame.entry_ip,
							&request.frame.outer_lock_addr, &request.frame.state,
							&request.frame.packet_state, &regs->ip, &regs->sp, &regs->bp };
						for (unsigned int h = 0; h < sizeof(hot)/sizeof(hot[0]); h++)
							CHECK((uintptr_t)hot[h] / L1_CACHE_BYTES ==
								  (uintptr_t)&request.frame / L1_CACHE_BYTES);
						CHECK((uintptr_t)&regs->r15 / L1_CACHE_BYTES ==
							  (uintptr_t)&regs->r11 / L1_CACHE_BYTES);
						CHECK((uintptr_t)&request.frame.regs_ref / L1_CACHE_BYTES ==
							  (uintptr_t)&request.frame.parent / L1_CACHE_BYTES);
						for (unsigned int h = 0; h < old_packet; h++)
							CHECK(hints[h] == lookup[h]);
						CHECK(hint_has_line(hints, new_packet, &regs->r15));
						CHECK(hint_has_line(hints, new_packet, &request.frame.logical_task));
					}
					/* Hint every valid upward address, without touching a guard page.
					 * Caller statistics at SP+144..167 must be covered for each
					 * tested SP alignment when that range is inside the stack. */
					CHECK(node.prefetch_stack_lines <= 4);
					if (node.prefetch_sp) {
						CHECK(hints[new_packet] == (void *)(regs->sp - 8));
						unsigned int lines = 0;
						for (unsigned int line = 0; line < 4; line++) {
							unsigned long address = regs->sp + line * L1_CACHE_BYTES;
							if (address >= (unsigned long)stack + THREAD_SIZE)
								break;
							CHECK(hints[new_packet + 1 + lines] == (void *)address);
							lines++;
						}
						CHECK(node.prefetch_stack_lines == lines);
						if (offsets[j] + 167 < THREAD_SIZE) {
							CHECK(hint_has_line(hints, hint_count, (void *)(regs->sp + 144)));
							CHECK(hint_has_line(hints, hint_count, (void *)(regs->sp + 167)));
						}
					} else {
						CHECK(!node.prefetch_stack_lines);
					}
					CHECK(!memcmp(&before, &request, sizeof(request)));
					CHECK(!memcmp(&saved, regs, sizeof(saved)));
					CHECK(node.locked && !node.completed);
				}
			}
		}
	}
	request.frame.logical_task = NULL;
	kd_spin_prepare_prefetch(&node, &borrowed);
	CHECK(!node.prefetch_sp && !node.prefetch_stack_lines);
	kd_spin_prepare_prefetch(&node, NULL);
	CHECK(!node.prefetch_regs && !node.prefetch_sp && !node.prefetch_stack_lines);

	/* Guard pages prove the consumer reads neither frame nor logical packet.
	 * prefetchw records addresses without touching memory in this fixture. */
	size_t page = sysconf(_SC_PAGESIZE);
	size_t bytes = (sizeof(request) + page - 1) / page * page;
	void *area = mmap(NULL, bytes + page, PROT_READ | PROT_WRITE,
			  MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(area != MAP_FAILED);
	struct kd_spin_continuation *protected = area;
	struct kd_regs *external_packet = (void *)((char *)area + bytes);
	node.execution = protected;
	for (unsigned int full = 0; full < 2; full++) {
		/* Protect inline MINIMAL and a separately borrowed FULL packet. */
		struct kd_regs *packet = full ? external_packet : &protected->frame.regs;

		CHECK(mprotect(area, bytes + page, PROT_READ | PROT_WRITE) == 0);
		protected->frame.spin_kind = full ? KD_SPIN_CONT_VIRTUAL : KD_SPIN_CONT_ROOT;
		protected->frame.regs_ref = packet;
		protected->frame.logical_task = &task;
		protected->frame.packet_state = full ? KD_PACKET_FULL : KD_PACKET_MINIMAL;
		protected->frame.complex_ready = true;
		packet->sp = (unsigned long)stack + 128;
		kd_spin_prepare_prefetch(&node, packet);
		CHECK(mprotect(area, bytes + page, PROT_NONE) == 0);
		hint_count = 0;
		kd_spin_prefetch_request(&node);
		CHECK(hint_count == (full ? 13 : 11));
		CHECK(hints[hint_count - 5] == stack + 120);
		for (unsigned int line = 0; line < 4; line++)
			CHECK(hints[hint_count - 4 + line] == stack + 128 + line * L1_CACHE_BYTES);
		if (!full) {
			CHECK(hint_has_line(hints, hint_count, &packet->bp));
			CHECK(hint_has_line(hints, hint_count, &packet->ip));
			CHECK(hint_has_line(hints, hint_count, &packet->sp));
		}
	}
	/* Disabled mode must not follow even a deliberately unusable node. */
	kd_spin_prefetch_mode = 0; hint_count = 0;
	kd_spin_prefetch_request((void *)1);
	CHECK(!hint_count);
	kd_spin_prefetch_mode = 2;
	node.socket_id = IRQ_NUMA_NODE;
	kd_spin_prefetch_request(&node);
	kd_spin_prefetch_request(NULL);
	CHECK(!hint_count);
	CHECK(munmap(area, bytes + page) == 0);
}

int main(void)
{
	test_batch_refill();
	test_cache();
	test_stats();
	test_simple_success();
	test_waiter_observations();
	test_retained_slot();
	test_root_retirement();
	test_prefetch();
	test_prepared_prefetch();
	puts("spin batch PASS: cache invalidation, per-CPU sum/max, physical/virtual prefetch");
	return 0;
}
