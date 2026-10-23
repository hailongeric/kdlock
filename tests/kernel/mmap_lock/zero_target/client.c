// SPDX-License-Identifier: GPL-2.0
#define main old_whole_probe_main
#include "../unmap_body/client.c"
#undef main
#ifndef KD_TEST_ABSENT
#define KD_TEST_ABSENT 0
#endif
#ifndef KD_TEST_TABLE
#define KD_TEST_TABLE 0
#endif

static int resident, native, injection, busy, cancellation, free_first;
static unsigned int slice, masks[3], zeros[3], pin_mask, late_slot;
static int no_resident, missing_target, busy_page, changing;
static int empty_control, inherited;
static int missing_table, changing_zero, changing_empty, upper_refusal, fault_interaction;
static unsigned int table_change;
static uintptr_t anchors[3];
static struct ub_change change;
static struct ub_change_more change_more;
/* Survivor letters are ordered by ascending address, excluding the target.
 * R is a private resident page, Z a verified shared-zero PTE, U no PTE. */
static const struct { const char *name; unsigned int target, mask, zero; } shapes[] = {
	{"prefix-ru", 0, 2, 1}, {"prefix-ur", 0, 4, 1}, {"prefix-rz", 0, 2, 5},
	{"prefix-zr", 0, 4, 3}, {"prefix-rr", 0, 6, 1},
	{"middle-ru", 1, 1, 2}, {"middle-ur", 1, 4, 2}, {"middle-rz", 1, 1, 6},
	{"middle-zr", 1, 4, 3}, {"middle-rr", 1, 5, 2},
	{"suffix-ru", 2, 1, 4}, {"suffix-ur", 2, 2, 4}, {"suffix-rz", 2, 1, 6},
	{"suffix-zr", 2, 2, 5}, {"suffix-rr", 2, 3, 4},
	{"prefix-zz", 0, 0, 7}, {"prefix-zu", 0, 0, 3},
	{"prefix-uz", 0, 0, 5}, {"prefix-uu", 0, 0, 1},
	{"middle-zz", 1, 0, 7}, {"middle-zu", 1, 0, 3},
	{"middle-uz", 1, 0, 6}, {"middle-uu", 1, 0, 2},
	{"suffix-zz", 2, 0, 7}, {"suffix-zu", 2, 0, 5},
	{"suffix-uz", 2, 0, 6}, {"suffix-uu", 2, 0, 4},
};
static FILE *smaps;
static struct residency { uintptr_t lo, hi; unsigned long rss, anon; unsigned int seen; } residency[3][3][3];
static struct ub_ptes ptes_before[3], ptes_after[3], ptes_written[3];
static struct ub_pte_tables tables_before[3], tables_after[3];
static struct ub_table_walk walks_before[3], walks_after[3], walks_accessed[3], walks_written[3], walks_cleanup[3];
static struct ub_ptes independent_before, independent_after;
static struct { unsigned int group, slot; struct ub_ptes state, independent; } writes[9];
static unsigned int write_count;
static struct ub_ptes independent(void)
{
	/* Separate, pre-existing neighbor VMA; this query never accesses its data. */
	struct ub_ptes r = {.address = KD_TEST_TABLE ? anchors[0] : addresses[0] - 2 * PAGE};
	require(!ioctl(device, UB_PTES, &r) && (r.zero & 1) && !(r.anon & 1) && !(r.none & 1) && !(r.other & 1),
		"independent mapping still uses the kernel shared zero page");
	check_page(r.address, 0); return r;
}
static struct ub_pages pages_before, pages_after;
static struct ub_pte_tables table_state(unsigned int g)
{
	struct ub_pte_tables r = {.ptes.address = addresses[g]};
	require(!ioctl(device, UB_PTE_TABLES, &r), "read-only existing table and leaf-state query");
	return r;
}
static void check_tables(unsigned int g, struct ub_pte_tables *r)
{
	int missing = missing_table && g == 1;
	require(r->leaf == (missing ? 0U : 7U) && r->higher_none == (missing ? 7U : 0U),
		"empty leaf and absent upper-level table are distinct");
	for (unsigned int i = 0; i < 3; i++)
		require(missing ? !r->table_pfn[i] : r->table_pfn[i] && r->table_pfn[i] == r->table_pfn[0],
			"all three leaf entries share the retained table");
}
static struct ub_table_walk walk_state(unsigned int g)
{
	struct ub_table_walk w = {.tables.ptes.address = addresses[g]};
	require(!ioctl(device, UB_TABLE_WALK, &w), "exact upper/PMD/leaf walk without allocation");
	return w;
}
static void check_walk(unsigned int g, struct ub_table_walk *w, int leaf, int upper)
{
	require(w->tables.leaf == (leaf ? 7U : 0U) && w->pmd_none == (!leaf && !upper ? 7U : 0U) &&
		w->upper_none == (upper ? 7U : 0U) && w->tables.higher_none == (leaf ? 0U : 7U),
		"missing leaf, missing upper and populated table are distinct");
	for (unsigned int p = 0; p < 3; p++) {
		require(leaf ? w->tables.table_pfn[p] && w->tables.table_pfn[p] == w->tables.table_pfn[0] : !w->tables.table_pfn[p],
			"one shared leaf table or no leaf table");
		require(upper ? !w->parent_pfn[p] : w->parent_pfn[p] && w->parent_pfn[p] == w->parent_pfn[0],
			"required PMD table identity");
		if (w != &walks_before[g] && walks_before[g].parent_pfn[p])
			require(w->parent_pfn[p] == walks_before[g].parent_pfn[p], "upper table never replaced by unmap or later fault");
	}
}
static void print_walks(struct ub_table_walk *w)
{
	putchar('[');
	for (unsigned int g = 0; g < groups; g++) {
		printf("%s{\"pmd_none\":%llu,\"upper_none\":%llu,\"parent_pfn\":[%llu,%llu,%llu],\"leaf\":%llu,\"table_pfn\":[%llu,%llu,%llu]}",
			g ? "," : "", (unsigned long long)w[g].pmd_none, (unsigned long long)w[g].upper_none,
			(unsigned long long)w[g].parent_pfn[0], (unsigned long long)w[g].parent_pfn[1], (unsigned long long)w[g].parent_pfn[2],
			(unsigned long long)w[g].tables.leaf, (unsigned long long)w[g].tables.table_pfn[0],
			(unsigned long long)w[g].tables.table_pfn[1], (unsigned long long)w[g].tables.table_pfn[2]);
	}
	putchar(']');
}
static void print_tables(struct ub_pte_tables *r)
{
	printf("{\"leaf\":%llu,\"higher_none\":%llu,\"pfn\":[%llu,%llu,%llu]}",
		(unsigned long long)r->leaf,(unsigned long long)r->higher_none,
		(unsigned long long)r->table_pfn[0],(unsigned long long)r->table_pfn[1],(unsigned long long)r->table_pfn[2]);
}
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
	/* Warm resident and already-zero translations; never touch U slots here. */
	if (resident)
		for (unsigned int p = 0; p < 3; p++)
			if (((masks[w->group] | zeros[w->group]) & (1U << p)) && (probe_read(addresses[w->group] + p * PAGE) || observed != ((masks[w->group] & (1U << p)) ? pattern(w->group, p) : 0))) _exit(93);
	atomic_store(&w->ready, 1);
	while (!atomic_load(&w->go)) usleep(1000);
	errno = 0;
	w->result = munmap((void *)(addresses[w->group] + w->offset * PAGE), w->width * PAGE);
	w->error = errno;
	/* An untouched failed target is read by the controller only after its
	 * page-table accounting/layout snapshot, so that read cannot obscure it. */
	w->fault = w->result && (!resident || KD_TEST_ABSENT) ? -2 : probe_read(addresses[w->group] + w->offset * PAGE);
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
	/* Fault on a U survivor, or the untouched neighbor when both survivors
	 * already have PTEs. Admission must block this real fault until handoff. */
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
/* smaps walks the explicit mm without accessing the target addresses. Observe
 * RSS/Anonymous before removal, before survivor reads, and after local writes;
 * a shared zero-page read contributes no ordinary anonymous resident page. */
static void account(unsigned int phase)
{
	char line[1024]; uintptr_t lo = 0, hi = 0; unsigned long value;
	rewind(smaps);
	while (fgets(line, sizeof(line), smaps)) {
		uintptr_t a, b;
		if (sscanf(line, "%lx-%lx", &a, &b) == 2) {
			lo = a; hi = b;
			for (unsigned int g = 0; g < groups; g++) for (unsigned int p = 0; p < 3; p++)
				if (addresses[g] + p * PAGE >= lo && addresses[g] + p * PAGE < hi) {
					struct residency *r = &residency[phase][g][p];
					require(!r->seen, "one smaps entry per mapped slot");
					r->lo = lo; r->hi = hi; r->seen = 1;
				}
		} else {
			unsigned int field = sscanf(line, "Rss: %lu kB", &value) == 1 ? 2 :
				sscanf(line, "Anonymous: %lu kB", &value) == 1 ? 4 : 0;
			if (!field) continue;
			for (unsigned int g = 0; g < groups; g++) for (unsigned int p = 0; p < 3; p++) {
				struct residency *r = &residency[phase][g][p];
				if (r->seen && r->lo == lo && r->hi == hi) {
					require(!(r->seen & field), "one resident accounting field");
					r->seen |= field;
					if (field == 2) r->rss = value; else r->anon = value;
				}
			}
		}
	}
	require(!ferror(smaps), "complete read-only resident accounting");
	for (unsigned int g = 0; g < groups; g++) for (unsigned int p = 0; p < 3; p++) {
		struct residency *r = &residency[phase][g][p]; unsigned int count = 0;
		if (phase && removed(g, p)) {
			require(!r->seen, "removed slot absent from smaps"); continue;
		}
		require(r->seen == 7 && r->lo >= addresses[g] && r->hi <= addresses[g] + 3 * PAGE,
			"complete per-VMA resident accounting");
		for (unsigned int q = 0; q < 3; q++)
			if (addresses[g] + q * PAGE >= r->lo && addresses[g] + q * PAGE < r->hi &&
			    (!phase || !removed(g, q)) && (phase == 2 || (masks[g] & (1U << q)))) count++;
		require(r->rss == count * (PAGE / 1024) && r->anon == r->rss,
			"only expected ordinary resident anonymous pages contribute RSS");
	}
}
static void print_account(void)
{
	putchar('[');
	for (unsigned int phase = 0; phase < 3; phase++) {
		if (phase) putchar(',');
		putchar('[');
		for (unsigned int g = 0; g < groups; g++) {
			if (g) putchar(',');
			putchar('[');
			for (unsigned int p = 0; p < 3; p++) {
				struct residency *r = &residency[phase][g][p];
				printf("%s{\"mapped\":%d,\"lo\":%lu,\"hi\":%lu,\"rss_kb\":%lu,\"anonymous_kb\":%lu}",
					p ? "," : "", !!r->seen, r->seen ? r->lo - addresses[g] : 0,
					r->seen ? r->hi - addresses[g] : 0, r->rss, r->anon);
			}
			putchar(']');
		}
		putchar(']');
	}
	putchar(']');
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
			if (roots[g].anon) {
				require(r.anon == roots[g].anon && r.root == roots[g].root && r.links == 1 &&
					r.refs == roots[g].refs && r.active == 1 + splits - lost && r.intervals == r.active,
					"reverse-map root, links, active VMAs and reference lifetime");
			} else if (changing && !changing_zero && !changing_empty && g == (native ? 0U : 1U)) {
				/* The controlled write fault created ancestry after preparation.
				 * Its removed private target leaves the same root on both splits. */
				require(r.anon && r.root == r.anon && r.links == 1 && r.refs == 1 &&
					r.active == 1 + splits - lost && r.intervals == r.active &&
					(!p || r.anon == rmaps[g][0].anon), "new native reverse-map ancestry survives target removal");
				if (KD_TEST_ABSENT) require(r.anon == change_more.anon_after,
					"surviving ancestry matches the controlled native fault");
			} else require(!r.anon && !r.links && !r.refs && !r.active && !r.intervals,
				"absent reverse map remains absent before first private write");
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
	require(argc == 3 || argc == 6, "target|native SHAPE or error native|kd resident middle-rz 1|2");
	if (argc == 6) {
		require(!strcmp(argv[1], "error") && (!strcmp(argv[2], "native") || !strcmp(argv[2], "kd")) &&
			(!strcmp(argv[3], "resident") || !strcmp(argv[3], "untouched")), "error mode");
		native = !strcmp(argv[2], "native"); resident = !strcmp(argv[3], "resident"); injection = atoi(argv[5]);
		require(injection == 1 || injection == 2, "reachable split count");
	} else {
		require(!strcmp(argv[1], "target") || !strcmp(argv[1], "native"), "target/native mode"); resident = 1;
		native = !strcmp(argv[1], "native");
		empty_control = !strcmp(argv[2], "change-empty") || !strcmp(argv[2], "missing-empty") || !strcmp(argv[2], "cancel-empty");
		inherited = !strcmp(argv[2], "inherited");
		missing_table = KD_TEST_ABSENT && !strcmp(argv[2], "missing-table");
		table_change = KD_TEST_TABLE ? !strcmp(argv[2], "change-table-empty") ? 3 :
			!strcmp(argv[2], "change-table-zero") ? 4 : !strcmp(argv[2], "change-table-private") ? 5 : 0 : 0;
		changing_empty = table_change == 3;
		changing_zero = (KD_TEST_ABSENT && !strcmp(argv[2], "change-zero")) || table_change == 4;
		upper_refusal = KD_TEST_TABLE && !strcmp(argv[2], "upper-refusal");
		fault_interaction = KD_TEST_TABLE && !strcmp(argv[2], "fault");
		busy_page = !strcmp(argv[2], "refusal");
		missing_target = !strcmp(argv[2], "missing") || !strcmp(argv[2], "missing-empty");
		changing = !strcmp(argv[2], "change") || !strcmp(argv[2], "change-empty") ||
			changing_zero || table_change || (KD_TEST_ABSENT && !strcmp(argv[2], "change-private"));
		if (KD_TEST_ABSENT && (missing_table || changing || upper_refusal)) empty_control = 1;
		busy = busy_page || missing_target || missing_table || upper_refusal;
		cancellation = !strcmp(argv[2], "cancel") || !strcmp(argv[2], "cancel-empty"); free_first = !strcmp(argv[2], "free");
	}
	const char *shape = argc == 6 ? argv[4] : argv[2];
	unsigned int shape_mask = busy_page ? 5 : changing ? 4 : 1, shape_zero = busy_page ? 2 : changing ? 3 : 6; int found = 0; slice = 1;
	if (empty_control || inherited) { shape_mask = 0; shape_zero = 7; }
	for (unsigned int i = 0; i < sizeof(shapes) / sizeof(shapes[0]); i++)
		if (!strcmp(shape, shapes[i].name)) { found = 1; slice = shapes[i].target; shape_mask = shapes[i].mask; shape_zero = shapes[i].zero; }
	require(found || busy || cancellation || free_first || changing || inherited || fault_interaction, "shape");
	require(!KD_TEST_ABSENT || (!inherited && !missing_target), "absent target has no fabricated history or obsolete missing-PTE refusal");
	if (KD_TEST_TABLE) {
		require(!shape_mask || (!found && (changing || cancellation || upper_refusal || fault_interaction)),
			"a missing leaf table cannot contain any resident survivor");
		require(!found || shape_zero == (1U << slice), "only UU survivors are geometrically possible");
		shape_mask = shape_zero = 0;
		require(!busy_page && !missing_target && !missing_table && !inherited && !free_first,
			"missing-table path uses explicit narrow controls");
	}
	require(!native || !(busy || cancellation || free_first), "native success controls use supported shapes");
	require(injection != 2 || slice == 1, "two splits only for an interior range");
	require(resident && (!injection || slice == 1), "zero-survivor resident interior error scope");
	pin(63); groups = native ? 1 : injection || cancellation || free_first ? 2 : 3;
	struct sigaction action = {.sa_sigaction = segv, .sa_flags = SA_SIGINFO};
	sigemptyset(&action.sa_mask); require(!sigaction(SIGSEGV, &action, NULL), "signal handler");
	device = open("/dev/kd_mm_unmap_test", O_RDWR | O_CLOEXEC); require(device >= 0, "probe open");
	struct ub_status initial = status();
	uintptr_t stride = KD_TEST_TABLE ? (upper_refusal ? 1UL << 30 : 4UL << 20) : resident ? 2 * 1024 * 1024 : initial.pgdir_size;
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
		if (KD_TEST_TABLE) {
			anchors[g] = addresses[g] + (2UL << 20);
			require((addresses[g] & ~((2UL << 20) - 1)) == ((addresses[g] + 3 * PAGE - 1) & ~((2UL << 20) - 1)) &&
				(addresses[g] >> 21) != (anchors[g] >> 21) && (addresses[g] >> 30) == (anchors[g] >> 30),
				"three-page VMA in one PMD, anchor in a different PMD of the same PUD");
			require(mmap((void *)anchors[g], PAGE, PROT_READ | PROT_WRITE,
				MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0) == (void *)anchors[g] &&
				!madvise((void *)anchors[g], PAGE, MADV_NOHUGEPAGE), "separate upper-level anchor VMA");
			if (!(upper_refusal && g == 1)) require(!probe_read(anchors[g]) && !observed,
				"construct upper levels without allocating the target leaf table");
		}
		masks[g] = shape_mask; zeros[g] = shape_zero;
		if (injection && !native && !g) { masks[g] = 7; zeros[g] = 0; }
		if (missing_target && g == 1) { masks[g] = empty_control ? 0 : 1; zeros[g] = empty_control ? 5 : 4; }
		if (KD_TEST_ABSENT) zeros[g] &= ~(1U << slice);
		if (missing_table && g == 1) { masks[g] = 0; zeros[g] = 0; }
		if (inherited) {
			/* Only the TARGET gets a temporary private history. No survivor is
			 * populated to bypass eligibility. DONTNEED keeps its simple VMA
			 * ancestry but drops the private page; the later read proves Z. */
			memset((void *)(addresses[g] + slice * PAGE), 0x37, PAGE);
			require(!madvise((void *)(addresses[g] + slice * PAGE), PAGE, MADV_DONTNEED), "drop historical private target before zero read fault");
		}
		pin_mask |= masks[g] << (g * 3);
		for (unsigned int p = 0; p < 3; p++) if (masks[g] & (1U << p)) memset((void *)(addresses[g] + p * PAGE), pattern(g, p), PAGE);
		for (unsigned int p = 0; p < 3; p++) if (zeros[g] & (1U << p))
			require(!probe_read(addresses[g] + p * PAGE) && !observed, "read-fault intended zero slot without writing");
		if (KD_TEST_ABSENT && !KD_TEST_TABLE && !(missing_table && g == 1))
			require(!probe_read(addresses[g] - 2 * PAGE) && !observed,
				"independent neighbor establishes an existing table without accessing any target slot");
		original[g] = layout(addresses[g]); roots[g] = rmap(addresses[g]);
		if (masks[g] || inherited) require(roots[g].anon && roots[g].anon == roots[g].root && roots[g].links == 1 && roots[g].active == 1 && roots[g].intervals == 1, "one original reverse-map chain");
		else require(!roots[g].anon && !roots[g].links, "no private page means no fabricated reverse map");
	}
	require(!probe_read(KD_TEST_TABLE ? anchors[0] : addresses[0] - 2 * PAGE) && !observed, "read-fault independent zero mapping");
	independent_before = independent();
	struct ub_experiment e = {{base - 2 * PAGE, addresses[groups - 1] + 5 * PAGE, base, stride}, native ? 0 : resident ? 2 : 1, groups, injection};
	require(!ioctl(device, UB_EXPERIMENT, &e), "explicit experiment opt-in");
	if (resident) {
		require((!pin_mask || !ioctl(device, UB_PIN_MASK, (unsigned long)pin_mask)) && !ioctl(device, UB_PAGESTATE, &pages_before), "exact original page references, including zero owned pages");
		for (unsigned int i = 0; i < pages_before.count; i++) if (pin_mask & (1U << i)) require(pages_before.page[i].mapcount == 1 && pages_before.page[i].refs == 2 && !pages_before.page[i].locked, "initial page ownership");
		if (free_first) require(!ioctl(device, UB_UNPIN_MAPPED), "drop test references before real final release");
		if (busy_page) require(!ioctl(device, UB_BUSY_LOCK), "make final page busy before admission");
	}
	for (unsigned int g = 0; g < groups; g++) {
		if (KD_TEST_TABLE) {
			walks_before[g] = walk_state(g);
			check_walk(g, &walks_before[g], injection && !native && !g, upper_refusal && g == 1);
			tables_before[g] = walks_before[g].tables; ptes_before[g] = tables_before[g].ptes;
		} else if (KD_TEST_ABSENT) {
			tables_before[g] = table_state(g); check_tables(g, &tables_before[g]);
			ptes_before[g] = tables_before[g].ptes;
			require((injection && !native && !g) || (ptes_before[g].none & (1U << slice)),
				"target is absent before admission without a data access");
		} else ptes_before[g] = ptes(g);
		check_ptes(g, ptes_before[g], masks[g], zeros[g]);
	}
	smaps = fopen("/proc/self/smaps", "r"); require(smaps != NULL, "open per-VMA resident accounting");
	account(0); /* Allocate/warm the observation buffer before global mm counters. */
	while (late_slot < 3 && ((masks[1] | zeros[1] | (1U << slice)) & (1U << late_slot))) late_slot++;
	if (late_slot == 3) late_slot = 4; /* Existing, untouched neighbor VMA. */
	if (changing) require(!ioctl(device, KD_TEST_TABLE ? (table_change == 3 ? UB_CHANGE_TABLE_EMPTY_ARM :
		table_change == 4 ? UB_CHANGE_TABLE_ZERO_ARM : UB_CHANGE_TABLE_PRIVATE_ARM) : KD_TEST_ABSENT ?
		(changing_zero ? UB_CHANGE_EMPTY_ZERO_ARM : UB_CHANGE_EMPTY_PRIVATE_ARM) : UB_CHANGE_ARM,
		native ? 1UL : 4UL), "arm exact target transition before queued execution");
	extra_before = extra();
	int fault_test = !native && !injection && !busy && !cancellation && (!KD_TEST_TABLE || fault_interaction);
	if (native) {
		before = layout(base); workers[0].tid = syscall(SYS_gettid); workers[0].offset = slice; workers[0].width = 1;
		if (changing) require(!ioctl(device, UB_CHANGE_NOW), "native controlled zero-to-private fault");
		errno = 0; workers[0].result = munmap((void *)(base + slice * PAGE), PAGE); workers[0].error = errno;
		workers[0].fault = KD_TEST_ABSENT && workers[0].result ? -2 : probe_read(base + slice * PAGE);
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
			if ((injection || busy || changing) && !g) wait_state(2, 1);
		}
		wait_state(1, 0);
		if (fault_test) capture_late_fault(1);
		require(!ioctl(device, UB_RELEASE), "release concurrent readers");
		for (unsigned int g = 0; g < (busy ? 2 : groups); g++) wait_atomic(&workers[g].done);
		if (busy) { atomic_store(&workers[2].go, 1); wait_atomic(&workers[2].done); }
		if (fault_test) { wait_atomic(&late_done); require(!late_code && !fault_value, "real survivor fault resolves locally"); }
		wait_atomic(&holder_done); require(!hold_error, "reader controller drained");
	}
	if (changing) {
		if (KD_TEST_ABSENT) {
			require(!ioctl(device, UB_CHANGE_RESULT_MORE, &change_more), "extended native transition result");
			change = change_more.state;
			if (KD_TEST_TABLE) require(change_more.mode == table_change && !change_more.before_none && !change.before_zero &&
				change_more.after_zero == (unsigned)changing_zero && change.after_private == (unsigned)(table_change == 5) &&
				!change_more.table_before && change_more.table_after && !change_more.anon_before &&
				(table_change == 5 ? !!change_more.anon_after : !change_more.anon_after), "native fault constructs the missing table before execution");
			else require(change_more.mode == (changing_zero ? 1U : 2U) && change_more.before_none && !change.before_zero &&
				change_more.after_zero == (unsigned)changing_zero && change.after_private == (unsigned)!changing_zero &&
				change_more.table_before == tables_before[native ? 0 : 1].table_pfn[0] &&
				change_more.table_after == change_more.table_before && !change_more.anon_before &&
				(changing_zero ? !change_more.anon_after : !!change_more.anon_after),
				"absent target changes through a native fault in the same retained table");
		} else require(!ioctl(device, UB_CHANGE_RESULT, &change) && change.before_zero && change.after_private,
			"native zero-to-private transition");
		require(change.done && !change.result, "native target transition completed before body admission");
		require(change.index == (native ? 1U : 4U) && change.pending == (native ? 0U : 3U) &&
			change.readers == (native ? 1U : 2U) && (native || change.admission == -1) &&
			(changing_empty ? !change.page.pfn && !change.zero_pfn : changing_zero ? !change.page.pfn && !change.page.refs && change.zero_pfn :
			change.page.mapcount == 1 && change.page.refs == 2 && change.page.charged_same && !change.page.locked),
			"changed target exact reference and queued/local-reader ordering");
		if (!changing_zero && !changing_empty) pin_mask |= 1U << change.index;
	}
	after = layout(base); extra_after = extra();
	unsigned int removed_pages = injection ? (native ? 0 : 3) : cancellation ? 1 : groups;
	int map_delta = injection ? injection - !native : slice == 1 ? (int)removed_pages : 0;
	require(before.total_vm == after.total_vm + removed_pages && before.data_vm == after.data_vm + removed_pages &&
		before.exec_vm == after.exec_vm && before.stack_vm == after.stack_vm &&
		(long long)after.map_count - (long long)before.map_count == map_delta && before.pgtables + (KD_TEST_TABLE && (changing || fault_test) ? PAGE : 0) == after.pgtables,
		"exact native page/VMA/table accounting including harmless splits");
	require(extra_after.fail_after == 0 && extra_after.fail_seen == !!injection, "one exact injection consumed");
	if (!cancellation) for (unsigned int g = 0; g < groups; g++) {
		int failed = injection && (native || g == 1);
		require(workers[g].result == (failed ? -1 : 0) && (!failed || workers[g].error == ENOMEM), "original caller receives exact return");
		require(workers[g].fault == (failed ? (resident && !KD_TEST_ABSENT ? 0 : -2) : SEGV_MAPERR), "same CPU checks removal, delaying reads of failed absent targets");
	}
	for (unsigned int g = 0; g < groups; g++) {
		unsigned int gone = 0;
		for (unsigned int p = 0; p < 3; p++) if (removed(g, p)) gone |= 1U << p;
		if (KD_TEST_TABLE) {
			walks_after[g] = walk_state(g);
			check_walk(g, &walks_after[g], (injection && !native && !g) ||
				(changing && g == (native ? 0U : 1U)) || (fault_test && g == 1), upper_refusal && g == 1);
			tables_after[g] = walks_after[g].tables; ptes_after[g] = tables_after[g].ptes;
			if (changing && g == (native ? 0U : 1U)) require(tables_after[g].table_pfn[0] == change_more.table_after,
				"execution preserves the exact fault-created table");
		} else if (KD_TEST_ABSENT) {
			tables_after[g] = table_state(g); check_tables(g, &tables_after[g]);
			for (unsigned int p = 0; p < 3; p++) require(tables_after[g].table_pfn[p] == tables_before[g].table_pfn[p],
				"the exact leaf table remains without freeing or replacement");
			ptes_after[g] = tables_after[g].ptes;
		} else ptes_after[g] = ptes(g);
		check_ptes(g, ptes_after[g], masks[g] & ~gone,
			(zeros[g] & ~gone) | (fault_test && g == 1 && late_slot < 3 ? 1U << late_slot : 0));
	}
	account(1); /* No survivor read by this controller precedes this snapshot. */
	verify_mappings();
	if (KD_TEST_TABLE) for (unsigned int g = 0; g < groups; g++) {
		walks_accessed[g] = walk_state(g); check_walk(g, &walks_accessed[g], 1, 0);
		if (tables_after[g].table_pfn[0]) require(walks_accessed[g].tables.table_pfn[0] == tables_after[g].table_pfn[0],
			"later survivor reads retain any table already installed");
	}
	if (busy_page) require(!ioctl(device, UB_BUSY_UNLOCK), "release original busy-page lock");
	if (resident && !free_first) {
		require(!ioctl(device, UB_PAGESTATE, &pages_after), "post-body exact page references");
		for (unsigned int i = 0; i < pages_after.count; i++) {
			struct ub_page *a = changing && i == change.index ? &change.page : &pages_before.page[i], *b = &pages_after.page[i]; int gone = removed(i / 3, i % 3);
			if (!(pin_mask & (1U << i))) {
				require(!a->pfn && !a->refs && !b->pfn && !b->refs, "untouched slots acquire no test reference"); continue;
			}
			require(a->pfn == b->pfn && a->hash == b->hash && b->mapcount == (unsigned)!gone &&
				b->refs == (unsigned)(2 - gone) && !b->locked && b->charged_same,
				"exact pages retained, unlocked and reference-balanced after completion/error/refusal");
		}
	}
	/* The pre-access observations above prove U and Z separately. Full reads
	 * now populate remaining U slots with zero PTEs, then private writes must
	 * change only the selected slot, never another or the independent zero. */
	for (unsigned int g = 0; g < groups; g++) {
		unsigned int gone = 0, written = 0;
		for (unsigned int p = 0; p < 3; p++) if (removed(g, p)) gone |= 1U << p;
		for (unsigned int p = 0; p < 3; p++) if (!removed(g, p) && !(masks[g] & (1U << p))) {
			memset((void *)(addresses[g] + p * PAGE), pattern(g, p), PAGE); written |= 1U << p;
			struct ub_ptes r = ptes(g);
			unsigned int anon = (masks[g] | written) & ~gone, zero = 7U & ~(anon | gone);
			require(r.anon == anon && r.zero == zero && r.none == gone && !r.other, "one private write converts exactly one zero PTE");
			for (unsigned int q = 0; q < 3; q++) if (!removed(g, q)) {
				check_page(addresses[g] + q * PAGE, (anon & (1U << q)) ? pattern(g, q) : 0);
				if (anon & (1U << q)) {
					require(r.pfn[q] && (!(masks[g] & (1U << q)) || r.pfn[q] == pages_before.page[g * 3 + q].pfn), "private physical identity after write");
					for (unsigned int t = 0; t < q; t++) if (anon & (1U << t)) require(r.pfn[q] != r.pfn[t], "private survivors do not alias");
				}
			}
			require(write_count < 9, "bounded write observations");
			writes[write_count].group = g; writes[write_count].slot = p;
			writes[write_count].state = r; writes[write_count++].independent = independent();
		}
		ptes_written[g] = ptes(g);
		require(ptes_written[g].anon == (7U & ~gone) && ptes_written[g].none == gone &&
			!ptes_written[g].zero && !ptes_written[g].other, "survivors end as private writable pages");
	}
	if (KD_TEST_TABLE) for (unsigned int g = 0; g < groups; g++) {
		walks_written[g] = walk_state(g); check_walk(g, &walks_written[g], 1, 0);
		require(walks_written[g].tables.table_pfn[0] == walks_accessed[g].tables.table_pfn[0],
			"isolated writes keep the same leaf table");
	}
	independent_after = independent();
	account(2);
	require(!fclose(smaps), "close resident accounting observer");
	struct ub_status done = status();
	require(done.idle && !done.pending && !done.errors && (native || done.reader_peak == 2) &&
		done.counts.handbacks == done.counts.acks, "no stranded ownership/ACK");
	atomic_store(&leave_threads, 1);
	if (!native && !cancellation) {
		for (unsigned int g = 0; g < groups; g++) require(!pthread_join(workers[g].thread, NULL), "join origins");
		require(!pthread_join(holder, NULL), "join controller");
		if (fault_test) require(!pthread_join(late_thread, NULL) && !close(late_stack_fd), "join fault observer");
	}
	unsigned int cleanup = 0, routed_cleanup = 0;
	for (unsigned int g = 0; g < groups; g++) {
		require(!munmap((void *)addresses[g], 3 * PAGE), "cleanup all target pieces"); cleanup++;
		require(!munmap((void *)(addresses[g] - 2 * PAGE), PAGE), "cleanup left neighbor"); cleanup++;
		require(!munmap((void *)(addresses[g] + 4 * PAGE), PAGE), "cleanup right neighbor"); cleanup++;
		for (unsigned int p = 0; p < 3; p++) require(!mapped(addresses[g] + p * PAGE), "cleanup target absence");
		require(!mapped(addresses[g] - 2 * PAGE) && !mapped(addresses[g] + 4 * PAGE), "cleanup neighbor absence");
		routed_cleanup += 3;
	}
	if (KD_TEST_TABLE) {
		for (unsigned int g = 0; g < groups; g++) {
			require(!munmap((void *)anchors[g], PAGE) && !mapped(anchors[g]), "cleanup independent upper anchor"); cleanup++;
			if (anchors[g] >= e.region.start && anchors[g] < e.region.end) routed_cleanup++;
		}
		for (unsigned int g = 0; g < groups; g++) {
			walks_cleanup[g] = walk_state(g);
			require(walks_cleanup[g].upper_none == 7 && !walks_cleanup[g].tables.leaf && !walks_cleanup[g].pmd_none &&
				!walks_cleanup[g].parent_pfn[0] && !walks_cleanup[g].tables.table_pfn[0], "local cleanup retires empty table hierarchy");
		}
	}
	if (resident) require(!ioctl(device, UB_DROP), "retire every exact test reference");
	struct ub_status clean = status(); struct ub_extra clean_extra = extra();
	/* The final separate anchor is outside the enabled interval. Its munmap
	 * is still checked, but __vm_munmap never submits it to the KD queue. */
	require(routed_cleanup == cleanup - (KD_TEST_TABLE ? 1U : 0U), "exact cleanup entry routing by enabled interval");
	if (clean.counts.calls != done.counts.calls + (native ? 0 : routed_cleanup) ||
	    clean.counts.native != done.counts.native + (native ? 0 : routed_cleanup))
		fprintf(stderr, "cleanup total=%u routed=%u calls=%llu before=%llu native=%llu before_native=%llu\n", cleanup,routed_cleanup,
			(unsigned long long)clean.counts.calls,(unsigned long long)done.counts.calls,
			(unsigned long long)clean.counts.native,(unsigned long long)done.counts.native);
	require(clean.idle && !clean.pending && !clean.errors && !clean_extra.pins_owned &&
		clean_extra.pins_released == (unsigned int)__builtin_popcount(pin_mask) && clean.counts.removed == done.counts.removed &&
		clean.counts.delegated == done.counts.delegated && clean.counts.failed == done.counts.failed &&
		clean.counts.calls == done.counts.calls + (native ? 0 : routed_cleanup) &&
		clean.counts.native == done.counts.native + (native ? 0 : routed_cleanup), "cleanup cannot replay a failed body");
	require(!close(device), "release mm reference");
	printf("{\"zero_target_test\":%d,\"absent_target_test\":%d,\"shape\":\"%s\",\"no_resident\":%d,\"missing_target\":%d,\"missing_table\":%d,\"busy_page\":%d,\"changing\":%d,\"changing_zero\":%d,\"late_slot\":%u,\"masks\":[",
		!KD_TEST_ABSENT,KD_TEST_ABSENT,shape,no_resident,missing_target,missing_table,busy_page,changing,changing_zero,late_slot);
	for (unsigned int g=0;g<groups;g++) printf("%s%u",g?",":"",masks[g]);
	printf("],\"zero_masks\":[");for(unsigned int g=0;g<groups;g++)printf("%s%u",g?",":"",zeros[g]);
	printf("],\"ptes_written\":[");for(unsigned int g=0;g<groups;g++){if(g)putchar(',');print_ptes(&ptes_written[g]);}
	printf("],\"independent_before\":");print_ptes(&independent_before);
	printf(",\"independent_after\":");print_ptes(&independent_after);
	printf(",\"writes\":[");for(unsigned int i=0;i<write_count;i++){
		printf("%s{\"group\":%u,\"slot\":%u,\"state\":",i?",":"",writes[i].group,writes[i].slot);print_ptes(&writes[i].state);
		printf(",\"independent\":");print_ptes(&writes[i].independent);putchar('}');}
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
	printf(",\"empty_control\":%d,\"inherited\":%d",empty_control,inherited);
	if (KD_TEST_TABLE) {
		printf(",\"interval_cleanup_calls\":%u",routed_cleanup);
		printf(",\"pgdir_size\":%llu,\"page_size\":%lu,\"pmd_size\":%lu,\"pud_size\":%lu",(unsigned long long)initial.pgdir_size,(unsigned long)PAGE,2UL << 20,1UL << 30);
		printf(",\"missing_table_test\":1,\"changing_empty\":%d,\"upper_refusal\":%d,\"fault_interaction\":%d,\"table_bytes_before\":%llu,\"table_bytes_after\":%llu,\"anchors\":[",
			changing_empty,upper_refusal,fault_interaction,(unsigned long long)before.pgtables,(unsigned long long)after.pgtables);
		for (unsigned int g = 0; g < groups; g++) printf("%s%lu",g ? "," : "",(unsigned long)anchors[g]);
		printf("],\"walks_before\":");print_walks(walks_before);
		printf(",\"walks_after\":");print_walks(walks_after);
		printf(",\"walks_accessed\":");print_walks(walks_accessed);
		printf(",\"walks_written\":");print_walks(walks_written);
		printf(",\"walks_cleanup\":");print_walks(walks_cleanup);
	}

	printf(",\"residency\":"); print_account();
	if (KD_TEST_ABSENT) {
		printf(",\"tables_before\":[");for(unsigned int g=0;g<groups;g++){if(g)putchar(',');print_tables(&tables_before[g]);}
		printf("],\"tables_after\":[");for(unsigned int g=0;g<groups;g++){if(g)putchar(',');print_tables(&tables_after[g]);}putchar(']');
		printf(",\"change_more\":{\"mode\":%llu,\"before_none\":%llu,\"after_zero\":%llu,\"table_before\":%llu,\"table_after\":%llu,\"anon_before\":%llu,\"anon_after\":%llu}",
			(unsigned long long)change_more.mode,(unsigned long long)change_more.before_none,(unsigned long long)change_more.after_zero,
			(unsigned long long)change_more.table_before,(unsigned long long)change_more.table_after,
			(unsigned long long)change_more.anon_before,(unsigned long long)change_more.anon_after);
	}
	printf(",\"change\":{\"index\":%llu,\"actor\":%llu,\"pending\":%llu,\"readers\":%llu,\"admission\":%lld,\"zero_pfn\":%llu,\"before_zero\":%llu,\"after_private\":%llu,\"done\":%llu,\"result\":%lld,\"page\":",
		(unsigned long long)change.index,(unsigned long long)change.actor,(unsigned long long)change.pending,(unsigned long long)change.readers,
		(long long)change.admission,(unsigned long long)change.zero_pfn,(unsigned long long)change.before_zero,(unsigned long long)change.after_private,
		(unsigned long long)change.done,(long long)change.result);
	struct ub_pages changed = {.count = changing && !changing_zero && !changing_empty ? 1U : 0U}; changed.page[0] = change.page; print_pages(&changed); putchar('}');
	printf(",\"late_fault_blocked\":%d,\"late_fault_code\":%d,\"late_fault_value\":%d,\"late_fault_stack\":",late_blocked,late_code,fault_value); print_string(late_stack); puts("}");
	return 0;
}
