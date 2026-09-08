/*
 * klock_test — userspace driver for /dev/lock_dev.
 *
 * Usage:  ./klock_test <threads> <loops> <workload> <runs> <mode> [role-base]
 *
 *   threads  — number of concurrent threads
 *   loops    — how many ioctl calls per thread
 *   workload — busy-loop iterations inside each critical section
 *   runs     — ioctl invocations per worker
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
 *   → 4 threads, 100k iterations each, 1000-loop workload, mode 0
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <unistd.h>

#define DEVICE_PATH "/dev/lock_dev"
#define IOC_MAGIC 'k'

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
	struct test_args args;
};

static pthread_barrier_t start_barrier;

static void *worker_thread(void *arg)
{
	struct thread_data *data = arg;
	unsigned long count;
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

	pthread_barrier_wait(&start_barrier);
	if (data->error)
		return NULL;

	for (count = 0; count < data->sys_count; count++) {
		if (ioctl(data->fd, IOC_RUN_TEST, &data->args) < 0) {
			data->error = errno;
			perror("IOCTL failed");
			break;
		}
		printf("Thread %d: Loop %lu completed\n", data->thread_id,
		       count);
	}
	return NULL;
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
	int fd;
	pthread_t *threads;
	struct thread_data *thread_data;
	long long start_time;
	long long end_time;
	int error;
	int result = EXIT_SUCCESS;
	int i;

	if (argc < 6) {
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
		return EXIT_FAILURE;
	}

	num_threads = atoi(argv[1]);
	loop_count = strtoul(argv[2], NULL, 10);
	work_load = strtoul(argv[3], NULL, 10);
	sys_count = strtoul(argv[4], NULL, 10);
	mode = (unsigned int)strtoul(argv[5], NULL, 10);
	role_base = argc > 6 ? (unsigned int)strtoul(argv[6], NULL, 10) : 0;

	if (num_threads <= 0 || mode > MODE_MUTEX_GS_CONTEXT) {
		fprintf(stderr, "Invalid thread count or mode: %d, %u\n",
			num_threads, mode);
		return EXIT_FAILURE;
	}

	fd = open(DEVICE_PATH, O_RDWR);
	if (fd < 0) {
		perror("Failed to open device");
		return EXIT_FAILURE;
	}

	threads = calloc((size_t)num_threads, sizeof(*threads));
	thread_data = calloc((size_t)num_threads, sizeof(*thread_data));
	if (!threads || !thread_data) {
		fprintf(stderr, "Failed to allocate thread state\n");
		free(threads);
		free(thread_data);
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
		close(fd);
		return EXIT_FAILURE;
	}

	printf("Starting Test:\n");
	printf("  Threads: %d\n", num_threads);
	printf("  Loops per thread: %lu\n", loop_count);
	printf("  Critical Section Workload: %lu\n", work_load);
	printf("  Mode: %u (%s)\n", mode, mode_name(mode));

	start_time = current_timestamp();

	for (i = 0; i < num_threads; i++) {
		thread_data[i].thread_id = i;
		thread_data[i].fd = fd;
		thread_data[i].args.loop_count = loop_count;
		thread_data[i].args.work_load = work_load;
		thread_data[i].args.mode = mode;
		thread_data[i].args.role = role_base + (unsigned int)i;
		thread_data[i].sys_count = sys_count;

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
			result = EXIT_FAILURE;
		}
		if (thread_data[i].error)
			result = EXIT_FAILURE;
	}

	end_time = current_timestamp();

	printf("------------------------------------------------\n");
	printf("All threads finished.\n");
	printf("Total Time: %lld ms\n", end_time - start_time);

	printf("Check 'dmesg' for kernel logs.\n");

	free(threads);
	free(thread_data);
	pthread_barrier_destroy(&start_barrier);
	close(fd);
	return result;
}
