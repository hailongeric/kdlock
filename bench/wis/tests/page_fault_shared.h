/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Page faults on one mapping shared by all tasks (kdlock addition, not part
 * of TCLocks' will-it-scale). Included by page_fault_shared{1,2,3}.c, which
 * set PF_MPROTECT and PF_KERNEL_FAULT before including it.
 *
 * testcase_prepare() maps one anonymous private region before the tasks
 * start, so in the threads model every task faults on the same VMA of the
 * same mm. Task t owns the contiguous slice t of PF_PAGES pages; eight
 * neighbouring slices share one page table, so their faults also share
 * its split PTE lock. One pass of a task:
 *
 *   1. fault every page of its slice in, with a user store (the per-VMA
 *      lock path of arch/x86/mm/fault.c) or, with PF_KERNEL_FAULT, with
 *      read() from /dev/zero, whose clear_user() faults from kernel mode;
 *      a kernel-mode fault always takes mmap_lock for reading
 *      (lock_mm_and_find_vma), never the per-VMA lock;
 *   2. store a tag in every page and check it;
 *   3. MADV_DONTNEED the slice (per-VMA lock);
 *   4. with PF_MPROTECT, make the first page of the slice read-only and
 *      writable again. The first call splits the shared VMA and the second
 *      merges it back, both under mmap_lock held for writing and with the
 *      VMA write-locked (vma_start_write), so a fault of any other task in
 *      the VMA meanwhile fails lock_vma_under_rcu() and falls back to
 *      mmap_lock for reading, behind the writer. The page is not present
 *      then, so neither call changes a PTE or flushes the TLB;
 *   5. check that the first page reads zero again (a read fault).
 *
 * Every page faulted counts as one iteration. A check that fails aborts the
 * task: in the threads model the harness then exits non-zero; in the
 * processes model it does not notice, but the aborted task stops counting
 * (the runner treats a rate of 0 as a failure).
 *
 * In the processes model each task has its own copy of the region and its
 * own mm, so nothing is shared; that is the uncontended reference.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#define PF_PAGES	64UL		/* pages per task and pass */
#define PF_MAX_TASKS	1024UL

static char *pf_region;
static unsigned long pf_pgsize;

void testcase_prepare(unsigned long nr_tasks)
{
	pf_pgsize = getpagesize();
	if (nr_tasks > PF_MAX_TASKS) {
		fprintf(stderr, "page_fault_shared: at most %lu tasks\n", PF_MAX_TASKS);
		exit(1);
	}
	pf_region = mmap(NULL, nr_tasks * PF_PAGES * pf_pgsize, PROT_READ | PROT_WRITE,
			 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (pf_region == MAP_FAILED) {
		perror("mmap");
		exit(1);
	}
}

static void pf_fail(const char *what, unsigned long nr, unsigned long i)
{
	fprintf(stderr, "page_fault_shared: task %lu page %lu: %s\n", nr, i, what);
	abort();
}

void testcase(unsigned long long *iterations, unsigned long nr)
{
	unsigned long len = PF_PAGES * pf_pgsize;
	char *c = pf_region + nr * len;
	unsigned long pass = 0;
	int zero = -1;

	if (PF_KERNEL_FAULT) {
		zero = open("/dev/zero", O_RDONLY);
		if (zero < 0)
			pf_fail("open /dev/zero", nr, 0);
	}

	while (1) {
		unsigned long tag = (nr << 32) ^ ++pass;
		unsigned long i;

		/* A pending signal can end the read early; finish it. */
		for (i = 0; PF_KERNEL_FAULT && i < len; ) {
			ssize_t r = read(zero, c + i, len - i);

			if (r > 0)
				i += r;
			else if (r < 0 && errno == EINTR)
				continue;
			else
				pf_fail("read /dev/zero", nr, i / pf_pgsize);
		}
		for (i = 0; i < PF_PAGES; i++) {
			unsigned long *w = (unsigned long *)(c + i * pf_pgsize);

			w[1] = tag ^ i;
			(*iterations)++;
		}
		for (i = 0; i < PF_PAGES; i++) {
			unsigned long *w = (unsigned long *)(c + i * pf_pgsize);

			if (w[0] != 0 || w[1] != (tag ^ i))
				pf_fail("tag", nr, i);
		}
		if (madvise(c, len, MADV_DONTNEED))
			pf_fail("madvise", nr, 0);
		if (PF_MPROTECT) {
			if (mprotect(c, pf_pgsize, PROT_READ))
				pf_fail("mprotect read-only", nr, 0);
			if (mprotect(c, pf_pgsize, PROT_READ | PROT_WRITE))
				pf_fail("mprotect writable", nr, 0);
		}
		if (*(volatile unsigned long *)(c + sizeof(long)) != 0)
			pf_fail("not zero after MADV_DONTNEED", nr, 0);
	}
}
