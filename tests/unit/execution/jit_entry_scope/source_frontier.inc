/* Actual frontier consumer, with the existing bounded read/lease substitutes. */
static void frontier_packet(struct kd_jit_batch_call *call,
	struct kd_exec_continuation *cont)
{
	static const struct kd_exec_service_ops ops;
	static const unsigned char opcode[] = { 0x67, 0x48, 0x0f, 0xb9, 0x3a };

	escape_packet(call);
	kd_exec_frame_own_regs(&active);
	memset(cont, 0, sizeof(*cont));
	cont->state = KD_CONT_BOUND;
	cont->executor = current;
	cont->source_lease = true;
	cont->service_ops = &ops;
	kd_exec_frame_set_continuation(&active, cont);
	((struct kd_jit_image *)active.image)->requirements =
		KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_SOURCE_FRONTIER;
	memcpy(escape_text, opcode, sizeof(opcode));
	active.regs.ax = 0x1234;
	active.regs.di = 0x5678;
	active.regs.si = 0x9876;
	active.regs.dx = 0x2468;
	call->args[0] = KD_EXE_SOURCE_FRONTIER;
}

static void check_source_frontier(void)
{
	struct kd_jit_batch_call call;
	struct kd_exec_continuation cont;
	struct kd_regs before;
	unsigned long words[ARRAY_SIZE(stack)];

	for (unsigned int complete = 0; complete < 2; ++complete) {
		frontier_packet(&call, &cont);
		active.control_call.phase = complete ? KD_CALL_COMPLETE : KD_CALL_NONE;
		before = active.regs;
		memcpy(words, stack, sizeof(words));
		CHECK(!kd_jit_source_frontier(entry, &active, &active.regs));
		CHECK(source_range_size == 5 && source_calls == 1);
		before.orig_ax = KD_REG_ORIGIN_SUFFIX_TAG;
		CHECK(!memcmp(&before, &active.regs, sizeof(before)));
		CHECK(!memcmp(words, stack, sizeof(words)));
		CHECK(active.continuation_ip == before.ip && active.continuation_sp == before.sp);
		CHECK(entry->status_code == KD_EXE_NORMAL && !entry->tgt_addr && !entry->jump_from);
	}
	for (unsigned int bad = 0; bad < 17; ++bad) {
		frontier_packet(&call, &cont);
		switch (bad) {
		case 0: active.packet_state = KD_PACKET_MINIMAL; break;
		case 1: active.executed = false; break;
		case 2: active.logical_task = current; break;
		case 3: active.remote_request = (void *)1; break;
		case 4: active.native_request = (void *)1; break;
		case 5: active.control_call.phase = KD_CALL_ACQUIRED; break;
		case 6: active.regs.flags = 0; break;
		case 7: active.regs.sp = (unsigned long)stack + sizeof(unsigned long); break;
		case 8: active.regs.ip = ~0UL - 3; break;
		case 9: source_error = -ESTALE; break;
		case 10: stack_error = 1; break;
		case 11: escape_text[4] ^= 1; break;
		case 12: ((struct kd_jit_image *)active.image)->requirements = KD_IMAGE_REQUIRE_SERVICE_QUEUE; break;
		case 13: ((struct kd_jit_image *)active.image)->requirements = KD_IMAGE_REQUIRE_SOURCE_FRONTIER; break;
		case 14: cont.service_call.api = KD_SERVICE_MUTEX_LOCK; break;
		case 15: ((struct kd_jit_image *)active.image)->entry_abi = KD_ENTRY_ABI_LEGACY; break;
		case 16: ((struct kd_jit_image *)active.image)->immutable = 0; break;
		}
		before = active.regs;
		memcpy(words, stack, sizeof(words));
		CHECK(kd_jit_source_frontier(entry, &active, &active.regs) < 0);
		CHECK(!memcmp(&before, &active.regs, sizeof(before)));
		CHECK(!memcmp(words, stack, sizeof(words)));
		CHECK(entry->status_code == KD_EXE_NORMAL && !entry->tgt_addr && !entry->jump_from);
	}
	CHECK(kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
		KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_SOURCE_FRONTIER));
	CHECK(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
		KD_IMAGE_REQUIRE_SOURCE_FRONTIER));
	CHECK(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, KD_ENTRY_ABI_SPIN_CLOBBER_V1,
		KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_SOURCE_FRONTIER));
}
