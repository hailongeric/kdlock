// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Tail encoding, node publication and optional NUMA successor selection.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/*
 * We must be able to distinguish between no-tail and the tail at 0:0,
 * therefore increment the cpu number by one.
 */
static inline u32 encode_tail(int cpu, int idx)
{
	u32 tail;

	tail = (cpu + 1) << _Q_TAIL_CPU_OFFSET_HL;
	tail |= idx << _Q_TAIL_IDX_OFFSET_HL; /* assume < 4 */

	return tail;
}

static inline struct kd_spin_node *decode_tail(u32 tail)
{
	int cpu = (tail >> _Q_TAIL_CPU_OFFSET_HL) - 1;
	int idx = (tail & _Q_TAIL_IDX_MASK_HL) >> _Q_TAIL_IDX_OFFSET_HL;

	return per_cpu_ptr(&kd_spin_nodes[idx], cpu);
}

static __always_inline void kd_spin_set_resume_node(struct kd_spin_node *node)
{
	WRITE_ONCE(*this_cpu_ptr(&kd_spin_resume_nodes), node);
}

static inline bool check_irq_node(struct kd_spin_node *node)
{
	return (node->socket_id == IRQ_NUMA_NODE || node->rsp == 0xdeadbeef);
}

static __always_inline void
clear_locked_set_completed(struct kd_spin_node *lock)
{
	/* On x86 this word sets completed and clears locked together. Publish
	 * the final register packet before the waiter can consume/reuse it. */
	smp_store_release(&lock->locked_completed, 1);
}

static __always_inline void clear_pending_set_locked(struct qspinlock *word)
{
#ifdef DEBUG_KD_SPIN
	BUG_ON(word->locked != 0);
#endif
	WRITE_ONCE(word->locked_pending, _Q_LOCKED_VAL_HL);
}

static __always_inline u32 xchg_tail(struct qspinlock *word, u32 tail)
{
	/* Count each actual MCS publication once, for both cold native and hot
	 * delegated producers. Fast/pending success and node-exhaustion polling
	 * never reach this boundary. Raw accounting is independent of queue depth;
	 * a native queue head can later veto admission without recounting. */
	if (kd_spin_delegate)
		kd_hotlock_record_spin_mcs_pinned();
	return ((u32)xchg(&word->tail, tail >> _Q_TAIL_OFFSET_HL))
	       << _Q_TAIL_OFFSET_HL;
}

/**
 * clear_pending - clear the pending bit.
 * @word: The single KD exclusion/scheduling word
 *
 * *,1,* -> *,0,*
 */
static __always_inline void clear_pending(struct qspinlock *word)
{
	atomic_andnot(_Q_PENDING_VAL_HL, &word->val);
}

/**
 * set_locked - Set the lock bit and own the lock
 * @word: The single KD exclusion/scheduling word
 *
 * *,*,0 -> *,0,1
 */
static __always_inline void set_locked(struct qspinlock *word)
{
	WRITE_ONCE(word->locked, _Q_LOCKED_VAL_HL);
}

static __always_inline void check_and_set_combiner(struct qspinlock *word)
{
	u32 val, new_val;

#ifdef DEBUG_KD_SPIN
	BUG_ON(word->locked == _Q_LOCKED_VAL_HL);
#endif

	if (word->locked > 0) {
		while (true) {
			val = atomic_cond_read_relaxed(
				&word->val, !(VAL & _Q_LOCKED_PENDING_MASK));

#ifdef DEBUG_KD_SPIN
			BUG_ON(word->locked != 0);
#endif

			new_val = val >> _Q_LOCKED_BITS_HL;
			new_val <<= _Q_LOCKED_BITS_HL;
			new_val |= _Q_LOCKED_COMBINER_VAL;

			if (atomic_cmpxchg_acquire(&word->val, val, new_val) ==
			    val)
				return;
		}
	}
	WRITE_ONCE(word->locked, _Q_LOCKED_COMBINER_VAL);
}

/**
 * kd_spin_fetch_set_pending_acquire - fetch lock value and set pending
 * @word : Private scheduling word S
 * Return: The previous lock value
 *
 * *,*,* -> *,1,*
 */
static __always_inline u32
kd_spin_fetch_set_pending_acquire(struct qspinlock *word)
{
	return atomic_fetch_or_acquire(_Q_PENDING_VAL_HL, &word->val);
}

/* Called only at initial batch entry, while this executor owns S/L and before
 * any NUMA splicing. A producer publishes tail before linking prev->next.
 * A different nonzero tail therefore proves a successor exists: wait for its
 * release publication instead of mistaking that window for the final waiter.
 * No wait is allowed for an actual tail node, or a detached deferred list. */
static struct kd_spin_node *kd_spin_linked_successor(struct qspinlock *word,
						    struct kd_spin_node *node)
{
	struct kd_spin_node *next = smp_load_acquire(&node->next);

	if (!next) {
		u32 tail = atomic_read_acquire(&word->val) & _Q_TAIL_MASK_HL;

		if (tail && decode_tail(tail) != node) {
			smp_cond_load_relaxed_sched(&node->next, VAL);
			next = smp_load_acquire(&node->next);
		}
	}
	return next;
}

#ifdef NUMA_AWARE
__always_inline static void add_to_local_queue(struct kd_spin_node *node)
{
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);

	if (ptr->local_queue_head == NULL) {
		ptr->local_queue_head = node;
		ptr->local_queue_tail = node;
	} else {
		ptr->local_queue_tail->next = node;
		ptr->local_queue_tail = node;
	}
}
#endif

__always_inline static struct kd_spin_node *
get_next_node(struct kd_spin_node *my_node)
{
#ifdef NUMA_AWARE
	struct kd_spin_node *curr_node, *next_node;

	curr_node = my_node;
	next_node = curr_node->next;

	while (true) {
		if (next_node == NULL || next_node->next == NULL)
			goto next_node_null;
		else if (check_irq_node(next_node) ||
			 check_irq_node(next_node->next))
			goto next_node_null;

		if (next_node->socket_id == numa_node_id()) {
			return next_node;
		}

		add_to_local_queue(next_node);
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_defer(my_node, next_node);
#endif
		curr_node = next_node;
		next_node = curr_node->next;
	}

next_node_null:
	return next_node;
#else
	return my_node->next;
#endif
}

#define get_rsp_from_regs(name, regs, i) ((unsigned long *)regs)[i]

/* Decode the physical hook packet on its originating CPU before publication.
 * After publication the waiter lends its C stack and only polls locked; JIT
 * may update node->execution->frame.regs_ref in place until the release wake. Caller-saved values
 * keep the existing hook ABI; this is the saved callee-register/return frame. */
static void kd_spin_prepare_regs(struct kd_spin_node *node)
{
	const unsigned long *saved = (const unsigned long *)node->execution->frame.regs_ref->sp;

	node->execution->frame.regs_ref->bx = saved[1];
	node->execution->frame.regs_ref->r12 = saved[2];
	node->execution->frame.regs_ref->r13 = saved[3];
	node->execution->frame.regs_ref->r14 = saved[4];
	node->execution->frame.regs_ref->r15 = saved[5];
	node->execution->frame.regs_ref->bp = saved[6];
	node->execution->frame.regs_ref->ip = saved[7];
	node->execution->frame.regs_ref->sp = (unsigned long)(saved + 8);
	node->execution->native_regs_decoded = true;
}
