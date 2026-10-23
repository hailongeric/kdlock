// SPDX-License-Identifier: GPL-2.0
/* Reuse the established signal, pinned-reader and exact queue observers. */
#define main whole_probe_main
#include "../unmap_body/client.c"
#undef main

static _Atomic int leave_threads, hold_done;
static unsigned int slice, refused_case;
static struct ub_layout originals[GROUPS], accounting_before, accounting_after;
struct partial_worker {
	pthread_t thread;
	unsigned int group, offset;
	_Atomic int ready, go, done;
	pid_t tid;
	int result, fault;
};
static struct partial_worker origins[UB_WORKERS];

static struct ub_layout layout(uintptr_t address)
{
	struct ub_layout l = {.address = address};
	require(!ioctl(device, UB_LAYOUT, &l), "exact VMA and explicit-mm accounting");
	return l;
}
static void *partial_holder(void *unused)
{
	(void)unused;
	pin(62); hold_error = ioctl(device, UB_HOLD, groups == 3 ? 2UL : (unsigned long)groups);
	atomic_store(&hold_done, 1);
	while (!atomic_load(&leave_threads)) usleep(1000);
	return NULL;
}
static void *partial_origin(void *arg)
{
	struct partial_worker *w = arg;
	pin(w->group); w->tid = syscall(SYS_gettid);
	if (probe_read((uintptr_t)&warm_byte)) _exit(92);
	if (refused_case && w->group == 1)
		if (probe_read(addresses[1] + PAGE) || observed != pattern(1, 1)) _exit(93);
	atomic_store(&w->ready, 1);
	while (!atomic_load(&w->go)) usleep(1000);
	w->result = munmap((void *)(addresses[w->group] + w->offset * PAGE), PAGE);
	w->fault = probe_read(addresses[w->group] + w->offset * PAGE);
	atomic_store(&w->done, 1);
	/* Keep stacks mapped until the exact global accounting comparison. */
	while (!atomic_load(&leave_threads)) usleep(1000);
	return NULL;
}
static void *partial_fault(void *unused)
{
	(void)unused; pin(59);
	if (probe_read((uintptr_t)&warm_byte)) _exit(91);
	late_tid = syscall(SYS_gettid); atomic_store(&late_ready, 1);
	while (!atomic_load(&late_go)) usleep(1000);
	atomic_store(&late_entered, 1);
	late_code = probe_read(addresses[7] + slice * PAGE);
	atomic_store(&late_done, 1);
	while (!atomic_load(&leave_threads)) usleep(1000);
	return NULL;
}
static void verify_layout(unsigned int group, int removed)
{
	uintptr_t base = addresses[group];
	struct ub_layout original = originals[group];
	for (unsigned int p = 0; p < 3; p++) {
		struct ub_layout l = layout(base + p * PAGE);
		if (removed && p == slice) {
			require(!l.start && !mapped(base + p * PAGE) && probe_read(base + p * PAGE) == SEGV_MAPERR,
				"removed range inaccessible");
		} else {
			uintptr_t lo = !removed || p < slice ? base : base + (slice + 1) * PAGE;
			uintptr_t hi = !removed || p > slice ? base + 3 * PAGE : base + slice * PAGE;
			require(l.start == lo && l.end == hi && l.flags == original.flags &&
				l.pgoff == original.pgoff + (lo - base) / PAGE, "retained VMA bounds, offset and flags");
		}
	}
}
static void contents(unsigned int group, int removed)
{
	for (unsigned int p = 0; p < 3; p++) {
		if (removed && p == slice) continue;
		/* Supported inputs were never faulted before removal: their contents
		 * must still be zero. The refused resident input retains its pattern. */
		check_page(addresses[group] + p * PAGE, refused_case && group == 1 ? pattern(group, p) : 0);
		memset((void *)(addresses[group] + p * PAGE), pattern(group, p), PAGE);
		check_page(addresses[group] + p * PAGE, pattern(group, p));
	}
}
static void account(unsigned int removed)
{
	accounting_after = layout(addresses[0]);
	require(accounting_after.total_vm + removed == accounting_before.total_vm &&
		accounting_after.data_vm + removed == accounting_before.data_vm &&
		accounting_after.stack_vm == accounting_before.stack_vm && accounting_after.exec_vm == accounting_before.exec_vm &&
		accounting_after.map_count == accounting_before.map_count + (slice == 1 ? removed : 0),
		"exact VMA count, total/data/stack/exec accounting");
	if (!refused_case)
		require(accounting_after.pgtables == accounting_before.pgtables, "unpopulated split retains page-table accounting");
}
int main(int argc, char **argv)
{
	int cancel = argc == 2 && !strcmp(argv[1], "cancel");
	refused_case = argc == 2 && !strcmp(argv[1], "refusal");
	slice = argc == 2 && !strcmp(argv[1], "prefix") ? 0 : argc == 2 && !strcmp(argv[1], "suffix") ? 2 : 1;
	require(argc == 2 && (cancel || refused_case || !strcmp(argv[1], "middle") ||
		!strcmp(argv[1], "prefix") || !strcmp(argv[1], "suffix")), "partial case argument");
	pin(63); groups = cancel ? 2 : refused_case ? 3 : UB_WORKERS;
	struct sigaction action = {.sa_sigaction = segv, .sa_flags = SA_SIGINFO};
	sigemptyset(&action.sa_mask); require(!sigaction(SIGSEGV, &action, NULL), "signal handler");
	device = open("/dev/kd_mm_unmap_test", O_RDWR | O_CLOEXEC); require(device >= 0, "open exact-mm probe");
	struct ub_status initial = status();
	uintptr_t base = initial.pgdir_size * 8 + 8 * PAGE;
	require(base + groups * initial.pgdir_size < initial.task_size, "caller address range");
	for (unsigned int g = 0; g < groups; g++) {
		addresses[g] = base + g * initial.pgdir_size;
		uintptr_t ranges[] = {addresses[g], addresses[g] - 2 * PAGE, addresses[g] + 4 * PAGE};
		for (unsigned int r = 0; r < 3; r++) {
			size_t len = (r ? 1 : 3) * PAGE;
			void *p = mmap((void *)ranges[r], len, PROT_READ | PROT_WRITE,
				MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0);
			require(p == (void *)ranges[r] && !madvise(p, len, MADV_NOHUGEPAGE), "untouched anonymous mapping");
		}
		if (refused_case && g == 1)
			for (unsigned int p = 0; p < 3; p++) memset((void *)(addresses[g] + p * PAGE), pattern(g, p), PAGE);
		originals[g] = layout(addresses[g]);
	}
	struct ub_config config = {base - 2 * PAGE, addresses[groups - 1] + 5 * PAGE, base, initial.pgdir_size};
	require(!ioctl(device, UB_ENABLE, &config), "enable typed unmap path");
	if (cancel) {
		accounting_before = layout(base);
		require(!ioctl(device, UB_CANCEL_PARTIAL), "queued partial cancellation");
		account(1);
	} else {
		for (unsigned int g = 0; g < groups; g++) {
			origins[g].group = g; origins[g].offset = slice;
			require(!pthread_create(&origins[g].thread, NULL, partial_origin, &origins[g]), "partial origin");
			wait_atomic(&origins[g].ready);
		}
		if (!refused_case) {
			require(!pthread_create(&late_thread, NULL, partial_fault, NULL), "real fault origin");
			wait_atomic(&late_ready); capture_late_fault(0);
		}
		require(!pthread_create(&holder, NULL, partial_holder, NULL), "concurrent reader controller");
		wait_state(0, 0);
		/* Already-held readers still permit this local shared query. */
		accounting_before = layout(base);
		for (unsigned int g = 0; g < (refused_case ? 2 : groups); g++) {
			atomic_store(&origins[g].go, 1);
			if (refused_case && !g) wait_state(2, 1);
		}
		wait_state(1, 0);
		if (!refused_case) capture_late_fault(1);
		require(!ioctl(device, UB_RELEASE), "release two local readers");
		for (unsigned int g = 0; g < (refused_case ? 2 : groups); g++) wait_atomic(&origins[g].done);
		if (refused_case) { atomic_store(&origins[2].go, 1); wait_atomic(&origins[2].done); }
		else { wait_atomic(&late_done); require(late_code == SEGV_MAPERR, "blocked fault sees the removed slice"); }
		wait_atomic(&hold_done); require(!hold_error, "reader controller drained");
		account(groups);
	}
	for (unsigned int g = 0; g < groups; g++) {
		verify_layout(g, !cancel || !g);
		contents(g, !cancel || !g);
		if (!cancel) require(!origins[g].result && origins[g].fault == SEGV_MAPERR, "origin completion and translation invalidation");
	}
	struct ub_status done = status();
	require(done.idle && !done.pending && !done.errors && done.reader_peak == 2, "exact request retirement");
	atomic_store(&leave_threads, 1);
	if (!cancel) {
		for (unsigned int g = 0; g < groups; g++) require(!pthread_join(origins[g].thread, NULL), "join original task");
		require(!pthread_join(holder, NULL), "join reader controller");
		if (!refused_case) require(!pthread_join(late_thread, NULL) && !close(late_stack_fd), "join real fault observer");
	}
	unsigned int cleanup = 0;
	for (unsigned int g = 0; g < groups; g++) {
		require(!munmap((void *)addresses[g], 3 * PAGE), "cleanup retained ranges"); cleanup++;
		require(!munmap((void *)(addresses[g] - 2 * PAGE), PAGE), "cleanup left neighbor"); cleanup++;
		require(!munmap((void *)(addresses[g] + 4 * PAGE), PAGE), "cleanup right neighbor"); cleanup++;
		for (unsigned int p = 0; p < 3; p++) require(!mapped(addresses[g] + p * PAGE), "cleanup leaves no target mappings");
		require(!mapped(addresses[g] - 2 * PAGE) && !mapped(addresses[g] + 4 * PAGE), "cleanup leaves no neighbor mappings");
	}
	struct ub_status clean = status();
	require(clean.idle && !clean.pending && !clean.errors && clean.counts.calls == done.counts.calls + cleanup &&
		clean.counts.native == done.counts.native + cleanup && clean.counts.removed == done.counts.removed &&
		clean.counts.delegated == done.counts.delegated && clean.counts.handbacks == clean.counts.acks, "local cleanup and matching retirement");
	require(!close(device), "release test mm reference");
	printf("{\"mode\":\"%s\",\"mm\":%llu,\"gate\":%llu,\"checks\":%lu,\"errors\":%llu,\"groups\":%u,\"slice\":%u,\"idle\":1,\"reader_peak\":%llu,\"cleanup_calls\":%u,\"late_fault_blocked\":%d,\"late_fault_code\":%d,\"counts\":{",argv[1],(unsigned long long)done.mm,(unsigned long long)done.gate,checks+(unsigned long)clean.checks,(unsigned long long)clean.errors,groups,slice,(unsigned long long)done.reader_peak,cleanup,late_blocked,late_code);
	print_counts(&done.counts); printf("},\"cleanup_tid\":%ld,\"after_cleanup\":{", syscall(SYS_gettid)); print_counts(&clean.counts);
	printf("},\"maps_before\":%llu,\"maps_after\":%llu,\"pages_before\":%llu,\"pages_after\":%llu,\"cancel_result\":[%lld,%lld],\"cancel_tid\":[%llu,%llu],\"origins\":[",(unsigned long long)accounting_before.map_count,(unsigned long long)accounting_after.map_count,(unsigned long long)accounting_before.total_vm,(unsigned long long)accounting_after.total_vm,(long long)done.cancel_result[0],(long long)done.cancel_result[1],(unsigned long long)done.cancel_tid[0],(unsigned long long)done.cancel_tid[1]);
	for (unsigned int g = 0; g < groups; g++) printf("%s{\"tid\":%d,\"start\":%llu,\"end\":%llu,\"old_start\":%llu,\"old_end\":%llu}",g ? "," : "",origins[g].tid,(unsigned long long)(addresses[g]+slice*PAGE),(unsigned long long)(addresses[g]+(slice+1)*PAGE),(unsigned long long)addresses[g],(unsigned long long)(addresses[g]+3*PAGE));
	printf("],\"late_fault_stack\":"); print_string(late_stack); puts("}"); return 0;
}
