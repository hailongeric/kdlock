// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE
#include <fcntl.h>
#include <linux/magic.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <unistd.h>
#include "fixture/api.h"
#define PAGES 64
#define CHECK(c) do { if (!(c)) { perror(#c); fprintf(stderr, "line %d\n", __LINE__); exit(1); } } while (0)
int main(int argc, char **argv)
{
	CHECK(argc == 3 && sysconf(_SC_PAGESIZE) == 4096);
	int expected_kd = atoi(argv[2]);
	cpu_set_t set;
	CPU_ZERO(&set); CPU_SET(0, &set);
	CHECK(!sched_setaffinity(0, sizeof(set), &set));
	int file = open(argv[1], O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
	CHECK(file >= 0);
	struct statfs fs;
	CHECK(!fstatfs(file, &fs) && fs.f_type == EXT4_SUPER_MAGIC);
	unsigned char *buffer = malloc(PAGES * 4096);
	CHECK(buffer);
	memset(buffer, 0x31, PAGES * 4096);
	CHECK(write(file, buffer, PAGES * 4096) == PAGES * 4096 && !fsync(file));
	volatile unsigned char *map = mmap(NULL, PAGES * 4096, PROT_READ | PROT_WRITE, MAP_SHARED, file, 0);
	CHECK(map != MAP_FAILED);
	/* Populate only the read PTEs before observing writes. The dirty shared
	 * page fault must run page_mkwrite and return its genuine result. */
	for (unsigned i = 0; i < PAGES; i++) CHECK(map[i * 4096] == 0x31);
	int probe = open("/dev/kd_mmap_completed", O_RDWR | O_CLOEXEC);
	CHECK(probe >= 0);
	struct completed_range range = {.start = (unsigned long)map, .end = (unsigned long)map + PAGES * 4096};
	CHECK(!ioctl(probe, COMPLETED_START, &range));
	for (unsigned i = 0; i < PAGES; i++) {
		map[i * 4096] = 0x80 + i;
		map[i * 4096 + 4095] = 0x40 + i;
	}
	struct completed_result result;
	CHECK(!ioctl(probe, COMPLETED_END, &result));
	printf("{\"mm\":%llu,\"lock\":%llu,\"tid\":%llu,\"use_kd\":%llu,"
	       "\"entries\":%llu,\"returns\":%llu,\"completed\":%llu,\"retries\":%llu,"
	       "\"errors\":%llu,\"missed\":%llu,\"write_reacquired\":%llu}\n",
	       result.mm, result.lock, result.tid, result.use_kd, result.entries, result.returns,
	       result.completed, result.retries, result.errors, result.missed, result.write_reacquired);
	fflush(stdout);
	CHECK(result.mm && result.lock && result.tid == (unsigned long)syscall(SYS_gettid));
	CHECK(result.use_kd == (unsigned)expected_kd && result.entries == PAGES && result.returns == PAGES &&
	      result.completed == PAGES && !result.retries && !result.errors && !result.missed && result.write_reacquired);
	CHECK(!msync((void *)map, PAGES * 4096, MS_SYNC) && !munmap((void *)map, PAGES * 4096));
	CHECK(pread(file, buffer, PAGES * 4096, 0) == PAGES * 4096);
	for (unsigned i = 0; i < PAGES * 4096; i++) {
		unsigned char expected = i % 4096 == 0 ? 0x80 + i / 4096 :
			i % 4096 == 4095 ? 0x40 + i / 4096 : 0x31;
		CHECK(buffer[i] == expected);
	}
	free(buffer);
	CHECK(!close(probe) && !close(file) && !unlink(argv[1]));
	puts("{\"passed\":true,\"pages\":64,\"data_ok\":true,\"timing\":false}");
	return 0;
}
