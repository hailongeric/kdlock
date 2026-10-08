/* Entry-scope fixture cases; shared stubs live in jit_entry_scope_fixture.c. */
static void check_timing_boundaries(void)
{
	const unsigned int wrappers[] = { 3, 1, 1, 1, 1, 1, 17, 1, 0, 1, 1 };
	const unsigned int services[] = { 2, 0, 0, 1, 0, 0, 16, 0, 0, 0, 1 };
	const unsigned int controls[] = { 1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0 };
	const int results[] = { KD_EXE_RUN_TO_UNLOCK, KD_EXE_NO_RUN,
		KD_EXE_RUN_ERROR, KD_EXE_RUN_ERROR, KD_EXE_RUN_NATIVE,
		KD_EXE_RUN_NATIVE, KD_EXE_RUN_NATIVE, KD_EXE_RUN_ERROR,
		KD_EXE_NO_RUN, KD_EXE_RUN_ERROR, KD_EXE_RUN_ERROR };

	for (unsigned int scenario = 0; scenario < ARRAY_SIZE(results); scenario++) {
		struct kd_exec_frame expected;
		struct kd_exe_info registered;
		unsigned long saved_stack[ARRAY_SIZE(stack)];

		for (int enabled = 0; enabled < 2; enabled++) {
			unsigned int inner = wrappers[scenario] + services[scenario] +
				controls[scenario];
			unsigned int samples[KD_JIT_TIME_COUNT] = {
				scenario != 8, wrappers[scenario], services[scenario],
				controls[scenario],
			};

			service_packet();
			timing_clock_active = true;
			kd_jit_timing = enabled;
			steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x2000, 1, -8 };
			switch (scenario) {
			case 0:
				steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
				steps[1] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[2].addr, 1, -8 };
				steps[2] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
				break;
			case 1:
			case 2:
				steps[0] = (struct step){ KD_EXE_ENTRY_REFUSED, 0, scenario == 2, 0 };
				break;
			case 3:
				kd_hostcalls[0].invoke = failing_service;
				steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
				break;
			case 4:
				known_result = KD_EXE_KNOWN_NATIVE;
				break;
			case 5:
				known_result = 0;
				break;
			case 6:
				for (int i = 0; i <= KD_EXE_HL_MAX_HOSTCALLS; i++)
					steps[i] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
				break;
			case 7:
				kd_jit_hl_fault_after_known_call = 3;
				break;
			case 8:
				entry->status_code = KD_EXE_UNINIT;
				break;
			case 9:
				known_result = -EIO;
				break;
			case 10:
				steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1,
					-(long)active.regs.sp };
				break;
			}
			CHECK(run() == results[scenario]);
			CHECK(timing_reads == (enabled && scenario != 8 ? 2 * (inner + 1) : 0));
			for (int phase = 0; phase < KD_JIT_TIME_COUNT; phase++) {
				u64 ns = samples[phase] * 10;

				if (phase == KD_JIT_TIME_DISPATCH && scenario != 8)
					ns = (2 * inner + 1) * 10;
				CHECK(kd_jit_times[phase].samples == enabled * samples[phase]);
				CHECK(kd_jit_times[phase].ns == (s64)(enabled * ns));
				CHECK(!kd_jit_times[phase].invalid);
			}
			if (!enabled) {
				memcpy(&expected, &active, sizeof(expected));
				memcpy(&registered, entry, sizeof(registered));
				memcpy(saved_stack, stack, sizeof(stack));
			} else {
				CHECK(!memcmp(&active, &expected, sizeof(active)));
				CHECK(!memcmp(entry, &registered, sizeof(registered)));
				CHECK(!memcmp(stack, saved_stack, sizeof(stack)));
			}
		}
	}
	/* Invalid clocks and saturated counters poison only telemetry, never the
	 * execution packet or later valid counter updates. Start at zero is valid. */
	for (int bad = 0; bad < 4; bad++) {
		struct kd_exec_frame before;
		struct kd_jit_timing_stat *stat = &kd_jit_times[KD_JIT_TIME_WRAPPER];

		reset();
		memcpy(&before, &active, sizeof(before));
		kd_jit_timing = timing_clock_active = true;
		if (bad == 1)
			stat->samples = S64_MAX;
		if (bad == 2)
			stat->ns = S64_MAX;
		timing_clock = bad == 2 ? 1 : 0;
		kd_jit_timing_end(KD_JIT_TIME_WRAPPER, bad == 0 ? 1 : 0);
		CHECK(stat->invalid == (bad != 3));
		CHECK(stat->samples == (bad == 1 ? S64_MAX : 1));
		CHECK(stat->ns == (bad == 2 ? S64_MAX : 0));
		CHECK(!memcmp(&active, &before, sizeof(active)));
	}
	reset();
}

/* Verify the actual counter API separately from queue/clock substitutes in
 * the producer fixtures: saved endpoints exclude body time, reuse counts once,
 * and disabled measurement changes neither clocks nor execution packets. */
static void check_queue_timings(void)
{
	for (int mutex = 0; mutex < 2; mutex++) {
		for (int enabled = 0; enabled < 2; enabled++) {
			u64 queued_at;
			u64 endpoint;
			int phase = mutex ? KD_JIT_TIME_MUTEX_QUEUE : KD_JIT_TIME_SPIN_QUEUE;
			struct kd_exec_frame before;

			reset();
			memcpy(&before, &active, sizeof(before));
			kd_jit_timing = enabled;
			timing_clock_active = true;
			timing_clock = 100;
			for (int request = 1; request <= 2; request++) {
				queued_at = kd_exe_queue_timing_start();
				endpoint = kd_exe_queue_timing_start();
				timing_clock += 1000; /* Substituted body elapsed time. */
				kd_exe_queue_timing_end(mutex, &queued_at, endpoint);
				CHECK(queued_at == 0);
				kd_exe_queue_timing_end(mutex, &queued_at, endpoint);
				CHECK(timing_reads == (unsigned int)(enabled * request * 2));
				for (int i = 0; i < KD_JIT_TIME_COUNT; i++) {
					int count = enabled && i == phase ? request : 0;

					CHECK(kd_jit_times[i].samples == count);
					CHECK(kd_jit_times[i].ns == count * 10);
					CHECK(!kd_jit_times[i].invalid);
				}
				CHECK(!memcmp(&active, &before, sizeof(active)));
			}
		}
	}
	reset();
}

/* The wider native envelope must contain the inner wait without adding their
 * times together. Clock/backend selection never changes the saved packet. */
static void check_native_handoff_timings(void)
{
	for (int mutex = 0; mutex < 2; mutex++) {
		for (int enabled = 0; enabled < 2; enabled++) {
			struct kd_exec_frame before;
			u64 handoff, wait;
			int outer = mutex ? KD_JIT_TIME_NATIVE_MUTEX_HANDOFF :
					    KD_JIT_TIME_NATIVE_SPIN_HANDOFF;
			int inner = mutex ? KD_JIT_TIME_NATIVE_MUTEX_WAIT :
					    KD_JIT_TIME_NATIVE_SPIN_WAIT;

			reset();
			memcpy(&before, &active, sizeof(before));
			kd_jit_timing = enabled;
			timing_clock_active = true;
			handoff = kd_exe_native_timing_start();
			wait = kd_exe_native_timing_start();
			kd_exe_native_timing_end(mutex, wait);
			kd_exe_native_handoff_timing_end(mutex, handoff);
			CHECK(timing_reads == (unsigned int)(enabled * 4));
			for (int i = 0; i < KD_JIT_TIME_COUNT; i++) {
				int count = enabled && (i == outer || i == inner);

				CHECK(kd_jit_times[i].samples == count);
				CHECK(kd_jit_times[i].ns == count * (i == outer ? 30 : 10));
				CHECK(!kd_jit_times[i].invalid);
			}
			CHECK(!memcmp(&active, &before, sizeof(active)));
		}
	}
	reset();
}
