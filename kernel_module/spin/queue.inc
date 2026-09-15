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

static __always_inline void clear_pending_set_locked(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
#ifdef DEBUG_KD_SPIN
	BUG_ON(word->locked != 0);
#endif
	WRITE_ONCE(word->locked_pending, _Q_LOCKED_VAL_HL);
}

static __always_inline u32 xchg_tail(struct qspinlock *lock, u32 tail)
{
	struct qspinlock *word = kd_spin_word(lock);
	return ((u32)xchg(&word->tail, tail >> _Q_TAIL_OFFSET_HL))
	       << _Q_TAIL_OFFSET_HL;
}

/**
 * clear_pending - clear the pending bit.
 * @lock: Pointer to queued spinlock structure
 *
 * *,1,* -> *,0,*
 */
static __always_inline void clear_pending(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	atomic_andnot(_Q_PENDING_VAL_HL, &word->val);
}

/**
 * set_locked - Set the lock bit and own the lock
 * @lock: Pointer to queued spinlock structure
 *
 * *,*,0 -> *,0,1
 */
static __always_inline void set_locked(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	WRITE_ONCE(word->locked, _Q_LOCKED_VAL_HL);
}

static __always_inline void check_and_set_combiner(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
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
 * @lock : Pointer to queued spinlock structure
 * Return: The previous lock value
 *
 * *,*,* -> *,1,*
 */
static __always_inline u32
kd_spin_fetch_set_pending_acquire(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	return atomic_fetch_or_acquire(_Q_PENDING_VAL_HL, &word->val);
}

#ifdef NUMA_AWARE
__always_inline static void add_to_local_queue(struct kd_spin_node *node)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

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
#ifdef PREFETCHING
			void *rsp_ptr = (per_cpu_ptr(&kd_spin_nodes[0],
						     next_node->cpuid)
						 ->rsp);
			prefetchw(rsp_ptr);
			int i;
			for (i = 1; i < KD_SPIN_NUM_PREFETCH_LINES; i++)
				prefetchw(rsp_ptr + (64 * i));

			prefetch(next_node->next);
#endif
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
