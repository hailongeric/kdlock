// SPDX-License-Identifier: GPL-2.0
/*
 * mm_stress: data-checked stress of the mmap lock paths, for correctness
 * of CONFIG_KDLOCK_MM (not a benchmark).
 *
 *   mm_stress THREADS SECONDS
 *
 * All threads share one mm, so the mmap lock is contended. Each thread
 * repeats, on its own mappings, a mix of the operations that take the lock
 * for writing (mmap, munmap, mprotect, mremap, madvise(MADV_DONTNEED) is
 * read-side, brk through large malloc) and page faults (read side or
 * per-VMA lock), and checks every page it wrote. One thread also forks
 * now and then (dup_mmap write-locks the parent's mm); the child checks
 * a mapping it inherited and exits with the result.
 *
 * Prints the operation count and exits non-zero on the first mismatch.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define PG 4096UL

static volatile int stop;
static long page;

struct worker {
	pthread_t t;
	int id;
	unsigned long ops, faults;
	int bad;
};

static unsigned long rnd(unsigned long *s)
{
	*s ^= *s << 13;
	*s ^= *s >> 7;
	*s ^= *s << 17;
	return *s;
}

static int fill_check(unsigned char *p, size_t len, unsigned long tag, int check)
{
	size_t i;

	for (i = 0; i < len; i += page) {
		unsigned long *w = (unsigned long *)(p + i);

		if (check) {
			if (w[0] != (tag ^ i) || w[1] != ~(tag ^ i))
				return -1;
		} else {
			w[0] = tag ^ i;
			w[1] = ~(tag ^ i);
		}
	}
	return 0;
}

static int zero_check(unsigned char *p, size_t len)
{
	size_t i;

	for (i = 0; i < len; i += page)
		if (((unsigned long *)(p + i))[0] || ((unsigned long *)(p + i))[1])
			return -1;
	return 0;
}

#define FAIL(w, what) do { fprintf(stderr, "worker %d: %s failed (%s)\n", (w)->id, what, strerror(errno)); (w)->bad = 1; return NULL; } while (0)
#define BAD(w, what) do { fprintf(stderr, "worker %d: data mismatch after %s (op %d, len %zu)\n", (w)->id, what, op, len); (w)->bad = 1; return NULL; } while (0)

static void *work(void *arg)
{
	struct worker *w = arg;
	unsigned long s = 0x9e3779b97f4a7c15UL * (w->id + 1);

	while (!stop) {
		size_t len = (1 + rnd(&s) % 512) * page;
		unsigned long tag = rnd(&s);
		unsigned char *p, *q;
		int op = rnd(&s) % 6;

		p = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		if (p == MAP_FAILED)
			FAIL(w, "mmap");
		if (zero_check(p, len))
			BAD(w, "mmap (not zero)");
		fill_check(p, len, tag, 0);
		w->faults += len / page;

		switch (op) {
		case 0:		/* mprotect read-only, read back, then writable again */
			if (mprotect(p, len, PROT_READ))
				FAIL(w, "mprotect");
			if (fill_check(p, len, tag, 1))
				BAD(w, "mprotect");
			if (mprotect(p, len, PROT_READ | PROT_WRITE))
				FAIL(w, "mprotect");
			break;
		case 1:		/* grow with mremap (may move) */
			q = mremap(p, len, 2 * len, MREMAP_MAYMOVE);
			if (q == MAP_FAILED)
				FAIL(w, "mremap");
			p = q;
			if (fill_check(p, len, tag, 1) || zero_check(p + len, len))
				BAD(w, "mremap");
			len *= 2;
			fill_check(p, len, tag, 0);
			break;
		case 2:		/* discard and refault */
			if (madvise(p, len, MADV_DONTNEED))
				FAIL(w, "madvise");
			if (zero_check(p, len))
				BAD(w, "madvise");
			fill_check(p, len, tag, 0);
			break;
		case 3:		/* punch a hole: munmap the middle, check both ends */
			if (len >= 3 * page) {
				size_t h = (len / page / 3) * page;

				if (munmap(p + h, h))
					FAIL(w, "munmap middle");
				/* the tail keeps its offsets relative to p */
				for (size_t i = 2 * h; i < len; i += page)
					if (((unsigned long *)(p + i))[0] != (tag ^ i))
						BAD(w, "hole (tail)");
				if (fill_check(p, h, tag, 1))
					BAD(w, "hole (head)");
				/*
				 * Not refilled with MAP_FIXED: another thread may
				 * have mapped the hole by now. Release both ends.
				 */
				if (munmap(p, h) || munmap(p + 2 * h, len - 2 * h))
					FAIL(w, "munmap ends");
				w->ops++;
				continue;
			}
			break;
		case 4: {	/* heap through malloc (brk or mmap) */
			size_t n = (1 + rnd(&s) % 64) * 1024;
			unsigned char *m = malloc(n);

			if (!m)
				FAIL(w, "malloc");
			memset(m, (int)tag, n);
			for (size_t i = 0; i < n; i += 997)
				if (m[i] != (unsigned char)tag) {
					free(m);
					BAD(w, "malloc");
				}
			free(m);
			break;
		}
		default:
			break;
		}
		if (fill_check(p, len, tag, 1))
			BAD(w, "final check");
		if (munmap(p, len))
			FAIL(w, "munmap");
		w->ops++;
	}
	return NULL;
}

/* Fork now and then; the child checks an inherited mapping. */
static int forker(unsigned long *forks, time_t end)
{
	size_t len = 64 * page;
	unsigned char *p = mmap(NULL, len, PROT_READ | PROT_WRITE,
				MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	unsigned long tag = 12345;

	if (p == MAP_FAILED)
		return -1;
	while (time(NULL) < end) {
		pid_t pid;
		int st;

		fill_check(p, len, ++tag, 0);
		pid = fork();
		if (pid < 0)
			return -1;
		if (!pid) {
			int r = fill_check(p, len, tag, 1);

			fill_check(p, len, tag + 1000, 0);	/* COW in the child */
			_exit(r ? 3 : 0);
		}
		if (waitpid(pid, &st, 0) != pid || !WIFEXITED(st) || WEXITSTATUS(st)) {
			fprintf(stderr, "fork child failed: status %#x\n", st);
			return -1;
		}
		if (fill_check(p, len, tag, 1)) {
			fprintf(stderr, "parent data changed by child\n");
			return -1;
		}
		(*forks)++;
		usleep(2000);
	}
	munmap(p, len);
	return 0;
}

int main(int argc, char **argv)
{
	int n = argc > 1 ? atoi(argv[1]) : 8, secs = argc > 2 ? atoi(argv[2]) : 10;
	struct worker *ws = calloc(n, sizeof(*ws));
	unsigned long ops = 0, faults = 0, forks = 0;
	int bad = 0, i;
	time_t end;

	page = sysconf(_SC_PAGESIZE);
	for (i = 0; i < n; i++) {
		ws[i].id = i;
		pthread_create(&ws[i].t, NULL, work, &ws[i]);
	}
	end = time(NULL) + secs;
	/* The main thread forks until the time is up. */
	if (forker(&forks, end))
		bad = 1;
	stop = 1;
	for (i = 0; i < n; i++) {
		pthread_join(ws[i].t, NULL);
		ops += ws[i].ops;
		faults += ws[i].faults;
		bad |= ws[i].bad;
	}
	printf("threads %d seconds %d ops %lu pages %lu forks %lu %s\n",
	       n, secs, ops, faults, forks, bad ? "FAILED" : "ok");
	return bad;
}
