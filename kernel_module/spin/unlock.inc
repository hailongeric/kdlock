// SPDX-License-Identifier: GPL-2.0
/*
 * Unlock routing by acquisition provenance: physical owner, ticket and
 * native ACK. Release remains independent of the current heat/admission policy.
 */

/*
 * Keep the noipa call boundary: delegated completion can resume after unlock
 * without executing this function. The caller must honor its register-clobber
 * contract even when interprocedural analysis could infer fewer clobbers from
 * the physical unlock implementation.
 */
__attribute__((noipa)) noinline notrace static void
kd_spin_unlock_request(struct qspinlock *lock, struct kd_spin_request *request)
{
	struct qspinlock *word = request->word;
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);
	int j, max_idx, my_idx;

	uint64_t temp_lock_addr;

	j = 0;
	max_idx = -1;
	my_idx = -1;

	if (word->locked == _Q_LOCKED_VAL_HL ||
	    word->locked == _Q_LOCKED_IRQ_VAL) {
		kd_spin_release_origin(request);
		return;
	}

	for (j = 0; j < 8; j++) {
		temp_lock_addr = ptr->lock_addr[j];
		if (temp_lock_addr != 0)
			max_idx = j;
		if (temp_lock_addr == (uint64_t)(unsigned long)lock)
			my_idx = j;
		if (temp_lock_addr == 0)
			break;
	}
	kd_spin_diag_validate_lock_stack(ptr);
	kd_spin_diag_validate_outer_unlock(ptr, lock, word, my_idx, max_idx);

	if (my_idx == -1) {
		if (word->locked == _Q_LOCKED_COMBINER_VAL) {
#ifdef KD_SPIN_STATS
			this_cpu_inc(ooo_unlocks);
#endif
			kd_spin_debug_ooo_unlock(lock,
						 kd_spin_lock_stack_depth(ptr));
			word->locked = _Q_UNLOCKED_OOO_VAL;
			print_debug("OOO unlock\n");
		} else
			BUG_ON(true);
		return;
	}

#ifdef DEBUG_KD_SPIN
	if (word->locked != _Q_LOCKED_COMBINER_VAL)
		BUG_ON(true);

	BUG_ON(ptr->curr_cs_cpu == -1);

	if (max_idx < 0) {
		BUG_ON(true);
	}

#endif
	if (my_idx < max_idx) {
#ifdef KD_SPIN_STATS
		this_cpu_inc(ooo_unlocks);
#endif

		kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
		word->locked = _Q_UNLOCKED_OOO_VAL;
		return;
	}

	/* Plain spin leaves each physical caller's IRQ state unchanged. */
}

__attribute__((noipa)) noinline notrace void
kd_spin_unlock_ref(struct qspinlock *lock, const struct kd_spin_ref *ref)
{
	struct kd_spin_request request = {
		.ref = *ref,
		.word = kd_spin_request_word(ref),
	};

	kd_spin_unlock_request(lock, &request);
}

__attribute__((noipa)) noinline notrace void
kd_spin_unlock_protocol(struct qspinlock *lock)
{
	struct kd_spin_request request = kd_spin_unlock_lookup(lock);

	kd_spin_unlock_request(lock, &request);
}

/*
 * Explicit callers need the same acquisition-provenance release as the old
 * hook, including the ticket-free KD owner and unstarted native fallback.
 * This is protocol routing, independent of comm, frequency or JIT policy.
 */
noinline notrace static void
kd_spin_unlock_slow(struct qspinlock *lock)
{
	struct kd_spin_ref ref = { 0 };

	if (kd_exec_native_unlock((unsigned long)lock, false))
		return;
	if (kd_spin_entry_find((raw_spinlock_t *)lock, &ref)) {
		kd_spin_unlock_ref(lock, &ref);
		return;
	}
	kd_spin_unlock_nondelegated(lock);
}

/*
 * Avoid preparing a ticket reference until physical fast ownership misses.
 * Inline only this small router; request/continuation work remains slow.
 */
static __always_inline void
kd_spin_unlock_core(struct qspinlock *lock)
{
	if (kd_spin_fast_unlock((raw_spinlock_t *)lock))
		return;
	kd_spin_unlock_slow(lock);
}

__attribute__((noipa)) noinline notrace void
kd_spin_unlock(struct qspinlock *lock)
{
	kd_spin_unlock_core(lock);
}

EXPORT_SYMBOL_GPL(kd_spin_unlock);

/*
 * This ABI shell does not retain state after either helper. Permit sibling
 * calls locally so the common native release needs no C frame: rescheduling
 * and the generic ownership router return directly to the original caller.
 * Keep the kernel's preempt decrement/test and return-thunk machinery.
 * Fix the small native entry's alignment independently of adjacent helpers.
 */
__attribute__((noipa, aligned(64), optimize("optimize-sibling-calls")))
noinline notrace void
kd_spin_unlock_clobber_v1(struct qspinlock *lock, unsigned long sp,
						  unsigned long ip, unsigned long bp)
{
	/*
	 * Byte 5 carries paired native ownership without a fast record/ticket.
	 * Release only that byte, then drop its count and acquisition pin. Keep
	 * this short route inline; the ordinary generic router handles all other
	 * owners. Callers still provide SP/IP/BP: the JIT completion endpoint
	 * validates those words even though physical release does not use them.
	 * Prefer fall-through for native holds; delegated COMPLETE exits bypass
	 * this physical call, leaving this route common at low contention.
	 */
	if (likely(READ_ONCE(lock->locked) == KD_SPIN_DIRECT_NATIVE_HELD)) {
		smp_store_release(&lock->locked, 0);
		this_cpu_dec(kd_spin_fast_cpu.nondelegated);
		/*
		 * Same decrement/test as preempt_enable. This clobber ABI permits
		 * an ordinary C call: expose it to the compiler instead of hiding
		 * it in __preempt_schedule's register-preserving inline assembly.
		 * Use the exported module trampoline: its target follows dynamic
		 * preemption, while its private static-call key is not exported.
		 */
#ifdef CONFIG_PREEMPTION
		barrier();
		if (unlikely(preempt_count_dec_and_test())) {
#ifdef CONFIG_PREEMPT_DYNAMIC
			static_call_mod(preempt_schedule)();
#else
			preempt_schedule();
#endif
		}
#else
		preempt_enable();
#endif
		return;
	}
	kd_spin_unlock(lock);
}

EXPORT_SYMBOL_GPL(kd_spin_unlock_clobber_v1);

static __always_inline int kd_spin_trylock(struct qspinlock *word)
{
	u32 val;

	val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);
	if (val == 0)
		return true;

	return false;
}
