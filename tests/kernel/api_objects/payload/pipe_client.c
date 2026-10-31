// SPDX-License-Identifier: GPL-2.0-only
/* Actual syscall correctness only: no copied kernel body and no score. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "../../../../include/kd_api_control.h"

#define PAGE_BYTES 4096U
#define RECORD_BYTES 64U
#define RECORDS 256U
#define DATA_BYTES (2U * RECORDS * RECORD_BYTES)
#define PHASE_NS 5000000000ULL
static int control = -1;
static unsigned int backend;
static const char *case_name = "setup";
static atomic_uint live_workers;
static unsigned int cases;
static bool ready_emitted;

static void fail(const char *what)
{
	int error = errno;
	fprintf(stderr, "%s: %s: errno=%d (%s)\n", case_name, what, error, strerror(error));
	printf("{\"case\":\"%s\",\"passed\":false,\"joined\":%s,\"errno\":%d}\n",
	       case_name, atomic_load(&live_workers) ? "false" : "true", error);
	fflush(stdout);
	/* A failed timed join is never reported as drain. The controller retains
	 * provider state and must independently establish kernel quiescence. */
	exit(EXIT_FAILURE);
}
#define CHECK(test, what) do { if (!(test)) { errno = EPROTO; fail(what); } } while (0)
#define SYS_OK(test, what) do { if (!(test)) fail(what); } while (0)

static uint64_t now_ns(clockid_t clock)
{
	struct timespec ts;
	SYS_OK(clock_gettime(clock, &ts) == 0, "clock_gettime");
	return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}
static struct timespec timestamp(uint64_t ns)
{
	return (struct timespec){ .tv_sec = (time_t)(ns / 1000000000ULL),
		.tv_nsec = (long)(ns % 1000000000ULL) };
}
static void close_fd(int fd)
{
	SYS_OK(close(fd) == 0, "close");
}
static void open_control(void)
{
	control = open("/dev/kd_dev", O_RDONLY | O_CLOEXEC);
	SYS_OK(control >= 0, "read-only control open");
}
static void select_pipe(unsigned int selected)
{
	struct kd_api_select s = { .version = KD_API_VERSION, .pipes_budget = selected };
	SYS_OK(ioctl(control, KD_API_SELECT, &s) == 0, "pipe SELECT");
}
static void cancel(void)
{
	SYS_OK(ioctl(control, KD_API_CANCEL) == 0, "CANCEL");
}
static struct kd_api_query query(int fd, unsigned int expected)
{
	struct kd_api_query q = { .version = KD_API_VERSION, .fd = fd };
	SYS_OK(ioctl(control, KD_API_QUERY, &q) == 0, "pipe QUERY");
	CHECK(q.version == KD_API_VERSION && q.fd == fd && q.kind == KD_API_KIND_PIPE &&
	      q.backend == expected && q.object && q.lock &&
	      !!q.provider == (expected == KD_API_BACKEND_KD), "pipe identity/backend");
	for (unsigned int i = 0; i < KD_API_SITE_COUNT; ++i) {
		CHECK(q.entries[i] != 0, "entry identity missing");
		for (unsigned int j = 0; j < i; ++j)
			CHECK(q.entries[i] != q.entries[j], "duplicate entry identity");
	}
	return q;
}
static void same(int fd, const struct kd_api_query *expected)
{
	struct kd_api_query q = query(fd, expected->backend);
	q.fd = expected->fd;
	CHECK(memcmp(&q, expected, sizeof(q)) == 0, "same live pipe identity");
}
static void print_binding(const char *key, const struct kd_api_query *q)
{
	printf(",\"%s\":{\"version\":%u,\"kind\":%u,\"backend\":%u,\"object\":%llu,\"lock\":%llu,"
	       "\"provider\":%llu,\"entries\":[%llu,%llu,%llu]}", key, q->version, q->kind, q->backend,
	       (unsigned long long)q->object, (unsigned long long)q->lock,
	       (unsigned long long)q->provider, (unsigned long long)q->entries[0],
	       (unsigned long long)q->entries[1], (unsigned long long)q->entries[2]);
}
static void begin_receipt(void)
{
	CHECK(atomic_load(&live_workers) == 0, "unjoined worker at case completion");
	printf("{\"case\":\"%s\",\"passed\":true,\"joined\":true,\"backend\":%u",
	       case_name, backend);
}
static void end_receipt(void)
{
	puts("}");
	fflush(stdout);
	++cases;
}
struct pipe_object {
	int hold;
	struct kd_api_query id;
};
/* The first RDWR description keeps the FIFO object alive across independent
 * /proc reopens. Never use it in an EOF/EPIPE oracle: it owns both endpoints. */
static struct pipe_object raw_pipe(unsigned int expected)
{
	char dir[] = "/dev/shm/kdlock-object-pipe-XXXXXX", path[160];
	SYS_OK(mkdtemp(dir) != NULL, "mkdtemp");
	CHECK(snprintf(path, sizeof(path), "%s/fifo", dir) < (int)sizeof(path), "FIFO path");
	SYS_OK(mkfifo(path, 0600) == 0, "mkfifo");
	int fd = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
	SYS_OK(fd >= 0, "initial FIFO open");
	SYS_OK(unlink(path) == 0 && rmdir(dir) == 0, "remove FIFO name");
	return (struct pipe_object){ .hold = fd, .id = query(fd, expected) };
}
static struct pipe_object make_pipe(void)
{
	select_pipe(backend == KD_API_BACKEND_KD);
	struct pipe_object p = raw_pipe(backend);
	cancel();
	if (!ready_emitted) {
		printf("{\"ready\":true,\"pid\":%d,\"backend\":%u", getpid(), backend);
		print_binding("binding", &p.id);
		puts("}");
		fflush(stdout);
		ready_emitted = true;
	}
	return p;
}
static int reopen(const struct pipe_object *p, int mode)
{
	char path[96];
	CHECK(snprintf(path, sizeof(path), "/proc/self/fd/%d", p->hold) < (int)sizeof(path), "fd path");
	int fd = open(path, mode | O_NONBLOCK | O_CLOEXEC);
	SYS_OK(fd >= 0, "independent FIFO description");
	same(fd, &p->id);
	return fd;
}
static void bytes_equal(int fd, int expected)
{
	int value = -1;
	SYS_OK(ioctl(fd, FIONREAD, &value) == 0, "FIONREAD");
	CHECK(value == expected, "quiescent byte count");
}
static void capacity_equal(int fd, int expected)
{
	int value = fcntl(fd, F_GETPIPE_SZ);
	SYS_OK(value >= 0, "F_GETPIPE_SZ");
	CHECK(value == expected, "quiescent capacity");
}
static void set_capacity(int fd, int expected)
{
	int value = fcntl(fd, F_SETPIPE_SZ, expected);
	SYS_OK(value >= 0, "F_SETPIPE_SZ");
	CHECK(value == expected, "rounded capacity differs");
}
static void wait_io(int fd, short events, uint64_t deadline)
{
	for (;;) {
		uint64_t now = now_ns(CLOCK_MONOTONIC);
		if (now >= deadline) { errno = ETIMEDOUT; fail("I/O deadline"); }
		int ms = (int)((deadline - now + 999999ULL) / 1000000ULL);
		struct pollfd p = { .fd = fd, .events = events };
		int rc = poll(&p, 1, ms);
		if (rc < 0 && errno == EINTR) continue;
		SYS_OK(rc >= 0, "poll");
		if (!rc) { errno = ETIMEDOUT; fail("poll deadline"); }
		CHECK(!(p.revents & (POLLERR | POLLNVAL | POLLHUP)), "unexpected pipe endpoint loss");
		if (p.revents & events) return;
	}
}
static void write_record(int fd, const void *data, size_t size, uint64_t deadline)
{
	for (;;) {
		if (now_ns(CLOCK_MONOTONIC) >= deadline) { errno = ETIMEDOUT; fail("write deadline"); }
		ssize_t count = write(fd, data, size);
		if (count < 0 && errno == EINTR) continue;
		if (count < 0 && errno == EAGAIN) { wait_io(fd, POLLOUT, deadline); continue; }
		SYS_OK(count >= 0, "atomic record write");
		CHECK((size_t)count == size, "partial <=PIPE_BUF write");
		return;
	}
}
static void read_exact(int fd, void *data, size_t size, uint64_t deadline)
{
	size_t done = 0;
	while (done < size) {
		if (now_ns(CLOCK_MONOTONIC) >= deadline) { errno = ETIMEDOUT; fail("read deadline"); }
		ssize_t count = read(fd, (char *)data + done, size - done);
		if (count < 0 && errno == EINTR) continue;
		if (count < 0 && errno == EAGAIN) { wait_io(fd, POLLIN, deadline); continue; }
		SYS_OK(count >= 0, "read");
		CHECK(count > 0, "unexpected EOF");
		done += (size_t)count;
	}
}
static void fill_pages(int fd, unsigned int pages, unsigned char value, uint64_t deadline)
{
	unsigned char page[PAGE_BYTES];
	memset(page, value, sizeof(page));
	for (unsigned int i = 0; i < pages; ++i)
		write_record(fd, page, sizeof(page), deadline);
}
static void check_fill(const unsigned char *data, size_t size, unsigned char value)
{
	for (size_t i = 0; i < size; ++i) CHECK(data[i] == value, "pipe payload byte");
}
static void expect_errno(int result, int expected, const char *what)
{
	CHECK(result == -1 && errno == expected, what);
}
static void barrier_wait(pthread_barrier_t *barrier)
{
	int rc = pthread_barrier_wait(barrier);
	CHECK(rc == 0 || rc == PTHREAD_BARRIER_SERIAL_THREAD, "barrier wait");
}

enum role { WRITE_RECORDS, READ_RECORDS, QUERY_BYTES, QUERY_CAPACITY, RESIZE,
	BLOCK_READ, BLOCK_WRITE };
struct worker {
	enum role role;
	int fd, capacity;
	unsigned int index, operations;
	uint64_t deadline;
	pthread_barrier_t *barrier;
	struct kd_api_query id;
	unsigned char *buffer;
	size_t size;
	ssize_t result;
	atomic_int tid;
};
static void record(unsigned char *data, unsigned int writer, unsigned int sequence)
{
	uint32_t header[2] = { writer, sequence };
	memcpy(data, header, sizeof(header));
	for (unsigned int i = sizeof(header); i < RECORD_BYTES; ++i)
		data[i] = (unsigned char)(writer * 71U + sequence * 13U + i);
}
static void *worker_main(void *arg)
{
	struct worker *w = arg;
	SYS_OK(prctl(PR_SET_NAME, "sc_worker") == 0, "worker comm");
	same(w->fd, &w->id);
	atomic_store_explicit(&w->tid, (int)syscall(SYS_gettid), memory_order_release);
	if (w->barrier) barrier_wait(w->barrier);
	if (w->role == WRITE_RECORDS) {
		unsigned char data[RECORD_BYTES];
		for (unsigned int i = 0; i < RECORDS; ++i) {
			record(data, w->index, i);
			write_record(w->fd, data, sizeof(data), w->deadline);
			++w->operations;
		}
	} else if (w->role == READ_RECORDS) {
		read_exact(w->fd, w->buffer, w->size, w->deadline);
		w->operations = (unsigned int)(w->size / RECORD_BYTES);
	} else if (w->role == QUERY_BYTES || w->role == QUERY_CAPACITY) {
		unsigned int limit = w->capacity ? 512U : 256U;
		for (unsigned int i = 0; i < limit; ++i) {
			CHECK(now_ns(CLOCK_MONOTONIC) < w->deadline, "query deadline");
			if (w->role == QUERY_BYTES) {
				int bytes = -1;
				SYS_OK(ioctl(w->fd, FIONREAD, &bytes) == 0, "concurrent FIONREAD");
				CHECK(bytes >= 0 && bytes <= w->capacity, "concurrent byte range");
			} else {
				int size = fcntl(w->fd, F_GETPIPE_SZ);
				SYS_OK(size >= 0, "concurrent F_GETPIPE_SZ");
				CHECK(w->capacity ? size == w->capacity : (size == 8192 || size == 16384),
				      "concurrent capacity range");
			}
			++w->operations;
		}
	} else if (w->role == RESIZE) {
		for (unsigned int i = 0; i < 32; ++i) {
			CHECK(now_ns(CLOCK_MONOTONIC) < w->deadline, "resize deadline");
			set_capacity(w->fd, (i & 1) ? 8192 : 16384);
			++w->operations;
		}
	} else if (w->role == BLOCK_READ) {
		w->result = read(w->fd, w->buffer, w->size);
		SYS_OK(w->result >= 0, "blocking read");
		w->operations = 1;
	} else {
		CHECK(w->role == BLOCK_WRITE, "worker role");
		w->result = write(w->fd, w->buffer, w->size);
		SYS_OK(w->result >= 0, "blocking write");
		w->operations = 1;
	}
	same(w->fd, &w->id);
	return NULL;
}
static void start(pthread_t *thread, struct worker *w)
{
	atomic_init(&w->tid, 0);
	atomic_fetch_add(&live_workers, 1);
	int error = pthread_create(thread, NULL, worker_main, w);
	if (error) { atomic_fetch_sub(&live_workers, 1); errno = error; fail("pthread_create"); }
}
static void join(pthread_t thread, uint64_t deadline)
{
	uint64_t now = now_ns(CLOCK_MONOTONIC);
	if (now >= deadline) { errno = ETIMEDOUT; fail("join deadline"); }
	struct timespec until = timestamp(now_ns(CLOCK_REALTIME) + deadline - now);
	int error = pthread_timedjoin_np(thread, NULL, &until);
	if (error) { errno = error; fail("pthread_timedjoin_np"); }
	atomic_fetch_sub(&live_workers, 1);
}
static void make_blocking(int fd)
{
	int flags = fcntl(fd, F_GETFL);
	SYS_OK(flags >= 0 && fcntl(fd, F_SETFL, flags & ~O_NONBLOCK) == 0, "blocking description");
}
static void poll_ready(int fd, short events, bool expected)
{
	struct pollfd p = { .fd = fd, .events = events };
	SYS_OK(poll(&p, 1, 0) >= 0, "readiness snapshot");
	CHECK(!!(p.revents & events) == expected && !(p.revents & POLLNVAL), "quiescent readiness");
}
static bool syscall_matches(int tid, long call, int fd, const void *buffer, size_t size)
{
	char path[128], line[512];
	CHECK(snprintf(path, sizeof(path), "/proc/self/task/%d/syscall", tid) < (int)sizeof(path), "syscall path");
	FILE *file = fopen(path, "re");
	SYS_OK(file != NULL, "syscall observation open");
	bool got = fgets(line, sizeof(line), file) != NULL;
	SYS_OK(fclose(file) == 0, "syscall observation close");
	long number;
	unsigned long a0, a1, a2;
	return got && sscanf(line, "%ld %lx %lx %lx", &number, &a0, &a1, &a2) == 4 &&
		number == call && a0 == (unsigned long)fd && a1 == (unsigned long)buffer && a2 == size;
}
static bool sleeping(int tid)
{
	char path[128], line[1024];
	CHECK(snprintf(path, sizeof(path), "/proc/self/task/%d/stat", tid) < (int)sizeof(path), "stat path");
	FILE *file = fopen(path, "re");
	SYS_OK(file != NULL, "stat observation open");
	bool got = fgets(line, sizeof(line), file) != NULL;
	SYS_OK(fclose(file) == 0, "stat observation close");
	char *end = got ? strrchr(line, ')') : NULL;
	return end && end[1] == ' ' && end[2] == 'S';
}
static int observe_blocked(struct worker *w, long call)
{
	uint64_t deadline = now_ns(CLOCK_MONOTONIC) + 1000000000ULL;
	while (now_ns(CLOCK_MONOTONIC) < deadline) {
		int tid = atomic_load_explicit(&w->tid, memory_order_acquire);
		if (tid && syscall_matches(tid, call, w->fd, w->buffer, w->size) && sleeping(tid) &&
		    syscall_matches(tid, call, w->fd, w->buffer, w->size)) return tid;
		struct timespec delay = { .tv_nsec = 1000000 };
		nanosleep(&delay, NULL);
	}
	errno = ETIMEDOUT;
	fail("no bracketed sleeping syscall observed");
	return 0;
}

static void mixed_io(void)
{
	case_name = "mixed_io";
	struct pipe_object p = make_pipe();
	set_capacity(p.hold, 16384);
	unsigned char data[DATA_BYTES];
	struct worker workers[7] = {0};
	pthread_t threads[7];
	pthread_barrier_t barrier;
	CHECK(pthread_barrier_init(&barrier, NULL, 8) == 0, "mixed barrier init");
	uint64_t deadline = now_ns(CLOCK_MONOTONIC) + PHASE_NS;
	for (unsigned int i = 0; i < 7; ++i) {
		enum role role = i < 2 ? WRITE_RECORDS : i == 2 ? READ_RECORDS :
			(i < 5 ? QUERY_BYTES : QUERY_CAPACITY);
		workers[i] = (struct worker){ .role = role, .index = i,
			.fd = reopen(&p, i < 2 ? O_WRONLY : O_RDONLY), .capacity = 16384,
			.deadline = deadline, .barrier = &barrier, .id = p.id,
			.buffer = data, .size = sizeof(data) };
		start(&threads[i], &workers[i]);
	}
	barrier_wait(&barrier);
	for (unsigned int i = 0; i < 7; ++i) {
		join(threads[i], deadline);
		CHECK(workers[i].operations == (i < 2 ? RECORDS : 512U), "mixed exact operation count");
		close_fd(workers[i].fd);
	}
	CHECK(pthread_barrier_destroy(&barrier) == 0, "mixed barrier destroy");
	unsigned int next[2] = {0};
	for (unsigned int i = 0; i < 2U * RECORDS; ++i) {
		uint32_t header[2];
		unsigned char expected[RECORD_BYTES];
		memcpy(header, data + i * RECORD_BYTES, sizeof(header));
		CHECK(header[0] < 2 && header[1] == next[header[0]]++, "record identity/order");
		record(expected, header[0], header[1]);
		CHECK(memcmp(data + i * RECORD_BYTES, expected, sizeof(expected)) == 0, "atomic record payload");
	}
	CHECK(next[0] == RECORDS && next[1] == RECORDS, "record conservation");
	bytes_equal(p.hold, 0); capacity_equal(p.hold, 16384); same(p.hold, &p.id);
	close_fd(p.hold);
	begin_receipt(); print_binding("binding", &p.id);
	printf(",\"workers_started\":7,\"workers_joined\":7,\"records_written\":512,"
	       "\"records_read\":512,\"bytes\":32768,\"byte_queries\":1024,\"capacity_queries\":1024");
	end_receipt();
}
static void resize_case(void)
{
	case_name = "resize";
	struct pipe_object p = make_pipe();
	set_capacity(p.hold, 8192);
	uint64_t deadline = now_ns(CLOCK_MONOTONIC) + PHASE_NS;
	fill_pages(p.hold, 2, 0x5a, deadline);
	errno = 0;
	expect_errno(fcntl(p.hold, F_SETPIPE_SZ, 4096), EBUSY, "occupied shrink EBUSY");
	bytes_equal(p.hold, 8192); capacity_equal(p.hold, 8192);
	unsigned char data[8192];
	read_exact(p.hold, data, sizeof(data), deadline); check_fill(data, sizeof(data), 0x5a);
	struct worker workers[3] = {0};
	pthread_t threads[3];
	pthread_barrier_t barrier;
	CHECK(pthread_barrier_init(&barrier, NULL, 4) == 0, "resize barrier init");
	for (unsigned int i = 0; i < 3; ++i) {
		workers[i] = (struct worker){ .role = i ? QUERY_CAPACITY : RESIZE,
			.fd = reopen(&p, O_RDONLY), .deadline = deadline, .barrier = &barrier, .id = p.id };
		start(&threads[i], &workers[i]);
	}
	barrier_wait(&barrier);
	for (unsigned int i = 0; i < 3; ++i) {
		join(threads[i], deadline);
		CHECK(workers[i].operations == (i ? 256U : 32U), "resize operation count");
		close_fd(workers[i].fd);
	}
	CHECK(pthread_barrier_destroy(&barrier) == 0, "resize barrier destroy");
	bytes_equal(p.hold, 0); capacity_equal(p.hold, 8192); same(p.hold, &p.id); close_fd(p.hold);
	begin_receipt(); print_binding("binding", &p.id);
	printf(",\"workers_started\":3,\"workers_joined\":3,\"resizes\":32,"
	       "\"capacity_queries\":512,\"occupied_shrink_errno\":%d,\"preserved_bytes\":8192", EBUSY);
	end_receipt();
}
static void error_recovery(void)
{
	case_name = "error_recovery";
	struct pipe_object p = make_pipe();
	set_capacity(p.hold, 8192);
	unsigned char data[RECORD_BYTES], got[RECORD_BYTES];
	record(data, 0, 0);
	uint64_t deadline = now_ns(CLOCK_MONOTONIC) + PHASE_NS;
	write_record(p.hold, data, sizeof(data), deadline);
	void *inaccessible = mmap(NULL, PAGE_BYTES, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	SYS_OK(inaccessible != MAP_FAILED, "inaccessible output page");
	errno = 0;
	expect_errno(ioctl(p.hold, FIONREAD, inaccessible), EFAULT, "FIONREAD EFAULT");
	bytes_equal(p.hold, RECORD_BYTES); capacity_equal(p.hold, 8192);
	errno = 0;
	expect_errno(ioctl(p.hold, _IO('z', 0x7f), 0), ENOTTY, "unsupported ioctl ENOTTY");
	bytes_equal(p.hold, RECORD_BYTES); capacity_equal(p.hold, 8192);
	read_exact(p.hold, got, sizeof(got), deadline);
	CHECK(memcmp(data, got, sizeof(got)) == 0, "error recovery data");
	SYS_OK(munmap(inaccessible, PAGE_BYTES) == 0, "unmap inaccessible output");
	bytes_equal(p.hold, 0); same(p.hold, &p.id); close_fd(p.hold);
	begin_receipt(); print_binding("binding", &p.id);
	printf(",\"fault_errno\":%d,\"unsupported_errno\":%d,\"recovery_queries\":4,\"preserved_bytes\":64", EFAULT, ENOTTY);
	end_receipt();
}
static void wake_case(bool writer)
{
	case_name = writer ? "writer_wake" : "reader_wake";
	struct pipe_object p = make_pipe();
	set_capacity(p.hold, 8192);
	int rd = reopen(&p, O_RDONLY), wr = reopen(&p, O_WRONLY);
	close_fd(p.hold);
	uint64_t deadline = now_ns(CLOCK_MONOTONIC) + PHASE_NS;
	unsigned char data[PAGE_BYTES], got[8192];
	memset(data, writer ? 0x42 : 0x17, sizeof(data));
	if (writer) {
		fill_pages(wr, 2, 0x41, deadline);
		errno = 0;
		expect_errno((int)write(wr, data, sizeof(data)), EAGAIN, "full nonblocking pipe");
		poll_ready(wr, POLLOUT, false);
	} else {
		bytes_equal(rd, 0); poll_ready(rd, POLLIN, false);
	}
	make_blocking(writer ? wr : rd);
	struct worker w = { .role = writer ? BLOCK_WRITE : BLOCK_READ, .fd = writer ? wr : rd,
		.id = p.id, .buffer = data, .size = writer ? sizeof(data) : RECORD_BYTES, .deadline = deadline };
	pthread_t thread;
	start(&thread, &w);
	int tid = observe_blocked(&w, writer ? SYS_write : SYS_read);
	if (writer) {
		read_exact(rd, got, PAGE_BYTES, deadline); check_fill(got, PAGE_BYTES, 0x41);
	} else {
		unsigned char expected[RECORD_BYTES];
		memset(expected, 0x43, sizeof(expected));
		write_record(wr, expected, sizeof(expected), deadline);
	}
	join(thread, deadline);
	CHECK(w.result == (ssize_t)w.size && w.operations == 1, "woken exact operation");
	if (writer) {
		bytes_equal(rd, 8192); poll_ready(rd, POLLIN, true);
		read_exact(rd, got, sizeof(got), deadline);
		check_fill(got, PAGE_BYTES, 0x41); check_fill(got + PAGE_BYTES, PAGE_BYTES, 0x42);
		poll_ready(wr, POLLOUT, true);
	} else {
		check_fill(data, RECORD_BYTES, 0x43); bytes_equal(rd, 0);
	}
	same(rd, &p.id); same(wr, &p.id); close_fd(rd); close_fd(wr);
	begin_receipt(); print_binding("binding", &p.id);
	printf(",\"workers_started\":1,\"workers_joined\":1,\"sleeping_tid\":%d,"
	       "\"observed_syscall\":%ld,\"syscall_state_syscall_bracket\":true,\"completed_bytes\":%zu",
	       tid, (long)(writer ? SYS_write : SYS_read), w.size);
	end_receipt();
}
static void endpoint_release(void)
{
	case_name = "endpoint_release";
	struct pipe_object p = make_pipe();
	int rd = reopen(&p, O_RDONLY), wr = reopen(&p, O_WRONLY);
	close_fd(p.hold);
	unsigned char data[RECORD_BYTES], got[RECORD_BYTES];
	record(data, 1, 4);
	uint64_t deadline = now_ns(CLOCK_MONOTONIC) + PHASE_NS;
	write_record(wr, data, sizeof(data), deadline); close_fd(wr);
	read_exact(rd, got, sizeof(got), deadline);
	CHECK(memcmp(data, got, sizeof(data)) == 0, "EOF buffered data");
	CHECK(read(rd, got, sizeof(got)) == 0, "EOF after final writer close");
	same(rd, &p.id); close_fd(rd);
	struct pipe_object q = make_pipe();
	rd = reopen(&q, O_RDONLY); wr = reopen(&q, O_WRONLY);
	close_fd(q.hold); close_fd(rd);
	sigset_t blocked, old, pending;
	SYS_OK(sigemptyset(&blocked) == 0 && sigaddset(&blocked, SIGPIPE) == 0, "SIGPIPE set");
	CHECK(pthread_sigmask(SIG_BLOCK, &blocked, &old) == 0, "block SIGPIPE");
	SYS_OK(sigpending(&pending) == 0, "pending signal before write");
	CHECK(sigismember(&pending, SIGPIPE) == 0, "preexisting SIGPIPE");
	errno = 0;
	expect_errno((int)write(wr, data, sizeof(data)), EPIPE, "write without readers");
	struct timespec zero = {0};
	CHECK(sigtimedwait(&blocked, NULL, &zero) == SIGPIPE, "generated SIGPIPE");
	CHECK(pthread_sigmask(SIG_SETMASK, &old, NULL) == 0, "restore signal mask");
	same(wr, &q.id); close_fd(wr);
	begin_receipt(); print_binding("eof_binding", &p.id); print_binding("epipe_binding", &q.id);
	printf(",\"buffered_bytes_before_eof\":64,\"eof_returns\":1,\"epipe_errno\":%d,\"sigpipe_consumed\":1", EPIPE);
	end_receipt();
}
static void selector_errors(void)
{
	case_name = "selector_errors";
	struct pipe_object p = make_pipe();
	struct kd_api_select bad[4] = {
		{ .version = KD_API_VERSION + 1 }, { .version = KD_API_VERSION, .reserved = 1 },
		{ .version = KD_API_VERSION, .files_budget = 2 }, { .version = KD_API_VERSION, .pipes_budget = 2 }
	};
	for (unsigned int i = 0; i < 4; ++i) {
		errno = 0; expect_errno(ioctl(control, KD_API_SELECT, &bad[i]), EINVAL, "invalid SELECT");
	}
	/* This setup-only arm is deliberate even for a Native target object. No
	 * new object is created before CANCEL, so its backend remains Native. */
	select_pipe(1);
	struct kd_api_select armed = { .version = KD_API_VERSION, .pipes_budget = 1 };
	errno = 0; expect_errno(ioctl(control, KD_API_SELECT, &armed), EBUSY, "duplicate SELECT");
	armed.pipes_budget = 0;
	errno = 0; expect_errno(ioctl(control, KD_API_SELECT, &armed), EBUSY, "Native SELECT with pending selector");
	cancel(); cancel();
	struct kd_api_query invalid = { .version = KD_API_VERSION + 1, .fd = p.hold };
	errno = 0; expect_errno(ioctl(control, KD_API_QUERY, &invalid), EINVAL, "QUERY version");
	invalid.version = KD_API_VERSION; invalid.fd = -2;
	errno = 0; expect_errno(ioctl(control, KD_API_QUERY, &invalid), EINVAL, "QUERY negative fd");
	int regular = memfd_create("kd-api-not-pipe", MFD_CLOEXEC);
	SYS_OK(regular >= 0, "regular memfd");
	int closed = fcntl(regular, F_DUPFD_CLOEXEC, 256);
	SYS_OK(closed >= 0, "closed QUERY fd"); close_fd(closed);
	invalid.fd = closed;
	errno = 0; expect_errno(ioctl(control, KD_API_QUERY, &invalid), EBADF, "QUERY closed fd");
	invalid.fd = regular;
	errno = 0; expect_errno(ioctl(control, KD_API_QUERY, &invalid), EINVAL, "QUERY non-pipe");
	close_fd(regular);
	unsigned char data[RECORD_BYTES], got[RECORD_BYTES];
	record(data, 0, 9);
	uint64_t deadline = now_ns(CLOCK_MONOTONIC) + PHASE_NS;
	write_record(p.hold, data, sizeof(data), deadline); read_exact(p.hold, got, sizeof(got), deadline);
	CHECK(memcmp(data, got, sizeof(data)) == 0, "selector error recovery");
	bytes_equal(p.hold, 0); same(p.hold, &p.id); close_fd(p.hold);
	begin_receipt(); print_binding("binding", &p.id);
	printf(",\"invalid_selects\":4,\"busy_selects\":2,\"invalid_queries\":4,"
	       "\"cancels\":2,\"setup_only_kd_selector\":true,\"recovery_bytes\":64");
	end_receipt();
}
static void selector_lifetime(void)
{
	case_name = "selector_lifetime";
	select_pipe(backend == KD_API_BACKEND_KD);
	struct pipe_object first = raw_pipe(backend), second = raw_pipe(KD_API_BACKEND_NATIVE);
	CHECK(first.id.object != second.id.object && first.id.lock != second.id.lock,
	      "distinct concurrently retained pipes");
	cancel(); same(first.hold, &first.id); same(second.hold, &second.id);
	close_fd(first.hold); close_fd(second.hold);
	select_pipe(backend == KD_API_BACKEND_KD); cancel();
	struct pipe_object cancelled = raw_pipe(KD_API_BACKEND_NATIVE);
	same(cancelled.hold, &cancelled.id); close_fd(cancelled.hold);
	select_pipe(backend == KD_API_BACKEND_KD);
	int duplicate = fcntl(control, F_DUPFD_CLOEXEC, 0);
	SYS_OK(duplicate >= 0, "duplicate control token");
	close_fd(control); control = duplicate;
	struct pipe_object retained = raw_pipe(backend);
	cancel(); same(retained.hold, &retained.id); close_fd(retained.hold);
	select_pipe(backend == KD_API_BACKEND_KD);
	close_fd(control); control = -1;
	open_control();
	struct pipe_object released = raw_pipe(KD_API_BACKEND_NATIVE);
	same(released.hold, &released.id); close_fd(released.hold); cancel();
	begin_receipt(); print_binding("first_binding", &first.id); print_binding("second_binding", &second.id);
	print_binding("cancelled_binding", &cancelled.id); print_binding("duplicate_token_binding", &retained.id);
	print_binding("last_close_binding", &released.id);
	printf(",\"objects_created\":5,\"objects_closed\":5,\"selected_budget\":%u,\"token_final_release_checked\":true",
	       (unsigned int)(backend == KD_API_BACKEND_KD));
	end_receipt();
}
int main(int argc, char **argv)
{
	if (argc != 2 || (strcmp(argv[1], "native") && strcmp(argv[1], "kd"))) return 2;
	backend = !strcmp(argv[1], "kd") ? KD_API_BACKEND_KD : KD_API_BACKEND_NATIVE;
	CHECK(sysconf(_SC_PAGESIZE) == PAGE_BYTES, "4096-byte page prerequisite");
	SYS_OK(prctl(PR_SET_NAME, "sc_worker") == 0, "main comm");
	open_control();
	mixed_io(); resize_case(); error_recovery(); wake_case(false); wake_case(true);
	endpoint_release(); selector_errors(); selector_lifetime();
	cancel(); close_fd(control); control = -1;
	CHECK(cases == 8 && atomic_load(&live_workers) == 0, "final case/join conservation");
	printf("{\"done\":true,\"passed\":true,\"joined\":true,\"cases\":%u,\"backend\":%u,\"control_closed\":true}\n",
	       cases, backend);
	fflush(stdout);
	return 0;
}
