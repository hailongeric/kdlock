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
#define ____cacheline_aligned_in_smp __attribute__((aligned(64)))
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
static struct pt_regs *kd_exec_frame_regs(struct kd_exec_frame *f)
{ return f->regs_ref ? f->regs_ref : &f->regs; }
static void kd_exec_frame_set_state(struct kd_exec_frame *f, int state)
{ f->state = state; }
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
	CHECK(kd_spin_diag_waiter_enter(&lock) == slot);
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
	kd_spin_diag_waiter_exit(slot);
	CHECK(!atomic_read(&slot->waiter_count));
	slot->jit_disabled.counter = 1;
	cpu = 1;
	CHECK(kd_spin_jit_is_disabled(slot));
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

/* Retained identities must keep observing mutable latches/counts, including
 * table exhaustion; neither a missing slot nor a new lock aliases an old one. */
static void test_retained_slot(void)
{
	struct kd_spin_diag_slot *slot = kd_spin_diag_find(0x400000);
	CHECK(slot);
	CHECK(offsetof(struct kd_spin_diag_slot, waiter_count) == 64);
	CHECK(sizeof(*slot) == 128);
	for (unsigned long a = 0x800000; a < 0x800000 + 64 * 64; a += 64)
		kd_spin_diag_find(a);
	CHECK(!kd_spin_diag_waiter_enter((void *)0xdead000));
	kd_spin_diag_waiter_exit(NULL);
	CHECK(kd_spin_diag_find(0x400000) == slot);
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
	struct pt_regs root = { .sp = (unsigned long)(stack + 128) }, saved = root;
	struct kd_spin_node node = { .execution = &request, .locked = 1 };
	request.frame.regs_ref = &root;
	request.frame.logical_task = &task;
	request.kind = KD_SPIN_CONT_VIRTUAL;
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
	request.kind = KD_SPIN_CONT_ROOT;
	request.frame.regs_ref->sp = saved.sp;
	kd_spin_prefetch_request(&node);
	CHECK(hints[0] == request.frame.regs_ref && hint_count == with_stack);
}

/* Prepared hints must match the old bounded targets for both inline and
 * borrowed packets, and overwrite stale node hints before each publication. */
static void test_prepared_prefetch(void)
{
	char stack[THREAD_SIZE];
	struct task_struct task = { .stack = stack };
	struct kd_spin_continuation request = { 0 };
	struct pt_regs borrowed = { 0 };
	struct kd_spin_node node = { .execution = &request, .locked = 1 };
	const void *lookup[16];
	CHECK(sizeof(node) == 2 * L1_CACHE_BYTES);
	request.frame.logical_task = &task;
	for (unsigned int alias = 0; alias < 2; alias++) {
		struct pt_regs *regs = alias ? &borrowed : &request.frame.regs;
		request.frame.regs_ref = regs;
		for (unsigned int full = 0; full < 2; full++) {
			request.frame.packet_state = full ? KD_PACKET_FULL : KD_PACKET_MINIMAL;
			for (unsigned int complex = 0; complex < 2; complex++) {
				request.frame.complex_ready = complex;
				unsigned long offsets[] = { 0, 7, 8, 64, 128, THREAD_SIZE - 1, THREAD_SIZE };
				for (unsigned int j = 0; j < sizeof(offsets)/sizeof(offsets[0]); j++) {
					regs->sp = (unsigned long)stack + offsets[j];
					kd_spin_prefetch_mode = 1; hint_count = 0;
					kd_spin_prefetch_request(&node);
					unsigned int expected = hint_count;
					memcpy(lookup, hints, sizeof(lookup));
					kd_spin_prefetch_mode = 2;
					kd_spin_prepare_prefetch(&node, regs);
					struct kd_spin_continuation before = request;
					struct pt_regs saved = *regs;
					hint_count = 0;
					kd_spin_prefetch_request(&node);
					CHECK(hint_count == expected);
					/* Frame warming moves first; the address multiset stays equal. */
					for (unsigned int h = 0; h < expected; h++) {
						unsigned int a = 0, b = 0;
						for (unsigned int k = 0; k < expected; k++) {
							a += hints[k] == lookup[h]; b += lookup[k] == lookup[h];
						}
						CHECK(a == b);
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
	CHECK(!node.prefetch_sp);
	kd_spin_prepare_prefetch(&node, NULL);
	CHECK(!node.prefetch_regs && !node.prefetch_sp);

	/* Guard pages prove the consumer reads neither frame nor logical packet.
	 * prefetchw records addresses without touching memory in this fixture. */
	size_t page = sysconf(_SC_PAGESIZE);
	size_t bytes = (sizeof(request) + page - 1) / page * page;
	void *area = mmap(NULL, bytes + page, PROT_READ | PROT_WRITE,
			  MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(area != MAP_FAILED);
	struct kd_spin_continuation *protected = area;
	struct pt_regs *packet = (void *)((char *)area + bytes);
	protected->frame.logical_task = &task;
	protected->frame.packet_state = KD_PACKET_FULL;
	protected->frame.complex_ready = true;
	packet->sp = (unsigned long)stack + 128;
	node.execution = protected;
	kd_spin_prepare_prefetch(&node, packet);
	CHECK(mprotect(area, bytes + page, PROT_NONE) == 0);
	hint_count = 0;
	kd_spin_prefetch_request(&node);
	CHECK(hint_count == 10 && hints[hint_count - 2] == stack + 128);
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
	test_cache();
	test_stats();
	test_retained_slot();
	test_root_retirement();
	test_prefetch();
	test_prepared_prefetch();
	puts("spin batch PASS: cache invalidation, per-CPU sum/max, physical/virtual prefetch");
	return 0;
}
