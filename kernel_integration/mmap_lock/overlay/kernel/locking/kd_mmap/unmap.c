// SPDX-License-Identifier: GPL-2.0
/* Fixed whole-VMA munmap requests. The original caller prepares allocations;
 * the combiner owns one actual mmap writer acquisition. Native continuation
 * begins only after refusal ACK and queue/slot retirement, so it may acquire,
 * downgrade and release its own mmap lock without borrowing another owner. */
#include <linux/kd_mmap_lock.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/wait_bit.h>
#include "kd_mmap_rwsem.h"
#include "body_internal.h"

#define UNMAP_TAG 252
#define UNMAP_BATCH 256
enum unmap_state { UNMAP_WAIT, UNMAP_HEAD, UNMAP_NATIVE, UNMAP_ACK, UNMAP_DONE };
enum unmap_claim { UNMAP_PENDING, UNMAP_RUNNING, UNMAP_CANCELLED };
struct unmap_request {
	struct mm_struct *mm;
	struct task_struct *origin, *physical_owner;
	struct ma_state *live, *reserve;
	unsigned long start, end;
	u64 id;
	int result;
	bool handled;
};

void kd_mmap_unmap_init(struct kd_mmap_lock *lock)
{
	struct kd_mmap_unmap_state *u = &lock->unmap;

	u->tail = 0;
	u->start = u->end = 0;
	u->enabled = u->native_only = false;
	u->allow_populated = false;
	u->allow_partial = false;
	u->test_fail_after = u->test_fail_seen = 0;
	atomic64_set(&u->calls, 0);
	atomic64_set(&u->removed, 0);
	atomic64_set(&u->delegated, 0);
	atomic64_set(&u->native, 0);
	atomic64_set(&u->post_ban, 0);
	atomic64_set(&u->handbacks, 0);
	atomic64_set(&u->acks, 0);
	atomic64_set(&u->cancelled, 0);
	atomic64_set(&u->refused, 0);
	atomic64_set(&u->failed, 0);
	atomic64_set(&u->populated, 0);
	atomic64_set(&u->populated_remote, 0);
}

static int enable(struct mm_struct *mm, unsigned long start, unsigned long end,
		  bool populated, bool partial)
{
	struct kd_mmap_lock *lock = &mm->mmap_lock;
	unsigned long owner;

	if (!lock->use_kd || !start || end <= start || ((start | end) & ~PAGE_MASK))
		return -EINVAL;
	owner = atomic_long_read(&lock->kd.gate.owner);
	if ((owner & 4UL) || (owner & ~7UL) != (unsigned long)current ||
	    atomic_long_read(&lock->kd.admission) != -1 || lock->unmap.enabled ||
	    READ_ONCE(lock->unmap.tail))
		return -EBUSY;
	lock->unmap.start = start;
	lock->unmap.end = end;
	lock->unmap.allow_populated = populated;
	lock->unmap.allow_partial = partial;
	smp_store_release(&lock->unmap.enabled, true);
	return 0;
}

int kd_mmap_unmap_enable(struct mm_struct *mm, unsigned long start, unsigned long end)
{
	return enable(mm, start, end, false, false);
}
EXPORT_SYMBOL_GPL(kd_mmap_unmap_enable);

int kd_mmap_unmap_populated_enable(struct mm_struct *mm, unsigned long start, unsigned long end)
{
	return enable(mm, start, end, true, false);
}
EXPORT_SYMBOL_GPL(kd_mmap_unmap_populated_enable);

int kd_mmap_unmap_resident_partial_enable(struct mm_struct *mm, unsigned long start,
					unsigned long end)
{
	return enable(mm, start, end, true, true);
}
EXPORT_SYMBOL_GPL(kd_mmap_unmap_resident_partial_enable);

unsigned int kd_mmap_unmap_pending(struct mm_struct *mm)
{
	unsigned int count = 0;
	int cpu, slot;

	/* Coordination observation only; object/node identity governs retirement. */
	for_each_possible_cpu(cpu)
		for (slot = 0; slot < KD_MMAP_MUTEX_MAX_NODES; slot++) {
			struct kd_mmap_mutex_node *n = per_cpu_ptr(&kd_mmap_mutex_nodes[slot], cpu);
			if (READ_ONCE(n->lock) == &mm->mmap_lock.kd.gate &&
			    READ_ONCE(n->entry_abi) == UNMAP_TAG)
				count++;
		}
	return count;
}
EXPORT_SYMBOL_GPL(kd_mmap_unmap_pending);

static struct unmap_request *request(struct kd_mmap_mutex_node *node)
{
	return (void *)(unsigned long)node->rsp;
}

static bool owned(struct mm_struct *mm)
{
	struct kd_mmap_rwsem *sem = &mm->mmap_lock.kd;
	unsigned long owner = atomic_long_read(&sem->gate.owner);

	return !(owner & 4UL) && (owner & ~7UL) == (unsigned long)current &&
		atomic_long_read(&sem->admission) == -1 && !atomic_long_read(&sem->readers);
}

static struct kd_mmap_mutex_node *decode(u32 tail)
{
	return per_cpu_ptr(&kd_mmap_mutex_nodes[(tail >> KD_MMAP_MUTEX_TAIL_IDX_OFFSET) &
		KD_MMAP_MUTEX_TAIL_IDX_MASK], (tail >> KD_MMAP_MUTEX_TAIL_CPU_OFFSET) - 1);
}

static struct kd_mmap_mutex_node *detach(struct kd_mmap_mutex_node *node)
{
	struct unmap_request *r = request(node);
	struct kd_mmap_mutex_node *next = smp_load_acquire(&node->next);

	if (!next && cmpxchg(&r->mm->mmap_lock.unmap.tail, node->tail, 0) != node->tail)
		while (!(next = smp_load_acquire(&node->next)))
			cpu_relax();
	WRITE_ONCE(node->next, NULL);
	return next;
}

static void execute(struct kd_mmap_mutex_node *node)
{
	struct unmap_request *r = request(node);
	struct kd_mmap_unmap_state *u = &r->mm->mmap_lock.unmap;
	bool remote = r->origin != current;
	unsigned int claim;
	u64 count;

	BUG_ON(!owned(r->mm) || node->lock != &r->mm->mmap_lock.kd.gate ||
	       node->task_struct_ptr != r->origin);
	claim = cmpxchg(&node->packet_state, UNMAP_PENDING, UNMAP_RUNNING);
	BUG_ON(claim != UNMAP_PENDING && claim != UNMAP_CANCELLED);
	if (claim == UNMAP_CANCELLED) {
		r->handled = true;
		r->result = -EINTR;
		atomic64_inc(&u->cancelled);
		return;
	}
	if (!READ_ONCE(u->native_only) && kd_mmap_unmap_try(r->mm, r->start,
			r->end, r->origin, r->live, r->reserve, r->id, &r->result)) {
		r->handled = true;
		BUG_ON(!owned(r->mm));
		if (r->result) {
			/* An admitted body's error is returned, never replayed locally. */
			count = atomic64_inc_return(&u->failed);
			if (remote && count <= 16)
				pr_info("KD_MM_UNMAP error mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx result=%d\n",
					r->mm, r->id, r->origin->pid, current->pid, r->start, r->end, r->result);
			return;
		}
		atomic64_inc(&u->removed);
		if (remote) {
			count = atomic64_inc_return(&u->delegated);
			if (count <= 16)
				pr_info("KD_MM_UNMAP done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx result=0\n",
					r->mm, r->id, r->origin->pid, current->pid, r->start, r->end);
		}
		return;
	}
	if (!READ_ONCE(u->native_only))
		atomic64_inc(&u->refused);
	WRITE_ONCE(u->native_only, true);
	atomic64_inc(&u->native);
	if (!remote)
		return;
	count = atomic64_inc_return(&u->handbacks);
	r->physical_owner = current;
	smp_store_release(&node->locked, UNMAP_NATIVE);
	wait_var_event(&node->locked, smp_load_acquire(&node->locked) == UNMAP_ACK);
	BUG_ON(r->physical_owner != current || !owned(r->mm) || r->handled);
	atomic64_inc(&u->acks);
	if (count <= 16)
		pr_info("KD_MM_UNMAP ack mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx\n",
			r->mm, r->id, r->origin->pid, current->pid, r->start, r->end);
}

static void combine(struct kd_mmap_mutex_node *head)
{
	struct unmap_request *r = request(head);
	struct kd_mmap_rwsem *sem = &r->mm->mmap_lock.kd;
	struct kd_mmap_mutex_node *node = head, *next;
	unsigned int count = 0;
	int error = kd_mmap_rwsem_body_lock(sem, head);

	if (error) {
		r->handled = true;
		r->result = error;
		atomic64_inc(&r->mm->mmap_lock.unmap.cancelled);
		next = detach(head);
		if (next)
			smp_store_release(&next->locked, UNMAP_HEAD);
		return;
	}
	for (;;) {
		execute(node);
		next = detach(node);
		if (node != head)
			smp_store_release(&node->locked, UNMAP_DONE);
		if (!next || ++count == UNMAP_BATCH)
			break;
		node = next;
	}
	kd_mmap_up_write(sem);
	if (next)
		smp_store_release(&next->locked, UNMAP_HEAD);
}

bool kd_mmap_unmap_submit(struct mm_struct *mm, unsigned long start,
	unsigned long end, struct ma_state *live, struct ma_state *reserve, int *result)
{
	struct kd_mmap_unmap_state *u = &mm->mmap_lock.unmap;
	struct unmap_request r = { .mm = mm, .origin = current,
		.start = start, .end = end, .live = live, .reserve = reserve };
	struct kd_mmap_mutex_node *node;
	u32 previous;
	u8 state;

	BUG_ON(!mm->mmap_lock.use_kd || !smp_load_acquire(&u->enabled));
	r.id = atomic64_inc_return(&u->calls);
	if (READ_ONCE(u->native_only)) {
		atomic64_inc(&u->post_ban);
		atomic64_inc(&u->native);
		return false;
	}
	mmget(mm);
	migrate_disable();
	preempt_disable();
	node = kd_mmap_body_node_get(&mm->mmap_lock.kd.gate);
	if (!node) {
		preempt_enable();
		migrate_enable();
		atomic64_inc(&u->native);
		goto put;
	}
	node->next = NULL;
	node->rsp = (unsigned long)&r;
	node->tail = node->osq.tail;
	node->locked = UNMAP_WAIT;
	node->packet_state = UNMAP_PENDING;
	WRITE_ONCE(node->entry_abi, UNMAP_TAG);
	previous = xchg(&u->tail, node->tail);
	if (previous)
		smp_store_release(&decode(previous)->next, node);
	else
		node->locked = UNMAP_HEAD;
	for (;;) {
		state = smp_load_acquire(&node->locked);
		if (state == UNMAP_DONE)
			break;
		if (state == UNMAP_HEAD) {
			preempt_enable();
			combine(node);
			preempt_disable();
			break;
		}
		if (state == UNMAP_NATIVE) {
			unsigned long owner = atomic_long_read(&mm->mmap_lock.kd.gate.owner);

			BUG_ON(request(node) != &r || node->task_struct_ptr != current ||
			       node->lock != &mm->mmap_lock.kd.gate || r.origin != current ||
			       r.handled || !r.physical_owner || (owner & 4UL) ||
			       (owner & ~7UL) != (unsigned long)r.physical_owner ||
			       atomic_long_read(&mm->mmap_lock.kd.admission) != -1);
			if (atomic64_read(&u->handbacks) <= 16)
				pr_info("KD_MM_UNMAP handback mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx\n",
					mm, r.id, current->pid, r.physical_owner->pid, start, end);
			smp_store_release(&node->locked, UNMAP_ACK);
			wake_up_var(&node->locked);
		} else if (fatal_signal_pending(current)) {
			cmpxchg(&node->packet_state, UNMAP_PENDING, UNMAP_CANCELLED);
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
	*result = r.result;
	return r.handled;
}
