/* Wrapper scope, image identity and reduced-entry/batch preparation.
 * Private to exe.c; the dispatcher consumes only validated packet states. */
/* Only abnormal exits log here. Saved flags are not live execution evidence. */
static void kd_jit_log_hl_error(const char *reason,
				const struct kd_exec_frame *frame,
				const struct kd_regs *regs,
				unsigned long raw_exit, long detail,
				int continuations, int hostcalls)
{
	pr_err_ratelimited(
		"[KD_JIT][ERROR] reason=%s path=high entry=0x%lx rip=0x%lx executor_pid=%d waiter_pid=%d outer=0x%lx depth=%u raw_exit=0x%lx detail=%ld continuations=%d hostcalls=%d continuation_limit=%d hostcall_limit=%d control_phase=%u\n",
		reason, frame->entry_ip, regs->ip, current->pid,
		frame->logical_task->pid, frame->outer_lock_addr, frame->depth,
		raw_exit, detail, continuations, hostcalls,
		KD_EXE_HL_MAX_CONTINUATIONS, KD_EXE_HL_MAX_HOSTCALLS,
		frame->control_call.phase);
}

/* A non-root first dispatch is valid only for the published logical child of
 * a root invocation which already returned through a known lock CALL. A CPU-
 * local physical parent is not that proof. This establishes logical scope,
 * not immutable code identity; in-place publication remains a separate limit.
 */
static bool kd_jit_entry_has_scope(const struct kd_exec_frame *frame,
				   const struct kd_regs *regs,
				   unsigned long entry_ip)
{
	const struct kd_exec_frame *parent = frame->resume_target;

	if (!entry_ip || !regs->sp || frame->executed ||
	    kd_exec_frame_state(frame) != KD_EXEC_FRAME_RUNNING ||
	    frame->outer_unlock_seen || frame->entry_ip != entry_ip ||
	    frame->control_call.phase != KD_CALL_NONE)
		return false;
	if (!parent)
		return regs->ip == entry_ip;
	if (parent == frame || frame->mutex_backend ||
	    smp_load_acquire(&parent->remote_result) != KD_EXEC_REMOTE_WAITING)
		return false;
	return kd_exec_frame_validate(parent) && !parent->mutex_backend &&
	       !parent->completion_seen &&
	       kd_exec_frame_state(parent) != KD_EXEC_FRAME_ERROR &&
	       parent->executed && parent->entry_ip == entry_ip &&
	       parent->logical_task == frame->logical_task &&
	       parent->gsbase == frame->gsbase &&
	       parent->control_call.phase == KD_CALL_ENTERED &&
	       parent->control_call.return_ip == regs->ip &&
	       parent->control_call.stack + sizeof(unsigned long) == regs->sp &&
	       parent->delegated_lock_addr == frame->outer_lock_addr &&
	       parent->outer_lock_index < frame->outer_lock_index;
}

/* The excess CALL has not executed: retain its pushed return word and let the
 * original waiter run this callee and the native suffix. This is not an exit
 * from an arbitrary instruction/budget trap and needs no new flags contract. */
static int kd_jit_call_limit_native(struct kd_exec_frame *frame,
				    struct kd_regs *regs, bool hostcall)
{
	unsigned long base, end, return_ip;
	int ret;

	if (!regs || !regs->ip || !kd_exec_frame_can_borrow_locks(frame) ||
	    !frame->executed || frame->logical_task == current ||
	    kd_exec_frame_remote_pending(frame) || frame->remote_request ||
	    frame->native_request ||
	    (frame->control_call.phase != KD_CALL_NONE &&
	     frame->control_call.phase != KD_CALL_COMPLETE))
		return -EINVAL;
	if (hostcall) {
		ret = kd_hostcall_validate(kd_hostcall_lookup(regs->ip));
		if (ret)
			return ret;
	}
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return -EFAULT;
	end = base + THREAD_SIZE;
	if (regs->sp < base || regs->sp > end - sizeof(return_ip) ||
	    copy_from_kernel_nofault(&return_ip, (void *)regs->sp,
				     sizeof(return_ip)) || !return_ip)
		return -EFAULT;
	ret = kd_source_pin_target(regs->ip);
	if (!ret)
		ret = kd_source_pin_target(return_ip);
	if (ret)
		return ret;

	/* A previous control CALL may be COMPLETE; it does not describe this new
	 * unexecuted CALL. Do not pop the word, replay stores or request learning. */
	frame->control_call.phase = KD_CALL_NONE;
	kd_exec_frame_save_continuation(frame, regs);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=CALL_LIMIT_NATIVE entry=0x%lx ip=0x%lx sp=0x%lx return=0x%lx lock=0x%lx task=%d hostcall=%u\n",
		frame->entry_ip, regs->ip, regs->sp, return_ip,
		frame->outer_lock_addr, frame->logical_task->pid, hostcall);
	return 0;
}

/* Called after a real wrapper return, once per logical invocation. */
static void kd_exe_note_body(unsigned long entry_ip, unsigned long outer_lock_addr,
			     unsigned long witness)
{
	KD_PR_INFO("JIT body witness: entry=%lx lock=%lx body=%lu\n",
		   entry_ip, outer_lock_addr, witness);
}

/* This is a root-only admission, not a bypass around translated entry guards.
 * Source OPEN, slot key/backend/status/code and the versioned alternate entry
 * are checked for every candidate. Code storage remains pinned by the batch. */
static __always_inline bool kd_jit_image_matches(const struct kd_exe_info *exe,
                                 const struct kd_exec_frame *frame)
{
	const unsigned char *code = READ_ONCE(exe->code_block);
	/* Exact directory bytes, without the out-of-line seven-byte memcmp on
	 * every request. The overlapping words do not read beyond the signature. */
	bool directory = code && get_unaligned_le32(code + 25) == 0x4357444bU &&
	                 get_unaligned_le32(code + 28) == 0x32303043U &&
	                 get_unaligned_le32(code + 41) == 0x4241444bU;

	if (READ_ONCE(exe->entry_abi) != frame->entry_abi)
		return false;
	if (kd_entry_abi_spin_clobber(frame->entry_abi))
		return directory && code[KD_JIT_ABI_OFFSET] == frame->entry_abi &&
		       clobber_spin_lock_addr && clobber_spin_unlock_addr;
	if (frame->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1)
		return directory && code[KD_JIT_ABI_OFFSET] == frame->entry_abi &&
		       (frame->owned_mutex ? (owned_direct_lock_addr && owned_direct_unlock_addr) :
		(direct_mutex_lock_addr && direct_mutex_unlock_addr));
	return frame->entry_abi == KD_ENTRY_ABI_LEGACY &&
	       (!directory || code[KD_JIT_ABI_OFFSET] == KD_ENTRY_ABI_LEGACY);
}

/* Minimal completion is possible only on the first wrapper invocation of a
 * pristine physical root. A mutex root has a real owner ledger even before
 * its first body; subsequent nested/service exits always use FULL instead. */
static bool kd_jit_minimal_complete_allowed(const struct kd_exec_frame *frame)
{
	if (frame->parent || frame->depth)
		return false;
	if (kd_entry_abi_spin_clobber(frame->entry_abi))
		return !frame->mutex_backend && frame->spin_simple;
	return frame->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 &&
	       frame->mutex_backend && frame->jit_lock_depth == 1 &&
	       frame->outer_lock_index == 0 && !frame->outer_unlock_seen &&
	       !frame->jit_lock_released[0] && !frame->completion_seen &&
	       (!frame->complex_ready || !kd_exec_frame_remote_pending(frame));
}

static void kd_jit_prepare_clobber(struct kd_jit_batch_call *call,
                                  struct kd_exec_frame *frame, void *code)
{
	call->regs = kd_exec_frame_regs(frame);
	call->args[0] = frame->gsbase;
	call->args[1] = (unsigned long)frame->logical_task;
	call->code = (char *)code + KD_JIT_CLOBBER_OFFSET;
	call->lock = frame->outer_lock_addr;
	call->unlock = frame->owned_mutex ? owned_direct_unlock_addr :
		frame->mutex_backend ? direct_mutex_unlock_addr :
					     clobber_spin_unlock_addr;
	call->entry_sp = call->regs->sp;
	call->entry_abi = frame->entry_abi;
	call->packet_state = &frame->packet_state;
	call->complete = kd_jit_minimal_complete_allowed(frame);
}

/* GNU inline retains the external definition for other execution clients;
 * the shared spin compilation unit folds this into its resident batch loop. */
__always_inline __gnu_inline
bool kd_exe_spin_batch_prepare(struct kd_exe_info *exe,
			       struct kd_exec_frame *frame,
			       struct kd_jit_batch_call *call)
{
	void *code;
	struct kd_regs *regs = kd_exec_frame_regs(frame);
	bool clobber;

	if (!frame->spin_simple || frame->parent || frame->depth ||
	    !frame->request_frame || frame->mutex_backend || frame->complex_ready ||
	    frame->completion_seen || frame->state != KD_EXEC_FRAME_RUNNING ||
	    !frame->outer_lock_addr || !regs->sp || regs != &frame->regs ||
	    frame->executed || !frame->gsbase || !frame->logical_task ||
	    regs->ip != frame->entry_ip ||
	    !kd_exe_entry_is_ready(exe, 0, frame->entry_ip) ||
	    READ_ONCE(exe->lock_kind) != KD_EXE_LOCK_SPIN ||
	    !kd_jit_image_matches(exe, frame) ||
	    frame->packet_state != (frame->entry_abi == KD_ENTRY_ABI_LEGACY ?
	                          KD_PACKET_FULL : KD_PACKET_MINIMAL))
		return false;
	code = READ_ONCE(exe->code_block);
	/* Check exactly KDWB002: overlapping unaligned words cover bytes 9..15.
	 * This avoids the out-of-line seven-byte memcmp without reading byte 16. */
	if (!code || get_unaligned_le32((char *)code + 9) != 0x4257444bU ||
	    get_unaligned_le32((char *)code + 12) != 0x32303042U)
		return false;
	/* These admission checks already prove the simple spin root predicates
	 * required by kd_jit_minimal_complete_allowed. Select its final metadata
	 * once: do not fill the legacy call and then rewrite it via the general
	 * clobber helper, which still handles mutex and complex dispatch below. */
	clobber = kd_entry_abi_spin_clobber(frame->entry_abi);
	call->regs = regs;
	call->args[0] = frame->gsbase;
	call->args[1] = (unsigned long)frame->logical_task;
	call->code = (char *)code + (clobber ? KD_JIT_CLOBBER_OFFSET :
					   KD_JIT_BATCH_OFFSET);
	call->lock = frame->outer_lock_addr;
	call->unlock = clobber ? clobber_spin_unlock_addr : raw_spin_unlock_addr;
	call->entry_sp = regs->sp;
	call->entry_abi = frame->entry_abi;
	call->packet_state = &frame->packet_state;
	call->complete = clobber;
	/* The load-time timing switch is immutable during a session. Avoid
	 * two out-of-line disabled helpers for every ordinary delegated body,
	 * but retain distinct, ordered endpoints when timing is enabled. */
	if (unlikely(kd_jit_timing)) {
		call->dispatch_start = kd_jit_timing_start();
		call->wrapper_start = kd_jit_timing_start();
	} else {
		call->dispatch_start = 0;
		call->wrapper_start = 0;
	}
	return true;
}

__always_inline __gnu_inline
bool kd_exe_spin_batch_completed(const struct kd_jit_batch_call *call,
				 const struct kd_exec_frame *frame)
{
	if (kd_entry_abi_spin_clobber(call->entry_abi) ?
	    (call->args[0] != KD_EXE_CLOBBER_COMPLETE ||
	     *call->packet_state != KD_PACKET_COMPLETE || !call->complete) :
	    (call->args[0] != KD_EXE_CALL_MISS ||
	     call->regs->ip != call->unlock || call->regs->di != call->lock))
		return false;
	/* Only prepared batch calls reach here. Their local endpoint is zero
	 * exactly when the immutable timing policy is off; avoid reloading it. */
	if (unlikely(call->wrapper_start)) {
		kd_jit_timing_end(KD_JIT_TIME_WRAPPER, call->wrapper_start);
		kd_jit_timing_end(KD_JIT_TIME_DISPATCH, call->dispatch_start);
	}
	/* The batch retains this exact bound frame until retirement below. */
	if (call->args[1] == 1)
		kd_exe_note_body(frame->entry_ip, call->lock, call->args[1]);
	return true;
}

/* Mutex batches retain a full ownership ledger and a borrowed register packet.
 * Only pristine ABI2 roots use the short wrapper path. Every candidate still
 * checks OPEN, publication, backend and image ABI; a cached slot is no lease. */
__always_inline __gnu_inline
bool kd_exe_mutex_batch_prepare(struct kd_exe_info *exe,
	struct kd_exec_frame *frame, struct kd_jit_batch_call *call)
{
	struct kd_regs *regs = kd_exec_frame_regs(frame);

	if (!frame->mutex_backend || !frame->batch_lease ||
	    !frame->regs_borrowed || frame->spin_simple ||
	    frame->parent || frame->depth || frame->request_frame ||
	    frame->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	    frame->packet_state != KD_PACKET_MINIMAL || frame->executed ||
	    frame->state != KD_EXEC_FRAME_RUNNING || !frame->outer_lock_addr ||
	    !frame->gsbase || !frame->logical_task || !regs->sp ||
	    regs->ip != frame->entry_ip ||
	    (!frame->complex_ready &&
	     (!frame->jit_lock_node[0] || !frame->outer_unlock_hook)) ||
	    (frame->complex_ready && frame->control_call.phase != KD_CALL_NONE) ||
	    !kd_jit_minimal_complete_allowed(frame) ||
	    !kd_exe_entry_is_ready(exe, 0, frame->entry_ip) ||
	    READ_ONCE(exe->lock_kind) != (frame->owned_mutex ?
		KD_EXE_LOCK_OWNED_MUTEX : KD_EXE_LOCK_MUTEX) ||
	    !kd_jit_image_matches(exe, frame))
		return false;
	/* This pristine, exclusively bound root has just passed the complete
	 * ABI2/ledger predicate above. Fill its final transport directly rather
	 * than selecting the packet/backend and testing that predicate again in
	 * the general clobber preparer. Complex/FULL dispatch still uses that
	 * preparer and all completion/physical-owner retirement checks remain. */
	call->regs = regs;
	call->args[0] = frame->gsbase;
	call->args[1] = (unsigned long)frame->logical_task;
	call->code = (char *)READ_ONCE(exe->code_block) + KD_JIT_CLOBBER_OFFSET;
	call->lock = frame->outer_lock_addr;
	call->unlock = frame->owned_mutex ? owned_direct_unlock_addr : direct_mutex_unlock_addr;
	call->entry_sp = regs->sp;
	call->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	call->packet_state = &frame->packet_state;
	call->complete = true;
	if (unlikely(kd_jit_timing)) {
		call->dispatch_start = kd_jit_timing_start();
		call->wrapper_start = kd_jit_timing_start();
	} else {
		call->dispatch_start = 0;
		call->wrapper_start = 0;
	}
	return true;
}

__always_inline __gnu_inline
bool kd_exe_mutex_batch_completed(const struct kd_jit_batch_call *call,
	const struct kd_exec_frame *frame)
{
	if (call->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	    call->args[0] != KD_EXE_CLOBBER_COMPLETE || !call->complete ||
	    *call->packet_state != KD_PACKET_COMPLETE)
		return false;
	if (unlikely(call->wrapper_start)) {
		kd_jit_timing_end(KD_JIT_TIME_WRAPPER, call->wrapper_start);
		kd_jit_timing_end(KD_JIT_TIME_DISPATCH, call->dispatch_start);
	}
	if (call->args[1] == 1)
		kd_exe_note_body(frame->entry_ip, call->lock, call->args[1]);
	return true;
}

/* One logical invocation may cross several control/hostcall wrapper returns.
 * Keep exit classification here: backends must not infer replay permission
 * from an error number or from the optional generated-body witness. */
