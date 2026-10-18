static void copy_packet(void)
{
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
}

static void check_string_copy(void)
{
	for (unsigned int truncated = 0; truncated < 2; truncated++) {
		copy_packet();
		pad_result = truncated ? -7 : 15;
		pad_truncates = truncated;
		if (truncated)
			string_right[15] = 'b';
		string_read_error = 1;
		steps[0] = (struct step){ KD_EXE_HOSTCALL, PAD_IP, 1, -8 };
		steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		CHECK(pad_calls == 1 && !string_calls && active.regs.ax == (unsigned long)pad_result);
		CHECK(!string_read_extent && stack_reads == 1 && stack[4] == PAD_RETURN);
		CHECK(source_calls == 1 && source_targets[0] == PAD_RETURN);
		CHECK(active.continuation_ip == PAD_RETURN && active.continuation_sp == (unsigned long)&stack[5]);
		for (unsigned int i = 0; i < KD_STRSCPY_BYTES; i++)
			CHECK(((unsigned char *)pad_destination)[i] == (i < (truncated ? 63U : 15U) ? 'b' : 0));
		CHECK(!errors && kd_hostcall_executed == 1 && kd_hostcall_resumed == 1);
	}
	copy_packet();
	active.regs.ip = PAD_IP;
	CHECK(kd_hostcall_dispatch(&active.regs) == -EPERM && !pad_calls);
	/* Pad shares the original16 scalar/control allowance. The seventeenth
	 * pending CALL must run on the original waiter without consuming its word. */
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
	/* Ownership/return errors remain before writes. No helper-specific byte,
	 * source-string or destination-range rejection is manufactured here. */
	for (unsigned int bad = 0; bad < 4; bad++) {
		unsigned long return_ip;
		unsigned char before[KD_STRSCPY_BYTES];
		copy_packet();
		active.executed = true;
		active.regs.ip = PAD_IP;
		active.regs.sp = (unsigned long)&stack[4];
		memcpy(before, (void *)pad_destination, sizeof(before));
		if (bad == 0) guard_image.requirements = KD_IMAGE_REQUIRE_STRING_SERVICES;
		if (bad == 1) stack[4] = 0;
		if (bad == 2) active.native_request = (void *)1;
		if (bad == 3) source_error = -ESTALE;
		CHECK(kd_jit_string_prepare(entry, &active, &active.regs, &return_ip) < 0);
		CHECK(!pad_calls && !memcmp(before, (void *)pad_destination, sizeof(before)));
	}
}
