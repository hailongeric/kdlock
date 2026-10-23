// SPDX-License-Identifier: GPL-2.0
#define main old_whole_probe_main
#include "../unmap_body/client.c"
#undef main

static int resident, native, injection, busy, cancellation, free_first;
static unsigned int slice, masks[3], pin_mask, late_slot;
static int zero_case, missing_case, busy_page;
static struct ub_ptes ptes_before[3], ptes_after[3];
static struct ub_pages pages_before, pages_after;
static struct ub_ptes ptes(unsigned int g)
{
	struct ub_ptes r = {.address = addresses[g]};
	require(!ioctl(device, UB_PTES, &r), "read-only exact PTE state"); return r;
}
static void check_ptes(unsigned int g, struct ub_ptes r, unsigned int anon, unsigned int zero)
{
	require(r.anon == anon && r.zero == zero && !r.other && r.none == (7U ^ (anon | zero)), "exact anonymous/untouched/zero PTE masks");
	for (unsigned int p = 0; p < 3; p++)
		require(!(anon & (1U << p)) || r.pfn[p] == pages_before.page[g * 3 + p].pfn, "original per-slot physical page");
}
static void print_ptes(struct ub_ptes *r)
{
	printf("{\"none\":%llu,\"anon\":%llu,\"zero\":%llu,\"other\":%llu,\"pfn\":[%llu,%llu,%llu]}",
		(unsigned long long)r->none,(unsigned long long)r->anon,(unsigned long long)r->zero,(unsigned long long)r->other,
		(unsigned long long)r->pfn[0],(unsigned long long)r->pfn[1],(unsigned long long)r->pfn[2]);
}
static _Atomic int leave_threads, holder_done;
static struct ub_layout before, after, original[3], layouts[3][3];
static struct ub_rmap roots[3], rmaps[3][3];
static struct ub_extra extra_before, extra_after;
static int fault_value;
struct ex_worker {
	pthread_t thread;
	unsigned int group, offset, width;
	pid_t tid;
	_Atomic int ready, go, done;
	int result, error, fault;
};
static struct ex_worker workers[3];

static struct ub_layout layout(uintptr_t address)
{
	struct ub_layout l = {.address = address};
	require(!ioctl(device, UB_LAYOUT, &l), "exact VMA/accounting query"); return l;
}
static struct ub_rmap rmap(uintptr_t address)
{
	struct ub_rmap r = {.address = address};
	require(!ioctl(device, UB_RMAP, &r), "exact reverse-map query"); return r;
}
static struct ub_extra extra(void)
{
	struct ub_extra e;
	require(!ioctl(device, UB_EXTRA, &e), "allocation/injection state"); return e;
}
static void *ex_hold(void *unused)
{
	(void)unused; pin(62); hold_error = ioctl(device, UB_HOLD, busy ? 2UL : (unsigned long)groups);
	atomic_store(&holder_done, 1);
	while (!atomic_load(&leave_threads)) usleep(1000);
	return NULL;
}
static void *ex_origin(void *arg)
{
	struct ex_worker *w = arg;
	pin(w->group); w->tid = syscall(SYS_gettid);
	if (probe_read((uintptr_t)&warm_byte)) _exit(92);
	/* Warm only resident slots on the CPU that will verify the removed target. */
	if (resident)
		for (unsigned int p = 0; p < 3; p++)
			if ((masks[w->group] & (1U << p)) && (probe_read(addresses[w->group] + p * PAGE) || observed != pattern(w->group, p))) _exit(93);
	atomic_store(&w->ready, 1);
	while (!atomic_load(&w->go)) usleep(1000);
	errno = 0;
	w->result = munmap((void *)(addresses[w->group] + w->offset * PAGE), w->width * PAGE);
	w->error = errno;
	/* An untouched failed target is read by the controller only after its
	 * page-table accounting/layout snapshot, so that read cannot obscure it. */
	w->fault = w->result && !resident ? -2 : probe_read(addresses[w->group] + w->offset * PAGE);
	atomic_store(&w->done, 1);
	while (!atomic_load(&leave_threads)) usleep(1000);
	return NULL;
}
static void *ex_fault(void *unused)
{
	(void)unused; pin(59);
	if (probe_read((uintptr_t)&warm_byte)) _exit(91);
	late_tid = syscall(SYS_gettid); atomic_store(&late_ready, 1);
	while (!atomic_load(&late_go)) usleep(1000);
	atomic_store(&late_entered, 1);
	/* An untouched survivor inside the original VMA has no PTE: this is a real hardware
	 * fault that must wait on reader admission, then resolve locally. */
	late_code = probe_read(addresses[1] + late_slot * PAGE); fault_value = observed;
	atomic_store(&late_done, 1);
	while (!atomic_load(&leave_threads)) usleep(1000);
	return NULL;
}
static int removed(unsigned int g, unsigned int p)
{
	if (injection) return !native && g == 0;
	if (cancellation && g == 1) return 0;
	return p == slice;
}
static unsigned int split_count(unsigned int g)
{
	if (injection) return native || g == 1 ? injection : 0;
	if (cancellation && g == 1) return 0;
	return slice == 1 ? 2 : 1;
}
static void verify_mappings(void)
{
	for (unsigned int g = 0; g < groups; g++) {
		unsigned int splits = split_count(g), lost = 0;
		for (unsigned int p = 0; p < 3; p++) lost += removed(g, p);
		for (unsigned int p = 0; p < 3; p++) {
			uintptr_t base = addresses[g], lo = base, hi = base + 3 * PAGE;
			struct ub_layout l = layout(base + p * PAGE);
			struct ub_rmap r = rmap(base + p * PAGE);
			layouts[g][p] = l; rmaps[g][p] = r;
			if (removed(g, p)) {
				require(!l.start && !r.anon && !mapped(base + p * PAGE) &&
					probe_read(base + p * PAGE) == SEGV_MAPERR, "removed page inaccessible");
				continue;
			}
			if (splits) {
				unsigned int first = slice ? slice : 1;
				if (p < first) hi = base + first * PAGE;
				else lo = base + first * PAGE;
				if (splits == 2) {
					if (p < 2 && p >= first) hi = base + 2 * PAGE;
					if (p >= 2) lo = base + 2 * PAGE;
				}
			}
			require(l.start == lo && l.end == hi && l.flags == original[g].flags &&
				l.pgoff == original[g].pgoff + (lo - base) / PAGE, "native split bounds/flags/offsets");
			if (resident) {
				require(r.anon == roots[g].anon && r.root == roots[g].root && r.links == 1 &&
					r.refs == roots[g].refs && r.active == 1 + splits - lost && r.intervals == r.active,
					"reverse-map root, links, active VMAs and reference lifetime");
			} else require(!r.anon, "untouched reverse map remains absent before first read");
		}
		/* Read only after every split/absence observation for this VMA. */
		for (unsigned int p = 0; p < 3; p++)
			if (!removed(g, p)) check_page(addresses[g] + p * PAGE, (masks[g] & (1U << p)) ? pattern(g, p) : 0);
		check_page(addresses[g] - 2 * PAGE, 0);
		check_page(addresses[g] + 4 * PAGE, 0);
	}
}
static void print_layouts(unsigned int g)
{
	putchar('[');
	for (unsigned int p = 0; p < 3; p++) {
		struct ub_layout *l = &layouts[g][p]; struct ub_rmap *r = &rmaps[g][p];
		printf("%s{\"mapped\":%d,\"lo\":%lld,\"hi\":%lld,\"pgoff\":%lld,\"flags\":%llu,\"anon\":%llu,\"root\":%llu,\"link\":%llu,\"active\":%llu,\"refs\":%llu,\"intervals\":%llu}",
			p ? "," : "", !!l->start, l->start ? (long long)(l->start - addresses[g]) : 0,
			l->end ? (long long)(l->end - addresses[g]) : 0, l->start ? (long long)(l->pgoff - original[g].pgoff) : 0,
			(unsigned long long)l->flags, (unsigned long long)r->anon, (unsigned long long)r->root,
			(unsigned long long)r->link, (unsigned long long)r->active, (unsigned long long)r->refs, (unsigned long long)r->intervals);
	}
	putchar(']');
}
static void print_pages(struct ub_pages *s)
{
	putchar('[');
	for (unsigned int i = 0; i < s->count; i++) {
		struct ub_page *p = &s->page[i];
		printf("%s{\"address\":%llu,\"pfn\":%llu,\"hash\":%llu,\"maps\":%llu,\"refs\":%llu,\"locked\":%llu,\"charged_same\":%llu}",
			i ? "," : "", (unsigned long long)p->address, (unsigned long long)p->pfn, (unsigned long long)p->hash,
			(unsigned long long)p->mapcount, (unsigned long long)p->refs, (unsigned long long)p->locked, (unsigned long long)p->charged_same);
	}
	putchar(']');
}
int main(int argc, char **argv)
{
	require(argc == 3 || argc == 6, "mixed MODE or error native|kd resident middle 1|2");
	if (argc == 6) {
		require(!strcmp(argv[1], "error") && (!strcmp(argv[2], "native") || !strcmp(argv[2], "kd")) &&
			(!strcmp(argv[3], "resident") || !strcmp(argv[3], "untouched")), "error mode");
		native = !strcmp(argv[2], "native"); resident = !strcmp(argv[3], "resident"); injection = atoi(argv[5]);
		require(injection == 1 || injection == 2, "reachable split count");
	} else {
		require(!strcmp(argv[1], "mixed"), "mixed mode"); resident = 1;
		busy_page = !strcmp(argv[2], "refusal"); zero_case = !strcmp(argv[2], "zero"); missing_case = !strcmp(argv[2], "missing");
		busy = busy_page || zero_case || missing_case; cancellation = !strcmp(argv[2], "cancel"); free_first = !strcmp(argv[2], "free");
	}
	const char *shape = argc == 6 ? argv[4] : argv[2];
	slice = !strcmp(shape, "prefix") ? 0 : !strcmp(shape, "suffix") ? 2 : 1;
	require(!strcmp(shape, "prefix") || !strcmp(shape, "suffix") || !strcmp(shape, "middle") || !strcmp(shape, "left") || !strcmp(shape, "right") || busy || cancellation || free_first, "shape");
	require(injection != 2 || slice == 1, "two splits only for an interior range");
	require(resident && (!injection || slice == 1), "mixed resident interior error scope");
	pin(63); groups = native ? 1 : injection || cancellation || free_first ? 2 : 3;
	struct sigaction action = {.sa_sigaction = segv, .sa_flags = SA_SIGINFO};
	sigemptyset(&action.sa_mask); require(!sigaction(SIGSEGV, &action, NULL), "signal handler");
	device = open("/dev/kd_mm_unmap_test", O_RDWR | O_CLOEXEC); require(device >= 0, "probe open");
	struct ub_status initial = status();
	uintptr_t stride = resident ? 2 * 1024 * 1024 : initial.pgdir_size;
	uintptr_t base = initial.pgdir_size * 8 + 8 * PAGE;
	require(base + groups * stride < initial.task_size, "caller address range");
	for (unsigned int g = 0; g < groups; g++) {
		addresses[g] = base + g * stride;
		uintptr_t ranges[] = {addresses[g], addresses[g] - 2 * PAGE, addresses[g] + 4 * PAGE};
		for (unsigned int r = 0; r < 3; r++) {
			size_t len = (r ? 1 : 3) * PAGE;
			void *p = mmap((void *)ranges[r], len, PROT_READ | PROT_WRITE,
				MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0);
			require(p == (void *)ranges[r] && !madvise(p, len, MADV_NOHUGEPAGE), "mapping setup");
		}
		masks[g] = 1U << slice;
		if (!strcmp(shape, "left")) masks[g] |= 1;
		if (!strcmp(shape, "right")) masks[g] |= 4;
		if (injection && !native && !g) masks[g] = 7;
		if (busy && g == 1) masks[g] = missing_case ? 5 : busy_page ? 6 : 2;
		pin_mask |= masks[g] << (g * 3);
		for (unsigned int p = 0; p < 3; p++) if (masks[g] & (1U << p)) memset((void *)(addresses[g] + p * PAGE), pattern(g, p), PAGE);
		if (zero_case && g == 1) require(!probe_read(addresses[g] + 2 * PAGE) && !observed, "real unsupported zero-page survivor");
		original[g] = layout(addresses[g]); roots[g] = rmap(addresses[g]);
		if (resident) require(roots[g].anon && roots[g].anon == roots[g].root && roots[g].links == 1 && roots[g].active == 1 && roots[g].intervals == 1, "one original reverse-map chain");
	}
	struct ub_experiment e = {{base - 2 * PAGE, addresses[groups - 1] + 5 * PAGE, base, stride}, native ? 0 : resident ? 2 : 1, groups, injection};
	require(!ioctl(device, UB_EXPERIMENT, &e), "explicit experiment opt-in");
	if (resident) {
		require(!ioctl(device, UB_PIN_MASK, (unsigned long)pin_mask) && !ioctl(device, UB_PAGESTATE, &pages_before), "exact original page references");
		for (unsigned int i = 0; i < pages_before.count; i++) if (pin_mask & (1U << i)) require(pages_before.page[i].mapcount == 1 && pages_before.page[i].refs == 2 && !pages_before.page[i].locked, "initial page ownership");
		if (free_first) require(!ioctl(device, UB_UNPIN_MAPPED), "drop test references before real final release");
		if (busy_page) require(!ioctl(device, UB_BUSY_LOCK), "make final page busy before admission");
	}
	for (unsigned int g = 0; g < groups; g++) {
		ptes_before[g] = ptes(g); check_ptes(g, ptes_before[g], masks[g], zero_case && g == 1 ? 4 : 0);
	}
	while (masks[1] & (1U << late_slot)) late_slot++;
	require(late_slot < 3, "untouched survivor for fault interaction");
	extra_before = extra();
	int fault_test = !native && !injection && !busy && !cancellation;
	if (native) {
		before = layout(base); workers[0].tid = syscall(SYS_gettid); workers[0].offset = slice; workers[0].width = 1;
		errno = 0; workers[0].result = munmap((void *)(base + slice * PAGE), PAGE); workers[0].error = errno;
	} else if (cancellation) {
		before = layout(base); require(!ioctl(device, UB_CANCEL_PARTIAL), "queued fatal cancellation");
	} else {
		for (unsigned int g = 0; g < groups; g++) {
			workers[g].group = g; workers[g].offset = injection && !g ? 0 : slice; workers[g].width = injection && !g ? 3 : 1;
			require(!pthread_create(&workers[g].thread, NULL, ex_origin, &workers[g]), "create origin"); wait_atomic(&workers[g].ready);
		}
		if (fault_test) {
			require(!pthread_create(&late_thread, NULL, ex_fault, NULL), "create real fault task"); wait_atomic(&late_ready); capture_late_fault(0);
		}
		require(!pthread_create(&holder, NULL, ex_hold, NULL), "create reader controller"); wait_state(0, 0);
		before = layout(base);
		for (unsigned int g = 0; g < (busy ? 2 : groups); g++) {
			atomic_store(&workers[g].go, 1);
			if ((injection || busy) && !g) wait_state(2, 1);
		}
		wait_state(1, 0);
		if (fault_test) capture_late_fault(1);
		require(!ioctl(device, UB_RELEASE), "release concurrent readers");
		for (unsigned int g = 0; g < (busy ? 2 : groups); g++) wait_atomic(&workers[g].done);
		if (busy) { atomic_store(&workers[2].go, 1); wait_atomic(&workers[2].done); }
		if (fault_test) { wait_atomic(&late_done); require(!late_code && !fault_value, "real survivor fault resolves locally"); }
		wait_atomic(&holder_done); require(!hold_error, "reader controller drained");
	}
	after = layout(base); extra_after = extra();
	unsigned int removed_pages = injection ? (native ? 0 : 3) : cancellation ? 1 : groups;
	int map_delta = injection ? injection - !native : slice == 1 ? (int)removed_pages : 0;
	require(before.total_vm == after.total_vm + removed_pages && before.data_vm == after.data_vm + removed_pages &&
		before.exec_vm == after.exec_vm && before.stack_vm == after.stack_vm &&
		(long long)after.map_count - (long long)before.map_count == map_delta && before.pgtables == after.pgtables,
		"exact native page/VMA/table accounting including harmless splits");
	require(extra_after.fail_after == 0 && extra_after.fail_seen == !!injection, "one exact injection consumed");
	if (!cancellation) for (unsigned int g = 0; g < groups; g++) {
		int failed = injection && (native || g == 1);
		require(workers[g].result == (failed ? -1 : 0) && (!failed || workers[g].error == ENOMEM), "original caller receives exact return");
		if (!native) require(workers[g].fault == (failed ? (resident ? 0 : -2) : SEGV_MAPERR), "same CPU checks retained or invalidated translation");
	}
	for (unsigned int g = 0; g < groups; g++) {
		unsigned int gone = 0;
		for (unsigned int p = 0; p < 3; p++) if (removed(g, p)) gone |= 1U << p;
		ptes_after[g] = ptes(g);
		check_ptes(g, ptes_after[g], masks[g] & ~gone,
			(zero_case && g == 1 ? 4 : 0) | (fault_test && g == 1 ? 1U << late_slot : 0));
	}
	verify_mappings();
	if (busy_page) require(!ioctl(device, UB_BUSY_UNLOCK), "release original busy-page lock");
	if (resident && !free_first) {
		require(!ioctl(device, UB_PAGESTATE, &pages_after), "post-body exact page references");
		for (unsigned int i = 0; i < pages_after.count; i++) {
			struct ub_page *a = &pages_before.page[i], *b = &pages_after.page[i]; int gone = removed(i / 3, i % 3);
			if (!(pin_mask & (1U << i))) {
				require(!a->pfn && !a->refs && !b->pfn && !b->refs, "untouched slots acquire no test reference"); continue;
			}
			require(a->pfn == b->pfn && a->hash == b->hash && b->mapcount == (unsigned)!gone &&
				b->refs == (unsigned)(2 - gone) && !b->locked && b->charged_same,
				"exact pages retained, unlocked and reference-balanced after completion/error/refusal");
		}
	}
	/* Previously untouched survivors remain writable after the observations. */
	for (unsigned int g = 0; g < groups; g++) for (unsigned int p = 0; p < 3; p++)
		if (!removed(g, p) && !(masks[g] & (1U << p))) {
			memset((void *)(addresses[g] + p * PAGE), pattern(g, p), PAGE);
			check_page(addresses[g] + p * PAGE, pattern(g, p));
		}
	struct ub_status done = status();
	require(done.idle && !done.pending && !done.errors && (native || done.reader_peak == 2) &&
		done.counts.handbacks == done.counts.acks, "no stranded ownership/ACK");
	atomic_store(&leave_threads, 1);
	if (!native && !cancellation) {
		for (unsigned int g = 0; g < groups; g++) require(!pthread_join(workers[g].thread, NULL), "join origins");
		require(!pthread_join(holder, NULL), "join controller");
		if (fault_test) require(!pthread_join(late_thread, NULL) && !close(late_stack_fd), "join fault observer");
	}
	unsigned int cleanup = 0;
	for (unsigned int g = 0; g < groups; g++) {
		require(!munmap((void *)addresses[g], 3 * PAGE), "cleanup all target pieces"); cleanup++;
		require(!munmap((void *)(addresses[g] - 2 * PAGE), PAGE), "cleanup left neighbor"); cleanup++;
		require(!munmap((void *)(addresses[g] + 4 * PAGE), PAGE), "cleanup right neighbor"); cleanup++;
		for (unsigned int p = 0; p < 3; p++) require(!mapped(addresses[g] + p * PAGE), "cleanup target absence");
		require(!mapped(addresses[g] - 2 * PAGE) && !mapped(addresses[g] + 4 * PAGE), "cleanup neighbor absence");
	}
	if (resident) require(!ioctl(device, UB_DROP), "retire every exact test reference");
	struct ub_status clean = status(); struct ub_extra clean_extra = extra();
	require(clean.idle && !clean.pending && !clean.errors && !clean_extra.pins_owned &&
		clean_extra.pins_released == (unsigned int)__builtin_popcount(pin_mask) && clean.counts.removed == done.counts.removed &&
		clean.counts.delegated == done.counts.delegated && clean.counts.failed == done.counts.failed &&
		clean.counts.calls == done.counts.calls + (native ? 0 : cleanup) &&
		clean.counts.native == done.counts.native + (native ? 0 : cleanup), "cleanup cannot replay a failed body");
	require(!close(device), "release mm reference");
	printf("{\"mixed\":1,\"zero_case\":%d,\"missing_case\":%d,\"busy_page\":%d,\"late_slot\":%u,\"masks\":[",zero_case,missing_case,busy_page,late_slot);
	for (unsigned int g=0;g<groups;g++) printf("%s%u",g?",":"",masks[g]);
	printf("],\"ptes_before\":[");for(unsigned int g=0;g<groups;g++){if(g)putchar(',');print_ptes(&ptes_before[g]);}
	printf("],\"ptes_after\":[");for(unsigned int g=0;g<groups;g++){if(g)putchar(',');print_ptes(&ptes_after[g]);}
	printf("],\"resident\":%d,\"native\":%d,\"injection\":%d,\"busy\":%d,\"cancel\":%d,\"free_first\":%d,\"slice\":%u,\"groups\":%u,\"mm\":%llu,\"gate\":%llu,\"checks\":%lu,\"errors\":%llu,\"idle\":1,\"reader_peak\":%llu,\"cleanup_calls\":%u,\"cleanup_tid\":%ld,\"fail_seen\":%llu,\"pins_released_before\":%llu,\"pins_released\":%llu,\"maps_delta\":%d,\"pages_removed\":%u,\"counts\":{",
		resident,native,injection,busy,cancellation,free_first,slice,groups,(unsigned long long)done.mm,(unsigned long long)done.gate,
		checks+(unsigned long)clean.checks,(unsigned long long)clean.errors,(unsigned long long)done.reader_peak,cleanup,syscall(SYS_gettid),
		(unsigned long long)extra_after.fail_seen,(unsigned long long)extra_before.pins_released,(unsigned long long)clean_extra.pins_released,map_delta,removed_pages);
	print_counts(&done.counts); printf("},\"after_cleanup\":{"); print_counts(&clean.counts); printf("},\"origins\":[");
	for (unsigned int g = 0; g < groups; g++) {
		unsigned int offset = injection && !native && !g ? 0 : slice, width = injection && !native && !g ? 3 : 1;
		printf("%s{\"tid\":%llu,\"start\":%llu,\"end\":%llu,\"old_start\":%llu,\"old_end\":%llu,\"result\":%d,\"errno\":%d,\"fault\":%d,\"original_anon\":%llu,\"original_link\":%llu,\"layouts\":",g ? "," : "",
			cancellation ? (unsigned long long)done.cancel_tid[g] : (unsigned long long)workers[g].tid,
			(unsigned long long)(addresses[g]+offset*PAGE),(unsigned long long)(addresses[g]+(offset+width)*PAGE),
			(unsigned long long)addresses[g],(unsigned long long)(addresses[g]+3*PAGE),cancellation ? (int)done.cancel_result[g] : workers[g].result,workers[g].error,workers[g].fault,
			(unsigned long long)roots[g].anon,(unsigned long long)roots[g].link);
		print_layouts(g); putchar('}');
	}
	printf("],\"pages_before\":"); print_pages(&pages_before); printf(",\"pages_after\":"); print_pages(&pages_after);
	printf(",\"late_fault_blocked\":%d,\"late_fault_code\":%d,\"late_fault_value\":%d,\"late_fault_stack\":",late_blocked,late_code,fault_value); print_string(late_stack); puts("}");
	return 0;
}
