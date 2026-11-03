/* Actual syscall participants of one immutable files_struct binding.
 * Control ioctls select/query setup; every protected operation is a syscall. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "../../../../include/kd_api_control.h"

static int control, stable_fd, backend;
static struct kd_api_query original;
static struct stat stable_stat;
static int stable_flags;
static unsigned int cases;

static void fail(const char *what)
{
	fprintf(stderr, "setfd semantic failure: %s: %s\n", what, strerror(errno));
	exit(1);
}
#define CHECK(condition, what) do { if (!(condition)) { errno = EPROTO; fail(what); } } while (0)

static void named(void)
{
	if (prctl(PR_SET_NAME, "sc_worker")) fail("task name");
}

static struct timespec deadline(unsigned int seconds)
{
	struct timespec result;
	if (clock_gettime(CLOCK_REALTIME, &result)) fail("clock");
	result.tv_sec += seconds;
	return result;
}

static void join(pthread_t task)
{
	struct timespec until = deadline(10);
	int error = pthread_timedjoin_np(task, NULL, &until);
	if (error) { errno = error; fail("joined task required; timeout is not drain"); }
}

static struct kd_api_query query(void)
{
	struct kd_api_query value = {.version = KD_API_VERSION, .fd = -1};
	if (ioctl(control, KD_API_QUERY, &value)) fail("files binding query");
	CHECK(value.version == KD_API_VERSION && value.kind == KD_API_KIND_FILES &&
	      value.object && value.lock && value.entries[0] && value.entries[1] &&
	      value.entries[2] && value.backend <= KD_API_BACKEND_KD &&
	      !!value.provider == (value.backend == KD_API_BACKEND_KD), "files binding fields");
	return value;
}

static void same_binding(void)
{
	struct kd_api_query value = query();
	CHECK(!memcmp(&value, &original, sizeof(value)), "binding changed for live files object");
}

static void record(const char *name, unsigned int operations)
{
	same_binding();
	printf("{\"case\":\"%s\",\"passed\":true,\"joined\":true,\"backend\":%d,"
	       "\"object\":%llu,\"lock\":%llu,\"provider\":%llu,\"operations\":%u}\n",
	       name, backend, (unsigned long long)original.object,
	       (unsigned long long)original.lock, (unsigned long long)original.provider, operations);
	fflush(stdout);
	cases++;
}

struct holder {
	pthread_barrier_t barrier;
	struct kd_api_query before, after;
};

static void *hold_files(void *argument)
{
	struct holder *holder = argument;
	named();
	holder->before = query();
	pthread_barrier_wait(&holder->barrier);
	pthread_barrier_wait(&holder->barrier);
	holder->after = query();
	return NULL;
}

static struct kd_api_query copy_files(bool select_kd)
{
	struct holder holder;
	pthread_t task;
	int error = pthread_barrier_init(&holder.barrier, NULL, 2);
	if (!error) error = pthread_create(&task, NULL, hold_files, &holder);
	if (error) { errno = error; fail("files holder"); }
	pthread_barrier_wait(&holder.barrier);
	struct kd_api_select selection = {.version = KD_API_VERSION, .files_budget = select_kd};
	if (ioctl(control, KD_API_SELECT, &selection)) fail("files selector");
	if (unshare(CLONE_FILES)) fail("actual files copy");
	struct kd_api_query current = query();
	if (ioctl(control, KD_API_CANCEL)) fail("selector cancel");
	pthread_barrier_wait(&holder.barrier);
	join(task);
	CHECK(!memcmp(&holder.before, &holder.after, sizeof(holder.before)), "old files binding changed");
	CHECK(current.object != holder.before.object, "unshare did not create a distinct files object");
	CHECK(current.backend == (select_kd ? KD_API_BACKEND_KD : KD_API_BACKEND_NATIVE), "new files backend");
	pthread_barrier_destroy(&holder.barrier);
	return current;
}

static int fdinfo_flags(int *result)
{
	char name[96], line[256];
	snprintf(name, sizeof(name), "/proc/self/fdinfo/%d", stable_fd);
	FILE *file = fopen(name, "r");
	if (!file) return errno;
	bool found = false;
	unsigned int flags = 0;
	while (fgets(line, sizeof(line), file)) {
		if (sscanf(line, "flags:\t%o", &flags) == 1) { found = true; break; }
	}
	int error = ferror(file) ? EIO : 0;
	if (fclose(file) && !error) error = errno;
	if (!found && !error) error = EPROTO;
	*result = (int)flags;
	return error;
}

static void flags_and_duplicates(void)
{
	for (int flag = 0; flag <= FD_CLOEXEC; flag++) {
		if (fcntl(stable_fd, F_SETFD, flag)) fail("F_SETFD");
		CHECK(fcntl(stable_fd, F_GETFD) == flag, "F_GETFD stable value");
		int proc_flags;
		CHECK(!fdinfo_flags(&proc_flags) && (proc_flags & O_CLOEXEC) == (flag ? O_CLOEXEC : 0) &&
		      (proc_flags & ~O_CLOEXEC) == stable_flags, "stable proc fdinfo flags");
		for (int cloexec = 0; cloexec <= 1; cloexec++) {
			int duplicate = fcntl(stable_fd, cloexec ? F_DUPFD_CLOEXEC : F_DUPFD, 256);
			if (duplicate < 0) fail("duplicate/expand table");
			struct stat value;
			CHECK(!fstat(duplicate, &value) && value.st_dev == stable_stat.st_dev &&
			      value.st_ino == stable_stat.st_ino &&
			      fcntl(duplicate, F_GETFD) == (cloexec ? FD_CLOEXEC : 0), "duplicate flags and identity");
			if (close(duplicate)) fail("close duplicate");
		}
	}
	record("flags_and_duplicates", 6);
}

struct participant { int kind, error; unsigned int completed; pthread_barrier_t *barrier; };

static void *participant(void *argument)
{
	struct participant *worker = argument;
	named();
	same_binding();
	pthread_barrier_wait(worker->barrier);
	unsigned int limit = worker->kind == 2 ? 2048 : 8192;
	for (unsigned int i = 0; i < limit && !worker->error; i++) {
		if (worker->kind == 0) {
			if (fcntl(stable_fd, F_SETFD, (i & 1) ? FD_CLOEXEC : 0)) worker->error = errno;
		} else if (worker->kind == 1) {
			int fd = dup(stable_fd);
			if (fd < 0) { worker->error = errno; break; }
			struct stat value;
			if (fstat(fd, &value) || value.st_dev != stable_stat.st_dev ||
			    value.st_ino != stable_stat.st_ino || fcntl(fd, F_GETFD) != 0)
				worker->error = EPROTO;
			if (close(fd) && !worker->error) worker->error = errno;
		} else {
			int flags;
			worker->error = fdinfo_flags(&flags);
			/* Concurrent close-on-exec changes allow either bit value; the
			 * open-file status flags and file identity remain invariant. */
			if (!worker->error && (flags & ~O_CLOEXEC) != stable_flags) worker->error = EPROTO;
		}
		if (!worker->error) worker->completed++;
	}
	same_binding();
	return NULL;
}

static void concurrent_participants(void)
{
	pthread_barrier_t barrier;
	pthread_t tasks[3];
	struct participant workers[3];
	int error = pthread_barrier_init(&barrier, NULL, 4);
	if (error) { errno = error; fail("participant barrier"); }
	for (int i = 0; i < 3; i++) {
		workers[i] = (struct participant){.kind = i, .barrier = &barrier};
		error = pthread_create(&tasks[i], NULL, participant, &workers[i]);
		if (error) { errno = error; fail("participant create"); }
	}
	pthread_barrier_wait(&barrier);
	for (int i = 0; i < 3; i++) {
		join(tasks[i]);
		CHECK(!workers[i].error && workers[i].completed == (i == 2 ? 2048U : 8192U), "participant exact completion");
	}
	pthread_barrier_destroy(&barrier);
	CHECK(!fcntl(stable_fd, F_SETFD, FD_CLOEXEC) && fcntl(stable_fd, F_GETFD) == FD_CLOEXEC,
	      "post-join exact flag");
	int flags;
	CHECK(!fdinfo_flags(&flags) && flags == (stable_flags | O_CLOEXEC), "post-join exact proc flags");
	record("concurrent_participants", 18432);
}

static void fork_copy(void)
{
	int report[2];
	if (pipe2(report, O_CLOEXEC)) fail("fork report pipe");
	pid_t child = fork();
	if (child < 0) fail("fork");
	if (!child) {
		close(report[0]);
		struct kd_api_query value = query();
		int ok = value.backend == KD_API_BACKEND_NATIVE && value.object != original.object &&
		         !fcntl(stable_fd, F_SETFD, 0) && fcntl(stable_fd, F_GETFD) == 0;
		ssize_t written = write(report[1], &ok, sizeof(ok));
		close(report[1]);
		_exit(ok && written == (ssize_t)sizeof(ok) ? 0 : 1);
	}
	close(report[1]);
	int status = 0;
	struct timespec pause = {.tv_nsec = 1000000};
	struct timespec until, now;
	if (clock_gettime(CLOCK_MONOTONIC, &until)) fail("fork deadline");
	until.tv_sec += 5;
	for (;;) {
		pid_t waited = waitpid(child, &status, WNOHANG);
		if (waited == child) break;
		if (waited < 0 && errno != EINTR) fail("waitpid");
		if (clock_gettime(CLOCK_MONOTONIC, &now)) fail("fork deadline");
		CHECK(now.tv_sec < until.tv_sec || (now.tv_sec == until.tv_sec && now.tv_nsec < until.tv_nsec),
		      "fork child exit missing; no drain inferred");
		nanosleep(&pause, NULL);
	}
	CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0, "fork child status");
	int ok = 0;
	CHECK(read(report[0], &ok, sizeof(ok)) == (ssize_t)sizeof(ok) && ok, "fork result");
	close(report[0]);
	CHECK(fcntl(stable_fd, F_GETFD) == FD_CLOEXEC, "fork changed parent flags");
	record("fork_copy", 1);
}

int main(int argc, char **argv)
{
	if (argc != 2 || (strcmp(argv[1], "native") && strcmp(argv[1], "kd"))) return 2;
	backend = !strcmp(argv[1], "kd") ? KD_API_BACKEND_KD : KD_API_BACKEND_NATIVE;
	named();
	control = open("/dev/kd_dev", O_RDONLY | O_CLOEXEC);
	if (control < 0) fail("control open");
	original = copy_files(backend == KD_API_BACKEND_KD);
	printf("{\"ready\":true,\"pid\":%d,\"version\":%u,\"kind\":%u,\"backend\":%d,"
	       "\"object\":%llu,\"lock\":%llu,\"provider\":%llu,"
	       "\"entries\":[%llu,%llu,%llu]}\n", getpid(), original.version, original.kind, backend,
	       (unsigned long long)original.object, (unsigned long long)original.lock,
	       (unsigned long long)original.provider, (unsigned long long)original.entries[0],
	       (unsigned long long)original.entries[1], (unsigned long long)original.entries[2]);
	fflush(stdout);
	stable_fd = open("/dev/null", O_RDWR | O_CLOEXEC);
	if (stable_fd < 0 || fstat(stable_fd, &stable_stat) || (stable_flags = fcntl(stable_fd, F_GETFL)) < 0)
		fail("stable descriptor");
	record("binding", 1);
	flags_and_duplicates();
	concurrent_participants();
	fork_copy();
	struct kd_api_query replacement = copy_files(false);
	CHECK(replacement.object != original.object && replacement.backend == KD_API_BACKEND_NATIVE,
	      "one-shot selector was not consumed");
	printf("{\"case\":\"unshare_release\",\"passed\":true,\"joined\":true,\"backend\":%d,"
	       "\"old_object\":%llu,\"new_object\":%llu,\"new_backend\":%u}\n", backend,
	       (unsigned long long)original.object, (unsigned long long)replacement.object, replacement.backend);
	cases++;
	if (close(stable_fd) || close(control)) fail("final descriptors");
	printf("{\"done\":true,\"passed\":true,\"joined\":true,\"control_closed\":true,"
	       "\"backend\":%d,\"cases\":%u}\n", backend, cases);
	return 0;
}
