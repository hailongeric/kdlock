// SPDX-License-Identifier: GPL-2.0
/* One ioctl per process: no automatic EINTR retry or ambiguous thread target. */
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

int main(int argc, char **argv)
{
	struct test_args args = { .loop_count = 1, .work_load = 1, .mode = 3 };
	struct sigaction action = { .sa_handler = notice_signal };
	int role, fd, ret, error;
	int race = 0;
	int pending_signal = 0;
	int pending_race = 0;
	sigset_t block, previous;

	if ((argc != 3 && argc != 4) ||
	    (strcmp(argv[1], "0") && strcmp(argv[1], "1")) ||
	    (strcmp(argv[2], "klock_test") && strcmp(argv[2], "kd_native")))
		return 2;
	role = argv[1][0] - '0';
	if (argc == 4) {
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
		if (role || (!race && !pending_signal))
			return 2;
	}
	args.role = 0x10000000U | role;
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
