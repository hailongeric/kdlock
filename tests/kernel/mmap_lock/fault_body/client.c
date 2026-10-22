// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/userfaultfd.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "payload/api.h"

#define PAGE 4096
#define PAGES 512
static int device, pagemap;
static unsigned char *area;
static unsigned long checks, completed;
struct writer {
	pthread_t thread;
	unsigned int cpu, first, pages, initial;
	_Atomic pid_t tid;
	unsigned long checked;
};
struct phase { struct fb_status status; struct writer workers[FB_WORKERS]; };
static struct phase phases[3];
static unsigned int phase_count;
static pthread_t holder;
static int hold_error;

static void require(int good, const char *message)
{
	checks++;
	if (!good) { fprintf(stderr, "%s (errno=%d: %s)\n", message, errno, strerror(errno)); exit(1); }
}
static void pin(unsigned int cpu)
{
	cpu_set_t set;
	CPU_ZERO(&set); CPU_SET(cpu, &set);
	if (sched_setaffinity(0, sizeof(set), &set)) { perror("affinity"); exit(1); }
}
static struct fb_status status(void)
{
	struct fb_status s;
	require(!ioctl(device, FB_STATUS, &s), "status");
	return s;
}
static void wait_state(unsigned int pending, int held_only)
{
	unsigned int i;
	for (i = 0; i < 10000; i++) {
		struct fb_status s = status();
		if (held_only ? s.held == 1 : s.pending == pending) return;
		usleep(1000);
	}
	require(0, "queue coordination deadline");
}
static void *hold(void *arg)
{
	pin(62);
	hold_error = ioctl(device, FB_HOLD, (unsigned long)arg);
	return NULL;
}
static void hold_start(unsigned int count)
{
	hold_error = 0;
	require(!pthread_create(&holder, NULL, hold, (void *)(unsigned long)count), "create gate holder");
	wait_state(0, 1);
}
static void hold_join(void)
{
	require(!pthread_join(holder, NULL), "join gate holder");
	require(hold_error == 0, "gate holder completed");
}
static unsigned char value(const struct writer *w, unsigned int page)
{
	return (unsigned char)(1 + ((w->cpu * 17 + page * 3) % 251));
}
static void *write_pages(void *arg)
{
	struct writer *w = arg;
	unsigned int page, byte;
	pin(w->cpu);
	w->tid = syscall(SYS_gettid);
	for (page = 0; page < w->pages; page++) {
		volatile unsigned char *p = area + (w->first + page) * PAGE;
		/* This store is the actual CPU fault. No preceding read may install
		 * the zero page and silently turn this into a COW test. */
		p[0] = value(w, page);
		for (byte = 1; byte < PAGE; byte++) {
			if (p[byte] != w->initial) { fprintf(stderr, "initial page contents differ\n"); exit(1); }
			w->checked++;
			p[byte] = value(w, page);
		}
	}
	return NULL;
}
static void start_writer(struct writer *w, unsigned int cpu, unsigned int first,
			 unsigned int pages, unsigned int initial)
{
	w->cpu = cpu; w->first = first; w->pages = pages; w->initial = initial;
	require(!pthread_create(&w->thread, NULL, write_pages, w), "create fault origin");
}
static void join_writer(struct writer *w)
{
	unsigned int page, byte;
	require(!pthread_join(w->thread, NULL), "join fault origin");
	checks += w->checked;
	for (page = 0; page < w->pages; page++)
		for (byte = 0; byte < PAGE; byte++)
			require(area[(w->first + page) * PAGE + byte] == value(w, page), "completed page contents");
	completed += w->pages;
}
static void cohort(unsigned int first, unsigned int pages, int gated)
{
	struct phase *p = &phases[phase_count++];
	unsigned int i;
	if (gated) hold_start(FB_WORKERS);
	for (i = 0; i < FB_WORKERS; i++) start_writer(&p->workers[i], i, first + i * pages, pages, 0);
	for (i = 0; i < FB_WORKERS; i++) join_writer(&p->workers[i]);
	if (gated) hold_join();
	p->status = status();
	require(p->status.idle && !p->status.errors && !p->status.pending, "exact retirement and control checks");
}
static unsigned long long pfn(unsigned int page)
{
	uint64_t entry;
	off_t offset = ((uintptr_t)area / PAGE + page) * sizeof(entry);
	require(pread(pagemap, &entry, sizeof(entry), offset) == sizeof(entry), "read pagemap");
	require((entry >> 63) == 1 && (entry & ((1ULL << 55) - 1)), "present observable physical page");
	return entry & ((1ULL << 55) - 1);
}
static void print_status(const struct fb_status *s)
{
	const struct fb_counts *c = &s->counts;
#define FIELD(name) printf("\"" #name "\":%llu,", (unsigned long long)c->name)
	FIELD(calls); FIELD(supported); FIELD(delegated); FIELD(native); FIELD(post_ban);
	FIELD(handbacks); FIELD(acks); FIELD(cancelled); FIELD(refused);
 #undef FIELD
	printf("\"native_only\":%llu", (unsigned long long)c->native_only);
}
static void report(const char *mode, struct fb_status final, unsigned int bindings, int retry)
{
	unsigned int i, j;
	/* Capture actual installed PFNs before unmapping, but print only after
	 * cleanup succeeds. A full array ties every receipt to a live PTE. */
	unsigned long long pfns[256];
	for (i = 0; i < bindings; i++) pfns[i] = pfn(i);
	require(!munmap(area, PAGES * PAGE), "unmap arena");
	struct fb_status after = status();
	require(after.idle && !after.pending && !after.errors, "post-unmap exact idle");
	require(!memcmp(&after.counts, &final.counts, sizeof(final.counts)), "cleanup did not submit faults");
	require(!close(device) && !close(pagemap), "close test handles");
	printf("{\"mode\":\"%s\",\"checks\":%lu,\"errors\":%llu,\"completed\":%lu,"
	       "\"mm\":%llu,\"gate\":%llu,\"idle\":%llu,\"unmapped_pages\":%d,"
	       "\"reader_peak\":%llu,\"delegated_with_readers\":%llu,\"retry_writer_completed\":%d,"
	       "\"cancel_tid\":[%llu,%llu],\"cancel_present\":[%llu,%llu],\"cancel_result\":[%lld,%lld],\"phases\":[",
	       mode, checks + final.checks, (unsigned long long)final.errors, completed,
	       (unsigned long long)final.mm, (unsigned long long)final.gate, (unsigned long long)after.idle, PAGES,
	       (unsigned long long)final.reader_peak, (unsigned long long)final.delegated_with_readers, retry,
	       (unsigned long long)final.cancel_tid[0], (unsigned long long)final.cancel_tid[1],
	       (unsigned long long)final.cancel_present[0], (unsigned long long)final.cancel_present[1],
	       (long long)final.cancel_result[0], (long long)final.cancel_result[1]);
	for (i = 0; i < phase_count; i++) {
		printf("%s{", i ? "," : ""); print_status(&phases[i].status);
		printf(",\"tids\":[");
		for (j = 0; j < FB_WORKERS; j++) printf("%s%d", j ? "," : "", phases[i].workers[j].tid);
		printf("]}");
	}
	printf("],\"pages\":[");
	for (i = 0; i < bindings; i++)
		printf("%s{\"address\":%llu,\"pfn\":%llu,\"origin\":%d}", i ? "," : "",
		       (unsigned long long)(uintptr_t)(area + i * PAGE), pfns[i], phases[0].workers[i / 16].tid);
	puts("]}");
}
static void retry_case(void)
{
	int uffd = syscall(SYS_userfaultfd, O_CLOEXEC | O_NONBLOCK | UFFD_USER_MODE_ONLY);
	struct uffdio_api api = {.api = UFFD_API, .features = UFFD_FEATURE_THREAD_ID};
	struct uffdio_register reg = {.range = {.start = (uintptr_t)(area + 16 * PAGE), .len = 3 * PAGE},
		.mode = UFFDIO_REGISTER_MODE_MISSING};
	struct uffd_msg message;
	unsigned char *copy;
	require(uffd >= 0, "userfaultfd");
	require(!ioctl(uffd, UFFDIO_API, &api) && (api.features & UFFD_FEATURE_THREAD_ID), "userfaultfd API/tid");
	require(!ioctl(uffd, UFFDIO_REGISTER, &reg), "register missing pages");
	require(!posix_memalign((void **)&copy, PAGE, PAGE), "copy page");
	memset(copy, 0xa5, PAGE);
	hold_start(2);
	start_writer(&phases[0].workers[0], 0, 0, 1, 0);
	wait_state(1, 0);
	start_writer(&phases[0].workers[1], 1, 16, 1, 0xa5);
	struct pollfd poller = {.fd = uffd, .events = POLLIN};
	require(poll(&poller, 1, 15000) == 1 && (poller.revents & POLLIN), "missing-page event");
	require(read(uffd, &message, sizeof(message)) == sizeof(message), "read fault event");
	require(message.event == UFFD_EVENT_PAGEFAULT &&
		message.arg.pagefault.address == (uintptr_t)(area + 16 * PAGE) &&
		(message.arg.pagefault.flags & UFFD_PAGEFAULT_FLAG_WRITE) &&
		message.arg.pagefault.feat.ptid == (unsigned int)phases[0].workers[1].tid, "exact original fault event");
	hold_join();
	/* While the origin is unresolved, this writer must acquire mmap_lock.
	 * It splits the neighboring part without revoking the faulting page. */
	require(!mprotect(area + 17 * PAGE, PAGE, PROT_READ), "writer during fault retry");
	struct uffdio_copy transfer = {.dst = (uintptr_t)(area + 16 * PAGE),
		.src = (uintptr_t)copy, .len = PAGE};
	require(!ioctl(uffd, UFFDIO_COPY, &transfer) && transfer.copy == PAGE, "resolve refused real fault");
	join_writer(&phases[0].workers[0]); join_writer(&phases[0].workers[1]);
	phases[0].status = status(); phase_count = 1;
	start_writer(&phases[1].workers[0], 0, 32, 1, 0);
	join_writer(&phases[1].workers[0]);
	phases[1].status = status(); phase_count = 2;
	require(!ioctl(uffd, UFFDIO_UNREGISTER, &reg.range) && !close(uffd), "userfaultfd cleanup");
	free(copy);
	report("retry", status(), 0, 1);
}
int main(int argc, char **argv)
{
	pin(63);
	require(sysconf(_SC_PAGESIZE) == PAGE, "4 KiB page configuration");
	device = open("/dev/kd_mm_fault_test", O_RDWR | O_CLOEXEC);
	pagemap = open("/proc/self/pagemap", O_RDONLY | O_CLOEXEC);
	require(device >= 0 && pagemap >= 0, "open controls");
	area = mmap(NULL, PAGES * PAGE, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	require(area != MAP_FAILED && !madvise(area, PAGES * PAGE, MADV_NOHUGEPAGE), "anonymous non-huge arena");
	struct fb_region region = {(uintptr_t)area, (uintptr_t)(area + PAGES * PAGE)};
	require(!ioctl(device, FB_ENABLE, &region), "enable immutable interval");
	if (argc == 2 && !strcmp(argv[1], "--cancel")) {
		require(!ioctl(device, FB_CANCEL), "queued fatal cancellation");
		phases[0].status = status(); phase_count = 1;
		require(area[0] == 0x61, "healthy real fault contents");
		report("cancel", status(), 0, 0); return 0;
	}
	if (argc == 2 && !strcmp(argv[1], "--retry")) { retry_case(); return 0; }
	require(argc == 1, "supported command arguments");
	require(*(volatile unsigned char *)(area + 500 * PAGE) == 0 &&
		*(volatile unsigned char *)(area + 501 * PAGE) == 0 && status().counts.calls == 0,
		"read faults stay local");
	cohort(0, 16, 1);
	require(!mlock2(area + 256 * PAGE, FB_WORKERS * PAGE, MLOCK_ONFAULT), "unsupported locked mappings");
	cohort(256, 1, 1);
	require(!munlock(area + 256 * PAGE, FB_WORKERS * PAGE), "unlock refused mappings");
	cohort(272, 8, 0);
	report("body", status(), 256, 0);
	return 0;
}
