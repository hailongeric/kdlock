// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <sys/xattr.h>
#include <time.h>
#include <unistd.h>
#include "../../workload_modules/real_api/control.h"

#define MAX_WORKERS 63
#define MAX_SAMPLES 2048
#define BATCH 256
static int nworkers, cpus[MAX_WORKERS], collector = 63, entries = 128;
static int duration_ms = 2000, warmup_ms = 1000, value_size = 64, query_fd, owner_fd;
static uint64_t warmup = 48000, start_ns, deadline_ns;
static bool xattr_mode, setfd_mode, miss, size_only, front;
static bool pipebytes_mode, pipecap_mode, seek_mode, seek_end;
static bool uts_mode, uts_domain;
static char uts_values[2][65];
static struct utsname uts_baseline;
static int control_fd = -1, pipe_capacity;
static int flag_fds[MAX_WORKERS];
static char name[80], expected[4096];
static off_t query_offset;
static pthread_barrier_t barrier;
static bool timed;

struct worker {
	_Alignas(64) _Atomic uint64_t progress;
	uint64_t done, started, finished, cpu_ns;
	uint64_t reads, writes;
	int cpu, observed_cpu, error, fd;
};
static struct worker workers[MAX_WORKERS];
struct sample {
	uint64_t started, finished, counts[MAX_WORKERS];
};
static struct sample samples[MAX_SAMPLES];

static void die(const char *what) { perror(what); exit(1); }
static uint64_t now(clockid_t clock)
{
	struct timespec ts;
	if (clock_gettime(clock, &ts)) die("clock_gettime");
	return (uint64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}
static int pin(int cpu)
{
	cpu_set_t set;
	CPU_ZERO(&set);
	CPU_SET(cpu, &set);
	return sched_setaffinity(0, sizeof(set), &set);
}
static void sleep_until(uint64_t ns)
{
	struct timespec ts = {.tv_sec = ns / 1000000000, .tv_nsec = ns % 1000000000};
	int rc;
	do { rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL); }
	while (rc == EINTR);
	if (rc) { errno = rc; die("clock_nanosleep"); }
}
static void drain_workers(void)
{
	if (control_fd < 0) return;
	/* pthread_join observes clear_child_tid before the kernel necessarily
	 * finishes task exit. The provider releases registrations only after its
	 * exact pid_alive/quiescence checks pass; never bypass those checks. */
	uint64_t deadline = now(CLOCK_MONOTONIC) + 5000000000ULL;
	while (ioctl(control_fd, RA_DRAIN)) {
		if (errno != EBUSY || now(CLOCK_MONOTONIC) >= deadline) die("worker drain");
		sleep_until(now(CLOCK_MONOTONIC) + 1000000);
	}
}
static void value_for(char *buf, int key)
{
	for (int i = 0; i < value_size; i++)
		buf[i] = (unsigned char)((key * 37 + i * 13) ^ (key >> 8));
}
static int operation(void)
{
	if (uts_mode) {
		struct utsname u;
		if (uname(&u)) return errno;
		const char *value = uts_domain ? u.domainname : u.nodename;
		const char *unchanged = uts_domain ? u.nodename : u.domainname;
		return (memcmp(value, uts_values[0], 65) && memcmp(value, uts_values[1], 65)) ||
			memcmp(unchanged, uts_values[0], 65) ||
			memcmp(u.sysname, uts_baseline.sysname, 65) ||
			memcmp(u.release, uts_baseline.release, 65) ||
			memcmp(u.version, uts_baseline.version, 65) ||
			memcmp(u.machine, uts_baseline.machine, 65) ? EILSEQ : 0;
	}
	if (pipebytes_mode) {
		int count = -1;
		return ioctl(query_fd, FIONREAD, &count) || count != entries*4096 ? EIO : 0;
	}
	if (pipecap_mode)
		return fcntl(query_fd, F_GETPIPE_SZ) == pipe_capacity ? 0 : EIO;
	if (seek_mode) {
		off_t offset = seek_end ? -1 : 1;
		return lseek(query_fd, offset, seek_end ? SEEK_END : SEEK_SET) ==
			(seek_end ? entries*4096-1 : 1) ? 0 : EIO;
	}
	if (setfd_mode) {
		int flags = fcntl(query_fd, F_GETFD);
		return flags >= 0 ? 0 : errno;
	}
	if (xattr_mode) {
		char buf[4096];
		ssize_t rc = fgetxattr(query_fd, name, size_only ? NULL : buf,
				    size_only ? 0 : (size_t)value_size);
		if (miss)
			return rc == -1 && errno == ENODATA ? 0 : EIO;
		if (rc != value_size)
			return EIO;
		return size_only || !memcmp(buf, expected, value_size) ? 0 : EILSEQ;
	} else {
		struct flock fl = {.l_type = F_WRLCK, .l_whence = SEEK_SET,
			.l_start = query_offset, .l_len = 1};
		if (fcntl(query_fd, F_OFD_GETLK, &fl))
			return errno;
		if (miss)
			return fl.l_type == F_UNLCK ? 0 : EIO;
		return fl.l_type == F_WRLCK && fl.l_whence == SEEK_SET &&
			fl.l_start == query_offset && fl.l_len == 1 && fl.l_pid == -1 ? 0 : EIO;
	}
}
static bool check_all(void)
{
	if (uts_mode) {
		for (int i = 0; i < 2; i++)
			if (syscall(uts_domain ? SYS_setdomainname : SYS_sethostname,
				    uts_values[i], 64) || operation()) return false;
		return true;
	}
	if (pipebytes_mode || pipecap_mode)
		return operation() == 0;
	if (seek_mode) {
		if (lseek(query_fd, 0, SEEK_SET) != 0 ||
		    lseek(query_fd, 0, SEEK_END) != entries*4096 ||
		    lseek(query_fd, -1, SEEK_SET) != -1 || errno != EINVAL)
			return false;
		return operation() == 0;
	}
	if (setfd_mode) {
		for (int i = 0; i < nworkers; i++) {
			int old = fcntl(flag_fds[i], F_GETFD);
			if (old < 0 || fcntl(flag_fds[i], F_SETFD, 0) ||
			    fcntl(flag_fds[i], F_GETFD) != 0 ||
			    fcntl(flag_fds[i], F_SETFD, FD_CLOEXEC) ||
			    fcntl(flag_fds[i], F_GETFD) != FD_CLOEXEC ||
			    fcntl(flag_fds[i], F_SETFD, old)) return false;
		}
		return true;
	}
	for (int i = 0; i < entries; i++) {
		if (xattr_mode) {
			char key[80], buf[4096], want[4096];
			snprintf(key, sizeof(key), "trusted.kdlock.%08d", i);
			value_for(want, i);
			if (fgetxattr(query_fd, key, buf, value_size) != value_size ||
			    memcmp(buf, want, value_size) ||
			    fgetxattr(query_fd, key, NULL, 0) != value_size) return false;
			if (value_size > 1 && (fgetxattr(query_fd, key, buf, value_size-1) != -1 ||
			    errno != ERANGE)) return false;
		} else {
			struct flock fl = {.l_type = F_WRLCK, .l_whence = SEEK_SET,
				.l_start = i*2, .l_len = 1};
			if (fcntl(query_fd, F_OFD_GETLK, &fl) || fl.l_type != F_WRLCK ||
			    fl.l_start != i*2 || fl.l_len != 1 || fl.l_pid != -1) return false;
			fl = (struct flock){.l_type = F_WRLCK, .l_whence = SEEK_SET,
				.l_start = i*2+1, .l_len = 1};
			if (fcntl(query_fd, F_OFD_GETLK, &fl) || fl.l_type != F_UNLCK) return false;
			fl = (struct flock){.l_type = F_WRLCK, .l_whence = SEEK_SET,
				.l_start = i*2, .l_len = 1};
			if (fcntl(owner_fd, F_OFD_GETLK, &fl) || fl.l_type != F_UNLCK) return false;
		}
	}
	if (xattr_mode) {
		char buf[4096];
		if (fgetxattr(query_fd, "trusted.kdlock.absent", buf, value_size) != -1 ||
		    errno != ENODATA) return false;
	}
	return operation() == 0;
}
static void *worker_main(void *arg)
{
	struct worker *w = arg;
	if (pin(w->cpu)) w->error = errno;
	if (prctl(PR_SET_NAME, "sc_worker")) w->error = errno;
	if (control_fd >= 0 && ioctl(control_fd, RA_REGISTER)) w->error = errno;
	w->observed_cpu = sched_getcpu();
	pthread_barrier_wait(&barrier);
	sleep_until(start_ns);
	w->started = now(CLOCK_MONOTONIC);
	uint64_t cpu_start = now(CLOCK_THREAD_CPUTIME_ID);
	int mix = (w->cpu * 17) % 100;
	while (!w->error) {
		unsigned int count = BATCH;
		if (!timed && w->done < warmup && warmup - w->done < count)
			count = warmup - w->done;
		for (unsigned int i = 0; i < count; i++) {
			if (uts_mode) {
				mix += entries;
				if (mix >= 100) {
					mix -= 100;
					if (syscall(uts_domain ? SYS_setdomainname : SYS_sethostname,
						    uts_values[(w->writes + w->cpu) & 1], 64))
						w->error = errno;
					else w->writes++;
				} else {
					w->error = operation();
					if (!w->error) w->reads++;
				}
			} else if (pipebytes_mode) {
				int bytes = -1;
				if (ioctl(w->fd, FIONREAD, &bytes) || bytes != entries*4096)
					w->error = EIO;
			} else if (pipecap_mode) {
				if (fcntl(w->fd, F_GETPIPE_SZ) != pipe_capacity) w->error = EIO;
			} else if (seek_mode) {
				off_t offset = 1 + ((w->done + w->cpu) & 1023);
				off_t expected_offset = offset;
				if (seek_end) { offset = -offset; expected_offset = entries*4096 + offset; }
				if (lseek(query_fd, offset, seek_end ? SEEK_END : SEEK_SET) != expected_offset)
					w->error = EIO;
			} else if (setfd_mode) {
				int flags = w->done & 1 ? FD_CLOEXEC : 0;
				if (fcntl(w->fd, F_SETFD, flags) || fcntl(w->fd, F_GETFD) != flags)
					w->error = EIO;
			} else {
				w->error = operation();
			}
			if (w->error) break;
			w->done++;
		}
		atomic_store_explicit(&w->progress, w->done, memory_order_relaxed);
		if ((!timed && w->done >= warmup && now(CLOCK_MONOTONIC) >= deadline_ns) ||
		    (timed && now(CLOCK_MONOTONIC) >= deadline_ns)) break;
	}
	w->finished = now(CLOCK_MONOTONIC);
	w->cpu_ns = now(CLOCK_THREAD_CPUTIME_ID) - cpu_start;
	return NULL;
}
static bool run_phase(bool measure)
{
	pthread_t threads[MAX_WORKERS];
	uint64_t total = 0, finish = 0;
	uint64_t reads = 0, writes = 0;
	int nsamples = 0;
	bool ok = true;
	timed = measure;
	memset(workers, 0, sizeof(workers));
	if (pthread_barrier_init(&barrier, NULL, nworkers + 1)) die("barrier");
	for (int i = 0; i < nworkers; i++) {
		workers[i].cpu = cpus[i];
		workers[i].fd = flag_fds[i];
		int rc = pthread_create(&threads[i], NULL, worker_main, &workers[i]);
		if (rc) { errno = rc; die("pthread_create"); }
	}
	start_ns = now(CLOCK_MONOTONIC) + 50000000;
	deadline_ns = start_ns + (uint64_t)(measure ? duration_ms : warmup_ms) * 1000000;
	pthread_barrier_wait(&barrier);
	if (measure) {
		for (uint64_t next = start_ns; next < deadline_ns; next += 10000000) {
			sleep_until(next);
			if (nsamples == MAX_SAMPLES) break;
			struct sample *s = &samples[nsamples++];
			s->started = now(CLOCK_MONOTONIC);
			for (int i = 0; i < nworkers; i++)
				s->counts[i] = atomic_load_explicit(&workers[i].progress, memory_order_relaxed);
			s->finished = now(CLOCK_MONOTONIC);
		}
	}
	for (int i = 0; i < nworkers; i++) {
		pthread_join(threads[i], NULL);
		struct worker *w = &workers[i];
		total += w->done;
		reads += w->reads; writes += w->writes;
		if (w->finished > finish) finish = w->finished;
		if (w->error || w->observed_cpu != w->cpu || !w->done ||
		    (!measure && (w->done < warmup || w->finished < deadline_ns))) ok = false;
	}
	pthread_barrier_destroy(&barrier);
	drain_workers();
	printf("{\"phase\":\"%s\",\"ok\":%s,\"completed\":%llu,"
	       "\"started_ns\":%llu,\"deadline_ns\":%llu,\"finished_ns\":%llu,"
	       "\"wall_ns\":%llu,\"duration_ns\":%llu,\"peak_window_ns\":300000000,"
	       "\"peak_settle_ns\":300000000,\"sample_period_ns\":10000000,"
	       "\"progress_batch\":256,\"collector_cpu\":%d,\"collector_observed_cpu\":%d,"
	       "\"collector_error\":0,\"workers\":[",
	       measure ? "measure" : "warmup", ok ? "true" : "false",
	       (unsigned long long)total, (unsigned long long)start_ns,
	       (unsigned long long)deadline_ns, (unsigned long long)finish,
	       (unsigned long long)(finish-start_ns),
	       (unsigned long long)(measure ? duration_ms : warmup_ms)*1000000,
	       collector, sched_getcpu());
	for (int i = 0; i < nworkers; i++) {
		struct worker *w = &workers[i];
		printf("%s{\"cpu\":%d,\"observed_cpu\":%d,\"error\":%d,\"completed\":%llu,"
		       "\"active_started_ns\":%llu,\"kernel_finished_ns\":%llu,"
		       "\"finished_ns\":%llu,\"cpu_ns\":%llu}", i ? "," : "",
		       w->cpu, w->observed_cpu, w->error, (unsigned long long)w->done,
		       (unsigned long long)w->started, (unsigned long long)w->finished,
		       (unsigned long long)w->finished, (unsigned long long)w->cpu_ns);
	}
	printf("],\"reads\":%llu,\"writes\":%llu,\"samples\":[",
	       (unsigned long long)reads, (unsigned long long)writes);
	for (int i = 0; i < nsamples; i++) {
		struct sample *s = &samples[i];
		printf("%s{\"started_ns\":%llu,\"finished_ns\":%llu,\"completed\":[",
		       i ? "," : "", (unsigned long long)s->started, (unsigned long long)s->finished);
		for (int j = 0; j < nworkers; j++)
			printf("%s%llu", j ? "," : "", (unsigned long long)s->counts[j]);
		printf("]}");
	}
	printf("]}\n");
	fflush(stdout);
	return ok;
}
static void *check_thread(void *arg)
{
	bool *ok = arg;
	*ok = !pin(cpus[0]) && !prctl(PR_SET_NAME, "sc_worker");
	if (*ok && control_fd >= 0) *ok = !ioctl(control_fd, RA_REGISTER);
	if (*ok) *ok = check_all();
	return NULL;
}
static bool checked(void)
{
	pthread_t thread;
	bool ok;
	if (pthread_create(&thread, NULL, check_thread, &ok)) die("check thread");
	pthread_join(thread, NULL);
	drain_workers();
	return ok;
}
int main(int argc, char **argv)
{
	/* Positional, recorded by the controller: kind query entries value bytes,
	 * comma-separated CPUs, collector, duration, warmup count and time. */
	if (argc != 10) { fprintf(stderr, "kind query entries value_bytes cpus collector duration_ms warmup warmup_ms\n"); return 2; }
	xattr_mode = !strcmp(argv[1], "xattr");
	setfd_mode = !strcmp(argv[1], "setfd");
	pipebytes_mode = !strcmp(argv[1], "pipebytes");
	pipecap_mode = !strcmp(argv[1], "pipecap");
	seek_mode = !strcmp(argv[1], "seek");
	uts_mode = !strcmp(argv[1], "utsname");
	uts_domain = !strcmp(argv[2], "domain");
	bool sync_mode = pipebytes_mode || pipecap_mode || seek_mode || uts_mode;
	if (!xattr_mode && !setfd_mode && !sync_mode && strcmp(argv[1], "ofd")) return 2;
	miss = !strcmp(argv[2], "miss");
	size_only = !strcmp(argv[2], "size");
	front = !strcmp(argv[2], "front");
	seek_end = !strcmp(argv[2], "end");
	if (sync_mode ? (uts_mode ? (strcmp(argv[2], "host") && !uts_domain) :
	    seek_mode ? (strcmp(argv[2], "set") && !seek_end) : strcmp(argv[2], "query")) :
	    setfd_mode ? strcmp(argv[2], "toggle") :
	    (!miss && !size_only && !front && strcmp(argv[2], "tail"))) return 2;
	entries = atoi(argv[3]); value_size = atoi(argv[4]);
	collector = atoi(argv[6]); duration_ms = atoi(argv[7]); warmup = strtoull(argv[8], NULL, 10);
	warmup_ms = atoi(argv[9]);
	if (entries < 1 || entries > 4096 || value_size < 1 || value_size > 4096 ||
	    duration_ms < 700 || duration_ms > 10000 || warmup_ms < 0 || warmup_ms > 10000 ||
	    !warmup || collector < 0 || collector >= CPU_SETSIZE || (!xattr_mode && size_only)) return 2;
	char *save, *p = strtok_r(argv[5], ",", &save);
	while (p) {
		int cpu = atoi(p);
		if (nworkers == MAX_WORKERS || cpu < 0 || cpu >= CPU_SETSIZE || cpu == collector) return 2;
		for (int i = 0; i < nworkers; i++) if (cpus[i] == cpu) return 2;
		cpus[nworkers++] = cpu;
		p = strtok_r(NULL, ",", &save);
	}
	if (!nworkers) return 2;
	if (uts_mode) {
		if (entries > 100 || value_size != 64) return 2;
		if (unshare(CLONE_NEWUTS)) die("private UTS namespace");
		for (int i = 0; i < 64; i++) {
			uts_values[0][i] = 'a' + i % 26;
			uts_values[1][i] = 'A' + i % 26;
		}
		if (sethostname(uts_values[0], 64) || setdomainname(uts_values[0], 64) ||
		    uname(&uts_baseline)) die("initialize private UTS metadata");
	}
	/* Initialize data on the first worker's node equally for all arms. */
	if (pin(cpus[0])) die("setup affinity");
	if (pipebytes_mode || pipecap_mode) {
		char dir[] = "/dev/shm/kdlock-api-XXXXXX", fifo[128];
		if (!mkdtemp(dir)) die("mkdtemp");
		snprintf(fifo, sizeof(fifo), "%s/fifo", dir);
		if (mkfifo(fifo, 0600)) die("mkfifo");
		owner_fd = open(fifo, O_RDWR | O_NONBLOCK | O_CLOEXEC);
		if (owner_fd < 0) die("fifo open");
		if (unlink(fifo) || rmdir(dir)) die("remove private fifo name");
		pipe_capacity = fcntl(owner_fd, F_SETPIPE_SZ, entries*4096);
		if (pipe_capacity < entries*4096) die("pipe capacity");
		char page[4096];
		memset(page, 0x5a, sizeof(page));
		for (int i = 0; i < entries; i++)
			if (write(owner_fd, page, sizeof(page)) != sizeof(page)) die("fill pipe");
	} else {
		owner_fd = memfd_create("kdlock-real-api", MFD_CLOEXEC);
	}
	if (owner_fd < 0) die("memfd_create");
	if (xattr_mode) {
		for (int i = 0; i < entries; i++) {
			snprintf(name, sizeof(name), "trusted.kdlock.%08d", i);
			value_for(expected, i);
			if (fsetxattr(owner_fd, name, expected, value_size, XATTR_CREATE)) die("fsetxattr");
		}
		snprintf(name, sizeof(name), "trusted.kdlock.%08d", miss ? entries : (front ? entries-1 : 0));
		value_for(expected, front ? entries-1 : 0);
	} else if (seek_mode) {
		if (ftruncate(owner_fd, (off_t)entries*4096)) die("seek file size");
	} else if (!setfd_mode && !sync_mode) {
		for (int i = 0; i < entries; i++) {
			struct flock fl = {.l_type = F_WRLCK, .l_whence = SEEK_SET, .l_start = i*2, .l_len = 1};
			if (fcntl(owner_fd, F_OFD_SETLK, &fl)) die("F_OFD_SETLK");
		}
		query_offset = miss ? entries*2+1 : (front ? 0 : (entries-1)*2);
	}
	char path[80];
	snprintf(path, sizeof(path), "/proc/%d/fd/%d", getpid(), owner_fd);
	query_fd = open(path, O_RDWR | O_CLOEXEC);
	if (query_fd < 0) die("open independent OFD");
	if (seek_mode) {
		/* Hook and workers must refer to this exact open file description. */
		snprintf(path, sizeof(path), "/proc/%d/fd/%d", getpid(), query_fd);
	}
	if (pipebytes_mode || pipecap_mode)
		for (int i = 0; i < nworkers; i++) {
			flag_fds[i] = open(path, O_RDWR | O_CLOEXEC);
			if (flag_fds[i] < 0) die("pipe worker description");
		}
	if (setfd_mode) {
		struct rlimit limit;
		rlim_t needed = (rlim_t)nworkers*entries + 128;
		if (getrlimit(RLIMIT_NOFILE, &limit)) die("getrlimit");
		if (limit.rlim_cur < needed) {
			limit.rlim_cur = needed;
			if (setrlimit(RLIMIT_NOFILE, &limit)) die("setrlimit");
		}
		for (int i = 0; i < nworkers; i++) {
			/* A separate open file description avoids a shared f_count
			 * bottleneck outside the file-table critical section. Keep
			 * the descriptor spacing while sharing the same files_struct. */
			int independent = open(path, O_RDWR | O_CLOEXEC);
			if (independent < 0) die("open worker description");
			flag_fds[i] = fcntl(independent, F_DUPFD_CLOEXEC, 64 + i*entries);
			if (flag_fds[i] < 0) die("allocate worker descriptor");
			close(independent);
		}
	}
	if (operation()) { errno = EIO; die("stock oracle"); }
	if (pin(collector)) die("collector affinity");
	printf("{\"ready\":true,\"pid\":%d,\"path\":\"%s\"}\n", getpid(), path);
	fflush(stdout);
	char cmd[80];
	while (fgets(cmd, sizeof(cmd), stdin)) {
		if (!strcmp(cmd, "bind\n")) {
			control_fd = open("/dev/real_api_control", O_RDONLY | O_CLOEXEC);
			if (control_fd < 0) die("control open");
			puts("{\"bound\":true}"); fflush(stdout);
		} else if (!strcmp(cmd, "unbind\n")) {
			if (control_fd >= 0) close(control_fd);
			control_fd = -1;
			puts("{\"unbound\":true}"); fflush(stdout);
		} else if (!strcmp(cmd, "warmup\n")) { if (!run_phase(false)) return 1; }
		else if (!strcmp(cmd, "measure\n")) { if (!run_phase(true)) return 1; }
		else if (!strcmp(cmd, "check\n")) {
			bool ok = sync_mode ? checked() : check_all();
			printf("{\"check\":%s}\n", ok ? "true" : "false"); fflush(stdout);
			if (!ok) return 1;
		} else if (!strcmp(cmd, "quit\n")) break;
		else return 2;
	}
	close(query_fd);
	if (setfd_mode || pipebytes_mode || pipecap_mode)
		for (int i = 0; i < nworkers; i++) close(flag_fds[i]);
	close(owner_fd);
	return 0;
}
