// SPDX-License-Identifier: GPL-2.0
/* Page-fault correctness only; keep separate from untouched mmap transactions. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/userfaultfd.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>

static _Atomic unsigned checks;
#define CHECK(c) do { atomic_fetch_add(&checks, 1); if (!(c)) { \
	fprintf(stderr, "FAIL line %d: %s errno=%d\n", __LINE__, #c, errno); exit(1); \
} } while (0)
static size_t page_size;

static void pin(unsigned cpu)
{
	cpu_set_t cpus;
	CPU_ZERO(&cpus);
	CPU_SET(cpu, &cpus);
	CHECK(!sched_setaffinity(0, sizeof(cpus), &cpus) && sched_getcpu() == (int)cpu);
}

static void wait_child(pid_t pid)
{
	int status;
	CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && !WEXITSTATUS(status));
}

static void fork_remote(void)
{
	unsigned char *map = mmap(NULL, page_size * 2, PROT_READ | PROT_WRITE,
				 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(map != MAP_FAILED);
	memset(map, 0x31, page_size * 2); /* Explicit faults belong to this task. */
	for (unsigned round = 0; round < 16; round++) {
		int ready[2], release[2];
		CHECK(!pipe2(ready, O_CLOEXEC) && !pipe2(release, O_CLOEXEC));
		pid_t child = fork();
		CHECK(child >= 0);
		if (!child) {
			char byte = 'R';
			pin(0);
			close(ready[0]); close(release[1]);
			CHECK(map[0] == 0x31);
			map[page_size] = 0x51; /* Child COW; parent bytes must stay private. */
			CHECK(write(ready[1], &byte, 1) == 1);
			CHECK(read(release[0], &byte, 1) == 1 && byte == 'G');
			CHECK(map[0] == 0x71 && map[page_size] == 0x51);
			/* Leave the real VMAs for exit_mmap, including the remote write. */
			_exit(0);
		}
		close(ready[1]); close(release[0]);
		char byte;
		CHECK(read(ready[0], &byte, 1) == 1 && byte == 'R');
		unsigned char values[2] = {0, 0};
		struct iovec local[2] = {{values, 1}, {values + 1, 1}};
		struct iovec remote[2] = {{map, 1}, {map + page_size, 1}};
		CHECK(process_vm_readv(child, local, 2, remote, 2, 0) == 2);
		CHECK(values[0] == 0x31 && values[1] == 0x51);
		values[0] = 0x71;
		CHECK(process_vm_writev(child, local, 1, remote, 1, 0) == 1);
		CHECK(map[0] == 0x31 && map[page_size] == 0x31);
		byte = 'G';
		CHECK(write(release[1], &byte, 1) == 1);
		wait_child(child);
		CHECK(!close(ready[0]) && !close(release[1]));
	}
	CHECK(!munmap(map, page_size * 2));
	printf("{\"case\":\"fork_cow_remote_exit\",\"children\":16,\"remote_reads\":16,"
	       "\"remote_writes\":16,\"joined\":16,\"passed\":true}\n");
}

struct fault_worker {
	volatile unsigned char *address;
	_Atomic int tid, done;
	unsigned char value;
};

static void *fault_read(void *argument)
{
	struct fault_worker *w = argument;
	pin(0);
	atomic_store(&w->tid, syscall(SYS_gettid));
	w->value = *w->address;
	atomic_store(&w->done, 1);
	return NULL;
}

static void mapping(unsigned long address, unsigned long *start, unsigned long *end, char mode[5])
{
	FILE *maps = fopen("/proc/self/maps", "r");
	char *line = NULL;
	size_t size = 0;
	int found = 0;
	CHECK(maps);
	while (getline(&line, &size, maps) > 0) {
		unsigned long lo, hi;
		char permissions[5];
		if (sscanf(line, "%lx-%lx %4s", &lo, &hi, permissions) == 3 && lo <= address && address < hi) {
			*start = lo; *end = hi;
			memcpy(mode, permissions, 5);
			found++;
		}
	}
	free(line);
	CHECK(!fclose(maps) && found == 1);
}

static void retry_revalidate(void)
{
	for (unsigned round = 0; round < 16; round++) {
		int uffd = syscall(SYS_userfaultfd, O_CLOEXEC | O_NONBLOCK | UFFD_USER_MODE_ONLY);
		CHECK(uffd >= 0); /* Missing support is a failure, never a skip/pass. */
		struct uffdio_api api = {.api = UFFD_API, .features = UFFD_FEATURE_THREAD_ID};
		CHECK(!ioctl(uffd, UFFDIO_API, &api) && (api.features & UFFD_FEATURE_THREAD_ID));
		char *guard = mmap(NULL, page_size * 5, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		CHECK(guard != MAP_FAILED);
		char *base = guard + page_size, *address = base + page_size;
		CHECK(!mprotect(base, page_size * 3, PROT_READ | PROT_WRITE));
		CHECK(!madvise(base, page_size * 3, MADV_NOHUGEPAGE));
		struct uffdio_register registration = {
			.range = {.start = (unsigned long)base, .len = page_size * 3},
			.mode = UFFDIO_REGISTER_MODE_MISSING,
		};
		CHECK(!ioctl(uffd, UFFDIO_REGISTER, &registration));
		unsigned long before_start, before_end, after_start, after_end;
		char before_mode[5], after_mode[5];
		mapping((unsigned long)address, &before_start, &before_end, before_mode);
		CHECK(before_start == (unsigned long)base && before_end == (unsigned long)base + page_size * 3);
		CHECK(!strcmp(before_mode, "rw-p"));
		struct fault_worker w = {.address = (void *)address};
		pthread_t thread;
		CHECK(!pthread_create(&thread, NULL, fault_read, &w));
		struct pollfd pfd = {.fd = uffd, .events = POLLIN};
		CHECK(poll(&pfd, 1, 5000) == 1 && (pfd.revents & POLLIN));
		struct uffd_msg event;
		CHECK(read(uffd, &event, sizeof(event)) == sizeof(event));
		CHECK(event.event == UFFD_EVENT_PAGEFAULT && event.arg.pagefault.address == (unsigned long)address);
		CHECK(!event.arg.pagefault.flags && event.arg.pagefault.feat.ptid == (unsigned)atomic_load(&w.tid));
		CHECK(!atomic_load(&w.done));
		/* The userfault wait has dropped the real mmap read lock. This write
		 * operation must complete while that exact fault remains unresolved.
		 * Splitting its VMA forces the retried fault to look up the new range. */
		CHECK(!mprotect(address, page_size, PROT_READ));
		mapping((unsigned long)address, &after_start, &after_end, after_mode);
		CHECK(after_start == (unsigned long)address && after_end == (unsigned long)address + page_size);
		CHECK(!strcmp(after_mode, "r--p") && !atomic_load(&w.done));
		void *page;
		CHECK(!posix_memalign(&page, page_size, page_size));
		memset(page, 0xa0 + round, page_size);
		struct uffdio_copy copy = {.dst = (unsigned long)address, .src = (unsigned long)page, .len = page_size};
		CHECK(!ioctl(uffd, UFFDIO_COPY, &copy) && copy.copy == (long long)page_size);
		CHECK(!pthread_join(thread, NULL) && atomic_load(&w.done) && w.value == 0xa0 + round);
		free(page);
		CHECK(!ioctl(uffd, UFFDIO_UNREGISTER, &registration.range));
		CHECK(!close(uffd) && !munmap(guard, page_size * 5));
		printf("{\"case\":\"userfault_retry_vma_split\",\"round\":%u,\"tid\":%d,"
		       "\"address\":%lu,\"before_start\":%lu,\"before_end\":%lu,"
		       "\"after_start\":%lu,\"after_end\":%lu,\"value\":%u,\"joined\":1,\"passed\":true}\n",
		       round, atomic_load(&w.tid), (unsigned long)address, before_start, before_end,
		       after_start, after_end, w.value);
	}
}

int main(void)
{
	setvbuf(stdout, NULL, _IOLBF, 0);
	page_size = sysconf(_SC_PAGESIZE);
	CHECK(page_size == 4096);
	pin(63);
	fork_remote();
	retry_revalidate();
	printf("{\"case\":\"complete\",\"checks\":%u,\"passed\":true,\"timing\":false}\n", atomic_load(&checks));
	return 0;
}
