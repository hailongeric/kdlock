/* Actual dispatcher and pending-CALL validators; source reads/wrapper results
 * are substitutes. No Native lock primitive executes in this fixture. */
static void native_call_packet(struct kd_jit_batch_call *call, bool indirect,
			       bool terminal)
{
	escape_packet(call);
	active.regs.ip = 0xb000;
	active.regs.orig_ax = indirect ? ESCAPE_IP : KD_REG_NATIVE_ESCAPE_TAG;
	stack[9] = indirect ? ESCAPE_IP + 2 : 0x2005;
	escape_text[0] = 0xff;
	escape_text[1] = 0xd0;
	call->args[0] = indirect ? KD_EXE_INDIRECT_CALL : KD_EXE_CALL_MISS;
	known_result = 0;
	if (terminal)
		kd_native_terminals[0].address = active.regs.ip;
}

static void check_terminal_and_indirect_calls(void)
{
	struct kd_jit_batch_call call;
	struct kd_regs before;
	unsigned long saved_stack[ARRAY_SIZE(stack)];
	static const struct { unsigned char bytes[8]; unsigned int length; } calls[] = {
		{{0xff, 0xd0}, 2}, {{0x41, 0xff, 0xd0}, 3},
		{{0xff, 0x14, 0x24}, 3}, {{0xff, 0x15, 1, 2, 3, 4}, 6},
		{{0xff, 0x94, 0x24, 1, 2, 3, 4}, 7},
		{{0x41, 0xff, 0x94, 0x24, 1, 2, 3, 4}, 8},
		{{0x2e, 0xff, 0xd0}, 3}, {{0x2e, 0x2e, 0xff, 0xd0}, 4},
		{{0x2e, 0x2e, 0x2e, 0xff, 0xd0}, 5},
		{{0x2e, 0x41, 0xff, 0xd0}, 4},
		{{0x2e, 0x2e, 0x41, 0xff, 0xd0}, 5},
		{{0x2e, 0x2e, 0x2e, 0x41, 0xff, 0xd0}, 6},
	};
	static const struct { unsigned char bytes[8]; unsigned int length; } malformed[] = {
		{{0x2e, 0x2e, 0x2e, 0x2e, 0xff, 0xd0}, 6},
		{{0x2e, 0x66, 0xff, 0xd0}, 4}, {{0x66, 0x2e, 0xff, 0xd0}, 4},
		{{0x2e, 0xf3, 0xff, 0xd0}, 4},
		{{0x2e, 0xff, 0xe0}, 3}, {{0x2e, 0xff, 0xd8}, 3},
		{{0x2e, 0xff, 0x14, 0x24}, 4},
		{{0x2e, 0x41, 0xff, 0x14, 0x24}, 5},
		{{0x41, 0x2e, 0xff, 0xd0}, 4},
		{{0x2e, 0x41, 0x41, 0xff, 0xd0}, 5},
	};
	for (unsigned int terminal = 0; terminal < 2; terminal++) {
		native_call_packet(&call, false, terminal);
		CHECK(!kd_native_terminal_target(0));
		CHECK(kd_exe_mutex_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
		CHECK(known_calls == (terminal ? 0 : 1) &&
		      !kd_native_escape_count && !active.regs.orig_ax);
		CHECK(entry->status_code == (terminal ? KD_EXE_NORMAL : KD_EXE_CALL_MISS));
		CHECK(stack[9] == 0x2005 && active.regs.sp == (unsigned long)&stack[9]);
		CHECK(source_calls == (terminal ? 2 : 1));
	}
	for (unsigned int i = 0; i < ARRAY_SIZE(calls); i++) {
		for (unsigned int terminal = 0; terminal < 2; terminal++) {
			native_call_packet(&call, true, terminal);
			memcpy(escape_text, calls[i].bytes, sizeof(calls[i].bytes));
			stack[9] = ESCAPE_IP + calls[i].length;
			before = active.regs;
			CHECK(kd_exe_mutex_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
			before.orig_ax = 0;
			CHECK(!memcmp(&before, &active.regs, sizeof(before)));
			CHECK(entry->status_code == (terminal ? KD_EXE_NORMAL : KD_EXE_IJ_MISS));
			if (!terminal)
				CHECK(entry->tgt_addr == 0xb000 &&
				      entry->jump_from == ESCAPE_IP + calls[i].length);
			CHECK(source_calls == 4 && !known_calls && !kd_native_escape_count);
			CHECK(stack[9] == ESCAPE_IP + calls[i].length &&
			      active.continuation_sp == (unsigned long)&stack[9] &&
			      active.continuation_ip == 0xb000);
		}
		/* The source CALL word names the decoded instruction's exact end,
		 * not an alternatives patch-window length or following padding. */
		native_call_packet(&call, true, false);
		kd_exec_frame_own_regs(&active);
		memcpy(escape_text, calls[i].bytes, sizeof(calls[i].bytes));
		stack[9] = ESCAPE_IP + calls[i].length + 1;
		CHECK(kd_jit_indirect_call_native(entry, &active, &active.regs) < 0);
		CHECK(stack[9] == ESCAPE_IP + calls[i].length + 1);
	}
	for (unsigned int i = 0; i < ARRAY_SIZE(malformed); i++) {
		unsigned int length = ~0U;

		reset();
		memcpy(escape_text, malformed[i].bytes, malformed[i].length);
		CHECK(kd_jit_indirect_call_length(ESCAPE_IP, &length) < 0);
		CHECK(length == ~0U);
	}
	/* Bound every read by the live source extent. Truncating any accepted
	 * form must fail even when the missing byte is a prefix's next opcode. */
	for (unsigned int i = 0; i < ARRAY_SIZE(calls); i++) {
		for (unsigned int available = 1; available < calls[i].length; available++) {
			unsigned int length = ~0U;
			unsigned int offset = sizeof(escape_text) - available;

			reset();
			memcpy(escape_text + offset, calls[i].bytes, available);
			CHECK(kd_jit_indirect_call_length(ESCAPE_IP + offset, &length) == -EFAULT);
			CHECK(length == ~0U);
		}
	}
	for (unsigned int bad = 0; bad < 22; bad++) {
		native_call_packet(&call, true, false);
		/* These direct consumers start after FULL-packet ownership transfer,
		 * even when a predicate mutant wrongly accepts the malformed CALL.
		 * Keep case 15's foreign borrowed packet as its own refusal control. */
		if (bad != 15)
			kd_exec_frame_own_regs(&active);
		switch (bad) {
		case 0: escape_text[1] = 0xe0; break; /* JMP /4 */
		case 1: escape_text[1] = 0xd8; break; /* Far CALL /3 */
		case 2: escape_text[0] = 0x66; break;
		case 3: escape_text[0] = 0xf3; break;
		case 4: escape_text[0] = 0xe8; break;
		case 5: active.regs.orig_ax = 0; break;
		case 6: active.regs.orig_ax = ~0UL - 2; break;
		case 7: stack[9]++; break;
		case 8: active.control_call.phase = KD_CALL_ACQUIRED; break;
		case 9: active.packet_state = KD_PACKET_MINIMAL; break;
		case 10: active.logical_task = current; break;
		case 11: active.remote_request = (void *)1; break;
		case 12: active.native_request = (void *)1; break;
		case 13: active.executed = false; break;
		case 14: active.jit_lock_depth = 0; break;
		case 15: active.borrowed_regs = &before; break;
		case 16: active.regs.ip = 0; break;
		case 17: active.regs.sp = (unsigned long)stack - 8; break;
		default: source_error = -ESTALE; source_fail_at = bad - 17; break;
		}
		CHECK(kd_jit_indirect_call_native(entry, &active, &active.regs) < 0);
		CHECK(entry->status_code == KD_EXE_NORMAL && !entry->tgt_addr &&
		      !entry->jump_from && !kd_native_escape_count);
	}
	/* Terminal continuation cannot reopen another publisher's status/generation. */
	for (unsigned int ban = 0; ban < 2; ban++) {
		native_call_packet(&call, true, true);
		/* This direct helper starts after the dispatcher owns a FULL packet;
		 * preserve the real CALL word while recording its continuation. */
		kd_exec_frame_own_regs(&active);
		memcpy(saved_stack, stack, sizeof(stack));
		entry->status_code = ban ? KD_EXE_NATIVE_ONLY : KD_EXE_CALL_MISS;
		entry->generation = 19;
		entry->tgt_addr = 0xabc;
		entry->jump_from = 0xdef;
		CHECK(!kd_jit_indirect_call_native(entry, &active, &active.regs));
		CHECK(!memcmp(saved_stack, stack, sizeof(stack)));
		CHECK(entry->status_code == (ban ? KD_EXE_NATIVE_ONLY : KD_EXE_CALL_MISS) &&
		      entry->generation == 19 && entry->tgt_addr == 0xabc && entry->jump_from == 0xdef &&
		      !active.regs.orig_ax);
	}
	/* Terminal lookup must precede ordinary control-phase clearing. */
	native_call_packet(&call, false, true);
	active.control_call.phase = KD_CALL_ACQUIRED;
	CHECK(kd_exe_mutex_batch_resume(entry, &call) == KD_EXE_RUN_ERROR);
	CHECK(active.control_call.phase == KD_CALL_ACQUIRED && !known_calls &&
	      entry->status_code == KD_EXE_NORMAL);
}
