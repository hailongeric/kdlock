// SPDX-License-Identifier: GPL-2.0
/* Actual syscall cases for opt-in capture selection; no kernel test body. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

#define MAP_BYTES (128UL * 1024 * 1024)

static void checkpoint(const char *name)
{
	char command[16];

	puts(name);
	assert(!fflush(stdout));
	assert(fgets(command, sizeof(command), stdin));
	assert(!strcmp(command, "next\n"));
}

static void verify_mapping(char *area, size_t length)
{
	assert(area != MAP_FAILED);
	area[0] = 17;
	area[length - 1] = 29;
	assert(area[0] == 17 && area[length - 1] == 29);
}

int main(void)
{
	int file;
	char *area;

	checkpoint("ready");
	area = mmap(NULL, MAP_BYTES / 2, PROT_READ | PROT_WRITE,
		MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	verify_mapping(area, MAP_BYTES / 2);
	assert(!munmap(area, MAP_BYTES / 2));
	checkpoint("anonymous64");

	file = syscall(SYS_memfd_create, "argument-fixture", 0);
	assert(file >= 0 && !ftruncate(file, MAP_BYTES));
	area = mmap(NULL, MAP_BYTES, PROT_READ | PROT_WRITE, MAP_PRIVATE, file, 0);
	verify_mapping(area, MAP_BYTES);
	checkpoint("file128");
	/* The argument filter cannot tell this unmap from an anonymous unmap. */
	assert(!munmap(area, MAP_BYTES));
	assert(!close(file));
	checkpoint("file128-unmapped");

	area = mmap(NULL, MAP_BYTES, PROT_READ | PROT_WRITE,
		MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	verify_mapping(area, MAP_BYTES);
	checkpoint("anonymous128");
	assert(!munmap(area, MAP_BYTES));
	checkpoint("anonymous128-unmapped");
	return 0;
}
