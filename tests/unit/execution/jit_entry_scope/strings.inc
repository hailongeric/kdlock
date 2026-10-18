/* The helper and wrapper are doubles; source-byte matching, ownership, packet
 * validation, preflight, budget and single CALL consumption are production. */
static void string_packet(void)
{
	static const unsigned char code[KD_STRCMP_CODE_BYTES] = KD_STRCMP_CODE_TEMPLATE;
	struct kd_jit_batch_call unused;
	int displacement;

	guard_packet(&unused);
	guard_code[47] = entry->requirements = guard_image.requirements =
		KD_IMAGE_REQUIRE_STRING_SERVICES;
	string_wrapper = true;
	string_wrapper_code = guard_code;
	active.executed = active.spin_simple = false;
	active.regs.ip = active.entry_ip;
	active.regs.orig_ax = 0;
	active.regs.di = STRING_LEFT;
	active.regs.si = STRING_RIGHT;
	stack[8] = STRING_RETURN;
	memcpy(string_text, code, sizeof(code));
	displacement = kd_string_return_thunk - (STRING_IP + KD_STRCMP_TAIL1_DISP + 4);
	memcpy(string_text + KD_STRCMP_TAIL1_DISP, &displacement, sizeof(displacement));
	displacement = kd_string_return_thunk - (STRING_IP + KD_STRCMP_TAIL2_DISP + 4);
	memcpy(string_text + KD_STRCMP_TAIL2_DISP, &displacement, sizeof(displacement));
	string_call[0] = 0xe8;
	displacement = (int)(STRING_IP - STRING_RETURN);
	memcpy(string_call + 1, &displacement, sizeof(displacement));
	memset(string_left, 'a', sizeof(string_left));
	memset(string_right, 'b', sizeof(string_right));
	string_left[sizeof(string_left) - 1] = 0;
	string_right[sizeof(string_right) - 1] = 0;
}

static void check_string_services(void)
{
	/* Exact EAX width; both arguments stay original, without scratch copies. */
	for (int result = -1; result <= 1; result++) {
		string_packet();
		string_result = result;
		steps[0] = (struct step){ KD_EXE_HOSTCALL, STRING_IP, 1, -8 };
		steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		CHECK(string_calls == 1 && active.regs.ax == (unsigned int)result);
		CHECK(active.regs.si == STRING_RIGHT && stack[8] == STRING_RETURN);
		CHECK(active.continuation_ip == STRING_RETURN &&
		      active.continuation_sp == (unsigned long)&stack[9]);
		CHECK(!errors && kd_hostcall_executed == 1 && kd_hostcall_resumed == 1);
	}
	/* The scalar dispatcher is not a bypass around string preflight. */
	string_packet();
	active.regs.ip = STRING_IP;
	CHECK(kd_hostcall_dispatch(&active.regs) == -EPERM && !string_calls);
	/* Both the linked thunk jumps and the live kernel's exact RET/INT3 patch
	 * are valid. Padding is part of the source identity, not arbitrary code. */
	for (unsigned int mask = 1; mask < 4; mask++) {
		static const unsigned char patched[5] = KD_STRCMP_RETURN_TEMPLATE;
		unsigned long return_ip;
		string_packet();
		active.executed = true;
		active.regs.ip = STRING_IP;
		active.regs.sp = (unsigned long)&stack[8];
		if (mask & 1)
			memcpy(string_text + KD_STRCMP_TAIL1_DISP - 1, patched, sizeof(patched));
		if (mask & 2)
			memcpy(string_text + KD_STRCMP_TAIL2_DISP - 1, patched, sizeof(patched));
		CHECK(!kd_jit_string_prepare(entry, &active, &active.regs, &return_ip));
		if (mask == 3) {
			kd_string_return_thunk = 0;
			CHECK(!kd_jit_string_prepare(entry, &active, &active.regs, &return_ip));
		}
		string_text[(mask & 1) ? KD_STRCMP_TAIL1_DISP : KD_STRCMP_TAIL2_DISP] = 0x90;
		CHECK(kd_jit_string_prepare(entry, &active, &active.regs, &return_ip) < 0);
		CHECK(!string_calls);
	}

	/* Invalid ownership/image/source packets cause no service or replay. */
	for (unsigned int bad = 0; bad < 23; bad++) {
		struct kd_regs before;
		unsigned long return_ip = 0;
		string_packet();
		active.executed = true;
		active.regs.ip = STRING_IP;
		active.regs.sp = (unsigned long)&stack[8];
		switch (bad) {
		case 0: active.image = NULL; break;
		case 1: guard_image.requirements = 0; break;
		case 2: guard_image.immutable = 0; break;
		case 3: guard_image.entry = entry + 1; break;
		case 4: active.entry_abi = 3; break;
		case 5: active.mutex_backend = true; break;
		case 6: active.packet_state = KD_PACKET_MINIMAL; break;
		case 7: active.logical_task = current; break;
		case 8: active.parent = &parent; break;
		case 9: active.remote_request = (void *)1; break;
		case 10: active.native_request = (void *)1; break;
		case 11: active.control_call.phase = KD_CALL_PENDING; break;
		case 12: active.regs.sp = (unsigned long)&stack[3]; break;
		case 13: stack[8] = 0; break;
		case 14: string_call[0] = 0x90; break;
		case 15: string_call[1]++; break;
		case 16: string_text[0] = 0x90; break;
		case 17: string_text[KD_STRCMP_TAIL1_DISP]++; break;
		case 18: string_text[KD_STRCMP_TAIL2_DISP]++; break;
		case 19: kd_string_return_thunk = 0; break;
		case 20: source_error = -ESTALE; break;
		case 21: active.regs.ip++; break;
		case 22: kd_hostcalls[3].flags = 0; break;
		}
		before = active.regs;
		CHECK(kd_jit_string_prepare(entry, &active, &active.regs, &return_ip) < 0);
		CHECK(!memcmp(&before, &active.regs, sizeof(before)) && !string_calls);
		CHECK(entry->status_code == KD_EXE_NORMAL);
	}

	/* Argument refusals are before helper/packet effects; native keeps CALL. */
	for (unsigned int bad = 0; bad < 6; bad++) {
		string_packet();
		switch (bad) {
		case 0: active.regs.di = 0; break;
		case 1: active.regs.si = 0x1000; break;
		case 2: active.regs.di = ~0UL - 1; break;
		case 3: string_left[sizeof(string_left) - 1] = 'x'; break;
		case 4: string_right[sizeof(string_right) - 1] = 'x'; break;
		case 5: string_read_error = 1; break;
		}
		steps[0] = (struct step){ KD_EXE_HOSTCALL, STRING_IP, 1, -8 };
		CHECK(run() == KD_EXE_RUN_NATIVE);
		CHECK(!memcmp(&last_wrapper_output, &active.regs, sizeof(active.regs)));
		CHECK(!string_calls && !kd_hostcall_executed && !errors);
		CHECK(entry->status_code == KD_EXE_NATIVE_ONLY && stack[8] == STRING_RETURN);
		CHECK(active.continuation_ip == STRING_IP && active.continuation_sp == (unsigned long)&stack[8]);
		CHECK(active.control_call.phase == KD_CALL_NONE && active.jit_lock_depth == 1);
		CHECK(!kd_exe_publish_status(entry, KD_EXE_NORMAL));
	}

	/* Keep the old shared scalar/control16 limit; strings add only their own128. */
	for (unsigned int legacy = 0; legacy <= KD_EXE_HL_MAX_CONTINUATIONS; legacy += KD_EXE_HL_MAX_CONTINUATIONS) {
		for (unsigned int excess = 0; excess < 2; excess++) {
			string_packet();
			for (unsigned int i = 0; i < legacy; i++)
				steps[i] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
			for (unsigned int i = 0; i < KD_STRCMP_MAX_CALLS + excess; i++)
				steps[legacy + i] = (struct step){ KD_EXE_HOSTCALL, STRING_IP, 1, -8 };
			steps[legacy + KD_STRCMP_MAX_CALLS + excess] =
				(struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
			CHECK(run() == (excess ? KD_EXE_RUN_NATIVE : KD_EXE_RUN_TO_UNLOCK));
			CHECK(string_calls == KD_STRCMP_MAX_CALLS && service_calls[0] == legacy);
			CHECK(kd_hostcall_executed == KD_STRCMP_MAX_CALLS + legacy && !errors);
			CHECK(kd_hostcall_limit == excess && stack[8] == STRING_RETURN);
			CHECK(entry->status_code == KD_EXE_NORMAL);
		}
	}

	/* Deliberately violate the readonly primitive double to catch rediscovery:
	 * production must consume the validated token, not read a new return target. */
	string_packet();
	string_change_return = true;
	steps[0] = (struct step){ KD_EXE_HOSTCALL, STRING_IP, 1, -8 };
	steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(active.continuation_ip == STRING_RETURN && stack[8] == 0xdead && !errors);
}
