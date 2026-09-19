/*
 * Bounded registration and retirement; publication is not a JIT body witness.
 * Private implementation included only by exe.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static bool kd_exe_registered(unsigned int pid, unsigned long rip,
			      enum kd_exe_lock_kind kind, enum kd_entry_abi abi)
{
	struct kd_exe_info *exe = kd_get_exe(pid, rip);

	/* A lookup can return an UNUSED slot whose writer is still initializing
	 * its key. Only publication proves that root pinning and all immutable
	 * metadata are complete. UNINIT/miss/native-only entries also need no
	 * duplicate registration; this check does not claim JIT readiness. */
	if (!exe || smp_load_acquire(&exe->status_code) == KD_EXE_UNUSED)
		return false;
	return READ_ONCE(exe->pid) == pid && READ_ONCE(exe->RIP) == rip &&
	       READ_ONCE(exe->lock_kind) == kind &&
	       READ_ONCE(exe->entry_abi) == abi &&
	       READ_ONCE(exe->code_block) && kd_source_is_open();
}

void kd_exe_add_abi(int pid, unsigned long rip, enum kd_exe_lock_kind kind,
                    enum kd_entry_abi abi)
{
	void *mem = NULL;
	struct kd_exe_info *exe;
	int ret;

	if (!kd_entry_abi_valid(kind, abi))
		return;
	/* Root pins outlive the append-only registry within this source session.
	 * Repeated registrations read metadata only, without taking the global
	 * gate or repeating source/module lookup. Retirement can race this no-op:
	 * it neither dereferences source/code nor grants an execution lease.
	 * Actual dispatch still requires readiness and an admitted source frame.
	 * Misses, backend conflicts and closed admission keep the serialized path. */
	if (kd_exe_registered(pid, rip, kind, abi))
		return;
	kd_code_block_gate_lock();
	ret = kd_source_pin_root(rip);
	if (ret) {
		kd_code_block_gate_unlock();
		pr_warn_ratelimited(
			"[KD_JIT][WARN] reason=SOURCE_ROOT_REFUSED entry=0x%lx error=%d\n",
			rip, ret);
		return;
	}
	exe = kd_get_exe(pid, rip);
	if (!exe) {
		kd_code_block_gate_unlock();
		KD_PR_ERR("kd_exe_add: translation table exhausted\n");
		return;
	}
	if (exe->pid == pid && exe->RIP == rip) {
		/* A RIP may be shared by locks, but not by incompatible backends. */
		if (exe->lock_kind != kind || exe->entry_abi != abi) {
			kd_exe_publish_status(exe, KD_EXE_NATIVE_ONLY);
			pr_warn_ratelimited(
				"[KD_JIT][WARN] reason=ENTRY_LOCK_KIND_CONFLICT entry=0x%lx registered=%d requested=%d\n",
				rip, exe->lock_kind, kind);
		}
		kd_code_block_gate_unlock();
		return;
	}

	if (exe->status_code != KD_EXE_UNUSED)
		KD_PR_ERR(
			"translation slot collision: status=%d old=%d/%lx new=%d/%lx\n",
			exe->status_code, exe->pid, exe->RIP, pid, rip);

	/* The pool makes registration safe while a lock hook has IRQs disabled. */
	if (kd_code_block_free > 0)
		mem = kd_code_block_pool[--kd_code_block_free];

	if (!mem) {
		kd_code_block_gate_unlock();
		/* Identify the rejected root without publishing a partial entry or
		 * evicting an image still used by an older execution/native frame. */
		KD_PR_ERR(
			"kd_exe_add: code block pool exhausted entry=%lx task=%d kind=%d\n",
			rip, current->pid, kind);
		return;
	}

	exe->pid = pid;
	exe->RIP = rip;
	exe->tgid = current->tgid;
	exe->lock_kind = kind;
	exe->entry_abi = abi;
	exe->code_block = mem;

	smp_store_release(&exe->status_code, KD_EXE_UNINIT);
	kd_code_block_gate_unlock();
	KD_PR_INFO("exe added %d %lx %d lock_kind=%d\n", pid, rip,
		   current->tgid, kind);
}

void kd_exe_add(int pid, unsigned long rip, enum kd_exe_lock_kind kind)
{
	kd_exe_add_abi(pid, rip, kind, KD_ENTRY_ABI_LEGACY);
}

void kd_exe_retire_all(void)
{
	unsigned int i;

	/* Closing precedes this gate, so a racing registration either finishes
	 * before invalidation or refuses. Slots/images are not reused in-session. */
	kd_code_block_gate_lock();
	for (i = 0; kd_exes && i < KD_MAX_EXE; i++)
		if (READ_ONCE(kd_exes[i].status_code) != KD_EXE_UNUSED)
			kd_exe_publish_status(&kd_exes[i], KD_EXE_NATIVE_ONLY);
	kd_code_block_gate_unlock();
}
