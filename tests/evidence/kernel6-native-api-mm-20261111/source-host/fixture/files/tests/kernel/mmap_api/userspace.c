// SPDX-License-Identifier: GPL-2.0-only
/* Actual userspace mmap/munmap effects, independent of lock/JIT observations.
 * The explicit deadline is checked between bounded userspace phases. An in-flight
 * syscall must return before cleanup; an outer observer must not infer drain from
 * a timeout. No signal, cancellation or extracted-body call completes MM work.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "abi.h"

#ifndef MAP_FIXED_NOREPLACE
#error "Linux MAP_FIXED_NOREPLACE headers are required"
#endif

struct control {
	const char *path;
	uint64_t capacity;
	bool quiescent, started, cleanup_required, cleanup_failed;
	int fd, open_errno, start_errno, end_errno, query_errno, close_errno, wait_errno;
	uint64_t end_attempts;
	struct kd_mmap_api_status start, final;
	sigset_t original_mask, wait_mask;
};

static volatile sig_atomic_t retry_end;
static bool now_ns(uint64_t *value);
static void print_gate_status(const struct kd_mmap_api_status *status);

static int unjoined_failure(struct control *control, const char *operation, int error)
{
	fprintf(stderr, "%s failed: %s; drain unverified\n", operation, strerror(error));
	if (!control->started)
		return 1;
	printf("{\"schema\":1,\"phase\":\"worker_drain_unverified\",\"pid\":%ld,"
	       "\"tid\":%ld,\"errno\":%d,\"cleanup_required\":true}\n",
	       (long)getpid(), (long)syscall(SYS_gettid), error);
	fflush(stdout);
	/* The END precondition is not established. Preserve the original owner,
	 * workers and fd for inspection rather than exiting or attempting END.
	 */
	for (;;) {
		sigsuspend(&control->wait_mask);
		retry_end = 0;
	}
}

static void request_retry(int signal_number)
{
	(void)signal_number;
	retry_end = 1;
}

static bool retry_signal(struct control *control)
{
	struct sigaction action = { .sa_handler = request_retry };
	sigset_t blocked;
	int result;
	sigemptyset(&action.sa_mask);
	if (sigaction(SIGUSR1, &action, NULL))
		return false;
	sigemptyset(&blocked);
	sigaddset(&blocked, SIGUSR1);
	result = pthread_sigmask(SIG_BLOCK, &blocked, &control->original_mask);
	if (result) {
		errno = result;
		return false;
	}
	control->wait_mask = control->original_mask;
	sigdelset(&control->wait_mask, SIGUSR1);
	return true;
}

static bool query_control(struct control *control)
{
	struct kd_mmap_api_request request = { .abi = KD_MMAP_API_ABI };
	if (ioctl(control->fd, KD_MMAP_API_QUERY, &request)) {
		control->query_errno = errno;
		control->cleanup_required = true;
		return false;
	}
	if (request.abi != KD_MMAP_API_ABI || request.status.state > KD_MMAP_API_RETIRED) {
		control->query_errno = EPROTO;
		control->cleanup_required = true;
		return false;
	}
	control->query_errno = 0;
	control->final = request.status;
	control->cleanup_required = request.status.cleanup_required != 0 ||
		request.status.state == KD_MMAP_API_SELECTED;
	return true;
}

static bool start_control(struct control *control)
{
	struct kd_mmap_api_request request = { .abi = KD_MMAP_API_ABI,
		.native_capacity = control->capacity,
		.contract_flags = KD_MMAP_API_QUIESCENT_CHANGE };
	control->fd = open(control->path, O_RDWR | O_CLOEXEC);
	if (control->fd < 0) {
		control->open_errno = errno;
		return false;
	}
	if (ioctl(control->fd, KD_MMAP_API_START, &request)) {
		control->start_errno = errno;
		query_control(control);
		return false;
	}
	control->start = request.status;
	if (request.abi != KD_MMAP_API_ABI || request.status.state != KD_MMAP_API_SELECTED ||
	    !request.status.owner_is_current || request.status.source_calls ||
	    request.status.native_capacity != control->capacity ||
	    !request.status.mm_identity || !request.status.object_identity ||
	    !request.status.gate_identity) {
		control->start_errno = EPROTO;
		query_control(control);
		return false;
	}
	control->started = true;
	control->cleanup_required = true;
	control->final = request.status;
	return true;
}

static bool single_owner(struct control *control, uint64_t deadline_ns)
{
	uint64_t current_ns;
	control->wait_errno = 0;
	for (;;) {
		if (!query_control(control))
			return false;
		if (!control->cleanup_required || !control->final.owner_is_current ||
		    control->final.owner_threads == 1)
			return true;
		if (!now_ns(&current_ns)) {
			control->wait_errno = errno;
			return false;
		}
		if (current_ns >= deadline_ns) {
			control->wait_errno = EBUSY;
			return false;
		}
		if (sched_yield()) {
			control->wait_errno = errno;
			return false;
		}
	}
}

static void finish_control(struct control *control, uint64_t deadline_ns)
{
	if (control->fd < 0)
		return;
	if (!control->started)
		query_control(control);
	while (control->cleanup_required &&
	       (control->started || control->query_errno || control->final.owner_is_current)) {
		struct kd_mmap_api_request request = { .abi = KD_MMAP_API_ABI,
			.contract_flags = KD_MMAP_API_QUIESCENT_CHANGE };
		if (single_owner(control, deadline_ns)) {
			if (!control->cleanup_required || !control->final.owner_is_current)
				break;
			control->end_attempts++;
			if (ioctl(control->fd, KD_MMAP_API_END, &request))
				control->end_errno = errno;
			else
				control->end_errno = 0;
			/* A failed output copy does not undo END. Reconcile metadata. */
			if (query_control(control) && !control->cleanup_required)
				break;
		}
		control->cleanup_failed = true;
		if (!control->started && !control->query_errno && !control->final.owner_is_current)
			break;
		printf("{\"schema\":1,\"phase\":\"control_cleanup_required\",\"pid\":%ld,"
		       "\"tid\":%ld,\"end_attempts\":%" PRIu64 ",\"end_errno\":%d,"
		       "\"query_errno\":%d,\"wait_errno\":%d,\"owner_threads\":%" PRIu64 ","
		       "\"cleanup_required\":true,\"retry_signal\":\"SIGUSR1\",\"selected_gate\":",
		       (long)getpid(), (long)syscall(SYS_gettid), control->end_attempts,
		       control->end_errno, control->query_errno, control->wait_errno,
		       (uint64_t)control->final.owner_threads);
		print_gate_status(&control->final);
		puts("}");
		fflush(stdout);
		/* Only the handler's flag changes in signal context. The original owner
		 * keeps its mm/fd alive; every explicit retry runs END here, never MM.
		 */
		while (!retry_end)
			sigsuspend(&control->wait_mask);
		retry_end = 0;
	}
	if (close(control->fd))
		control->close_errno = errno;
	control->fd = -1;
	pthread_sigmask(SIG_SETMASK, &control->original_mask, NULL);
}

static void print_gate_status(const struct kd_mmap_api_status *status)
{
	printf("{\"state\":%" PRIu64, (uint64_t)status->state);
#define GATE_FIELD(field) printf(",\"" #field "\":%" PRIu64, (uint64_t)status->field)
	GATE_FIELD(cleanup_required); GATE_FIELD(native_capacity); GATE_FIELD(record_bytes);
	GATE_FIELD(owner_pid); GATE_FIELD(owner_tgid); GATE_FIELD(owner_is_current);
	GATE_FIELD(owner_threads);
	GATE_FIELD(mm_identity); GATE_FIELD(object_identity); GATE_FIELD(gate_identity);
	GATE_FIELD(source_calls); GATE_FIELD(pool_idle); GATE_FIELD(gate_locked);
	GATE_FIELD(gate_write_locked); GATE_FIELD(gate_contended);
	GATE_FIELD(native_read_acquires); GATE_FIELD(native_read_releases);
	GATE_FIELD(native_write_acquires); GATE_FIELD(native_write_releases);
	GATE_FIELD(native_downgrades); GATE_FIELD(native_cancels); GATE_FIELD(native_try_misses);
	GATE_FIELD(queue_enqueues); GATE_FIELD(local_selections);
	GATE_FIELD(physical_begins); GATE_FIELD(physical_ends); GATE_FIELD(jit_entries);
	GATE_FIELD(jit_observation_available);
	GATE_FIELD(observed_events); GATE_FIELD(count_overflow);
#undef GATE_FIELD
	putchar('}');
}

static bool balanced_native_counts(const struct kd_mmap_api_status *status)
{
	if (status->count_overflow ||
	    status->native_write_releases > UINT64_MAX - status->native_downgrades ||
	    status->native_read_acquires > UINT64_MAX - status->native_downgrades)
		return false;
	return status->native_write_acquires == status->native_write_releases + status->native_downgrades &&
		status->native_read_releases == status->native_read_acquires + status->native_downgrades;
}

struct group {
	pthread_mutex_t mutex;
	pthread_cond_t condition;
	atomic_bool stop;
	bool start;
	bool abort;
	uint64_t iterations;
	uint64_t deadline_ns;
	size_t page_bytes;
};

struct worker {
	struct group *group;
	pthread_t thread;
	unsigned char *slot;
	uint64_t id;
	long tid;
	uint64_t completed;
	uint64_t mmap_attempts, mmap_successes;
	uint64_t munmap_attempts, munmap_successes;
	uint64_t mincore_attempts, hole_checks;
	uint64_t zero_bytes, written_bytes, checked_bytes;
	uint64_t reuse_successes;
	uint64_t error_iteration;
	size_t error_offset;
	const char *error;
	int error_number;
	bool deadline_reached;
};

static bool now_ns(uint64_t *value)
{
	struct timespec time;
	if (clock_gettime(CLOCK_MONOTONIC, &time))
		return false;
	if (time.tv_sec < 0 || (uint64_t)time.tv_sec >
	    (UINT64_MAX - (uint64_t)time.tv_nsec) / UINT64_C(1000000000)) {
		errno = EOVERFLOW;
		return false;
	}
	*value = (uint64_t)time.tv_sec * UINT64_C(1000000000) + time.tv_nsec;
	return true;
}

static void fail(struct worker *worker, const char *operation, int error,
		 uint64_t iteration, size_t offset)
{
	if (!worker->error) {
		worker->error = operation;
		worker->error_number = error;
		worker->error_iteration = iteration;
		worker->error_offset = offset;
	}
	atomic_store_explicit(&worker->group->stop, true, memory_order_relaxed);
}

static bool deadline(struct worker *worker, uint64_t iteration)
{
	uint64_t value;
	if (!now_ns(&value)) {
		fail(worker, "clock_gettime", errno, iteration, 0);
		return true;
	}
	if (value < worker->group->deadline_ns)
		return false;
	worker->deadline_reached = true;
	atomic_store_explicit(&worker->group->stop, true, memory_order_relaxed);
	return true;
}

static unsigned char pattern(uint64_t worker, uint64_t iteration,
			     unsigned int phase, size_t offset)
{
	/* Both pages and reuse phases have reproducible, nonconstant contents. */
	return (unsigned char)(worker * 37 + iteration * 19 + phase * 71 +
			       offset * 13 + (offset >> 8));
}

static bool contents(struct worker *worker, uint64_t iteration,
		     unsigned int phase)
{
	volatile unsigned char *bytes = worker->slot;
	size_t length = 2 * worker->group->page_bytes;
	size_t offset;

	for (offset = 0; offset < length; ++offset) {
		unsigned char value = bytes[offset];
		worker->zero_bytes++;
		if (value) {
			fail(worker, "fresh_anonymous_bytes", 0, iteration, offset);
			return false;
		}
	}
	for (offset = 0; offset < length; ++offset) {
		bytes[offset] = pattern(worker->id, iteration, phase, offset);
		worker->written_bytes++;
	}
	for (offset = 0; offset < length; ++offset) {
		unsigned char value = bytes[offset];
		worker->checked_bytes++;
		if (value != pattern(worker->id, iteration, phase, offset)) {
			fail(worker, "written_bytes_readback", 0, iteration, offset);
			return false;
		}
	}
	return true;
}

static bool map_slot(struct worker *worker, uint64_t iteration, int protection,
		     int placement)
{
	size_t length = 2 * worker->group->page_bytes;
	void *mapped;

	worker->mmap_attempts++;
	mapped = (void *)syscall(SYS_mmap, worker->slot, length, protection,
				MAP_PRIVATE | MAP_ANONYMOUS | placement, -1, 0);
	if (mapped == MAP_FAILED) {
		fail(worker, "mmap", errno, iteration, 0);
		return false;
	}
	worker->mmap_successes++;
	if (mapped != worker->slot) {
		/* A kernel ignoring NOREPLACE must not count another address as reuse. */
		worker->munmap_attempts++;
		if (!syscall(SYS_munmap, mapped, length))
			worker->munmap_successes++;
		fail(worker, "mmap_exact_address", 0, iteration, 0);
		return false;
	}
	return true;
}

static bool unmap_slot(struct worker *worker, uint64_t iteration)
{
	worker->munmap_attempts++;
	if (syscall(SYS_munmap, worker->slot, 2 * worker->group->page_bytes)) {
		fail(worker, "munmap", errno, iteration, 0);
		return false;
	}
	worker->munmap_successes++;
	return true;
}

static bool hole(struct worker *worker, uint64_t iteration)
{
	size_t page;
	for (page = 0; page < 2; ++page) {
		unsigned char vector = 0;
		long result;
		int error;
		worker->mincore_attempts++;
		errno = 0;
		result = syscall(SYS_mincore, worker->slot + page * worker->group->page_bytes,
				 worker->group->page_bytes, &vector);
		error = errno;
		if (result != -1 || error != ENOMEM) {
			fail(worker, "unmapped_page_mincore", error, iteration, page);
			return false;
		}
		worker->hole_checks++;
	}
	return true;
}

static void *run_worker(void *argument)
{
	struct worker *worker = argument;
	struct group *group = worker->group;
	uint64_t iteration;
	int result;

	worker->tid = syscall(SYS_gettid);
	if (worker->tid <= 0)
		fail(worker, "gettid", errno, 0, 0);
	result = pthread_mutex_lock(&group->mutex);
	if (result) {
		fail(worker, "pthread_mutex_lock", result, 0, 0);
		return NULL;
	}
	while (!group->start) {
		result = pthread_cond_wait(&group->condition, &group->mutex);
		if (result) {
			fail(worker, "pthread_cond_wait", result, 0, 0);
			break;
		}
	}
	result = pthread_mutex_unlock(&group->mutex);
	if (result)
		fail(worker, "pthread_mutex_unlock", result, 0, 0);
	if (group->abort || worker->error)
		return NULL;

	for (iteration = 0; iteration < group->iterations; ++iteration) {
		bool mapped = false;
		if (atomic_load_explicit(&group->stop, memory_order_relaxed) ||
		    deadline(worker, iteration))
			break;
		/* MAP_FIXED only replaces this worker's still-owned PROT_NONE slot.
		 * All workers were created before start; no worker allocates other
		 * addresses, frees another slot or performs a body through an ioctl.
		 */
		if (!map_slot(worker, iteration, PROT_READ | PROT_WRITE, MAP_FIXED))
			break;
		mapped = true;
		if (!contents(worker, iteration, 0) || deadline(worker, iteration))
			goto finish_mapping;
		if (!unmap_slot(worker, iteration))
			break;
		mapped = false;
		if (!hole(worker, iteration))
			break;
		if (!map_slot(worker, iteration, PROT_READ | PROT_WRITE, MAP_FIXED_NOREPLACE))
			break;
		mapped = true;
		worker->reuse_successes++;
		if (!contents(worker, iteration, 1) || deadline(worker, iteration))
			goto finish_mapping;
		if (!unmap_slot(worker, iteration))
			break;
		mapped = false;
		if (!hole(worker, iteration))
			break;
		/* Close the hole before the next iteration. No replacement can hide
		 * an unexpected mapping in a slot which was checked as unmapped.
		 */
		if (!map_slot(worker, iteration, PROT_NONE, MAP_FIXED_NOREPLACE))
			break;
		worker->completed++;
		continue;
finish_mapping:
		if (mapped)
			unmap_slot(worker, iteration);
		break;
	}
	return NULL;
}

static bool number(const char *text, uint64_t *value)
{
	char *end;
	unsigned long long parsed;
	const char *cursor;
	if (!*text)
		return false;
	for (cursor = text; *cursor; ++cursor)
		if (*cursor < '0' || *cursor > '9')
			return false;
	errno = 0;
	parsed = strtoull(text, &end, 10);
	if (errno || *end || !parsed)
		return false;
	*value = parsed;
	return true;
}

int main(int argc, char **argv)
{
	struct group group = { .mutex = PTHREAD_MUTEX_INITIALIZER,
		.condition = PTHREAD_COND_INITIALIZER };
	struct worker *workers;
	struct control control = { .fd = -1 };
	uint64_t count = 0, iterations = 0, milliseconds = 0, start = 0, end = 0;
	uint64_t completed = 0, errors = 0;
	size_t arena_length, stride, created = 0, index;
	unsigned char *arena;
	long page;
	const char *setup_error = "none";
	int setup_errno = 0, cleanup_errno = 0;
	bool passed = false, control_ok, counts_balanced;

	if (argc < 7) {
		fprintf(stderr, "Required: --threads N --iterations N --deadline-ms N; optional: "
			"--control-device PATH --native-capacity N --quiescent-mm\n");
		return 2;
	}
	for (index = 1; index < (size_t)argc;) {
		if (!strcmp(argv[index], "--quiescent-mm")) {
			if (control.quiescent)
				return 2;
			control.quiescent = true;
			index++;
			continue;
		}
		if (index + 1 >= (size_t)argc)
			return 2;
		if (!strcmp(argv[index], "--control-device")) {
			if (control.path || argv[index + 1][0] != '/')
				return 2;
			control.path = argv[index + 1];
			index += 2;
			continue;
		}
		uint64_t *destination = !strcmp(argv[index], "--threads") ? &count :
			!strcmp(argv[index], "--iterations") ? &iterations :
			!strcmp(argv[index], "--deadline-ms") ? &milliseconds :
			!strcmp(argv[index], "--native-capacity") ? &control.capacity : NULL;
		if (!destination || *destination || !number(argv[index + 1], destination)) {
			fprintf(stderr, "Arguments must be distinct positive decimal bounds\n");
			return 2;
		}
		index += 2;
	}
	if ((control.path && (!control.capacity || control.capacity > UINT_MAX || !control.quiescent)) ||
	    (!control.path && (control.capacity || control.quiescent))) {
		fprintf(stderr, "A control device requires explicit native capacity and quiescence contract\n");
		return 2;
	}
	page = sysconf(_SC_PAGESIZE);
	if (!count || !iterations || !milliseconds || page <= 0 ||
	    (size_t)page > SIZE_MAX / 4 || count > SIZE_MAX / sizeof(*workers) ||
	    count > SIZE_MAX / (4 * (size_t)page) ||
	    iterations > UINT64_MAX / count || milliseconds > UINT64_MAX / 1000000 ||
	    iterations > UINT64_MAX / (4 * (uint64_t)page)) {
		fprintf(stderr, "Requested counts or address extents do not fit\n");
		return 2;
	}
	group.page_bytes = page;
	group.iterations = iterations;
	atomic_init(&group.stop, false);
	if (control.path && !retry_signal(&control)) {
		fprintf(stderr, "Cleanup retry signal setup failed: %s\n", strerror(errno));
		return 1;
	}
	stride = 4 * (size_t)page;
	arena_length = count * stride;
	workers = calloc(count, sizeof(*workers));
	if (!workers) {
		fprintf(stderr, "Worker allocation failed: %s\n", strerror(errno));
		return 1;
	}
	arena = (void *)syscall(SYS_mmap, NULL, arena_length, PROT_NONE,
			       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (arena == MAP_FAILED) {
		fprintf(stderr, "Arena reservation failed: %s\n", strerror(errno));
		free(workers);
		return 1;
	}
	if (control.path && !start_control(&control)) {
		setup_error = "control_start";
		setup_errno = control.open_errno ? control.open_errno : control.start_errno;
		now_ns(&start);
		group.deadline_ns = start;
		goto joined;
	}
	/* One untouched guard page surrounds each two-page worker slot. */
	for (index = 0; index < count; ++index) {
		workers[index].group = &group;
		workers[index].id = index;
		workers[index].slot = arena + index * stride + page;
		setup_errno = pthread_create(&workers[index].thread, NULL, run_worker, &workers[index]);
		if (setup_errno) {
			setup_error = "pthread_create";
			break;
		}
		created++;
	}
	{
		int result = pthread_mutex_lock(&group.mutex);
		if (result) {
			return unjoined_failure(&control, "Start mutex", result);
		}
	}
	if (!now_ns(&start) || milliseconds * 1000000 > UINT64_MAX - start) {
		setup_error = "deadline_clock";
		setup_errno = errno ? errno : EOVERFLOW;
	}
	group.deadline_ns = start + milliseconds * 1000000;
	group.abort = created != count || strcmp(setup_error, "none");
	group.start = true;
	{
		int broadcast = pthread_cond_broadcast(&group.condition);
		int unlock = pthread_mutex_unlock(&group.mutex);
		if (broadcast || unlock) {
			return unjoined_failure(&control, "Start gate", broadcast ? broadcast : unlock);
		}
	}
	for (index = 0; index < created; ++index) {
		int result = pthread_join(workers[index].thread, NULL);
		if (result) {
			/* Outstanding tasks are not a drain proof. Do not unmap their slots. */
			return unjoined_failure(&control, "pthread_join", result);
		}
	}
joined:
	if (!now_ns(&end)) {
		setup_error = "final_clock";
		setup_errno = errno;
	}
	if (syscall(SYS_munmap, arena, arena_length))
		cleanup_errno = errno;
	if (control.path)
		finish_control(&control, group.deadline_ns);
	counts_balanced = control.path && control.final.state == KD_MMAP_API_RETIRED &&
		control.final.pool_idle && !control.final.gate_locked && !control.final.gate_contended &&
		balanced_native_counts(&control.final);
	control_ok = !control.path || (control.started && !control.cleanup_failed &&
		!control.open_errno && !control.start_errno &&
		!control.end_errno && !control.query_errno && !control.close_errno &&
		!control.cleanup_required && control.final.state == KD_MMAP_API_RETIRED &&
		control.final.pool_idle && !control.final.gate_locked && !control.final.gate_contended &&
		!control.final.source_calls && !control.final.count_overflow &&
		counts_balanced &&
		control.final.native_write_acquires && control.final.native_read_acquires &&
		control.final.native_downgrades && control.final.mm_identity == control.start.mm_identity &&
		control.final.object_identity == control.start.object_identity &&
		control.final.gate_identity == control.start.gate_identity);
	for (index = 0; index < count; ++index) {
		completed += workers[index].completed;
		errors += workers[index].error != NULL;
	}
	passed = created == count && !strcmp(setup_error, "none") && !cleanup_errno &&
		!errors && completed == count * iterations && end <= group.deadline_ns;
	printf("{\"schema\":1,\"status\":\"syscall_completion_%s\","
	       "\"kd_observations\":\"%s\",\"pid\":%ld,\"threads\":%" PRIu64 ","
	       "\"created_threads\":%zu,\"iterations_per_thread\":%" PRIu64 ","
	       "\"deadline_ms\":%" PRIu64 ",\"page_bytes\":%ld,\"mapping_pages\":2,"
	       "\"arena_address\":%" PRIuPTR ",\"arena_bytes\":%zu,\"arena_reservations\":1,"
	       "\"arena_cleanup_errno\":%d,\"deadline_exceeded\":%s,"
	       "\"completed_iterations\":%" PRIu64 ",\"worker_errors\":%" PRIu64 ","
	       "\"setup_error\":\"%s\",\"setup_errno\":%d,\"elapsed_ns\":%" PRIu64 ",\"workers\":[",
	       passed ? "pass" : "fail", control.path ? "native_gate_only" : "not_collected",
	       (long)getpid(), count, created, iterations, milliseconds,
	       page, (uintptr_t)arena, arena_length, cleanup_errno,
	       end > group.deadline_ns ? "true" : "false", completed, errors, setup_error,
	       setup_errno, end >= start ? end - start : 0);
	for (index = 0; index < count; ++index) {
		struct worker *worker = &workers[index];
		printf("%s{\"id\":%zu,\"tid\":%ld,\"slot_address\":%" PRIuPTR
		       ",\"completed\":%" PRIu64 ",\"mmap_attempts\":%" PRIu64
		       ",\"mmap_successes\":%" PRIu64 ",\"munmap_attempts\":%" PRIu64
		       ",\"munmap_successes\":%" PRIu64 ",\"mincore_attempts\":%" PRIu64
		       ",\"unmapped_page_checks\":%" PRIu64 ",\"reuse_successes\":%" PRIu64
		       ",\"fresh_zero_bytes\":%" PRIu64 ",\"written_bytes\":%" PRIu64
		       ",\"readback_bytes\":%" PRIu64 ",\"deadline_reached\":%s,"
		       "\"error\":\"%s\",\"errno\":%d,\"error_iteration\":%" PRIu64
		       ",\"error_offset\":%zu}", index ? "," : "", index, worker->tid,
		       (uintptr_t)worker->slot, worker->completed,
		       worker->mmap_attempts, worker->mmap_successes, worker->munmap_attempts,
		       worker->munmap_successes, worker->mincore_attempts, worker->hole_checks,
		       worker->reuse_successes, worker->zero_bytes, worker->written_bytes,
		       worker->checked_bytes, worker->deadline_reached ? "true" : "false",
		       worker->error ? worker->error : "none", worker->error_number,
		       worker->error_iteration, worker->error_offset);
	}
	printf("],\"overall_pass\":%s,\"selected_gate\":{\"requested\":%s,"
	       "\"open_errno\":%d,\"start_errno\":%d,\"end_errno\":%d,\"query_errno\":%d,"
	       "\"close_errno\":%d,\"wait_errno\":%d,\"end_attempts\":%" PRIu64 ",\"cleanup_required\":%s,"
	       "\"cleanup_failed\":%s,\"native_counts_balanced\":%s,\"start\":",
	       passed && control_ok ? "true" : "false", control.path ? "true" : "false",
	       control.open_errno, control.start_errno, control.end_errno, control.query_errno,
	       control.close_errno, control.wait_errno, control.end_attempts,
	       control.cleanup_required ? "true" : "false",
	       control.cleanup_failed ? "true" : "false", counts_balanced ? "true" : "false");
	print_gate_status(&control.start);
	printf(",\"final\":");
	print_gate_status(&control.final);
	puts("}}");
	free(workers);
	return passed && control_ok ? 0 : 1;
}
