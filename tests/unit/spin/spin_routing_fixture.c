/* SPDX-License-Identifier: GPL-2.0 */
/* Extracted hook and acquisition routing with deterministic target/CPU state.
 * Native ownership, active tickets and closing must select the correct path;
 * this does not run queue scheduling or an assembly continuation. */
#include "spin_gate_mock.h"
#include <stddef.h>
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)

typedef unsigned int u32;
static bool promoted, frame_active, context_busy;
static bool cpu_hot = true, trace_admission, sampled_first;
static unsigned int comm_queries, sample_calls;
static unsigned int softirq, scenarios, registrations;
static const char *target_process = "target";
/* Drive closing independently from task identity and retained origin routing. */
static bool source_open = true;
static bool kd_source_is_open(void)
{
	return source_open;
}

#define CONFIG_NR_CPUS 64
#define TASK_COMM_LEN 16
#define noinline __attribute__((noinline))
#define BUILD_BUG_ON(c) _Static_assert(!(c), "kernel build contract")
#define BUG_ON(c) CHECK(!(c))
#define BUG() CHECK(false)
#define unlikely(c) (c)
#define likely(c) (c)
#define spin_acquire(...) ((void)0)
#define DECLARE_PER_CPU(type, name) extern type name[2]
#define DEFINE_PER_CPU(type, name) type name[2]
#define raw_cpu_ptr(p) (&(*(p))[mock_cpu])
#define per_cpu(name, cpu) ((name)[cpu])
#define KD_PR_ERR(...) ((void)0)
#define KD_EXE_LOCK_SPIN 1
#define KD_ENTRY_ABI_LEGACY 0
#define KD_ENTRY_ABI_SPIN_CLOBBER_V1 1
#define alloc_percpu(type) calloc(2, sizeof(type))
#define free_percpu(p) free(p)
#define softirq_count() softirq
#define smp_store_release(p, value) (*(p) = (value))
#define atomic_cmpxchg_acquire(p, old, new) cmpxchg(&(p)->counter, old, new)
#define atomic_andnot(bits, p) ((p)->counter &= ~(bits))
#define atomic_fetch_or_acquire(bits, p) \
	({                               \
		int old = (p)->counter;  \
		(p)->counter |= (bits);  \
		old;                     \
	})
#define atomic_cond_read_relaxed(p, c)  \
	({                              \
		int VAL = (p)->counter; \
		CHECK(c);               \
		VAL;                    \
	})
#define atomic_cond_read_acquire(p, c) atomic_cond_read_relaxed(p, c)

static bool kd_exec_current_frame(void)
{
	return frame_active;
}
static bool kd_exec_context_busy(void)
{
	return context_busy;
}

static void __raw_spin_lock(raw_spinlock_t *lock)
{
	preempt_disable();
	kd_preempt_disable_raw_spin_lock(lock);
}

static void __raw_spin_unlock(raw_spinlock_t *lock)
{
	do_raw_spin_unlock(lock);
	preempt_enable();
}

/* Most scenarios force the cache off to exercise S-first admission directly.
 * The cache scenario below separately proves real hits and avoids duplicate
 * translation-table probes after the key has been populated. */
int kd_spin_native_cache;
static unsigned int cache_queries;
#define KD_EXE_NORMAL 0
struct kd_exe_info { int pid, lock_kind, status_code; unsigned long RIP; };
static struct kd_exe_info registered = {0, KD_EXE_LOCK_SPIN, KD_EXE_NORMAL, 0x1000};
static struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long rip)
{
	cache_queries++;
	return pid == 0 && rip == registered.RIP ? &registered : NULL;
}
static bool do_raw_spin_trylock(raw_spinlock_t *lock)
{
	CHECK(mock_preempt > 0);
	if (lock->held)
		return false;
	kd_preempt_disable_raw_spin_lock(lock);
	return true;
}

struct orig_qspinlock;
struct kd_spin_request;
static bool expect_queue;
static void kd_spin_lock_slowpath(struct orig_qspinlock *lock,
	unsigned long rsp, struct kd_spin_request *request,
	unsigned long ip, unsigned long bp, unsigned int abi);

static int kd_hotlock_record(unsigned long lock)
{
	CHECK(lock);
	sample_calls++;
	sampled_first = true;
	return cpu_hot && promoted;
}
static void kd_exe_add(int pid, unsigned long ip, int kind)
{
	CHECK(pid == 0 && ip == 0x1000 && kind == KD_EXE_LOCK_SPIN);
	registrations++;
}

static void kd_exe_add_abi(int pid, unsigned long ip, int kind, unsigned int abi)
{
	CHECK(abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1);
	kd_exe_add(pid, ip, kind);
}

static bool kd_exec_native_unlock(unsigned long lock, bool mutex)
{
	(void)lock;
	CHECK(!mutex);
	return false;
}

#include "routing_production.h"

/* Deterministic predecessor handoff, not a simulated JIT success. Assert the
 * real acquisition has reserved exactly one ticket/pin before queue entry. */
static void kd_spin_lock_slowpath(struct orig_qspinlock *lock,
	unsigned long rsp, struct kd_spin_request *request,
	unsigned long ip, unsigned long bp, unsigned int abi)
{
	struct kd_spin_ref found = { 0 };
	(void)rsp; (void)bp;
	CHECK(expect_queue && mock_preempt == 1 && ip == 0x1000);
	CHECK(abi == KD_ENTRY_ABI_LEGACY || abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1);
	CHECK(kd_spin_entry_find((raw_spinlock_t *)lock, &found));
	CHECK(found.entry == request->ref.entry && kd_spin_fast_idle());
	CHECK(request->word == &kd_spin_entry_gate(&found)->word);
	CHECK(request->word->val.counter & ~_Q_LOCKED_MASK_HL);
	request->word->val.counter = _Q_LOCKED_VAL_HL;
	expect_queue = false;
}

static raw_spinlock_t locks[KD_SPIN_GATE_SLOTS + 1];

static void hook_lock(raw_spinlock_t *lock)
{
	kd_spin_dispatch_lock(lock, 0, 0x1000);
}

static void hook_unlock(raw_spinlock_t *lock)
{
	kd_spin_dispatch_unlock(lock, 0, 0x1000);
}

/* Cold CPU/lock cannot inspect comm. Non-target traffic still reaches the
 * sampler, and an existing owner can unlock after its CPU cools down. */
static void frequency_before_task(void)
{
	for (unsigned int abi = 0; abi < 2; abi++) {
		for (unsigned int stage = 0; stage < 3; stage++) {
			unsigned int queries = comm_queries, seen = sample_calls;
			cpu_hot = stage != 0;
			promoted = stage != 1;
			strcpy(current->comm, "non-target");
			sampled_first = false;
			trace_admission = true;
			if (abi) kd_spin_dispatch_clobber_lock_v1(&locks[0], 0, 0x1000, 0);
			else hook_lock(&locks[0]);
			CHECK(sample_calls == seen + 1 && locks[0].held);
			CHECK(comm_queries == queries + (stage == 2));
			CHECK(!kd_spin_entry_task_active());
			queries = comm_queries;
			cpu_hot = promoted = false;
			hook_unlock(&locks[0]);
			CHECK(comm_queries == queries && sample_calls == seen + 1);
			CHECK(!locks[0].held && !mock_preempt);
			trace_admission = false;
		}
	}
	cpu_hot = promoted = true;
	strcpy(current->comm, "target");
}

static void promotion_and_rename(void)
{
	struct kd_spin_gate *gate;

	strcpy(current->comm, "target");
	CHECK(__is_kd_test() == 2);
	promoted = false;
	hook_lock(&locks[0]);
	CHECK(mock_preempt == 1 && locks[0].held &&
	      !kd_spin_entry_task_active());
	promoted = true;
	hook_unlock(&locks[0]);
	CHECK(mock_preempt == 0 && !locks[0].held);
	CHECK(kd_spin_gate_find(&locks[0]) == NULL);
	scenarios++;

	hook_lock(&locks[0]);
	gate = kd_spin_gate_find(&locks[0]);
	CHECK(gate && gate->word.locked == 1 && locks[0].held);
	CHECK(mock_preempt == 1 && kd_spin_entry_task_active());
	cpu_hot = false;
	source_open = false;
	CHECK(__is_kd_test() == 2);
	strcpy(current->comm, "renamed");
	CHECK(__is_kd_test() == 2);
	hook_unlock(&locks[0]);
	CHECK(mock_preempt == 0 && !locks[0].held &&
	      gate->word.val.counter == 0);
	CHECK(__is_kd_test() == 0 && !kd_spin_entry_task_active());
	strcpy(current->comm, "target");
	CHECK(__is_kd_test() == 0);
	source_open = true;
	cpu_hot = true;
	scenarios++;

	__raw_spin_lock(&locks[0]);
	strcpy(current->comm, "target");
	CHECK(__is_kd_test() == 2 && mock_preempt == 1);
	hook_unlock(&locks[0]);
	CHECK(mock_preempt == 0 && !locks[0].held);
	scenarios++;
}

static void native_contexts(void)
{
	/* Unlike hardirq/BH contexts, task context with IRQs masked is admitted. */
	mock_irq = true;
	hook_lock(&locks[0]);
	CHECK(mock_irq && mock_preempt == 1 && locks[0].held);
	CHECK(kd_spin_entry_task_active());
	hook_unlock(&locks[0]);
	CHECK(mock_irq && !mock_preempt && !locks[0].held);
	mock_irq = false;
	scenarios++;
	for (unsigned int context = 1; context < 6; context++) {
		mock_irq = context == 0;
		softirq = context == 1;
		current->migration_disabled = context == 2;
		frame_active = context == 3;
		context_busy = context == 4;
		mock_in_task = context != 5;
		mock_preempt =
			1; /* A caller-owned pin must survive each pair. */
		hook_lock(&locks[0]);
		CHECK(mock_preempt == 2 && locks[0].held);
		CHECK(!kd_spin_entry_task_active());
		hook_unlock(&locks[0]);
		CHECK(mock_preempt == 1 && !locks[0].held);
		scenarios++;
	}
	mock_irq = frame_active = context_busy = false;
	mock_in_task = true;
	softirq = 0;
	current->migration_disabled = 0;
	mock_preempt = 0;
}

static void native_continuation_helpers(void)
{
	struct kd_spin_ref ref = { 0 }, other = { 0 };
	bool last = false;

	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) == 0);
	CHECK(kd_spin_entry_borrow_get(&ref) == 0);
	CHECK(kd_spin_entry_mark_native(&ref) == 0);
	CHECK(kd_spin_entry_native_active() && mock_preempt == 1);
	for (int renamed = 0; renamed <= 1; renamed++) {
		strcpy(current->comm, renamed ? "renamed" : "target");
		CHECK(__is_kd_test() == 2);
		hook_lock(&locks[1]);
		CHECK(mock_preempt == 2 && locks[1].held);
		CHECK(!kd_spin_entry_find(&locks[1], &other));
		hook_unlock(&locks[1]);
		CHECK(mock_preempt == 1 && !locks[1].held);
		CHECK(kd_spin_entry_native_active());
		scenarios++;
	}
	CHECK(kd_spin_entry_borrow_put(&ref, &last) == 0 && last);
	CHECK(kd_spin_entry_end(&ref) == 0);
	CHECK(!kd_spin_entry_native_active() && mock_preempt == 0);
	strcpy(current->comm, "target");
}

static void bounded_fallback(void)
{
	struct kd_spin_ref refs[KD_SPIN_ENTRY_SLOTS] = { 0 };

	for (unsigned int i = 0; i < KD_SPIN_ENTRY_SLOTS; i++)
		CHECK(kd_spin_entry_begin(&locks[i], KD_SPIN_ENTRY_HOOK,
					  &refs[i]) == 0);
	hook_lock(&locks[KD_SPIN_ENTRY_SLOTS]);
	CHECK(mock_preempt == KD_SPIN_ENTRY_SLOTS + 1);
	CHECK(locks[KD_SPIN_ENTRY_SLOTS].held);
	hook_unlock(&locks[KD_SPIN_ENTRY_SLOTS]);
	CHECK(mock_preempt == KD_SPIN_ENTRY_SLOTS);
	for (unsigned int i = 0; i < KD_SPIN_ENTRY_SLOTS; i++)
		CHECK(kd_spin_entry_end(&refs[i]) == 0);
	CHECK(mock_preempt == 0);
	scenarios++;
	for (unsigned int i = 0; i < KD_SPIN_GATE_SLOTS; i++)
		CHECK(kd_spin_gate_get(&locks[i]));
	hook_lock(&locks[KD_SPIN_GATE_SLOTS]);
	CHECK(mock_preempt == 1 && locks[KD_SPIN_GATE_SLOTS].held);
	hook_unlock(&locks[KD_SPIN_GATE_SLOTS]);
	CHECK(mock_preempt == 0 && !locks[KD_SPIN_GATE_SLOTS].held);
	scenarios++;
}

/* Uncontended S ownership precedes ticket allocation, with native L still
 * excluding Linux peers. No previous site registration/cache is required. */
static void native_fast_root(void)
{
	struct kd_spin_gate *gate = kd_spin_gate_find(&locks[0]);
	struct kd_spin_ref ref = { 0 };
	unsigned long generation = gate->generation;
	unsigned long sequence = kd_spin_entries[mock_cpu].sequence;
	unsigned int adds = registrations;

	for (unsigned int i = 0; i < 4; i++) {
		hook_lock(&locks[0]);
		CHECK(locks[0].held && mock_preempt == 1);
		CHECK(kd_spin_entry_task_active() && !kd_spin_entry_native_active());
		CHECK(!kd_spin_entry_find(&locks[0], &ref));
		CHECK(gate->word.locked == 1 && gate->owner == current && gate->held);
		CHECK(kd_spin_entries_check_idle() == -EBUSY);
		CHECK(kd_spin_gates_check_idle() == -EBUSY);
		hook_unlock(&locks[0]);
		CHECK(!locks[0].held && !mock_preempt && !gate->word.val.counter);
		CHECK(!gate->held && !gate->owner);
		CHECK(kd_spin_entries_check_idle() == 0);
	}
	CHECK(registrations == adds + 4 && gate->generation == generation + 4);
	CHECK(kd_spin_entries[mock_cpu].sequence == sequence);

	hook_lock(&locks[0]);
	strcpy(current->comm, "renamed");
	source_open = false;
	CHECK(__is_kd_test() == 2);
	hook_lock(&locks[1]);
	CHECK(locks[0].held && locks[1].held && mock_preempt == 2);
	CHECK(kd_spin_entry_find(&locks[1], &ref));
	CHECK(!kd_spin_entry_native_active());
	hook_unlock(&locks[1]);
	CHECK(locks[0].held && !locks[1].held && mock_preempt == 1);
	/* A concurrent tail must survive the root's byte-sized S release. */
	gate->word.val.counter |= 0x10000;
	hook_unlock(&locks[0]);
	ref = (struct kd_spin_ref){ 0 };
	CHECK(!locks[0].held && !mock_preempt && __is_kd_test() == 0);
	CHECK(gate->word.val.counter == 0x10000);
	gate->word.val.counter = 0;

	/* Closing/non-target calls retain the Linux path, with no cached bypass. */
	adds = registrations;
	kd_spin_dispatch_lock(&locks[0], 0, 0x1000);
	CHECK(locks[0].held && mock_preempt == 1 && kd_spin_fast_idle());
	kd_spin_dispatch_unlock(&locks[0], 0, 0x1000);
	source_open = true;
	strcpy(current->comm, "non-target");
	kd_spin_dispatch_lock(&locks[1], 0, 0x2000);
	CHECK(locks[1].held && mock_preempt == 1 && kd_spin_fast_idle());
	kd_spin_dispatch_unlock(&locks[1], 0, 0x2000);
	CHECK(!locks[1].held && !mock_preempt && registrations == adds);
	strcpy(current->comm, "target");
	kd_spin_dispatch_clobber_lock_v1(&locks[1], 0, 0x1000, 0);
	CHECK(locks[1].held && mock_preempt == 1 && !kd_spin_fast_idle());
	CHECK(!kd_spin_entry_find(&locks[1], &ref));
	kd_spin_dispatch_unlock(&locks[1], 0, 0x1000);
	CHECK(!mock_preempt && kd_spin_entries_check_idle() == 0);
	scenarios++;
}

/* Both uncontended and queued roots hash once. The contended ticket adopts
 * that gate/pin, without creating a second gate lookup or a native fast owner. */
static void request_reuses_gate(void)
{
	struct kd_spin_gate *gate = kd_spin_gate_find(&locks[0]);
	for (unsigned int i = 0; i < 100; i++) {
		unsigned int before = gate_hashes;
		unsigned long sequence = kd_spin_entries[mock_cpu].sequence;
		expect_queue = i & 1;
		gate->word.val.counter = expect_queue ? 0x10000 : 0;
		hook_lock(&locks[0]);
		CHECK(!expect_queue && locks[0].held && mock_preempt == 1);
		CHECK(kd_spin_entries[mock_cpu].sequence == sequence + (i & 1));
		hook_unlock(&locks[0]);
		CHECK(!locks[0].held && !mock_preempt && !gate->word.val.counter);
		CHECK(gate_hashes == before + 1);
	}
}

static void optional_native_cache(void)
{
	struct kd_spin_gate *gate = kd_spin_gate_find(&locks[0]);
	struct kd_spin_ref ref = { 0 };
	unsigned int queries = cache_queries, adds;

	kd_spin_native_cache = true;
	hook_lock(&locks[0]); /* first key: S/L owner, not a cached native owner */
	CHECK(gate->held && !kd_spin_entry_native_active());
	hook_unlock(&locks[0]);
	CHECK(cache_queries == queries + 1);
	adds = registrations;
	hook_lock(&locks[0]);
	CHECK(locks[0].held && !gate->word.val.counter && !gate->held);
	CHECK(kd_spin_entry_native_active() && !kd_spin_entry_find(&locks[0], &ref));
	CHECK(registrations == adds && cache_queries == queries + 1);
	strcpy(current->comm, "renamed");
	source_open = false;
	hook_lock(&locks[1]);
	CHECK(locks[1].held && mock_preempt == 2 && !kd_spin_entry_find(&locks[1], &ref));
	hook_unlock(&locks[1]);
	hook_unlock(&locks[0]);
	CHECK(!mock_preempt && kd_spin_fast_idle());
	source_open = true;
	strcpy(current->comm, "target");
	/* Busy S must bypass the native try. The unchanged cached key must not
	 * trigger another kd_get_exe while the real ticket enters the queue. */
	for (unsigned int i = 0; i < 100; i++) {
		expect_queue = true;
		gate->word.val.counter = 0x10000;
		hook_lock(&locks[0]);
		CHECK(!expect_queue && gate->held && mock_preempt == 1);
		CHECK(kd_spin_entry_find(&locks[0], &ref));
		hook_unlock(&locks[0]);
		CHECK(!mock_preempt && !gate->word.val.counter);
	}
	CHECK(cache_queries == queries + 1);
	kd_spin_native_cache = false;
	kd_spin_dispatch_lock(&locks[0], 0, 0x1000);
	CHECK(gate->held && gate->word.locked && !kd_spin_entry_native_active());
	kd_spin_dispatch_unlock(&locks[0], 0, 0x1000);
	CHECK(!mock_preempt && kd_spin_fast_idle());
	scenarios++;
}

int main(void)
{
	/* Exact name equivalence, including embedded terminator/stale tail bytes
	 * and the 8/16-byte boundaries used by the production word comparison. */
	const char *names[] = { "", "a", "target", "1234567", "12345678",
		"123456789012345", "1234567890123456" };
	for (unsigned int i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
		kd_comm_init(&kd_spin_target, names[i]);
		for (unsigned int j = 0; j < sizeof(names) / sizeof(names[0]); j++) {
			memset(current->comm, 0xa5, sizeof(current->comm));
			snprintf(current->comm, sizeof(current->comm), "%s", names[j]);
			CHECK(kd_comm_matches(&kd_spin_target, current->comm) ==
			      !strcmp(names[i], current->comm));
		}
	}
	kd_comm_init(&kd_spin_target, NULL);
	CHECK(!kd_comm_matches(&kd_spin_target, current->comm));
	kd_comm_init(&kd_spin_target, target_process);
	CHECK(kd_spin_entries_init() == 0);
	frequency_before_task();
	promotion_and_rename();
	native_contexts();
	native_continuation_helpers();
	native_fast_root();
	request_reuses_gate();
	optional_native_cache();
	bounded_fallback();
	CHECK(kd_spin_entries_check_idle() == 0 &&
	      kd_spin_gates_check_idle() == 0);
	CHECK(native_claims == native_releases && mock_preempt == 0);
	kd_spin_entries_exit();
	CHECK(scenarios == 15);
	printf("[PASS] test_spin_routing (%u scenarios, %u checks, production hooks/acquisition/helpers)\n",
	       scenarios, checks);
	return 0;
}
