/* SPDX-License-Identifier: GPL-2.0-only */
/* ABI2 setup/phase control reuses run_worker and every actual syscall body. */
struct jit_input {
	uint64_t abi, contract_flags;
	struct kd_mmap_jit_config config;
};
struct jit_round {
	struct worker *workers;
	uint64_t count, created, iterations, milliseconds, start, end, completed, errors;
	uint64_t arena_reservations;
	size_t arena_length;
	unsigned char *arena;
	long page;
	const char *setup_error;
	int setup_errno, cleanup_errno;
	bool passed;
};
struct jit_client {
	struct control control;
	const char *config_path;
	uint64_t config_bytes, phase_ms, rounds, completed_rounds;
	void *input_bytes;
	struct jit_input input;
	struct kd_mmap_jit_status profile;
	bool all_rounds_pass;
	int phase_errno, leave_errno;
	uint64_t leave_attempts;
	sigset_t phase_signals;
};

static bool jit_requested(int argc, char **argv)
{
	int index;
	for (index = 1; index < argc; ++index)
		if (!strcmp(argv[index], "--jit-config"))
			return true;
	return false;
}

static void print_jit_status(const struct kd_mmap_jit_status *status)
{
	printf("{\"native\":");
	print_gate_status(&status->native);
#define JIT_FIELD(field) printf(",\"" #field "\":%" PRIu64, (uint64_t)status->field)
	JIT_FIELD(state); JIT_FIELD(roles); JIT_FIELD(last_error); JIT_FIELD(setup_error);
	JIT_FIELD(killable_source_calls); JIT_FIELD(source_closing); JIT_FIELD(owner_left);
	JIT_FIELD(source_identity); JIT_FIELD(runtime_identity); JIT_FIELD(storage_identity);
	JIT_FIELD(origin_gs); JIT_FIELD(event_capacity); JIT_FIELD(event_count);
	JIT_FIELD(event_overflow); JIT_FIELD(event_readers); JIT_FIELD(source_regions); JIT_FIELD(source_bytes);
#undef JIT_FIELD
	putchar('}');
}

static bool jit_query(struct jit_client *client)
{
	struct kd_mmap_jit_request request = { .abi = KD_MMAP_JIT_ABI };
	if (ioctl(client->control.fd, KD_MMAP_API_QUERY_JIT, &request)) {
		client->control.query_errno = errno;
		client->control.cleanup_required = true;
		return false;
	}
	if (request.abi != KD_MMAP_JIT_ABI || request.status.state > KD_MMAP_JIT_RETIRED) {
		client->control.query_errno = EPROTO;
		client->control.cleanup_required = true;
		return false;
	}
	client->control.query_errno = 0;
	client->profile = request.status;
	client->control.final = request.status.native;
	client->control.cleanup_required = request.status.roles != 0 ||
		request.status.native.cleanup_required != 0;
	return true;
}

static void jit_phase_prefix(struct jit_client *client, const char *phase,
		uint64_t round, bool next)
{
	printf("{\"schema\":2,\"phase\":\"%s\",\"pid\":%ld,\"tid\":%ld,"
		"\"round\":%" PRIu64 ",\"requested_rounds\":%" PRIu64 ",\"completed_rounds\":%" PRIu64 ","
		"\"phase_timeout_ms\":%" PRIu64 ",\"next_round_allowed\":%s,"
		"\"cleanup_required\":%s,\"cleanup_failed\":%s,\"profile\":",
		phase, (long)getpid(), (long)syscall(SYS_gettid), round, client->rounds,
		client->completed_rounds, client->phase_ms, next ? "true" : "false",
		client->control.cleanup_required ? "true" : "false",
		client->control.cleanup_failed ? "true" : "false");
	print_jit_status(&client->profile);
}

static void jit_preserve(struct jit_client *client, const char *stage, int error)
{
	client->control.cleanup_failed = true;
	jit_phase_prefix(client, "jit_cleanup_required", client->completed_rounds, false);
	printf(",\"stage\":\"%s\",\"errno\":%d,\"retry_signal\":\"SIGUSR1\"}\n", stage, error);
	fflush(stdout);
	/* An explicit signal authorizes one metadata/cleanup retry on this same
	 * original owner. It never replays a completed or failed syscall round.
	 */
	while (!retry_end)
		sigsuspend(&client->control.wait_mask);
	retry_end = 0;
}

static bool jit_signals(struct jit_client *client)
{
	int result;
	if (!retry_signal(&client->control))
		return false;
	sigemptyset(&client->phase_signals);
	sigaddset(&client->phase_signals, SIGUSR1);
	sigaddset(&client->phase_signals, SIGUSR2);
	result = pthread_sigmask(SIG_BLOCK, &client->phase_signals, NULL);
	if (result) {
		errno = result;
		return false;
	}
	/* In preservation waits, only SIGUSR1 is unblocked for its existing handler.
	 * Children inherit both blocked signals; phase controls never cancel MM work.
	 */
	sigaddset(&client->control.wait_mask, SIGUSR2);
	return true;
}

static bool jit_clear_phase_signals(struct jit_client *client)
{
	struct timespec zero = {};
	unsigned int index;
	retry_end = 0;
	/* Standard signals coalesce. Bound the discard pass rather than consuming
	 * an unbounded stream. No signal queued before a marker can advance it.
	 */
	for (index = 0; index < 3; ++index) {
		if (sigtimedwait(&client->phase_signals, NULL, &zero) < 0) {
			if (errno == EAGAIN)
				return true;
			return false;
		}
	}
	errno = EBUSY;
	return false;
}

static int jit_timed_signal(struct jit_client *client)
{
	uint64_t start, end, value;
	if (!now_ns(&start))
		return -1;
	if (client->phase_ms > (UINT64_MAX - start) / UINT64_C(1000000)) {
		errno = EOVERFLOW;
		return -1;
	}
	end = start + client->phase_ms * UINT64_C(1000000);
	for (;;) {
		struct timespec remaining;
		int result;
		if (!now_ns(&value))
			return -1;
		if (value >= end) {
			errno = ETIMEDOUT;
			return -1;
		}
		remaining.tv_sec = (end - value) / UINT64_C(1000000000);
		remaining.tv_nsec = (end - value) % UINT64_C(1000000000);
		result = sigtimedwait(&client->phase_signals, NULL, &remaining);
		if (result >= 0)
			return result;
		if (errno == EAGAIN)
			errno = ETIMEDOUT;
		if (errno != EINTR)
			return -1;
	}
}

static bool same_input(const struct stat *before, const struct stat *after)
{
	return before->st_dev == after->st_dev && before->st_ino == after->st_ino &&
		before->st_mode == after->st_mode && before->st_size == after->st_size &&
		before->st_mtim.tv_sec == after->st_mtim.tv_sec && before->st_mtim.tv_nsec == after->st_mtim.tv_nsec &&
		before->st_ctim.tv_sec == after->st_ctim.tv_sec && before->st_ctim.tv_nsec == after->st_ctim.tv_nsec;
}

static bool jit_read_input(struct jit_client *client)
{
	struct stat before, after;
	struct jit_input *input;
	size_t region_bytes, total, done = 0;
	int fd, saved;
	_Static_assert(sizeof(size_t) == sizeof(uint64_t), "ABI2 x86_64 sizes");
	_Static_assert(sizeof(struct jit_input) == 34 * sizeof(uint64_t), "ABI2 input layout");
	_Static_assert(sizeof(struct kd_mmap_jit_request) == 82 * sizeof(uint64_t), "ABI2 ioctl layout");
	if (client->config_bytes < sizeof(*input)) {
		errno = EINVAL;
		return false;
	}
	fd = open(client->config_path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		return false;
	if (fstat(fd, &before)) {
		saved = errno;
		close(fd); errno = saved;
		return false;
	}
	if (!S_ISREG(before.st_mode) || before.st_size < 0 ||
		(uint64_t)before.st_size != client->config_bytes) {
		saved = EINVAL;
		close(fd); errno = saved;
		return false;
	}
	client->input_bytes = malloc(client->config_bytes);
	if (!client->input_bytes) {
		saved = errno; close(fd); errno = saved;
		return false;
	}
	while (done < client->config_bytes) {
		size_t wanted = client->config_bytes - done;
		ssize_t amount;
		if (wanted > SSIZE_MAX)
			wanted = SSIZE_MAX;
		amount = read(fd, (char *)client->input_bytes + done, wanted);
		if (amount < 0 && errno == EINTR)
			continue;
		if (amount <= 0) {
			saved = amount < 0 ? errno : EIO;
			close(fd); errno = saved;
			return false;
		}
		done += amount;
	}
	if (fstat(fd, &after)) {
		saved = errno;
		close(fd); errno = saved;
		return false;
	}
	if (!same_input(&before, &after)) {
		saved = ESTALE;
		close(fd); errno = saved;
		return false;
	}
	if (close(fd))
		return false;
	input = client->input_bytes;
	if (input->abi != KD_MMAP_JIT_ABI || input->contract_flags != KD_MMAP_JIT_CONTRACTS ||
				input->config.source_regions || input->config.source_version ||
				!input->config.source_region_count || input->config.source_region_count > UINT_MAX ||
				!input->config.source_version_bytes || !input->config.native_capacity ||
				input->config.native_capacity > UINT_MAX ||
				input->config.source_region_count > (SIZE_MAX - sizeof(*input)) / sizeof(struct kd_mmap_jit_region)) {
		errno = EINVAL;
		return false;
	}
	region_bytes = input->config.source_region_count * sizeof(struct kd_mmap_jit_region);
	total = sizeof(*input) + region_bytes;
	if (input->config.source_version_bytes > SIZE_MAX - total ||
				total + input->config.source_version_bytes != client->config_bytes) {
		errno = EINVAL;
		return false;
	}
	client->input = *input;
	client->input.config.source_regions = (uintptr_t)((char *)client->input_bytes + sizeof(*input));
	client->input.config.source_version = (uintptr_t)((char *)client->input_bytes + total);
	client->control.capacity = input->config.native_capacity;
	return true;
}

static bool jit_start_client(struct jit_client *client)
{
	struct kd_mmap_jit_request request = { .abi = KD_MMAP_JIT_ABI,
		.contract_flags = client->input.contract_flags, .config = client->input.config };
	client->control.fd = open(client->control.path, O_RDWR | O_CLOEXEC);
	if (client->control.fd < 0) {
		client->control.open_errno = errno;
		return false;
	}
	if (ioctl(client->control.fd, KD_MMAP_API_START_JIT, &request)) {
		client->control.start_errno = errno;
		jit_query(client);
		return false;
	}
	client->profile = request.status;
	client->control.final = request.status.native;
	client->control.cleanup_required = true;
	client->control.start = request.status.native;
	if (request.abi != KD_MMAP_JIT_ABI || request.status.state != KD_MMAP_JIT_SELECTED ||
				request.status.roles != (KD_MMAP_JIT_ROLE_NATIVE | KD_MMAP_JIT_ROLE_OBSERVER |
				KD_MMAP_JIT_ROLE_SOURCE | KD_MMAP_JIT_ROLE_RUNTIME | KD_MMAP_JIT_ROLE_OWNER |
				KD_MMAP_JIT_ROLE_BINDING) || !request.status.native.owner_is_current ||
				!request.status.native.source_calls || !request.status.killable_source_calls ||
				request.status.native.native_capacity != client->control.capacity ||
				!request.status.native.mm_identity || !request.status.native.object_identity ||
				!request.status.native.gate_identity || !request.status.source_identity ||
				!request.status.runtime_identity || !request.status.storage_identity) {
		client->control.start_errno = EPROTO;
		jit_query(client);
		return false;
	}
	client->control.started = true;
	return true;
}

static void print_jit_round(struct jit_round *round)
{
	uint64_t index;
	printf("{\"status\":\"syscall_completion_%s\",\"overall_pass\":%s,"
		"\"threads\":%" PRIu64 ",\"created_threads\":%" PRIu64 ",\"iterations_per_thread\":%" PRIu64 ","
		"\"deadline_ms\":%" PRIu64 ",\"page_bytes\":%ld,\"mapping_pages\":2,"
		"\"arena_address\":%" PRIuPTR ",\"arena_bytes\":%zu,\"arena_reservations\":%" PRIu64 ","
		"\"arena_cleanup_errno\":%d,\"deadline_exceeded\":%s,\"completed_iterations\":%" PRIu64 ","
		"\"worker_errors\":%" PRIu64 ",\"setup_error\":\"%s\",\"setup_errno\":%d,"
		"\"elapsed_ns\":%" PRIu64 ",\"workers\":[", round->passed ? "pass" : "fail",
		round->passed ? "true" : "false", round->count, round->created, round->iterations,
		round->milliseconds, round->page, (uintptr_t)round->arena, round->arena_length,
		round->arena_reservations, round->cleanup_errno, round->end > round->start + round->milliseconds * UINT64_C(1000000) ? "true" : "false",
		round->completed, round->errors, round->setup_error, round->setup_errno,
		round->end >= round->start ? round->end - round->start : 0);
	for (index = 0; index < round->count && round->workers; ++index) {
		struct worker *worker = &round->workers[index];
		printf("%s{\"id\":%" PRIu64 ",\"tid\":%ld,\"slot_address\":%" PRIuPTR
			",\"completed\":%" PRIu64 ",\"mmap_attempts\":%" PRIu64 ",\"mmap_successes\":%" PRIu64
			",\"munmap_attempts\":%" PRIu64 ",\"munmap_successes\":%" PRIu64
			",\"mincore_attempts\":%" PRIu64 ",\"unmapped_page_checks\":%" PRIu64
			",\"reuse_successes\":%" PRIu64 ",\"fresh_zero_bytes\":%" PRIu64 ",\"written_bytes\":%" PRIu64
			",\"readback_bytes\":%" PRIu64 ",\"deadline_reached\":%s,\"error\":\"%s\",\"errno\":%d,"
			"\"error_iteration\":%" PRIu64 ",\"error_offset\":%zu}", index ? "," : "", index, worker->tid,
			(uintptr_t)worker->slot, worker->completed, worker->mmap_attempts, worker->mmap_successes,
			worker->munmap_attempts, worker->munmap_successes, worker->mincore_attempts,
			worker->hole_checks, worker->reuse_successes, worker->zero_bytes, worker->written_bytes,
			worker->checked_bytes, worker->deadline_reached ? "true" : "false",
			worker->error ? worker->error : "none", worker->error_number, worker->error_iteration, worker->error_offset);
	}
	printf("]}");
}

/* Only this original owner controls the start gate and joins. Every worker uses
 * the unchanged common real-syscall body above; no ioctl supplies MM effects.
 */
static void jit_run_round(struct jit_client *client, struct jit_round *round)
{
	struct group group = { .mutex = PTHREAD_MUTEX_INITIALIZER,
		.condition = PTHREAD_COND_INITIALIZER };
	size_t index;
	size_t stride = 4 * (size_t)round->page;
	round->setup_error = "none";
	group.page_bytes = round->page;
	group.iterations = round->iterations;
	atomic_init(&group.stop, false);
	round->arena_length = round->count * stride;
	round->workers = calloc(round->count, sizeof(*round->workers));
	if (!round->workers) {
		round->setup_error = "workers_calloc"; round->setup_errno = errno;
		return;
	}
	round->arena = (void *)syscall(SYS_mmap, NULL, round->arena_length, PROT_NONE,
		MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (round->arena == MAP_FAILED) {
		round->setup_error = "arena_mmap"; round->setup_errno = errno;
		return;
	}
	round->arena_reservations = 1;
	for (index = 0; index < round->count; ++index) {
		struct worker *worker = &round->workers[index];
		worker->group = &group; worker->id = index;
		worker->slot = round->arena + index * stride + round->page;
		round->setup_errno = pthread_create(&worker->thread, NULL, run_worker, worker);
		if (round->setup_errno) {
			round->setup_error = "pthread_create";
			break;
		}
		++round->created;
	}
	{
		int result = pthread_mutex_lock(&group.mutex);
		if (result)
			unjoined_failure(&client->control, "JIT start mutex", result);
	}
	if (!now_ns(&round->start) || round->milliseconds >
				(UINT64_MAX - round->start) / UINT64_C(1000000)) {
		round->setup_error = "deadline_clock";
		round->setup_errno = errno ? errno : EOVERFLOW;
	}
	group.deadline_ns = round->start + round->milliseconds * UINT64_C(1000000);
	group.abort = round->created != round->count || strcmp(round->setup_error, "none");
	group.start = true;
	{
		int broadcast = pthread_cond_broadcast(&group.condition);
		int unlock = pthread_mutex_unlock(&group.mutex);
		if (broadcast || unlock)
			unjoined_failure(&client->control, "JIT start gate", broadcast ? broadcast : unlock);
	}
	for (index = 0; index < round->created; ++index) {
		int result = pthread_join(round->workers[index].thread, NULL);
		if (result)
			unjoined_failure(&client->control, "JIT pthread_join", result);
	}
	if (!now_ns(&round->end)) {
		round->setup_error = "final_clock"; round->setup_errno = errno;
	}
	if (syscall(SYS_munmap, round->arena, round->arena_length))
		round->cleanup_errno = errno;
	{
		int result = pthread_cond_destroy(&group.condition);
		int other = pthread_mutex_destroy(&group.mutex);
		if ((result || other) && !strcmp(round->setup_error, "none")) {
			round->setup_error = "pthread_destroy";
			round->setup_errno = result ? result : other;
		}
	}
	for (index = 0; index < round->count; ++index) {
		round->completed += round->workers[index].completed;
		round->errors += round->workers[index].error != NULL;
	}
	round->passed = round->created == round->count && !strcmp(round->setup_error, "none") &&
		!round->cleanup_errno && !round->errors && round->completed == round->count * round->iterations &&
		round->end <= group.deadline_ns;
}

/* True selects another explicit round; false closes source admission. Each
 * announcement discards old pending phase signals before publishing readiness.
 */
static bool jit_pause(struct jit_client *client, const char *phase,
		uint64_t round_number, struct jit_round *round, bool next)
{
	int signal_number;
	if (!jit_clear_phase_signals(client)) {
		client->phase_errno = errno;
		jit_preserve(client, "phase", client->phase_errno);
		return false;
	}
	jit_phase_prefix(client, phase, round_number, next);
	if (round) {
		printf(",\"workload\":"); print_jit_round(round);
	}
	puts("}"); fflush(stdout);
	signal_number = jit_timed_signal(client);
	if (signal_number == SIGUSR2 && next)
		return true;
	if (signal_number == SIGUSR1)
		return false;
	client->phase_errno = signal_number < 0 ? errno : EPROTO;
	jit_preserve(client, "phase", client->phase_errno);
	return false;
}

static bool jit_single_owner(struct jit_client *client)
{
	uint64_t start, value;
	if (!now_ns(&start))
		return false;
	for (;;) {
		if (!jit_query(client))
			return false;
		if (!client->control.cleanup_required || !client->profile.native.owner_is_current ||
				client->profile.native.owner_threads == 1)
			return true;
		if (!now_ns(&value))
			return false;
		if (value - start >= client->phase_ms * UINT64_C(1000000)) {
			errno = EBUSY;
			return false;
		}
		if (sched_yield())
			return false;
	}
}

static void jit_finish_client(struct jit_client *client)
{
	bool owner_left = false;
	if (client->control.fd < 0)
		return;
	for (;;) {
		if (!jit_single_owner(client)) {
			jit_preserve(client, "query", client->control.query_errno ? client->control.query_errno : errno);
			continue;
		}
		if (!client->control.cleanup_required)
			break;
		if (!client->profile.native.owner_is_current) {
			jit_preserve(client, "query", EPERM);
			continue;
		}
		if (!client->profile.owner_left || (client->profile.roles & KD_MMAP_JIT_ROLE_OWNER)) {
			struct kd_mmap_jit_request request = { .abi = KD_MMAP_JIT_ABI,
				.contract_flags = KD_MMAP_API_QUIESCENT_CHANGE };
			++client->leave_attempts;
			if (ioctl(client->control.fd, KD_MMAP_API_LEAVE_JIT, &request))
				client->leave_errno = errno;
			else
				client->leave_errno = 0;
			if (!jit_query(client) || !client->profile.owner_left ||
				(client->profile.roles & KD_MMAP_JIT_ROLE_OWNER)) {
				jit_preserve(client, "leave", client->leave_errno ? client->leave_errno : EBUSY);
				continue;
			}
		}
		if (!owner_left) {
			/* A fresh post-LEAVE signal alone permits END; earlier RUN/LEAVE pulses
			 * cannot stand in for host shutdown/archive/settle/session-close proof.
			 */
			jit_pause(client, "jit_owner_left", client->completed_rounds, NULL, false);
			owner_left = true;
		}
		{
			struct kd_mmap_jit_request request = { .abi = KD_MMAP_JIT_ABI,
				.contract_flags = KD_MMAP_API_QUIESCENT_CHANGE };
			++client->control.end_attempts;
			if (ioctl(client->control.fd, KD_MMAP_API_END_JIT, &request))
				client->control.end_errno = errno;
			else
				client->control.end_errno = 0;
			if (jit_query(client) && !client->control.cleanup_required)
				break;
			jit_preserve(client, "end", client->control.end_errno ? client->control.end_errno : EBUSY);
		}
	}
	if (close(client->control.fd))
		client->control.close_errno = errno;
	client->control.fd = -1;
	jit_clear_phase_signals(client);
	pthread_sigmask(SIG_SETMASK, &client->control.original_mask, NULL);
}

static int jit_main(int argc, char **argv)
{
	struct jit_client client = { .control = { .fd = -1 }, .all_rounds_pass = true };
	uint64_t count = 0, iterations = 0, milliseconds = 0;
	size_t index;
	long page;
	bool started, next, clean;
	for (index = 1; index < (size_t)argc;) {
		uint64_t *destination;
		if (!strcmp(argv[index], "--quiescent-mm")) {
			if (client.control.quiescent)
				return 2;
			client.control.quiescent = true; ++index; continue;
		}
		if (index + 1 >= (size_t)argc)
			return 2;
		if (!strcmp(argv[index], "--control-device") || !strcmp(argv[index], "--jit-config")) {
			const char **path = !strcmp(argv[index], "--control-device") ?
				&client.control.path : &client.config_path;
			if (*path || argv[index + 1][0] != '/')
				return 2;
			*path = argv[index + 1]; index += 2; continue;
		}
		destination = !strcmp(argv[index], "--threads") ? &count :
			!strcmp(argv[index], "--iterations") ? &iterations :
			!strcmp(argv[index], "--deadline-ms") ? &milliseconds :
			!strcmp(argv[index], "--jit-config-bytes") ? &client.config_bytes :
			!strcmp(argv[index], "--jit-phase-timeout-ms") ? &client.phase_ms :
			!strcmp(argv[index], "--jit-rounds") ? &client.rounds : NULL;
		if (!destination || *destination || !number(argv[index + 1], destination))
			return 2;
		index += 2;
	}
	page = sysconf(_SC_PAGESIZE);
	if (!count || !iterations || !milliseconds || !client.control.path || !client.control.quiescent ||
				!client.config_path || !client.config_bytes || !client.phase_ms || !client.rounds ||
				client.rounds > UINT_MAX || page <= 0 || (size_t)page > SIZE_MAX / 4 ||
				count > SIZE_MAX / sizeof(struct worker) || count > SIZE_MAX / (4 * (size_t)page) ||
				iterations > UINT64_MAX / count || client.rounds > UINT64_MAX / (count * iterations) ||
				milliseconds > UINT64_MAX / UINT64_C(1000000) || client.phase_ms > UINT64_MAX / UINT64_C(1000000) ||
				iterations > UINT64_MAX / (4 * (uint64_t)page)) {
		fprintf(stderr, "ABI2 needs explicit finite syscall/phase/round bounds and frozen config\n");
		return 2;
	}
	if (!jit_read_input(&client)) {
		fprintf(stderr, "ABI2 input failed: %s\n", strerror(errno));
		free(client.input_bytes);
		return 1;
	}
	if (!jit_signals(&client)) {
		fprintf(stderr, "ABI2 phase signal setup failed: %s\n", strerror(errno));
		free(client.input_bytes);
		return 1;
	}
	started = jit_start_client(&client);
	next = false;
	if (started)
		next = jit_pause(&client, "jit_ready", 0, NULL, true);
	else if (client.control.fd >= 0 && (client.control.cleanup_required || client.control.query_errno))
		jit_preserve(&client, "start", client.control.start_errno ? client.control.start_errno : EPROTO);
	while (next && client.completed_rounds < client.rounds) {
		struct jit_round round = { .count = count, .iterations = iterations,
			.milliseconds = milliseconds, .page = page };
		jit_run_round(&client, &round);
		++client.completed_rounds;
		client.all_rounds_pass = client.all_rounds_pass && round.passed;
		if (!jit_query(&client))
			client.control.cleanup_failed = true;
		next = jit_pause(&client, "jit_round_complete", client.completed_rounds, &round,
			client.all_rounds_pass && client.completed_rounds < client.rounds);
		free(round.workers);
	}
	jit_finish_client(&client);
	clean = started && !client.control.start_errno && !client.control.open_errno &&
		!client.control.query_errno && !client.control.end_errno && !client.leave_errno &&
		!client.control.close_errno && !client.phase_errno && !client.control.cleanup_failed &&
		!client.control.cleanup_required && client.profile.state == KD_MMAP_JIT_RETIRED &&
		!client.profile.roles && client.profile.native.pool_idle && !client.profile.native.gate_locked &&
		!client.profile.native.gate_contended && !client.profile.native.count_overflow && !client.profile.event_overflow &&
		client.profile.native.mm_identity == client.control.start.mm_identity &&
		client.profile.native.object_identity == client.control.start.object_identity &&
		client.profile.native.gate_identity == client.control.start.gate_identity;
	printf("{\"schema\":2,\"phase\":\"jit_finished\",\"status\":\"syscall_completion_%s\","
		"\"overall_pass\":%s,\"kd_observations\":\"raw_source_profile\",\"pid\":%ld,\"tid\":%ld,"
		"\"round\":%" PRIu64 ",\"phase_timeout_ms\":%" PRIu64 ",\"next_round_allowed\":false,"
		"\"all_rounds_pass\":%s,\"requested_rounds\":%" PRIu64 ",\"completed_rounds\":%" PRIu64 ","
		"\"cleanup_required\":%s,\"cleanup_failed\":%s,\"open_errno\":%d,\"start_errno\":%d,"
		"\"query_errno\":%d,\"leave_errno\":%d,\"end_errno\":%d,\"close_errno\":%d,\"phase_errno\":%d,"
		"\"leave_attempts\":%" PRIu64 ",\"end_attempts\":%" PRIu64 ",\"profile\":",
		started && client.all_rounds_pass && client.completed_rounds == client.rounds ? "pass" : "fail",
		clean && client.all_rounds_pass && client.completed_rounds == client.rounds ? "true" : "false",
		(long)getpid(), (long)syscall(SYS_gettid), client.completed_rounds, client.phase_ms,
		client.all_rounds_pass ? "true" : "false", client.rounds, client.completed_rounds,
		client.control.cleanup_required ? "true" : "false", client.control.cleanup_failed ? "true" : "false",
		client.control.open_errno, client.control.start_errno, client.control.query_errno,
		client.leave_errno, client.control.end_errno, client.control.close_errno, client.phase_errno,
		client.leave_attempts, client.control.end_attempts);
	print_jit_status(&client.profile);
	puts("}"); fflush(stdout);
	free(client.input_bytes);
	return clean && client.all_rounds_pass && client.completed_rounds == client.rounds ? 0 : 1;
}
