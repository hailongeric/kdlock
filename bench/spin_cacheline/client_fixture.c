// SPDX-License-Identifier: GPL-2.0
/* Guest userspace substitute for the device, running the real client/payload.
 * This tests aggregation and deltas, not guest spinlock or JIT execution. */
#define _GNU_SOURCE
#include <pthread.h>
#include <sched.h>
#include <time.h>
static int fixture_create(pthread_t *, const pthread_attr_t *, void *(*)(void *), void *);
static int fixture_affinity(pthread_t, size_t, const cpu_set_t *);
static int fixture_name(pthread_t, const char *);
static int fixture_clock_gettime(clockid_t, struct timespec *);
#define pthread_create fixture_create
#define pthread_setaffinity_np fixture_affinity
#define pthread_setname_np fixture_name
#define clock_gettime fixture_clock_gettime
#define ioctl fixture_ioctl
#define open fixture_open
#define close fixture_close
#define main client_main
#include "client.c"
#undef ioctl
#undef open
#undef close
#undef main
#undef pthread_create
#undef pthread_setaffinity_np
#undef pthread_setname_np
#undef clock_gettime
#include <stdarg.h>

typedef pthread_spinlock_t spinlock_t;
#define spin_lock(p) pthread_spin_lock(p)
#define spin_unlock(p) pthread_spin_unlock(p)
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x, v) (*(volatile __typeof__(x) *)&(x) = (v))
#include "../../workload_modules/spin_cacheline/payload.h"
#include "../../workload_modules/spin_cacheline/post_work.h"

static unsigned char control[64] __attribute__((aligned(64)));
static int snapshots;
static unsigned int creates, expected_workers, layout_calls;
static atomic_uint setup_calls;
static atomic_uint run_calls, monotonic_calls, cpu_clock_calls;
static atomic_ullong submitted_iterations;
static struct gate *start_gate;

/* Observe API calls only in this substitute device, never in the measured
 * client. Increasing batch size must not increase ioctl or clock call counts. */
static int fixture_clock_gettime(clockid_t clock, struct timespec *t)
{
	if (clock == CLOCK_MONOTONIC)
		atomic_fetch_add_explicit(&monotonic_calls, 1, memory_order_relaxed);
	else if (clock == CLOCK_THREAD_CPUTIME_ID)
		atomic_fetch_add_explicit(&cpu_clock_calls, 1, memory_order_relaxed);
	else
		abort();
	return clock_gettime(clock, t);
}

static bool fault_is(const char *name)
{
	const char *fault = getenv("SC_FIXTURE_FAULT");
	return fault && !strcmp(fault, name);
}

static int fixture_create(pthread_t *thread, const pthread_attr_t *attr,
			  void *(*entry)(void *), void *arg)
{
	if (!creates)
		start_gate = ((struct worker *)arg)->gate;
	if (creates++ == 1 && fault_is("create"))
		return EAGAIN;
	return pthread_create(thread, attr, entry, arg);
}

static int fixture_affinity(pthread_t thread, size_t size, const cpu_set_t *cpus)
{
	if (fault_is("affinity"))
		return EINVAL;
	return pthread_setaffinity_np(thread, size, cpus);
}

static int fixture_name(pthread_t thread, const char *name)
{
	/* Leave one worker unready long enough to expose premature release. */
	if (fault_is("slow_ready") && atomic_fetch_add(&setup_calls, 1) == 0)
		usleep(50000);
	return pthread_setname_np(thread, name);
}

int fixture_open(const char *path, int flags, ...)
{
	(void)flags;
	return !strcmp(path, SC_DEVICE) ? 100 : -1;
}

int fixture_close(int fd)
{
	return fd == 100 ? 0 : -1;
}

int fixture_ioctl(int fd, unsigned long cmd, ...)
{
	va_list args;
	void *packet;
	const char *fault = getenv("SC_FIXTURE_FAULT");
	if (fd != 100)
		return -1;
	va_start(args, cmd);
	packet = va_arg(args, void *);
	va_end(args);
	if (cmd == SC_LAYOUT) {
		struct sc_layout *l = packet;
		layout_calls++;
		*l = (struct sc_layout){ .version = 1, .line_bytes = 64, .slots = 16,
			.lock_bytes = sizeof(sc_lock), .lock_addr = (uintptr_t)&sc_lock,
			.control_addr = (uintptr_t)control, .data_addr = (uintptr_t)sc_data };
		for (int i = 0; i < 16; i++)
			l->slot_addr[i] = (uintptr_t)&sc_data[i];
		if (fault && !strcmp(fault, "layout"))
			l->slot_addr[1]++;
		return 0;
	}
	if (cmd == SC_COUNTS) {
		struct sc_counts *c = packet;
		memset(c, 0, sizeof(*c));
		for (int i = 0; i < 16; i++)
			c->values[i] = sc_data[i].value;
		if (snapshots++ && fault) {
			if (!strcmp(fault, "inactive"))
				c->values[15]++;
			if (!strcmp(fault, "active"))
				c->values[0]--;
		}
		return 0;
	}
	if (cmd == SC_RUN) {
		struct sc_run *r = packet;
		void (*body)(void) = NULL;
		__u64 post_state = 1;
		atomic_fetch_add_explicit(&run_calls, 1, memory_order_relaxed);
		atomic_fetch_add_explicit(&submitted_iterations, r->iterations, memory_order_relaxed);
		if (fault_is("create") || fault_is("affinity") ||
		    atomic_load_explicit(&start_gate->ready, memory_order_acquire) != expected_workers ||
		    !atomic_load_explicit(&start_gate->go, memory_order_acquire))
			abort();
		switch (r->cachelines) {
		case 1: body = sc_body_1; break;
		case 2: body = sc_body_2; break;
		case 4: body = sc_body_4; break;
		case 8: body = sc_body_8; break;
		case 16: body = sc_body_16; break;
		}
		if (!body)
			return -1;
		for (r->completed = 0; r->completed < r->iterations; r->completed++) {
			body();
			post_state = sc_post_work(post_state);
		}
		if (fault && !strcmp(fault, "completed"))
			r->completed--;
		return 0;
	}
	return -1;
}

int main(int argc, char **argv)
{
	_Static_assert(sizeof(struct sc_slot) == 64, "payload stride");
	_Static_assert(_Alignof(struct sc_slot) == 64, "payload alignment");
	pthread_spin_init(&sc_lock, PTHREAD_PROCESS_PRIVATE);
	for (int i = 1; i + 1 < argc; i++) {
		if (!strcmp(argv[i], "--cpus")) {
			expected_workers = 1;
			for (const char *p = argv[i + 1]; *p; p++)
				expected_workers += *p == ',';
		}
	}
	for (int i = 0; i < 16; i++)
		sc_data[i].value = 100 + i;
	int result = client_main(argc, argv);
	if (getenv("SC_FIXTURE_COUNTS"))
		fprintf(stderr, "{\"layout\":%u,\"counts\":%d,\"run\":%u,"
			"\"submitted_iterations\":%llu,\"monotonic\":%u,\"thread_cputime\":%u}\n",
			layout_calls, snapshots, atomic_load(&run_calls),
			atomic_load(&submitted_iterations), atomic_load(&monotonic_calls),
			atomic_load(&cpu_clock_calls));
	return result;
}
