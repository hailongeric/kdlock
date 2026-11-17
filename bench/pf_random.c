// SPDX-License-Identifier: GPL-2.0
/*
 * pf_random: page faults on one large mapping in a pseudo-random order,
 * with the mapping unmapped and mapped again between rounds.
 *
 *   pf_random THREADS SECONDS [-g GB] [-w] [-H]
 *
 * One round:
 *   1. thread 0 maps GB gigabytes of private anonymous memory
 *      (MADV_NOHUGEPAGE unless -H, so every fault is a 4 KB fault);
 *   2. all threads fault the region in: the round walks a pseudo-random
 *      permutation of all page numbers, and thread t takes positions
 *      t, t + THREADS, t + 2 THREADS, ... So every page faults exactly once
 *      per round, from a random thread, in a random order. Neighbouring
 *      pages are not touched one after the other, so fault-around and
 *      huge-page paths do not merge faults;
 *   3. after all threads are done, thread 0 unmaps the region.
 *
 * Without -w a thread reads one word of each page and checks that it is 0
 * (a fresh anonymous page). With -w it writes a tag (round and page number)
 * into each page, and after all threads are done each thread reads its
 * pages back and checks the tags. The program exits non-zero on the first
 * mismatch.
 *
 * Output: rounds; faults per second over the fault phases only; the
 * average fault phase, munmap and mmap times; and pages per second over
 * the whole run.
 */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define PG 4096UL

static int nthreads, do_write, keep_thp;
static unsigned long npages;
static unsigned int kbits;
static double seconds;
static pthread_barrier_t bar;

/* Shared per round, set by thread 0 between barriers. */
static char *volatile region;
static volatile uint64_t seed;
static volatile int stop;
static int bad;			/* mismatches, atomic */

/* Report the first few mismatches only. */
static void mismatch(uint64_t pg, uint64_t v, uint64_t want)
{
	if (__atomic_fetch_add(&bad, 1, __ATOMIC_RELAXED) < 8)
		fprintf(stderr, "page %lu: %#lx, expected %#lx\n",
			(unsigned long)pg, (unsigned long)v, (unsigned long)want);
}

static double now(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/*
 * A bijection of [0, 2^kbits): every step (add, multiply by an odd number,
 * xor with a right shift) is one. Cycle walking turns it into a bijection
 * of [0, npages): apply it again while the value is out of range.
 */
static inline uint64_t mix(uint64_t x, uint64_t s, uint64_t mask)
{
	x = (x + s) & mask;
	x = (x * 0x9E3779B97F4A7C15ULL) & mask;
	x ^= x >> (kbits / 2 + 1);
	x = (x * 0xBF58476D1CE4E5B9ULL) & mask;
	x ^= x >> (kbits / 3 + 1);
	x = (x * 0x94D049BB133111EBULL) & mask;
	x ^= x >> (kbits / 2);
	return x;
}

static inline uint64_t page_at(uint64_t i, uint64_t s)
{
	uint64_t mask = (1ULL << kbits) - 1, x = i;

	do
		x = mix(x, s, mask);
	while (x >= npages);
	return x;
}

struct worker {
	pthread_t t;
	int id;
	unsigned long faults;
};

static struct {
	unsigned long rounds;
	double fault_s, munmap_s, mmap_s;
} tot;

static void map_region(void)
{
	size_t len = npages * PG;
	double t0 = now();
	char *p = mmap(NULL, len, PROT_READ | PROT_WRITE,
		       MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);

	if (p == MAP_FAILED) {
		perror("mmap");
		exit(2);
	}
	if (!keep_thp && madvise(p, len, MADV_NOHUGEPAGE)) {
		perror("madvise");
		exit(2);
	}
	tot.mmap_s += now() - t0;
	region = p;
}

static void *run(void *arg)
{
	struct worker *w = arg;
	double start = now(), t0 = 0;

	for (;;) {
		/* Round start: thread 0 has mapped the region and set the seed. */
		if (w->id == 0) {
			stop = __atomic_load_n(&bad, __ATOMIC_RELAXED) || now() - start >= seconds;
			if (!stop) {
				map_region();
				seed = seed * 6364136223846793005ULL + 1442695040888963407ULL;
				t0 = now();
			}
		}
		pthread_barrier_wait(&bar);
		if (stop)
			break;

		char *base = region;
		uint64_t s = seed;

		for (uint64_t i = w->id; i < npages; i += nthreads) {
			uint64_t pg = page_at(i, s);
			volatile uint64_t *word = (volatile uint64_t *)(base + pg * PG);

			if (do_write) {
				*word = (tot.rounds << 32) ^ pg;
			} else {
				uint64_t v = *word;

				if (v != 0)
					mismatch(pg, v, 0);
			}
			w->faults++;
		}
		pthread_barrier_wait(&bar);
		if (w->id == 0)
			tot.fault_s += now() - t0;

		if (do_write) {
			for (uint64_t i = w->id; i < npages; i += nthreads) {
				uint64_t pg = page_at(i, s);
				uint64_t v = *(volatile uint64_t *)(base + pg * PG);

				if (v != ((tot.rounds << 32) ^ pg))
					mismatch(pg, v, (tot.rounds << 32) ^ pg);
			}
			pthread_barrier_wait(&bar);
		}

		if (w->id == 0) {
			double t1 = now();

			if (munmap(base, npages * PG)) {
				perror("munmap");
				exit(2);
			}
			tot.munmap_s += now() - t1;
			tot.rounds++;
		}
	}
	return NULL;
}

int main(int argc, char **argv)
{
	double gb = 10, t0, el;
	unsigned long faults = 0;
	struct worker *ws;
	int opt;

	if (argc < 3) {
		fprintf(stderr, "usage: %s THREADS SECONDS [-g GB] [-w] [-H]\n", argv[0]);
		return 2;
	}
	nthreads = atoi(argv[1]);
	seconds = atof(argv[2]);
	optind = 3;
	while ((opt = getopt(argc, argv, "g:wH")) != -1) {
		switch (opt) {
		case 'g': gb = atof(optarg); break;
		case 'w': do_write = 1; break;
		case 'H': keep_thp = 1; break;
		default: return 2;
		}
	}
	if (nthreads < 1 || seconds <= 0 || gb <= 0)
		return 2;
	npages = (unsigned long)(gb * (1UL << 30)) / PG;
	for (kbits = 1; (1UL << kbits) < npages; kbits++)
		;
	seed = 0x2545F4914F6CDD1DULL;

	ws = calloc(nthreads, sizeof(*ws));
	pthread_barrier_init(&bar, NULL, nthreads);
	t0 = now();
	for (int i = 0; i < nthreads; i++) {
		ws[i].id = i;
		if (pthread_create(&ws[i].t, NULL, run, &ws[i])) {
			perror("pthread_create");
			return 2;
		}
	}
	for (int i = 0; i < nthreads; i++) {
		pthread_join(ws[i].t, NULL);
		faults += ws[i].faults;
	}
	el = now() - t0;

	printf("threads %d gb %.1f mode %s rounds %lu faults %lu fault_rate %.0f "
	       "fault_ms %.1f munmap_ms %.1f mmap_ms %.3f pages_per_s %.0f %s\n",
	       nthreads, gb, do_write ? "write" : "read", tot.rounds, faults,
	       tot.fault_s > 0 ? faults / tot.fault_s : 0,
	       tot.rounds ? tot.fault_s * 1e3 / tot.rounds : 0,
	       tot.rounds ? tot.munmap_s * 1e3 / tot.rounds : 0,
	       tot.rounds ? tot.mmap_s * 1e3 / tot.rounds : 0,
	       faults / el, bad ? "FAILED" : "ok");
	return bad ? 1 : 0;
}
