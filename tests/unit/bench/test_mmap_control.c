/* SPDX-License-Identifier: GPL-2.0 */
/* Deterministic transport faults against the production control helpers. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

enum fault { OK, PARTIAL, BACKPRESSURE, INTERRUPTED, CLOSED, LATE_POLL, LATE_BYTE };
static enum fault fault;
static long long tick;
static const char *input;
static size_t offset;
static unsigned send_calls, recv_calls, checks;

static int fake_clock(clockid_t id, struct timespec *t)
{
	(void)id;t->tv_sec=tick/1000;t->tv_nsec=(tick%1000)*1000000;return 0;
}
static ssize_t fake_send(int fd, const void *buf, size_t size, int flags)
{
	(void)fd;(void)buf;send_calls++;
	assert(flags & MSG_DONTWAIT);assert(flags & MSG_NOSIGNAL);
	if(fault==INTERRUPTED) { tick++;errno=EINTR;return -1; }
	if(fault==BACKPRESSURE) { errno=EAGAIN;return -1; }
	if(fault==CLOSED) { errno=EPIPE;return -1; }
	return fault==PARTIAL ? 1 : (ssize_t)size;
}
static int fake_poll(struct pollfd *p, nfds_t count, int timeout)
{
	(void)p;assert(count==1 && timeout>0);
	if(fault==INTERRUPTED) { tick++;errno=EINTR;return -1; }
	if(fault==BACKPRESSURE) { tick+=timeout;return 0; }
	if(fault==LATE_POLL) tick+=timeout;
	return 1;
}
static ssize_t fake_recv(int fd, void *buf, size_t size, int flags)
{
	(void)fd;assert(size==1 && flags==MSG_DONTWAIT);recv_calls++;
	if(fault==CLOSED || !input[offset]) return 0;
	*(char *)buf=input[offset++];
	if(fault==LATE_BYTE && !input[offset]) tick=10;
	return 1;
}
#define clock_gettime fake_clock
#define send fake_send
#define poll fake_poll
#define recv fake_recv
#include "../../../bench/mmap_writer/control.h"
#undef clock_gettime
#undef send
#undef poll
#undef recv

static void reset(enum fault kind, const char *bytes)
{
	fault=kind;input=bytes;offset=0;tick=0;send_calls=recv_calls=0;
}
#define CHECK(value) do { assert(value);checks++; } while(0)
int main(void)
{
	reset(PARTIAL,"");CHECK(!mw_control_send(3,"MW1 GO\n",10));CHECK(send_calls==7);
	reset(BACKPRESSURE,"");CHECK(mw_control_send(3,"MW1 GO\n",10)==-1);CHECK(tick==10);
	reset(INTERRUPTED,"");CHECK(mw_control_send(3,"MW1 GO\n",10)==-1);CHECK(send_calls==10);
	reset(CLOSED,"");CHECK(mw_control_send(3,"MW1 GO\n",10)==-1);
	reset(OK,"MW1 GO\n");CHECK(!mw_control_wait(3,"MW1 GO\n",10));
	reset(INTERRUPTED,"MW1 GO\n");CHECK(mw_control_wait(3,"MW1 GO\n",10)==-1);CHECK(tick==10);
	reset(CLOSED,"MW1 GO\n");CHECK(mw_control_wait(3,"MW1 GO\n",10)==-1);
	reset(LATE_POLL,"MW1 GO\n");CHECK(mw_control_wait(3,"MW1 GO\n",10)==-1);CHECK(!recv_calls);
	reset(LATE_BYTE,"MW1 GO\n");CHECK(mw_control_wait(3,"MW1 GO\n",10)==-1);
	reset(OK,"MW1 GO\nMW1 EXPORT\n");CHECK(!mw_control_wait(3,"MW1 GO\n",10));
	CHECK(mw_control_wait(3,"MW1 EXPORT 0123456789abcdef\n",10)==-1);
	reset(OK,"MW1 GO\nMW1 GO\n");CHECK(!mw_control_wait(3,"MW1 GO\n",10));
	CHECK(mw_control_wait(3,"MW1 EXPORT 0123456789abcdef\n",10)==-1);
	reset(OK,"MW1 EXPORT fedcba9876543210\n");CHECK(mw_control_wait(3,"MW1 EXPORT 0123456789abcdef\n",10)==-1);
	reset(OK,"MW1 EXPORT 0123456789abcdef\n");CHECK(!mw_control_wait(3,"MW1 EXPORT 0123456789abcdef\n",10));
	reset(OK,"");CHECK(mw_control_wait(3,"MW1 EXPORT 0123456789abcdef\n",10)==-1);
	printf("mmap control: %u assertions passed\n",checks);return 0;
}
