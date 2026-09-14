// SPDX-License-Identifier: GPL-2.0
/* Exercise the delivered client's explicit two-ioctl contract and legacy
 * argument routing. Substituted syscalls are not kernel/signal acceptance. */
#include <assert.h>
#include <fcntl.h>
#include <stdarg.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <unistd.h>

static int fixture_open(const char *path, int flags, ...);
static int fixture_close(int fd);
static int fixture_ioctl(int fd, unsigned long request, ...);
static int fixture_prctl(int option, ...);
#define open fixture_open
#define close fixture_close
#define ioctl fixture_ioctl
#define prctl fixture_prctl
#define main client_main
#include "../mutex_signal_client.c"
#undef main
#undef open
#undef close
#undef ioctl
#undef prctl

static unsigned int calls, closes, expected_role, expected_mode;
static int first_error, second_error, delivered;

static int fixture_open(const char *path, int flags, ...)
{
	assert(!strcmp(path, "/dev/lock_dev") && flags == O_RDWR);
	return 7;
}

static int fixture_close(int fd)
{
	assert(fd == 7);
	closes++;
	return 0;
}

static int fixture_prctl(int option, ...)
{
	assert(option == PR_SET_NAME);
	return 0;
}

static int fixture_ioctl(int fd, unsigned long request, ...)
{
	const struct test_args *args;
	va_list ap;
	int i;

	va_start(ap, request);
	args = va_arg(ap, const struct test_args *);
	va_end(ap);
	assert(fd == 7 && request == IOC_RUN_TEST && args->loop_count == 1);
	assert(args->role == expected_role && args->mode == expected_mode);
	calls++;
	assert(calls <= 2);
	if (calls == 1)
		for (i = 0; i < delivered; i++)
			notice_signal(SIGUSR1);
	errno = calls == 1 ? first_error : second_error;
	return errno ? -1 : 0;
}

int main(void)
{
	char *args[] = { "client", "0", "kd_native", "parallel-peer", NULL };
	unsigned int lane, variant, rounds = 0;

	for (lane = 0; lane < 2; lane++) {
		args[1] = lane ? "1" : "0";
		expected_role = 22 + lane;
		expected_mode = 3;
		for (variant = 0; variant < 6; variant++) {
			calls = closes = signals = 0;
			first_error = variant == 1 ? 0 :
				      variant == 2 ? EINVAL :
						     EINTR;
			second_error = variant == 3 ? EINTR : 0;
			delivered = variant == 4 ? 0 : variant == 5 ? 2 : 1;
			assert(client_main(4, args) == (variant != 0));
			assert(calls == (variant == 0 || variant == 3 ? 2 : 1));
			assert(closes == 1);
			rounds++;
		}
		/* Existing plain signal clients remain one ioctl, including the
		 * role-1 peer that must not see a signal or retry. */
		calls = closes = signals = 0;
		expected_role = 0x10000000U | lane;
		first_error = lane ? 0 : EINTR;
		delivered = lane ? 0 : 1;
		assert(!client_main(3, args));
		assert(calls == 1 && closes == 1);
		rounds++;
	}
	/* The original waiter never retries EINTR. Only a successful one-ioctl
	 * return with one delivered SIGUSR1 is accepted; fatal exit is live-only. */
	args[2] = "klock_test";
	args[3] = "parallel-waiter";
	expected_mode = 3;
	for (lane = 0; lane < 2; lane++) {
		args[1] = lane ? "1" : "0";
		expected_role = 8 * lane + 2;
		for (variant = 0; variant < 4; variant++) {
			calls = closes = signals = 0;
			first_error = variant == 1 ? EINTR : 0;
			delivered = variant == 2 ? 0 : variant == 3 ? 2 : 1;
			assert(client_main(4, args) == (variant != 0));
			assert(calls == 1 && closes == 1);
			rounds++;
		}
	}
	args[2] = "kd_native";
	args[1] = "0";
	for (variant = 0; variant < 2; variant++) {
		calls = closes = signals = 0;
		args[3] = variant ? "pending-int" : "race-int";
		expected_role = variant ? 0x80000000U : 0x10000000U;
		expected_mode = variant ? 4 : 3;
		first_error = variant ? 0 : EINTR;
		delivered = 1;
		assert(!client_main(4, args));
		assert(calls == 1 && closes == 1);
		rounds++;
	}
	calls = closes = signals = 0;
	args[3] = "parallel-peer";
	args[2] = "klock_test";
	assert(client_main(4, args) == 2 && !calls && !closes);
	args[3] = "parallel-waiter";
	args[2] = "kd_native";
	assert(client_main(4, args) == 2 && !calls && !closes);
	printf("parallel client fixture: %u valid/error rounds and invalid target pass\n",
	       rounds);
	return 0;
}
