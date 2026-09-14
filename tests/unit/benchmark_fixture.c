/* Run the actual userspace driver with real pthreads, but never a kernel
 * workload. Deterministic clocks expose boundary/quantile mistakes without
 * depending on scheduler speed; a second path uses the real guest clocks. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static int fixture_open(const char *path, int flags, ...);
static int fixture_ioctl(int fd, unsigned long command, ...);
static int fixture_clock(clockid_t clock, struct timespec *stamp);
static int fixture_create(pthread_t *thread, const pthread_attr_t *attr,
			  void *(*start)(void *), void *arg);
static int fixture_join(pthread_t thread, void **result);

#define main benchmark_main
#define open fixture_open
#define ioctl fixture_ioctl
#define clock_gettime fixture_clock
#define pthread_create fixture_create
#define pthread_join fixture_join
#include "../../bench/klock_test.c"
#undef main
#undef open
#undef ioctl
#undef clock_gettime
#undef pthread_create
#undef pthread_join

static atomic_uint ready, ioctls;
static unsigned int opens, creates, joins, expected_threads, expected_role;
static _Thread_local struct thread_data *worker;
static _Thread_local unsigned int mono_reads, cpu_reads, calls;
static _Thread_local uint64_t mono_now;

struct launch {
	void *(*start)(void *);
	void *arg;
};

static void *fixture_worker(void *arg)
{
	struct launch copy = *(struct launch *)arg;

	free(arg);
	worker = copy.arg;
	atomic_fetch_add(&ready, 1);
	return copy.start(copy.arg);
}

static int fixture_create(pthread_t *thread, const pthread_attr_t *attr,
			  void *(*start)(void *), void *arg)
{
	struct launch *launch;
	int error;

	creates++;
	if (getenv("BENCH_CREATE_FAIL") && creates == 2)
		return EAGAIN;
	launch = malloc(sizeof(*launch));
	assert(launch);
	*launch = (struct launch){ .start = start, .arg = arg };
	error = pthread_create(thread, attr, fixture_worker, launch);
	if (error)
		free(launch);
	return error;
}

static int fixture_join(pthread_t thread, void **result)
{
	joins++;
	if (getenv("BENCH_JOIN_FAIL"))
		return EINVAL;
	return pthread_join(thread, result);
}

static int fixture_open(const char *path, int flags, ...)
{
	opens++;
	assert(!strcmp(path, DEVICE_PATH) && flags == O_RDWR);
	if (getenv("BENCH_OPEN_FAIL")) {
		errno = ENOENT;
		return -1;
	}
	return open("/dev/null", flags);
}

static int fixture_ioctl(int fd, unsigned long command, ...)
{
	struct test_args *args;
	unsigned int role;
	char name[16];
	va_list ap;

	assert(worker && fd == worker->fd && command == IOC_RUN_TEST);
	assert(atomic_load(&ready) == expected_threads);
	va_start(ap, command);
	args = va_arg(ap, struct test_args *);
	va_end(ap);
	assert(args == &worker->args);
	role = expected_role + worker->thread_id;
	if (getenv("KD_TEST_MIXED")) {
		role = 0x20000000U |
		       (worker->thread_id & 1 ? (worker->thread_id / 2) % 4 : 0);
		assert(!pthread_getname_np(pthread_self(), name, sizeof(name)));
		assert(!strcmp(name, worker->thread_id & 1 ? "kd_native" : "klock_test"));
	}
	assert(args->role == role);
	calls++;
	if (getenv("BENCH_IOCTL_FAIL") && calls == 2) {
		errno = EIO;
		return -1;
	}
	atomic_fetch_add(&ioctls, 1);
	/* Give real pthreads a chance to overlap even on a single guest CPU. */
	usleep(1000);
	return 0;
}

static int fixture_clock(clockid_t clock, struct timespec *stamp)
{
	const char *fault = getenv("BENCH_CLOCK_FAIL");
	uint64_t value;
	unsigned int index;

	/* A main-thread timestamp or pre-barrier sample must not be accepted as
	 * worker payload time, regardless of how slow thread creation/join is. */
	assert(worker && atomic_load(&ready) == expected_threads);
	if (getenv("BENCH_REAL_CLOCK"))
		return clock_gettime(clock, stamp);
	if (clock == CLOCK_THREAD_CPUTIME_ID) {
		index = cpu_reads++;
		value = 1000000 + index * 500;
		if (fault && !strcmp(fault, "cpu") && index == 1) {
			errno = EIO;
			return -1;
		}
	} else {
		assert(clock == CLOCK_MONOTONIC);
		index = mono_reads++;
		if (fault && ((!strcmp(fault, "before") && index == 1) ||
			      (!strcmp(fault, "after") && index == 2) ||
			      (!strcmp(fault, "end") &&
			       index == 2 * worker->sys_count + 1))) {
			errno = EIO;
			return -1;
		}
		if (!index)
			mono_now = 1000000000ULL + worker->thread_id * 100;
		else if (index & 1)
			mono_now += 1000;
		else
			mono_now += (worker->thread_id + 1) * 1000 + (index / 2 - 1) * 100;
		value = mono_now;
		if (fault && !strcmp(fault, "backward") && index == 2)
			value = 0;
	}
	stamp->tv_sec = value / 1000000000ULL;
	stamp->tv_nsec = value % 1000000000ULL;
	return 0;
}

int main(int argc, char **argv)
{
	int result;

	expected_threads = argc > 1 ? strtoul(argv[1], NULL, 10) : 0;
	expected_role = argc > 6 ? strtoul(argv[6], NULL, 10) : 0;
	result = benchmark_main(argc, argv);
	fprintf(stderr, "fixture opens=%u creates=%u joins=%u ioctls=%u\n",
		opens, creates, joins, atomic_load(&ioctls));
	return result;
}
