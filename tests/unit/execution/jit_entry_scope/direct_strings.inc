/* Production direct-image admission/exit consumer. Generated helper execution
 * and its register/flags behavior have a separate machine-code fixture. */
static void direct_packet(struct kd_jit_batch_call *call)
{
	guard_packet(call);
	guard_code[47] = entry->requirements = guard_image.requirements =
		KD_IMAGE_REQUIRE_DIRECT_STRINGS | KD_IMAGE_REQUIRE_STRING_SERVICES |
		KD_IMAGE_REQUIRE_STRING_WRITE;
	guard_image.near_text = 1;
	active.request_frame = true;
	active.regs.ip = STRING_IP;
	active.regs.sp = (unsigned long)&stack[8];
	active.regs.orig_ax = 0;
	stack[8] = STRING_RETURN;
	call->args[0] = KD_EXE_DIRECT_CALL_LIMIT;
	call->lock = active.outer_lock_addr;
	call->unlock = clobber_spin_unlock_addr;
	call->direct_strcmp = KD_STRCMP_MAX_CALLS;
	call->direct_pad = 0;
}

static void check_direct_strings(void)
{
	struct kd_jit_batch_call call, untouched;
	struct kd_exec_frame before;

	_Static_assert(sizeof(struct kd_jit_batch_call) == 112, "private call size");
	_Static_assert(__builtin_offsetof(struct kd_jit_batch_call, args) == 8, "args unchanged");
	_Static_assert(__builtin_offsetof(struct kd_jit_batch_call, complete) == 88, "completion unchanged");
	_Static_assert(__builtin_offsetof(struct kd_jit_batch_call, direct_strcmp) == 96, "strcmp result");
	_Static_assert(__builtin_offsetof(struct kd_jit_batch_call, direct_pad) == 104, "pad result");
	for (unsigned int bad = 0; bad < 11; bad++) {
		direct_packet(&call);
		active.complex_ready = false;
		active.executed = false;
		active.packet_state = KD_PACKET_MINIMAL;
		active.regs.ip = active.entry_ip;
		CHECK(kd_exe_spin_batch_prepare(entry, &active, &call));
		CHECK(!call.direct_strcmp && !call.direct_pad && call.complete);
		switch (bad) {
		case 0: active.logical_task = current; break;
		case 1: active.parent = &parent; break;
		case 2: active.depth = 1; break;
		case 3: active.executed = true; break;
		case 4: active.packet_state = KD_PACKET_FULL; break;
		case 5: active.complex_ready = true; break;
		case 6: active.request_frame = false; break;
		case 7: active.completion_seen = true; break;
		case 8: guard_image.near_text = 0; break;
		case 9: guard_image.immutable = 0; break;
		case 10: active.entry_abi = KD_ENTRY_ABI_RWLOCK_CLOBBER_V1; break;
		}
		memcpy(&before, &active, sizeof(before));
		memcpy(&untouched, &call, sizeof(call));
		CHECK(!kd_jit_direct_entry(&active));
		CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
		CHECK(!memcmp(&before, &active, sizeof(before)));
		CHECK(!memcmp(&untouched, &call, sizeof(call)) && !calls);
	}
	/* A successful minimal completion exports direct observations once, with
	 * no fabricated service dispatcher exits, executions or resumptions. */
	direct_packet(&call);
	call.complete = true;
	call.args[0] = KD_EXE_CLOBBER_COMPLETE;
	active.packet_state = KD_PACKET_COMPLETE;
	call.direct_strcmp = 16;
	call.direct_pad = 1;
	CHECK(kd_exe_spin_batch_completed(&call, &active));
	CHECK(kd_direct_strcmp == 16 && kd_direct_pad == 1);
	CHECK(!kd_hostcall_exits && !kd_hostcall_executed && !kd_hostcall_resumed);
	/* A pending exit cannot count in the completed batch, then counts once
	 * in the dispatcher. Quota recovery retains the actual return word/SP. */
	for (unsigned int pad = 0; pad < 2; pad++) {
		direct_packet(&call);
		if (pad) {
			active.regs.ip = PAD_IP;
			call.direct_strcmp = 0;
			call.direct_pad = KD_EXE_HL_MAX_HOSTCALLS;
		}
		CHECK(!kd_exe_spin_batch_completed(&call, &active));
		CHECK(!kd_direct_strcmp && !kd_direct_pad);
		CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
		CHECK(active.continuation_ip == (pad ? PAD_IP : STRING_IP) &&
		      active.continuation_sp == (unsigned long)&stack[8]);
		CHECK(stack[8] == STRING_RETURN && !calls && !known_calls);
		CHECK(source_calls == 2 && source_targets[0] == (pad ? PAD_IP : STRING_IP) &&
		      source_targets[1] == STRING_RETURN);
		CHECK(kd_direct_strcmp == (pad ? 0 : KD_STRCMP_MAX_CALLS) &&
		      kd_direct_pad == (pad ? KD_EXE_HL_MAX_HOSTCALLS : 0));
		CHECK(!kd_hostcall_exits && !kd_hostcall_executed && !kd_hostcall_resumed);
	}
	for (unsigned int bad = 0; bad < 13; bad++) {
		direct_packet(&call);
		switch (bad) {
		case 0: call.direct_strcmp--; break;
		case 1: call.direct_strcmp++; break;
		case 2: call.direct_pad = KD_EXE_HL_MAX_HOSTCALLS + 1; break;
		case 3: guard_image.requirements &= ~KD_IMAGE_REQUIRE_DIRECT_STRINGS; break;
		case 4: active.regs.ip = kd_hostcalls[0].addr; break;
		case 5: active.logical_task = current; break;
		case 6: active.parent = &parent; break;
		case 7: active.control_call.phase = KD_CALL_PENDING; break;
		case 8: stack[8] = 0; break;
		case 9: source_error = -ESTALE; break;
		case 10: active.packet_state = KD_PACKET_MINIMAL; break;
		case 11: guard_image.near_text = 0; break;
		case 12: call.args[0] = KD_EXE_HOSTCALL; break;
		}
		CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_ERROR);
		CHECK(!calls && !string_calls && !pad_calls && !kd_hostcall_executed);
	}
	/* An ordinary unknown CALL transfers to native once; a FULL direct image
	 * must not execute known control helpers then reset/reenter its wrapper. */
	direct_packet(&call);
	call.args[0] = KD_EXE_CALL_MISS;
	call.direct_strcmp = 3;
	active.regs.ip = 0x7770;
	CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
	CHECK(!calls && !known_calls && kd_direct_strcmp == 3 &&
	      entry->tgt_addr == 0x7770 && entry->status_code == KD_EXE_CALL_MISS);
	CHECK(active.continuation_sp == (unsigned long)&stack[8] && stack[8] == STRING_RETURN);
	direct_packet(&call);
	call.args[0] = KD_EXE_INST_LIMIT;
	call.direct_strcmp = 3;
	CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_ERROR);
	CHECK(!calls && !source_calls && kd_direct_strcmp == 3);
	direct_packet(&call);
	active.spin_simple = false;
	active.executed = false;
	active.regs.ip = active.entry_ip;
	CHECK(run() == KD_EXE_NO_RUN && !calls); /* never enter direct code from FULL */
}
