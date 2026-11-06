/* Keep retained frames in their actual owner/ACCEPT fixture. Legacy-frame
 * fixtures deliberately reject this protocol and must keep that assertion. */
static void check_frontier_refusals(struct kd_exec_continuation *cont)
{
	struct kd_exec_frame saved = cont->frame;
	for (unsigned int bad = 0; bad < 18; ++bad) {
		struct kd_jit_image image = frontier_image;
		struct kd_regs before;
		unsigned long words[64];
		cont->frame = saved;
		cont->frame.image = &image;
		switch (bad) {
		case 0: cont->frame.packet_state = KD_PACKET_MINIMAL; break;
		case 1: cont->frame.executed = false; break;
		case 2: cont->frame.logical_task = current; break;
		case 3: cont->frame.remote_request = (void *)1; break;
		case 4: cont->frame.native_request = (void *)1; break;
		case 5: cont->frame.control_call.phase = KD_CALL_PENDING; break;
		case 6: cont->frame.regs.flags = 0; break;
		case 7: cont->frame.regs.sp = (unsigned long)origin_words + sizeof(unsigned long); break;
		case 8: cont->frame.regs.ip = ~0UL - 3; break;
		case 9: frontier_source_error = -ESTALE; break;
		case 10: frontier_read_error = -EFAULT; break;
		case 11: frontier_text[4] ^= 1; break;
		case 12: image.requirements = KD_IMAGE_REQUIRE_SERVICE_QUEUE; break;
		case 13: image.requirements = KD_IMAGE_REQUIRE_SOURCE_FRONTIER; break;
		case 14: cont->service_call.api = 1; break;
		case 15: image.entry_abi = KD_ENTRY_ABI_LEGACY; break;
		case 16: image.immutable = 0; break;
		case 17: cont->source_lease = false; break;
		}
		before = cont->frame.regs;
		memcpy(words, origin_words, sizeof(words));
		assert(kd_jit_source_frontier(&frontier_entry, &cont->frame, &cont->frame.regs) < 0);
		assert(!memcmp(&before, &cont->frame.regs, sizeof(before)));
		assert(!memcmp(words, origin_words, sizeof(words)));
		assert(!frontier_calls && !frontier_entry.status_code &&
		       !frontier_entry.tgt_addr && !frontier_entry.jump_from);
		frontier_source_error = frontier_read_error = 0;
		frontier_text[4] = 0x3a;
		cont->service_call.api = KD_SERVICE_NONE;
		cont->source_lease = true;
	}
	for (unsigned int i = 0; i < 2; ++i) {
		struct kd_regs before;
		frontier_instruction_length = 3;
		frontier_text[0] = 0x0f; frontier_text[1] = 0x01;
		frontier_text[2] = i ? 0xca : 0xee;
		cont->frame = saved;
		before = cont->frame.regs;
		assert(!kd_jit_source_frontier(&frontier_entry, &cont->frame, &cont->frame.regs));
		assert(frontier_calls == 1 && cont->frame.regs.ip == before.ip &&
		       cont->frame.regs.sp == before.sp && cont->frame.regs.flags == before.flags &&
		       cont->frame.regs.orig_ax == KD_REG_ORIGIN_SUFFIX_TAG);
		frontier_calls = 0;
		cont->frame = saved;
		frontier_text[2] ^= 1;
		assert(kd_jit_source_frontier(&frontier_entry, &cont->frame, &cont->frame.regs) == -EILSEQ);
		assert(!memcmp(&before, &cont->frame.regs, sizeof(before)) && !frontier_calls);
	}
	memcpy(frontier_text, (unsigned char[]){0x67,0x48,0x0f,0xb9,0x3a}, sizeof(frontier_text));
	frontier_instruction_length = sizeof(frontier_text);
	cont->frame = saved;
	assert(kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
		KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_SOURCE_FRONTIER));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
		KD_IMAGE_REQUIRE_SOURCE_FRONTIER));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, KD_ENTRY_ABI_SPIN_CLOBBER_V1,
		KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_SOURCE_FRONTIER));
}
