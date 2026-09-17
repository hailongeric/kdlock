/* SPDX-License-Identifier: GPL-2.0 */
/* Deterministic substitutes around real batch/readiness/statistics helpers.
 * Keep virtual packet aliases distinct to detect prefetching unused storage. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
typedef uint64_t u64;
typedef uint8_t u8;
typedef uint16_t u16;
typedef struct { int counter; } atomic_t;
typedef struct { long counter; } atomic_long_t;
struct list_head { struct list_head *next, *prev; };
struct qspinlock { int unused; };
struct task_struct { void *stack; };
#include "spin_batch_types.h"

#define READ_ONCE(x) (x)
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
#define L1_CACHE_BYTES 64
#define THREAD_SIZE 16384
#define task_stack_page(task) ((task)->stack)
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
static void prefetchw(const void *p)
{
	CHECK(hint_count < 16);
	hints[hint_count++] = p;
}
#include "spin_batch_production.h"

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
	CHECK(lookups == 1 && batch.exe->code_block == &entries[1]);
	CHECK(kd_spin_batch_find_ready(&batch, 0x900) == &entries[1]);
	CHECK(lookups == 2);
	CHECK(kd_spin_batch_find_ready(&next_batch, 0x900) == &entries[1]);
	CHECK(lookups == 3);
	/* Foreign backends are never hits; unchanged dispatcher rejects them. */
	entries[1].lock_kind = KD_EXE_LOCK_MUTEX;
	CHECK(kd_spin_batch_find_ready(&batch, 0x900) == &entries[1]);
	CHECK(lookups == 4);
	CHECK(!kd_spin_batch_find_ready(&batch, 0xa00));
}

static void test_stats(void)
{
	struct qspinlock lock;
	unsigned long addr = (unsigned long)&lock;
	struct kd_spin_diag_slot *slot = kd_spin_diag_find(addr);
	unsigned int index = slot - kd_spin_diag_slots;
	struct kd_spin_diag_counts sum;
	kd_spin_diag_waiter_enter(&lock);
	for (cpu = 0; cpu < 3; cpu++) {
		for (unsigned int e = 0; e < KD_SPIN_DIAG_EVENT_COUNT; e++)
			for (unsigned int n = 0; n <= cpu; n++)
				kd_spin_diag_record_addr(addr, e, cpu + 1);
		CHECK(cpu_stats[cpu].slot[index].event[0] == cpu + 1);
		CHECK(atomic_read(&slot->waiter_count) == 1);
	}
	cpu = 0;
	interrupt_max = true;
	kd_spin_diag_record_addr(addr, KD_SPIN_DIAG_SLOWPATH, 4);
	kd_spin_diag_waiter_exit(&lock);
	CHECK(!atomic_read(&slot->waiter_count));
	slot->jit_disabled.counter = 1;
	cpu = 1;
	CHECK(kd_spin_jit_is_disabled(&lock));
	kd_spin_diag_sum(index, &sum);
	CHECK(sum.max_depth == 8);
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

static void test_prefetch(void)
{
	char stack[THREAD_SIZE];
	struct task_struct task = { .stack = stack };
	struct kd_spin_exec_request request = { 0 }, before;
	struct pt_regs root = { .sp = (unsigned long)(stack + 128) }, saved = root;
	struct kd_spin_node node = { .execution = &request, .locked = 1 };
	request.frame.regs_ref = &root;
	request.frame.logical_task = &task;
	request.jit_waiter = true;
	before = request;
	kd_spin_prefetch_request(&node);
	for (unsigned int i = 0; i < 3; i++)
		CHECK(hints[i] == (char *)&root + i * L1_CACHE_BYTES);
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
	request.jit_waiter = false;
	request.frame.regs_ref->sp = saved.sp;
	kd_spin_prefetch_request(&node);
	CHECK(hints[0] == request.frame.regs_ref && hint_count == with_stack);
}

int main(void)
{
	test_cache();
	test_stats();
	test_prefetch();
	puts("spin batch PASS: cache invalidation, per-CPU sum/max, physical/virtual prefetch");
	return 0;
}
