/* SPDX-License-Identifier: GPL-2.0 */
/* Execute extracted production BPF/read-token helpers. Kernel scheduling and
 * MM primitives are substitutes; this is not a live IRQ/NMI or MM test. */
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

typedef uint64_t u64;
typedef uint32_t u32;
#define CHECK(x) do { if (!(x)) { \
	fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); \
} } while (0)
#define BUG_ON(x) CHECK(!(x))
#define WARN_ON_ONCE(x) (x)
#define CONFIG_PREEMPT_RT 0
#define IS_ENABLED(x) (x)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x, v) __atomic_store_n(&(x), (v), __ATOMIC_RELAXED)
#define xchg(p, v) __atomic_exchange_n((p), (v), __ATOMIC_SEQ_CST)
#define cmpxchg(p, old, value) ({ __typeof__(*(p)) expected = (old); \
	__atomic_compare_exchange_n((p), &expected, (value), false, \
		__ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); expected; })
#define smp_store_release(p, value) __atomic_store_n((p), (value), __ATOMIC_RELEASE)
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define EXPORT_SYMBOL_GPL(x)
#define DECLARE_PER_CPU(type, name) extern type name
#define this_cpu_ptr(p) (p)
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define _RET_IP_ 0
#define BPF_CALL_5(name, t1, a1, t2, a2, t3, a3, t4, a4, t5, a5) \
	static long name(t1 a1, t2 a2, t3 a3, t4 a4, t5 a5)
#define BPF_STACK_BUILD_ID_IP 1
#define BPF_STACK_BUILD_ID_VALID 2
#define BUILD_ID_SIZE_MAX 20
#define PAGE_SHIFT 12

struct mm_struct {
	int shares, refs;
	bool freed;
	struct { int dep_map; } mmap_lock;
};
struct task_struct { struct mm_struct *mm; };
struct vm_area_struct { unsigned long vm_start, vm_end, vm_pgoff; };
struct bpf_stack_build_id {
	int status;
	char build_id[BUILD_ID_SIZE_MAX];
	union { u64 ip, offset; };
};
struct irq_work { bool busy, pending; };
typedef u64 (*bpf_callback_t)(u64, u64, u64, u64, u64);

static struct mm_struct mm;
static struct task_struct task;
static struct task_struct *current = &task;
static struct vm_area_struct vma = { .vm_start = 0x1000, .vm_end = 0x3000 };
static bool irq_disabled, read_allowed, lookup_found;
static unsigned int queues, direct_unlocks, deferred_unlocks, drops;
static bool inspect_completion;
static void check_completion_reservation(void);

static bool irqs_disabled(void) { return irq_disabled; }
static bool irq_work_is_busy(struct irq_work *work) { return work->busy; }
static bool irq_work_queue(struct irq_work *work)
{
	if (work->pending)
		return false;
	work->busy = work->pending = true;
	queues++;
	return true;
}
static bool mmap_read_trylock(struct mm_struct *m)
{
	CHECK(m && !m->freed && m->refs > 0);
	if (!read_allowed)
		return false;
	m->shares++;
	return true;
}
static void mmap_read_unlock(struct mm_struct *m)
{
	CHECK(!irq_disabled && m->shares > 0);
	m->shares--;
	direct_unlocks++;
}
static void mmap_read_unlock_non_owner(struct mm_struct *m)
{
	CHECK(m->shares > 0 && !m->freed);
	if (inspect_completion)
		check_completion_reservation();
	m->shares--;
	deferred_unlocks++;
}
static void mmgrab(struct mm_struct *m)
{
	CHECK(m->shares > 0 && m->refs > 0 && !m->freed);
	m->refs++;
}
static void mmdrop_async(struct mm_struct *m)
{
	CHECK(!m->shares && m->refs > 0 && !m->freed);
	if (inspect_completion)
		check_completion_reservation();
	if (!--m->refs)
		m->freed = true;
	drops++;
}
static void rwsem_release(int *map, unsigned long ip) { (void)map; (void)ip; }
static struct vm_area_struct *find_vma(struct mm_struct *m, unsigned long start)
{
	CHECK(m->shares > 0);
	(void)start;
	return lookup_found ? &vma : NULL;
}
static bool range_in_vma(struct vm_area_struct *v, u64 low, u64 high)
{
	return v && v->vm_start <= low && high < v->vm_end;
}
static int fetch_build_id(struct vm_area_struct *v, char *id, bool may_fault)
{
	(void)v; (void)may_fault;
	memset(id, 0x5a, BUILD_ID_SIZE_MAX);
	return 0;
}

#include "mmap_unlock_production.h"

struct mmap_unlock_irq_work mmap_unlock_work;

static void check_completion_reservation(void)
{
#ifdef CONFIG_KDLOCK_MMAP
	struct mmap_unlock_irq_work *nested = (void *)1;
	CHECK(mmap_unlock_work.reserved == 1);
	CHECK(mmap_unlock_work.token.mm == NULL);
	CHECK(bpf_mmap_unlock_get_irq_work(&nested));
	CHECK(nested == NULL);
#endif
}

static void reset(void)
{
	memset(&mmap_unlock_work, 0, sizeof(mmap_unlock_work));
	mm = (struct mm_struct){ .refs = 1 };
	task.mm = &mm;
	current = &task;
	irq_disabled = false;
	read_allowed = lookup_found = true;
	queues = direct_unlocks = deferred_unlocks = drops = 0;
	inspect_completion = false;
}

static void complete(void)
{
	CHECK(mmap_unlock_work.irq_work.pending && irq_disabled);
	/* Model irq_work_single: BUSY spans the callback even after PENDING clears. */
	mmap_unlock_work.irq_work.pending = false;
	do_mmap_read_unlock(&mmap_unlock_work.irq_work);
	CHECK(mmap_unlock_work.irq_work.busy);
	mmap_unlock_work.irq_work.busy = false;
}

static u64 empty_callback(u64 a, u64 b, u64 c, u64 d, u64 e)
{
	(void)a; (void)b; (void)c; (void)d; (void)e;
	return 0;
}

#ifdef CONFIG_KDLOCK_MMAP
static u64 nested_callback(u64 a, u64 b, u64 c, u64 d, u64 e)
{
	struct bpf_stack_build_id id = { .ip = 0x1000 };
	(void)a; (void)b; (void)c; (void)d; (void)e;
	CHECK(bpf_find_vma(current, 0x1000, empty_callback, NULL, 0) == -EBUSY);
	CHECK(mm.shares == 1 && mm.refs == 1 && !queues);
	stack_map_get_build_id_offset(&id, 1, true, false);
	CHECK(id.status == BPF_STACK_BUILD_ID_IP);
	CHECK(mm.shares == 1 && mmap_unlock_work.reserved == 1 && !queues);
	return 0;
}

static void check_reusable(void)
{
	struct mmap_unlock_irq_work *work = NULL;
	CHECK(!bpf_mmap_unlock_get_irq_work(&work));
	CHECK(work == &mmap_unlock_work && work->reserved == 1);
	bpf_mmap_unlock_cancel_irq_work(work);
	CHECK(!work->reserved && !work->token.mm && !work->irq_work.busy);
}

static void checked_double_completion(void)
{
	pid_t child = fork();
	int status;
	CHECK(child >= 0);
	if (!child) {
		if (!freopen("/dev/null", "w", stderr))
			_exit(2);
		mmap_read_unlock_complete(&mmap_unlock_work.token);
		_exit(0);
	}
	CHECK(waitpid(child, &status, 0) == child);
	CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 1);
}

static void checked_invalid_cancel(struct mmap_unlock_irq_work *work)
{
	pid_t child = fork();
	int status;
	CHECK(child >= 0);
	if (!child) {
		if (!freopen("/dev/null", "w", stderr))
			_exit(2);
		bpf_mmap_unlock_cancel_irq_work(work);
		_exit(0);
	}
	CHECK(waitpid(child, &status, 0) == child);
	CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 1);
}

static void enabled_cases(void)
{
	struct mmap_unlock_irq_work *outer, *inner;
	struct bpf_stack_build_id id;

	reset(); irq_disabled = true;
	CHECK(!bpf_mmap_unlock_get_irq_work(&outer));
	CHECK(bpf_mmap_unlock_get_irq_work(&inner) && !inner);
	bpf_mmap_unlock_cancel_irq_work(inner);
	CHECK(outer->reserved == 1);
	bpf_mmap_unlock_cancel_irq_work(outer);
	checked_invalid_cancel(outer);
	check_reusable();
	CHECK(mm.refs == 1 && !mm.shares && !queues);

	reset(); irq_disabled = true; read_allowed = false;
	CHECK(bpf_find_vma(current, 0x1000, empty_callback, NULL, 0) == -EBUSY);
	check_reusable();
	CHECK(!mm.shares && mm.refs == 1 && !queues);

	/* Every early stackmap fallback must release its own reservation only. */
	for (int mode = 0; mode < 4; mode++) {
		reset(); irq_disabled = true;
		id = (struct bpf_stack_build_id){ .ip = 0x1000 };
		if (mode == 1) task.mm = NULL;
		if (mode == 2) read_allowed = false;
		if (mode == 3) current = NULL;
		stack_map_get_build_id_offset(&id, 1, mode != 0, false);
		CHECK(id.status == BPF_STACK_BUILD_ID_IP);
		check_reusable();
		CHECK(!mm.shares && mm.refs == 1 && !queues);
	}

	reset(); irq_disabled = true;
	CHECK(bpf_find_vma(current, 0x1000, nested_callback, NULL, 0) == 0);
	CHECK(mm.shares == 1 && mm.refs == 2 && queues == 1);
	CHECK(mmap_unlock_work.reserved == 1 && mmap_unlock_work.token.mm == &mm);
	checked_invalid_cancel(&mmap_unlock_work);
	/* Drop the original owner: the transfer alone now retains the mm. */
	mm.refs--;
	inspect_completion = true;
	complete();
	CHECK(mm.freed && !mm.refs && !mm.shares && drops == 1);
	CHECK(!mmap_unlock_work.reserved && !mmap_unlock_work.token.mm);
	checked_double_completion();
	check_reusable();

	reset(); irq_disabled = true; lookup_found = false;
	CHECK(bpf_find_vma(current, 0x1000, empty_callback, NULL, 0) == -ENOENT);
	CHECK(mm.shares == 1 && mm.refs == 2 && queues == 1);
	complete();
	CHECK(mm.refs == 1 && !mm.shares && drops == 1);
	check_reusable();

	reset(); irq_disabled = true;
	id = (struct bpf_stack_build_id){ .ip = 0x1000 };
	stack_map_get_build_id_offset(&id, 1, true, false);
	CHECK(id.status == BPF_STACK_BUILD_ID_VALID && queues == 1);
	CHECK(mm.shares == 1 && mm.refs == 2);
	complete();
	CHECK(mm.refs == 1 && !mm.shares && drops == 1);
	check_reusable();
}
#endif

int main(void)
{
	reset();
	CHECK(bpf_find_vma(current, 0x1000, empty_callback, NULL, 0) == 0);
	CHECK(!mm.shares && mm.refs == 1 && direct_unlocks == 1 && !queues);
#ifdef CONFIG_KDLOCK_MMAP
	enabled_cases();
	puts("PASS: enabled nested reservation, cancellation, transfer, final release and duplicate-completion rejection");
#else
	reset(); irq_disabled = true;
	CHECK(bpf_find_vma(current, 0x1000, empty_callback, NULL, 0) == 0);
	CHECK(mm.shares == 1 && mm.refs == 1 && queues == 1);
	complete();
	CHECK(!mm.shares && mm.refs == 1 && deferred_unlocks == 1 && !drops);
	puts("PASS: disabled native direct/deferred read unlock without token references");
#endif
	return 0;
}
