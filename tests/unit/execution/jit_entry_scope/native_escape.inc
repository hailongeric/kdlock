/* Execute the production marker consumer with substituted wrapper packets.
 * Real assembly restoration and generated markers have separate VM tests. */
static void escape_packet(struct kd_jit_batch_call *call)
{
	static unsigned char code[64];
	static struct kd_exec_outer_unlock hook;

	reset();
	memset(code, 0, sizeof(code));
	memcpy(code + 25, "KDWC002", 7);
	memcpy(code + 41, "KDAB", 4);
	code[45] = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	active.mutex_backend = active.batch_lease = active.regs_borrowed = true;
	active.borrowed_regs = &active.regs;
	active.entry_abi = entry->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	active.packet_state = KD_PACKET_MINIMAL;
	active.jit_lock_node[0] = &active;
	active.outer_unlock_hook = &hook;
	entry->lock_kind = KD_EXE_LOCK_MUTEX;
	entry->requirements = KD_IMAGE_REQUIRE_NATIVE_ESCAPE;
	entry->code_block = code;
	CHECK(kd_exe_mutex_batch_prepare(entry, &active, call));
	active.executed = true;
	active.packet_state = KD_PACKET_FULL;
	active.regs.ip = ESCAPE_IP;
	active.regs.flags = 0x8d7;
	call->args[0] = KD_EXE_NATIVE_ESCAPE;
	call->args[1] = 1;
}

static void check_native_escape(void)
{
	struct kd_jit_batch_call call;
	struct kd_regs before;
	const unsigned char reviewed[][3] = {
		{0x0f, 0x31}, {0x0f, 0x01, 0xf9}, {0x0f, 0xa2},
		{0xfa}, {0xfb}, {0xfc}, {0xfd}, {0x0f, 0x32},
		{0x0f, 0x30}, {0x0f, 0x33}, {0x9f}, {0x9e},
	};
	for (unsigned int i = 0; i < ARRAY_SIZE(reviewed); i++) {
		escape_packet(&call);
		memcpy(escape_text, reviewed[i], sizeof(reviewed[i]));
		before = active.regs;
		CHECK(kd_exe_mutex_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
		CHECK(active.regs.ip == before.ip && active.regs.sp == before.sp);
		CHECK(active.regs.flags == before.flags &&
		      active.regs.orig_ax == KD_REG_NATIVE_ESCAPE_TAG);
		before.orig_ax = KD_REG_NATIVE_ESCAPE_TAG;
		CHECK(!memcmp(&before, &active.regs, sizeof(before)));
		CHECK(active.continuation_ip == before.ip &&
		      active.continuation_sp == before.sp);
		CHECK(entry->status_code == KD_EXE_NORMAL);
		CHECK(kd_native_escape_count == 1 && !errors && warnings == 1 &&
		      source_calls == 1 && !known_calls);
		CHECK(kd_exe_entry_is_ready(entry, 0, active.entry_ip));
	}
	/* A retained invocation may finish after another publisher or policy
	 * decision changes the entry. It must neither ban nor reopen that entry. */
	const int statuses[] = { KD_EXE_NORMAL, KD_EXE_NATIVE_ONLY, KD_EXE_CALL_MISS };
	for (unsigned int i = 0; i < ARRAY_SIZE(statuses); i++) {
		escape_packet(&call);
		entry->status_code = statuses[i];
		entry->generation = 19;
		entry->tgt_addr = 0xabc;
		entry->jump_from = 0xdef;
		CHECK(!kd_jit_native_escape(entry, &active, &active.regs));
		CHECK(entry->status_code == statuses[i] && entry->generation == 19 &&
		      entry->tgt_addr == 0xabc && entry->jump_from == 0xdef);
		if (statuses[i] == KD_EXE_NATIVE_ONLY)
			CHECK(!kd_exe_publish_status(entry, KD_EXE_NORMAL));
	}
	/* Reject malformed markers before tagging or source-side execution. */
	for (unsigned int bad = 0; bad < 15; bad++) {
		escape_packet(&call);
		active.regs_borrowed = false;
		switch (bad) {
		case 0: active.mutex_backend = false; break;
		case 1: active.entry_abi = KD_ENTRY_ABI_LEGACY; break;
		case 2: active.packet_state = KD_PACKET_MINIMAL; break;
		case 3: active.image = NULL; break;
		case 4: ((struct kd_jit_image *)active.image)->requirements = 0; break;
		case 5: active.executed = false; break;
		case 6: active.logical_task = current; break;
		case 7: active.remote_request = (void *)1; break;
		case 8: active.native_request = (void *)1; break;
		case 9: active.control_call.phase = KD_CALL_ACQUIRED; break;
		case 10: active.regs.flags = 0; break;
		case 11: active.regs.sp = (unsigned long)stack + sizeof(unsigned long); break;
		case 12: source_error = -ESTALE; break;
		case 13: escape_text[0] = 0x66; break;
		case 14: stack_error = 1; break;
		}
		CHECK(kd_jit_native_escape(entry, &active, &active.regs) < 0);
		CHECK(entry->status_code == KD_EXE_NORMAL && !kd_native_escape_count &&
		      active.regs.orig_ax != KD_REG_NATIVE_ESCAPE_TAG);
	}
	/* A completed earlier control does not describe the new source marker. */
	escape_packet(&call);
	active.control_call.phase = KD_CALL_COMPLETE;
	CHECK(kd_exe_mutex_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
	CHECK(active.control_call.phase == KD_CALL_NONE);
	/* Generic native CALL exits must erase a stale marker tag. */
	escape_packet(&call);
	active.regs.orig_ax = KD_REG_NATIVE_ESCAPE_TAG;
	active.regs.ip = 0xdead;
	call.args[0] = KD_EXE_CALL_MISS;
	known_result = 0;
	CHECK(kd_exe_mutex_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
	CHECK(!active.regs.orig_ax && !kd_native_escape_count &&
	      entry->status_code == KD_EXE_CALL_MISS);
}
