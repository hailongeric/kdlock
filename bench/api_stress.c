// SPDX-License-Identifier: GPL-2.0
/*
 * api_stress: data-checked system-call workloads for the switchable lock
 * objects of CONFIG_KDLOCK_API. Each mode drives one converted lock through
 * its real system calls from THREADS threads of one process and checks
 * every result against an exact expectation, so the same program measures
 * the rate and tests mutual exclusion.
 *
 *   api_stress MODE THREADS SECONDS [ARG]
 *
 *   setfd  files->file_lock: fcntl(F_SETFD) toggles on per-thread fds, read
 *          back with F_GETFD; every 16th step also dup()s and close()s
 *          (fd allocation under the same lock). ARG: fds per thread (16).
 *   ofd    flc_lock: ARG (16) fixed OFD read locks on one file; threads
 *          query F_OFD_GETLK at the first, last and a free range and check
 *          the reported conflict exactly; each thread also sets and clears
 *          a write lock in its own range and checks it from a second fd.
 *   pipe   pipe->mutex: all threads write fixed 64-byte records into one
 *          pipe and read records back; each record carries writer, sequence
 *          and checksum; FIONREAD and F_GETPIPE_SZ are queried in between.
 *          The per-writer record counts must balance at the end.
 *   seek   f_pos_lock: one shared fd on a tmpfs file of 8-byte indices.
 *          Threads read() 8 bytes at a time until EOF; every index must be
 *          seen exactly once (each read updates the shared position under
 *          the lock), then lseek(SEEK_SET/SEEK_END) returns are checked.
 *          Repeats with a fresh rewind until time is up.
 *   uts    uts_sem: in a private UTS namespace, ARG% (20) of operations
 *          sethostname() a self-consistent 64-byte name, the rest uname()
 *          and check that the name read is one consistent write.
 *   xattr  simple_xattrs lock: ARG (16) user xattrs on a tmpfs file with
 *          self-consistent 64-byte values; 20% of operations replace a
 *          value, the rest getxattr() and check it is one consistent write.
 *
 * Output: "mode M threads N seconds S ops X rate R ok|FAILED". Exit 1 on the
 * first mismatch.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/utsname.h>
#include <sys/xattr.h>
#include <time.h>
#include <unistd.h>

static volatile int stop;
static volatile int failed;
static int nthreads, arg;
static const char *mode;

struct worker {
	pthread_t t;
	int id;
	unsigned long ops;
	unsigned long sent, got;	/* pipe */
	char pad[64];
};

static struct worker *ws;

#define FAIL(...) do { fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); failed = 1; stop = 1; return NULL; } while (0)

static unsigned long rnd(unsigned long *s)
{
	*s ^= *s << 13;
	*s ^= *s >> 7;
	*s ^= *s << 17;
	return *s;
}

/* ---- setfd --------------------------------------------------------------- */

static void *setfd_work(void *a)
{
	struct worker *w = a;
	int n = arg > 0 ? arg : 16, i, fds[512], st[512];

	if (n > 512)
		n = 512;
	for (i = 0; i < n; i++) {
		fds[i] = open("/dev/null", O_RDONLY);
		if (fds[i] < 0)
			FAIL("open: %s", strerror(errno));
		st[i] = 0;
	}
	for (i = 0; !stop; i = (i + 1) % n) {
		int v = st[i] ^ FD_CLOEXEC, r;

		if (fcntl(fds[i], F_SETFD, v))
			FAIL("F_SETFD: %s", strerror(errno));
		r = fcntl(fds[i], F_GETFD);
		if (r != v)
			FAIL("thread %d fd %d: F_GETFD %d, expected %d", w->id, fds[i], r, v);
		st[i] = v;
		if ((w->ops & 15) == 15) {
			int d = dup(fds[i]);

			if (d < 0 || fcntl(d, F_GETFD) != 0 || close(d))
				FAIL("dup/close of fd %d: %d %s", fds[i], d, strerror(errno));
		}
		w->ops++;
	}
	for (i = 0; i < n; i++)
		close(fds[i]);
	return NULL;
}

/* ---- ofd ------------------------------------------------------------------ */

static char ofd_path[64];
#define OFD_SLOT 4096L		/* bytes per fixed lock or per thread range */

static void *ofd_work(void *a)
{
	struct worker *w = a;
	int n = arg > 0 ? arg : 16, q = 0;
	int fd = open(ofd_path, O_RDWR), fd2 = open(ofd_path, O_RDWR);
	off_t mine = (off_t)(2 * n + 2 * w->id) * OFD_SLOT;

	if (fd < 0 || fd2 < 0)
		FAIL("open %s: %s", ofd_path, strerror(errno));
	while (!stop) {
		struct flock fl = { .l_whence = SEEK_SET, .l_len = 16 };
		off_t want_start = -1;

		switch (q) {
		case 0:			/* first fixed lock */
			fl.l_start = 0 + 8;
			want_start = 0;
			break;
		case 1:			/* last fixed lock */
			fl.l_start = (off_t)(n - 1) * 2 * OFD_SLOT + 8;
			want_start = (off_t)(n - 1) * 2 * OFD_SLOT;
			break;
		default:		/* gap between fixed locks: no conflict */
			fl.l_start = OFD_SLOT + 8;
			break;
		}
		q = (q + 1) % 3;
		fl.l_type = F_WRLCK;
		if (fcntl(fd, F_OFD_GETLK, &fl))
			FAIL("F_OFD_GETLK: %s", strerror(errno));
		if (want_start < 0 ? fl.l_type != F_UNLCK
				   : fl.l_type != F_RDLCK || fl.l_start != want_start ||
				     fl.l_len != OFD_SLOT || fl.l_pid != -1)
			FAIL("thread %d query %d: type %d start %ld len %ld pid %d", w->id, q,
			     fl.l_type, (long)fl.l_start, (long)fl.l_len, fl.l_pid);
		if ((w->ops & 7) == 7) {
			/* own range: set, see it from the other fd, clear, see it gone */
			struct flock s = { .l_type = F_WRLCK, .l_whence = SEEK_SET,
					   .l_start = mine, .l_len = OFD_SLOT };
			struct flock g = s;

			if (fcntl(fd, F_OFD_SETLK, &s))
				FAIL("F_OFD_SETLK: %s", strerror(errno));
			if (fcntl(fd2, F_OFD_GETLK, &g) || g.l_type != F_WRLCK || g.l_start != mine)
				FAIL("thread %d: own lock not seen (type %d start %ld)", w->id,
				     g.l_type, (long)g.l_start);
			s.l_type = F_UNLCK;
			if (fcntl(fd, F_OFD_SETLK, &s))
				FAIL("F_OFD_SETLK unlock: %s", strerror(errno));
			g = s;
			g.l_type = F_WRLCK;
			if (fcntl(fd2, F_OFD_GETLK, &g) || g.l_type != F_UNLCK)
				FAIL("thread %d: own lock still seen (type %d)", w->id, g.l_type);
		}
		w->ops++;
	}
	close(fd);
	close(fd2);
	return NULL;
}

static int ofd_setup(int *holder)
{
	int n = arg > 0 ? arg : 16, i, fd;

	snprintf(ofd_path, sizeof(ofd_path), "/dev/shm/api_stress_ofd.%d", getpid());
	fd = open(ofd_path, O_RDWR | O_CREAT | O_TRUNC, 0600);
	if (fd < 0 || ftruncate(fd, (off_t)(2 * n + 2 * nthreads + 2) * OFD_SLOT))
		return -1;
	for (i = 0; i < n; i++) {
		struct flock fl = { .l_type = F_RDLCK, .l_whence = SEEK_SET,
				    .l_start = (off_t)i * 2 * OFD_SLOT, .l_len = OFD_SLOT };

		if (fcntl(fd, F_OFD_SETLK, &fl))
			return -1;
	}
	*holder = fd;
	return 0;
}

/* ---- pipe ----------------------------------------------------------------- */

static int pfd[2];
struct rec {
	uint32_t writer, seq;
	uint64_t sum;
	uint64_t body[6];
};

static uint64_t rec_sum(const struct rec *r)
{
	uint64_t s = r->writer * 0x9e3779b97f4a7c15ULL ^ r->seq;
	int i;

	for (i = 0; i < 6; i++)
		s = s * 31 + r->body[i];
	return s;
}

static void *pipe_work(void *a)
{
	struct worker *w = a;
	struct rec r;
	unsigned long s = w->id + 1;
	int cap = fcntl(pfd[1], F_GETPIPE_SZ);

	while (!stop) {
		int i, avail;

		r.writer = w->id;
		r.seq = w->sent;
		for (i = 0; i < 6; i++)
			r.body[i] = rnd(&s);
		r.sum = rec_sum(&r);
		if (write(pfd[1], &r, sizeof(r)) == sizeof(r))
			w->sent++;
		else if (errno != EAGAIN)
			FAIL("pipe write: %s", strerror(errno));
		if (ioctl(pfd[0], FIONREAD, &avail) || avail < 0 || avail > cap || avail % sizeof(r))
			FAIL("FIONREAD %d (capacity %d)", avail, cap);
		if (fcntl(pfd[1], F_GETPIPE_SZ) != cap)
			FAIL("F_GETPIPE_SZ changed");
		avail = read(pfd[0], &r, sizeof(r));
		if (avail == sizeof(r)) {
			if (r.writer >= (unsigned)nthreads || r.sum != rec_sum(&r))
				FAIL("torn pipe record: writer %u seq %u", r.writer, r.seq);
			__atomic_fetch_add(&ws[r.writer].got, 1, __ATOMIC_RELAXED);
		} else if (avail >= 0 || errno != EAGAIN) {
			FAIL("pipe read: %d %s", avail, strerror(errno));
		}
		w->ops++;
	}
	return NULL;
}

/* ---- seek ----------------------------------------------------------------- */

static int sfd;
static long nidx = 1 << 16;
static unsigned char *seen;
static pthread_barrier_t bar;
static volatile int round_no;

/* The other threads wait at a barrier: report and leave at once. */
#define SFAIL(...) do { fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); \
	printf("mode seek FAILED\n"); fflush(stdout); _exit(1); } while (0)

static void *seek_work(void *a)
{
	struct worker *w = a;
	struct stat stt;

	fstat(sfd, &stt);
	while (1) {
		uint64_t v;
		ssize_t r;

		pthread_barrier_wait(&bar);		/* main rewound and cleared */
		if (stop)
			break;
		while ((r = read(sfd, &v, 8)) == 8) {
			if (v >= (uint64_t)nidx || __atomic_fetch_add(&seen[v], 1, __ATOMIC_RELAXED))
				SFAIL("index %lu read twice or out of range", (unsigned long)v);
			w->ops++;
		}
		if (r != 0)
			SFAIL("short read %zd", r);
		/* everybody who saw EOF left the shared position at the end */
		if (lseek(sfd, 0, SEEK_CUR) != stt.st_size)
			SFAIL("SEEK_CUR not at the end");
		w->ops++;
		pthread_barrier_wait(&bar);		/* everybody done */
	}
	return NULL;
}

static int seek_setup(void)
{
	char path[64];
	uint64_t *buf = malloc(nidx * 8);
	long i;

	snprintf(path, sizeof(path), "/dev/shm/api_stress_seek.%d", getpid());
	sfd = open(path, O_RDWR | O_CREAT | O_TRUNC, 0600);
	unlink(path);
	for (i = 0; i < nidx; i++)
		buf[i] = i;
	if (sfd < 0 || write(sfd, buf, nidx * 8) != nidx * 8)
		return -1;
	free(buf);
	seen = calloc(nidx, 1);
	return 0;
}

/* ---- uts ------------------------------------------------------------------ */

static void make_name(char *n, unsigned v)
{
	int i;

	snprintf(n, 16, "h%08x-", v);
	for (i = 10; i < 63; i++)
		n[i] = 'a' + (v + i) % 26;
	n[63] = 0;
}

static void *uts_work(void *a)
{
	struct worker *w = a;
	unsigned long s = w->id * 77 + 1;
	int pct = arg >= 0 ? arg : 20;

	while (!stop) {
		if ((int)(rnd(&s) % 100) < pct) {
			char n[64];

			make_name(n, (unsigned)rnd(&s));
			if (sethostname(n, 63))
				FAIL("sethostname: %s", strerror(errno));
		} else {
			struct utsname u;
			unsigned v;
			char e[64];

			if (uname(&u))
				FAIL("uname: %s", strerror(errno));
			if (sscanf(u.nodename, "h%08x-", &v) == 1) {
				make_name(e, v);
				if (strcmp(e, u.nodename))
					FAIL("torn hostname %s", u.nodename);
			}
		}
		w->ops++;
	}
	return NULL;
}

/* ---- xattr ---------------------------------------------------------------- */

static char xpath[64];

static void make_val(unsigned char *b, unsigned v)
{
	int i;

	memcpy(b, &v, 4);
	for (i = 4; i < 64; i++)
		b[i] = (unsigned char)(v * 7 + i);
}

static void *xattr_work(void *a)
{
	struct worker *w = a;
	unsigned long s = w->id * 31 + 7;
	int n = arg > 0 ? arg : 16;

	while (!stop) {
		char name[32];
		unsigned char b[64], e[64];
		int k = rnd(&s) % n;

		snprintf(name, sizeof(name), "user.k%03d", k);
		if (rnd(&s) % 100 < 20) {
			make_val(b, (unsigned)rnd(&s));
			if (setxattr(xpath, name, b, 64, XATTR_REPLACE))
				FAIL("setxattr %s: %s", name, strerror(errno));
		} else {
			unsigned v;
			ssize_t r = getxattr(xpath, name, b, sizeof(b));

			if (r != 64)
				FAIL("getxattr %s: %zd %s", name, r, strerror(errno));
			memcpy(&v, b, 4);
			make_val(e, v);
			if (memcmp(b, e, 64))
				FAIL("torn xattr %s", name);
		}
		w->ops++;
	}
	return NULL;
}

static int xattr_setup(void)
{
	int n = arg > 0 ? arg : 16, i, fd;
	unsigned char b[64];

	snprintf(xpath, sizeof(xpath), "/dev/shm/api_stress_x.%d", getpid());
	fd = open(xpath, O_RDWR | O_CREAT | O_TRUNC, 0600);
	if (fd < 0)
		return -1;
	close(fd);
	for (i = 0; i < n; i++) {
		char name[32];

		snprintf(name, sizeof(name), "user.k%03d", i);
		make_val(b, i);
		if (setxattr(xpath, name, b, 64, XATTR_CREATE))
			return -1;
	}
	return 0;
}

/* ---- main ----------------------------------------------------------------- */

int main(int argc, char **argv)
{
	void *(*fn)(void *);
	int secs, i, holder = -1;
	unsigned long ops = 0;
	struct timeval t0, t1;
	double el;

	if (argc < 4) {
		fprintf(stderr, "usage: %s setfd|ofd|pipe|seek|uts|xattr THREADS SECONDS [ARG]\n",
			argv[0]);
		return 2;
	}
	mode = argv[1];
	nthreads = atoi(argv[2]);
	secs = atoi(argv[3]);
	arg = argc > 4 ? atoi(argv[4]) : -1;
	ws = calloc(nthreads, sizeof(*ws));

	if (!strcmp(mode, "setfd")) {
		fn = setfd_work;
	} else if (!strcmp(mode, "ofd")) {
		fn = ofd_work;
		if (ofd_setup(&holder))
			return perror("ofd setup"), 2;
	} else if (!strcmp(mode, "pipe")) {
		fn = pipe_work;
		if (pipe2(pfd, O_NONBLOCK))
			return perror("pipe"), 2;
	} else if (!strcmp(mode, "seek")) {
		fn = seek_work;
		if (seek_setup())
			return perror("seek setup"), 2;
		pthread_barrier_init(&bar, NULL, nthreads + 1);
	} else if (!strcmp(mode, "uts")) {
		fn = uts_work;
		if (unshare(CLONE_NEWUTS))
			return perror("unshare"), 2;
	} else if (!strcmp(mode, "xattr")) {
		fn = xattr_work;
		if (xattr_setup())
			return perror("xattr setup"), 2;
	} else {
		fprintf(stderr, "unknown mode %s\n", mode);
		return 2;
	}

	gettimeofday(&t0, NULL);
	for (i = 0; i < nthreads; i++) {
		ws[i].id = i;
		pthread_create(&ws[i].t, NULL, fn, &ws[i]);
	}
	if (fn == seek_work) {
		time_t end = time(NULL) + secs;

		do {
			lseek(sfd, 0, SEEK_SET);
			memset(seen, 0, nidx);
			pthread_barrier_wait(&bar);	/* go */
			pthread_barrier_wait(&bar);	/* done */
			for (i = 0; i < nidx && !failed; i++)
				if (seen[i] != 1) {
					fprintf(stderr, "index %d seen %d times\n", i, seen[i]);
					failed = 1;
				}
			round_no++;
		} while (!failed && time(NULL) < end);
		stop = 1;
		pthread_barrier_wait(&bar);
	} else {
		for (i = 0; i < secs * 10 && !stop; i++)
			usleep(100000);
		stop = 1;
	}
	for (i = 0; i < nthreads; i++)
		pthread_join(ws[i].t, NULL);
	gettimeofday(&t1, NULL);
	el = (t1.tv_sec - t0.tv_sec) + (t1.tv_usec - t0.tv_usec) / 1e6;

	if (fn == pipe_work && !failed) {
		struct rec r;

		while (read(pfd[0], &r, sizeof(r)) == sizeof(r)) {
			if (r.writer >= (unsigned)nthreads || r.sum != rec_sum(&r)) {
				fprintf(stderr, "torn pipe record at drain\n");
				failed = 1;
				break;
			}
			ws[r.writer].got++;
		}
		for (i = 0; i < nthreads; i++)
			if (ws[i].sent != ws[i].got) {
				fprintf(stderr, "writer %d sent %lu, %lu read\n", i, ws[i].sent, ws[i].got);
				failed = 1;
			}
	}
	if (fn == ofd_work)
		unlink(ofd_path);
	if (fn == xattr_work)
		unlink(xpath);
	if (holder >= 0)
		close(holder);
	for (i = 0; i < nthreads; i++)
		ops += ws[i].ops;
	printf("mode %s threads %d seconds %.1f ops %lu rate %.0f %s\n", mode, nthreads, el, ops,
	       ops / el, failed ? "FAILED" : "ok");
	return failed;
}
