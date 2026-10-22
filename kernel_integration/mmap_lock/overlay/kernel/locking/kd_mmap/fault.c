// SPDX-License-Identifier: GPL-2.0
/* Fixed anonymous write-fault installation. Reuse KD's physical mutex,
 * preallocated nodes, independent OSQ/FIFO links and exact request/ACK lifetime.
 * Each origin keeps its actual mmap read acquisition and its prepared page.
 * The fault service gate never closes mmap reader admission. */
#include <linux/kd_mmap_lock.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/wait_bit.h>
#include "body_internal.h"

#define FAULT_TAG 253
#define FAULT_BATCH 256
enum fault_state { FAULT_WAIT, FAULT_HEAD, FAULT_NATIVE, FAULT_ACK, FAULT_DONE };
enum fault_claim { FAULT_PENDING, FAULT_RUNNING, FAULT_CANCELLED };

struct fault_request {
	struct mm_struct *mm;
	struct task_struct *origin, *physical_owner;
	struct vm_fault *vmf;
	struct page *page;
	unsigned long entry;
	u64 id;
	enum kd_mmap_fault_result result;
};

void kd_mmap_fault_init(struct kd_mmap_lock *lock)
{
	struct kd_mmap_fault_state *f = &lock->fault;

	kd_mmap_mutex_init(&f->gate);
	f->start = f->end = 0;
	f->enabled = f->native_only = false;
	atomic64_set(&f->calls, 0);
	atomic64_set(&f->supported, 0);
	atomic64_set(&f->delegated, 0);
	atomic64_set(&f->native, 0);
	atomic64_set(&f->post_ban, 0);
	atomic64_set(&f->handbacks, 0);
	atomic64_set(&f->acks, 0);
	atomic64_set(&f->cancelled, 0);
	atomic64_set(&f->refused, 0);
}

bool kd_mmap_fault_idle(struct kd_mmap_lock *lock)
{
	return kd_mmap_mutex_is_idle(&lock->fault.gate);
}
EXPORT_SYMBOL_GPL(kd_mmap_fault_idle);

int kd_mmap_fault_enable(struct mm_struct *mm, unsigned long start, unsigned long end)
{
	struct kd_mmap_lock *lock = &mm->mmap_lock;
	unsigned long owner;

	if (!lock->use_kd || !start || end <= start || ((start | end) & ~PAGE_MASK))
		return -EINVAL;
	owner = atomic_long_read(&lock->kd.gate.owner);
	if ((owner & 4UL) || (owner & ~7UL) != (unsigned long)current ||
	    atomic_long_read(&lock->kd.admission) != -1 || lock->fault.enabled ||
	    !kd_mmap_fault_idle(lock))
		return -EBUSY;
	/* The immutable interval prevents incidental stack/runtime faults from
	 * joining the experiment. Refusal remains sticky until mm destruction. */
	lock->fault.start = start;
	lock->fault.end = end;
	smp_store_release(&lock->fault.enabled, true);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_mmap_fault_enable);

unsigned int kd_mmap_fault_pending(struct mm_struct *mm)
{
	unsigned int count = 0;
	int cpu, slot;

	/* Observation only. Exact node identities, not this count, govern drain. */
	for_each_possible_cpu(cpu)
		for (slot = 0; slot < KD_MMAP_MUTEX_MAX_NODES; slot++) {
			struct kd_mmap_mutex_node *n = per_cpu_ptr(&kd_mmap_mutex_nodes[slot], cpu);
			if (READ_ONCE(n->lock) == &mm->mmap_lock.fault.gate &&
			    READ_ONCE(n->entry_abi) == FAULT_TAG)
				count++;
		}
	return count;
}
EXPORT_SYMBOL_GPL(kd_mmap_fault_pending);

static struct fault_request *request(struct kd_mmap_mutex_node *node)
{
	return (void *)(unsigned long)node->rsp;
}

static bool owned(struct kd_mmap_mutex *gate)
{
	unsigned long owner = atomic_long_read(&gate->owner);

	return !(owner & 4UL) && (owner & ~7UL) == (unsigned long)current;
}

static struct kd_mmap_mutex_node *decode(u32 tail)
{
	return per_cpu_ptr(&kd_mmap_mutex_nodes[(tail >> KD_MMAP_MUTEX_TAIL_IDX_OFFSET) &
		KD_MMAP_MUTEX_TAIL_IDX_MASK], (tail >> KD_MMAP_MUTEX_TAIL_CPU_OFFSET) - 1);
}

static struct kd_mmap_mutex_node *detach(struct kd_mmap_mutex_node *node)
{
	struct kd_mmap_mutex_node *next = smp_load_acquire(&node->next);

	if (!next && cmpxchg(&node->lock->delegation_tail, node->tail, 0) != node->tail)
		while (!(next = smp_load_acquire(&node->next)))
			cpu_relax();
	WRITE_ONCE(node->next, NULL);
	return next;
}

static bool may_cancel(struct fault_request *r)
{
	/* Only the origin may perform the corresponding read-unlock/retry edge. */
	return (r->vmf->flags & FAULT_FLAG_ALLOW_RETRY) &&
		!(r->vmf->flags & FAULT_FLAG_RETRY_NOWAIT);
}

static void execute(struct kd_mmap_mutex_node *node)
{
	struct fault_request *r = request(node);
	struct kd_mmap_fault_state *f = &r->mm->mmap_lock.fault;
	bool remote = r->origin != current;
	unsigned int claim;
	u64 count;

	BUG_ON(!owned(&f->gate) || node->lock != &f->gate ||
	       node->task_struct_ptr != r->origin || r->vmf->vma->vm_mm != r->mm);
	claim = cmpxchg(&node->packet_state, FAULT_PENDING, FAULT_RUNNING);
	BUG_ON(claim != FAULT_PENDING && claim != FAULT_CANCELLED);
	if (claim == FAULT_CANCELLED) {
		BUG_ON(!may_cancel(r));
		r->result = KD_MMAP_FAULT_CANCELLED;
		atomic64_inc(&f->cancelled);
		return;
	}
	if (!READ_ONCE(f->native_only) &&
	    kd_mmap_fault_try(r->vmf, r->page, r->entry, r->origin)) {
		r->result = KD_MMAP_FAULT_INSTALLED;
		atomic64_inc(&f->supported);
		if (remote) {
			count = atomic64_inc_return(&f->delegated);
			if (count <= 16)
				pr_info("KD_MM_FAULT done mm=%px id=%llu origin=%d executor=%d address=%lx pfn=%lx\n",
					r->mm, r->id, r->origin->pid, current->pid,
					r->vmf->address, page_to_pfn(r->page));
		}
		return;
	}
	/* No effect has occurred. ACK acknowledges the exact refusal request;
	 * native fault processing starts only after DONE and slot retirement.
	 * Waiting here for userfaultfd/native completion could deadlock a writer
	 * behind the combiner's own read share. Never call that continuation here. */
	if (!READ_ONCE(f->native_only))
		atomic64_inc(&f->refused);
	WRITE_ONCE(f->native_only, true);
	atomic64_inc(&f->native);
	r->result = KD_MMAP_FAULT_LOCAL;
	if (!remote)
		return;
	count = atomic64_inc_return(&f->handbacks);
	r->physical_owner = current;
	smp_store_release(&node->locked, FAULT_NATIVE);
	wait_var_event(&node->locked, smp_load_acquire(&node->locked) == FAULT_ACK);
	BUG_ON(r->physical_owner != current || !owned(&f->gate));
	atomic64_inc(&f->acks);
	if (count <= 16)
		pr_info("KD_MM_FAULT ack mm=%px id=%llu origin=%d executor=%d address=%lx\n",
			r->mm, r->id, r->origin->pid, current->pid, r->vmf->address);
}

static void combine(struct kd_mmap_mutex_node *head)
{
	struct fault_request *r = request(head);
	struct kd_mmap_fault_state *f = &r->mm->mmap_lock.fault;
	struct kd_mmap_mutex_node *node = head, *next;
	unsigned int count = 0;
	int error = kd_mmap_mutex_lock_killable_node(&f->gate, head);

	if (error) {
		r->result = may_cancel(r) ? KD_MMAP_FAULT_CANCELLED : KD_MMAP_FAULT_LOCAL;
		atomic64_inc(may_cancel(r) ? &f->cancelled : &f->native);
		next = detach(head);
		if (next)
			smp_store_release(&next->locked, FAULT_HEAD);
		return;
	}
	for (;;) {
		execute(node);
		next = detach(node);
		if (node != head)
			smp_store_release(&node->locked, FAULT_DONE);
		if (!next || ++count == FAULT_BATCH)
			break;
		node = next;
	}
	kd_mmap_mutex_local_unlock(&f->gate);
	if (next)
		smp_store_release(&next->locked, FAULT_HEAD);
}

enum kd_mmap_fault_result kd_mmap_fault_submit(struct vm_fault *vmf,
					      struct page *page, unsigned long entry)
{
	struct mm_struct *mm = vmf->vma->vm_mm;
	struct kd_mmap_fault_state *f = &mm->mmap_lock.fault;
	struct fault_request r = { .mm = mm, .origin = current, .vmf = vmf,
		.page = page, .entry = entry, .result = KD_MMAP_FAULT_LOCAL };
	struct kd_mmap_mutex_node *node;
	u32 previous;
	u8 state;

	BUG_ON(!mm->mmap_lock.use_kd || !smp_load_acquire(&f->enabled) ||
	       !(vmf->flags & FAULT_FLAG_WRITE));
	r.id = atomic64_inc_return(&f->calls);
	if (READ_ONCE(f->native_only)) {
		atomic64_inc(&f->post_ban);
		atomic64_inc(&f->native);
		return KD_MMAP_FAULT_LOCAL;
	}
	mmget(mm);
	migrate_disable();
	preempt_disable();
	node = kd_mmap_body_node_get(&f->gate);
	if (!node) {
		preempt_enable();
		migrate_enable();
		atomic64_inc(&f->native);
		goto put;
	}
	node->next = NULL;
	node->rsp = (unsigned long)&r;
	node->tail = node->osq.tail;
	node->locked = FAULT_WAIT;
	node->packet_state = FAULT_PENDING;
	WRITE_ONCE(node->entry_abi, FAULT_TAG);
	previous = xchg(&f->gate.delegation_tail, node->tail);
	if (previous)
		smp_store_release(&decode(previous)->next, node);
	else
		node->locked = FAULT_HEAD;
	for (;;) {
		state = smp_load_acquire(&node->locked);
		if (state == FAULT_DONE)
			break;
		if (state == FAULT_HEAD) {
			preempt_enable();
			combine(node);
			preempt_disable();
			break;
		}
		if (state == FAULT_NATIVE) {
			unsigned long owner = atomic_long_read(&f->gate.owner);

			BUG_ON(request(node) != &r || node->task_struct_ptr != current ||
			       node->lock != &f->gate || r.origin != current ||
			       vmf->vma->vm_mm != mm || !r.physical_owner ||
			       (owner & 4UL) || (owner & ~7UL) != (unsigned long)r.physical_owner ||
			       r.result != KD_MMAP_FAULT_LOCAL);
			if (atomic64_read(&f->handbacks) <= 16)
				pr_info("KD_MM_FAULT handback mm=%px id=%llu origin=%d executor=%d address=%lx\n",
					mm, r.id, current->pid, r.physical_owner->pid, vmf->address);
			smp_store_release(&node->locked, FAULT_ACK);
			wake_up_var(&node->locked);
		} else if (may_cancel(&r) && fatal_signal_pending(current)) {
			cmpxchg(&node->packet_state, FAULT_PENDING, FAULT_CANCELLED);
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
