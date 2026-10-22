// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "payload/api.h"

static void fail(const char *message) { perror(message); exit(1); }
int main(int argc, char **argv)
{
	struct mb_result r = {0};
	size_t page = (size_t)sysconf(_SC_PAGESIZE);
	unsigned int i, p;
	char *arena;
	int fd;
	cpu_set_t affinity;
	int cancel = argc == 2 && !strcmp(argv[1], "--cancel");

	if (argc != 1 && !cancel) return 2;

	CPU_ZERO(&affinity); CPU_SET(63, &affinity);
	if (sched_setaffinity(0, sizeof(affinity), &affinity)) fail("collector affinity");
	arena = mmap(NULL, MB_WORKERS * 5 * page, PROT_READ | PROT_WRITE,
		     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (arena == MAP_FAILED) fail("mmap");
	/* Keep real unmapped gaps, so a supported whole-VMA update cannot merge.
	 * No mapped byte is touched; setup and VMA advice do not trigger a fault. */
	for (i = 0; i < MB_WORKERS; i++) {
		r.address[i] = (uintptr_t)(arena + (5 * i + 1) * page);
		if (munmap(arena + 5 * i * page, page) ||
		    munmap(arena + (5 * i + 4) * page, page)) fail("unmap guard");
	}
	fd = open("/dev/kd_mm_body_test", O_RDWR);
	if (fd < 0 || ioctl(fd, cancel ? MB_CANCEL : MB_RUN, &r)) fail("body ioctl");
	if (close(fd)) fail("close");
	for (i = 0; i < MB_WORKERS; i++)
		if (munmap((void *)(uintptr_t)r.address[i], 3 * page)) fail("final unmap");
	printf("{\"mm\":%llu,\"lock\":%llu,\"checks\":%llu,\"errors\":%llu,"
	       "\"completed\":%llu,\"reader_peak\":%llu,\"pending_peak\":%llu,\"idle\":%llu,\"phases\":[",
	       r.mm, r.lock, r.checks, r.errors, r.completed, r.reader_peak, r.pending_peak, r.idle);
	for (p = 0; p < 3; p++) {
		struct mb_counts *c = &r.counts[p];
		printf("%s{\"calls\":%llu,\"supported\":%llu,\"delegated\":%llu,\"handbacks\":%llu,"
		       "\"native\":%llu,\"post_ban\":%llu,\"cancelled\":%llu,\"acks\":%llu,"
		       "\"native_only\":%llu,\"tids\":[", p ? "," : "", c->calls, c->supported,
		       c->delegated, c->handbacks, c->native, c->post_ban, c->cancelled, c->acks, c->native_only);
		for (i = 0; i < MB_WORKERS; i++) printf("%s%llu", i ? "," : "", r.tids[p][i]);
		printf("]}");
	}
	printf("],\"unmapped\":%u}\n", MB_WORKERS);
	return r.errors || !r.idle;
}
