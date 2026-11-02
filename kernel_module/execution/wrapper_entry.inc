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
static int kd_jit_pending_call_native(struct kd_exec_frame *frame,
				     struct kd_regs *regs, bool hostcall,
				     unsigned long expected_return,
				     const char *reason)
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
				     sizeof(return_ip)) || !return_ip ||
	    (expected_return && return_ip != expected_return))
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
		"[KD_JIT][WARN] reason=%s entry=0x%lx ip=0x%lx sp=0x%lx return=0x%lx lock=0x%lx task=%d hostcall=%u\n",
		reason, frame->entry_ip, regs->ip, regs->sp, return_ip,
		frame->outer_lock_addr, frame->logical_task->pid, hostcall);
	return 0;
}

static int kd_jit_call_limit_native(struct kd_exec_frame *frame,
				    struct kd_regs *regs, bool hostcall)
{
	return kd_jit_pending_call_native(frame, regs, hostcall, 0,
					 "CALL_LIMIT_NATIVE");
}

/* Canonical near indirect CALL only: optional single REX, FF /2, then the
 * actual ModRM/SIB displacement. No guessed backward scan, far CALL, legacy
 * prefix or RET/JMP can supply this provenance. Read only required bytes. */
static int kd_jit_indirect_call_length(unsigned long site, unsigned int *length)
{
	u8 bytes[8], modrm, mode, rm, base = 0xff;
	unsigned int offset = 0, count;

	if (!site || site > ~0UL - sizeof(bytes) ||
	    copy_from_kernel_nofault(bytes, (void *)site, 1))
		return -EFAULT;
	if (bytes[0] >= 0x40 && bytes[0] <= 0x4f)
		offset++;
	if (copy_from_kernel_nofault(bytes, (void *)site, offset + 2))
		return -EFAULT;
	modrm = bytes[offset + 1];
	if (bytes[offset] != 0xff || ((modrm >> 3) & 7) != 2)
		return -EILSEQ;
	count = offset + 2;
	mode = modrm >> 6;
	rm = modrm & 7;
	if (mode != 3 && rm == 4) {
		if (copy_from_kernel_nofault(bytes, (void *)site, ++count))
			return -EFAULT;
		base = bytes[count - 1] & 7;
	}
	count += mode == 1 ? 1 : mode == 2 ||
		 (mode == 0 && (rm == 5 || base == 5)) ? 4 : 0;
	if (count > sizeof(bytes) ||
	    copy_from_kernel_nofault(bytes, (void *)site, count))
		return -EFAULT;
	*length = count;
	return 0;
}

static int kd_jit_indirect_call_native(struct kd_exe_info *exe,
				      struct kd_exec_frame *frame,
				      struct kd_regs *regs)
{
	unsigned long site, continuation;
	unsigned int length;
	int ret;

	if (!exe || !frame || !regs || frame->packet_state != KD_PACKET_FULL ||
	    regs != kd_exec_frame_regs(frame) ||
	    !kd_exec_frame_can_borrow_locks(frame) || !frame->executed ||
	    frame->logical_task == current || kd_exec_frame_remote_pending(frame) ||
	    frame->remote_request || frame->native_request)
		return -EINVAL;
	site = regs->orig_ax;
	ret = kd_source_pin_target(site);
	if (!ret)
		ret = kd_jit_indirect_call_length(site, &length);
	if (ret)
		return ret;
	continuation = site + length;
	ret = kd_source_pin_target(continuation - 1);
	if (!ret)
		ret = kd_jit_pending_call_native(frame, regs, false, continuation,
						 "INDIRECT_CALL_NATIVE");
	if (ret)
		return ret;
	/* Remember only this proved CALL edge. A stable Native boundary never
	 * invalidates an image or asks the daemon to import its body. */
	if (!kd_native_terminal_target(regs->ip) && !is_end_point(regs->ip))
		kd_image_report(exe, frame->image, KD_EXE_IJ_MISS, regs->ip, continuation);
	regs->orig_ax = 0;
	return 0;
}

/* Keep the actual pending CALL word in place until the original C helper
 * returns. The caller supplies valid arguments, memory and lifetime exactly
 * as for a native call. Only KD ownership and continuation bookkeeping are
 * checked here: successful execution consumes this saved token once, never a
 * newly discovered return address after the helper's effects. */
static int kd_jit_string_prepare(struct kd_exe_info *exe,
				 struct kd_exec_frame *frame, struct kd_regs *regs,
				 unsigned long *return_ip)
{
	const struct kd_hostcall_desc *service;
	unsigned long base, end;
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
	return kd_source_pin_target(*return_ip);
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

static bool kd_jit_root_escape_image(const struct kd_exec_frame *frame)
{
	return frame->image &&
	       frame->image->requirements == (KD_IMAGE_REQUIRE_NATIVE_ESCAPE |
					       KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE);
}

/* Only initialized complex fields describe ownership. The first batch entry
 * leaves them cold; its retained physical root supplies this ledger on FULL. */
static bool kd_jit_root_escape_owner(const struct kd_exec_frame *frame)
{
	return frame->complex_ready && !frame->mutex_backend &&
	       frame->spin_kind == KD_SPIN_CONT_ROOT &&
	       !frame->parent && !frame->depth && !frame->resume_target &&
	       !frame->outer_unlock_seen && !frame->completion_seen &&
	       frame->held_lock_depth == 1 && frame->outer_lock_depth == 1 &&
	       frame->jit_lock_depth == 1 && !frame->outer_lock_index &&
	       frame->jit_lock_addr[0] == frame->outer_lock_addr &&
	       frame->jit_lock_kind[0] == KD_EXEC_LOCK_QUEUE_OWNER &&
	       !frame->jit_lock_released[0] &&
	       !kd_exec_frame_remote_pending(frame) && !frame->remote_request &&
	       !frame->native_request && frame->control_call.phase == KD_CALL_NONE;
}

static int kd_jit_native_escape(struct kd_exe_info *exe,
				struct kd_exec_frame *frame, struct kd_regs *regs)
{
	unsigned long base, end;
	int ret;

	if (!exe || !frame || !regs ||
	    frame->packet_state != KD_PACKET_FULL || !frame->image ||
	    !frame->image->immutable || frame->image->entry != exe ||
	    frame->image->entry_abi != frame->entry_abi ||
	    !(frame->image->requirements & KD_IMAGE_REQUIRE_NATIVE_ESCAPE) ||
	    !((frame->mutex_backend &&
	       frame->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1) ||
	      (kd_jit_root_escape_image(frame) &&
	       kd_entry_abi_spin_clobber(frame->entry_abi) &&
	       !frame->regs_borrowed && regs == &frame->regs &&
	       (frame->entry_abi != KD_ENTRY_ABI_RWLOCK_CLOBBER_V1 ||
		frame->rwlock_admitted) &&
	       kd_jit_root_escape_owner(frame))) ||
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
	/* This reached instruction ends only this invocation. The immutable
	 * image and source lease survive through native completion and unlock ACK.
	 * Leave registry state untouched: an older retained image must neither
	 * disable a newer image nor reopen an independently disabled entry. */
	atomic64_inc(&kd_native_escape_count);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=NATIVE_ESCAPE entry=0x%lx rip=0x%lx generation=%lu waiter_pid=%d action=native_suffix_keep_eligible\n",
		frame->entry_ip, regs->ip, frame->image->generation,
		frame->logical_task->pid);
	return 0;
}

/* 1 resumes this same image; 0/2 return a validated before/after native suffix.
 * Unlike a CALL, one of these fixed opcodes has no source return word to pop. */
__attribute__((__noinline__, __cold__, __no_instrument_function__))
static int kd_jit_origin_instruction(struct kd_exe_info *exe,
				     struct kd_exec_frame *frame,
				     struct kd_regs *regs,
				     unsigned long sequence)
{
	const struct kd_origin_site *sites, *site = NULL;
	const struct kd_jit_image *image;
	unsigned char opcode[8];
	unsigned long base, end;
	unsigned int count, i;
	int ret;

	if (!exe || !frame || !regs || frame->packet_state != KD_PACKET_FULL ||
	    !frame->mutex_backend || frame->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	    !frame->executed || frame->logical_task == current ||
	    regs != kd_exec_frame_regs(frame) || !kd_exec_frame_can_borrow_locks(frame) ||
	    !frame->image || !frame->image->immutable || frame->image->entry != exe ||
	    frame->image->entry_abi != frame->entry_abi || !(regs->flags & 2) ||
	    !regs->ss || regs->ss > 0x1000000UL)
		return -EINVAL;
	image = frame->image;
	sites = kd_image_origin_sites(image, &count);
	if (!sites)
		return -EPROTO;
	for (i = 0; i < count; i++)
		if (sites[i].ip == regs->ip) {
			if (site)
				return -EPROTO;
			site = &sites[i];
		}
	if (!site || !kd_image_origin_site_valid(image, site))
		return -EPROTO;
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return -EFAULT;
	end = base + THREAD_SIZE;
	if (regs->sp < base + 2 * sizeof(unsigned long) || regs->sp > end - sizeof(unsigned long))
		return -EFAULT;
	ret = kd_source_pin_target(site->ip);
	if (!ret)
		ret = kd_source_pin_target(site->next_ip - 1);
	if (!ret)
		ret = kd_source_pin_target(site->next_ip);
	if (ret)
		return ret;
	if (copy_from_kernel_nofault(opcode, (void *)site->ip, site->length) ||
	    memcmp(opcode, site->opcode, site->length))
		return -EILSEQ;
	/* A quota or context refusal is still BEFORE this source instruction.
	 * The established suffix path retains every previously committed effect. */
	ret = sequence > KD_EXE_HL_MAX_CONTINUATIONS ? 0 :
		kd_mutex_origin_instruction(frame, site->kind, sequence);
	if (ret < 0)
		return ret;
	if (!ret) {
		ret = kd_jit_native_escape(exe, frame, regs);
		return ret ? ret : 0;
	}
	/* The service's ACK proves the origin no longer accesses this packet.
	 * Every later refusal must use this post-instruction state, never ip. */
	if (ret != 1 || frame->image != image ||
	    !kd_exec_frame_can_borrow_locks(frame) || regs->ip != site->ip ||
	    frame->control_call.phase != KD_CALL_NONE)
		return -EINVAL;
	regs->ip = site->next_ip;
	atomic64_inc(&kd_origin_instruction_count);
	regs->orig_ax = READ_ONCE(kd_origin_instruction_force_suffix) ?
		KD_REG_ORIGIN_SUFFIX_TAG : KD_REG_ORIGIN_REENTRY_TAG;
	kd_exec_frame_save_continuation(frame, regs);
	if (regs->orig_ax == KD_REG_ORIGIN_SUFFIX_TAG) {
		atomic64_inc(&kd_origin_suffix_count);
		return 2;
	}
	return 1;
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
	    ((image->requirements & (KD_IMAGE_REQUIRE_SERVICE_QUEUE |
				    KD_IMAGE_REQUIRE_ORIGIN_CALL)) &&
	     (!kd_exec_frame_continuation(frame) ||
	      !kd_exec_frame_continuation(frame)->service_ops)) ||
	    ((image->requirements & KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE) &&
	     !image->immutable) ||
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
	/* Retained requests first use FULL output for exact CALL-result/packet
	 * transfer. Legacy ABI2 roots keep their existing minimal fast path. */
	if (kd_exec_frame_continuation(frame))
		return false;
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

static bool kd_jit_direct_image(const struct kd_exec_frame *frame)
{
	return frame->image &&
	       (frame->image->requirements & KD_IMAGE_REQUIRE_DIRECT_STRINGS);
}

/* Check before any body instruction, on both batch and general dispatch.
 * Batch admission precedes frame binding and writer admission. Do not read
 * cold routing/ledger fields there or require an already admitted writer. */
static bool kd_jit_root_escape_entry(const struct kd_exec_frame *frame)
{
	const struct kd_regs *regs = kd_exec_frame_regs(frame);

	if (!kd_jit_root_escape_image(frame))
		return true;
	if (!frame->image->immutable ||
	    !kd_entry_abi_spin_clobber(frame->entry_abi) ||
	    frame->mutex_backend || frame->spin_kind != KD_SPIN_CONT_ROOT ||
	    !frame->spin_regs_decoded || !frame->request_frame ||
	    frame->regs_borrowed ||
	    frame->parent || frame->depth || frame->executed ||
	    frame->completion_seen || !frame->logical_task ||
	    frame->logical_task == current ||
	    frame->state != KD_EXEC_FRAME_RUNNING || !frame->outer_lock_addr ||
	    frame->packet_state != KD_PACKET_MINIMAL || regs != &frame->regs ||
	    regs->ip != frame->entry_ip || !regs->sp)
		return false;
	if (!frame->complex_ready)
		return frame->spin_simple;
	return kd_jit_root_escape_owner(frame);
}

/* Direct code can enter only once from an untouched spin request. The simple
 * request binding already retains its physical owner and source/batch lease;
 * deferred routing fields must not be read until a real FULL exit promotes it. */
static bool kd_jit_direct_entry(const struct kd_exec_frame *frame)
{
	const struct kd_regs *regs = kd_exec_frame_regs(frame);

	if (!kd_jit_direct_image(frame))
		return true;
	return frame->image->immutable && frame->image->near_text &&
	       frame->entry_abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1 &&
	       frame->spin_simple && !frame->complex_ready && frame->request_frame &&
	       !frame->mutex_backend && !frame->parent && !frame->depth &&
	       !frame->executed && !frame->completion_seen &&
	       frame->logical_task && frame->logical_task != current &&
	       frame->state == KD_EXEC_FRAME_RUNNING && frame->outer_lock_addr &&
	       frame->packet_state == KD_PACKET_MINIMAL && regs == &frame->regs &&
	       regs->ip == frame->entry_ip && regs->sp;
}

static bool kd_jit_note_direct_calls(const struct kd_jit_batch_call *call,
				     const struct kd_exec_frame *frame)
{
	if (!kd_jit_direct_image(frame))
		return true;
	if (!call->direct_strcmp && !call->direct_pad)
		return true;
	if (call->direct_strcmp > KD_STRCMP_MAX_CALLS ||
	    call->direct_pad > KD_EXE_HL_MAX_HOSTCALLS ||
	    (call->direct_strcmp && !(frame->image->requirements & KD_IMAGE_REQUIRE_STRING_SERVICES)) ||
	    (call->direct_pad && !(frame->image->requirements & KD_IMAGE_REQUIRE_STRING_WRITE)))
		return false;
	if (call->direct_strcmp)
		atomic64_add(call->direct_strcmp, &kd_direct_strcmp);
	if (call->direct_pad)
		atomic64_add(call->direct_pad, &kd_direct_pad);
	return true;
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
	if (kd_jit_direct_image(frame)) {
		call->direct_strcmp = 0;
		call->direct_pad = 0;
	}
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
	if (!kd_jit_direct_entry(frame) || !kd_jit_root_escape_entry(frame)) {
		frame->image = previous_image;
		return false;
	}
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
	if (kd_jit_direct_image(frame)) {
		call->direct_strcmp = 0;
		call->direct_pad = 0;
	}
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
	if (!kd_jit_note_direct_calls(call, frame))
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
