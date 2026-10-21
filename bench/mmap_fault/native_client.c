// SPDX-License-Identifier: GPL-2.0
/* Rejected provider requests must not configure a file or become fallback. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include "mmap_fault_uapi.h"

static void require(int ok, const char *message)
{
	if (!ok) { perror(message); exit(1); }
}
int main(void)
{
	int fd = open("/dev/kd_mmap_fault", O_RDWR | O_CLOEXEC);
	unsigned rejected = 0;
	require(fd >= 0, "open");
	for (unsigned backend = MF_KD; backend <= MF_TC; backend++) {
		for (unsigned fallback = 0; fallback <= 1; fallback++) {
			struct mf_create c = { .abi = MF_ABI, .backend = backend,
				.pages = 1, .features = fallback ? MF_PRIVATE | MF_ALLOW_FALLBACK : 0 };
			errno = 0;
			require(ioctl(fd, MF_CREATE, &c) == -1 && errno == EOPNOTSUPP,
				"non-Native backend must be rejected");
			struct mf_stats absent;
			errno = 0;
			require(ioctl(fd, MF_STATS, &absent) == -1 && errno == EINVAL,
				"rejection must not publish an object");
			rejected++;
		}
	}
	struct mf_create c = { .abi = MF_ABI, .backend = MF_NATIVE, .pages = 1 };
	struct mf_stats s;
	require(!ioctl(fd, MF_CREATE, &c) && c.selected_backend == MF_NATIVE && !c.fallback,
		"rejections must leave file unconfigured");
	require(!ioctl(fd, MF_STATS, &s) && !s.backend && !s.vmas && !s.faults &&
		!s.reads && !s.read_ends && !s.writes && !s.write_ends && !s.fallback,
		"untouched Native object");
	errno = 0;
	require(ioctl(fd, MF_CREATE, &c) == -1 && errno == EBUSY, "immutable file backend");
	require(!close(fd), "final close");
	printf("{\"passed\":true,\"rejected_backends\":%u,\"selected_backend\":0}\n", rejected);
	return 0;
}
