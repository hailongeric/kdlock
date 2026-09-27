// SPDX-License-Identifier: GPL-2.0
/* Private ticket pool, packed generation/phase/borrow control word and
 * shared validation/CAS helpers. Allocation is initialization-only. */

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
