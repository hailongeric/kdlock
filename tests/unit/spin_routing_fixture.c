/* SPDX-License-Identifier: GPL-2.0 */
/* Extracted hook and acquisition routing with deterministic target/CPU state.
 * Native ownership, active tickets and closing must select the correct path;
 * this does not run queue scheduling or an assembly continuation. */
#include "spin_gate_mock.h"

typedef unsigned int u32;
static bool promoted, frame_active, context_busy;
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
#define KD_EXE_NORMAL 0
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

static bool do_raw_spin_trylock(raw_spinlock_t *lock)
{
	CHECK(mock_preempt > 0);
	if (lock->held)
		return false;
	kd_preempt_disable_raw_spin_lock(lock);
	return true;
}

struct kd_exe_info {
	int pid, lock_kind, status_code;
	unsigned long RIP;
};
static struct kd_exe_info registered = { 0, KD_EXE_LOCK_SPIN, -1, 0x1000 };
static struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long rip)
{
	return pid == (unsigned int)registered.pid && rip == registered.RIP ?
		&registered : NULL;
}

struct orig_qspinlock;
static void kd_spin_lock_slowpath(struct orig_qspinlock *lock,
				  unsigned long rsp)
{
	(void)lock;
	(void)rsp;
	CHECK(false); /* This fixture never represents a queue or JIT completion. */
}

static bool kd_hotlock_is_promoted(unsigned long lock)
{
	(void)lock;
	return promoted;
}

static void kd_hotlock_record(unsigned long lock)
{
	(void)lock;
}
static void kd_exe_add(int pid, unsigned long ip, int kind)
{
	CHECK(pid == 0 && ip == 0x1000 && kind == KD_EXE_LOCK_SPIN);
	registrations++;
}

static bool kd_exec_native_unlock(unsigned long lock, bool mutex)
{
	(void)lock;
	CHECK(!mutex);
	return false;
}

#include "routing_production.h"

static raw_spinlock_t locks[KD_SPIN_GATE_SLOTS + 1];

static void hook_lock(raw_spinlock_t *lock)
{
	__kd_raw_spin_lock(lock, 0, 0x1000);
}

static void hook_unlock(raw_spinlock_t *lock)
{
	__kd_raw_spin_unlock(lock, 0, 0x1000);
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
	for (unsigned int context = 0; context < 6; context++) {
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

/* A published, uncontended root must really own Linux L without a ticket or
 * private S. Test native-peer exclusion, queue priority, nesting, comm changes
 * and admission closing; timing and live queue/JIT are checked in the guest. */
static void native_fast_root(void)
{
	struct kd_spin_gate *gate = kd_spin_gate_find(&locks[0]);
	struct kd_spin_ref ref = { 0 };
	unsigned int adds;
	unsigned long generation = gate->generation;

	registered.status_code = KD_EXE_NORMAL;
	kd_spin_fast_remember(&locks[0], 0x1000);
	adds = registrations;
	for (unsigned int i = 0; i < 4; i++) {
		hook_lock(&locks[0]);
		CHECK(locks[0].held && mock_preempt == 1);
		CHECK(kd_spin_entry_task_active() && kd_spin_entry_native_active());
		CHECK(!kd_spin_entry_find(&locks[0], &ref));
		CHECK(!gate->word.val.counter && !gate->owner);
		CHECK(kd_spin_entries_check_idle() == -EBUSY);
		hook_unlock(&locks[0]);
		CHECK(!locks[0].held && mock_preempt == 0);
		CHECK(kd_spin_entries_check_idle() == 0);
	}
	CHECK(registrations == adds && gate->generation == generation);

	/* Native fast ownership survives both nested hooks and lost target name. */
	hook_lock(&locks[0]);
	strcpy(current->comm, "renamed");
	source_open = false;
	CHECK(__is_kd_test() == 2);
	hook_lock(&locks[1]);
	CHECK(locks[0].held && locks[1].held && mock_preempt == 2);
	hook_unlock(&locks[1]);
	CHECK(locks[0].held && !locks[1].held && mock_preempt == 1);
	hook_unlock(&locks[0]);
	CHECK(!locks[0].held && !mock_preempt && __is_kd_test() == 0);
	CHECK(!kd_spin_fast_trylock(&locks[0], 0x1000));
	strcpy(current->comm, "target");
	source_open = true;

	/* Either the original lock or a private queued tail must defeat the try. */
	locks[0].held = true;
	CHECK(!kd_spin_fast_trylock(&locks[0], 0x1000));
	CHECK(locks[0].held && !mock_preempt && kd_spin_fast_idle());
	locks[0].held = false;
	gate->word.val.counter = 0x100;
	CHECK(!kd_spin_fast_trylock(&locks[0], 0x1000));
	CHECK(gate->word.val.counter == 0x100 && !locks[0].held && !mock_preempt);
	CHECK(kd_spin_fast_acquire(&locks[0], 0x1000) == KD_SPIN_FAST_MISS_PINNED);
	CHECK(mock_preempt == 1 && !locks[0].held && kd_spin_fast_idle());
	CHECK(kd_spin_fast_acquire(&locks[0], 0x1000) == KD_SPIN_FAST_CONTEXT);
	CHECK(mock_preempt == 1);
	preempt_enable();
	gate->word.val.counter = 0;
	CHECK(!kd_spin_fast_trylock(&locks[0], 0x2000));
	CHECK(!kd_spin_fast_trylock(&locks[1], 0x1000));
	CHECK(kd_spin_entries_check_idle() == 0 && registrations == adds);

	/* Combined entry: cached native L works for a caller that has lost its
	 * target name, without inventing a JIT/ticket. Cold non-target sites must
	 * retain Linux fallback; closing and nested ownership still route safely. */
	strcpy(current->comm, "non-target");
	CHECK(__is_kd_test() == 0);
	kd_spin_dispatch_lock(&locks[0], 0, 0x1000);
	CHECK(locks[0].held && mock_preempt == 1 && !kd_spin_fast_idle());
	CHECK(!kd_spin_entry_find(&locks[0], &ref) && registrations == adds);
	source_open = false;
	kd_spin_dispatch_lock(&locks[1], 0, 0x1000);
	CHECK(locks[0].held && locks[1].held && mock_preempt == 2);
	kd_spin_dispatch_unlock(&locks[1], 0, 0x1000);
	kd_spin_dispatch_unlock(&locks[0], 0, 0x1000);
	CHECK(!locks[0].held && !locks[1].held && !mock_preempt);
	CHECK(kd_spin_fast_idle() && __is_kd_test() == 0);
	kd_spin_dispatch_lock(&locks[1], 0, 0x2000);
	CHECK(locks[1].held && mock_preempt == 1 && kd_spin_fast_idle());
	kd_spin_dispatch_unlock(&locks[1], 0, 0x2000);
	CHECK(!locks[1].held && !mock_preempt && registrations == adds);
	source_open = true;
	strcpy(current->comm, "target");
	/* A selected cache miss still uses the actual ticket/gate producer. */
	kd_spin_dispatch_lock(&locks[1], 0, 0x1000);
	CHECK(locks[1].held && mock_preempt == 1);
	CHECK(kd_spin_entry_find(&locks[1], &ref));
	kd_spin_dispatch_unlock(&locks[1], 0, 0x1000);
	CHECK(!locks[1].held && !mock_preempt && kd_spin_entries_check_idle() == 0);
	registered.status_code = -1;
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
	promotion_and_rename();
	native_contexts();
	native_continuation_helpers();
	native_fast_root();
	bounded_fallback();
	CHECK(kd_spin_entries_check_idle() == 0 &&
	      kd_spin_gates_check_idle() == 0);
	CHECK(native_claims == native_releases && mock_preempt == 0);
	kd_spin_entries_exit();
	CHECK(scenarios == 14);
	printf("[PASS] test_spin_routing (%u scenarios, %u checks, production hooks/acquisition/helpers)\n",
	       scenarios, checks);
	return 0;
}
