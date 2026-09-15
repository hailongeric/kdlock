/*
 * Worker barrier, optional ioctl timing and completed-operation accounting.
 * Private implementation included only by klock_test.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* Convert one clock reading without allowing bad/overflowing timestamps to
 * produce a plausible duration. The caller propagates errors to run status. */
static int clock_ns(clockid_t clock, uint64_t *value)
{
	struct timespec stamp;

	if (clock_gettime(clock, &stamp))
		return errno ? errno : EIO;
	if (stamp.tv_sec < 0 || stamp.tv_nsec < 0 ||
	    stamp.tv_nsec >= 1000000000L ||
	    (uint64_t)stamp.tv_sec >
		    (UINT64_MAX - (uint64_t)stamp.tv_nsec) / 1000000000ULL)
		return EOVERFLOW;
	*value = (uint64_t)stamp.tv_sec * 1000000000ULL + stamp.tv_nsec;
	return 0;
}

/* The shared barrier creates contention; optional comm/role changes select
 * test participants, not a JIT switch. Actual JIT evidence comes from kernel
 * wrapper-return logs plus the workload integrity oracle, never this printf. */
static void *worker_thread(void *arg)
{
	struct thread_data *data = arg;
	unsigned long count;
	uint64_t cpu_start = 0, cpu_end, begin, end;
	int error;
	const char *comm = getenv("KD_TEST_COMM");

	/* Mixed validation keeps even workers on the ordinary target API and
	 * sends odd workers through native names and four spin/mutex variants. */
	if (getenv("KD_TEST_MIXED")) {
		comm = data->thread_id & 1 ? "kd_native" : "klock_test";
		data->args.role =
			0x20000000U |
			(data->thread_id & 1 ? (data->thread_id / 2) % 4 : 0);
	}
	if (comm)
		data->error = pthread_setname_np(pthread_self(), comm);

	error = pthread_barrier_wait(&start_barrier);
	if (error && error != PTHREAD_BARRIER_SERIAL_THREAD)
		data->error = error;
	if (data->error)
		return NULL;

	/* All workers have finished setup at the barrier. The envelope ends in
	 * this worker, not after main joins, so setup/reaping are not payload time.
	 * CPU accounting is only for this worker, not external owners or daemon. */
	if (data->latencies) {
		data->error = clock_ns(CLOCK_MONOTONIC, &data->wall_start);
		if (!data->error)
			data->error = clock_ns(CLOCK_THREAD_CPUTIME_ID, &cpu_start);
		if (data->error)
			return NULL;
	}
	for (count = 0; count < data->sys_count; count++) {
		if (data->latencies) {
			data->error = clock_ns(CLOCK_MONOTONIC, &begin);
			if (data->error)
				break;
		}
		if (ioctl(data->fd, IOC_RUN_TEST, &data->args) < 0) {
			data->error = errno ? errno : EIO;
			perror("IOCTL failed");
			break;
		}
		/* Count successful ioctls even if their final timestamp fails. They
		 * already ran and must not disappear from a partial-result record. */
		data->completed++;
		if (data->latencies) {
			data->error = clock_ns(CLOCK_MONOTONIC, &end);
			if (!data->error && end < begin)
				data->error = EIO;
			if (data->error)
				break;
			data->latencies[count] = end - begin;
		} else {
			printf("Thread %d: Loop %lu completed\n", data->thread_id,
			       count);
		}
	}
	if (data->latencies) {
		error = clock_ns(CLOCK_THREAD_CPUTIME_ID, &cpu_end);
		if (!error && cpu_end < cpu_start)
			error = EIO;
		if (!error)
			data->cpu_ns = cpu_end - cpu_start;
		if (!data->error)
			data->error = error;
		error = clock_ns(CLOCK_MONOTONIC, &data->wall_end);
		if (!error && data->wall_end < data->wall_start)
			error = EIO;
		if (!data->error)
			data->error = error;
	}
	return NULL;
}
