// SPDX-License-Identifier: GPL-2.0
/* Minimal typed MM body executor. This is not an arbitrary-call/JIT ABI.
 * The immutable kernel supplies exactly one reviewed body and its origin-only
 * continuation. All participants still use the same KD physical mmap rwsem.
 * Published producers poll pinned. Only the physical owner releases the gate;
 * a borrowed origin retains that owner through its exact completion ACK.
 */
#include <linux/kd_mmap_lock.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/wait_bit.h>
#include "kd_mmap_rwsem.h"
#include "body_internal.h"

#define BODY_TAG 254
#define BODY_BATCH 256
enum body_state { BODY_WAIT, BODY_HEAD, BODY_NATIVE, BODY_ACK, BODY_DONE };
enum body_claim { BODY_PENDING, BODY_RUNNING, BODY_CANCELLED };

struct body_request {
	struct mm_struct *mm;
	struct task_struct *origin, *physical_owner;
	unsigned long start, end;
	int behavior, result;
};

static struct body_request *request(struct kd_mmap_mutex_node *node)
{
	return (void *)(unsigned long)node->rsp;
}

static struct kd_mmap_mutex_node *decode(u32 tail)
{
	return per_cpu_ptr(&kd_mmap_mutex_nodes[(tail >> KD_MMAP_MUTEX_TAIL_IDX_OFFSET) &
		KD_MMAP_MUTEX_TAIL_IDX_MASK], (tail >> KD_MMAP_MUTEX_TAIL_CPU_OFFSET) - 1);
}

/* The producer cannot retire while linked. Obtain the successor (including a
 * producer between its tail exchange and link store) before releasing this node.
 * No code may dereference a remote node after publishing BODY_DONE. */
static struct kd_mmap_mutex_node *detach(struct kd_mmap_mutex_node *node)
{
	struct kd_mmap_mutex_node *next = smp_load_acquire(&node->next);

	if (!next && cmpxchg(&node->lock->delegation_tail, node->tail, 0) != node->tail)
		while (!(next = smp_load_acquire(&node->next)))
			cpu_relax();
	WRITE_ONCE(node->next, NULL);
	return next;
}

bool kd_mmap_body_write_owned(struct kd_mmap_lock *lock)
{
	bool owned = false;
	int slot;

	/* Inspect only current's pinned live slot. A lock-wide borrowed pointer
	 * could become stale for a task that never owned that request. */
	preempt_disable();
	for (slot = 0; slot < KD_MMAP_MUTEX_MAX_NODES; slot++) {
		struct kd_mmap_mutex_node *node = this_cpu_ptr(&kd_mmap_mutex_nodes[slot]);
		struct body_request *r;

		if (READ_ONCE(node->lock) != &lock->kd.gate ||
		    READ_ONCE(node->task_struct_ptr) != current ||
		    READ_ONCE(node->entry_abi) != BODY_TAG ||
		    smp_load_acquire(&node->locked) != BODY_NATIVE)
			continue;
		r = request(node);
		owned = r->origin == current && &r->mm->mmap_lock == lock &&
			(atomic_long_read(&lock->kd.gate.owner) & ~7UL) ==
			(unsigned long)r->physical_owner;
		break;
	}
	preempt_enable();
	return owned;
}

int kd_mmap_body_enable(struct mm_struct *mm)
{
	struct kd_mmap_lock *lock = &mm->mmap_lock;
	unsigned long owner;

	if (!lock->use_kd)
		return -EOPNOTSUPP;
	/* Opt-in does not change the object's protocol or reset a sticky refusal. */
	owner = atomic_long_read(&lock->kd.gate.owner);
	if ((owner & 4UL) || (owner & ~7UL) != (unsigned long)current ||
	    atomic_long_read(&lock->kd.admission) != -1 ||
	    READ_ONCE(lock->kd.gate.delegation_tail))
		return -EBUSY;
	WRITE_ONCE(lock->body_enabled, true);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_mmap_body_enable);

unsigned int kd_mmap_body_pending(struct mm_struct *mm)
{
	unsigned int count = 0;
	int cpu, slot;

	/* Test observation only. This count neither authorizes ownership nor drain. */
	for_each_possible_cpu(cpu)
		for (slot = 0; slot < KD_MMAP_MUTEX_MAX_NODES; slot++) {
			struct kd_mmap_mutex_node *n = per_cpu_ptr(&kd_mmap_mutex_nodes[slot], cpu);
			if (READ_ONCE(n->lock) == &mm->mmap_lock.kd.gate &&
			    READ_ONCE(n->entry_abi) == BODY_TAG)
				count++;
		}
	return count;
}
EXPORT_SYMBOL_GPL(kd_mmap_body_pending);

static void execute(struct kd_mmap_mutex_node *node)
{
	struct body_request *r = request(node);
	struct kd_mmap_lock *lock = &r->mm->mmap_lock;
	bool remote = r->origin != current;
	unsigned int claim;

	BUG_ON(!kd_mmap_is_write_owner(lock));
	lock->body_calls++;
	claim = cmpxchg(&node->packet_state, BODY_PENDING, BODY_RUNNING);
	BUG_ON(claim != BODY_PENDING && claim != BODY_CANCELLED);
	if (claim == BODY_CANCELLED) {
		r->result = -EINTR;
		lock->body_cancelled++;
		return;
	}
	if (!lock->body_native_only && kd_mmap_madvise_try(r->mm, r->start, r->end,
							r->behavior, &r->result)) {
		lock->body_supported++;
		if (remote) {
			lock->body_delegated++;
			if (lock->body_delegated <= 16)
				pr_info("KD_MM_BODY done mm=%px origin=%d executor=%d start=%lx end=%lx behavior=%d result=%d\n",
					r->mm, r->origin->pid, current->pid, r->start, r->end,
					r->behavior, r->result);
		}
		return;
	}
	/* Refusal precedes every effect. The continuation starts the unmodified
	 * native walk; no committed prefix is replayed and no VMA pointer escapes. */
	WRITE_ONCE(lock->body_native_only, true);
	lock->body_native++;
	if (!remote) {
		r->result = kd_mmap_madvise_native(r->mm, r->start, r->end, r->behavior);
		return;
	}
	lock->body_handbacks++;
	r->physical_owner = current;
	smp_store_release(&node->locked, BODY_NATIVE);
	wait_var_event(&node->locked, smp_load_acquire(&node->locked) == BODY_ACK);
	/* The origin has left the native body and surrendered borrowed authority.
	 * Its slot and result remain live until this owner acknowledges retirement. */
	BUG_ON(r->physical_owner != current || !kd_mmap_is_write_owner(lock));
	lock->body_acks++;
}

static void combine(struct kd_mmap_mutex_node *head)
{
	struct body_request *r = request(head);
	struct kd_mmap_rwsem *sem = &r->mm->mmap_lock.kd;
	struct kd_mmap_mutex_node *node = head, *next;
	unsigned int count = 0;
	int error = kd_mmap_rwsem_body_lock(sem, head);

	if (error) {
		r->result = error;
		next = detach(head);
		if (next)
			smp_store_release(&next->locked, BODY_HEAD);
		return;
	}
	for (;;) {
		execute(node);
		next = detach(node);
		if (node != head)
			smp_store_release(&node->locked, BODY_DONE);
		if (!next || ++count == BODY_BATCH)
			break;
		node = next;
	}
	/* Release this exact physical acquisition before another head may acquire.
	 * The head keeps its slot/mm reference until all ACK services have ended. */
	kd_mmap_up_write(sem);
	if (next)
		smp_store_release(&next->locked, BODY_HEAD);
}

static int local(struct body_request *r)
{
	struct kd_mmap_lock *lock = &r->mm->mmap_lock;
	int error = kd_mmap_write_lock_killable(lock);

	if (error)
		return error;
	lock->body_calls++;
	if (lock->body_native_only)
		lock->body_post_ban++;
	else if (kd_mmap_madvise_try(r->mm, r->start, r->end, r->behavior, &r->result)) {
		lock->body_supported++;
		goto out;
	}
	WRITE_ONCE(lock->body_native_only, true);
	lock->body_native++;
	r->result = kd_mmap_madvise_native(r->mm, r->start, r->end, r->behavior);
out:
	kd_mmap_write_unlock(lock);
	return r->result;
}

int kd_mmap_madvise(struct mm_struct *mm, unsigned long start,
		   unsigned long end, int behavior)
{
	struct body_request r = { .mm = mm, .origin = current, .start = start,
		.end = end, .behavior = behavior };
	struct kd_mmap_mutex_node *node;
	u32 previous;
	u8 state;

	BUG_ON(!mm->mmap_lock.use_kd || !READ_ONCE(mm->mmap_lock.body_enabled));
	if (READ_ONCE(mm->mmap_lock.body_native_only))
		return local(&r);
	/* mm_users covers every VMA through the last remote result/ACK. The stack
	 * request is never copied and remains owned by this synchronous caller. */
	mmget(mm);
	migrate_disable();
	preempt_disable();
	node = kd_mmap_body_node_get(&mm->mmap_lock.kd.gate);
	if (!node) {
		preempt_enable();
		migrate_enable();
		r.result = local(&r);
		goto put;
	}
	node->next = NULL;
	node->rsp = (unsigned long)&r;
	node->tail = node->osq.tail;
	node->locked = BODY_WAIT;
	node->packet_state = BODY_PENDING;
	WRITE_ONCE(node->entry_abi, BODY_TAG);
	previous = xchg(&node->lock->delegation_tail, node->tail);
	if (previous)
		smp_store_release(&decode(previous)->next, node);
	else
		node->locked = BODY_HEAD;
	for (;;) {
		state = smp_load_acquire(&node->locked);
		if (state == BODY_DONE)
			break;
		if (state == BODY_HEAD) {
			preempt_enable();
			combine(node);
			preempt_disable();
			break;
		}
		if (state == BODY_NATIVE) {
			preempt_enable();
			BUG_ON(!kd_mmap_body_write_owned(&mm->mmap_lock));
			r.result = kd_mmap_madvise_native(mm, start, end, behavior);
			preempt_disable();
			smp_store_release(&node->locked, BODY_ACK);
			wake_up_var(&node->locked);
		} else if (fatal_signal_pending(current)) {
			/* Cancellation cannot remove a published link. The owner consumes
			 * it once, before admitting any body, and returns the exact result. */
			cmpxchg(&node->packet_state, BODY_PENDING, BODY_CANCELLED);
		}
		cpu_relax();
	}
	BUG_ON(node->next);
	node->rsp = 0;
	node->entry_abi = 0;
	kd_mmap_mutex_osq_node_put(&node->osq);
	preempt_enable();
	migrate_enable();
put:
	mmput(mm);
	return r.result;
}
