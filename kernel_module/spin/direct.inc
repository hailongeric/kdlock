// SPDX-License-Identifier: GPL-2.0
/* Public lock ABI shells and out-of-loop source preparation.
 * The inlined admission core comes from entry.inc; no extra call layer is added. */

/* The pinned caller already counted the acquisition and observed a failed
 * CAS. Later heat changes never turn this native queue wait into delegation. */
__attribute__((noipa)) noinline notrace void
kd_spin_direct_native_contended(kd_spinlock_t *lock, u32 failed)
{
	kd_spin_acquire_nondelegated_contended(lock, failed);
	/* The core acquired with its ordinary byte. Publish native provenance
	 * without changing pending/tail or issuing another acquisition CAS. */
	WRITE_ONCE(lock->locked, KD_SPIN_DIRECT_NATIVE_HELD);
}
EXPORT_SYMBOL_GPL(kd_spin_direct_native_contended);

/* Retain the out-of-line API for existing pinned callers. */
__attribute__((noipa)) noinline notrace void
kd_spin_direct_native_lock(kd_spinlock_t *lock)
{
	kd_spin_direct_native_lock_inline(lock);
}
EXPORT_SYMBOL_GPL(kd_spin_direct_native_lock);

__attribute__((noipa)) noinline notrace void
kd_spin_direct_native_unlock(kd_spinlock_t *lock)
{
	/* The lock byte proves native ownership; preserve a concurrently added tail. */
	smp_store_release(&lock->locked, 0);
	this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	preempt_enable();
}
EXPORT_SYMBOL_GPL(kd_spin_direct_native_unlock);

__attribute__((noipa)) noinline notrace void
kd_spin_lock_pinned_clobber_v1(kd_spinlock_t *lock, unsigned long sp,
			     unsigned long ip, unsigned long bp)
{
	kd_spin_lock_abi_pinned(lock, sp, ip, bp, KD_ENTRY_ABI_SPIN_CLOBBER_V1);
}
EXPORT_SYMBOL_GPL(kd_spin_lock_pinned_clobber_v1);

/* Remote completion resumes after the caller's paired unlock and never
 * returns here. An intact return owns the gate and still needs admission. */
__attribute__((noipa)) noinline notrace void
kd_rwlock_lock_pinned_clobber_v1(kd_spinlock_t *gate, unsigned long sp,
			       unsigned long ip, unsigned long bp)
{
	kd_spin_lock_abi_pinned(gate, sp, ip, bp, KD_ENTRY_ABI_RWLOCK_CLOBBER_V1);
	kd_rwlock_writer_enter(container_of(gate, kd_rwlock_t, gate));
}
EXPORT_SYMBOL_GPL(kd_rwlock_lock_pinned_clobber_v1);

__attribute__((noipa)) noinline notrace void
kd_rwlock_fast_write_unlock(kd_rwlock_t *lock)
{
	kd_rwlock_writer_exit(lock);
	this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	preempt_enable();
}
EXPORT_SYMBOL_GPL(kd_rwlock_fast_write_unlock);

void kd_spin_lock(struct qspinlock *lock, unsigned long sp, unsigned long ip)
{
	kd_spin_lock_abi(lock, sp, ip, 0, KD_ENTRY_ABI_LEGACY);
}
EXPORT_SYMBOL_GPL(kd_spin_lock);

/* Preparation is explicitly outside the operation loop and after the source
 * module is LIVE, so its text can be pinned until retirement. */
int kd_spin_prepare(struct qspinlock *lock, unsigned long ip, unsigned int abi)
{
	struct kd_exe_info *exe;

	if (!lock || !ip || !kd_entry_abi_valid(KD_EXE_LOCK_SPIN, abi))
		return -EINVAL;
	if (!kd_source_is_open())
		return -ESHUTDOWN;
	kd_exe_add_abi(0, ip, KD_EXE_LOCK_SPIN, abi);
	exe = kd_get_exe(0, ip);
	if (!exe || smp_load_acquire(&exe->status_code) == KD_EXE_UNUSED ||
		exe->RIP != ip || exe->entry_abi != abi ||
		exe->lock_kind != KD_EXE_LOCK_SPIN || !exe->code_block)
		return -EINVAL;
	return READ_ONCE(exe->status_code) == KD_EXE_NATIVE_ONLY ? -EOPNOTSUPP : 0;
}
EXPORT_SYMBOL_GPL(kd_spin_prepare);

__attribute__((noipa)) noinline notrace void
kd_spin_lock_clobber_v1(struct qspinlock *lock, unsigned long sp,
						unsigned long ip, unsigned long bp)
{
	/* Ordinary clobber callers acquire their own pin; paired hot callers
	 * enter the same inlined core through the already-pinned entry above. */
	preempt_disable();
	kd_spin_lock_abi_pinned(lock, sp, ip, bp, KD_ENTRY_ABI_SPIN_CLOBBER_V1);
}
EXPORT_SYMBOL_GPL(kd_spin_lock_clobber_v1);
