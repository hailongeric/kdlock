/* The guard consumer sees a published, bound image and its exact FULL exit.
 * The generated predicate/flags proof and real waiter restore are separate
 * checks. These cases ensure no malformed boundary grants native execution. */
static unsigned char guard_code[128];
static struct kd_jit_image guard_image;

static struct kd_address_guard_site *guard_packet(struct kd_jit_batch_call *call)
{
	struct kd_address_guard_site *site = (void *)(guard_code + 80);
	struct kd_address_guard_footer *footer = (void *)(guard_code + 112);

	reset();
	memset(guard_code, 0, sizeof(guard_code));
	memcpy(guard_code + 9, "KDWB002", 7);
	memcpy(guard_code + 25, "KDWC002", 7);
	memcpy(guard_code + 41, "KDAB", 4);
	guard_code[45] = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	guard_code[46] = KD_IMAGE_PROTOCOL;
	guard_code[47] = KD_IMAGE_REQUIRE_ADDRESS_GUARD;
	memcpy(footer->magic, "KDAG0001", 8);
	footer->offset = 80;
	footer->count = 1;
	site->ip = ESCAPE_IP;
	site->length = 3;
	site->proof = KD_ADDRESS_GUARD_PROOF;
	site->opcode[0] = 0x48;
	site->opcode[1] = 0x8b;
	site->opcode[2] = 0x00;
	memcpy(escape_text, site->opcode, site->length);
	active.entry_abi = entry->entry_abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	entry->requirements = KD_IMAGE_REQUIRE_ADDRESS_GUARD;
	entry->code_block = guard_code;
	guard_image = (struct kd_jit_image){ .code = guard_code,
		.length = sizeof(guard_code), .generation = 2,
		.requirements = KD_IMAGE_REQUIRE_ADDRESS_GUARD,
		.entry_abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1, .entry = entry,
		.immutable = 1 };
	active.image = &guard_image;
	active.spin_simple = true;
	active.packet_state = KD_PACKET_FULL;
	active.executed = true;
	active.regs.ip = site->ip;
	active.regs.orig_ax = KD_REG_ADDRESS_GUARD_TAG;
	*call = (struct kd_jit_batch_call){ .regs = &active.regs,
		.args = { KD_EXE_ADDRESS_GUARD, 1 },
		.entry_abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1,
		.packet_state = &active.packet_state, .entry_sp = active.regs.sp };
	return site;
}

static void check_address_guard(void)
{
	struct kd_jit_batch_call call;
	struct kd_regs before;
	struct kd_address_guard_site *site;
	unsigned int count;

	guard_packet(&call);
	before = active.regs;
	CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_NATIVE);
	before.orig_ax = 0;
	CHECK(!memcmp(&before, &active.regs, sizeof(before)));
	CHECK(active.continuation_ip == before.ip &&
	      active.continuation_sp == before.sp && !known_calls);
	CHECK(entry->status_code == KD_EXE_NATIVE_ONLY && warnings == 1 && !errors);
	CHECK(kd_address_guard_count == 1);
	CHECK(!kd_exe_publish_status(entry, KD_EXE_NORMAL));
	CHECK(source_calls == 1 && source_targets[0] == before.ip);
	/* The original waiter finishes only the suffix; no synthetic CALL word
	 * is pushed or consumed and the old bound image survives publication. */
	CHECK(stack[8] == 0x1005);
	for (unsigned int bad = 0; bad < 25; bad++) {
		site = guard_packet(&call);
		switch (bad) {
		case 0: active.mutex_backend = true; break;
		case 1: active.entry_abi = KD_ENTRY_ABI_RWLOCK_CLOBBER_V1; break;
		case 2: active.packet_state = KD_PACKET_MINIMAL; break;
		case 3: active.image = NULL; break;
		case 4: guard_image.requirements = 0; break;
		case 5: guard_image.immutable = 0; break;
		case 6: guard_image.entry = entry + 1; break;
		case 7: active.executed = false; break;
		case 8: active.logical_task = current; break;
		case 9: active.regs.ip++; break;
		case 10: active.regs.orig_ax++; break;
		case 11: active.regs.orig_ax ^= 1UL << 40; break;
		case 12: active.regs.sp = (unsigned long)stack; break;
		case 13: active.remote_request = (void *)1; break;
		case 14: active.native_request = (void *)1; break;
		case 15: active.control_call.phase = KD_CALL_ACQUIRED; break;
		case 16: active.outer_unlock_seen = true; break;
		case 17: active.parent = &parent; break;
		case 18: guard_code[112] = 0; break;
		case 19: site->proof = 0; break;
		case 20: site->opcode[1] = 0x89; break;
		case 21: site->opcode[15] = 1; break;
		case 22: escape_text[2] = 1; break;
		case 23: source_error = -ESTALE; break;
		case 24: stack_error = 1; break;
		}
		CHECK(kd_jit_address_guard(entry, &active, &active.regs) < 0);
		CHECK(entry->status_code == KD_EXE_NORMAL && !warnings && !kd_address_guard_count);
	}
	guard_packet(&call);
	active.control_call.phase = KD_CALL_COMPLETE;
	CHECK(kd_jit_address_guard(entry, &active, &active.regs) == 0);
	CHECK(active.control_call.phase == KD_CALL_NONE);
	/* Trailer limits and offsets do not permit reads outside the image. */
	for (unsigned int bad = 0; bad < 4; bad++) {
		struct kd_address_guard_footer *footer;
		guard_packet(&call);
		footer = (void *)(guard_code + 112);
		if (bad == 0) footer->count = 0;
		if (bad == 1) footer->count = KD_ADDRESS_GUARD_MAX + 1;
		if (bad == 2) footer->offset = ~0U;
		if (bad == 3) guard_image.length = KD_IMAGE_HEADER_SIZE;
		CHECK(!kd_image_guard_sites(&guard_image, &count));
	}
	guard_packet(&call);
	call.args[0] = KD_EXE_INST_LIMIT;
	CHECK(kd_exe_spin_batch_resume(entry, &call) == KD_EXE_RUN_ERROR);
	CHECK(entry->status_code == KD_EXE_NORMAL && errors == 1);
}
