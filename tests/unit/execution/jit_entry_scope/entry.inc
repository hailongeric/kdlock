/* Entry-scope fixture cases; shared stubs live in jit_entry_scope_fixture.c. */
static void check_pristine_refusal(void)
{
	struct kd_regs before;

	reset();
	before = active.regs;
	steps[0].reason = KD_EXE_ENTRY_REFUSED;
	CHECK(run() == KD_EXE_NO_RUN);
	CHECK(calls == 1 && !active.executed && !known_calls);
	CHECK(memcmp(&before, &active.regs, sizeof(before)) == 0);
	CHECK(warnings == 1 && !errors && entry->status_code == KD_EXE_NORMAL);
	for (int bad = 0; bad < 4; bad++) {
		reset();
		steps[0].reason = KD_EXE_ENTRY_REFUSED;
		if (bad == 0)
			steps[0].witness = 1;
		if (bad == 1)
			steps[0].sp_delta = 8;
		if (bad == 2)
			steps[0].ip = 0x1001;
		if (bad == 3)
			steps[0].reason = KD_EXE_INST_LIMIT;
		CHECK(run() == KD_EXE_RUN_ERROR);
		CHECK(calls == 1 && active.executed && errors == 1);
	}
}

static void check_local_continuation(void)
{
	for (int witness = 0; witness <= 1; witness++) {
		reset();
		steps[0] =
			(struct step){ KD_EXE_CALL_MISS, 0x2000, witness, -8 };
		steps[1] = (struct step){ KD_EXE_ENTRY_REFUSED, 0x1000, 0, 0 };
		CHECK(run() == KD_EXE_RUN_ERROR);
		CHECK(active.executed && calls == 2 && known_calls == 1 &&
		      errors == 1);
		reset();
		steps[0] =
			(struct step){ KD_EXE_CALL_MISS, 0x2000, witness, -8 };
		steps[1] =
			(struct step){ KD_EXE_CALL_MISS, 0x9000, witness, 0 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		CHECK(active.executed && calls == 2 && known_calls == 2 &&
		      !errors);
	}
}

static void remote(void)
{
	reset();
	memcpy(&parent, &active, sizeof(parent));
	active.regs.ip = 0x1005;
	active.outer_lock_addr = active.regs.di = 0x8100;
	active.outer_lock_index = 1;
	active.jit_lock_depth = active.held_lock_depth =
		active.outer_lock_depth = 2;
	active.jit_lock_addr[1] = 0x8100;
	active.jit_lock_kind[1] = KD_EXEC_LOCK_QUEUE_OWNER;
	active.resume_target = &parent;
	parent.regs = active.regs;
	parent.delegated_lock_addr = active.outer_lock_addr;
	parent.executed = true;
	parent.remote_result = KD_EXEC_REMOTE_WAITING;
	parent.control_call.phase = KD_CALL_ENTERED;
	parent.control_call.return_ip = active.regs.ip;
	parent.control_call.stack = active.regs.sp - 8;
}

static void check_remote_scope(void)
{
	struct kd_exec_frame before;

	remote();
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(active.executed && calls == 1 && !errors);
	remote();
	steps[0].reason = KD_EXE_ENTRY_REFUSED;
	CHECK(run() == KD_EXE_RUN_ERROR);
	CHECK(active.executed && calls == 1 && errors == 1);
	for (int bad = 0; bad < 14; bad++) {
		remote();
		switch (bad) {
		case 0:
			parent.executed = false;
			break;
		case 1:
			parent.entry_ip++;
			break;
		case 2:
			parent.gsbase++;
			break;
		case 3:
			parent.logical_task = &stranger;
			break;
		case 4:
			parent.control_call.phase = KD_CALL_PENDING;
			break;
		case 5:
			parent.remote_result = KD_EXEC_REMOTE_DONE;
			break;
		case 6:
			parent.control_call.return_ip++;
			break;
		case 7:
			parent.control_call.stack++;
			break;
		case 8:
			parent.delegated_lock_addr++;
			break;
		case 9:
			active.parent = &parent;
			active.resume_target = NULL;
			break;
		case 10:
			active.regs.sp++;
			break;
		case 11:
			parent.mutex_backend = true;
			break;
		case 12:
			parent.state = KD_EXEC_FRAME_ERROR;
			break;
		case 13:
			active.state = KD_EXEC_FRAME_ERROR;
			break;
		}
		memcpy(&before, &parent, sizeof(before));
		CHECK(run() == KD_EXE_NO_RUN);
		CHECK(!calls && !active.executed && errors == 1);
		CHECK(memcmp(&parent, &before, sizeof(parent)) == 0);
	}
}

static void check_registry_refusal(void)
{
	struct kd_exec_frame before;
	unsigned long stack_before[16];
	struct kd_exe_info table_before[KD_MAX_EXE];

	/* These are unstarted spin/mutex roots, not post-progress recovery. Check
	 * the full packet, virtual stack and owner ledger, not just executed=false. */
	for (int backend = 0; backend < 1; backend++) {
		for (int state = 0; state < 7; state++) {
			reset();
			active.mutex_backend = backend;
			entry->lock_kind = backend ? KD_EXE_LOCK_OWNED_MUTEX :
						     KD_EXE_LOCK_SPIN;
			memset(&active.regs, 0x51, sizeof(active.regs));
			active.regs.ip = active.entry_ip;
			active.regs.sp = (unsigned long)&stack[9];
			active.regs.di = active.outer_lock_addr;
			switch (state) {
			case 0:
				kd_exes = NULL;
				break;
			case 1:
				entry->status_code = KD_EXE_UNUSED;
				break;
			case 2:
				entry->status_code = KD_EXE_UNINIT;
				break;
			case 3:
				entry->status_code = KD_EXE_CALL_MISS;
				break;
			case 4:
				entry->status_code = KD_EXE_NATIVE_ONLY;
				break;
			case 5:
				entry->code_block = NULL;
				break;
			case 6:
				for (int i = 0; i < KD_MAX_EXE; i++) {
					entry_table[i].status_code =
						KD_EXE_UNINIT;
					entry_table[i].pid = 1;
				}
				break;
			}
			memcpy(&before, &active, sizeof(before));
			memcpy(stack_before, stack, sizeof(stack));
			memcpy(table_before, entry_table, sizeof(entry_table));
			CHECK(run() == KD_EXE_NO_RUN);
			CHECK(!calls && !known_calls && !errors &&
			      !active.executed);
			CHECK(memcmp(&before, &active, sizeof(active)) == 0);
			CHECK(memcmp(stack_before, stack, sizeof(stack)) == 0);
			CHECK(memcmp(table_before, entry_table,
				     sizeof(entry_table)) == 0);
		}
	}
}

/* Model the setup gap between execute_cs's lookup and dispatcher entry.
 * The pointer is stable, but publication/readiness can change during the gap.
 * Source frame leasing itself is exercised by test_source_lifetime. */
static void check_cached_entry(void)
{
	for (int backend = 0; backend < 1; backend++) {
		for (int change = -1; change < 9; change++) {
			struct kd_exe_info *cached;
			struct kd_exec_frame before;
			unsigned int acquires;

			reset();
			active.mutex_backend = backend;
			entry->lock_kind = backend ? KD_EXE_LOCK_OWNED_MUTEX : KD_EXE_LOCK_SPIN;
			CHECK(kd_exe_is_ready(0, active.entry_ip));
			registry_lookups = 0;
			cached = kd_exe_find_ready(0, active.entry_ip);
			CHECK(cached == entry && registry_lookups == 1);
			steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
			switch (change) {
			case 0: source_open = false; break; /* DRAINING before invalidation */
			case 1: kd_exe_publish_status(entry, KD_EXE_UNINIT); break;
			case 2: kd_exe_publish_status(entry, KD_EXE_CALL_MISS); break;
			case 3: kd_exe_publish_status(entry, KD_EXE_NATIVE_ONLY); break;
			case 4: entry->code_block = NULL; break;
			case 5: entry->pid = 1; break;
			case 6: entry->RIP += 8; break;
			case 7: entry->lock_kind = backend ? KD_EXE_LOCK_SPIN : KD_EXE_LOCK_OWNED_MUTEX; break;
			case 8: cached = NULL; break;
			}
			memcpy(&before, &active, sizeof(before));
			acquires = readiness_acquires;
			CHECK(kd_exe_on_call_hl_entry(cached, &active.regs,
				active.entry_ip, active.outer_lock_addr) ==
			      (change < 0 ? KD_EXE_RUN_TO_UNLOCK : KD_EXE_NO_RUN));
			CHECK(registry_lookups == 1); /* no second/third hash in dispatch */
			if (change < 0) {
				CHECK(calls == 1 && active.executed);
				CHECK(readiness_acquires > acquires);
			} else {
				CHECK(!calls && !known_calls && !active.executed);
				CHECK(!memcmp(&before, &active, sizeof(active)));
				if (change == 7)
					CHECK(entry->status_code == KD_EXE_NATIVE_ONLY);
			}
		}
	}
}

static void check_source_target_refusal(void)
{
	for (int error = 0; error < 2; error++) {
		reset();
		known_result = 0;
		source_error = error ? -ESTALE : 0;
		steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x2000, 1, -8 };
		CHECK(run() == (error ? KD_EXE_RUN_ERROR : KD_EXE_RUN_NATIVE));
		CHECK(calls == 1 && source_calls == 1 && active.executed);
		CHECK(active.regs.ip == 0x2000 &&
		      active.regs.sp == (unsigned long)&stack[8]);
		CHECK(entry->status_code ==
		      (error ? KD_EXE_NORMAL : KD_EXE_CALL_MISS));
		CHECK(!memcmp(&active.regs, &last_wrapper_output, sizeof(active.regs)));
		CHECK(stack[8] == 0x1005 && !service_calls[0] &&
		      !service_calls[1] && !service_calls[2]);
		CHECK(errors == error);
	}
}
