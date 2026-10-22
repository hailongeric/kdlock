// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <setjmp.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>
#include "payload/api.h"

#define PAGE 4096
#define GROUPS 48
static int device, hold_error;
static unsigned long checks, completed;
static uintptr_t addresses[GROUPS];
static unsigned int groups, phase_count;
static pthread_t holder, late_thread;
static _Atomic int late_ready, late_go, late_entered, late_done;
static _Atomic pid_t late_tid;
static int late_code, late_blocked, read_first_code;
static char late_stack[8192];
static _Thread_local sigjmp_buf trap;
static _Thread_local volatile sig_atomic_t trap_armed, trap_code;
static _Thread_local uintptr_t trap_address;
static _Thread_local volatile unsigned char observed;

struct worker {
	pthread_t thread;
	unsigned int cpu, group, partial;
	_Atomic pid_t tid;
	_Atomic int ready, go;
	int result, error;
};
struct phase { struct ub_status status; struct worker workers[UB_WORKERS]; unsigned int count; };
static struct phase phases[3];

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
static struct ub_status status(void)
{
	struct ub_status s;
	require(!ioctl(device, UB_STATUS, &s), "status");
	return s;
}
static void wait_atomic(_Atomic int *flag)
{
	for (unsigned int i = 0; !atomic_load(flag); i++) {
		require(i < 10000, "thread ready deadline"); usleep(1000);
	}
}
static void wait_state(int which, unsigned int count)
{
	for (unsigned int i = 0; i < 10000; i++) {
		struct ub_status s = status();
		if ((which == 0 && s.held) || (which == 1 && s.ready) || (which == 2 && s.pending == count)) return;
		usleep(1000);
	}
	require(0, "queue state deadline");
}
static void *hold(void *arg)
{
	pin(62); hold_error = ioctl(device, UB_HOLD, (unsigned long)arg); return NULL;
}
static void hold_start(unsigned int count)
{
	require(!pthread_create(&holder, NULL, hold, (void *)(unsigned long)count), "create reader controller");
	wait_state(0, 0);
}
static void segv(int signal, siginfo_t *info, void *context)
{
	(void)context;
	if (signal != SIGSEGV || !trap_armed || (uintptr_t)info->si_addr != trap_address) _exit(90);
	trap_code = info->si_code;
	siglongjmp(trap, 1);
}
static int probe_read(uintptr_t address)
{
	trap_code = 0; trap_address = address;
	if (sigsetjmp(trap, 1) == 0) {
		trap_armed = 1;
		observed = *(volatile unsigned char *)address;
	}
	trap_armed = 0;
	return trap_code;
}
static void *late_fault(void *unused)
{
	(void)unused; pin(59);
	late_tid = syscall(SYS_gettid);
	atomic_store(&late_ready, 1);
	while (!atomic_load(&late_go)) usleep(1000);
	atomic_store(&late_entered, 1);
	late_code = probe_read(addresses[7]);
	atomic_store(&late_done, 1);
	return NULL;
}
static void capture_late_fault(void)
{
	char path[128];
	snprintf(path, sizeof(path), "/proc/self/task/%d/stack", (int)late_tid);
	atomic_store(&late_go, 1); wait_atomic(&late_entered);
	for (unsigned int i = 0; i < 5000; i++) {
		int fd = open(path, O_RDONLY | O_CLOEXEC);
		require(fd >= 0, "open actual fault stack");
		ssize_t length = read(fd, late_stack, sizeof(late_stack) - 1);
		require(length >= 0, "read actual fault stack");
		late_stack[length] = 0; close(fd);
		if (strstr(late_stack, "kd_mmap_down_read") && strstr(late_stack, "do_user_addr_fault")) break;
		require(i < 4999 && !atomic_load(&late_done), "late hardware fault waits on actual reader admission");
		usleep(1000);
	}
	struct ub_status s = status();
	require(s.readers == 2 && s.admission == -1 && !atomic_load(&late_done), "writer reservation blocks only the late reader");
	late_blocked = 1;
}
static void *unmap(void *arg)
{
	struct worker *w = arg;
	pin(w->cpu); w->tid = syscall(SYS_gettid); atomic_store(&w->ready, 1);
	while (!atomic_load(&w->go)) usleep(1000);
	w->result = munmap((void *)(addresses[w->group] + (w->partial ? PAGE : 0)),
			  (w->partial ? 1 : 3) * PAGE);
	w->error = errno;
	return NULL;
}
static int mapped(uintptr_t address)
{
	unsigned char vec = 0;
	int result = mincore((void *)address, PAGE, &vec);
	require(result == 0 || (result == -1 && errno == ENOMEM), "mincore mapping result");
	return result == 0;
}
static unsigned char pattern(unsigned int group, unsigned int page)
{
	return (unsigned char)(1 + group * 3 + page);
}
static void check_page(uintptr_t address, unsigned char value)
{
	for (unsigned int byte = 0; byte < PAGE; byte++)
		require(*(unsigned char *)(address + byte) == value, "preserved page contents");
}
static void cohort(unsigned int first, unsigned int count, int partial, int gated, int late, int ordered)
{
	struct phase *p = &phases[phase_count++];
	p->count = count;
	for (unsigned int i = 0; i < count; i++) {
		struct worker *w = &p->workers[i];
		w->cpu = i; w->group = first + i; w->partial = partial;
		require(!pthread_create(&w->thread, NULL, unmap, w), "create munmap origin");
		wait_atomic(&w->ready);
	}
	if (late) {
		require(!pthread_create(&late_thread, NULL, late_fault, NULL), "create late fault origin");
		wait_atomic(&late_ready);
	}
	if (gated) hold_start(count);
	for (unsigned int i = 0; i < count; i++) {
		atomic_store(&p->workers[i].go, 1);
		if (ordered && i == 0) wait_state(2, 1);
	}
	if (gated) {
		wait_state(1, 0);
		if (late) capture_late_fault();
		require(!ioctl(device, UB_RELEASE), "release existing readers");
	}
	for (unsigned int i = 0; i < count; i++) {
		struct worker *w = &p->workers[i];
		require(!pthread_join(w->thread, NULL), "join actual munmap origin");
		require(w->result == 0, "actual munmap returned success");
		completed++;
		for (unsigned int page = 0; page < 3; page++)
			require(mapped(addresses[w->group] + page * PAGE) == (partial && page != 1), "exact requested mapping removal");
		require(mapped(addresses[w->group] - 2 * PAGE) && mapped(addresses[w->group] + 4 * PAGE), "neighbor mappings survive");
		if (partial) {
			check_page(addresses[w->group], pattern(w->group, 0));
			check_page(addresses[w->group] + 2 * PAGE, pattern(w->group, 2));
			check_page(addresses[w->group] - 2 * PAGE, 0xa1);
			check_page(addresses[w->group] + 4 * PAGE, 0xb2);
		}
	}
	if (gated) {
		require(!pthread_join(holder, NULL) && hold_error == 0, "reader controller joined");
	}
	if (late) {
		require(!pthread_join(late_thread, NULL) && late_code == SEGV_MAPERR, "late fault observes completed unmap");
	}
	p->status = status();
	require(p->status.idle && !p->status.pending && !p->status.errors, "phase exact retirement");
}
static void print_counts(const struct ub_counts *c)
{
#define FIELD(n) printf("\"" #n "\":%llu,", (unsigned long long)c->n)
	FIELD(calls); FIELD(removed); FIELD(delegated); FIELD(native); FIELD(post_ban);
	FIELD(handbacks); FIELD(acks); FIELD(cancelled); FIELD(refused); FIELD(failed);
#undef FIELD
	printf("\"native_only\":%llu", (unsigned long long)c->native_only);
}
static void print_string(const char *s)
{
	putchar('"');
	for (; *s; s++) {
		if (*s == '\n') fputs("\\n", stdout);
		else if (*s == '\t') fputs("\\t", stdout);
		else { if (*s == '"' || *s == '\\') putchar('\\'); putchar(*s); }
	}
	putchar('"');
}
static void finish(const char *mode)
{
	struct ub_status before = status();
	unsigned int cleanup = 0;
	for (unsigned int i = 0; i < groups; i++) {
		require(!munmap((void *)addresses[i], 3 * PAGE), "cleanup target range"); cleanup++;
		require(!munmap((void *)(addresses[i] - 2 * PAGE), PAGE), "cleanup left neighbor"); cleanup++;
		require(!munmap((void *)(addresses[i] + 4 * PAGE), PAGE), "cleanup right neighbor"); cleanup++;
		for (unsigned int page = 0; page < 3; page++) require(!mapped(addresses[i] + page * PAGE), "target remains absent");
		require(!mapped(addresses[i] - 2 * PAGE) && !mapped(addresses[i] + 4 * PAGE), "neighbors cleaned");
	}
	struct ub_status after = status();
	require(after.idle && !after.pending && !after.errors && after.counts.calls == before.counts.calls + cleanup,
		"cleanup calls and exact idle");
	require(after.counts.removed == before.counts.removed && after.counts.delegated == before.counts.delegated,
		"cleanup does not claim delegated removals");
	require(!close(device), "close device and mm reference");
	printf("{\"mode\":\"%s\",\"checks\":%lu,\"errors\":%llu,\"completed\":%lu,\"groups\":%u,"
	       "\"mm\":%llu,\"gate\":%llu,\"idle\":%llu,\"reader_peak\":%llu,\"pending_peak\":%llu,"
	       "\"cleanup_calls\":%u,\"late_fault_blocked\":%d,\"late_fault_tid\":%d,\"late_fault_code\":%d,"
	       "\"read_first_code\":%d,\"cancel_tid\":[%llu,%llu],\"cancel_mapped\":[%llu,%llu],"
	       "\"cancel_result\":[%lld,%lld],\"after_cleanup\":{",
	       mode, checks + (unsigned long)after.checks, (unsigned long long)after.errors, completed, groups,
	       (unsigned long long)after.mm, (unsigned long long)after.gate, (unsigned long long)after.idle,
	       (unsigned long long)after.reader_peak, (unsigned long long)after.pending_peak, cleanup,
	       late_blocked, (int)late_tid, late_code, read_first_code,
	       (unsigned long long)before.cancel_tid[0], (unsigned long long)before.cancel_tid[1],
	       (unsigned long long)before.cancel_mapped[0], (unsigned long long)before.cancel_mapped[1],
	       (long long)before.cancel_result[0], (long long)before.cancel_result[1]);
	print_counts(&after.counts); printf("},\"late_fault_stack\":"); print_string(late_stack);
	printf(",\"phases\":[");
	for (unsigned int i = 0; i < phase_count; i++) {
		printf("%s{", i ? "," : ""); print_counts(&phases[i].status.counts); printf(",\"origins\":[");
		for (unsigned int j = 0; j < phases[i].count; j++) {
			struct worker *w = &phases[i].workers[j];
			printf("%s{\"tid\":%d,\"start\":%llu,\"end\":%llu}", j ? "," : "", (int)w->tid,
			       (unsigned long long)(addresses[w->group] + (w->partial ? PAGE : 0)),
			       (unsigned long long)(addresses[w->group] + (w->partial ? 2 : 3) * PAGE));
		}
		printf("]}");
	}
	puts("]}");
}
int main(int argc, char **argv)
{
	int cancel = argc == 2 && !strcmp(argv[1], "--cancel");
	int read_first = argc == 2 && !strcmp(argv[1], "--read-first");
	pin(63); require(argc == 1 || cancel || read_first, "arguments");
	struct sigaction action = {.sa_sigaction = segv, .sa_flags = SA_SIGINFO};
	sigemptyset(&action.sa_mask); require(!sigaction(SIGSEGV, &action, NULL), "install expected fault handler");
	device = open("/dev/kd_mm_unmap_test", O_RDWR | O_CLOEXEC);
	require(device >= 0 && sysconf(_SC_PAGESIZE) == PAGE, "device and page size");
	struct ub_status initial = status();
	groups = cancel ? 2 : read_first ? 3 : GROUPS;
	uintptr_t base = initial.pgdir_size * 8 + 8 * PAGE;
	require(initial.pgdir_size >= (1ULL << 39) && base + groups * initial.pgdir_size < initial.task_size,
		"unused top-level page-directory address interval");
	for (unsigned int i = 0; i < groups; i++) {
		addresses[i] = base + i * initial.pgdir_size;
		uintptr_t ranges[] = {addresses[i], addresses[i] - 2 * PAGE, addresses[i] + 4 * PAGE};
		for (unsigned int j = 0; j < 3; j++) {
			size_t length = (j ? 1 : 3) * PAGE;
			void *p = mmap((void *)ranges[j], length, PROT_READ | PROT_WRITE,
				MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0);
			require(p == (void *)ranges[j] && !madvise(p, length, MADV_NOHUGEPAGE), "isolated anonymous range");
		}
	}
	struct ub_config config = {base - 2 * PAGE, addresses[groups - 1] + 5 * PAGE, base, initial.pgdir_size};
	require(!ioctl(device, UB_ENABLE, &config), "enable immutable munmap interval");
	if (cancel) {
		require(!ioctl(device, UB_CANCEL), "queued munmap cancellation");
		phases[0].status = status(); phase_count = 1;
		require(!mapped(addresses[0]) && mapped(addresses[1]), "healthy removal and cancelled VMA retained");
		finish("cancel"); return 0;
	}
	if (read_first) {
		require(probe_read(addresses[1]) == 0 && observed == 0, "real initial zero-page fault");
		cohort(0, 2, 0, 1, 0, 1);
		read_first_code = probe_read(addresses[1]);
		require(read_first_code == SEGV_MAPERR, "native unmap invalidated cached read translation");
		cohort(2, 1, 0, 0, 0, 0);
		finish("read-first"); return 0;
	}
	cohort(0, UB_WORKERS, 0, 1, 1, 0);
	for (unsigned int i = 16; i < 32; i++) {
		for (unsigned int page = 0; page < 3; page++) memset((void *)(addresses[i] + page * PAGE), pattern(i, page), PAGE);
		memset((void *)(addresses[i] - 2 * PAGE), 0xa1, PAGE);
		memset((void *)(addresses[i] + 4 * PAGE), 0xb2, PAGE);
	}
	cohort(16, UB_WORKERS, 1, 1, 0, 0);
	cohort(32, UB_WORKERS, 0, 0, 0, 0);
	finish("body"); return 0;
}
