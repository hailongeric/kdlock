// SPDX-License-Identifier: GPL-2.0
/* Single-process signal target. Only parallel-peer explicitly retries once
 * after exposing EINTR to userspace; all other cases issue one ioctl. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <unistd.h>

struct test_args {
	unsigned long loop_count, work_load;
	unsigned int mode, role;
};
#define IOC_RUN_TEST _IOW('k', 1, struct test_args)
static volatile sig_atomic_t signals;

static void notice_signal(int sig)
{
	if (sig == SIGUSR1)
		signals++;
}

static int parallel_peer(int fd, struct test_args *args, int lane)
{
	int ret, error;

	/* The first ioctl must expose cancellation to userspace. Retry exactly
	 * once only after observing EINTR and the real signal handler; no generic
	 * automatic retry may turn an unexpected native success into a pass. */
	printf("parallel peer client enter: lane=%d pid=%ld\n", lane,
	       (long)getpid());
	fflush(stdout);
	ret = ioctl(fd, IOC_RUN_TEST, args);
	error = ret < 0 ? errno : 0;
	printf("parallel peer client cancelled: lane=%d pid=%ld ret=%d errno=%d signals=%d\n",
	       lane, (long)getpid(), ret, error, signals);
	fflush(stdout);
	if (ret != -1 || error != EINTR || signals != 1)
		return 1;
	ret = ioctl(fd, IOC_RUN_TEST, args);
	error = ret < 0 ? errno : 0;
	printf("parallel peer client return: lane=%d pid=%ld ret=%d errno=%d signals=%d\n",
	       lane, (long)getpid(), ret, error, signals);
	return ret != 0 || error || signals != 1;
}

/* One original waiter, one ioctl. A pending SIGKILL must prevent this return;
 * SIGUSR1 is delivered only after the kernel suffix and both owner ACKs. */
static int parallel_waiter(int fd, struct test_args *args, int lane)
{
	int ret, error;

	printf("parallel waiter client enter: lane=%d pid=%ld\n", lane,
	       (long)getpid());
	fflush(stdout);
	ret = ioctl(fd, IOC_RUN_TEST, args);
	error = ret < 0 ? errno : 0;
	printf("parallel waiter client return: lane=%d pid=%ld ret=%d errno=%d signals=%d\n",
	       lane, (long)getpid(), ret, error, signals);
	return ret != 0 || error || signals != 1;
}

int main(int argc, char **argv)
{
	struct test_args args = { .loop_count = 1, .work_load = 1, .mode = 3 };
	struct sigaction action = { .sa_handler = notice_signal };
	int role, fd, ret, error;
	int race = 0;
	int pending_signal = 0;
	int pending_race = 0;
	int parallel = 0;
	int waiter = 0;
	sigset_t block, previous;

	if ((argc != 3 && argc != 4) ||
	    (strcmp(argv[1], "0") && strcmp(argv[1], "1")) ||
	    (strcmp(argv[2], "klock_test") && strcmp(argv[2], "kd_native")))
		return 2;
	role = argv[1][0] - '0';
	if (argc == 4) {
		parallel = !strcmp(argv[3], "parallel-peer");
		waiter = !strcmp(argv[3], "parallel-waiter");
		pending_race = !strcmp(argv[3], "pending-race-int") ||
			       !strcmp(argv[3], "pending-race-kill");
		pending_signal = (!strcmp(argv[3], "pending-int") ||
				  !strcmp(argv[3], "pending-race-int")) ?
					 SIGUSR1 :
				 (!strcmp(argv[3], "pending-kill") ||
				  !strcmp(argv[3], "pending-race-kill")) ?
					 SIGKILL :
					 0;
		race = !strcmp(argv[3], "race-int")  ? 1 :
		       !strcmp(argv[3], "race-kill") ? 2 :
						       0;
		if ((!parallel && !waiter && (role || (!race && !pending_signal))) ||
		    (parallel && strcmp(argv[2], "kd_native")) ||
		    (waiter && strcmp(argv[2], "klock_test")))
			return 2;
	}
	args.role = 0x10000000U | role;
	if (parallel)
		args.role = 22U + role;
	if (waiter)
		args.role = 8U * role + 2;
	if (pending_signal) {
		/* One process, one ioctl, no EINTR retry: a fatal result must not
		 * be confused with the timeout supervisor or a different pthread.
		 */
		args.mode = 4;
		args.role = 0x80000000U;
		args.work_load = 50000;
		printf("pending client enter: pid=%ld signal=%d\n",
		       (long)getpid(), pending_signal);
		fflush(stdout);
	}
	sigemptyset(&action.sa_mask);
	if (sigaction(SIGUSR1, &action, NULL) ||
	    prctl(PR_SET_NAME, argv[2], 0, 0, 0)) {
		perror("signal/name setup");
		return 1;
	}
	fd = open("/dev/lock_dev", O_RDWR);
	if (fd < 0) {
		perror("open");
		return 1;
	}
	if (parallel || waiter) {
		ret = waiter ? parallel_waiter(fd, &args, role) :
			       parallel_peer(fd, &args, role);
		close(fd);
		return ret;
	}
	ret = ioctl(fd, IOC_RUN_TEST, &args);
	error = ret < 0 ? errno : 0;
	close(fd);
	if (pending_signal) {
		if (pending_race) {
			/* Acquisition may finish its kernel ACK before the signal.
			 * Wait only in userspace, never pin a kernel task/frame for the
			 * observer. SIGKILL may prevent even the ioctl-return log.
			 */
			printf("pending client ioctl: pid=%ld signal=%d ret=%d errno=%d signals=%d\n",
			       (long)getpid(), pending_signal, ret, error,
			       signals);
			fflush(stdout);
			if (ret || error)
				return 1;
			sigemptyset(&block);
			sigaddset(&block, SIGUSR1);
			if (sigprocmask(SIG_BLOCK, &block, &previous))
				return 1;
			while (pending_signal == SIGKILL || !signals)
				sigsuspend(&previous);
			if (sigprocmask(SIG_SETMASK, &previous, NULL))
				return 1;
		}
		printf("pending client return: pid=%ld signal=%d ret=%d errno=%d signals=%d\n",
		       (long)getpid(), pending_signal, ret, error, signals);
		return pending_signal != SIGUSR1 || ret != 0 || error ||
		       signals != 1;
	}
	if (race) {
		if (ret != 0 && (ret != -1 || error != EINTR))
			return 1;
		/* Stay alive when acquisition beats the signal. Blocking before the
		 * flag check avoids losing SIGUSR1 between that check and suspend. */
		sigemptyset(&block);
		sigaddset(&block, SIGUSR1);
		if (sigprocmask(SIG_BLOCK, &block, &previous))
			return 1;
		while (race == 2 || !signals)
			sigsuspend(&previous);
		if (sigprocmask(SIG_SETMASK, &previous, NULL))
			return 1;
	}
	printf("signal client: role=%d pid=%ld ret=%d errno=%d signals=%d\n",
	       role, (long)getpid(), ret, error, signals);
	return race ? signals != 1 :
	       role ? ret != 0 || signals != 0 :
		      ret != -1 || error != EINTR || signals != 1;
}
