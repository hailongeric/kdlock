/*
 * Executable-slot lookup/readiness and startup/shutdown of the bounded pool.
 * Private implementation included only by exe.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static struct kd_exe_info *kd_exes;

struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip)
{
	int pos;
	int probes;

	if (!kd_exes)
		return NULL;
	pos = zz_hash(pid, ip) % KD_MAX_EXE;
	for (probes = 0; probes < KD_MAX_EXE; probes++) {
		struct kd_exe_info *exe = &kd_exes[pos];

		/* Published keys are immutable until controlled module teardown.
		 * Pair with initial UNINIT publication before comparing their fields.
		 * An UNUSED result is only a candidate, not a registered entry. */
		if (smp_load_acquire(&exe->status_code) == KD_EXE_UNUSED ||
		    (READ_ONCE(exe->pid) == pid && READ_ONCE(exe->RIP) == ip))
			return exe;
		pos = (pos + 1) % KD_MAX_EXE;
	}
	return NULL;
}

const struct kd_exe_info *kd_exe_get_slot(unsigned int index)
{
	if (!kd_exes || index >= KD_MAX_EXE)
		return NULL;
	return &kd_exes[index];
}

/* Policy rejection is terminal even if an older executor reports a miss. */
bool kd_exe_publish_status(struct kd_exe_info *exe, int status)
{
	int old = smp_load_acquire(&exe->status_code);

	for (;;) {
		if (old == KD_EXE_NATIVE_ONLY)
			return status == KD_EXE_NATIVE_ONLY;
		if (try_cmpxchg(&exe->status_code, &old, status))
			return true;
	}
}

/* Fold this publication check into each spin dispatch; keep the external
 * entry for other callers. The acquire and source-close check are unchanged. */
__always_inline __gnu_inline
bool kd_exe_entry_is_ready(const struct kd_exe_info *exe, unsigned int pid,
			   unsigned long ip)
{
	if (!exe || !ip || !kd_source_is_open())
		return false;
	/* Pair with code upload/status publication on every dispatch, including
	 * when the caller resolved this stable slot before acquiring its frame.
	 * Source closing or a later miss/native-only status invalidates readiness;
	 * the slot itself is not reused until controlled provider teardown. */
	if (smp_load_acquire(&exe->status_code) != KD_EXE_NORMAL)
		return false;
	return READ_ONCE(exe->pid) == pid && READ_ONCE(exe->RIP) == ip &&
	       READ_ONCE(exe->code_block) != NULL;
}

struct kd_exe_info *kd_exe_find_ready(unsigned int pid, unsigned long ip)
{
	struct kd_exe_info *exe = kd_get_exe(pid, ip);

	return kd_exe_entry_is_ready(exe, pid, ip) ? exe : NULL;
}

bool kd_exe_is_ready(unsigned int pid, unsigned long ip)
{
	return kd_exe_find_ready(pid, ip) != NULL;
}

int kd_exe_init(void)
{
	int i, ret;

	kd_jit_timing_reset();
	kd_native_terminal_init();
	/* Resolve unlock function addresses dynamically */
	end_point_count = 0;
	/* Direct APIs are linked into this provider; kallsyms need not expose a
	 * module's symbols while its init function is still running. */
	raw_spin_lock_addr = (unsigned long)kd_spin_lock_legacy;
	raw_spin_unlock_addr = (unsigned long)kd_spin_unlock_legacy;
	end_points[end_point_count] = raw_spin_unlock_addr;
	if (raw_spin_unlock_addr)
		end_point_count++;
	clobber_spin_lock_addr = (unsigned long)kd_spin_lock_clobber_v1;
	clobber_spin_unlock_addr = (unsigned long)kd_spin_unlock_clobber_v1;
	if (clobber_spin_unlock_addr)
		end_points[end_point_count++] = clobber_spin_unlock_addr;
	pinned_spin_lock_addr = (unsigned long)kd_spin_lock_pinned_clobber_v1;
	cold_spin_unlock_addr = (unsigned long)kd_spin_direct_native_unlock;
	/* A delegated ABI3 writer owns the gate and 0xff writer byte. The native
	 * 0xf0 fast-unlock helper cannot acknowledge that retained gate owner. */
	rwlock_fast_unlock_addr = (unsigned long)kd_rwlock_fast_write_unlock;
	end_points[end_point_count++] = cold_spin_unlock_addr;
	mutex_lock_addr = (unsigned long)kd_mutex_local_lock;
	mutex_unlock_addr = (unsigned long)kd_mutex_local_unlock;
	end_points[end_point_count] = mutex_unlock_addr;
	if (mutex_unlock_addr)
		end_point_count++;
	clobber_mutex_lock_addr = 0;
	clobber_mutex_unlock_addr = 0;
	if (clobber_mutex_unlock_addr)
		end_points[end_point_count++] = clobber_mutex_unlock_addr;
	direct_mutex_lock_addr = (unsigned long)kd_mutex_direct_lock_clobber_v1;
	contended_mutex_lock_addr = (unsigned long)kd_mutex_direct_contended_clobber_v1;
	outer_mutex_lock_addr = (unsigned long)kd_mutex_outer_contended_clobber_v1;
	direct_mutex_unlock_addr = (unsigned long)kd_mutex_direct_unlock_clobber_v1;
	end_points[end_point_count++] = direct_mutex_unlock_addr;
	for (i = 0; i < end_point_count; i++)
		KD_PR_INFO("end_point[%d] = %lx", i, end_points[i]);
	if (mutex_lock_addr)
		KD_PR_INFO("mutex_lock addr = %lx", mutex_lock_addr);

	atomic64_set(&kd_hostcall_exits, 0);
	atomic64_set(&kd_hostcall_executed, 0);
	atomic64_set(&kd_hostcall_resumed, 0);
	atomic64_set(&kd_hostcall_rejected, 0);
	atomic64_set(&kd_hostcall_failed, 0);
	atomic64_set(&kd_hostcall_limit, 0);
	atomic64_set(&kd_direct_strcmp, 0);
	atomic64_set(&kd_direct_pad, 0);
	atomic64_set(&kd_mutex_stack_equal, 0);
	atomic64_set(&kd_mutex_stack_changed, 0);
	atomic64_set(&kd_mutex_stack_unavailable, 0);
	for (i = 0; i < ARRAY_SIZE(kd_hostcalls); i++) {
		kd_hostcalls[i].addr =
			kallsyms_lookup_name(kd_hostcalls[i].symbol);
		if (kd_hostcalls[i].addr)
			KD_PR_INFO(
				"hostcall service id=%u symbol=%s addr=%lx flags=%x\n",
				kd_hostcalls[i].id, kd_hostcalls[i].symbol,
				kd_hostcalls[i].addr, kd_hostcalls[i].flags);
		else
			KD_PR_INFO(
				"hostcall service unavailable id=%u symbol=%s\n",
				kd_hostcalls[i].id, kd_hostcalls[i].symbol);
	}

	kd_exes = vzalloc(sizeof(struct kd_exe_info) * KD_MAX_EXE);
	if (!kd_exes)
		return -ENOMEM;
	for (i = 0; i < KD_MAX_EXE; i++) {
		kd_exes[i].status_code = KD_EXE_UNUSED;
		kd_exes[i].code_block = NULL;
	}

	/* Lock hooks cannot allocate executable memory with IRQs disabled. */
	atomic_set(&kd_code_block_gate, 0);
	kd_code_block_free = 0;
	for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
		void *block = vmalloc(KD_CODE_BLOCK_SIZE);

		if (!block)
			continue;
		ret = set_memory_x((unsigned long)block, KD_CODE_BLOCK_PAGES);
		if (ret) {
			vfree(block);
			continue;
		}
		kd_code_block_allocations[i] = block;
		kd_code_block_pool[kd_code_block_free++] = block;
	}
	KD_PR_INFO("JIT code block pool ready: %d/%d\n", kd_code_block_free,
		   KD_CODE_BLOCK_POOL);
	if (!kd_code_block_free) {
		vfree(kd_exes);
		kd_exes = NULL;
		return -ENOMEM;
	}
	/* module_alloc supplies the x86 module address region for direct rel32
	 * calls. Keep the established vmalloc/mutex pool intact. At most another
	 * 64 * KD_CODE_BLOCK_SIZE is reserved; shared descriptors still cap all live
	 * image generations at 64. A missing pool disables only this capability.
	 * Call-depth instrumentation requires a different generated prologue. */
	kd_near_block_free = 0;
#if defined(CONFIG_X86_64) && !defined(CONFIG_MITIGATION_CALL_DEPTH_TRACKING) && \
	!defined(CONFIG_CALL_DEPTH_TRACKING)
	{
		void *(*allocate_near)(unsigned long) =
			(void *)kallsyms_lookup_name("module_alloc");
		kd_near_memfree = (void *)kallsyms_lookup_name("module_memfree");

		if (allocate_near && kd_near_memfree)
			for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
				void *block = allocate_near(KD_CODE_BLOCK_SIZE);

				if (!block)
					break;
				ret = set_memory_x((unsigned long)block, KD_CODE_BLOCK_PAGES);
				if (ret) {
					kd_near_memfree(block);
					break;
				}
				kd_near_block_allocations[kd_near_block_free] = block;
				kd_near_block_pool[kd_near_block_free++] = block;
			}
	}
#endif
	KD_PR_INFO("JIT direct-call pool ready: %d/%d; shared image limit=%d\n",
		   kd_near_block_free, KD_CODE_BLOCK_POOL, KD_CODE_BLOCK_POOL);

	return 0;
}

void kd_exe_exit(void)
{
	int i;

	kd_jit_timing_report();
	KD_PR_INFO(
		"kd_hostcall stats: exits=%lld executed=%lld resumed=%lld rejected=%lld failed=%lld limit=%lld\n",
		(long long)atomic64_read(&kd_hostcall_exits),
		(long long)atomic64_read(&kd_hostcall_executed),
		(long long)atomic64_read(&kd_hostcall_resumed),
		(long long)atomic64_read(&kd_hostcall_rejected),
		(long long)atomic64_read(&kd_hostcall_failed),
		(long long)atomic64_read(&kd_hostcall_limit));
	KD_PR_INFO("kd_direct_call stats: strcmp=%lld strscpy_pad=%lld\n",
		(long long)atomic64_read(&kd_direct_strcmp),
		(long long)atomic64_read(&kd_direct_pad));
	KD_PR_INFO(
		"kd_mutex stack checks: bytes=%u equal=%lld changed=%lld unavailable=%lld\n",
		KD_MUTEX_CALL_STACK_BYTES,
		(long long)atomic64_read(&kd_mutex_stack_equal),
		(long long)atomic64_read(&kd_mutex_stack_changed),
		(long long)atomic64_read(&kd_mutex_stack_unavailable));

	vfree(kd_exes);
	kd_exes = NULL;
	memset(kd_published_images, 0, sizeof(kd_published_images));
	memset(kd_images, 0, sizeof(kd_images));

	for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
		vfree(kd_code_block_allocations[i]);
		kd_code_block_allocations[i] = NULL;
		kd_code_block_pool[i] = NULL;
		if (kd_near_block_allocations[i])
			kd_near_memfree(kd_near_block_allocations[i]);
		kd_near_block_allocations[i] = NULL;
		kd_near_block_pool[i] = NULL;
	}
	kd_code_block_free = 0;
	kd_near_block_free = 0;
	kd_near_memfree = NULL;
}
