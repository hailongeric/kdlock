/* Real overlay and counter gates; wrapper/native helper primitives remain the
 * shared doubles. A witnessed prefix is not a completed delegated body. */
static void check_bench_completions(void)
{
	struct kd_jit_batch_call pending;

	/* Multiple helper returns still contribute exactly one body/completion. */
	for (unsigned int kind = 0; kind < 3; kind++) {
		for (unsigned int count = 1; count <= 3; count += 2) {
			unsigned long target;
			if (kind == 0) service_packet();
			else if (kind == 1) string_packet();
			else copy_packet();
			target = kind == 0 ? kd_hostcalls[0].addr : kind == 1 ? STRING_IP : PAD_IP;
			for (unsigned int i = 0; i < count; i++)
				steps[i] = (struct step){ KD_EXE_HOSTCALL, target, 1, -8 };
			steps[count] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
			CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
			CHECK(kd_hostcall_executed == count && kd_hostcall_resumed == count);
			CHECK(kd_bench_bodies == 1 && kd_bench_completions == 1);
		}
	}

	/* Both witness positions are legitimate; neither means no completion proof. */
	for (unsigned int witnesses = 0; witnesses < 4; witnesses++) {
		service_packet();
		steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr,
			!!(witnesses & 1), -8 };
		steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, !!(witnesses & 2), -8 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		CHECK(kd_bench_bodies == (u64)!!witnesses && kd_bench_completions == (u64)!!witnesses);
	}

	/* Invalid CALL word, quota, unknown CALL, instruction error, refused service
	 * flags and wrong unlock retain the prefix but never count complete. */
	for (unsigned int failure = 0; failure < 6; failure++) {
		unsigned int count = failure == 1 ? KD_STRCMP_MAX_CALLS + 1 : 1;
		string_packet();
		if (failure == 0) stack_error = 1;
		if (failure == 2) known_result = 0;
		if (failure == 4) kd_hostcalls[3].flags = 0;
		for (unsigned int i = 0; i < count; i++)
			steps[i] = (struct step){ KD_EXE_HOSTCALL, STRING_IP, 1, -8 };
		steps[count] = (struct step){ failure == 3 ? KD_EXE_INST_LIMIT : KD_EXE_CALL_MISS,
			failure == 2 || failure == 5 ? 0x9870 : 0x9000, 1, -8 };
		if (failure == 5) known_result = -EINVAL;
		CHECK(run() == (failure == 1 || failure == 2 ? KD_EXE_RUN_NATIVE : KD_EXE_RUN_ERROR));
		CHECK(kd_bench_bodies == 1 && kd_bench_completions == 0);
	}
	copy_packet();
	guard_image.requirements = 0;
	steps[0] = (struct step){ KD_EXE_HOSTCALL, PAD_IP, 1, -8 };
	CHECK(run() == KD_EXE_RUN_ERROR && !pad_calls);
	CHECK(kd_bench_bodies == 1 && !kd_bench_completions);
	guard_packet(&pending);
	CHECK(kd_exe_spin_batch_resume(entry, &pending) == KD_EXE_RUN_NATIVE);
	CHECK(kd_bench_bodies == 1 && !kd_bench_completions);
	escape_packet(&pending);
	CHECK(kd_exe_mutex_batch_resume(entry, &pending) == KD_EXE_RUN_NATIVE);
	CHECK(kd_bench_bodies == 1 && !kd_bench_completions);

	/* A remote suffix and a CPU-local nested frame can reach an unlock, but
	 * neither is evidence of a complete root invocation for that lock. */
	remote();
	kd_bench_lock_addr = active.outer_lock_addr;
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(kd_bench_bodies == 1 && !kd_bench_completions);
	reset();
	active.parent = &parent;
	active.depth = 1;
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(kd_bench_bodies == 1 && !kd_bench_completions);

	/* Mirror the backend branch: successful batches bypass dispatcher; pending
	 * service exits use it once, consuming the already-returned packet once. */
	for (unsigned int service = 0; service < 2; service++) {
		reset();
		active.spin_simple = true;
		pending = (struct kd_jit_batch_call){ .regs = &active.regs,
			.entry_sp = active.regs.sp, .lock = active.outer_lock_addr,
			.unlock = raw_spin_unlock_addr, .entry_abi = KD_ENTRY_ABI_LEGACY,
			.args = { active.gsbase, (unsigned long)&waiter } };
		steps[0] = (struct step){ service ? KD_EXE_HOSTCALL : KD_EXE_CALL_MISS,
			service ? kd_hostcalls[0].addr : raw_spin_unlock_addr, 1, service ? -8 : 0 };
		steps[1] = (struct step){ KD_EXE_CALL_MISS, raw_spin_unlock_addr, 1, 0 };
		active.executed = true;
		translated(pending.regs, pending.args);
		if (!kd_exe_spin_batch_completed(&pending, &active)) {
			CHECK(service && !kd_bench_completions && !kd_bench_bodies);
			CHECK(kd_exe_spin_batch_resume(entry, &pending) == KD_EXE_RUN_TO_UNLOCK);
		}
		CHECK(calls == (int)service + 1 && service_calls[0] == service);
		CHECK(kd_bench_bodies == 1 && kd_bench_completions == 1);
	}
	/* Prepared ABI1/ABI3 minimal completions retain the same single count. */
	for (unsigned int abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	     abi <= KD_ENTRY_ABI_RWLOCK_CLOBBER_V1; abi += 2) {
		unsigned char code[64] = { 0 };
		reset();
		active.spin_simple = active.request_frame = true;
		active.complex_ready = false;
		active.entry_abi = entry->entry_abi = abi;
		active.packet_state = KD_PACKET_MINIMAL;
		entry->code_block = code;
		memcpy(code + 9, "KDWB002", 7);
		memcpy(code + 25, "KDWC002", 7);
		memcpy(code + 41, "KDAB", 4);
		code[KD_JIT_ABI_OFFSET] = abi;
		CHECK(kd_exe_spin_batch_prepare(entry, &active, &pending));
		pending.args[0] = KD_EXE_CLOBBER_COMPLETE;
		pending.args[1] = 1;
		active.packet_state = KD_PACKET_COMPLETE;
		CHECK(kd_exe_spin_batch_completed(&pending, &active));
		CHECK(kd_bench_bodies == 1 && kd_bench_completions == 1);
	}
	/* Direct helpers retain one completed body; a quota/native suffix retains
	 * its executed-call observations but cannot count as a completed body. */
	direct_packet(&pending);
	pending.complete = true;
	pending.args[0] = KD_EXE_CLOBBER_COMPLETE;
	pending.direct_strcmp = 16;
	active.packet_state = KD_PACKET_COMPLETE;
	CHECK(kd_exe_spin_batch_completed(&pending, &active));
	CHECK(kd_bench_bodies == 1 && kd_bench_completions == 1 && kd_direct_strcmp == 16);
	direct_packet(&pending);
	CHECK(!kd_exe_spin_batch_completed(&pending, &active));
	CHECK(kd_exe_spin_batch_resume(entry, &pending) == KD_EXE_RUN_NATIVE);
	CHECK(kd_bench_bodies == 1 && !kd_bench_completions && kd_direct_strcmp == 128);
	/* Keep the selected ABI2 batch accounting, without altering its protocol. */
	escape_packet(&pending);
	pending.args[0] = KD_EXE_CLOBBER_COMPLETE;
	active.packet_state = KD_PACKET_COMPLETE;
	CHECK(kd_exe_mutex_batch_completed(&pending, &active));
	CHECK(kd_bench_bodies == 1 && kd_bench_completions == 1);

	for (unsigned int gate = 0; gate < 3; gate++) {
		reset();
		if (gate == 0) kd_bench_complete_probe = false;
		if (gate == 1) kd_bench_lock_addr++;
		if (gate == 2) kd_bench_lock_addr = 0;
		steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK && !kd_bench_completions);
		CHECK(kd_bench_bodies == (u64)(gate == 0));
	}
	reset();
	steps[0] = (struct step){ KD_EXE_ENTRY_REFUSED, 0, 0, 0 };
	CHECK(run() == KD_EXE_NO_RUN && !kd_bench_bodies && !kd_bench_completions);
}
