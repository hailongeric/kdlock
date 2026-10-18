/* Entry-scope fixture cases; shared stubs live in jit_entry_scope_fixture.c. */
static void reset(void)
{
	static struct kd_hostcall_desc original[ARRAY_SIZE(kd_hostcalls)];
	static bool captured;

	kd_jit_timing = false;
	complex_preparations = 0;
	kd_jit_timing_reset();
	timing_clock_active = false;
	timing_clock = timing_reads = 0;
	/* Restore actual manifest entries after deliberate flags/target failures. */
	if (!captured) {
		memcpy(original, kd_hostcalls, sizeof(original));
		captured = true;
	}
	memcpy(kd_hostcalls, original, sizeof(original));
	for (unsigned int i = 0; i < ARRAY_SIZE(kd_hostcalls); i++)
		kd_hostcalls[i].addr = 0x3000 + 8 * i;
	kd_hostcalls[3].addr = STRING_IP;
	kd_hostcalls[4].addr = PAD_IP;
	string_calls = 0;
	string_result = string_read_error = 0;
	string_change_return = false;
	string_wrapper = false;
	pad_calls = string_read_extent = 0;
	pad_result = 15;
	string_readable = STRING_BYTES;
	pad_truncates = false;
	memset(service_calls, 0, sizeof(service_calls));
	scalar_argument = 0;
	memset(last_error, 0, sizeof(last_error));
	failed_service_calls = 0;
	kd_hostcall_exits = kd_hostcall_executed = kd_hostcall_resumed = 0;
	kd_hostcall_limit = kd_hostcall_rejected = kd_hostcall_failed = 0;
	/* Whole-object checks below include padding around narrow frame fields.
	 * Zero it deterministically and preserve it in snapshots with memcpy;
	 * C structure assignment is allowed to leave padding unspecified. */
	memset(&active, 0, sizeof(active));
	active.complex_ready = true;
	active.entry_ip = 0x1000;
	active.outer_lock_addr = 0x8000;
#ifdef KD_BENCH_COMPLETION_FIXTURE
	kd_bench_lock_addr = active.outer_lock_addr;
	kd_bench_complete_probe = true;
	kd_bench_bodies = kd_bench_completions = 0;
#endif
	active.gsbase = 0xFEED;
	active.logical_task = &waiter;
	active.jit_lock_addr[0] = 0x8000;
	active.jit_lock_kind[0] = KD_EXEC_LOCK_QUEUE_OWNER;
	active.jit_lock_depth = 1;
	active.held_lock_depth = 1;
	active.outer_lock_depth = 1;
	active.outer_lock_index = 0;
	active.state = KD_EXEC_FRAME_RUNNING;
	active.regs.ip = active.entry_ip;
	active.regs.sp = (unsigned long)&stack[9];
	active.regs.di = active.outer_lock_addr;
	memset(stack, 0, sizeof(stack));
	stack[8] = 0x1005;
	waiter.stack = stack;
	memset(steps, 0, sizeof(steps));
	kd_exes = entry_table;
	memset(entry_table, 0, sizeof(entry_table));
	for (int i = 0; i < KD_MAX_EXE; i++)
		entry_table[i].status_code = KD_EXE_UNUSED;
	entry = kd_get_exe(0, active.entry_ip);
	memset(entry, 0, sizeof(*entry));
	entry->RIP = active.entry_ip;
	entry->lock_kind = KD_EXE_LOCK_SPIN;
	entry->code_block = translated;
	entry->status_code = KD_EXE_NORMAL;
	source_open = true;
	registry_lookups = readiness_acquires = 0;
	calls = known_calls = errors = warnings =
		kd_jit_hl_fault_after_known_call = 0;
	known_result = 1;
	source_error = source_calls = source_fail_at = stack_error = stack_reads = 0;
	memset(source_targets, 0, sizeof(source_targets));
	kd_native_escape_count = 0;
	kd_address_guard_count = 0;
	memset(escape_text, 0, sizeof(escape_text));
	escape_text[0] = 0x0f;
	escape_text[1] = 0x31;
}

static int run(void)
{
	struct kd_exe_info *exe = kd_exe_find_ready(0, active.entry_ip);

	return kd_exe_on_call_hl_entry(exe, kd_exec_frame_regs(&active), active.entry_ip,
				       active.outer_lock_addr);
}
