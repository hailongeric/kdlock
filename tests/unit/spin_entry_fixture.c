/* SPDX-License-Identifier: GPL-2.0 */
#include "spin_gate_mock.h"

static bool mock_alloc_fail;
#define alloc_percpu(type) (mock_alloc_fail ? NULL : calloc(2, sizeof(type)))
#define free_percpu(p) free(p)

#include "entry_production.h"

static raw_spinlock_t locks[KD_SPIN_GATE_SLOTS + 1];

static void select_cpu(unsigned int cpu)
{
	CHECK(!mock_irq);
	mock_cpu = cpu;
	current = &tasks[cpu];
}

static void lifecycle(void)
{
	struct kd_spin_ref ref = { 0 }, other = { 0 }, stale, found = { 0 };
	struct kd_spin_gate *gate;
	bool last = false;

	CHECK(kd_spin_entries_check_idle() == 0);
	CHECK(!kd_spin_entry_task_active() && !kd_spin_entry_native_active());
	CHECK(kd_spin_entry_begin(NULL, KD_SPIN_ENTRY_HOOK, &ref) == -EINVAL);
	mock_irq = true;
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) ==
	      -EINVAL);
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
	CHECK(kd_spin_entry_gate(&ref) == NULL);
	CHECK(kd_spin_entry_claim(&ref) == -EPERM);
	CHECK(kd_spin_entry_release_origin(&ref) == -EPERM);
	CHECK(kd_spin_entry_mark_native(&ref) == -EPERM);
	CHECK(kd_spin_entry_end(&ref) == -EPERM);
	CHECK(mock_preempt == 0 && ref.entry);
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
	gate = kd_spin_entry_gate(&ref);
	CHECK(gate && kd_spin_entry_claim(&ref) == -EINVAL);
	gate->word.locked = 1;
	CHECK(kd_spin_entry_claim(&ref) == 0);
	CHECK(kd_spin_entry_claim(&ref) == 0 && native_claims == 1);
	CHECK(kd_spin_entry_end(&ref) == -EBUSY && locks[0].held);
	CHECK(kd_spin_entry_borrow_get(&ref) == -EINVAL);
	CHECK(kd_spin_entry_release_origin(&ref) == 0);
	CHECK(!locks[0].held && gate->word.locked == 1 && mock_preempt == 1);
	CHECK(kd_spin_entry_release_origin(&ref) == -EBUSY);
	gate->word.val.counter = 0;
	stale = ref;
	CHECK(kd_spin_entry_end(&ref) == 0 && !ref.entry && mock_preempt == 0);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_VIRTUAL, &ref) == 0);
	CHECK(ref.entry == stale.entry && ref.sequence != stale.sequence);
	CHECK(kd_spin_entry_end(&stale) == -ESTALE);
	CHECK(kd_spin_entry_borrow_get(&stale) == -ESTALE);
	CHECK(kd_spin_entry_borrow_put(&stale, &last) == -ESTALE);
	CHECK(kd_spin_entry_borrow_get(&ref) == -EINVAL);
	CHECK(kd_spin_entry_mark_native(&ref) == -EINVAL);
	CHECK(kd_spin_entry_end(&ref) == 0);
}

static void remote_native(void)
{
	struct kd_spin_ref waiter = { 0 }, a = { 0 }, b = { 0 };
	struct kd_spin_gate *ag, *bg;
	bool last = true;

	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &a) == 0);
	CHECK(kd_spin_entry_begin(&locks[1], KD_SPIN_ENTRY_VIRTUAL, &b) == 0);
	ag = kd_spin_entry_gate(&a);
	bg = kd_spin_entry_gate(&b);
	ag->word.locked = bg->word.locked = 1;
	CHECK(kd_spin_entry_claim(&a) == 0 && kd_spin_entry_claim(&b) == 0);
	CHECK(mock_preempt == 2 && locks[0].held && locks[1].held);
	select_cpu(1);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &waiter) == 0);
	CHECK(mock_preempt == 1 &&
	      kd_spin_entry_mark_native(&waiter) == -EINVAL);
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
	ag->word.val.counter = 0;
	CHECK(kd_spin_entry_end(&a) == 0 && mock_preempt == 1);
	CHECK(kd_spin_entry_borrow_put(&waiter, &last) == 0 && !last);
	select_cpu(1);
	CHECK(mock_preempt == 1 && kd_spin_entry_native_active());
	CHECK(!locks[0].held && locks[1].held);
	CHECK(kd_spin_entry_end(&waiter) == -EBUSY);
	select_cpu(0);
	CHECK(kd_spin_entry_release_origin(&b) == 0);
	bg->word.val.counter = 0;
	CHECK(kd_spin_entry_end(&b) == 0 && mock_preempt == 0);
	CHECK(kd_spin_entry_borrow_put(&waiter, &last) == 0 && last);
	CHECK(mock_preempt == 0 && mock_preempts[1] == 1);
	CHECK(kd_spin_entry_borrow_put(&waiter, &last) == -EINVAL);
	select_cpu(1);
	CHECK(kd_spin_entry_end(&waiter) == 0 && mock_preempt == 0);
	CHECK(!kd_spin_entry_native_active() && !kd_spin_entry_task_active());
	select_cpu(0);
}

static void reclaim(void)
{
	struct kd_spin_ref ref = { 0 }, stale;
	struct kd_spin_gate *gate;
	unsigned int claims = native_claims, releases = native_releases;
	unsigned long generation;

	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) == 0);
	gate = kd_spin_entry_gate(&ref);
	gate->word.locked = 1;
	CHECK(kd_spin_entry_reclaim(&ref) == -EBUSY);
	CHECK(kd_spin_entry_claim(&ref) == 0);
	CHECK(kd_spin_entry_reclaim(&ref) == -EBUSY);
	generation = gate->generation;
	CHECK(kd_spin_entry_release_origin(&ref) == 0);
	CHECK(kd_spin_entry_claim(&ref) == -EBUSY);
	CHECK(mock_preempt == 1 && !ref.entry->hold.gate);
	mock_preempt = 0;
	CHECK(kd_spin_entry_reclaim(&ref) == -EPERM);
	mock_preempt = 1;
	current = &tasks[1];
	CHECK(kd_spin_entry_reclaim(&ref) == -EPERM);
	current = &tasks[0];
	select_cpu(1);
	mock_preempt = 1;
	current = &tasks[0];
	CHECK(kd_spin_entry_reclaim(&ref) == -EPERM);
	mock_preempt = 0;
	select_cpu(0);
	gate->word.locked = 0;
	CHECK(kd_spin_entry_reclaim(&ref) == -EINVAL);
	CHECK(ref.entry->state == KD_ENTRY_RELEASED);
	gate->word.locked = 1;
	gate->owner = &tasks[1];
	CHECK(kd_spin_entry_reclaim(&ref) == -EBUSY);
	CHECK(ref.entry->state == KD_ENTRY_RELEASED);
	gate->owner = NULL;
	ref.entry->native_refs = 1;
	CHECK(kd_spin_entry_reclaim(&ref) == -EBUSY);
	ref.entry->native_refs = 0;
	CHECK(kd_spin_entry_reclaim(&ref) == 0);
	CHECK(mock_preempt == 1 && gate->held && locks[0].held);
	CHECK(gate->generation == generation + 1);
	CHECK(ref.entry->hold.owner == current);
	CHECK(kd_spin_entry_release_origin(&ref) == 0);
	gate->word.val.counter = 0;
	stale = ref;
	CHECK(kd_spin_entry_end(&ref) == 0 && mock_preempt == 0);
	CHECK(kd_spin_entry_begin(&locks[0], KD_SPIN_ENTRY_HOOK, &ref) == 0);
	CHECK(ref.entry == stale.entry && ref.sequence != stale.sequence);
	CHECK(kd_spin_entry_reclaim(&stale) == -ESTALE);
	CHECK(kd_spin_entry_end(&ref) == 0 && mock_preempt == 0);
	CHECK(native_claims == claims + 2 && native_releases == releases + 2);
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
	select_cpu(1);
	for (unsigned int i = 0; i < KD_SPIN_GATE_SLOTS; i++)
		CHECK(kd_spin_gate_get(&locks[i]));
	CHECK(kd_spin_entry_begin(&locks[KD_SPIN_GATE_SLOTS],
				  KD_SPIN_ENTRY_HOOK, &extra) == -ENOMEM);
	CHECK(mock_preempt == 0 && !extra.entry);
	select_cpu(0);
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
	lifecycle();
	remote_native();
	reclaim();
	capacity();
	CHECK(kd_spin_entries_check_idle() == 0 &&
	      kd_spin_gates_check_idle() == 0);
	CHECK(native_claims == 5 && native_releases == 5);
	CHECK(mock_preempts[0] == 0 && mock_preempts[1] == 0 && !mock_irq);
	kd_spin_entries_exit();
	CHECK(!kd_spin_entries && kd_spin_entries_check_idle() == 0);
	printf("[PASS] test_spin_entry (%u checks, production tickets/gates)\n",
	       checks);
	return 0;
}
