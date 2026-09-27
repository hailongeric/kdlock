// SPDX-License-Identifier: GPL-2.0
/* Pinned acquisition routing: queue admission, native fallback and ticket
 * ownership. Uses the restore helpers above; public ABI shells follow. */

/* Queue preparation and combiner C code stay on the task stack. Like plain
 * raw_spin_lock, leave IRQ state unchanged throughout waiting/execution.
 * JIT may overwrite the original C frames, so restoration uses the packet. */
__attribute__((noipa)) noinline notrace static void
kd_spin_lock_slowpath(struct qspinlock *lock, unsigned long rsp_value,
					  struct kd_spin_request *request, unsigned long ip,
					  unsigned long bp, unsigned int abi)
{
	struct kd_spin_native_input input;
	unsigned long sp;
	int ret;

	asm volatile("movq %%rsp, %0" : "=r"(sp));
	input.rsp = sp;
	input.regs_sp = rsp_value;
	input.ip = ip;
	input.bp = bp;
	input.entry_abi = abi;
	ret = __kd_spin_lock_slowpath(lock, request, &input);
	if (ret == 0 || ret == 2)
	{
		return;
	}
	/* A pre-body refusal can acquire the queue and retry from its decoded
	 * entry. It has not touched the caller's stack; completed/native wakes
	 * already left through kd_spin_resume_completed and cannot return here. */
	if (ret == 4)
	{
		struct kd_spin_node *node =
			READ_ONCE(*this_cpu_ptr(&kd_spin_resume_nodes));

		sp = min(node->rsp, node->execution->frame.regs_ref->sp) & ~15UL;
		asm volatile("movq %0, %%rsp\n"
					 "callq %P3\n"
					 "ud2\n"
					 :
					 : "r"(sp), "D"(node), "S"(1U),
					   "i"(kd_spin_resume_waiter)
					 : "memory");
		__builtin_unreachable();
	}
	BUG();
}

/* Admission refusal retains the KD queue protocol. Only genuine node
 * exhaustion polls the full word; ordinary contention uses local MCS waits. */
static void kd_spin_lock_nondelegated_pinned(kd_spinlock_t *lock)
{
	this_cpu_inc(kd_spin_fast_cpu.nondelegated);
	kd_spin_acquire_nondelegated(lock);
	/* A sole task-context hold can use the existing fast ownership record.
	 * Publish it before dropping the acquisition drain count. Nested/IRQ
	 * callers keep their independent count and cannot overwrite that owner. */
	if (in_task() && preempt_count() == 1) {
		kd_spin_fast_claim(lock);
		this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	}
}
void kd_spin_lock_nondelegated(kd_spinlock_t *lock)
{
	preempt_disable();
	kd_hotlock_spin_entry_pinned();
	kd_spin_lock_nondelegated_pinned(lock);
}
/* A physical ACK releases a lock; this barrier releases the root's pin only
 * after every registered native executor has finished all frame accesses. */
void kd_spin_native_retire(struct kd_spin_ref *ref)
{
	struct kd_spin_continuation *root = *this_cpu_ptr(&kd_spin_native_root);

	BUG_ON(!root || root->frame.spin_origin.entry != ref->entry ||
	       root->frame.spin_origin.sequence != ref->sequence);
	BUG_ON(kd_spin_entry_borrow_wait(ref));
	*this_cpu_ptr(&kd_spin_native_root) = NULL;
	kd_spin_continuation_release(root);
	BUG_ON(kd_spin_entry_end(ref));
}

void kd_spin_unlock_nondelegated(kd_spinlock_t *lock)
{
	/* Native bridge callers use this paired API directly, bypassing the
	 * public unlock router. They can also own the sole fast record. */
	if (kd_spin_fast_unlock((raw_spinlock_t *)lock))
		return;
	smp_store_release(&lock->locked, 0);
	this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	preempt_enable();
}

/* The entry has already pinned admission. Root callers pass the failed CAS
 * value; nested callers reserve their ticket before their first CAS. Keeping
 * the address-taken request here avoids its initialization and stack canary
 * on an uncontended root acquisition. Pending ownership remains ticket-free. */
noinline notrace static void
kd_spin_lock_contended(struct qspinlock *lock, unsigned long rsp_value,
                      unsigned long rip, unsigned long bp, unsigned int abi,
                      u32 val)
{
	struct kd_spin_request request = { .word = lock };
	struct qspinlock *word = lock;
	u32 cnt;

	if (preempt_count() != 1) {
		if (kd_spin_entry_begin_pinned((raw_spinlock_t *)lock, &request.ref))
			goto native;
		val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);
		if (!val)
			goto acquired;
	}
	if (val == _Q_PENDING_VAL_HL)
	{
		cnt = _Q_PENDING_LOOPS_HL;
		val = atomic_cond_read_relaxed(
			&word->val, (VAL != _Q_PENDING_VAL_HL) || !cnt--);
	}
	if (val & ~_Q_LOCKED_MASK_HL)
		goto queue;
	val = kd_spin_fetch_set_pending_acquire(word);
	if (unlikely(val & ~_Q_LOCKED_MASK_HL))
	{
		if (!(val & _Q_PENDING_MASK_HL))
			clear_pending(word);
		goto queue;
	}
	if (val & _Q_LOCKED_MASK_HL)
		atomic_cond_read_acquire(&word->val,
								 !(VAL & _Q_LOCKED_MASK_HL));
	clear_pending_set_locked(word);
	goto acquired;
queue:
	/* A sole pending owner never publishes a continuation or lends its
	 * ownership to a remote executor. Defer its ticket until MCS admission;
	 * fast/pending success can use the same CPU-local physical owner record.
	 * Nested callers reserved above and retain their independent ticket. */
	if (!request.ref.entry &&
	    kd_spin_entry_begin_pinned((raw_spinlock_t *)lock, &request.ref))
		goto native;
	/* Before publication, an absent/refused translation needs only an MCS
	 * node. Keep registration for later admission, but allocate no logical
	 * packet/frame and never lend this caller's stack to a combiner. */
	if (preempt_count() != 1 ||
	    !kd_exe_entry_is_ready(kd_get_exe(0, rip), 0, rip)) {
		kd_exe_add_abi(0, rip, KD_EXE_LOCK_SPIN, abi);
		kd_spin_acquire_nondelegated(word);
		goto acquired;
	}
	kd_spin_lock_slowpath(lock, rsp_value, &request, rip, bp, abi);
	/* Every intact slowpath return has already claimed (or reclaimed) the
	 * ticket, including capacity fallback. Remote completion never returns
	 * here. Do not take its guard a second time merely to confirm OWNED. */
	return;
acquired:
	if (request.ref.entry)
		kd_spin_claim_origin(&request);
	else
		kd_spin_fast_claim(lock);
	return;
native:
	kd_spin_lock_nondelegated_pinned(lock);
}
/* One acquisition pin spans admission, queueing and the entire CS. Refusal
 * transfers that pin to native execution; unlock/completion consumes it. */
static __always_inline void
kd_spin_lock_abi_pinned(struct qspinlock *lock, unsigned long rsp_value,
                 unsigned long rip, unsigned long bp, unsigned int abi)
{
	u32 val = 0;

	kd_hotlock_spin_entry_pinned();
	if (!kd_spin_delegate || !kd_hotlock_record_spin_pinned((unsigned long)lock))
		goto native;
	if (!in_task() || softirq_count() || current->migration_disabled ||
	    kd_spin_entry_native_active())
		goto native;
	if (kd_exec_context_occupied())
		goto native;
	if (preempt_count() == 1) {
		val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL_HL);
		if (!val) {
			kd_spin_fast_claim(lock);
			return;
		}
	}
	kd_spin_lock_contended(lock, rsp_value, rip, bp, abi, val);
	return;
native:
	kd_spin_lock_nondelegated_pinned(lock);
}

__attribute__((noipa)) noinline notrace void
kd_spin_lock_abi(struct qspinlock *lock, unsigned long sp,
		 unsigned long ip, unsigned long bp, unsigned int abi)
{
	preempt_disable();
	kd_spin_lock_abi_pinned(lock, sp, ip, bp, abi);
}
