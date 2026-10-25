/* SPDX-License-Identifier: GPL-2.0 */
/* Optional private socket protocol. No target work or file output in a hold. */
#ifndef MMAP_WRITER_CONTROL_H
#define MMAP_WRITER_CONTROL_H
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static long long mw_control_ms(void)
{
	struct timespec t;
	if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
	return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static int mw_control_send(int fd, const char *message, int timeout_ms)
{
	size_t size = strlen(message), done = 0;
	long long now = mw_control_ms();
	if (now < 0) return -1;
	long long end = now + timeout_ms;
	while (done < size) {
		now = mw_control_ms();
		if (now < 0 || now >= end) return -1;
		ssize_t n = send(fd, message + done, size - done, MSG_NOSIGNAL | MSG_DONTWAIT);
		if (n < 0 && errno == EINTR) continue;
		if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
			struct pollfd p = { .fd = fd, .events = POLLOUT };
			int rc = poll(&p, 1, (int)(end - now));
			if (rc < 0 && errno == EINTR) continue;
			if (rc <= 0) return -1;
			continue;
		}
		if (n <= 0) return -1;
		done += (size_t)n;
	}
	now = mw_control_ms();
	return now >= 0 && now < end ? 0 : -1;
}

/* One absolute deadline also bounds fragmented or unterminated commands. */
static int mw_control_wait(int fd, const char *expected, int timeout_ms)
{
	char line[64];
	size_t used = 0;
	long long now = mw_control_ms();
	if (now < 0) return -1;
	long long end = now + timeout_ms;
	while (used < sizeof(line) - 1) {
		now = mw_control_ms();
		if (now < 0) return -1;
		long long left = end - now;
		if (left <= 0) return -1;
		struct pollfd p = { .fd = fd, .events = POLLIN };
		int rc = poll(&p, 1, (int)left);
		if (rc < 0 && errno == EINTR) continue;
		if (rc <= 0) return -1;
		now = mw_control_ms();
		if (now < 0 || now >= end) return -1;
		ssize_t n = recv(fd, line + used, 1, MSG_DONTWAIT);
		if (n < 0 && errno == EINTR) continue;
		if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) continue;
		if (n != 1) return -1;
		now = mw_control_ms();
		if (now < 0 || now >= end) return -1;
		if (line[used++] == '\n') {
			line[used] = 0;
			return strcmp(line, expected) ? -1 : 0;
		}
	}
	return -1;
}
#endif
