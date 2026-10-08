/* Entry-scope fixture cases; shared stubs live in jit_entry_scope_fixture.c. */
static void check_simple_spin(void)
{
	struct kd_regs packet, before;

	reset();
	active.spin_simple = true;
	packet = active.regs;
	active.borrowed_regs = &packet;
	active.regs_borrowed = true;
	memset(&active.regs, 0xa5, sizeof(active.regs));
	before = active.regs;
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(active.executed && active.spin_simple && calls == 1 &&
	      !known_calls && !complex_preparations);
	CHECK(packet.ip == 0x9000 && active.borrowed_regs == &packet &&
	      !memcmp(&active.regs, &before, sizeof(before)));

	/* A service promotes once, before the service runs; its eventual outer
	 * unlock uses the generic continuation path even when the ledger is 1. */
	reset();
	active.spin_simple = true;
	packet = active.regs;
	active.borrowed_regs = &packet;
	active.regs_borrowed = true;
	memset(&active.regs, 0xa5, sizeof(active.regs));
	steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
	steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(!active.spin_simple && complex_preparations == 1 &&
	      calls == 2 && known_calls == 1 && service_calls[0] == 1);
	CHECK(!active.regs_borrowed && active.regs.ip == 0x9000 &&
	      active.regs.ax == service_values[0]);
	/* After promotion the old node packet stops changing, including the CALL
	 * return advance and the resumed wrapper. */
	CHECK(packet.ip == kd_hostcalls[0].addr && packet.sp != active.regs.sp);

	/* The CALL target alone is insufficient; a different lock must take the
	 * existing control/error handling instead of completing this frame. */
	reset();
	active.spin_simple = true;
	active.regs.di++;
	known_result = -EINVAL;
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_ERROR);
	CHECK(!active.spin_simple && complex_preparations == 1 && known_calls == 1);

	reset();
	active.spin_simple = true;
	steps[0].reason = KD_EXE_ENTRY_REFUSED;
	packet = before = active.regs;
	active.borrowed_regs = &packet;
	active.regs_borrowed = true;
	CHECK(run() == KD_EXE_NO_RUN);
	CHECK(active.spin_simple && !active.executed && !complex_preparations);
	CHECK(active.borrowed_regs == &packet &&
	      !memcmp(&packet, &before, sizeof(packet)));
}

/* A batch exit has already executed its prefix. Import it once, then permit
 * only the required continuation wrapper call; a refusal remains unstarted. */
static void check_batch_admission(void)
{
	unsigned char code[64] = { 0 };
	struct kd_jit_batch_call call;

	reset();
	active.spin_simple = active.request_frame = true;
	active.complex_ready = false;
	entry->code_block = code;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	memcpy(code + 9, "KDWB002", 7);
	CHECK(kd_exe_spin_batch_prepare(entry, &active, &call));
	CHECK(call.code == code + KD_JIT_BATCH_OFFSET && call.regs == &active.regs &&
	      call.args[0] == active.gsbase && call.args[1] == (unsigned long)&waiter);
	source_open = false;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	source_open = true;
	entry->status_code = KD_EXE_CALL_MISS;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	entry->status_code = KD_EXE_NORMAL;
	active.executed = true;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	active.executed = false;
	active.regs.sp = 0;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	active.regs.sp = (unsigned long)&stack[9];
	active.complex_ready = true;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
}

/* The wrapper consumes every metadata word, even when no optional clock is
 * active. Poison reused call storage and validate both entry ABIs so the
 * single-pass batch setup cannot retain a legacy offset/endpoint or stale
 * completion/timing permission. Preparation must not mutate the frame. */
static void check_batch_metadata(void)
{
	unsigned char code[64] = { 0 };
	struct kd_jit_batch_call call, untouched;
	struct kd_exec_frame before;

	for (unsigned int abi = 0; abi < 2; abi++) {
		for (unsigned int timed = 0; timed < 2; timed++) {
			reset();
			active.spin_simple = active.request_frame = true;
			active.complex_ready = false;
			active.entry_abi = entry->entry_abi = abi;
			active.packet_state = abi ? KD_PACKET_MINIMAL : KD_PACKET_FULL;
			entry->code_block = code;
			memcpy(code + 9, "KDWB002", 7);
			memcpy(code + 25, "KDWC002", 7);
			memcpy(code + 41, "KDAB", 4);
			code[KD_JIT_ABI_OFFSET] = abi;
			kd_jit_timing = timed;
			timing_clock_active = true;
			timing_clock = 100;
			memset(&call, 0xa5, sizeof(call));
			memcpy(&before, &active, sizeof(before));
			CHECK(kd_exe_spin_batch_prepare(entry, &active, &call));
			CHECK(call.regs == &active.regs &&
			      call.args[0] == active.gsbase &&
			      call.args[1] == (unsigned long)active.logical_task);
			CHECK(call.code == code + (abi ? KD_JIT_CLOBBER_OFFSET :
						       KD_JIT_BATCH_OFFSET));
			CHECK(call.lock == active.outer_lock_addr &&
			      call.unlock == (abi ? clobber_spin_unlock_addr :
						    raw_spin_unlock_addr));
			CHECK(call.entry_sp == active.regs.sp && call.entry_abi == abi &&
			      call.packet_state == &active.packet_state);
			CHECK(call.complete == abi &&
			      call.complete == kd_jit_minimal_complete_allowed(&active));
			CHECK(call.dispatch_start == (timed ? 1000 : 0) &&
			      call.wrapper_start == (timed ? 1010 : 0) &&
			      timing_reads == timed * 2);
			CHECK(!memcmp(&active, &before, sizeof(active)));

			/* Both ABIs must validate all seven tag bytes, including the
			 * overlap and final byte, before publishing call metadata. */
			for (unsigned int byte = 0; byte < 7; byte++) {
				code[9 + byte] ^= 1;
				memcpy(&untouched, &call, sizeof(untouched));
				CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
				CHECK(!memcmp(&call, &untouched, sizeof(call)));
				CHECK(!memcmp(&active, &before, sizeof(active)));
				CHECK(timing_reads == timed * 2);
				code[9 + byte] ^= 1;
			}
			/* Integer directory comparisons must reject every changed byte
			 * just like memcmp, including each overlap/end byte. Legacy
			 * images intentionally permit an absent clobber directory. */
			if (abi) {
				for (unsigned int byte = 0; byte < 11; byte++) {
					unsigned int at = byte < 7 ? 25 + byte : 41 + byte - 7;

					code[at] ^= 1;
					memcpy(&untouched, &call, sizeof(untouched));
					CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
					CHECK(!memcmp(&call, &untouched, sizeof(call)));
					CHECK(!memcmp(&active, &before, sizeof(active)));
					CHECK(timing_reads == timed * 2);
					code[at] ^= 1;
				}
				code[32] = code[40] = 0xa5;
				CHECK(kd_jit_image_matches(entry, &active));
				code[32] = code[40] = 0;
			}

			/* The shortcut to COMPLETE permission is valid only after the
			 * original pristine-root guards. Reject each lost prerequisite
			 * without publishing even partial metadata to the caller. */
			for (unsigned int bad = 0; bad < 4; bad++) {
				memcpy(&active, &before, sizeof(active));
				if (bad == 0) active.spin_simple = false;
				if (bad == 1) active.parent = &parent;
				if (bad == 2) active.depth = 1;
				if (bad == 3) active.mutex_backend = true;
				memset(&call, 0xa5, sizeof(call));
				memcpy(&untouched, &call, sizeof(untouched));
				CHECK(!kd_jit_minimal_complete_allowed(&active));
				CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
				CHECK(!memcmp(&call, &untouched, sizeof(call)));
				CHECK(timing_reads == timed * 2);
			}
		}
	}
}

/* Completion receives freshly prepared metadata in both ABIs. Disabled
 * timing must read no clock; enabled endpoints retain wrapper-before-dispatch
 * order. A non-final exit leaves both endpoints for the generic dispatcher. */
static void check_batch_completion_timings(void)
{
	unsigned char code[64] = { 0 };
	struct kd_jit_batch_call call, rejected, before_call;
	struct kd_exec_frame before;
	struct kd_regs bad_regs;
	unsigned int bad_packet = KD_PACKET_MINIMAL;

	for (unsigned int abi = 0; abi < 2; abi++) {
		for (unsigned int timed = 0; timed < 2; timed++) {
			reset();
			active.spin_simple = active.request_frame = true;
			active.complex_ready = false;
			active.entry_abi = entry->entry_abi = abi;
			active.packet_state = abi ? KD_PACKET_MINIMAL : KD_PACKET_FULL;
			entry->code_block = code;
			memcpy(code + 9, "KDWB002", 7);
			memcpy(code + 25, "KDWC002", 7);
			memcpy(code + 41, "KDAB", 4);
			code[KD_JIT_ABI_OFFSET] = abi;
			kd_jit_timing = timed;
			timing_clock_active = true;
			timing_clock = 100;
			memset(&call, 0xa5, sizeof(call));
			CHECK(kd_exe_spin_batch_prepare(entry, &active, &call));
			call.args[0] = abi ? KD_EXE_CLOBBER_COMPLETE : KD_EXE_CALL_MISS;
			call.args[1] = 1;
			if (abi)
				active.packet_state = KD_PACKET_COMPLETE;
			else
				active.regs.ip = call.unlock;
			memcpy(&before, &active, sizeof(before));
			memcpy(&before_call, &call, sizeof(before_call));
			/* Completion reuses the batch's retained frame. It must not
			 * re-fetch physical context just to report this body's witness. */
			current_frame_reads = 0;
			for (unsigned int bad = 0; bad < 3; bad++) {
				rejected = call;
				bad_regs = active.regs;
				if (bad == 0)
					rejected.args[0] = KD_EXE_HOSTCALL;
				else if (abi) {
					if (bad == 1) rejected.packet_state = &bad_packet;
					if (bad == 2) rejected.complete = false;
				} else {
					rejected.regs = &bad_regs;
					if (bad == 1) bad_regs.ip++;
					if (bad == 2) bad_regs.di++;
				}
				CHECK(!kd_exe_spin_batch_completed(&rejected, &active));
				CHECK(timing_reads == timed * 2);
			}
			CHECK(kd_exe_spin_batch_completed(&call, &active));
			CHECK(current_frame_reads == 0);
			CHECK(timing_reads == timed * 4);
			for (unsigned int phase = 0; phase < KD_JIT_TIME_COUNT; phase++) {
				unsigned int count = timed &&
					(phase == KD_JIT_TIME_WRAPPER || phase == KD_JIT_TIME_DISPATCH);
				unsigned int ns = count * (phase == KD_JIT_TIME_WRAPPER ? 10 : 30);

				CHECK(kd_jit_times[phase].samples == count);
				CHECK(kd_jit_times[phase].ns == ns);
				CHECK(!kd_jit_times[phase].invalid);
			}
			CHECK(!memcmp(&active, &before, sizeof(active)));
			CHECK(!memcmp(&call, &before_call, sizeof(call)));
		}
	}
}

/* Entry identity and materialization state are independent of publication.
 * None of these mismatches may invoke the wrapper or read the absent GPRs. */
static void check_clobber_identity(void)
{
	unsigned char code[64] = { 0 };
	struct kd_jit_batch_call call;

	reset();
	active.spin_simple = active.request_frame = true;
	active.complex_ready = false;
	entry->code_block = code;
	memcpy(code + 9, "KDWB002", 7);
	active.entry_abi = entry->entry_abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	active.packet_state = KD_PACKET_MINIMAL;
	active.regs.di = 0xdead; /* deliberately not the root lock */
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	memcpy(code + 25, "KDWC002", 7);
	memcpy(code + 41, "KDAB", 4);
	code[45] = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	CHECK(kd_exe_spin_batch_prepare(entry, &active, &call));
	CHECK(call.code == code + KD_JIT_CLOBBER_OFFSET && call.complete);
	CHECK(call.packet_state == &active.packet_state && call.entry_abi == 1);
	for (unsigned int bad = 0; bad < 4; bad++) {
		if (bad == 0) entry->entry_abi = KD_ENTRY_ABI_LEGACY;
		if (bad == 1) code[45] = KD_ENTRY_ABI_LEGACY;
		if (bad == 2) active.packet_state = KD_PACKET_FULL;
		if (bad == 3) active.packet_state = KD_PACKET_COMPLETE;
		CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
		entry->entry_abi = code[45] = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
		active.packet_state = KD_PACKET_MINIMAL;
	}
	active.entry_abi = entry->entry_abi = KD_ENTRY_ABI_LEGACY;
	active.packet_state = KD_PACKET_FULL;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	CHECK(calls == 0 && !active.executed);
	active.entry_abi = entry->entry_abi = code[45] = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	active.mutex_backend = true;
	active.spin_simple = false;
	active.jit_lock_depth = 1;
	active.outer_lock_index = 0;
	active.jit_lock_released[0] = false;
	CHECK(kd_jit_image_matches(entry, &active));
	kd_jit_prepare_clobber(&call, &active, code);
	CHECK(call.complete && call.unlock == direct_mutex_unlock_addr);
	CHECK(call.entry_abi == 2 && call.regs == kd_exec_frame_regs(&active));
	active.jit_lock_depth = 2;
	CHECK(!kd_jit_minimal_complete_allowed(&active));
	active.jit_lock_depth = 1;
	active.outer_unlock_seen = true;
	CHECK(!kd_jit_minimal_complete_allowed(&active));
	active.outer_unlock_seen = false;
	active.mutex_backend = false;
	CHECK(!kd_jit_minimal_complete_allowed(&active));
	code[45] = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	CHECK(!kd_jit_image_matches(entry, &active));
}

static void check_pending_batch_exit(void)
{
	struct kd_jit_batch_call pending;

	for (int refuse = 0; refuse < 2; refuse++) {
		reset();
		active.spin_simple = true;
		pending = (struct kd_jit_batch_call){
			.regs = &active.regs, .entry_sp = active.regs.sp,
			.args = { active.gsbase, (unsigned long)&waiter },
		};
		steps[0] = refuse ? (struct step){ KD_EXE_ENTRY_REFUSED, 0, 0, 0 } :
			(struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
		steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
		active.executed = true;
		translated(pending.regs, pending.args);
		CHECK(calls == 1);
		int result = kd_exe_spin_batch_resume(entry, &pending);
		CHECK(result == (refuse ? KD_EXE_NO_RUN : KD_EXE_RUN_TO_UNLOCK));
		CHECK(calls == (refuse ? 1 : 2));
		CHECK(service_calls[0] == (refuse ? 0U : 1U));
		CHECK(active.executed == !refuse && complex_preparations == 1);
	}
}

/* Cold routing bytes may contain a previous retired frame. A pristine body
 * must not clear/read them, while promotion must initialize each discriminator
 * without changing the live physical ledger, hook or borrowed packet pointer. */
