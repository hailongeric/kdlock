// SPDX-License-Identifier: GPL-2.0
/* One ioctl per bound worker. Timing starts only after all workers are ready;
 * wall time is the common-release to last-ioctl-return envelope, not lock latency. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <inttypes.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
#include "../../workload_modules/spin_cacheline/api.h"

struct gate {
	_Alignas(SC_LINE_BYTES) atomic_uint ready;
	_Alignas(SC_LINE_BYTES) atomic_bool go;
	atomic_bool abort;
};

/* x86-64 only: the gate must never fall back to a library-internal lock. */
_Static_assert(ATOMIC_INT_LOCK_FREE == 2 && ATOMIC_BOOL_LOCK_FREE == 2,
	       "the start gate requires lock-free atomics");

static void gate_pause(void)
{
	__asm__ __volatile__("pause");
}

struct worker {
	pthread_t thread;
	struct gate *gate;
	struct sc_run run;
	struct sc_timed_run timed_run;
	bool timed;
	int fd, cpu, error, observed_cpu;
	uint64_t cpu_ns, finished_ns;
};

static uint64_t now(clockid_t clock)
{
	struct timespec t;
	if (clock_gettime(clock, &t)) {
		perror("clock_gettime");
		exit(1);
	}
	return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

static void *work(void *opaque)
{
	struct worker *w = opaque;
	struct gate *g = w->gate;
	cpu_set_t affinity, observed;
	uint64_t started;

	CPU_ZERO(&affinity);
	CPU_SET(w->cpu, &affinity);
	w->error = pthread_setaffinity_np(pthread_self(), sizeof(affinity), &affinity);
	if (!w->error)
		w->error = pthread_getaffinity_np(pthread_self(), sizeof(observed), &observed);
	if (!w->error && (CPU_COUNT(&observed) != 1 || !CPU_ISSET(w->cpu, &observed)))
		w->error = EINVAL;
	if (!w->error)
		w->error = pthread_setname_np(pthread_self(), SC_COMM);
	w->observed_cpu = sched_getcpu();
	if (!w->error && w->observed_cpu != w->cpu)
		w->error = EINVAL;
	if (!w->error && ioctl(w->fd, SC_WORKER_REGISTER))
		w->error = errno;
	if (w->error)
		atomic_store_explicit(&g->abort, true, memory_order_relaxed);
	/* Publish setup/error before ready. The main thread releases go only
	 * after every created worker is ready and the wall clock has started. */
	atomic_fetch_add_explicit(&g->ready, 1, memory_order_acq_rel);
	while (!atomic_load_explicit(&g->go, memory_order_acquire))
		gate_pause();
	if (atomic_load_explicit(&g->abort, memory_order_relaxed))
		return NULL;
	started = now(CLOCK_THREAD_CPUTIME_ID);
	if (ioctl(w->fd, w->timed ? SC_RUN_TIMED : SC_RUN,
		  w->timed ? (void *)&w->timed_run : (void *)&w->run))
		w->error = errno;
	if (w->timed)
		w->run.completed = w->timed_run.completed;
	w->finished_ns = now(CLOCK_MONOTONIC);
	w->cpu_ns = now(CLOCK_THREAD_CPUTIME_ID) - started;
	return NULL;
}

static uint64_t number(const char *s)
{
	char *end;
	unsigned long long value;
	if (!*s || strspn(s, "0123456789") != strlen(s))
		goto invalid;
	errno = 0;
	value = strtoull(s, &end, 10);
	if (errno || *end)
		goto invalid;
	return value;
invalid:
	fprintf(stderr, "Invalid unsigned number: %s\n", s);
	exit(2);
}

static bool layout_valid(const struct sc_layout *l)
{
	if (l->version != SC_VERSION || l->line_bytes != SC_LINE_BYTES ||
	    l->slots != SC_SLOTS || !l->lock_bytes ||
	    (l->lock_bytes > SC_LINE_BYTES &&
	     !(l->lock_kind == 2 && l->lock_bytes == 2 * SC_LINE_BYTES)) ||
	    !l->lock_addr || !l->control_addr || !l->data_addr ||
	    l->lock_addr % SC_LINE_BYTES || l->control_addr % SC_LINE_BYTES ||
	    l->data_addr % SC_LINE_BYTES ||
	    (l->control_addr >= l->lock_addr &&
	     l->control_addr - l->lock_addr < l->lock_bytes))
		return false;
	if (l->workload == SC_WORKLOAD_HASH)
		return l->buckets == SC_HASH_BUCKETS && l->entries == SC_HASH_ENTRIES &&
		       l->key_range == SC_HASH_KEY_RANGE && l->resched <= 1;
	if (l->workload != SC_WORKLOAD_CACHELINE)
		return false;
	for (int i = 0; i < SC_SLOTS; i++)
		if (l->slot_addr[i] != l->data_addr + i * SC_LINE_BYTES ||
		    (l->slot_addr[i] >= l->lock_addr &&
		     l->slot_addr[i] - l->lock_addr < l->lock_bytes) ||
		    l->slot_addr[i] == l->control_addr)
			return false;
	return true;
}

static void values_json(const __u64 *v)
{
	putchar('[');
	for (int i = 0; i < SC_SLOTS; i++)
		printf("%s%llu", i ? "," : "", (unsigned long long)v[i]);
	putchar(']');
}

/* The collector runs on a spare CPU and reads only separate progress slots.
 * Absolute sleeps prevent accumulated polling drift; missed ticks are skipped,
 * and Python uses actual kernel timestamp brackets rather than a nominal rate. */
static int collect_progress(int fd, const struct sc_timed_config *config,
			    uint64_t period, struct sc_progress *samples,
			    size_t capacity, size_t *count)
{
	uint64_t next = config->started_ns;

	while (next <= config->deadline_ns && *count < capacity) {
		struct timespec target = { .tv_sec = next / 1000000000,
			.tv_nsec = next % 1000000000 };
		struct sc_progress *sample = &samples[*count];
		int error;

		do {
			error = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, NULL);
		} while (error == EINTR);
		if (error)
			return error;
		if (ioctl(fd, SC_PROGRESS, sample))
			return errno;
		if (sample->started_ns != config->started_ns ||
		    sample->deadline_ns != config->deadline_ns ||
		    sample->workers != config->workers ||
		    sample->read_finished_ns < sample->read_started_ns)
			return EINVAL;
		(*count)++;
		next += period;
		if (sample->read_finished_ns > next)
			next += ((sample->read_finished_ns - next) / period + 1) * period;
	}
	return 0;
}

int main(int argc, char **argv)
{
	static const struct option options[] = {
		{ "cachelines", required_argument, NULL, 'n' },
		{ "iterations", required_argument, NULL, 'i' },
		{ "cpus", required_argument, NULL, 'c' },
		{ "layout", no_argument, NULL, 'l' },
		{ "counts", no_argument, NULL, 's' },
		{ "prepare", no_argument, NULL, 'p' },
		{ "workload", required_argument, NULL, 'w' },
		{ "lock-kind", required_argument, NULL, 'k' },
		{ "duration-ms", required_argument, NULL, 'd' },
		{ "peak-window-ms", required_argument, NULL, 'W' },
		{ "peak-settle-ms", required_argument, NULL, 'S' },
		{ "sample-ms", required_argument, NULL, 'P' },
		{ "collector-cpu", required_argument, NULL, 'C' },
		{ "share-collector", no_argument, NULL, 1000 },
		{ NULL, 0, NULL, 0 },
	};
	struct worker workers[CPU_SETSIZE] = { 0 };
	struct gate gate = { .ready = ATOMIC_VAR_INIT(0),
		.go = ATOMIC_VAR_INIT(false), .abort = ATOMIC_VAR_INIT(false) };
	struct sc_layout layout;
	struct sc_counts before, after;
	struct sc_timed_config timed_config = { 0 };
	struct sc_progress *samples = NULL;
	size_t sample_count = 0, sample_capacity = 0;
	uint64_t iterations = 10000, lines = 0, completed = 0, cpu_ns = 0;
	uint64_t duration_ms = 0, window_ms = 300, settle_ms = 300, sample_ms = 10;
	uint64_t collector_cpu = 30;
	uint64_t started, finished = 0, elapsed;
	unsigned int count = 0, created = 0;
	bool layout_only = false, counts_only = false, prepare_only = false, valid = true;
	bool hash = false, timed_options = false, iterations_set = false;
	bool share_collector = false;
	unsigned int lock_kind = 1;
	char *cpu_text = NULL, *token, *save;
	int fd, option, error = 0, collector_observed_cpu = -1, collector_error = 0;

	while ((option = getopt_long(argc, argv, "", options, NULL)) != -1) {
		switch (option) {
		case 'k':
			if (strcmp(optarg, "mutex") && strcmp(optarg, "spin"))
				return 2;
			lock_kind = !strcmp(optarg, "mutex") ? 2 : 1;
			break;
		case 'n': lines = number(optarg); break;
		case 'i': iterations = number(optarg); iterations_set = true; break;
		case 'c': cpu_text = optarg; break;
		case 'l': layout_only = true; break;
		case 's': counts_only = true; break;
		case 'p': prepare_only = true; break;
		case 'd': duration_ms = number(optarg); timed_options = true; break;
		case 'W': window_ms = number(optarg); timed_options = true; break;
		case 'S': settle_ms = number(optarg); timed_options = true; break;
		case 'P': sample_ms = number(optarg); timed_options = true; break;
		case 'C': collector_cpu = number(optarg); timed_options = true; break;
		case 1000: share_collector = true; timed_options = true; break;
		case 'w':
			if (strcmp(optarg, "rcuht") && strcmp(optarg, "cacheline"))
				return 2;
			hash = !strcmp(optarg, "rcuht");
			break;
		default: return 2;
		}
	}
	if (optind != argc || layout_only + counts_only + prepare_only > 1)
		return 2;
	if (timed_options && (!duration_ms ||
	    duration_ms > SC_TIMED_MAX_DURATION_NS / 1000000 ||
	    !window_ms || window_ms > duration_ms || settle_ms >= duration_ms - window_ms ||
	    !sample_ms || sample_ms > window_ms || collector_cpu >= CPU_SETSIZE ||
	    iterations_set || layout_only || counts_only || prepare_only))
		return 2;
	if (prepare_only && !(hash ? lines == 0 :
		(lines == 1 || lines == 2 || lines == 4 || lines == 8 || lines == 16)))
		return 2;
	if (!layout_only && !counts_only && !prepare_only) {
		if (!(hash ? lines == 0 :
		      (lines == 1 || lines == 2 || lines == 4 || lines == 8 || lines == 16)) ||
		    (!duration_ms && (!iterations || iterations > SC_MAX_ITERATIONS)) || !cpu_text ||
		    !*cpu_text || cpu_text[0] == ',' || cpu_text[strlen(cpu_text)-1] == ',' ||
		    strstr(cpu_text, ",,")) {
			fprintf(stderr, "Use --cachelines 1|2|4|8|16 --cpus 0,1,... "
				"with --iterations N or --duration-ms N\n");
			return 2;
		}
		for (token = strtok_r(cpu_text, ",", &save); token;
		     token = strtok_r(NULL, ",", &save)) {
			uint64_t cpu = number(token);
			if (cpu >= CPU_SETSIZE || count == CPU_SETSIZE)
				return 2;
			for (unsigned int j = 0; j < count; j++)
				if (workers[j].cpu == (int)cpu)
					return 2;
			workers[count++].cpu = cpu;
		}
	}
	if (duration_ms) {
		if (count > SC_TIMED_MAX_WORKERS)
			return 2;
		/* Explicitly labelled 64-worker point on the fixed 64-vCPU VM.
		 * Every smaller cohort retains a separate collector. */
		if (share_collector && (count != 64 || collector_cpu != 63 ||
		    sysconf(_SC_NPROCESSORS_ONLN) != 64))
			return 2;
		for (unsigned int i = 0; i < count; i++)
			if ((share_collector && workers[i].cpu != (int)i) ||
			    (!share_collector && workers[i].cpu == (int)collector_cpu))
				return 2;
		iterations = 0;
		sample_capacity = duration_ms / sample_ms + 2;
		samples = calloc(sample_capacity, sizeof(*samples));
		if (!samples) {
			perror("progress allocation");
			return 1;
		}
	}
	fd = open(lock_kind == 2 ? "/dev/mutex_cacheline" : SC_DEVICE, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror(SC_DEVICE);
		return 1;
	}
	if (ioctl(fd, SC_LAYOUT, &layout) || !layout_valid(&layout) ||
	    layout.lock_kind != lock_kind) {
		fprintf(stderr, "Invalid/unavailable payload layout\n");
		close(fd);
		return 1;
	}
	if (layout.workload != (hash ? SC_WORKLOAD_HASH : SC_WORKLOAD_CACHELINE)) {
		fprintf(stderr, "Loaded workload differs from --workload\n");
		close(fd);
		return 1;
	}
	if (prepare_only) {
		__u32 prepare_lines = lines;
		error = ioctl(fd, SC_PREPARE, &prepare_lines);
		if (error)
			perror("SC_PREPARE");
		else
			printf("{\"prepared\":true,\"cachelines\":%u}\n", prepare_lines);
		close(fd);
		return error ? 1 : 0;
	}
	if (layout_only) {
		printf("{\"version\":%u,\"line_bytes\":%u,\"slots\":%u,"
		       "\"lock_bytes\":%u,\"lock_addr\":%llu,\"control_addr\":%llu,"
		       "\"data_addr\":%llu,\"slot_addr\":", layout.version, layout.line_bytes,
		       layout.slots, layout.lock_bytes, layout.lock_addr,
		       layout.control_addr, layout.data_addr);
		values_json(layout.slot_addr);
		printf(",\"lock_kind\":%u", layout.lock_kind);
		printf(",\"workload\":\"%s\",\"buckets\":%u,\"entries\":%u,"
		       "\"key_range\":%u,\"resched\":%u}\n", hash ? "rcuht" : "cacheline",
		       layout.buckets, layout.entries, layout.key_range, layout.resched);
		close(fd);
		return 0;
	}
	if (ioctl(fd, SC_COUNTS, &before)) {
		perror("initial SC_COUNTS (workers must be drained)");
		close(fd);
		return 1;
	}
	if (counts_only) {
		printf("{\"active\":%u,\"values\":", before.active);
		values_json(before.values);
		puts("}");
		close(fd);
		return 0;
	}
	for (created = 0; created < count; created++) {
		struct worker *w = &workers[created];
		w->gate = &gate;
		w->fd = fd;
		w->run.cachelines = lines;
		w->run.iterations = iterations;
		w->timed = duration_ms != 0;
		w->timed_run.cachelines = lines;
		w->timed_run.worker = created;
		error = pthread_create(&w->thread, NULL, work, w);
		if (error)
			break;
	}
	while (atomic_load_explicit(&gate.ready, memory_order_acquire) != created)
		gate_pause();
	if (duration_ms && !error) {
		cpu_set_t affinity, observed;

		/* Worker threads already exist and pin themselves independently.
		 * Expand only the collector's affinity beyond the runner's CPUs. */
		CPU_ZERO(&affinity);
		CPU_SET(collector_cpu, &affinity);
		error = pthread_setaffinity_np(pthread_self(), sizeof(affinity), &affinity);
		if (!error)
			error = pthread_getaffinity_np(pthread_self(), sizeof(observed), &observed);
		collector_observed_cpu = sched_getcpu();
		if (!error && (CPU_COUNT(&observed) != 1 ||
		    !CPU_ISSET(collector_cpu, &observed) ||
		    collector_observed_cpu != (int)collector_cpu))
			error = EINVAL;
	}
	/* A partial create still releases and joins all existing workers; no
	 * worker enters the device if any setup/create operation failed. */
	if (error)
		atomic_store_explicit(&gate.abort, true, memory_order_relaxed);
	started = now(CLOCK_MONOTONIC);
	if (duration_ms && !error &&
	    !atomic_load_explicit(&gate.abort, memory_order_relaxed)) {
		timed_config.started_ns = started;
		timed_config.deadline_ns = started + duration_ms * 1000000;
		timed_config.workers = count;
		if (ioctl(fd, SC_TIMED_CONFIG, &timed_config)) {
			error = errno;
			atomic_store_explicit(&gate.abort, true, memory_order_relaxed);
		}
		for (unsigned int i = 0; i < created; i++) {
			workers[i].timed_run.started_ns = timed_config.started_ns;
			workers[i].timed_run.deadline_ns = timed_config.deadline_ns;
		}
	}
	atomic_store_explicit(&gate.go, true, memory_order_release);
	if (duration_ms && !atomic_load_explicit(&gate.abort, memory_order_relaxed)) {
		collector_error = collect_progress(fd, &timed_config, sample_ms * 1000000,
					   samples, sample_capacity, &sample_count);
		if (collector_error)
			fprintf(stderr, "progress collection failed: %s\n", strerror(collector_error));
	}
	for (unsigned int i = 0; i < created; i++) {
		int joined = pthread_join(workers[i].thread, NULL);
		if (joined) {
			fprintf(stderr, "pthread_join failed: %d; drain is unconfirmed\n", joined);
			return 1;
		}
		completed += workers[i].run.completed;
		cpu_ns += workers[i].cpu_ns;
		if (workers[i].finished_ns > finished)
			finished = workers[i].finished_ns;
		valid &= !workers[i].error;
		if (duration_ms)
			valid &= workers[i].run.completed > 0 &&
				workers[i].timed_run.active_started_ns >= started &&
				workers[i].timed_run.active_started_ns < timed_config.deadline_ns &&
				workers[i].timed_run.finished_ns >= timed_config.deadline_ns &&
				workers[i].timed_run.finished_ns <= workers[i].finished_ns;
		else
			valid &= workers[i].run.completed == iterations;
	}
	/* A completed ioctl is insufficient: keep TCLock task contexts through
	 * all pthread exits, including partial-create and worker-error cleanup. */
	uint64_t drain_deadline = now(CLOCK_MONOTONIC) + 5000000000ULL;
	do {
		error = ioctl(fd, SC_WORKERS_DRAIN);
		if (!error || errno != EBUSY)
			break;
		usleep(1000);
	} while (now(CLOCK_MONOTONIC) < drain_deadline);
	if (error) {
		perror("SC_WORKERS_DRAIN (registrations retained)");
		close(fd);
		return 1;
	}
	if (ioctl(fd, SC_COUNTS, &after)) {
		perror("final SC_COUNTS (drain unconfirmed)");
		close(fd);
		return 1;
	}
	close(fd);
	valid &= !atomic_load_explicit(&gate.abort, memory_order_relaxed) &&
		 created == count && !error && !collector_error &&
		 (duration_ms ? completed > 0 : completed == count * iterations);
	valid &= before.active == 0 && after.active == 0 && finished > started;
	bool data_ok = true;
	if (hash) {
		/* A successful SC_COUNTS also validates the complete hash structure.
		 * Every operation must publish exactly one of three outcomes. */
		for (int i = 0; i < 4; i++)
			data_ok &= after.values[i] >= before.values[i];
		data_ok &= after.values[0] - before.values[0] == completed &&
			before.values[0] == before.values[1] + before.values[2] + before.values[3] &&
			after.values[0] == after.values[1] + after.values[2] + after.values[3];
		for (int i = 4; i < SC_SLOTS; i++)
			data_ok &= !before.values[i] && !after.values[i];
	} else {
		for (int i = 0; i < SC_SLOTS; i++)
			data_ok &= after.values[i] >= before.values[i] &&
				after.values[i] - before.values[i] == (i < (int)lines ? completed : 0);
	}
	valid &= data_ok;
	elapsed = finished > started ? finished - started : 0;
	printf("{\"schema\":%u,\"cachelines\":%llu,\"threads\":%u,"
	       "\"iterations\":%llu,\"completed\":%llu,\"wall_ns\":%llu,"
	       "\"worker_cpu_ns\":%llu,\"data_ok\":%s,\"complete\":%s,"
	       "\"started_ns\":%llu,\"finished_ns\":%llu,\"before\":",
	       duration_ms ? 2 : 1, (unsigned long long)lines, count, (unsigned long long)iterations,
	       (unsigned long long)completed, (unsigned long long)elapsed,
	       (unsigned long long)cpu_ns, data_ok ? "true" : "false",
	       valid ? "true" : "false", (unsigned long long)started,
	       (unsigned long long)finished);
	values_json(before.values);
	printf(",\"after\":");
	values_json(after.values);
	printf(",\"workload\":\"%s\",\"hash_integrity_ok\":%s",
	       hash ? "rcuht" : "cacheline", hash && data_ok ? "true" : "false");
	printf(",\"workers\":[");
	for (unsigned int i = 0; i < created; i++) {
		struct worker *w = &workers[i];
		printf("%s{\"cpu\":%d,\"observed_cpu\":%d,\"completed\":%llu,"
		       "\"cpu_ns\":%llu,\"finished_ns\":%llu,\"error\":%d", i ? "," : "",
		       w->cpu, w->observed_cpu, w->run.completed,
		       (unsigned long long)w->cpu_ns, (unsigned long long)w->finished_ns, w->error);
		if (duration_ms)
			printf(",\"active_started_ns\":%llu,\"kernel_finished_ns\":%llu",
			       w->timed_run.active_started_ns, w->timed_run.finished_ns);
		putchar('}');
	}
	putchar(']');
	if (duration_ms) {
		printf(",\"measurement_mode\":\"duration\",\"duration_ns\":%llu,"
		       "\"deadline_ns\":%llu,\"peak_window_ns\":%llu,\"peak_settle_ns\":%llu,"
		       "\"sample_period_ns\":%llu,\"collector_cpu\":%llu,"
		       "\"collector_observed_cpu\":%d,\"collector_error\":%d,"
		       "\"collector_shared\":%s,"
		       "\"progress_batch\":%u,\"samples\":[",
		       (unsigned long long)(duration_ms * 1000000), timed_config.deadline_ns,
		       (unsigned long long)(window_ms * 1000000),
		       (unsigned long long)(settle_ms * 1000000),
		       (unsigned long long)(sample_ms * 1000000),
		       (unsigned long long)collector_cpu, collector_observed_cpu, collector_error,
		       share_collector ? "true" : "false",
		       SC_TIMED_BATCH);
		for (size_t i = 0; i < sample_count; i++) {
			struct sc_progress *sample = &samples[i];
			printf("%s{\"started_ns\":%llu,\"finished_ns\":%llu,\"completed\":[",
			       i ? "," : "", sample->read_started_ns, sample->read_finished_ns);
			for (unsigned int j = 0; j < count; j++)
				printf("%s%llu", j ? "," : "", sample->completed[j]);
			printf("]}");
		}
		putchar(']');
	}
	puts("}");
	free(samples);
	return valid ? 0 : 1;
}
