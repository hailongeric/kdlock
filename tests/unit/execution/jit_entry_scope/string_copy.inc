static void copy_rel32(unsigned char *code, unsigned long address, unsigned int offset,
			unsigned long target)
{
	int displacement = (int)(target - address - offset - 4);
	memcpy(code + offset, &displacement, sizeof(displacement));
}

static void copy_packet(void)
{
	static const unsigned char pad[] = KD_STRSCPY_PAD_CODE_TEMPLATE;
	static const unsigned char copy[] = KD_STRSCPY_CODE_TEMPLATE;
	static const unsigned char fill[] = KD_STRSCPY_MEMSET_ENTRY_TEMPLATE;
	static const unsigned char erms[] = KD_STRSCPY_MEMSET_ERMS_TEMPLATE;

	string_packet();
	guard_code[47] = entry->requirements = guard_image.requirements = KD_IMAGE_REQUIRE_STRING_WRITE;
	active.regs.sp = (unsigned long)&stack[5];
	active.regs.bp = (unsigned long)&stack[14];
	active.regs.di = pad_destination = (unsigned long)&stack[5];
	active.regs.si = STRING_RIGHT;
	active.regs.dx = KD_STRSCPY_BYTES;
	stack[4] = PAD_RETURN;
	memset((void *)pad_destination, 0xa5, KD_STRSCPY_BYTES);
	memset(string_right, 'b', sizeof(string_right));
	string_right[15] = 0;
	memcpy(pad_text, pad, sizeof(pad));
	memcpy(copy_text, copy, sizeof(copy));
	memcpy(fill_text, fill, sizeof(fill));
	memcpy(fill_erms, erms, sizeof(erms));
	copy_return = 0xc3;
	copy_rel32(pad_text, PAD_IP, KD_STRSCPY_PAD_CALL1_DISP, COPY_IP);
	copy_rel32(pad_text, PAD_IP, KD_STRSCPY_PAD_CALL2_DISP, FILL_IP);
	copy_rel32(pad_text, PAD_IP, KD_STRSCPY_PAD_RETURN_DISP, COPY_RETURN);
	copy_rel32(copy_text, COPY_IP, KD_STRSCPY_RETURN1_DISP, COPY_RETURN);
	copy_rel32(copy_text, COPY_IP, KD_STRSCPY_RETURN2_DISP, COPY_RETURN);
	copy_rel32(copy_text, COPY_IP, KD_STRSCPY_RETURN3_DISP, COPY_RETURN);
	fill_text[5] = FILL_ERMS - FILL_IP - sizeof(fill_text);
	copy_rel32(fill_erms, FILL_ERMS, KD_STRSCPY_MEMSET_RETURN_DISP, COPY_RETURN);
	copy_rel32(string_call, PAD_RETURN - 5, 1, PAD_IP);
}

static void check_string_copy(void)
{
	for (unsigned int negative = 0; negative < 2; negative++) {
		copy_packet();
		pad_result = negative ? -7 : 15;
		steps[0] = (struct step){ KD_EXE_HOSTCALL, PAD_IP, 1, -8 };
		steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		CHECK(pad_calls == 1 && !string_calls && active.regs.ax == (unsigned long)pad_result);
		CHECK(string_read_extent == 16 && stack[4] == PAD_RETURN);
		CHECK(active.continuation_ip == PAD_RETURN && active.continuation_sp == (unsigned long)&stack[5]);
		for (unsigned int i = 0; i < KD_STRSCPY_BYTES; i++)
			CHECK(((unsigned char *)pad_destination)[i] == (i < 15 ? 'b' : 0));
		CHECK(!errors && kd_hostcall_executed == 1 && kd_hostcall_resumed == 1);
	}
	copy_packet();
	active.regs.ip = PAD_IP;
	CHECK(kd_hostcall_dispatch(&active.regs) == -EPERM && !pad_calls);
	/* Pad is a writing service and retains the legacy shared16 budget. The
	 * seventeenth pending CALL must execute on the original waiter instead. */
	for (unsigned int excess = 0; excess < 2; excess++) {
		copy_packet();
		for (unsigned int i = 0; i < KD_EXE_HL_MAX_HOSTCALLS + excess; i++)
			steps[i] = (struct step){ KD_EXE_HOSTCALL, PAD_IP, 1, -8 };
		steps[KD_EXE_HL_MAX_HOSTCALLS + excess] =
			(struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
		CHECK(run() == (excess ? KD_EXE_RUN_NATIVE : KD_EXE_RUN_TO_UNLOCK));
		CHECK(pad_calls == KD_EXE_HL_MAX_HOSTCALLS && !string_calls);
		CHECK(kd_hostcall_executed == KD_EXE_HL_MAX_HOSTCALLS && kd_hostcall_limit == excess);
		CHECK(stack[4] == PAD_RETURN && !errors && entry->status_code == KD_EXE_NORMAL);
	}

	/* Every helper/edge is part of the contract, including the small memset
	 * alternative trampoline and final actual return instruction. */
	for (unsigned int bad = 0; bad < 13; bad++) {
		unsigned long return_ip;
		unsigned char before[KD_STRSCPY_BYTES];
		copy_packet();
		active.executed = true;
		active.regs.ip = PAD_IP;
		active.regs.sp = (unsigned long)&stack[4];
		memcpy(before, (void *)pad_destination, sizeof(before));
		switch (bad) {
		case 0: guard_image.requirements = KD_IMAGE_REQUIRE_STRING_SERVICES; break;
		case 1: pad_text[0] = 0x90; break;
		case 2: pad_text[KD_STRSCPY_PAD_CALL1_DISP]++; break;
		case 3: pad_text[KD_STRSCPY_PAD_CALL2_DISP]++; break;
		case 4: pad_text[KD_STRSCPY_PAD_RETURN_DISP]++; break;
		case 5: copy_text[0] = 0x90; break;
		case 6: copy_text[KD_STRSCPY_RETURN2_DISP]++; break;
		case 7: copy_text[229] ^= 1; break;
		case 8: fill_text[5]++; break;
		case 9: fill_erms[0] ^= 1; break;
		case 10: fill_erms[KD_STRSCPY_MEMSET_RETURN_DISP]++; break;
		case 11: copy_return = 0x90; break;
		case 12: kd_string_copy_helper = 0; break;
		}
		CHECK(kd_jit_string_prepare(entry, &active, &active.regs, &return_ip) < 0);
		CHECK(!pad_calls && !memcmp(before, (void *)pad_destination, sizeof(before)));
		CHECK(stack[4] == PAD_RETURN && entry->status_code == KD_EXE_NORMAL);
	}

	/* Bounds/read failures are no-effect refusals, even if native strscpy_pad
	 * would write truncated data. Only the original waiter may run that CALL. */
	for (unsigned int bad = 0; bad < 10; bad++) {
		unsigned char before[KD_STRSCPY_BYTES];
		copy_packet();
		memcpy(before, (void *)pad_destination, sizeof(before));
		switch (bad) {
		case 0: active.regs.dx = 63; break;
		case 1: active.regs.di = (unsigned long)&stack[4]; break;
		case 2: active.regs.di = (unsigned long)&stack[7]; break;
		case 3: active.regs.bp = (unsigned long)&stack[4]; break;
		case 4: active.regs.bp = (unsigned long)&stack[15]; break;
		case 5: active.regs.si = (unsigned long)&stack[12]; break;
		case 6: active.regs.si = ~0UL - 7; break;
		case 7: string_readable = 15; break;
		case 8: string_right[15] = 'b'; break;
		case 9: string_read_error = 1; break;
		}
		steps[0] = (struct step){ KD_EXE_HOSTCALL, PAD_IP, 1, -8 };
		CHECK(run() == KD_EXE_RUN_NATIVE);
		CHECK(!pad_calls && !memcmp(before, (void *)pad_destination, sizeof(before)));
		CHECK(!memcmp(&last_wrapper_output, &active.regs, sizeof(active.regs)));
		CHECK(stack[4] == PAD_RETURN && entry->status_code == KD_EXE_NATIVE_ONLY);
		CHECK(active.continuation_ip == PAD_IP && active.continuation_sp == (unsigned long)&stack[4]);
		CHECK(!errors && !kd_hostcall_executed && active.jit_lock_depth == 1);
	}
	/* Isolate the whole-stack exclusion with a high kernel-address stack model,
	 * independently of userspace addresses used for ordinary fixture storage. */
	copy_packet();
	active.regs.sp = STRING_RIGHT + 16;
	active.regs.bp = STRING_RIGHT + 96;
	active.regs.di = STRING_RIGHT + 24;
	CHECK(kd_hostcall_strscpy_preflight(&active.regs, STRING_RIGHT - 16,
					 STRING_RIGHT + 112) == KD_HOSTCALL_NOT_EXECUTED);
	CHECK(!pad_calls && !string_read_extent);
}
