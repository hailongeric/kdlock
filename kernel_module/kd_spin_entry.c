// SPDX-License-Identifier: GPL-2.0
/* Per-acquisition origin tickets, distinct from reusable scheduling nodes.
 * Generation checks prevent a stale ref from addressing a recycled ticket.
 * Hook and virtual nested requests retain their own task/CPU/native-L lifetime;
 * native suffix borrowing ends only after the real owner's final ACK. */
#include <linux/errno.h>
#include <linux/limits.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/string.h>

#include "kd_spin_entry.h"

enum kd_spin_entry_state {
	KD_ENTRY_FREE,
	KD_ENTRY_WAITING,
	KD_ENTRY_CLAIMING,
	KD_ENTRY_OWNED,
	KD_ENTRY_RELEASING,
	KD_ENTRY_RELEASED,
	KD_ENTRY_NATIVE,
};

struct kd_spin_entry {
	raw_spinlock_t guard;
	struct task_struct *task;
	raw_spinlock_t *origin;
	struct kd_spin_gate *gate;
	struct kd_spin_hold hold;
	unsigned long sequence;
	unsigned int native_refs;
	enum kd_spin_entry_kind kind;
	enum kd_spin_entry_state state;
	int cpu;
};

struct kd_spin_entry_pool {
	unsigned long sequence;
	struct kd_spin_entry entries[KD_SPIN_ENTRY_SLOTS];
};

static struct kd_spin_entry_pool __percpu *kd_spin_entries;

/* Allocate and initialize the per-CPU origin ticket pool.
 * No memory allocation is allowed while holding a lock admission stack.
 */
int kd_spin_entries_init(void)
{
	int cpu;
	unsigned int i;

	if (kd_spin_entries)
		return -EBUSY;
	/* Large static per-CPU objects consume the module reserved chunk. Allocate
	 * the fixed pool once at init instead, never in a lock acquisition path.
	 */
	kd_spin_entries = alloc_percpu(struct kd_spin_entry_pool);
	if (!kd_spin_entries)
		return -ENOMEM;
	for_each_possible_cpu(cpu) {
		struct kd_spin_entry_pool *pool =
			per_cpu_ptr(kd_spin_entries, cpu);

		memset(pool, 0, sizeof(*pool));
		for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++)
			raw_spin_lock_init(&pool->entries[i].guard);
	}
	return 0;
}

/* Called only after hook users, queue requests and borrowed frames drain. */
void kd_spin_entries_exit(void)
{
	free_percpu(kd_spin_entries);
	kd_spin_entries = NULL;
}

static int kd_entry_valid(const struct kd_spin_ref *ref)
{
	return ref->entry->state != KD_ENTRY_FREE &&
			       ref->entry->sequence == ref->sequence ?
		       0 :
		       -ESTALE;
}

static int kd_entry_local(const struct kd_spin_ref *ref)
{
	int ret = kd_entry_valid(ref);

	if (ret)
		return ret;
	if (ref->entry->task != current ||
	    ref->entry->cpu != raw_smp_processor_id())
		return -EPERM;
	return 0;
}

/* Check before taking guard: its own preemption pin cannot stand in for the
 * request pin which end() consumes after dropping guard.
 */
static bool kd_entry_pinned(void)
{
	return in_task() && (preempt_count() & PREEMPT_MASK);
}

static bool kd_entry_ref_present(const struct kd_spin_ref *ref)
{
	return ref && ref->entry && ref->sequence;
}

/* Only the pinned task changes slot membership/state. Remote executors may
 * change native_refs under guard, but never recycle a slot or migrate its task.
 */
static bool kd_entry_lookup(raw_spinlock_t *origin, bool native,
			    struct kd_spin_ref *ref)
{
	struct kd_spin_entry_pool *pool;
	unsigned int i;
	bool found = false;

	if (!kd_spin_entries || !in_task())
		return false;
	preempt_disable();
	pool = this_cpu_ptr(kd_spin_entries);
	for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++) {
		struct kd_spin_entry *entry = &pool->entries[i];

		if (READ_ONCE(entry->state) == KD_ENTRY_FREE ||
		    entry->task != current ||
		    (origin && entry->origin != origin) ||
		    (native && entry->state != KD_ENTRY_NATIVE))
			continue;
		if (ref)
			*ref = (struct kd_spin_ref){ entry, entry->sequence };
		found = true;
		break;
	}
	preempt_enable();
	return found;
}

bool kd_spin_entry_find(raw_spinlock_t *origin, struct kd_spin_ref *ref)
{
	return origin && ref && kd_entry_lookup(origin, false, ref);
}

bool kd_spin_entry_task_active(void)
{
	return kd_entry_lookup(NULL, false, NULL);
}

bool kd_spin_entry_native_active(void)
{
	return kd_entry_lookup(NULL, true, NULL);
}

/* Reserve a new ticket for hook/native caller; this is the admission checkpoint
 * before touching lock-specific gate state.
 */
int kd_spin_entry_begin(raw_spinlock_t *origin, enum kd_spin_entry_kind kind,
			struct kd_spin_ref *ref)
{
	struct kd_spin_entry_pool *pool;
	struct kd_spin_entry *entry = NULL;
	struct kd_spin_gate *gate;
	unsigned long flags;
	unsigned int i;
	int ret = -E2BIG;

	if (!kd_spin_entries)
		return -ENODEV;
	if (!origin || !ref || ref->entry || !in_task() || irqs_disabled() ||
	    (kind != KD_SPIN_ENTRY_HOOK && kind != KD_SPIN_ENTRY_VIRTUAL))
		return -EINVAL;
	preempt_disable();
	pool = this_cpu_ptr(kd_spin_entries);
	for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++) {
		struct kd_spin_entry *candidate = &pool->entries[i];

		if (candidate->state == KD_ENTRY_FREE) {
			if (!entry)
				entry = candidate;
		} else if (candidate->task == current &&
			   candidate->origin == origin) {
			ret = -EDEADLK;
			goto fail;
		}
	}
	if (!entry)
		goto fail;
	if (pool->sequence == ULONG_MAX) {
		ret = -EOVERFLOW;
		goto fail;
	}
	gate = kd_spin_gate_get(origin);
	if (!gate) {
		ret = -ENOMEM;
		goto fail;
	}
	/* Keep guard initialized for stale remote handles even after slot reuse. */
	raw_spin_lock_irqsave(&entry->guard, flags);
	entry->task = current;
	entry->origin = origin;
	entry->gate = gate;
	entry->hold = (struct kd_spin_hold){ 0 };
	entry->sequence = ++pool->sequence;
	entry->native_refs = 0;
	entry->kind = kind;
	entry->cpu = raw_smp_processor_id();
	WRITE_ONCE(entry->state, KD_ENTRY_WAITING);
	*ref = (struct kd_spin_ref){ entry, entry->sequence };
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	return 0;
fail:
	preempt_enable();
	return ret;
}

struct kd_spin_gate *kd_spin_entry_gate(const struct kd_spin_ref *ref)
{
	struct kd_spin_gate *gate = NULL;
	unsigned long flags;

	if (!kd_entry_ref_present(ref))
		return NULL;
	if (!kd_entry_pinned())
		return NULL;
	raw_spin_lock_irqsave(&ref->entry->guard, flags);
	if (!kd_entry_local(ref))
		gate = ref->entry->gate;
	raw_spin_unlock_irqrestore(&ref->entry->guard, flags);
	return gate;
}

static int kd_spin_entry_claim_from(const struct kd_spin_ref *ref,
				    enum kd_spin_entry_state from)
{
	struct kd_spin_entry *entry;
	unsigned long flags;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	raw_spin_lock_irqsave(&entry->guard, flags);
	ret = kd_entry_local(ref);
	if (ret || (entry->state == KD_ENTRY_OWNED && from == KD_ENTRY_WAITING))
		goto out;
	if (entry->state != from || entry->native_refs) {
		ret = -EBUSY;
		goto out;
	}
	entry->state = KD_ENTRY_CLAIMING;
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	/* Never wait on L under the ticket guard. */
	ret = kd_spin_gate_claim(entry->gate, &entry->hold);
	raw_spin_lock_irqsave(&entry->guard, flags);
	entry->state = ret ? from : KD_ENTRY_OWNED;
out:
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	return ret;
}

int kd_spin_entry_claim(const struct kd_spin_ref *ref)
{
	return kd_spin_entry_claim_from(ref, KD_ENTRY_WAITING);
}

/* Reclaim a released native/origin reference; used when original owner handed
 * back delegated ownership and now needs to continue local execution.
 */
int kd_spin_entry_reclaim(const struct kd_spin_ref *ref)
{
	return kd_spin_entry_claim_from(ref, KD_ENTRY_RELEASED);
}

/* Release the physical origin lock ownership but keep the slot alive for potential
 * follow-up state transitions and diagnostics.
 */
int kd_spin_entry_release_origin(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long flags;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	raw_spin_lock_irqsave(&entry->guard, flags);
	ret = kd_entry_local(ref);
	if (ret)
		goto out;
	if (entry->state != KD_ENTRY_OWNED) {
		ret = -EBUSY;
		goto out;
	}
	entry->state = KD_ENTRY_RELEASING;
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	ret = kd_spin_gate_release(&entry->hold);
	raw_spin_lock_irqsave(&entry->guard, flags);
	entry->state = ret ? KD_ENTRY_OWNED : KD_ENTRY_RELEASED;
out:
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	return ret;
}

/* Finalize the lifecycle. The caller must be on the pinned local CPU and no
 * other protocol participants can still reference this ref.
 */
int kd_spin_entry_end(struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long flags;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	raw_spin_lock_irqsave(&entry->guard, flags);
	ret = kd_entry_local(ref);
	if (ret)
		goto out;
	if (entry->native_refs || entry->hold.gate ||
	    (entry->state != KD_ENTRY_WAITING &&
	     entry->state != KD_ENTRY_RELEASED &&
	     entry->state != KD_ENTRY_NATIVE)) {
		ret = -EBUSY;
		goto out;
	}
	entry->task = NULL;
	entry->origin = NULL;
	entry->gate = NULL;
	entry->cpu = -1;
	WRITE_ONCE(entry->state, KD_ENTRY_FREE);
	*ref = (struct kd_spin_ref){ 0 };
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	/* Last access to ref/entry: scheduling may reuse this CPU's pool. */
	preempt_enable();
	return 0;
out:
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	return ret;
}

int kd_spin_entry_borrow_get(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long flags;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	entry = ref->entry;
	raw_spin_lock_irqsave(&entry->guard, flags);
	ret = kd_entry_valid(ref);
	if (ret)
		goto out;
	if (entry->kind != KD_SPIN_ENTRY_HOOK ||
	    entry->state != KD_ENTRY_WAITING)
		ret = -EINVAL;
	else if (entry->native_refs == UINT_MAX)
		ret = -EOVERFLOW;
	else
		entry->native_refs++;
out:
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	return ret;
}

int kd_spin_entry_mark_native(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long flags;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	raw_spin_lock_irqsave(&entry->guard, flags);
	ret = kd_entry_local(ref);
	if (ret)
		goto out;
	if (entry->state != KD_ENTRY_WAITING ||
	    entry->kind != KD_SPIN_ENTRY_HOOK || !entry->native_refs)
		ret = -EINVAL;
	else
		entry->state = KD_ENTRY_NATIVE;
out:
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	return ret;
}

int kd_spin_entry_borrow_put(const struct kd_spin_ref *ref, bool *last)
{
	struct kd_spin_entry *entry;
	unsigned long flags;
	int ret;

	if (!kd_entry_ref_present(ref) || !last)
		return -EINVAL;
	entry = ref->entry;
	raw_spin_lock_irqsave(&entry->guard, flags);
	ret = kd_entry_valid(ref);
	if (ret)
		goto out;
	if (!entry->native_refs || (entry->state != KD_ENTRY_WAITING &&
				    entry->state != KD_ENTRY_NATIVE))
		ret = -EINVAL;
	else
		*last = --entry->native_refs == 0;
out:
	raw_spin_unlock_irqrestore(&entry->guard, flags);
	return ret;
}

/* Controlled teardown only; neither pool memory nor native frames may be live. */
int kd_spin_entries_check_idle(void)
{
	int cpu;
	unsigned int i;

	if (!kd_spin_entries)
		return 0;
	for_each_possible_cpu(cpu) {
		struct kd_spin_entry_pool *pool =
			per_cpu_ptr(kd_spin_entries, cpu);

		for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++) {
			struct kd_spin_entry *entry = &pool->entries[i];

			if (READ_ONCE(entry->state) != KD_ENTRY_FREE ||
			    READ_ONCE(entry->native_refs) ||
			    READ_ONCE(entry->task) ||
			    READ_ONCE(entry->hold.gate))
				return -EBUSY;
		}
	}
	return 0;
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/spin_entry_selftest.c"
#endif
