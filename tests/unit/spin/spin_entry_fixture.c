/* SPDX-License-Identifier: GPL-2.0 */
/* Extracted origin-ticket lifetime code over deterministic gate primitives.
 * Allocation refusal, stale generations and borrow release are not live load. */
#include "spin_single_mock.h"
#define smp_store_release(p, v) __atomic_store_n((p), (v), __ATOMIC_RELEASE)
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)

static bool mock_alloc_fail;
#define alloc_percpu(type) (mock_alloc_fail ? NULL : calloc(2, sizeof(type)))
#define free_percpu(p) free(p)

/* Count temporary pins and per-CPU pool access separately from final balance.
 * A read-only query must not add a scheduling boundary or take a guard. */
static unsigned int lookup_pins, pool_reads;
#undef preempt_disable
#define preempt_disable() (lookup_pins++, mock_preempt++)
#undef this_cpu_ptr
#define this_cpu_ptr(p) (pool_reads++, &(p)[mock_cpu])

/* This fixture owns tickets only. The routing fixture separately exercises
 * the production native fast owner and its integration with these queries. */
static bool kd_spin_fast_active(void) { return false; }
static bool kd_spin_fast_idle(void) { return true; }

static void (*wait_peer)(void);
#define cpu_relax() do { if (wait_peer) wait_peer(); } while (0)
#include "entry_production.h"

static raw_spinlock_t locks[KD_SPIN_ENTRY_SLOTS + 1];

static void select_cpu(unsigned int cpu)
{
	CHECK(!mock_irq);
	mock_cpu = cpu;
	current = &tasks[cpu];
}

/* A contended root transfers its existing pin only on successful admission.
 * Wrong-gate/duplicate/refusal paths must neither repin nor consume it. */
static struct kd_spin_ref retiring;
static unsigned int retirement_polls;
static void retire_peer(void)
{
	bool last;

	CHECK(mock_preempt == 1 && retiring.entry->native_refs);
	if (++retirement_polls < 3)
		return;
	select_cpu(1);
	CHECK(!kd_spin_entry_borrow_put(&retiring, &last) && last);
	select_cpu(0);
	wait_peer = NULL;
}

/* A final physical ACK cannot consume the root pin while a no-lock relay
 * still borrows the ticket. Exercise the actual guarded wait/end functions. */
static void retirement_barrier(void)
{
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &retiring));
	CHECK(!kd_spin_entry_borrow_get(&retiring));
	CHECK(!kd_spin_entry_mark_native(&retiring));
	CHECK(kd_spin_entry_end(&retiring) == -EBUSY && mock_preempt == 1);
	retirement_polls = 0;
	wait_peer = retire_peer;
	CHECK(!kd_spin_entry_borrow_wait(&retiring) && retirement_polls == 3);
	CHECK(mock_preempt == 1 && !kd_spin_entry_end(&retiring) && !mock_preempt);
	/* All remote executors may retire before the native-ready load. */
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &retiring));
	CHECK(!kd_spin_entry_mark_native(&retiring));
	CHECK(!kd_spin_entry_borrow_wait(&retiring));
	CHECK(!kd_spin_entry_end(&retiring) && !mock_preempt);
}

static void pinned_admission(void)
{
	struct kd_spin_ref ref = { 0 }, duplicate = { 0 };
	kd_spinlock_t *gate = &locks[0];
	unsigned int pins = lookup_pins;

	CHECK(kd_spin_entry_begin_pinned(&locks[0], &ref) == -EPERM);
	preempt_disable();
	CHECK(kd_spin_entry_begin_pinned(&locks[0], &ref) == 0);
	CHECK(kd_spin_entry_begin_pinned(&locks[0], &duplicate) == -EDEADLK);
	CHECK(mock_preempt == 1 && !duplicate.entry);
	CHECK(lookup_pins == pins + 1);
	CHECK(kd_spin_entry_word(&ref) == gate);
	CHECK(kd_spin_entry_end(&ref) == 0 && !mock_preempt);
}

static void lifecycle(void)
{
	struct kd_spin_ref ref = { 0 }, other = { 0 }, stale, found = { 0 };
	kd_spinlock_t *gate;
	bool last = false;
	unsigned int guards;

	CHECK(kd_spin_entries_check_idle() == 0);
	CHECK(!kd_spin_entry_task_active() && !kd_spin_entry_native_active());
	CHECK(kd_spin_entry_begin(NULL, KD_SPIN_ENTRY_HOOK, &ref) == -EINVAL);
	mock_irq = true;
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) == 0);
	CHECK(mock_irq && mock_preempt == 1);
	CHECK(kd_spin_entry_end(&ref) == 0 && mock_irq && !mock_preempt);
	mock_irq = false;
	mock_in_task = false;
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) ==
	      -EINVAL);
	mock_in_task = true;
	CHECK(mock_preempt == 0);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) == 0);
	CHECK(mock_preempt == 1 && kd_spin_entry_task_active());
	CHECK(kd_spin_entry_find(&locks[0], &found) &&
	      found.entry == ref.entry);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &other) ==
	      -EDEADLK);
	CHECK(mock_preempt == 1 && !other.entry);
	CHECK(kd_spin_entries_check_idle() == -EBUSY);
	/* Guard's own pin must not make an unpinned caller look valid. */
	mock_preempt = 0;
	CHECK(kd_spin_entry_word(&ref) == NULL);
	CHECK(kd_spin_entry_claim(&ref) == -EPERM);
	CHECK(kd_spin_entry_release_origin(&ref) == -EPERM);
	CHECK(kd_spin_entry_mark_native(&ref) == -EPERM);
	CHECK(kd_spin_entry_end(&ref) == -EPERM);
	CHECK(mock_preempt == 0 && ref.entry);
	CHECK(!kd_spin_entry_find(&locks[0], &found));
	CHECK(!kd_spin_entry_task_active() && !kd_spin_entry_native_active());
	mock_preempt = 1;
	current = &tasks[1];
	CHECK(kd_spin_entry_end(&ref) == -EPERM);
	current = &tasks[0];
	select_cpu(1);
	mock_preempt = 1;
	current = &tasks[0];
	CHECK(kd_spin_entry_end(&ref) == -EPERM);
	mock_preempt = 0;
	select_cpu(0);
	gate = kd_spin_entry_word(&ref);
	CHECK(gate && kd_spin_entry_claim(&ref) == -EINVAL);
	gate->locked = 1;
	guards = map_locks;
	CHECK(kd_spin_entry_claim(&ref) == 0);
	CHECK(map_locks == guards + 1 && !mock_irq);
	CHECK(kd_spin_entry_claim(&ref) == 0);
	CHECK(kd_spin_entry_end(&ref) == -EBUSY && locks[0].held);
	CHECK(kd_spin_entry_borrow_get(&ref) == -EINVAL);
	guards = map_locks;
	CHECK(kd_spin_entry_release_origin(&ref) == 0);
	CHECK(map_locks == guards + 1 && !mock_irq);
	CHECK(locks[0].held && gate->locked == 1 && mock_preempt == 1);
	CHECK(kd_spin_entry_release_origin(&ref) == -EBUSY);
	gate->val.counter = 0;
	stale = ref;
	CHECK(kd_spin_entry_end(&ref) == 0 && !ref.entry && mock_preempt == 0);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_VIRTUAL, &ref) == 0);
	CHECK(ref.entry == stale.entry && ref.sequence != stale.sequence);
	CHECK(kd_spin_entry_word(&stale) == NULL);
	CHECK(kd_spin_entry_end(&stale) == -ESTALE);
	CHECK(kd_spin_entry_borrow_get(&stale) == -ESTALE);
	CHECK(kd_spin_entry_borrow_put(&stale, &last) == -ESTALE);
	CHECK(kd_spin_entry_borrow_get(&ref) == -EINVAL);
	CHECK(kd_spin_entry_mark_native(&ref) == -EINVAL);
	CHECK(kd_spin_entry_end(&ref) == 0);
}

/* Live tickets keep their own pin, while root callers cannot own a ticket.
 * Exercise those two cases, including read-only access while guard is held. */
static void read_only_queries(void)
{
	struct kd_spin_ref ref = { 0 }, found = { 0 };
	kd_spinlock_t *gate;
	unsigned int pins = lookup_pins, reads = pool_reads, guards = map_locks;
	unsigned long flags;

	CHECK(mock_preempt == 0);
	CHECK(!kd_spin_entry_task_active() && !kd_spin_entry_native_active());
	CHECK(!kd_spin_entry_find(&locks[0], &found));
	CHECK(lookup_pins == pins && pool_reads == reads && map_locks == guards);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) == 0);
	gate = &locks[0];
	pins = lookup_pins;
	guards = map_locks;
	CHECK(kd_spin_entry_task_active() && !kd_spin_entry_native_active());
	CHECK(kd_spin_entry_find(&locks[0], &found));
	CHECK(found.entry == ref.entry && found.sequence == ref.sequence);
	CHECK(kd_spin_entry_word(&ref) == gate);
	CHECK(lookup_pins == pins && map_locks == guards && mock_preempt == 1);
	raw_spin_lock_irqsave(&ref.entry->guard, flags);
	CHECK(kd_spin_entry_word(&ref) == gate);
	raw_spin_unlock_irqrestore(&ref.entry->guard, flags);
	/* CPU/task/generation checks still protect the guard-free read. */
	current = &tasks[1];
	CHECK(kd_spin_entry_word(&ref) == NULL);
	current = &tasks[0];
	select_cpu(1);
	preempt_disable();
	CHECK(kd_spin_entry_word(&ref) == NULL);
	preempt_enable();
	select_cpu(0);
	mock_in_task = false;
	CHECK(kd_spin_entry_word(&ref) == NULL);
	CHECK(!kd_spin_entry_find(&locks[0], &found));
	mock_in_task = true;
	CHECK(kd_spin_entry_end(&ref) == 0 && mock_preempt == 0);
}

static void remote_native(void)
{
	struct kd_spin_ref waiter = { 0 }, a = { 0 }, b = { 0 };
	kd_spinlock_t *ag, *bg;
	bool last = true;

	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &a) == 0);
	CHECK(kd_spin_entry_begin(&locks[1], KD_SPIN_ENTRY_VIRTUAL, &b) == 0);
	ag = kd_spin_entry_word(&a);
	bg = kd_spin_entry_word(&b);
	ag->locked = bg->locked = 1;
	CHECK(kd_spin_entry_claim(&a) == 0 && kd_spin_entry_claim(&b) == 0);
	CHECK(mock_preempt == 2 && locks[0].held && locks[1].held);
	select_cpu(1);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &waiter) == 0);
	CHECK(mock_preempt == 1);
	select_cpu(0);
	CHECK(kd_spin_entry_borrow_get(&waiter) == 0);
	CHECK(kd_spin_entry_borrow_get(&waiter) == 0);
	CHECK(kd_spin_entry_end(&waiter) == -EPERM && mock_preempt == 2);
	select_cpu(1);
	CHECK(kd_spin_entry_claim(&waiter) == -EBUSY);
	CHECK(kd_spin_entry_mark_native(&waiter) == 0);
	CHECK(kd_spin_entry_native_active());
	CHECK(kd_spin_entry_borrow_get(&waiter) == -EINVAL);
	CHECK(kd_spin_entry_end(&waiter) == -EBUSY && mock_preempt == 1);
	select_cpu(0);
	CHECK(kd_spin_entry_release_origin(&a) == 0);
	ag->val.counter = 0;
	CHECK(kd_spin_entry_end(&a) == 0 && mock_preempt == 1);
	CHECK(kd_spin_entry_borrow_put(&waiter, &last) == 0 && !last);
	select_cpu(1);
	CHECK(mock_preempt == 1 && kd_spin_entry_native_active());
	CHECK(!locks[0].held && locks[1].held);
	CHECK(kd_spin_entry_end(&waiter) == -EBUSY);
	select_cpu(0);
	CHECK(kd_spin_entry_release_origin(&b) == 0);
	bg->val.counter = 0;
	CHECK(kd_spin_entry_end(&b) == 0 && mock_preempt == 0);
	CHECK(kd_spin_entry_borrow_put(&waiter, &last) == 0 && last);
	CHECK(mock_preempt == 0 && mock_preempts[1] == 1);
	CHECK(kd_spin_entry_borrow_put(&waiter, &last) == -EINVAL);
	select_cpu(1);
	CHECK(kd_spin_entry_end(&waiter) == 0 && mock_preempt == 0);
	CHECK(!kd_spin_entry_native_active() && !kd_spin_entry_task_active());
	select_cpu(0);
}

/* Early release retains the ticket generation; reclaim follows a new CAS. */
static void reclaim(void)
{
 struct kd_spin_ref ref = { 0 }, stale;
 CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) == 0);
 locks[0].locked = 1;
 CHECK(kd_spin_entry_claim(&ref) == 0);
 CHECK(kd_spin_entry_release_origin(&ref) == 0);
 CHECK(kd_spin_entry_release_origin(&ref) == -EBUSY);
 locks[0].locked = 0;
 CHECK(kd_spin_entry_reclaim(&ref) == -EINVAL);
 locks[0].locked = 1;
 CHECK(kd_spin_entry_reclaim(&ref) == 0);
 CHECK(kd_spin_entry_owner(&locks[0]) == (unsigned long)current);
 CHECK(kd_spin_entry_end(&ref) == -EBUSY);
 CHECK(kd_spin_entry_release_origin(&ref) == 0);
 locks[0].locked = 0;
 stale = ref;
 CHECK(kd_spin_entry_end(&ref) == 0);
 CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) == 0);
 CHECK(ref.sequence != stale.sequence);
 CHECK(kd_spin_entry_reclaim(&stale) == -ESTALE);
 CHECK(kd_spin_entry_end(&ref) == 0);
}

static void capacity(void)
{
	struct kd_spin_ref refs[KD_SPIN_ENTRY_SLOTS] = { 0 }, extra = { 0 },
			   stale;
	bool last = false;

	for (unsigned int i = 0; i < KD_SPIN_ENTRY_SLOTS; i++) {
		CHECK(kd_spin_entry_begin(&locks[i], KD_SPIN_ENTRY_HOOK,
					  &refs[i]) == 0);
		CHECK(mock_preempt == (int)i + 1);
	}
	CHECK(kd_spin_entry_begin(&locks[KD_SPIN_ENTRY_SLOTS],
				  KD_SPIN_ENTRY_HOOK, &extra) == -E2BIG);
	CHECK(mock_preempt == KD_SPIN_ENTRY_SLOTS && !extra.entry);
	stale = refs[0];
	CHECK(kd_spin_entry_end(&refs[0]) == 0);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &refs[0]) ==
	      0);
	CHECK(refs[0].sequence != stale.sequence &&
	      refs[0].entry == stale.entry);
	CHECK(kd_spin_entry_end(&stale) == -ESTALE);
	refs[0].entry->native_refs = UINT_MAX;
	CHECK(kd_spin_entry_borrow_get(&refs[0]) == -EOVERFLOW);
	refs[0].entry->native_refs = 0;
	CHECK(kd_spin_entry_borrow_get(&refs[0]) == 0);
	CHECK(kd_spin_entry_borrow_put(&refs[0], &last) == 0 && last);
	for (unsigned int i = 0; i < KD_SPIN_ENTRY_SLOTS; i++)
		CHECK(kd_spin_entry_end(&refs[i]) == 0);
	CHECK(mock_preempt == 0);
	kd_spin_entries[0].sequence = ULONG_MAX;
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &extra) ==
	      -EOVERFLOW);
	CHECK(mock_preempt == 0 && !extra.entry);

}

int main(void)
{
	struct kd_spin_ref ref = { 0 };

	mock_alloc_fail = true;
	CHECK(kd_spin_entries_init() == -ENOMEM);
	CHECK(!kd_spin_entry_task_active() &&
	      kd_spin_entries_check_idle() == 0);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) ==
	      -ENODEV);
	mock_alloc_fail = false;
	CHECK(kd_spin_entries_init() == 0);
	CHECK(kd_spin_entries_init() == -EBUSY);
	retirement_barrier();
	pinned_admission();
	lifecycle();
	read_only_queries();
	remote_native();
	reclaim();
	capacity();
	CHECK(kd_spin_entries_check_idle() == 0);
	CHECK(mock_preempts[0] == 0 && mock_preempts[1] == 0 && !mock_irq);
	kd_spin_entries_exit();
	CHECK(!kd_spin_entries && kd_spin_entries_check_idle() == 0);
	printf("[PASS] test_spin_entry (%u checks, production single-word tickets)\n",
	       checks);
	return 0;
}
