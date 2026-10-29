/* Production immutable-site/packet consumer; original-task execution is a
 * primitive double. The service/node ownership protocol has its own fixture. */
static struct kd_origin_site *origin_packet(struct kd_jit_batch_call *call)
{
	static unsigned char code[128];
	struct kd_jit_image *image;
	struct kd_origin_site *site = (void *)(code + 80);
	struct kd_origin_footer *footer = (void *)(code + 112);

	escape_packet(call);
	memset(code, 0, sizeof(code));
	memcpy(code + 25, "KDWC002", 7);
	memcpy(code + 41, "KDAB", 4);
	code[45] = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	code[46] = KD_IMAGE_PROTOCOL;
	code[47] = KD_IMAGE_REQUIRE_NATIVE_ESCAPE | KD_IMAGE_REQUIRE_ORIGIN_INSN;
	*site = (struct kd_origin_site) {
		.ip = ESCAPE_IP, .next_ip = ESCAPE_IP + 2, .continuation_offset = 64,
		.kind = KD_ORIGIN_RDTSC, .length = 2, .opcode = { 0x0f, 0x31 },
	};
	memcpy(footer->magic, "KDOS0001", 8);
	footer->offset = 80;
	footer->count = 1;
	image = (struct kd_jit_image *)active.image;
	image->code = code;
	image->length = sizeof(code);
	image->requirements = code[47];
	entry->requirements = code[47];
	entry->code_block = code;
	active.regs_borrowed = false;
	active.borrowed_regs = NULL;
	active.regs.ss = 7;
	active.regs.ax = 99;
	call->args[0] = KD_EXE_ORIGIN_INSN;
	call->args[1] = 1;
	string_wrapper_code = code;
	return site;
}

static void check_origin_instruction(void)
{
	struct kd_jit_batch_call call;
	struct kd_regs before;
	struct kd_origin_site *site;

	origin_packet(&call);
	before = active.regs;
	CHECK(kd_jit_origin_instruction(entry, &active, &active.regs, 1) == 1);
	CHECK(origin_calls == 1 && origin_sequence == 1 && kd_origin_instruction_count == 1);
	before.ip += 2;
	before.ax = 0x12345678;
	before.orig_ax = KD_REG_ORIGIN_REENTRY_TAG;
	CHECK(!memcmp(&before, &active.regs, sizeof(before)));
	CHECK(!kd_native_escape_count && !kd_origin_suffix_count && !kd_origin_reentry_count);
	CHECK(active.continuation_ip == ESCAPE_IP + 2 && entry->status_code == KD_EXE_NORMAL);

	/* Production dispatch returns through the same image without replaying the
	 * first wrapper or treating a service ACK as a returned-body witness. */
	for (unsigned int witness = 0; witness <= 1; witness++) {
		origin_packet(&call);
		origin_wrapper = true;
		steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, witness, 0 };
		CHECK(kd_exe_mutex_batch_resume(entry, &call) == KD_EXE_RUN_TO_UNLOCK);
		CHECK(calls == 1 && origin_calls == 1 && kd_origin_instruction_count == 1);
		CHECK(kd_origin_reentry_count == witness && !kd_origin_suffix_count);
		CHECK(!active.regs.orig_ax && active.regs.ax == 0x12345678);
	}

	/* A refused generated successor must use the already-executed opcode's
	 * post-state. No receipt or a different packet may fabricate reentry. */
	for (unsigned int bad = 0; bad < 6; bad++) {
		origin_packet(&call);
		origin_wrapper = true;
		steps[0] = (struct step){
			bad & 1 ? KD_EXE_ENTRY_REFUSED : KD_EXE_IJ_MISS,
			ESCAPE_IP + 2, bad >= 2 && bad < 4, bad == 5 ? 8 : 0,
		};
		if (bad == 4)
			steps[0].ip++;
		CHECK(kd_exe_mutex_batch_resume(entry, &call) ==
			(bad < 2 ? KD_EXE_RUN_NATIVE : KD_EXE_RUN_ERROR));
		CHECK(origin_calls == 1 && kd_origin_instruction_count == 1);
		CHECK(kd_origin_suffix_count == (bad < 2));
		CHECK(active.regs.ax == 0x12345678);
		if (bad < 2) {
			CHECK(active.regs.ip == ESCAPE_IP + 2);
			CHECK(active.regs.orig_ax == KD_REG_ORIGIN_SUFFIX_TAG);
			CHECK(!kd_origin_reentry_count);
		}
	}

	/* Refusal/quota occurs before the opcode; the original marker stays the
	 * native boundary. A forced after-service suffix must advance exactly once. */
	origin_packet(&call);
	origin_result = 0;
	CHECK(kd_jit_origin_instruction(entry, &active, &active.regs, 1) == 0);
	CHECK(origin_calls == 1 && active.regs.ip == ESCAPE_IP && active.regs.ax == 99);
	CHECK(active.regs.orig_ax == KD_REG_NATIVE_ESCAPE_TAG && kd_native_escape_count == 1);
	origin_packet(&call);
	CHECK(kd_jit_origin_instruction(entry, &active, &active.regs,
		KD_EXE_HL_MAX_CONTINUATIONS + 1) == 0);
	CHECK(!origin_calls && active.regs.ip == ESCAPE_IP && active.regs.ax == 99);
	origin_packet(&call);
	kd_origin_instruction_force_suffix = true;
	CHECK(kd_jit_origin_instruction(entry, &active, &active.regs, 1) == 2);
	CHECK(origin_calls == 1 && active.regs.ip == ESCAPE_IP + 2 && active.regs.ax == 0x12345678);
	CHECK(active.regs.orig_ax == KD_REG_ORIGIN_SUFFIX_TAG && kd_origin_suffix_count == 1);
	CHECK(!kd_native_escape_count && !kd_origin_reentry_count);

	for (unsigned int bad = 0; bad < 15; bad++) {
		site = origin_packet(&call);
		switch (bad) {
		case 0: active.mutex_backend = false; break;
		case 1: active.entry_abi = KD_ENTRY_ABI_LEGACY; break;
		case 2: active.packet_state = KD_PACKET_MINIMAL; break;
		case 3: active.image = NULL; break;
		case 4: ((struct kd_jit_image *)active.image)->requirements = 1; break;
		case 5: active.regs.ss = 0; break;
		case 6: active.regs.ss = 0x1000001; break;
		case 7: active.regs.flags = 0; break;
		case 8: active.logical_task = current; break;
		case 9: site->next_ip++; break;
		case 10: site->opcode[0] = 0x66; break;
		case 11: site->continuation_offset = 80; break;
		case 12: source_error = -ESTALE; break;
		case 13: escape_text[0] = 0x90; break;
		case 14: stack_error = 1; break;
		}
		CHECK(kd_jit_origin_instruction(entry, &active, &active.regs, 1) < 0);
		CHECK(!origin_calls && !kd_origin_instruction_count && !kd_origin_reentry_count);
	}
	origin_packet(&call);
	origin_result = -EINVAL;
	CHECK(kd_jit_origin_instruction(entry, &active, &active.regs, 1) == -EINVAL);
	CHECK(origin_calls == 1 && active.regs.ax == 99 && active.regs.ip == ESCAPE_IP);
}
