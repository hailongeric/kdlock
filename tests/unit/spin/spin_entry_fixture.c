/* SPDX-License-Identifier: GPL-2.0 */
/* Extracted origin-ticket lifetime code over deterministic gate primitives.
 * Allocation refusal, stale generations and borrow release are not live load. */
#include "spin_single_mock.h"
#define smp_store_release(p, v) __atomic_store_n((p), (v), __ATOMIC_RELEASE)
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define atomic_cmpxchg_acquire(p, old, v) cmpxchg(&(p)->counter, old, v)
#define BUG_ON(condition) CHECK(!(condition))

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

/* Force a peer transition after a production snapshot but before its CAS.
 * This exercises retry/ABA decisions, not a hardware memory-order litmus. */
static void (*cas_peer)(void);
static unsigned long ticket_cmpxchg(atomic64_t *control, unsigned long old,
				   unsigned long value)
{
	if (cas_peer) {
		void (*peer)(void) = cas_peer;

		cas_peer = NULL;
		peer();
	}
	return cmpxchg(&control->counter, old, value);
}
#undef atomic64_cmpxchg
#define atomic64_cmpxchg(p, old, v) ticket_cmpxchg(p, old, v)

static void (*wait_peer)(void);
#define cpu_relax() do { if (wait_peer) wait_peer(); } while (0)
#include "entry_production.h"

_Static_assert(sizeof(((struct kd_spin_entry *)0)->control) == 8,
	       "ticket transitions must use one 64-bit atomic");
_Static_assert(KD_ENTRY_NATIVE <= KD_ENTRY_STATE_MASK,
	       "all ticket phases must fit below the kind bit");
_Static_assert(KD_ENTRY_SEQUENCE_MAX == ((1UL << 48) - 1),
	       "ticket generations must not silently shrink or wrap");
_Static_assert((KD_ENTRY_REF_MASK & (KD_ENTRY_STATE_MASK | KD_ENTRY_VIRTUAL_BIT)) == 0,
	       "ticket borrows must not overlap phase or kind");

static raw_spinlock_t locks[KD_SPIN_ENTRY_SLOTS + 1];

/* Exercise the mixed helper with the real ticket allocator/claim/retirement,
 * including a contended word and a peer's pending/tail bits at release. */
static void mixed_ticket(void)
{
	struct kd_spin_ref ref = { 0 }, stale;

	CHECK(!kd_spin_nested_try_once(&locks[0], &ref));
	CHECK(mock_preempt == 1 && locks[0].val.counter == 1);
	stale = ref;
	locks[0].val.counter = 0x12340101;
	CHECK(!kd_spin_nested_release_exact(&locks[0], &ref));
	CHECK(!mock_preempt && locks[0].val.counter == 0x12340100);
	CHECK(kd_spin_nested_release_exact(&locks[0], &stale) == -EINVAL);
	CHECK(kd_spin_nested_try_once(&locks[0], &ref) == -EAGAIN);
	CHECK(!mock_preempt && !ref.entry && locks[0].val.counter == 0x12340100);
	locks[0].val.counter = 0;
	CHECK(!kd_spin_entries_check_idle());
}

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

	CHECK(mock_preempt == 1 &&
	      kd_entry_refs(atomic64_read(&retiring.entry->control)));
	if (++retirement_polls < 3)
		return;
	select_cpu(1);
	CHECK(!kd_spin_entry_borrow_put(&retiring, &last) && last);
	select_cpu(0);
	wait_peer = NULL;
}

/* A final physical ACK cannot consume the root pin while a no-lock relay
 * still borrows the ticket. Exercise the actual atomic wait/end functions. */
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
	CHECK(kd_spin_entry_end_pinned(&ref) == 0 && !ref.entry && mock_preempt == 1);
	preempt_enable();
	CHECK(!mock_preempt);
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
	/* Every local mutation must reject an unpinned caller before work. */
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
	CHECK(map_locks == guards && !mock_irq);
	CHECK(kd_spin_entry_claim(&ref) == 0);
	CHECK(kd_spin_entry_end(&ref) == -EBUSY && locks[0].held);
	CHECK(kd_spin_entry_borrow_get(&ref) == -EINVAL);
	guards = map_locks;
	CHECK(kd_spin_entry_release_origin(&ref) == 0);
	CHECK(map_locks == guards && !mock_irq);
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
 * Exercise those two cases, including read-only access with another owner pin. */
static void read_only_queries(void)
{
	struct kd_spin_ref ref = { 0 }, found = { 0 };
	kd_spinlock_t *gate;
	unsigned int pins = lookup_pins, reads = pool_reads, guards = map_locks;

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
	preempt_disable();
	CHECK(kd_spin_entry_word(&ref) == gate);
	preempt_enable();
	/* CPU/task/generation checks still protect the read-only query. */
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

/* A peer can have validated the old WAITING tag when the owner frees and
 * reuses the same address. Only the full generation+state+count CAS may commit. */
static struct kd_spin_ref interleaved;
static bool replacement_borrow;

static void recycle_during_cas(void)
{
	unsigned int caller = mock_cpu;
	bool last;

	select_cpu(0);
	if (replacement_borrow)
		CHECK(!kd_spin_entry_borrow_put(&interleaved, &last) && last);
	CHECK(!kd_spin_entry_end(&interleaved));
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &interleaved));
	if (replacement_borrow)
		CHECK(!kd_spin_entry_borrow_get(&interleaved));
	select_cpu(caller);
}

static void mark_native_during_cas(void)
{
	unsigned int caller = mock_cpu;

	select_cpu(0);
	CHECK(!kd_spin_entry_mark_native(&interleaved));
	select_cpu(caller);
}

static void borrow_during_cas(void)
{
	unsigned int caller = mock_cpu;

	select_cpu(1);
	CHECK(!kd_spin_entry_borrow_get(&interleaved));
	select_cpu(caller);
}

static void atomic_interleavings(void)
{
	struct kd_spin_ref stale;
	bool last = false;

	/* A delayed get must not borrow a new occupant of the same slot. */
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &interleaved));
	stale = interleaved;
	select_cpu(1);
	cas_peer = recycle_during_cas;
	CHECK(kd_spin_entry_borrow_get(&stale) == -ESTALE);
	CHECK(interleaved.entry == stale.entry &&
	      interleaved.sequence != stale.sequence);
	CHECK(!kd_entry_refs(atomic64_read(&interleaved.entry->control)));
	select_cpu(0);
	CHECK(!kd_spin_entry_end(&interleaved));

	/* The same ABA must not let a duplicated stale put retire a new borrow. */
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &interleaved));
	CHECK(!kd_spin_entry_borrow_get(&interleaved));
	stale = interleaved;
	replacement_borrow = true;
	select_cpu(1);
	cas_peer = recycle_during_cas;
	CHECK(kd_spin_entry_borrow_put(&stale, &last) == -ESTALE);
	CHECK(kd_entry_refs(atomic64_read(&interleaved.entry->control)) == 1);
	CHECK(!kd_spin_entry_borrow_put(&interleaved, &last) && last);
	select_cpu(0);
	CHECK(!kd_spin_entry_end(&interleaved));
	replacement_borrow = false;

	/* Native publication closes get admission even after its initial read. */
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &interleaved));
	select_cpu(1);
	cas_peer = mark_native_during_cas;
	CHECK(kd_spin_entry_borrow_get(&interleaved) == -EINVAL);
	CHECK(!kd_entry_refs(atomic64_read(&interleaved.entry->control)));
	select_cpu(0);
	CHECK(!kd_spin_entry_end(&interleaved));

	/* A borrow winning against mark-native survives the retry and blocks end. */
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &interleaved));
	cas_peer = borrow_during_cas;
	CHECK(!kd_spin_entry_mark_native(&interleaved));
	CHECK(kd_entry_refs(atomic64_read(&interleaved.entry->control)) == 1);
	CHECK(kd_spin_entry_end(&interleaved) == -EBUSY);
	select_cpu(1);
	CHECK(!kd_spin_entry_borrow_put(&interleaved, &last) && last);
	select_cpu(0);
	CHECK(!kd_spin_entry_end(&interleaved));

	/* The same admission race prevents local claim and slot retirement. */
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &interleaved));
	locks[0].locked = 1;
	cas_peer = borrow_during_cas;
	CHECK(kd_spin_entry_claim(&interleaved) == -EBUSY);
	CHECK(!kd_spin_entry_borrow_put(&interleaved, &last) && last);
	locks[0].locked = 0;
	cas_peer = borrow_during_cas;
	CHECK(kd_spin_entry_end(&interleaved) == -EBUSY);
	CHECK(!kd_spin_entry_borrow_put(&interleaved, &last) && last);
	CHECK(!kd_spin_entry_end(&interleaved));
	CHECK(!cas_peer && !mock_preempts[0] && !mock_preempts[1]);
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
	atomic64_set(&refs[0].entry->control,
		     atomic64_read(&refs[0].entry->control) | KD_ENTRY_REF_MASK);
	CHECK(kd_spin_entry_borrow_get(&refs[0]) == -EOVERFLOW);
	atomic64_set(&refs[0].entry->control,
		     atomic64_read(&refs[0].entry->control) & ~KD_ENTRY_REF_MASK);
	CHECK(kd_spin_entry_borrow_get(&refs[0]) == 0);
	CHECK(kd_spin_entry_borrow_put(&refs[0], &last) == 0 && last);
	for (unsigned int i = 0; i < KD_SPIN_ENTRY_SLOTS; i++)
		CHECK(kd_spin_entry_end(&refs[i]) == 0);
	CHECK(mock_preempt == 0);
	/* The last representable generation succeeds; subsequent allocation
	 * fails without reusing a generation, including an out-of-range pool. */
	kd_spin_entries[0].sequence = KD_ENTRY_SEQUENCE_MAX - 1;
	CHECK(!kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &extra));
	CHECK(extra.sequence == KD_ENTRY_SEQUENCE_MAX);
	stale = extra;
	stale.sequence |= 1UL << 48;
	CHECK(kd_spin_entry_borrow_get(&stale) == -ESTALE);
	CHECK(kd_spin_entry_end(&stale) == -ESTALE);
	CHECK(!kd_spin_entry_end(&extra));
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &extra) ==
	      -EOVERFLOW);
	CHECK(mock_preempt == 0 && !extra.entry);
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
	mixed_ticket();
	retirement_barrier();
	pinned_admission();
	lifecycle();
	read_only_queries();
	remote_native();
	reclaim();
	atomic_interleavings();
	capacity();
	CHECK(kd_spin_entries_check_idle() == 0 && map_locks == 0);
	CHECK(mock_preempts[0] == 0 && mock_preempts[1] == 0 && !mock_irq);
	kd_spin_entries_exit();
	CHECK(!kd_spin_entries && kd_spin_entries_check_idle() == 0);
	printf("[PASS] test_spin_entry (%u checks, production single-word tickets)\n",
	       checks);
	return 0;
}
