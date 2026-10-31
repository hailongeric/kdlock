/* Pristine ABI1/ABI3 admission and terminal marker decisions use production
 * predicates. Wrapper, physical owner and source-residency primitives remain
 * substitutes; this does not claim execution of generated instructions. */
static unsigned char root_escape_code[64];
static struct kd_jit_image root_escape_image;

static void root_escape_entry(unsigned int abi)
{
	reset();
	memset(root_escape_code, 0, sizeof(root_escape_code));
	memcpy(root_escape_code + 9, "KDWB002", 7);
	memcpy(root_escape_code + 25, "KDWC002", 7);
	memcpy(root_escape_code + 41, "KDAB", 4);
	root_escape_code[45] = abi;
	root_escape_code[46] = KD_IMAGE_PROTOCOL;
	root_escape_code[47] = KD_IMAGE_REQUIRE_NATIVE_ESCAPE |
			       KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE;
	entry->entry_abi = active.entry_abi = abi;
	entry->requirements = root_escape_code[47];
	entry->code_block = root_escape_code;
	root_escape_image = (struct kd_jit_image){
		.code = root_escape_code, .length = sizeof(root_escape_code),
		.entry = entry, .entry_abi = abi, .generation = 7,
		.requirements = entry->requirements, .immutable = 1,
	};
	active.image = &root_escape_image;
	active.spin_simple = active.request_frame = true;
	active.spin_regs_decoded = true;
	active.spin_kind = KD_SPIN_CONT_ROOT;
	active.packet_state = KD_PACKET_MINIMAL;
	active.regs.flags = 0x8d7;
	active.jit_lock_node[0] = &active;
	root_escape_wrapper = true;
}

static void root_escape_pending(unsigned int abi, struct kd_jit_batch_call *call)
{
	root_escape_entry(abi);
	active.executed = true;
	active.rwlock_admitted = abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1;
	active.packet_state = KD_PACKET_FULL;
	active.regs.ip = ESCAPE_IP;
	*call = (struct kd_jit_batch_call){
		.regs = &active.regs, .args = { KD_EXE_NATIVE_ESCAPE, 1 },
		.entry_sp = active.regs.sp, .entry_abi = abi,
		.packet_state = &active.packet_state,
		.lock = active.outer_lock_addr, .unlock = clobber_spin_unlock_addr,
		.complete = true,
	};
}

static void check_root_escape_admission(unsigned int abi)
{
	struct kd_jit_batch_call call, untouched;
	struct kd_exec_frame before;
	struct kd_regs foreign;

	root_escape_entry(abi);
	CHECK(kd_jit_root_escape_entry(&active));
	active.spin_simple = false;
	CHECK(kd_jit_root_escape_entry(&active)); /* An initialized exact root. */
	active.spin_simple = true;
	active.complex_ready = false;
	/* Before batch binding these fields are cold, not a stale owner ledger.
	 * Admission must not demand a writer lease or inspect this routing tail. */
	active.resume_target = &parent;
	active.remote_request = (void *)1;
	active.native_request = (void *)1;
	active.held_lock_depth = active.outer_lock_depth = active.jit_lock_depth = 99;
	active.outer_lock_index = 99;
	active.outer_unlock_seen = true;
	active.control_call.phase = KD_CALL_ACQUIRED;
	active.remote_result = KD_EXEC_REMOTE_WAITING;
	CHECK(!active.batch_lease && !active.rwlock_admitted);
	CHECK(kd_jit_root_escape_entry(&active));
	CHECK(kd_exe_spin_batch_prepare(entry, &active, &call));
	CHECK(call.complete && call.regs == &active.regs &&
	      call.entry_abi == abi && call.unlock == clobber_spin_unlock_addr);

	for (unsigned int bad = 0; bad < 19; bad++) {
		root_escape_entry(abi);
		active.complex_ready = false;
		foreign = active.regs;
		switch (bad) {
		case 0: active.logical_task = current; break;
		case 1: active.parent = &parent; break;
		case 2: active.depth = 1; break;
		case 3: active.executed = true; break;
		case 4: active.packet_state = KD_PACKET_FULL; break;
		case 5: active.request_frame = false; break;
		case 6: active.completion_seen = true; break;
		case 7: active.spin_kind = KD_SPIN_CONT_VIRTUAL; break;
		case 8: active.spin_regs_decoded = false; break;
		case 9: active.spin_simple = false; break;
		case 10: active.regs_ref = &foreign; break;
		case 11: active.regs_borrowed = true;
			 active.borrowed_regs = &active.regs; break;
		case 12: root_escape_image.immutable = 0; break;
		case 13: active.entry_abi = KD_ENTRY_ABI_LEGACY; break;
		case 14: active.mutex_backend = true; break;
		case 15: active.regs.ip++; break;
		case 16: active.regs.sp = 0; break;
		case 17: active.state = KD_EXEC_FRAME_WAITING_LOCK; break;
		case 18: active.outer_lock_addr = 0; break;
		}
		memset(&call, 0xa5, sizeof(call));
		memcpy(&untouched, &call, sizeof(call));
		memcpy(&before, &active, sizeof(before));
		CHECK(!kd_jit_root_escape_entry(&active));
		CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
		CHECK(!memcmp(&before, &active, sizeof(before)) &&
		      !memcmp(&untouched, &call, sizeof(call)) && !calls);
	}

	/* Generic entry must refuse the same inadmissible scope before a wrapper,
	 * including cases which otherwise pass the general frame validator. */
	for (unsigned int bad = 0; bad < 16; bad++) {
		int result;

		root_escape_entry(abi);
		foreign = active.regs;
		switch (bad) {
		case 0: active.logical_task = current; break;
		case 1: active.parent = &parent; break;
		case 2: active.depth = 1; break;
		case 3: active.packet_state = KD_PACKET_FULL; break;
		case 4: active.request_frame = false; break;
		case 5: active.spin_kind = KD_SPIN_CONT_VIRTUAL; break;
		case 6: active.spin_regs_decoded = false; break;
		case 7: active.regs_borrowed = true;
			active.borrowed_regs = &active.regs; break;
		case 8: active.regs_ref = &foreign; break;
		case 9: active.held_lock_depth = 2; break;
		case 10: active.outer_lock_depth = 0; break;
		case 11: active.jit_lock_kind[0] = KD_EXEC_LOCK_FAST; break;
		case 12: active.jit_lock_released[0] = true; break;
		case 13: active.remote_request = (void *)1; break;
		case 14: active.native_request = (void *)1; break;
		case 15: root_escape_image.immutable = 0; break;
		}
		memcpy(&before, &active, sizeof(before));
		result = run();
		CHECK(result == KD_EXE_NO_RUN || result == KD_EXE_RUN_ERROR);
		CHECK(!calls && !known_calls && !source_calls &&
		      !memcmp(&before, &active, sizeof(before)));
	}
	root_escape_entry(abi);
	active.image = NULL;
	active.spin_regs_decoded = false;
	CHECK(run() == KD_EXE_NO_RUN && !active.image && !calls);
	/* A generated pre-body refusal preserves the MINIMAL packet; normal
	 * COMPLETE does not interpret an incidental instruction tag as an exit. */
	root_escape_entry(abi);
	steps[0] = (struct step){ KD_EXE_ENTRY_REFUSED, 0, 0, 0 };
	CHECK(run() == KD_EXE_NO_RUN && calls == 1 && !active.executed &&
	      active.packet_state == KD_PACKET_MINIMAL && !source_calls);
	root_escape_entry(abi);
	active.regs.orig_ax = KD_REG_NATIVE_ESCAPE_TAG;
	steps[0] = (struct step){ KD_EXE_CLOBBER_COMPLETE, 0, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK && calls == 1 &&
	      active.packet_state == KD_PACKET_COMPLETE && !kd_native_escape_count);
	root_escape_entry(abi);
	active.rwlock_admitted = abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1;
	steps[0] = (struct step){ KD_EXE_NATIVE_ESCAPE, ESCAPE_IP, 1, 0 };
	CHECK(run() == KD_EXE_RUN_NATIVE && calls == 1 &&
	      active.regs.orig_ax == KD_REG_NATIVE_ESCAPE_TAG &&
	      kd_native_escape_count == 1 && entry->status_code == KD_EXE_NORMAL);
	root_escape_entry(abi);
	steps[0] = (struct step){ KD_EXE_CALL_MISS, clobber_spin_unlock_addr, 1, -8 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK && calls == 1 && known_calls == 1 &&
	      !kd_native_escape_count);
	/* The old simple-root raw unlock shortcut must not bypass the stricter
	 * contract, even for the exact outer object and a fresh FULL return. */
	root_escape_entry(abi);
	steps[0] = (struct step){ KD_EXE_CALL_MISS, raw_spin_unlock_addr, 1, -8 };
	CHECK(run() == KD_EXE_RUN_ERROR && calls == 1 && !known_calls &&
	      !kd_native_escape_count);
}

static void check_root_escape_returns(unsigned int abi)
{
	static const unsigned char reviewed[][3] = {
		{0x0f, 0x31}, {0x0f, 0x01, 0xf9}, {0x0f, 0xa2},
		{0xfa}, {0xfb}, {0xfc}, {0xfd}, {0x0f, 0x32},
		{0x0f, 0x30}, {0x0f, 0x33}, {0x9f}, {0x9e},
	};
	struct kd_jit_batch_call call;
	struct kd_regs before;

	for (unsigned int i = 0; i < ARRAY_SIZE(reviewed); i++) {
		root_escape_pending(abi, &call);
		memcpy(escape_text, reviewed[i], sizeof(reviewed[i]));
		before = active.regs;
		/* An older retained image may finish, without changing the current
		 * generation's eligibility or requesting a new publication. */
		entry->generation = root_escape_image.generation + 1;
		CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
		before.orig_ax = KD_REG_NATIVE_ESCAPE_TAG;
		CHECK(!memcmp(&before, &active.regs, sizeof(before)));
		CHECK(active.continuation_ip == before.ip &&
		      active.continuation_sp == before.sp);
		CHECK(!calls && !known_calls && complex_preparations == 1 &&
		      source_calls == 1 && source_targets[0] == ESCAPE_IP &&
		      kd_native_escape_count == 1 && !errors);
		CHECK(active.jit_lock_depth == 1 && active.held_lock_depth == 1 &&
		      active.outer_lock_depth == 1 && !active.outer_unlock_seen &&
		      !active.jit_lock_released[0] && active.jit_lock_node[0] == &active);
		CHECK(entry->status_code == KD_EXE_NORMAL &&
		      entry->generation == root_escape_image.generation + 1);
	}
	/* Admission may close after this frame binds. A marker is not permission
	 * to reopen an independently banned entry, including a newer generation. */
	root_escape_pending(abi, &call);
	entry->status_code = KD_EXE_NATIVE_ONLY;
	entry->generation = root_escape_image.generation + 1;
	CHECK(!kd_jit_native_escape(entry, &active, &active.regs));
	CHECK(entry->status_code == KD_EXE_NATIVE_ONLY &&
	      entry->generation == root_escape_image.generation + 1 &&
	      !kd_exe_publish_status(entry, KD_EXE_NORMAL));
	for (unsigned int bad = 0; bad < 29; bad++) {
		root_escape_pending(abi, &call);
		switch (bad) {
		case 0: active.parent = &parent; break;
		case 1: active.depth = 1; break;
		case 2: active.resume_target = &parent; break;
		case 3: active.held_lock_depth = 2; break;
		case 4: active.outer_lock_depth = 0; break;
		case 5: active.jit_lock_depth = 2; break;
		case 6: active.outer_lock_index = 1; break;
		case 7: active.jit_lock_addr[0]++; break;
		case 8: active.jit_lock_kind[0] = KD_EXEC_LOCK_NATIVE; break;
		case 9: active.jit_lock_released[0] = true; break;
		case 10: active.outer_unlock_seen = true; break;
		case 11: active.remote_result = KD_EXEC_REMOTE_NATIVE; break;
		case 12: active.remote_request = (void *)1; break;
		case 13: active.native_request = (void *)1; break;
		case 14: active.control_call.phase = KD_CALL_COMPLETE; break;
		case 15: active.spin_kind = KD_SPIN_CONT_VIRTUAL; break;
		case 16: active.complex_ready = false; break;
		case 17: active.regs_borrowed = true;
			 active.borrowed_regs = &active.regs; break;
		case 18: root_escape_image.immutable = 0; break;
		case 19: root_escape_image.entry = NULL; break;
		case 20: root_escape_image.entry_abi = KD_ENTRY_ABI_LEGACY; break;
		case 21: root_escape_image.requirements = KD_IMAGE_REQUIRE_NATIVE_ESCAPE; break;
		case 22: active.packet_state = KD_PACKET_MINIMAL; break;
		case 23: active.executed = false; break;
		case 24: active.logical_task = current; break;
		case 25: active.regs.flags = 0; break;
		case 26: source_error = -ESTALE; break;
		case 27: escape_text[0] = 0x66; break;
		case 28: active.regs.sp = (unsigned long)stack + sizeof(unsigned long); break;
		}
		CHECK(kd_jit_native_escape(entry, &active, &active.regs) < 0);
		CHECK(entry->status_code == KD_EXE_NORMAL && !kd_native_escape_count &&
		      active.regs.orig_ax != KD_REG_NATIVE_ESCAPE_TAG && !calls);
	}
	if (abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1) {
		root_escape_pending(abi, &call);
		active.rwlock_admitted = false;
		CHECK(kd_jit_native_escape(entry, &active, &active.regs) < 0 &&
		      !source_calls && !kd_native_escape_count);
	}
	/* Ordinary CALL packets retain their return word and use ordinary native
	 * restore even when their unused orig_ax happens to contain an old tag. */
	root_escape_pending(abi, &call);
	active.regs.ip = 0xdead;
	active.regs.sp = (unsigned long)&stack[8];
	active.regs.orig_ax = KD_REG_NATIVE_ESCAPE_TAG;
	before = active.regs;
	call.args[0] = KD_EXE_CALL_MISS;
	known_result = 0;
	CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
	before.orig_ax = 0;
	CHECK(!memcmp(&before, &active.regs, sizeof(before)) && stack[8] == 0x1005 &&
	      !calls && known_calls == 1 && !kd_native_escape_count &&
	      entry->status_code == KD_EXE_CALL_MISS);
	/* A malformed generated control or service must not execute on a foreign
	 * task. The terminal outer unlock is covered by normal completion above. */
	for (unsigned int bad = 0; bad < 14; bad++) {
		const unsigned long controls[] = {
			raw_spin_lock_addr, clobber_spin_lock_addr, pinned_spin_lock_addr,
			raw_spin_unlock_addr, clobber_spin_unlock_addr, cold_spin_unlock_addr,
			mutex_lock_addr, mutex_unlock_addr, direct_mutex_lock_addr,
			contended_mutex_lock_addr, outer_mutex_lock_addr, direct_mutex_unlock_addr,
			rwlock_fast_unlock_addr,
		};
		root_escape_pending(abi, &call);
		active.regs.di = active.outer_lock_addr + 8;
		active.regs.ip = bad < ARRAY_SIZE(controls) ? controls[bad] : kd_hostcalls[0].addr;
		call.args[0] = bad < ARRAY_SIZE(controls) ? KD_EXE_CALL_MISS : KD_EXE_HOSTCALL;
		CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_ERROR);
		CHECK(!calls && !known_calls && !source_calls && !kd_hostcall_executed);
	}
	/* A handler double which incorrectly offers continuation cannot reenter
	 * the wrapper. Keep this independent of the explicit target denylist. */
	root_escape_entry(abi);
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0xdead, 1, -8 };
	CHECK(run() == KD_EXE_RUN_ERROR && calls == 1 && known_calls == 1 &&
	      active.continuation_ip == 0x1005 && !kd_native_escape_count);
}

static void check_root_native_escape(void)
{
	const unsigned int abis[] = {
		KD_ENTRY_ABI_SPIN_CLOBBER_V1, KD_ENTRY_ABI_RWLOCK_CLOBBER_V1,
	};
	for (unsigned int i = 0; i < ARRAY_SIZE(abis); i++) {
		check_root_escape_admission(abis[i]);
		check_root_escape_returns(abis[i]);
	}
}
