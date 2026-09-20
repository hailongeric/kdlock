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
	if (ioctl(w->fd, SC_RUN, &w->run))
		w->error = errno;
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
	    l->slots != SC_SLOTS || !l->lock_bytes || l->lock_bytes > SC_LINE_BYTES ||
	    !l->lock_addr || !l->control_addr || !l->data_addr ||
	    l->lock_addr % SC_LINE_BYTES || l->control_addr % SC_LINE_BYTES ||
	    l->data_addr % SC_LINE_BYTES || l->lock_addr == l->control_addr)
		return false;
	if (l->workload == SC_WORKLOAD_HASH)
		return l->buckets == SC_HASH_BUCKETS && l->entries == SC_HASH_ENTRIES &&
		       l->key_range == SC_HASH_KEY_RANGE && l->resched <= 1;
	if (l->workload != SC_WORKLOAD_CACHELINE)
		return false;
	for (int i = 0; i < SC_SLOTS; i++)
		if (l->slot_addr[i] != l->data_addr + i * SC_LINE_BYTES ||
		    l->slot_addr[i] == l->lock_addr || l->slot_addr[i] == l->control_addr)
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
		{ NULL, 0, NULL, 0 },
	};
	struct worker workers[CPU_SETSIZE] = { 0 };
	struct gate gate = { .ready = ATOMIC_VAR_INIT(0),
		.go = ATOMIC_VAR_INIT(false), .abort = ATOMIC_VAR_INIT(false) };
	struct sc_layout layout;
	struct sc_counts before, after;
	uint64_t iterations = 10000, lines = 0, completed = 0, cpu_ns = 0;
	uint64_t started, finished = 0, elapsed;
	unsigned int count = 0, created = 0;
	bool layout_only = false, counts_only = false, prepare_only = false, valid = true;
	bool hash = false;
	char *cpu_text = NULL, *token, *save;
	int fd, option, error = 0;

	while ((option = getopt_long(argc, argv, "", options, NULL)) != -1) {
		switch (option) {
		case 'n': lines = number(optarg); break;
		case 'i': iterations = number(optarg); break;
		case 'c': cpu_text = optarg; break;
		case 'l': layout_only = true; break;
		case 's': counts_only = true; break;
		case 'p': prepare_only = true; break;
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
	if (prepare_only && !(hash ? lines == 0 :
		(lines == 1 || lines == 2 || lines == 4 || lines == 8 || lines == 16)))
		return 2;
	if (!layout_only && !counts_only && !prepare_only) {
		if (!(hash ? lines == 0 :
		      (lines == 1 || lines == 2 || lines == 4 || lines == 8 || lines == 16)) ||
		    !iterations || iterations > SC_MAX_ITERATIONS || !cpu_text ||
		    !*cpu_text || cpu_text[0] == ',' || cpu_text[strlen(cpu_text)-1] == ',' ||
		    strstr(cpu_text, ",,")) {
			fprintf(stderr, "Use --cachelines 1|2|4|8|16 --iterations N --cpus 0,1,...\n");
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
	fd = open(SC_DEVICE, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror(SC_DEVICE);
		return 1;
	}
	if (ioctl(fd, SC_LAYOUT, &layout) || !layout_valid(&layout)) {
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
		error = pthread_create(&w->thread, NULL, work, w);
		if (error)
			break;
	}
	while (atomic_load_explicit(&gate.ready, memory_order_acquire) != created)
		gate_pause();
	/* A partial create still releases and joins all existing workers; no
	 * worker enters the device if any setup/create operation failed. */
	if (error)
		atomic_store_explicit(&gate.abort, true, memory_order_relaxed);
	started = now(CLOCK_MONOTONIC);
	atomic_store_explicit(&gate.go, true, memory_order_release);
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
		valid &= !workers[i].error && workers[i].run.completed == iterations;
	}
	if (ioctl(fd, SC_COUNTS, &after)) {
		perror("final SC_COUNTS (drain unconfirmed)");
		close(fd);
		return 1;
	}
	close(fd);
	valid &= !atomic_load_explicit(&gate.abort, memory_order_relaxed) &&
		 created == count && completed == count * iterations;
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
	printf("{\"schema\":1,\"cachelines\":%llu,\"threads\":%u,"
	       "\"iterations\":%llu,\"completed\":%llu,\"wall_ns\":%llu,"
	       "\"worker_cpu_ns\":%llu,\"data_ok\":%s,\"complete\":%s,"
	       "\"started_ns\":%llu,\"finished_ns\":%llu,\"before\":",
	       (unsigned long long)lines, count, (unsigned long long)iterations,
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
		       "\"cpu_ns\":%llu,\"finished_ns\":%llu,\"error\":%d}", i ? "," : "",
		       w->cpu, w->observed_cpu, w->run.completed,
		       (unsigned long long)w->cpu_ns, (unsigned long long)w->finished_ns, w->error);
	}
	puts("]}");
	return valid ? 0 : 1;
}
