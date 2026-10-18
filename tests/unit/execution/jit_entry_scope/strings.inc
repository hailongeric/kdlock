/* Helper arguments are the original native C caller's responsibility. This
 * fixture checks KD scope, original arguments/result, pending CALL identity,
 * quotas and single consumption, without substituting helper-specific checks. */
static void string_packet(void)
{
	struct kd_jit_batch_call unused;

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
	memset(string_left, 'a', sizeof(string_left));
	memset(string_right, 'b', sizeof(string_right));
	string_left[sizeof(string_left) - 1] = 0;
	string_right[sizeof(string_right) - 1] = 0;
}

static void check_string_services(void)
{
	/* Valid original strings exceed the retired 256-byte implementation limit.
	 * Injected data-read faults prove KD performs no scanner reads. The native
	 * helper double observes the original arguments and defines exact EAX. */
	for (int result = -1; result <= 1; result++) {
		string_packet();
		string_result = result;
		string_read_error = 1;
		steps[0] = (struct step){ KD_EXE_HOSTCALL, STRING_IP, 1, -8 };
		steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		CHECK(string_calls == 1 && active.regs.ax == (unsigned int)result);
		CHECK(active.regs.si == STRING_RIGHT && stack[8] == STRING_RETURN);
		CHECK(active.continuation_ip == STRING_RETURN &&
		      active.continuation_sp == (unsigned long)&stack[9]);
		CHECK(!errors && kd_hostcall_executed == 1 && kd_hostcall_resumed == 1);
		CHECK(!string_read_extent && stack_reads == 1);
		CHECK(source_calls == 1 && source_targets[0] == STRING_RETURN);
	}
	/* Generic scalar dispatch cannot bypass the pending CALL bookkeeping. */
	string_packet();
	active.regs.ip = STRING_IP;
	CHECK(kd_hostcall_dispatch(&active.regs) == -EPERM && !string_calls);

	for (unsigned int bad = 0; bad < 22; bad++) {
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
		case 14: active.regs.sp = (unsigned long)&stack[16]; break;
		case 15: stack_error = 1; break;
		case 16: active.jit_lock_depth = 0; break;
		case 17: active.outer_unlock_seen = true; break;
		case 18: active.resume_target = &parent; break;
		case 19: source_error = -ESTALE; break;
		case 20: active.regs.ip++; break;
		case 21: kd_hostcalls[3].flags = 0; break;
		}
		before = active.regs;
		CHECK(kd_jit_string_prepare(entry, &active, &active.regs, &return_ip) < 0);
		CHECK(!memcmp(&before, &active.regs, sizeof(before)) && !string_calls);
		CHECK(entry->status_code == KD_EXE_NORMAL && !string_read_extent);
	}

	/* A malformed continuation fails before helper effects, without turning a
	 * protocol error into a replayable native entry or a completed JIT body. */
	string_packet();
	stack_error = 1;
	steps[0] = (struct step){ KD_EXE_HOSTCALL, STRING_IP, 1, -8 };
	CHECK(run() == KD_EXE_RUN_ERROR && !string_calls);
	CHECK(!memcmp(&last_wrapper_output, &active.regs, sizeof(active.regs)));
	CHECK(entry->status_code == KD_EXE_NORMAL && stack[8] == STRING_RETURN);
	CHECK(!kd_hostcall_executed && kd_hostcall_failed == 1);

	/* Keep the old shared scalar/control16 limit; comparisons add only128. */
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

	/* Effects cannot make a newly read stack word authoritative. */
	string_packet();
	string_change_return = true;
	steps[0] = (struct step){ KD_EXE_HOSTCALL, STRING_IP, 1, -8 };
	steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(active.continuation_ip == STRING_RETURN && stack[8] == 0xdead && !errors);
}
