/*
 * Mutex hook ownership and nested CALL admission/cleanup against real owners.
 * Private implementation included only by kd_lock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* ==========================================================================
 * Mutex hooks
 * ========================================================================== */

/* Native owner bits are only inspected; delegation never changes the owner. */
#define KD_MUTEX_OWNER_FLAGS 0x7UL

bool kd_origin_mutex_owned(struct mutex *lock, struct task_struct *task)
{
	return (atomic_long_read(&lock->owner) & ~KD_MUTEX_OWNER_FLAGS) ==
	       (unsigned long)task;
}

static void kd_mutex_lock_entry(struct mutex *lock, unsigned long ret_rsp,
		unsigned long ret_addr, unsigned long bp, enum kd_entry_abi abi)
{
	struct kd_mutex *kd_mtx;
	bool admitted;
	/* The legacy kernel hook already saved the caller on its native stack.
	 * execute_cs reads that authoritative frame. The clobber bridge supplies
	 * IP/SP/BP explicitly; neither ABI needs a second hook snapshot. */

	/* Native ownership is authoritative even after a shadow has been created.
	 * A free original mutex needs no admission, task record or translation.
	 * The short pin ties the approximate entry/contention counts to one CPU;
	 * release it before any native slowpath is allowed to sleep. */
	might_sleep();
	preempt_disable();
	kd_hotlock_mutex_entry_pinned();
	if (kd_mutex_trylock_fast(lock)) {
		preempt_enable();
		return;
	}
	admitted = kd_hotlock_record_mutex((unsigned long)lock);
	preempt_enable();
	/* Only failed acquisitions supply contention observations. Frequency
	 * checks still precede process selection and any task/shadow work. */
	if (!admitted) {
		kd_origin_mutex_lock(lock);
		return;
	}
	/* Nested native calls and borrowed continuations must not join another
	 * delegation queue. Their original mutexes still provide mutual exclusion. */
	if (!kd_source_is_open() ||
	    !kd_comm_matches(&kd_spin_target, current->comm) ||
	    kd_mutex_task_active(current)) {
		kd_origin_mutex_lock(lock);
		return;
	}
	if (!kd_mutex_jit_is_enabled()) {
		kd_origin_mutex_lock(lock);
		return;
	}

	kd_mtx = get_kd_mutex_shadow(lock);
	if (!kd_mtx || !kd_mutex_task_get(current)) {
		/* Distinguish shadow exhaustion from task allocation refusal and
		 * node shortage. Neither branch acquired a routing reference. */
		if (kd_mtx)
			KD_PR_INFO(
				"mutex task fallback: task=%d entry=%lx lock=%px cpu=%u\n",
				current->pid, ret_addr, lock,
				raw_smp_processor_id());
		else
			KD_PR_INFO(
				"mutex shadow fallback: task=%d entry=%lx lock=%px cpu=%u\n",
				current->pid, ret_addr, lock,
				raw_smp_processor_id());
		kd_origin_mutex_lock(lock);
		return;
	}
	kd_exe_add_abi(0, ret_addr, KD_EXE_LOCK_MUTEX, abi);
	_kd_mutex_lock_abi(kd_mtx, ret_rsp, ret_addr, bp, abi);
}

void __kd_mutex_lock(struct mutex *lock, unsigned long ret_rsp,
		     unsigned long ret_addr)
{
	kd_mutex_lock_entry(lock, ret_rsp, ret_addr, 0, KD_ENTRY_ABI_LEGACY);
}

void __kd_mutex_lock_clobber_v1(struct mutex *lock, unsigned long sp,
			       unsigned long ip, unsigned long bp)
{
	kd_mutex_lock_entry(lock, sp, ip, bp, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
}

/* A borrowed unlock is a request, not permission to unlock another task's
 * Linux mutex. Queue owners also have bookkeeping beyond the native unlock. */
void __kd_mutex_unlock(struct mutex *lock, unsigned long ret_rsp,
		       unsigned long ret_addr)
{
	struct kd_mutex *kd_mtx;

	(void)ret_rsp;
	/* Always reached, even after CPU cooling, rename or source closing. Task
	 * membership is an ownership lookup here, not a fresh-admission filter. */
	if (!kd_mutex_task_reroute(current)) {
		kd_origin_mutex_unlock(lock, ret_addr);
		return;
	}
	if (kd_exec_native_unlock((unsigned long)lock, true))
		return;
	kd_mtx = find_kd_mutex_shadow(lock);
	if (kd_mtx && READ_ONCE(kd_mtx->physical_owner) == current) {
		_kd_mutex_unlock(kd_mtx);
		kd_mutex_task_put(current);
		return;
	}
	kd_origin_mutex_unlock(lock, ret_addr);
}

void __kd_mutex_unlock_clobber_v1(struct mutex *lock, unsigned long sp,
				 unsigned long ip, unsigned long bp)
{
	(void)bp;
	__kd_mutex_unlock(lock, sp, ip);
}

/* Explicit module callers work with global interception disabled. Keep the
 * captured kernel bridge aliases above for existing generic FULL exits. */
__attribute__((noipa)) noinline notrace void
kd_mutex_direct_lock_clobber_v1(struct mutex *lock, unsigned long sp,
			      unsigned long ip, unsigned long bp)
{
	kd_mutex_lock_entry(lock, sp, ip, bp, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
}
EXPORT_SYMBOL_GPL(kd_mutex_direct_lock_clobber_v1);

__attribute__((noipa)) noinline notrace void
kd_mutex_direct_unlock_clobber_v1(struct mutex *lock, unsigned long sp,
				unsigned long ip, unsigned long bp)
{
	__kd_mutex_unlock(lock, sp, ip);
}
EXPORT_SYMBOL_GPL(kd_mutex_direct_unlock_clobber_v1);

int kd_mutex_prepare(struct mutex *lock, unsigned long ip, unsigned int abi)
{
	struct kd_exe_info *exe;

	if (!lock || !ip || abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1)
		return -EINVAL;
	if (!kd_source_is_open())
		return -ESHUTDOWN;
	kd_exe_add_abi(0, ip, KD_EXE_LOCK_MUTEX, abi);
	exe = kd_get_exe(0, ip);
	if (!exe || smp_load_acquire(&exe->status_code) == KD_EXE_UNUSED ||
	    exe->RIP != ip || exe->entry_abi != abi ||
	    exe->lock_kind != KD_EXE_LOCK_MUTEX || !exe->code_block)
		return -EINVAL;
	return READ_ONCE(exe->status_code) == KD_EXE_NATIVE_ONLY ? -EOPNOTSUPP : 0;
}
EXPORT_SYMBOL_GPL(kd_mutex_prepare);

static int kd_jit_begin_call(struct kd_exec_frame *frame, struct kd_regs *regs)
{
	if (!frame || !regs || !regs->sp || !kd_exec_frame_validate(frame))
		return -EINVAL;
	return kd_call_begin(&frame->control_call, regs->ip, regs->sp,
			     READ_ONCE(*(unsigned long *)regs->sp));
}

static int kd_jit_advance_call(struct kd_exec_frame *frame,
			       struct kd_regs *regs)
{
	unsigned long return_ip;

	if (!frame || !regs || !regs->sp)
		return -EINVAL;
	return_ip = READ_ONCE(*(unsigned long *)regs->sp);
	if (!return_ip)
		return -EINVAL;
	regs->sp += sizeof(unsigned long);
	regs->ip = return_ip;
	kd_exec_frame_save_continuation(frame, regs);
	return 0;
}

int kd_mutex_jit_nested_lock_ctx(struct mutex *lock, struct kd_regs *regs,
				 struct kd_exec_frame *frame)
{
	int ret;

	if (!lock || !regs || !regs->sp || !frame ||
	    !kd_exec_frame_validate(frame))
		return -EINVAL;
	ret = kd_jit_begin_call(frame, regs);
	if (ret)
		return ret;
	if (kd_exec_frame_lock_contains(frame, (unsigned long)lock))
		return -EDEADLK;
	if (kd_exec_frame_lock_depth(frame) >= KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;
	if (!READ_ONCE(*(unsigned long *)regs->sp))
		return -EINVAL;
	ret = kd_exec_frame_record_event(frame, KD_EXEC_EVENT_NESTED_LOCK,
					 regs);
	if (ret)
		return ret;
	if (unlikely(cmpxchg(&kd_jit_fail_pending_lock, 2, 0) == 2))
		return -E2BIG;

	frame->control_call.phase = KD_CALL_ENTERED;
	ret = kd_mutex_nested_lock(lock);
	if (ret)
		return ret;
	frame->control_call.phase = KD_CALL_ACQUIRED;
	ret = kd_exec_frame_lock_push(frame, (unsigned long)lock,
				      KD_EXEC_LOCK_NATIVE, lock);
	if (ret) {
		BUG_ON(kd_mutex_nested_unlock(lock));
		return ret;
	}
	/* The CALL is consumed only after the physical lock and its record exist. */
	ret = kd_jit_advance_call(frame, regs);
	if (!ret)
		frame->control_call.phase = KD_CALL_COMPLETE;
	return ret ? ret : 1;
}

int kd_mutex_jit_nested_unlock_ctx(struct mutex *lock,
				   struct kd_exec_frame *frame)
{
	int ret;

	if (!lock || !frame || !kd_exec_frame_validate(frame))
		return -EINVAL;
	if (kd_exec_frame_lock_kind(frame, (unsigned long)lock) !=
		    KD_EXEC_LOCK_NATIVE ||
	    kd_exec_frame_lock_node(frame, (unsigned long)lock) != lock)
		return -ENOENT;
	ret = kd_exec_frame_record_event(frame, KD_EXEC_EVENT_NESTED_UNLOCK,
					 NULL);
	if (ret)
		return ret;
	ret = kd_mutex_nested_unlock(lock);
	return ret ? ret : kd_exec_frame_lock_pop(frame, (unsigned long)lock);
}

int kd_mutex_jit_abort_cleanup(struct kd_exec_frame *frame)
{
	if (!frame || !kd_exec_frame_validate(frame) ||
	    frame->outer_lock_index >= frame->jit_lock_depth)
		return -EINVAL;

	while (frame->jit_lock_depth > frame->outer_lock_index + 1) {
		unsigned int i = frame->jit_lock_depth - 1;
		struct mutex *lock = (struct mutex *)frame->jit_lock_addr[i];
		int ret;

		if (frame->jit_lock_kind[i] != KD_EXEC_LOCK_NATIVE ||
		    frame->jit_lock_node[i] != lock)
			return -EINVAL;
		if (!frame->jit_lock_released[i]) {
			ret = kd_mutex_nested_unlock(lock);
			if (ret)
				return ret;
			kd_mutex_note_nested_abort_release();
		}
		ret = kd_exec_frame_lock_pop(frame, (unsigned long)lock);
		if (ret)
			return ret;
	}
	return 0;
}

int kd_mutex_debug_waiter_count(struct mutex *lock)
{
	struct kd_mutex *kd_mtx;

	if (!lock)
		return -EINVAL;
	kd_mtx = find_kd_mutex_shadow(lock);
	return kd_mtx ? kd_mutex_waiter_count(kd_mtx) : -ENOENT;
}
EXPORT_SYMBOL_GPL(kd_mutex_debug_waiter_count);
