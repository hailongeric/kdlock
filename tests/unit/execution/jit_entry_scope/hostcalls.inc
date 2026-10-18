/* Entry-scope fixture cases; shared stubs live in jit_entry_scope_fixture.c. */
static void service_packet(void)
{
	reset();
	memset(&active.regs, 0x5A, sizeof(active.regs));
	active.regs.ip = active.entry_ip;
	active.regs.sp = (unsigned long)&stack[9];
	active.regs.di = active.outer_lock_addr;
}

/* Check the producer's real flags/address gates independently of the high-level
 * exit marker. Refused services must not consume CALL words or change GPRs. */
static void check_service_dispatch(void)
{
	const unsigned int required = KD_HOSTCALL_F_ATOMIC_SAFE |
		KD_HOSTCALL_F_NO_TASK_CONTEXT | KD_HOSTCALL_F_RETRY_SAFE;

	CHECK(ARRAY_SIZE(kd_hostcalls) == ARRAY_SIZE(service_calls) + 2);
	for (unsigned int i = 0; i < ARRAY_SIZE(service_calls); i++) {
		for (unsigned int flags = 0; flags <= required; flags++) {
			struct kd_regs expected;

			service_packet();
			active.regs.ip = kd_hostcalls[i].addr;
			kd_hostcalls[i].flags = flags;
			expected = active.regs;
			CHECK(kd_hostcall_dispatch(&active.regs) ==
			      (flags == required ? 0 : -EPERM));
			if (flags == required)
				expected.ax = service_values[i];
			CHECK(!memcmp(&active.regs, &expected, sizeof(expected)));
			for (unsigned int j = 0; j < ARRAY_SIZE(service_calls); j++)
				CHECK(service_calls[j] == (j == i && flags == required));
			if (i == 2 && flags == required)
				CHECK(scalar_argument == expected.di);
		}
	}
	for (unsigned int zero = 0; zero < 2; zero++) {
		struct kd_regs before;

		service_packet();
		for (unsigned int i = 0; i < ARRAY_SIZE(kd_hostcalls); i++)
			kd_hostcalls[i].addr = 0;
		active.regs.ip = zero ? 0 : 0xDEAD;
		before = active.regs;
		CHECK(kd_hostcall_dispatch(&active.regs) == -ENOENT);
		CHECK(!memcmp(&active.regs, &before, sizeof(before)));
		CHECK(!service_calls[0] && !service_calls[1] && !service_calls[2]);
	}
}

/* Distinguish the real adapter's register choice and width, independently of
 * the wrapper double. Preserve the entire software packet except return RAX. */
static void check_scalar_arguments(void)
{
	const unsigned long arguments[] = {
		0, 1, 0x7fffffffUL, 0xffffffffUL, 0x100000000UL,
		0x4000000080000001UL, 0x8000000000000000UL, ~0UL,
	};

	for (unsigned int i = 0; i < ARRAY_SIZE(arguments); i++) {
		struct kd_regs expected;

		service_packet();
		active.regs.ip = kd_hostcalls[2].addr;
		active.regs.di = arguments[i];
		active.regs.si = ~arguments[i];
		expected = active.regs;
		expected.ax = service_values[2];
		CHECK(kd_hostcall_dispatch(&active.regs) == 0);
		CHECK(scalar_argument == arguments[i]);
		CHECK(service_calls[2] == 1 && !service_calls[0] && !service_calls[1]);
		CHECK(!memcmp(&active.regs, &expected, sizeof(expected)));
		CHECK(stack[8] == 0x1005);
	}
}

/* Script service returns, not machine code. The actual high-level consumer must
 * reinitialize both wrapper words, preserve non-return GPRs and consume one CALL. */
static void check_service_returns(void)
{
	const unsigned int counts[] = { 1, KD_EXE_HL_MAX_HOSTCALLS - 1,
					KD_EXE_HL_MAX_HOSTCALLS };

	for (unsigned int n = 0; n < ARRAY_SIZE(counts); n++) {
		struct kd_regs expected;
		unsigned long before_stack[ARRAY_SIZE(stack)];
		unsigned int count = counts[n];

		service_packet();
		expected = active.regs;
		memcpy(before_stack, stack, sizeof(stack));
		for (unsigned int i = 0; i < count; i++)
			steps[i] = (struct step){ KD_EXE_HOSTCALL,
				kd_hostcalls[i % ARRAY_SIZE(service_calls)].addr, 1, -8 };
		steps[count] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		expected.ip = 0x9000;
		expected.sp -= 8;
		expected.ax = service_values[(count - 1) % ARRAY_SIZE(service_values)];
		CHECK(!memcmp(&active.regs, &expected, sizeof(expected)));
		CHECK(!memcmp(stack, before_stack, sizeof(stack)));
		CHECK(active.continuation_ip == stack[8] &&
		      active.continuation_sp == (unsigned long)&stack[9]);
		CHECK(active.executed && calls == (int)count + 1 && known_calls == 1);
		CHECK(kd_hostcall_exits == count && kd_hostcall_executed == count &&
		      kd_hostcall_resumed == count);
		for (unsigned int i = 0; i < ARRAY_SIZE(service_calls); i++)
			CHECK(service_calls[i] == count / ARRAY_SIZE(service_calls) +
			      (i < count % ARRAY_SIZE(service_calls)));
		CHECK(!errors && !source_calls && !kd_hostcall_failed &&
		      !kd_hostcall_rejected && !kd_hostcall_limit);
	}
}

static void check_service_errors(void)
{
	for (unsigned int bad = 0; bad < 6; bad++) {
		struct kd_regs expected;

		service_packet();
		if (bad >= 1 && bad <= 3)
			kd_hostcalls[0].flags &= ~(1U << (bad - 1));
		if (bad == 4)
			kd_hostcalls[0].invoke = failing_service;
		/* Keep entry admission valid; the bad continuation belongs to the
		 * wrapper's exit packet, after a service request has been produced. */
		steps[0] = (struct step){ KD_EXE_HOSTCALL,
			bad ? kd_hostcalls[0].addr : 0xDEAD, 1,
			bad == 5 ? -(long)active.regs.sp : -8 };
		CHECK(run() == KD_EXE_RUN_ERROR);
		expected = last_wrapper_output;
		if (bad == 5)
			expected.ax = service_values[0];
		CHECK(!memcmp(&active.regs, &expected, sizeof(expected)));
		/* Invoke/return failure after entry never authorizes unstarted replay. */
		CHECK(active.executed && calls == 1 && errors == 1);
		CHECK(kd_hostcall_exits == 1 && !kd_hostcall_resumed && !kd_hostcall_limit);
		CHECK(kd_hostcall_rejected == (bad < 4) &&
		      kd_hostcall_failed == (bad >= 4));
		CHECK(kd_hostcall_executed == (bad == 5) && service_calls[0] == (bad == 5));
		CHECK(!service_calls[1] && !service_calls[2] &&
		      failed_service_calls == (bad == 4));
		CHECK(!source_calls && !known_calls && entry->status_code == KD_EXE_NORMAL);
		CHECK(strstr(last_error, bad == 5 ? "HOSTCALL_CONTINUATION_FAILED" :
							 "HOSTCALL_FAILED"));
	}
	/* A CALL_MISS for an allowlisted address is still an ordinary native
	 * suffix. Only the explicit HOSTCALL exit requests a service and return. */
	service_packet();
	known_result = 0;
	steps[0] = (struct step){ KD_EXE_CALL_MISS, kd_hostcalls[0].addr, 1, -8 };
	CHECK(run() == KD_EXE_RUN_NATIVE);
	CHECK(calls == 1 && source_calls == 1 && !kd_hostcall_exits &&
	      !service_calls[0] && !service_calls[1] && !service_calls[2]);
	CHECK(!memcmp(&active.regs, &last_wrapper_output, sizeof(active.regs)));
}

/* Known lock controls and services share the invocation budget. Mixing them
 * must stop before the excess operation, with its CALL packet still intact. */
static void check_shared_budget(void)
{
	const unsigned int prefixes[] = { 0, 1, KD_EXE_HL_MAX_CONTINUATIONS };

	/* A remote child shares the image but not the parent's active CALL packet.
	 * Quota handling must leave that waiting parent untouched for native relay. */
	for (unsigned int n = 0; n < 2 * ARRAY_SIZE(prefixes); n++) {
		for (unsigned int service = 0; service < 2; service++) {
			bool child = n >= ARRAY_SIZE(prefixes);
			unsigned int known = prefixes[n % ARRAY_SIZE(prefixes)];
			unsigned int accepted = KD_EXE_HL_MAX_CONTINUATIONS;
			unsigned int services = accepted - known;
			struct kd_exec_frame saved_parent;

			if (child)
				remote();
			else
				service_packet();
			memcpy(&saved_parent, &parent, sizeof(saved_parent));
			for (unsigned int i = 0; i < accepted; i++)
				steps[i] = (struct step){ i < known ? KD_EXE_CALL_MISS :
					KD_EXE_HOSTCALL, i < known ? 0x2000 : kd_hostcalls[0].addr,
					1, -8 };
			steps[accepted] = (struct step){ service ? KD_EXE_HOSTCALL :
				KD_EXE_CALL_MISS, service ? kd_hostcalls[0].addr : 0x2000,
				1, -8 };
			CHECK(run() == KD_EXE_RUN_NATIVE);
			CHECK(calls == (int)accepted + 1 && known_calls == (int)known);
			CHECK(service_calls[0] == services && !service_calls[1] && !service_calls[2]);
			CHECK(kd_hostcall_exits == services + service &&
			      kd_hostcall_executed == services && kd_hostcall_resumed == services);
			CHECK(kd_hostcall_limit == service && !kd_hostcall_rejected &&
			      !kd_hostcall_failed);
			CHECK(!memcmp(&active.regs, &last_wrapper_output, sizeof(active.regs)));
			CHECK(active.regs.sp == (unsigned long)&stack[8] && stack[8] == 0x1005);
			CHECK(active.executed && !errors && warnings == 1 && source_calls == 2);
			CHECK(source_targets[0] == active.regs.ip && source_targets[1] == stack[8]);
			CHECK(active.continuation_ip == active.regs.ip &&
			      active.continuation_sp == active.regs.sp &&
			      active.control_call.phase == KD_CALL_NONE &&
			      active.state == KD_EXEC_FRAME_RESUME);
			CHECK(entry->status_code == KD_EXE_NORMAL && !entry->tgt_addr);
			CHECK(active.resume_target == (child ? &parent : NULL));
			if (child)
				CHECK(!memcmp(&parent, &saved_parent, sizeof(parent)));
		}
	}
}

/* Validate the exact pre-dispatch boundary independently of counter setup.
 * Corrupted packets must leave every frame/stack byte untouched. This is not
 * evidence for concurrent stack privacy or live hardware flags preservation. */
static void check_quota_packets(void)
{
	for (int backend = 0; backend < 2; backend++) {
		for (int service = 0; service < 2; service++) {
			for (int bad = 0; bad < 23; bad++) {
				struct kd_exec_frame before;
				struct kd_exe_info registered;
				unsigned long saved_stack[ARRAY_SIZE(stack)];
				int ret;

				service_packet();
				active.mutex_backend = backend;
				active.executed = true;
				active.control_call.phase = KD_CALL_COMPLETE;
				active.regs.ip = kd_hostcalls[0].addr;
				active.regs.sp = (unsigned long)&stack[8];
				switch (bad) {
				case 1:
					active.regs.ip = 0;
					break;
				case 2:
					active.regs.sp = 0;
					break;
				case 3:
					active.executed = false;
					break;
				case 4:
					active.logical_task = current;
					break;
				case 5:
					active.logical_task = NULL;
					break;
				case 6:
					active.state = KD_EXEC_FRAME_ERROR;
					break;
				case 7:
					active.control_call.phase = KD_CALL_ENTERED;
					break;
				case 8:
					active.control_call.phase = KD_CALL_PENDING;
					break;
				case 9:
					active.remote_result = KD_EXEC_REMOTE_WAITING;
					break;
				case 10:
					active.remote_request = (void *)1;
					break;
				case 11:
					active.native_request = (void *)1;
					break;
				case 12:
					waiter.stack = NULL;
					break;
				case 13:
					waiter.stack = (void *)(~0UL - THREAD_SIZE + 1);
					break;
				case 14:
					active.regs.sp = (unsigned long)stack - 1;
					break;
				case 15:
					active.regs.sp = (unsigned long)stack + sizeof(stack) - 7;
					break;
				case 16:
					stack[8] = 0;
					break;
				case 17:
					stack_error = 1;
					break;
				case 18:
				case 19:
					source_error = -ESTALE;
					source_fail_at = bad - 17;
					break;
				case 20:
					kd_hostcalls[0].addr = 0;
					break;
				case 21:
					kd_hostcalls[0].flags = 0;
					break;
				case 22:
					active.outer_unlock_seen = true;
					active.jit_lock_released[0] = true;
					break;
				}
				memcpy(&before, &active, sizeof(before));
				memcpy(&registered, entry, sizeof(registered));
				memcpy(saved_stack, stack, sizeof(stack));
				ret = kd_jit_call_limit_native(&active, &active.regs, service);
				if (!bad || (!service && (bad == 20 || bad == 21))) {
					CHECK(ret == 0 && source_calls == 2 && stack_reads == 1);
					before.control_call.phase = KD_CALL_NONE;
					before.continuation_ip = before.regs.ip;
					before.continuation_sp = before.regs.sp;
					before.role = KD_ROLE_COMBINER;
					before.state = KD_EXEC_FRAME_RESUME;
				} else {
					CHECK(ret < 0 && !warnings);
					if (bad >= 12 && bad <= 15)
						CHECK(!stack_reads && !source_calls);
					if (bad == 18 || bad == 19)
						CHECK(source_calls == source_fail_at);
				}
				CHECK(!memcmp(&before, &active, sizeof(active)));
				CHECK(!memcmp(saved_stack, stack, sizeof(stack)));
				CHECK(!memcmp(&registered, entry, sizeof(registered)));
				CHECK(!service_calls[0] && !service_calls[1] &&
				      !service_calls[2] && !known_calls && !calls);
			}
		}
	}
	/* Released A with retained B and a remote child both keep their ledger.
	 * Parent completion/unlock routing remains the backend's existing duty. */
	for (int scope = 0; scope < 3; scope++) {
		struct kd_exec_frame expected;

		remote();
		active.executed = true;
		active.regs.ip = 0x2000;
		active.regs.sp = (unsigned long)&stack[8];
		if (scope) {
			active.resume_target = NULL;
			active.outer_lock_addr = 0x8000;
			active.outer_lock_index = 0;
			active.outer_unlock_seen = true;
			active.jit_lock_released[0] = true;
			active.mutex_backend = scope == 2;
		}
		memcpy(&expected, &active, sizeof(expected));
		expected.continuation_ip = active.regs.ip;
		expected.continuation_sp = active.regs.sp;
		expected.role = KD_ROLE_COMBINER;
		expected.state = KD_EXEC_FRAME_RESUME;
		CHECK(kd_jit_call_limit_native(&active, &active.regs, false) == 0);
		CHECK(!memcmp(&expected, &active, sizeof(active)));
		CHECK(stack[8] == 0x1005 && source_calls == 2);
	}
}

/* Re-run the same scripted packets with timing off/on. The complete frame,
 * table entry and stack must agree, including refusal, progressed error and
 * native decisions. These are software-boundary checks, not hardware flags. */
