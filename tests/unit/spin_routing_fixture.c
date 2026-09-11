/* SPDX-License-Identifier: GPL-2.0 */
/* Extracted hook and acquisition routing with deterministic target/CPU state.
 * Native ownership, active tickets and closing must select the correct path;
 * this does not run queue scheduling or an assembly continuation. */
#include "spin_gate_mock.h"

typedef unsigned int u32;
static bool promoted, frame_active, context_busy;
static unsigned int softirq, scenarios;
static const char *target_process = "target";
/* Drive closing independently from task identity and retained origin routing. */
static bool source_open = true;
static bool kd_source_is_open(void)
{
	return source_open;
}

#define CONFIG_NR_CPUS 64
#define BUG_ON(c) CHECK(!(c))
#define BUG() CHECK(false)
#define unlikely(c) (c)
#define KD_PR_ERR(...) ((void)0)
#define KD_EXE_LOCK_SPIN 1
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

int main(void)
{
	CHECK(kd_spin_entries_init() == 0);
	promotion_and_rename();
	native_contexts();
	native_continuation_helpers();
	bounded_fallback();
	CHECK(kd_spin_entries_check_idle() == 0 &&
	      kd_spin_gates_check_idle() == 0);
	CHECK(native_claims == native_releases && mock_preempt == 0);
	kd_spin_entries_exit();
	CHECK(scenarios == 13);
	printf("[PASS] test_spin_routing (%u scenarios, %u checks, production hooks/acquisition/helpers)\n",
	       scenarios, checks);
	return 0;
}
