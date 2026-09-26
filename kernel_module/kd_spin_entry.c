// SPDX-License-Identifier: GPL-2.0
/* Per-acquisition origin tickets, distinct from reusable scheduling nodes.
 * Generation, phase and native borrows share one atomic word: an old remote
 * CAS cannot mutate a recycled slot. Only the pinned owner allocates/ends.
 * Native suffix borrowing ends after the real owner's final ACK/frame pop. */
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/limits.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/string.h>

#include "kd_spin_entry.h"
#include "kd_spin_fast.h"

enum kd_spin_entry_state {
	KD_ENTRY_FREE,
	KD_ENTRY_WAITING,
	KD_ENTRY_OWNED,
	KD_ENTRY_RELEASED,
	KD_ENTRY_NATIVE,
};

/* x86_64: 48-bit generation, 12-bit borrow count, immutable kind and phase.
 * The finite limits fail admission instead of wrapping into a live handle.
 * Keeping kind here lets remote borrowers inspect only this atomic word. */
#define KD_ENTRY_STATE_MASK 7UL
#define KD_ENTRY_VIRTUAL_BIT (1UL << 3)
#define KD_ENTRY_REF_SHIFT 4
#define KD_ENTRY_REF_ONE (1UL << KD_ENTRY_REF_SHIFT)
#define KD_ENTRY_REF_MAX ((1UL << 12) - 1)
#define KD_ENTRY_REF_MASK (KD_ENTRY_REF_MAX << KD_ENTRY_REF_SHIFT)
#define KD_ENTRY_SEQUENCE_SHIFT 16
#define KD_ENTRY_SEQUENCE_MAX (ULONG_MAX >> KD_ENTRY_SEQUENCE_SHIFT)
#define KD_ENTRY_LOW_MASK ((1UL << KD_ENTRY_SEQUENCE_SHIFT) - 1)

_Static_assert(KD_ENTRY_NATIVE <= KD_ENTRY_STATE_MASK,
	       "ticket phase must fit below the immutable kind bit");
_Static_assert((KD_ENTRY_STATE_MASK | KD_ENTRY_VIRTUAL_BIT | KD_ENTRY_REF_MASK) ==
	       KD_ENTRY_LOW_MASK, "ticket fields must fill the low 16 bits");

struct kd_spin_entry {
	atomic64_t control;
	struct task_struct *task;
	raw_spinlock_t *origin;
	int cpu;
};

struct kd_spin_entry_pool {
	unsigned long sequence;
	/* CPU-pinned task-only membership; remote peers never allocate/end. */
	unsigned long occupied;
	struct kd_spin_entry entries[KD_SPIN_ENTRY_SLOTS];
};

static struct kd_spin_entry_pool __percpu *kd_spin_entries;

int kd_spin_entries_init(void)
{
	int cpu;

	if (kd_spin_entries)
		return -EBUSY;
	/* Allocate the fixed pool at init, never on the lock admission stack. */
	kd_spin_entries = alloc_percpu(struct kd_spin_entry_pool);
	if (!kd_spin_entries)
		return -ENOMEM;
	for_each_possible_cpu(cpu)
		memset(per_cpu_ptr(kd_spin_entries, cpu), 0,
		       sizeof(struct kd_spin_entry_pool));
	return 0;
}

/* Called only after hook users, queue requests and borrowed frames drain. */
void kd_spin_entries_exit(void)
{
	free_percpu(kd_spin_entries);
	kd_spin_entries = NULL;
}

static __always_inline enum kd_spin_entry_state kd_entry_state(unsigned long control)
{
	return control & KD_ENTRY_STATE_MASK;
}

static __always_inline unsigned int kd_entry_refs(unsigned long control)
{
	return (control & KD_ENTRY_REF_MASK) >> KD_ENTRY_REF_SHIFT;
}

static __always_inline unsigned long
kd_entry_with_state(unsigned long control, enum kd_spin_entry_state state)
{
	return (control & ~KD_ENTRY_STATE_MASK) | state;
}

static __always_inline int kd_entry_valid(const struct kd_spin_ref *ref,
					 unsigned long control)
{
	/* Compare the complete caller generation: masking an invalid high bit
	 * would alias it onto a valid 48-bit generation. */
	return kd_entry_state(control) != KD_ENTRY_FREE &&
	       (control >> KD_ENTRY_SEQUENCE_SHIFT) == ref->sequence ? 0 : -ESTALE;
}

static __always_inline int kd_entry_local(const struct kd_spin_ref *ref,
					 unsigned long control)
{
	int ret = kd_entry_valid(ref, control);

	if (ret)
		return ret;
	if (READ_ONCE(ref->entry->cpu) != raw_smp_processor_id() ||
	    READ_ONCE(ref->entry->task) != current)
		return -EPERM;
	/* After local validation, the caller's pin prevents slot reuse across
	 * CAS retries. Only remote borrow counts can change its current tag. */
	return 0;
}

/* A successful CAS includes the generation even on a count-only update.
 * A failed CAS supplies the next snapshot without another shared load. */
static __always_inline bool kd_entry_update(struct kd_spin_entry *entry,
					   unsigned long *control,
					   unsigned long next)
{
	unsigned long before = atomic64_cmpxchg(&entry->control, *control, next);

	if (before == *control)
		return true;
	*control = before;
	return false;
}

static __always_inline bool kd_entry_pinned(void)
{
	return in_task() && (preempt_count() & PREEMPT_MASK);
}

static __always_inline bool kd_entry_ref_present(const struct kd_spin_ref *ref)
{
	return ref && ref->entry && ref->sequence;
}

/* The existing request pin protects membership and identity. Remote peers
 * update only the packed count, never recycle a slot or migrate its owner. */
static bool kd_entry_lookup(raw_spinlock_t *origin, bool native,
			    struct kd_spin_ref *ref)
{
	struct kd_spin_entry_pool *pool;
	unsigned long occupied;

	if (!kd_entry_pinned() || !kd_spin_entries)
		return false;
	pool = this_cpu_ptr(kd_spin_entries);
	for (occupied = pool->occupied; occupied; occupied &= occupied - 1) {
		struct kd_spin_entry *entry =
			&pool->entries[__builtin_ctzl(occupied)];
		unsigned long control = atomic64_read(&entry->control);

		if (kd_entry_state(control) == KD_ENTRY_FREE ||
		    entry->task != current ||
		    (origin && entry->origin != origin) ||
		    (native && kd_entry_state(control) != KD_ENTRY_NATIVE))
			continue;
		if (ref)
			*ref = (struct kd_spin_ref){
				entry, control >> KD_ENTRY_SEQUENCE_SHIFT
			};
		return true;
	}
	return false;
}

bool kd_spin_entry_find(raw_spinlock_t *origin, struct kd_spin_ref *ref)
{
	return origin && ref && kd_entry_lookup(origin, false, ref);
}

bool kd_spin_entry_task_active(void)
{
	return kd_spin_fast_active() || kd_entry_lookup(NULL, false, NULL);
}

bool kd_spin_entry_native_active(void)
{
	/* A lightweight KD root owns the physical lock but is not a native
	 * continuation. Its nested hooks still need their own tickets. */
	return kd_entry_lookup(NULL, true, NULL);
}

/* Reserve under a caller-owned pin. No peer may mutate a FREE generation;
 * the next tag is published only after its owner-local metadata is ready. */
static int kd_spin_entry_reserve(raw_spinlock_t *origin,
				enum kd_spin_entry_kind kind,
				struct kd_spin_ref *ref)
{
	struct kd_spin_entry_pool *pool;
	struct kd_spin_entry *entry;
	unsigned long occupied, available, control;
	unsigned int index;

	if (!kd_spin_entries)
		return -ENODEV;
	if (!origin || !ref || ref->entry || !in_task() ||
	    (kind != KD_SPIN_ENTRY_HOOK && kind != KD_SPIN_ENTRY_VIRTUAL))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	pool = this_cpu_ptr(kd_spin_entries);
	for (occupied = pool->occupied; occupied; occupied &= occupied - 1) {
		struct kd_spin_entry *candidate = &pool->entries[__builtin_ctzl(occupied)];

		if (candidate->task == current && candidate->origin == origin)
			return -EDEADLK;
	}
	available = ~pool->occupied & ((1UL << KD_SPIN_ENTRY_SLOTS) - 1);
	if (!available)
		return -E2BIG;
	if (pool->sequence >= KD_ENTRY_SEQUENCE_MAX)
		return -EOVERFLOW;
	index = __builtin_ctzl(available);
	entry = &pool->entries[index];
	entry->task = current;
	entry->origin = origin;
	entry->cpu = raw_smp_processor_id();
	control = (++pool->sequence << KD_ENTRY_SEQUENCE_SHIFT) | KD_ENTRY_WAITING;
	if (kind == KD_SPIN_ENTRY_VIRTUAL)
		control |= KD_ENTRY_VIRTUAL_BIT;
	pool->occupied |= 1UL << index;
	atomic64_set_release(&entry->control, control);
	*ref = (struct kd_spin_ref){ entry, pool->sequence };
	return 0;
}

int kd_spin_entry_begin(raw_spinlock_t *origin, enum kd_spin_entry_kind kind,
			struct kd_spin_ref *ref)
{
	int ret;

	preempt_disable();
	ret = kd_spin_entry_reserve(origin, kind, ref);
	if (ret)
		preempt_enable();
	return ret;
}

int kd_spin_entry_begin_pinned(raw_spinlock_t *origin,
			       struct kd_spin_ref *ref)
{
	return kd_spin_entry_reserve(origin, KD_SPIN_ENTRY_HOOK, ref);
}

kd_spinlock_t *kd_spin_entry_word(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;

	if (!kd_entry_ref_present(ref) || !kd_entry_pinned())
		return NULL;
	entry = ref->entry;
	/* A local request pin excludes identity reuse; remote native borrowers
	 * do not change these fields. Reject other CPUs before following origin. */
	if (READ_ONCE(entry->cpu) != raw_smp_processor_id() ||
	    entry->task != current || kd_entry_valid(ref, atomic64_read(&entry->control)))
		return NULL;
	return (kd_spinlock_t *)entry->origin;
}

static int kd_spin_entry_claim_from(const struct kd_spin_ref *ref,
				    enum kd_spin_entry_state from)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	for (;;) {
		if (kd_entry_state(control) == KD_ENTRY_OWNED && from == KD_ENTRY_WAITING)
			return 0;
		if (kd_entry_state(control) != from || kd_entry_refs(control))
			return -EBUSY;
		/* Physical acquisition precedes this metadata transition. The CAS
		 * excludes a racing native borrow without a separate guard word. */
		if (!READ_ONCE(((kd_spinlock_t *)entry->origin)->locked))
			return -EINVAL;
		if (kd_entry_update(entry, &control,
				    kd_entry_with_state(control, KD_ENTRY_OWNED)))
			return 0;
	}
}

int kd_spin_entry_claim(const struct kd_spin_ref *ref)
{
	return kd_spin_entry_claim_from(ref, KD_ENTRY_WAITING);
}

int kd_spin_entry_reclaim(const struct kd_spin_ref *ref)
{
	return kd_spin_entry_claim_from(ref, KD_ENTRY_RELEASED);
}

int kd_spin_entry_release_origin(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	for (;;) {
		if (kd_entry_state(control) != KD_ENTRY_OWNED)
			return -EBUSY;
		/* Metadata retirement is separate from the scheduler's physical
		 * release store and wake publication. Keep the request pin. */
		if (kd_entry_update(entry, &control,
				    kd_entry_with_state(control, KD_ENTRY_RELEASED)))
			return 0;
	}
}

int kd_spin_entry_end_pinned(struct kd_spin_ref *ref)
{
	struct kd_spin_entry_pool *pool;
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	for (;;) {
		enum kd_spin_entry_state state = kd_entry_state(control);

		if (kd_entry_refs(control) ||
		    (state != KD_ENTRY_WAITING && state != KD_ENTRY_RELEASED &&
		     state != KD_ENTRY_NATIVE))
			return -EBUSY;
		/* FREE retains the generation, rejecting any delayed old CAS.
		 * Only this pinned owner can reserve the slot after this point. */
		if (kd_entry_update(entry, &control, control & ~KD_ENTRY_LOW_MASK))
			break;
	}
	pool = this_cpu_ptr(kd_spin_entries);
	pool->occupied &= ~(1UL << (entry - pool->entries));
	entry->task = NULL;
	entry->origin = NULL;
	entry->cpu = -1;
	*ref = (struct kd_spin_ref){ 0 };
	/* The caller retains its pin until its remaining per-CPU reads finish. */
	return 0;
}

/* Ordinary C exits consume the pin here. Nonlocal packet restoration uses
 * end_pinned(), retires its record after the last load, then unpins. */
int kd_spin_entry_end(struct kd_spin_ref *ref)
{
	int ret = kd_spin_entry_end_pinned(ref);

	if (!ret)
		preempt_enable();
	return ret;
}

int kd_spin_entry_borrow_get(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	for (;;) {
		ret = kd_entry_valid(ref, control);
		if (ret)
			return ret;
		if ((control & KD_ENTRY_VIRTUAL_BIT) ||
		    kd_entry_state(control) != KD_ENTRY_WAITING)
			return -EINVAL;
		if (kd_entry_refs(control) == KD_ENTRY_REF_MAX)
			return -EOVERFLOW;
		if (kd_entry_update(entry, &control, control + KD_ENTRY_REF_ONE))
			return 0;
	}
}

int kd_spin_entry_mark_native(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	for (;;) {
		if (kd_entry_state(control) != KD_ENTRY_WAITING ||
		    (control & KD_ENTRY_VIRTUAL_BIT))
			return -EINVAL;
		/* Preserve borrows admitted before the native wake. New gets
		 * fail once this phase is published; existing puts can continue. */
		if (kd_entry_update(entry, &control,
				    kd_entry_with_state(control, KD_ENTRY_NATIVE)))
			return 0;
	}
}

int kd_spin_entry_borrow_put(const struct kd_spin_ref *ref, bool *last)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref) || !last)
		return -EINVAL;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	for (;;) {
		ret = kd_entry_valid(ref, control);
		if (ret)
			return ret;
		if (!kd_entry_refs(control) ||
		    (kd_entry_state(control) != KD_ENTRY_WAITING &&
		     kd_entry_state(control) != KD_ENTRY_NATIVE))
			return -EINVAL;
		/* The ordered CAS publishes frame retirement before the waiter
		 * observes zero. Do not touch the entry after dropping the last ref. */
		if (kd_entry_update(entry, &control, control - KD_ENTRY_REF_ONE)) {
			*last = kd_entry_refs(control) == 1;
			return 0;
		}
	}
}

/* Native ACK is distinct from frame retirement. The owner retains its pin,
 * so only borrows can change while it polls; no locked RMW is needed here. */
int kd_spin_entry_borrow_wait(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref) || !kd_entry_pinned())
		return -EINVAL;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	while (kd_entry_refs(control)) {
		cpu_relax();
		control = atomic64_read_acquire(&entry->control);
	}
	return 0;
}

/* Controlled teardown only; neither pool memory nor native frames may be live. */
int kd_spin_entries_check_idle(void)
{
	int cpu;
	unsigned int i;

	if (!kd_spin_fast_idle())
		return -EBUSY;
	if (!kd_spin_entries)
		return 0;
	for_each_possible_cpu(cpu) {
		struct kd_spin_entry_pool *pool =
			per_cpu_ptr(kd_spin_entries, cpu);

		for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++) {
			struct kd_spin_entry *entry = &pool->entries[i];
			unsigned long control = atomic64_read(&entry->control);

			if (kd_entry_state(control) != KD_ENTRY_FREE ||
			    kd_entry_refs(control) || READ_ONCE(entry->task))
				return -EBUSY;
		}
	}
	return 0;
}

/* Diagnostic snapshot only; ownership decisions use the caller's stable ref.
 * Pool storage survives all observers until provider drain. */
unsigned long kd_spin_entry_owner(raw_spinlock_t *origin)
{
	int cpu;
	unsigned int i;

	if (!kd_spin_entries)
		return 0;
	for_each_possible_cpu(cpu) {
		struct kd_spin_fast_cpu *fast = per_cpu_ptr(&kd_spin_fast_cpu, cpu);
		struct kd_spin_entry_pool *pool = per_cpu_ptr(kd_spin_entries, cpu);

		if (READ_ONCE(fast->held) == (kd_spinlock_t *)origin)
			return (unsigned long)READ_ONCE(fast->owner);
		for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++) {
			struct kd_spin_entry *entry = &pool->entries[i];

			if (READ_ONCE(entry->origin) == origin &&
			    kd_entry_state(atomic64_read(&entry->control)) == KD_ENTRY_OWNED)
				return (unsigned long)READ_ONCE(entry->task);
		}
	}
	return 0;
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/spin/spin_entry_selftest.c"
#endif
