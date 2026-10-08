/* SPDX-License-Identifier: GPL-2.0 */
/* Tail encoding and NUMA successor selection; preserve the original queue publication and native boundaries. */
#define _Q_LOCKED_PENDING_MASK (_Q_LOCKED_MASK | _Q_PENDING_MASK)
#define _Q_LOCKED_COMBINER_VAL 3
#define _Q_UNLOCKED_OOO_VAL 7 //Unlocked a lock out-of-order
#define _Q_LOCKED_IRQ_VAL 15 // Lock Stealing by IRQ
/*
 * We must be able to distinguish between no-tail and the tail at 0:0,
 * therefore increment the cpu number by one.
 */
static inline __pure u32 encode_tail(int cpu, int idx)
{
	u32 tail;

	tail = (cpu + 1) << _Q_TAIL_CPU_OFFSET;
	tail |= idx << _Q_TAIL_IDX_OFFSET; /* assume < 4 */

	return tail;
}

static inline __pure struct komb_node *decode_tail(u32 tail)
{
	int cpu = (tail >> _Q_TAIL_CPU_OFFSET) - 1;
	int idx = (tail & _Q_TAIL_IDX_MASK) >> _Q_TAIL_IDX_OFFSET;

	return per_cpu_ptr(&komb_nodes[idx], cpu);
}

inline __pure u32 get_cpu_from_tail(u32 tail)
{
	return ((tail >> _Q_TAIL_CPU_OFFSET) - 1);
}

static inline bool check_irq_node(struct komb_node *node)
{
	return (node->socket_id == IRQ_NUMA_NODE || node->rsp == 0xdeadbeef);
}

__always_inline void clear_locked_set_completed(struct komb_node *lock)
{
	WRITE_ONCE(lock->locked_completed, 1);
}

__always_inline void clear_pending_set_locked(struct qspinlock *lock)
{
#ifdef DEBUG_KOMB
	BUG_ON(lock->locked != 0);
#endif
	WRITE_ONCE(lock->locked_pending, _Q_LOCKED_VAL);
}

static __always_inline u32 xchg_tail(struct qspinlock *lock, u32 tail)
{
	return ((u32)xchg(&lock->tail, tail >> _Q_TAIL_OFFSET))
	       << _Q_TAIL_OFFSET;
}

__always_inline u32 cmpxchg_tail(struct qspinlock *lock, u32 tail, u32 new_tail)
{
	return ((u32)cmpxchg(&lock->tail, tail >> _Q_TAIL_OFFSET,
			     new_tail >> _Q_TAIL_OFFSET))
	       << _Q_TAIL_OFFSET;
}

/**
 * clear_pending - clear the pending bit.
 * @lock: Pointer to queued spinlock structure
 *
 * *,1,* -> *,0,*
 */
static __always_inline void clear_pending(struct qspinlock *lock)
{
	atomic_andnot(_Q_PENDING_VAL, &lock->val);
}

/**
 * set_locked - Set the lock bit and own the lock
 * @lock: Pointer to queued spinlock structure
 *
 * *,*,0 -> *,0,1
 */
static __always_inline void set_locked(struct qspinlock *lock)
{
	WRITE_ONCE(lock->locked, _Q_LOCKED_VAL);
}

static __always_inline void check_and_set_combiner(struct qspinlock *lock)
{
	u32 val, new_val;

#ifdef DEBUG_KOMB
	BUG_ON(lock->locked == _Q_LOCKED_VAL);
#endif

	if (lock->locked > 0) {
		while (true) {
			val = atomic_cond_read_relaxed(
				&lock->val, !(VAL & _Q_LOCKED_PENDING_MASK));

#ifdef DEBUG_KOMB
			BUG_ON(lock->locked != 0);
#endif

			new_val = val >> _Q_LOCKED_BITS;
			new_val <<= _Q_LOCKED_BITS;
			new_val |= _Q_LOCKED_COMBINER_VAL;

			if (atomic_cmpxchg_acquire(&lock->val, val, new_val) ==
			    val)
				return;
		}
	}
	WRITE_ONCE(lock->locked, _Q_LOCKED_COMBINER_VAL);
}

/**
 * komb_fetch_set_pending_acquire - fetch the whole lock value and set pending
 * @lock : Pointer to queued spinlock structure
 * Return: The previous lock value
 *
 * *,*,* -> *,1,*
 */
static __always_inline u32 komb_fetch_set_pending_acquire(struct qspinlock *lock)
{
	return atomic_fetch_or_acquire(_Q_PENDING_VAL, &lock->val);
}

#ifdef NUMA_AWARE
__always_inline static void add_to_local_queue(struct komb_node *node)
{
	//printk(KERN_ALERT "%d Move node to local queue: %d\n",
	//     smp_processor_id(), node->cpuid);

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

__always_inline static struct komb_node *
get_next_node(struct komb_node *my_node)
{
#ifdef NUMA_AWARE
	struct komb_node *curr_node, *next_node;

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
			void *rsp_ptr =
				(void *)(unsigned long)(per_cpu_ptr(&komb_nodes[0], next_node->cpuid)
					 ->rsp);
			prefetchw(rsp_ptr);
			int i;
			for (i = 1; i < NUM_PREFETCH_LINES; i++)
				prefetchw(rsp_ptr + (64 * i));

			prefetch(next_node->next);
#endif
			return next_node;
		}

		add_to_local_queue(next_node);
		curr_node = next_node;
		next_node = curr_node->next;
	}

next_node_null:
	return next_node;
#else
	return my_node->next;
#endif
}
