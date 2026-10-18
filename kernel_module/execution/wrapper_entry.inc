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
 * not immutable code identity; mutex frames bind a published image separately.
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

static int kd_hostcall_strcmp_text(unsigned long address)
{
	static const unsigned char expected[KD_STRCMP_CODE_BYTES] =
		KD_STRCMP_CODE_TEMPLATE;
	static const unsigned char patched_return[5] = KD_STRCMP_RETURN_TEMPLATE;
	static const unsigned int tails[] = { KD_STRCMP_TAIL1_DISP, KD_STRCMP_TAIL2_DISP };
	unsigned char actual[KD_STRCMP_CODE_BYTES];
	unsigned int i;
	int ret;

	if (!address || address > ~0UL - sizeof(actual))
		return -EINVAL;
	ret = kd_source_pin_target(address);
	if (ret)
		return ret;
	if (copy_from_kernel_nofault(actual, (void *)address, sizeof(actual)))
		return -EFAULT;
	for (i = 0; i < sizeof(actual); i++) {
		if ((i >= KD_STRCMP_TAIL1_DISP - 1 && i < KD_STRCMP_TAIL1_DISP + 4) ||
		    (i >= KD_STRCMP_TAIL2_DISP - 1 && i < KD_STRCMP_TAIL2_DISP + 4))
			continue;
		if (actual[i] != expected[i])
			return -ESTALE;
	}
	for (i = 0; i < ARRAY_SIZE(tails); i++) {
		unsigned int offset = tails[i];

		/* The captured kernel alternatives replace a thunk JMP by RET and
		 * four INT3 padding bytes. Accept that exact five-byte form only. */
		if (!memcmp(actual + offset - 1, patched_return, sizeof(patched_return)))
			continue;
		if (actual[offset - 1] != 0xe9 || !kd_string_return_thunk ||
		    address + offset + 4 + (long)(int)get_unaligned_le32(actual + offset) !=
			kd_string_return_thunk)
			return -ESTALE;
		ret = kd_source_pin_target(kd_string_return_thunk);
		if (ret)
			return ret;
	}
	return 0;
}

/* Read only through the first NUL, never beyond the negotiated byte bound.
 * A failed read or absent terminator has made no helper/packet side effects. */
static int kd_hostcall_string_preflight(unsigned long address)
{
	unsigned int i;
	unsigned char value;

	if ((long)address >= 0 || address > ~0UL - (KD_STRCMP_MAX_BYTES - 1))
		return KD_HOSTCALL_NOT_EXECUTED;
	for (i = 0; i < KD_STRCMP_MAX_BYTES; i++) {
		if (copy_from_kernel_nofault(&value, (void *)(address + i), 1))
			return KD_HOSTCALL_NOT_EXECUTED;
		if (!value)
			return 0;
	}
	return KD_HOSTCALL_NOT_EXECUTED;
}

/* Normalize only declared relative displacements after checking their exact
 * targets. All remaining helper bytes, including branches and CPU alternatives,
 * must match the leased live-kernel contract before any destination write. */
static int kd_hostcall_string_text_match(unsigned long address,
		const unsigned char *expected, unsigned int size,
		const unsigned int *offsets, const unsigned long *targets,
		unsigned int count, unsigned long short_target)
{
	unsigned char actual[KD_STRSCPY_CODE_BYTES];
	unsigned int i, j;
	int ret;

	if (!address || !size || size > sizeof(actual) || address > ~0UL - size || count > 3)
		return -EINVAL;
	ret = kd_source_pin_target(address);
	if (ret)
		return ret;
	if (copy_from_kernel_nofault(actual, (void *)address, size))
		return -EFAULT;
	for (i = 0; i < count; i++) {
		unsigned int offset = offsets[i];

		if (!targets[i] || size < 4 || offset > size - 4 ||
		    address + offset + 4 + (long)(int)get_unaligned_le32(actual + offset) != targets[i])
			return -ESTALE;
		for (j = 0; j < 4; j++)
			actual[offset + j] = 0;
	}
	if (short_target) {
		if (size != KD_STRSCPY_MEMSET_ENTRY_BYTES ||
		    address + size + (long)(signed char)actual[size - 1] != short_target)
			return -ESTALE;
		actual[size - 1] = 0;
	}
	return memcmp(actual, expected, size) ? -ESTALE : 0;
}

static int kd_hostcall_strscpy_text(unsigned long address)
{
	static const unsigned char pad[] = KD_STRSCPY_PAD_CODE_TEMPLATE;
	static const unsigned char copy[] = KD_STRSCPY_CODE_TEMPLATE;
	static const unsigned char fill_entry[] = KD_STRSCPY_MEMSET_ENTRY_TEMPLATE;
	static const unsigned char fill[] = KD_STRSCPY_MEMSET_ERMS_TEMPLATE;
	static const unsigned char returned[] = { 0xc3 };
	static const unsigned int pad_offsets[] = {
		KD_STRSCPY_PAD_CALL1_DISP, KD_STRSCPY_PAD_CALL2_DISP, KD_STRSCPY_PAD_RETURN_DISP };
	static const unsigned int copy_offsets[] = {
		KD_STRSCPY_RETURN1_DISP, KD_STRSCPY_RETURN2_DISP, KD_STRSCPY_RETURN3_DISP };
	static const unsigned int fill_offsets[] = { KD_STRSCPY_MEMSET_RETURN_DISP };
	const unsigned long pad_targets[] = {
		kd_string_copy_helper, kd_string_memset_entry, kd_string_its_return };
	const unsigned long copy_targets[] = {
		kd_string_its_return, kd_string_its_return, kd_string_its_return };
	const unsigned long fill_targets[] = { kd_string_its_return };
	int ret;

	if (!kd_string_copy_helper || !kd_string_memset_entry ||
	    !kd_string_memset_erms || !kd_string_its_return)
		return -ENOENT;
	ret = kd_hostcall_string_text_match(address, pad, sizeof(pad),
		pad_offsets, pad_targets, ARRAY_SIZE(pad_offsets), 0);
	if (!ret)
		ret = kd_hostcall_string_text_match(kd_string_copy_helper, copy, sizeof(copy),
			copy_offsets, copy_targets, ARRAY_SIZE(copy_offsets), 0);
	if (!ret)
		ret = kd_hostcall_string_text_match(kd_string_memset_entry, fill_entry,
			sizeof(fill_entry), NULL, NULL, 0, kd_string_memset_erms);
	if (!ret)
		ret = kd_hostcall_string_text_match(kd_string_memset_erms, fill, sizeof(fill),
			fill_offsets, fill_targets, ARRAY_SIZE(fill_offsets), 0);
	if (!ret)
		ret = kd_hostcall_string_text_match(kd_string_its_return, returned,
			sizeof(returned), NULL, NULL, 0, 0);
	return ret;
}

static int kd_hostcall_strscpy_preflight(const struct kd_regs *regs,
					unsigned long base, unsigned long end)
{
	unsigned char word[sizeof(unsigned long)];
	unsigned int i, j;

	/* The destination excludes the pending CALL, saved BP/return and every
	 * older frame. Source must not alias the original helper's discarded
	 * stack spills either, so exclude the waiter's entire stack allocation. */
	if (regs->dx != KD_STRSCPY_BYTES || regs->bp < regs->sp + sizeof(unsigned long) ||
	    regs->bp > end - 2 * sizeof(unsigned long) ||
	    regs->bp < KD_STRSCPY_BYTES || regs->di < regs->sp + sizeof(unsigned long) ||
	    regs->di > regs->bp - KD_STRSCPY_BYTES || (long)regs->si >= 0 ||
	    regs->si > ~0UL - KD_STRSCPY_BYTES ||
	    (regs->si < end && regs->si + KD_STRSCPY_BYTES > base))
		return KD_HOSTCALL_NOT_EXECUTED;
	/* The reviewed implementation reads whole eight-byte words, including
	 * bytes after NUL in its last word. Check that exact read extent first. */
	for (i = 0; i < KD_STRSCPY_BYTES; i += sizeof(word)) {
		if (copy_from_kernel_nofault(word, (void *)(regs->si + i), sizeof(word)))
			return KD_HOSTCALL_NOT_EXECUTED;
		for (j = 0; j < sizeof(word); j++)
			if (!word[j])
				return 0;
	}
	return KD_HOSTCALL_NOT_EXECUTED;
}

/* Validate before executing a memory-reading service. Keep the actual pushed
 * CALL word in place until success; refusal can still resume that exact callee
 * natively. Successful completion consumes this already checked return token,
 * never a newly discovered target after the helper's effects. */
static int kd_jit_string_prepare(struct kd_exe_info *exe,
				 struct kd_exec_frame *frame, struct kd_regs *regs,
				 unsigned long *return_ip)
{
	const struct kd_hostcall_desc *service;
	unsigned long base, end;
	unsigned char call[5];
	int ret;

	if (!exe || !frame || !regs || frame->mutex_backend ||
	    frame->entry_abi != KD_ENTRY_ABI_SPIN_CLOBBER_V1 ||
	    frame->packet_state != KD_PACKET_FULL || !frame->image ||
	    !frame->image->immutable || frame->image->entry != exe ||
	    frame->image->entry_abi != frame->entry_abi ||
	    !kd_exec_frame_can_borrow_locks(frame) || !frame->executed ||
	    frame->logical_task == current || frame->parent || frame->depth ||
	    frame->resume_target || frame->outer_unlock_seen ||
	    frame->jit_lock_depth != 1 || frame->outer_lock_index != 0 ||
	    kd_exec_frame_remote_pending(frame) || frame->remote_request ||
	    frame->native_request ||
	    (frame->control_call.phase != KD_CALL_NONE &&
	     frame->control_call.phase != KD_CALL_COMPLETE))
		return -EINVAL;
	service = kd_hostcall_lookup(regs->ip);
	ret = kd_hostcall_validate(service);
	if (ret || (service->id != KD_HOSTCALL_STRCMP && service->id != KD_HOSTCALL_STRSCPY_PAD))
		return ret ? ret : -EINVAL;
	if (!(frame->image->requirements & (service->id == KD_HOSTCALL_STRCMP ?
		KD_IMAGE_REQUIRE_STRING_SERVICES : KD_IMAGE_REQUIRE_STRING_WRITE)))
		return -EPROTO;
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return -EFAULT;
	end = base + THREAD_SIZE;
	/* Existing spin native restoration needs scratch words below source SP. */
	if (regs->sp < base + 4 * sizeof(unsigned long) ||
	    regs->sp > end - sizeof(*return_ip) ||
	    copy_from_kernel_nofault(return_ip, (void *)regs->sp,
				     sizeof(*return_ip)) || !*return_ip)
		return -EFAULT;
	ret = kd_source_pin_target(*return_ip);
	if (!ret)
		ret = *return_ip >= sizeof(call) ?
			kd_source_pin_target(*return_ip - sizeof(call)) : -EINVAL;
	if (ret)
		return ret;
	if (copy_from_kernel_nofault(call, (void *)(*return_ip - sizeof(call)),
				     sizeof(call)) || call[0] != 0xe8 ||
	    *return_ip + (long)(int)get_unaligned_le32(call + 1) != regs->ip)
		return -EPROTO;
	ret = service->id == KD_HOSTCALL_STRCMP ? kd_hostcall_strcmp_text(regs->ip) :
		kd_hostcall_strscpy_text(regs->ip);
	if (ret)
		return ret;
	if (service->id == KD_HOSTCALL_STRSCPY_PAD)
		return kd_hostcall_strscpy_preflight(regs, base, end);
	ret = kd_hostcall_string_preflight(regs->di);
	return ret ? ret : kd_hostcall_string_preflight(regs->si);
}

/* Verify the same exact, unprefixed instruction families as admission. This
 * is not a decoder for arbitrary failed code. The instruction itself has not
 * executed, and neither a CALL word nor its return address may be consumed. */
static int kd_jit_native_escape_opcode(unsigned long ip)
{
	unsigned char opcode[3];

	if (copy_from_kernel_nofault(opcode, (void *)ip, 1))
		return -EFAULT;
	if (opcode[0] == 0xfa || opcode[0] == 0xfb ||
	    opcode[0] == 0xfc || opcode[0] == 0xfd ||
	    opcode[0] == 0x9e || opcode[0] == 0x9f)
		return 0; /* CLI/STI, CLD/STD, SAHF/LAHF */
	if (opcode[0] != 0x0f ||
	    copy_from_kernel_nofault(opcode + 1, (void *)(ip + 1), 1))
		return -EILSEQ;
	if (opcode[1] == 0x31 || opcode[1] == 0xa2 ||
	    opcode[1] == 0x30 || opcode[1] == 0x32 || opcode[1] == 0x33)
		return 0; /* RDTSC, CPUID, WRMSR/RDMSR/RDPMC */
	if (opcode[1] == 0x01 &&
	    !copy_from_kernel_nofault(opcode + 2, (void *)(ip + 2), 1) &&
	    opcode[2] == 0xf9)
		return 0; /* RDTSCP */
	return -EILSEQ;
}

static int kd_jit_native_escape(struct kd_exe_info *exe,
				struct kd_exec_frame *frame, struct kd_regs *regs)
{
	unsigned long base, end;
	int ret;

	if (!exe || !frame || !regs || !frame->mutex_backend ||
	    frame->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	    frame->packet_state != KD_PACKET_FULL || !frame->image ||
	    frame->image->entry != exe ||
	    !(frame->image->requirements & KD_IMAGE_REQUIRE_NATIVE_ESCAPE) ||
	    !kd_exec_frame_can_borrow_locks(frame) || !frame->executed ||
	    frame->logical_task == current || !regs->ip || !regs->sp ||
	    kd_exec_frame_remote_pending(frame) || frame->remote_request ||
	    frame->native_request ||
	    (frame->control_call.phase != KD_CALL_NONE &&
	     frame->control_call.phase != KD_CALL_COMPLETE) || !(regs->flags & 2))
		return -EINVAL;
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return -EFAULT;
	end = base + THREAD_SIZE;
	/* The final restore pushes IP and merged flags below the virtual SP.
	 * Require those words and the caller's live stack to remain in bounds. */
	if (regs->sp < base + 2 * sizeof(unsigned long) ||
	    regs->sp > end - sizeof(unsigned long))
		return -EFAULT;
	ret = kd_source_pin_target(regs->ip);
	if (!ret)
		ret = kd_jit_native_escape_opcode(regs->ip);
	if (ret)
		return ret;

	/* The earlier control operation is complete; this is a new instruction
	 * boundary. Preserve its exact SP and all preceding side effects. */
	frame->control_call.phase = KD_CALL_NONE;
	regs->orig_ax = KD_REG_NATIVE_ESCAPE_TAG;
	kd_exec_frame_save_continuation(frame, regs);
	kd_image_disable(exe);
	atomic64_inc(&kd_native_escape_count);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=NATIVE_ESCAPE entry=0x%lx rip=0x%lx generation=%lu waiter_pid=%d action=native_suffix_and_disable\n",
		frame->entry_ip, regs->ip, frame->image->generation,
		frame->logical_task->pid);
	return 0;
}

/* Only a published MOV-load predicate can request this continuation. Source
 * flags are dead along every admitted successor before a flag read, proved by
 * the translator; the ordinary spin restore therefore needs no flags merge.
 * Preserve the exact instruction/SP and all prior stores: this is not a CALL
 * miss, a fault recovery path, or permission to replay the critical section. */
static int kd_jit_address_guard(struct kd_exe_info *exe,
			       struct kd_exec_frame *frame, struct kd_regs *regs)
{
	const struct kd_address_guard_site *sites, *site;
	unsigned int count, index;
	unsigned long base, end;
	unsigned char opcode[16];
	int ret;

	if (!exe || !frame || !regs || frame->mutex_backend ||
	    frame->entry_abi != KD_ENTRY_ABI_SPIN_CLOBBER_V1 ||
	    frame->packet_state != KD_PACKET_FULL || !frame->image ||
	    !frame->image->immutable || frame->image->entry != exe ||
	    frame->image->entry_abi != frame->entry_abi ||
	    !kd_exec_frame_can_borrow_locks(frame) || !frame->executed ||
	    frame->logical_task == current || frame->parent || frame->depth ||
	    frame->resume_target || frame->outer_unlock_seen ||
	    frame->jit_lock_depth != 1 || frame->outer_lock_index != 0 ||
	    kd_exec_frame_remote_pending(frame) || frame->remote_request ||
	    frame->native_request ||
	    (frame->control_call.phase != KD_CALL_NONE &&
	     frame->control_call.phase != KD_CALL_COMPLETE) ||
	    (regs->orig_ax & KD_REG_ADDRESS_GUARD_MASK) != KD_REG_ADDRESS_GUARD_TAG)
		return -EINVAL;
	sites = kd_image_guard_sites(frame->image, &count);
	index = (unsigned int)regs->orig_ax;
	if (!sites || index >= count)
		return -EPROTO;
	site = &sites[index];
	if (!kd_image_guard_site_valid(site) || regs->ip != site->ip)
		return -EPROTO;
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return -EFAULT;
	end = base + THREAD_SIZE;
	/* The existing original-waiter restore uses temporary words below SP.
	 * Retain the live caller stack and enough room for that exact sequence. */
	if (regs->sp < base + 4 * sizeof(unsigned long) ||
	    regs->sp > end - sizeof(unsigned long))
		return -EFAULT;
	ret = kd_source_pin_target(regs->ip);
	if (ret)
		return ret;
	if (copy_from_kernel_nofault(opcode, (void *)regs->ip, site->length) ||
	    memcmp(opcode, site->opcode, site->length))
		return -EILSEQ;
	frame->control_call.phase = KD_CALL_NONE;
	regs->orig_ax = 0;
	kd_exec_frame_save_continuation(frame, regs);
	kd_image_disable(exe);
	atomic64_inc(&kd_address_guard_count);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=ADDRESS_GUARD entry=0x%lx rip=0x%lx generation=%lu waiter_pid=%d action=native_suffix_and_disable\n",
		frame->entry_ip, regs->ip, frame->image->generation,
		frame->logical_task->pid);
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
static void *kd_jit_bound_code(const struct kd_exe_info *exe,
                               const struct kd_exec_frame *frame)
{
	(void)exe;
	return frame->image ? frame->image->code : NULL;
}

static const struct kd_jit_image *kd_jit_select_image(const struct kd_exe_info *exe,
						     const struct kd_exec_frame *frame)
{
	const struct kd_jit_image *image;

	image = frame->image ? frame->image : kd_image_current(exe);
	if (!image || image->entry != exe ||
	    image->entry_abi != frame->entry_abi ||
	    !kd_image_requirements_valid(frame->mutex_backend ? KD_EXE_LOCK_MUTEX :
					KD_EXE_LOCK_SPIN, frame->entry_abi,
					image->requirements))
		return NULL;
	return image;
}

static inline bool kd_jit_bind_image(const struct kd_exe_info *exe,
			      struct kd_exec_frame *frame)
{
	const struct kd_jit_image *image = kd_jit_select_image(exe, frame);

	if (!image)
		return false;
	frame->image = image;
	return true;
}

static __always_inline bool kd_jit_image_matches(const struct kd_exe_info *exe,
                                 struct kd_exec_frame *frame)
{
	const unsigned char *code;
	const struct kd_jit_image *image = kd_jit_select_image(exe, frame);
	bool directory, matches;

	if (!image)
		return false;
	code = image->code;
	/* Exact directory bytes, without the out-of-line seven-byte memcmp on
	 * every request. The overlapping words do not read beyond the signature. */
	directory = code && get_unaligned_le32(code + 25) == 0x4357444bU &&
	                 get_unaligned_le32(code + 28) == 0x32303043U &&
	                 get_unaligned_le32(code + 41) == 0x4241444bU;

	if (READ_ONCE(exe->entry_abi) != frame->entry_abi)
		return false;
	if (kd_entry_abi_spin_clobber(frame->entry_abi))
		matches = directory && code[KD_JIT_ABI_OFFSET] == frame->entry_abi &&
		       clobber_spin_lock_addr && clobber_spin_unlock_addr;
	else if (frame->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1)
		matches = directory && code[KD_JIT_ABI_OFFSET] == frame->entry_abi &&
		       direct_mutex_lock_addr && direct_mutex_unlock_addr;
	else
		matches = frame->entry_abi == KD_ENTRY_ABI_LEGACY &&
		       (!directory || code[KD_JIT_ABI_OFFSET] == KD_ENTRY_ABI_LEGACY);
	/* A refused image must not alter an unexecuted frame or its packet. */
	if (matches)
		frame->image = image;
	return matches;
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
	call->unlock = frame->mutex_backend ? direct_mutex_unlock_addr :
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
	const struct kd_jit_image *previous_image = frame->image;
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
	    frame->packet_state != (frame->entry_abi == KD_ENTRY_ABI_LEGACY ?
	                          KD_PACKET_FULL : KD_PACKET_MINIMAL) ||
	    !kd_jit_image_matches(exe, frame))
		return false;
	code = kd_jit_bound_code(exe, frame);
	/* Check exactly KDWB002: overlapping unaligned words cover bytes 9..15.
	 * This avoids the out-of-line seven-byte memcmp without reading byte 16. */
	if (!code || get_unaligned_le32((char *)code + 9) != 0x4257444bU ||
	    get_unaligned_le32((char *)code + 12) != 0x32303042U) {
		frame->image = previous_image;
		return false;
	}
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
	    READ_ONCE(exe->lock_kind) != KD_EXE_LOCK_MUTEX ||
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
	call->code = (char *)kd_jit_bound_code(exe, frame) + KD_JIT_CLOBBER_OFFSET;
	call->lock = frame->outer_lock_addr;
	call->unlock = direct_mutex_unlock_addr;
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
