/*
 * klock_test — userspace driver for /dev/lock_dev.
 *
 * Usage:  ./klock_test <threads> <loops> <workload> <runs> <mode> [role-base]
 *
 *   threads  — number of concurrent threads
 *   loops    — critical-section iterations inside each ioctl
 *   workload — busy-loop iterations inside each critical section
 *   runs     — ioctl invocations per worker (each contains loops iterations)
 *   mode     — benchmark mode (see below)
 *
 * Modes:
 *   0  MODE_SPIN_CONTENTION    Contended single spinlock
 *   1  MODE_SPIN_NESTED        Nested spinlocks (lock A → lock B)
 *   2  MODE_SPIN_API_IN_LOCK   Spinlock CS containing a kernel API call
 *   3  MODE_MUTEX_CONTENTION   Contended single mutex
 *   4  MODE_MUTEX_NESTED       Nested mutexes
 *   5  MODE_MUTEX_API_IN_LOCK  Mutex CS containing a kernel API call
 *   6  MODE_SPIN_DEEP_NESTED   Deep nested spinlocks (A -> B -> C)
 *   7  MODE_SPIN_OOO_NESTED    Out-of-order unlock (A, B, unlock A, B)
 *   8  MODE_SPIN_INNER_CONTENTION  Independent contenders for inner B
 *   9  MODE_SPIN_ABORT_RECOVERY  Isolated nested-JIT abort recovery
 *   10 MODE_SPIN_GS_CONTEXT      Nested spinlock GS/current validation
 *   11 MODE_MUTEX_GS_CONTEXT     Nested mutex GS/current validation
 *
 * Modes 0-2 and 6-10 exercise the spinlock delegation path (kd_spinlock.c).
 * Modes 3-5 and 11 exercise the mutex delegation path (kd_mutex.c).
 *
 * Example:  ./klock_test 4 100000 1000 10 0
 *   -> 4 threads, 10 ioctls each, 100k CS iterations/ioctl, mode 0
 *
 * KD_TEST_METRICS=1 suppresses per-ioctl printing and emits one JSON record.
 * These are instrumented ioctl timings, not pure lock/CS or JIT-only costs.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#define DEVICE_PATH "/dev/lock_dev"
#define IOC_MAGIC 'k'
/* At most 8 MiB of exact latency samples; do not silently downsample p99. */
#define MAX_METRIC_SAMPLES (1UL << 20)

struct test_args {
	unsigned long loop_count;
	unsigned long work_load;
	unsigned int mode;
	unsigned int role;
};

#define IOC_RUN_TEST _IOW(IOC_MAGIC, 1, struct test_args)

#define MODE_SPIN_CONTENTION 0
#define MODE_SPIN_NESTED 1
#define MODE_SPIN_API_IN_LOCK 2
#define MODE_MUTEX_CONTENTION 3
#define MODE_MUTEX_NESTED 4
#define MODE_MUTEX_API_IN_LOCK 5
#define MODE_SPIN_DEEP_NESTED 6
#define MODE_SPIN_OOO_NESTED 7
#define MODE_SPIN_INNER_CONTENTION 8
#define MODE_SPIN_ABORT_RECOVERY 9
#define MODE_SPIN_GS_CONTEXT 10
#define MODE_MUTEX_GS_CONTEXT 11

struct thread_data {
	int thread_id;
	int fd;
	unsigned long sys_count;
	int error;
	unsigned long completed;
	uint64_t wall_start, wall_end, cpu_ns;
	uint64_t *latencies;
	struct test_args args;
};

static pthread_barrier_t start_barrier;

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

/* Decimal-only parsing also prevents role truncation/wrap from selecting a
 * different kernel workload. Reject invalid input before touching the device. */
static bool parse_number(const char *text, unsigned long maximum,
			 unsigned long *value)
{
	char *end;

	if (!text[0] || strspn(text, "0123456789") != strlen(text))
		return false;
	errno = 0;
	*value = strtoul(text, &end, 10);
	return !errno && !*end && *value <= maximum;
}

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

static long long current_timestamp(void)
{
	struct timeval time;

	gettimeofday(&time, NULL);
	return time.tv_sec * 1000LL + time.tv_usec / 1000;
}

static const char *mode_name(unsigned int mode)
{
	switch (mode) {
	case MODE_SPIN_CONTENTION:
		return "spin-contention";
	case MODE_SPIN_NESTED:
		return "spin-nested";
	case MODE_SPIN_API_IN_LOCK:
		return "spin-api-in-lock";
	case MODE_MUTEX_CONTENTION:
		return "mutex-contention";
	case MODE_MUTEX_NESTED:
		return "mutex-nested";
	case MODE_MUTEX_API_IN_LOCK:
		return "mutex-api-in-lock";
	case MODE_SPIN_DEEP_NESTED:
		return "spin-deep-nested";
	case MODE_SPIN_OOO_NESTED:
		return "spin-ooo-nested";
	case MODE_SPIN_INNER_CONTENTION:
		return "spin-inner-contention";
	case MODE_SPIN_ABORT_RECOVERY:
		return "spin-abort-recovery";
	case MODE_SPIN_GS_CONTEXT:
		return "spin-gs-context";
	case MODE_MUTEX_GS_CONTEXT:
		return "mutex-gs-context";
	default:
		return "unknown";
	}
}

int main(int argc, char *argv[])
{
	int num_threads;
	unsigned long loop_count;
	unsigned long work_load;
	unsigned long sys_count;
	unsigned int mode;
	unsigned int role_base;
	unsigned long numbers[6] = { 0 };
	const unsigned long limits[] = {
		INT_MAX, ULONG_MAX, ULONG_MAX, ULONG_MAX,
		MODE_MUTEX_GS_CONTEXT, UINT_MAX,
	};
	const char *metrics_option = getenv("KD_TEST_METRICS");
	bool metrics = metrics_option && !strcmp(metrics_option, "1");
	uint64_t *samples = NULL;
	int fd;
	pthread_t *threads;
	struct thread_data *thread_data;
	long long start_time;
	long long end_time;
	int error;
	int result = EXIT_SUCCESS;
	int i;

	if (argc < 6 || argc > 7) {
		printf("Usage: %s <num_threads> <loop_count> <work_load> "
		       "<sys_count> <mode> [role-base]\n",
		       argv[0]);
		printf("Mode: 0=spin-contention, 1=spin-nested, "
		       "2=spin-api-in-lock\n");
		printf("      3=mutex-contention, 4=mutex-nested, "
		       "5=mutex-api-in-lock\n");
		printf("      6=spin-deep-nested\n");
		printf("      7=spin-ooo-nested\n");
		printf("      8=spin-inner-contention\n");
		printf("      9=spin-abort-recovery\n");
		printf("      10=spin-gs-context, 11=mutex-gs-context\n");
		printf("Example: %s 4 100000 1000 10 3\n", argv[0]);
		printf("KD_TEST_METRICS=1: structured instrumented ioctl timings\n");
		return EXIT_FAILURE;
	}

	for (i = 1; i < argc; i++) {
		if (!parse_number(argv[i], limits[i - 1], &numbers[i - 1])) {
			fprintf(stderr, "Invalid numeric argument %d: %s\n", i, argv[i]);
			return EXIT_FAILURE;
		}
	}
	num_threads = (int)numbers[0];
	loop_count = numbers[1];
	work_load = numbers[2];
	sys_count = numbers[3];
	mode = (unsigned int)numbers[4];
	role_base = (unsigned int)numbers[5];
	if (!num_threads || role_base > UINT_MAX - (unsigned int)(num_threads - 1) ||
	    (metrics_option && strcmp(metrics_option, "0") && !metrics) ||
	    (metrics && (!loop_count || !sys_count ||
			 sys_count > MAX_METRIC_SAMPLES / (unsigned long)num_threads))) {
		fprintf(stderr, "Invalid count, role range or KD_TEST_METRICS; "
			"metrics require positive loops/runs and at most %lu samples\n",
			MAX_METRIC_SAMPLES);
		return EXIT_FAILURE;
	}

	fd = open(DEVICE_PATH, O_RDWR);
	if (fd < 0) {
		perror("Failed to open device");
		return EXIT_FAILURE;
	}

	threads = calloc((size_t)num_threads, sizeof(*threads));
	thread_data = calloc((size_t)num_threads, sizeof(*thread_data));
	if (metrics)
		samples = calloc((size_t)num_threads * sys_count, sizeof(*samples));
	if (!threads || !thread_data || (metrics && !samples)) {
		fprintf(stderr, "Failed to allocate thread state\n");
		free(threads);
		free(thread_data);
		free(samples);
		close(fd);
		return EXIT_FAILURE;
	}

	error = pthread_barrier_init(&start_barrier, NULL,
				     (unsigned int)num_threads);
	if (error != 0) {
		fprintf(stderr, "Failed to initialize thread barrier: %s\n",
			strerror(error));
		free(threads);
		free(thread_data);
		free(samples);
		close(fd);
		return EXIT_FAILURE;
	}

	printf("Starting Test:\n");
	printf("  Threads: %d\n", num_threads);
	printf("  Loops per thread: %lu\n", loop_count);
	printf("  Critical Section Workload: %lu\n", work_load);
	printf("  Mode: %u (%s)\n", mode, mode_name(mode));

	start_time = metrics ? 0 : current_timestamp();

	for (i = 0; i < num_threads; i++) {
		thread_data[i].thread_id = i;
		thread_data[i].fd = fd;
		thread_data[i].args.loop_count = loop_count;
		thread_data[i].args.work_load = work_load;
		thread_data[i].args.mode = mode;
		thread_data[i].args.role = role_base + (unsigned int)i;
		thread_data[i].sys_count = sys_count;
		if (metrics)
			thread_data[i].latencies = samples + (size_t)i * sys_count;

		error = pthread_create(&threads[i], NULL, worker_thread,
				       &thread_data[i]);
		if (error != 0) {
			fprintf(stderr, "Failed to create thread: %s\n",
				strerror(error));
			exit(EXIT_FAILURE);
		}
	}

	for (i = 0; i < num_threads; i++) {
		error = pthread_join(threads[i], NULL);
		if (error) {
			fprintf(stderr, "Failed to join thread: %s\n",
				strerror(error));
			/* An unjoined worker may still own its state. Terminate the
			 * process instead of freeing storage or emitting success. */
			exit(EXIT_FAILURE);
		}
		if (thread_data[i].error) {
			fprintf(stderr, "Worker %d failed: %s\n", i,
				strerror(thread_data[i].error));
			result = EXIT_FAILURE;
		}
	}

	end_time = metrics ? 0 : current_timestamp();

	printf("------------------------------------------------\n");
	printf("All threads finished.\n");
	if (metrics) {
		if (report_metrics(thread_data, num_threads, role_base, samples))
			result = EXIT_FAILURE;
	} else {
		printf("Total Time: %lld ms\n", end_time - start_time);
	}

	printf("Check 'dmesg' for kernel logs.\n");

	free(threads);
	free(thread_data);
	free(samples);
	pthread_barrier_destroy(&start_barrier);
	close(fd);
	return result;
}
