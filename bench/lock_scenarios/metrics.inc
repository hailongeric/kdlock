/*
 * Complete-run aggregation and exact ioctl quantiles; errors keep counts only.
 * Private implementation included only by klock_test.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static int compare_latency(const void *left, const void *right)
{
	uint64_t a = *(const uint64_t *)left;
	uint64_t b = *(const uint64_t *)right;

	return (a > b) - (a < b);
}

/* Aggregate only a fully successful run. Failed ioctls/timestamps retain exact
 * completed counts but yield null performance fields, never a partial PASS.
 * Latencies are full ioctl calls (possibly many CS iterations), not lock waits. */
static int report_metrics(struct thread_data *data, int threads,
			  unsigned int role_base, uint64_t *samples)
{
	unsigned long requested = (unsigned long)threads * data[0].sys_count;
	unsigned long completed = 0;
	uint64_t start = UINT64_MAX, end = 0, cpu = 0;
	bool complete = true;
	int i;

	for (i = 0; i < threads; i++) {
		completed += data[i].completed;
		if (data[i].error || data[i].completed != data[i].sys_count)
			complete = false;
		if (data[i].wall_start < start)
			start = data[i].wall_start;
		if (data[i].wall_end > end)
			end = data[i].wall_end;
		if (UINT64_MAX - cpu < data[i].cpu_ns)
			complete = false;
		else
			cpu += data[i].cpu_ns;
	}
	if (end <= start)
		complete = false;
	printf("KD_BENCH_METRICS {\"schema\":1,\"complete\":%s,"
	       "\"threads\":%d,\"mode\":%u,\"role_base\":%u,"
	       "\"loops_per_ioctl\":%lu,\"workload\":%lu,"
	       "\"ioctls_per_thread\":%lu,\"requested_ioctls\":%lu,"
	       "\"completed_ioctls\":%lu,",
	       complete ? "true" : "false", threads, data[0].args.mode,
	       role_base, data[0].args.loop_count, data[0].args.work_load,
	       data[0].sys_count, requested, completed);
	if (complete) {
		qsort(samples, requested, sizeof(*samples), compare_latency);
		/* Nearest-rank quantiles, including small runs. The sample cap also
		 * bounds these integer products; no interpolation or sampling. */
		printf("\"wall_ns\":%" PRIu64 ",\"worker_cpu_ns\":%" PRIu64
		       ",\"ioctls_per_second\":%.6f,\"ioctl_p50_ns\":%" PRIu64
		       ",\"ioctl_p99_ns\":%" PRIu64 ",",
		       end - start, cpu, (double)requested * 1e9 / (end - start),
		       samples[(requested * 50 + 99) / 100 - 1],
		       samples[(requested * 99 + 99) / 100 - 1]);
	} else {
		printf("\"wall_ns\":null,\"worker_cpu_ns\":null,"
		       "\"ioctls_per_second\":null,\"ioctl_p50_ns\":null,"
		       "\"ioctl_p99_ns\":null,");
	}
	printf("\"workers\":[");
	for (i = 0; i < threads; i++)
		printf("%s{\"id\":%d,\"completed\":%lu,\"error\":%d}",
		       i ? "," : "", i, data[i].completed, data[i].error);
	printf("]}\n");
	return complete ? EXIT_SUCCESS : EXIT_FAILURE;
}
