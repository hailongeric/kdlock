// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE
#ifndef KD_BOUNDARY_EMPTY
#define KD_BOUNDARY_EMPTY 0
#endif
#ifndef KD_BOUNDARY_ZERO
#define KD_BOUNDARY_ZERO 0
#endif
#ifndef KD_BOUNDARY_PRIVATE
#define KD_BOUNDARY_PRIVATE 0
#endif
#ifndef KD_BOUNDARY_INTERIOR
#define KD_BOUNDARY_INTERIOR 0
#endif
#ifndef KD_BOUNDARY_NEAR_ZERO
#define KD_BOUNDARY_NEAR_ZERO 0
#endif
#ifndef KD_BOUNDARY_NEAR_CREATE
#define KD_BOUNDARY_NEAR_CREATE 0
#endif
#ifndef KD_BOUNDARY_NEAR_PRIVATE
#define KD_BOUNDARY_NEAR_PRIVATE 0
#endif
#ifndef KD_NEIGHBOR_TEST
#define KD_NEIGHBOR_TEST 0
#endif
#ifndef KD_BOUNDARY_SHARED
#define KD_BOUNDARY_SHARED 0
#endif
#define KD_BOUNDARY_INTERIOR_PRIVATE (KD_BOUNDARY_INTERIOR && KD_BOUNDARY_PRIVATE)
#define KD_BOUNDARY_EXISTING (KD_BOUNDARY_EMPTY || KD_BOUNDARY_ZERO || KD_BOUNDARY_PRIVATE)
#define KD_BOUNDARY_SHARED_MISSING (KD_BOUNDARY_SHARED && !KD_BOUNDARY_EXISTING)
#include <stdint.h>
static uintptr_t neighbors[3][2];
#define KD_TEST_ABSENT (!(KD_BOUNDARY_ZERO || KD_BOUNDARY_PRIVATE))
#define KD_TEST_TABLE 1
#define KD_TEST_MAIN previous_target_probe_main
#define KD_TEST_NEIGHBOR(g, side) neighbors[g][side]
#include "../zero_target/client.c"
#undef KD_TEST_MAIN
static int free_table, present_table, shared_edge, near_zero, zero_convert, zero_busy;
static int empty_convert, empty_busy, missing_convert, missing_busy, near_private;
static unsigned int interior_right, near_private_write_checks;
static int near_busy, far_busy;
static struct ub_near_create near_create;
static unsigned int target_rechecks_accessed, target_rechecks_written;
struct neighbor { unsigned long address, start, end, pgoff, flags, none, zero, anon, other, pfn; };
static struct neighbor neighbor_before[3][2], neighbor_after[3][2], retention_before;
static unsigned long retention_table_before, retention_table_after;
#if KD_NEIGHBOR_TEST
#include "../neighbor_replace/client.inc"
#endif
static struct neighbor neighbor_state(unsigned int g, unsigned int side)
{
	struct ub_layout l = layout(neighbors[g][side]);
	struct ub_ptes p = {.address = neighbors[g][side]};
	require(!ioctl(device, UB_PTES, &p), "neighbor PTE without data access");
	return (struct neighbor){neighbors[g][side],l.start,l.end,l.pgoff,l.flags,p.none&1,p.zero&1,p.anon&1,p.other&1,p.pfn[0]};
}
static void print_neighbors(void)
{
	printf(",\"neighbors\":[");
	for (unsigned int g = 0; g < groups; g++) {
		printf("%s[",g ? "," : "");
		for (unsigned int side = 0; side < 2; side++) {
			struct neighbor *original_neighbor = &neighbor_before[g][side], *b = &neighbor_after[g][side];
			struct neighbor *a = original_neighbor;
#if KD_NEIGHBOR_TEST
			if (neighbor_selected(g, side)) a = b;
#endif
			printf("%s{\"address\":%lu,\"start\":%lu,\"end\":%lu,\"flags\":%lu,\"pgoff\":%lu,\"none\":%lu,\"zero\":%lu,\"anon\":%lu,\"other\":%lu,\"pfn\":%lu,\"unchanged\":%d}",
				side ? "," : "",a->address,a->start,a->end,a->flags,a->pgoff,a->none,a->zero,a->anon,a->other,a->pfn,!memcmp(original_neighbor,b,sizeof(*a)));
		}
		putchar(']');
	}
	putchar(']');
}
static void edge_walk(unsigned int g, struct ub_table_walk *w, unsigned int phase)
{
	unsigned int leaf = 0;
	int selected = g == (native ? 0U : 1U);
	for (unsigned int p = 0; p < 3; p++) {
		uintptr_t interval = (addresses[g] + p * PAGE) >> 21;
		int exists = 0;
		for (unsigned int q = 0; q < 3; q++)
			if ((addresses[g] + q * PAGE) >> 21 == interval &&
			    (phase < 2 ? !!((masks[g] | zeros[g]) & (1U << q)) && (!phase || !removed(g,q)) : !removed(g,q))) exists = 1;
		if ((KD_BOUNDARY_EXISTING ? !(selected && free_table && phase && !KD_BOUNDARY_SHARED) :
		    selected && (present_table || (!phase && free_table && !KD_BOUNDARY_SHARED_MISSING) || (phase && changing))) &&
		    (addresses[g] + slice * PAGE) >> 21 == interval) exists = 1;
		if (phase && fault_interaction && !native && g == 1 &&
		    (addresses[g] + late_slot * PAGE) >> 21 == interval) exists = 1;
		if (phase >= 2) for (unsigned int side = 0; side < 2; side++)
			if (neighbors[g][side] >> 21 == interval) exists = 1;
		if (injection && !native && !g) exists = 1; /* neighbors retain the head's existing table */
		if (exists) leaf |= 1U << p;
		require(exists ? !!w->tables.table_pfn[p] : !w->tables.table_pfn[p], "per-interval leaf identity");
		require(w->parent_pfn[p] && w->parent_pfn[p] == w->parent_pfn[0], "common required upper directory");
		if (phase) {
			require(w->parent_pfn[p] == walks_before[g].parent_pfn[p], "upper table retained through body and later faults");
			if (w->tables.table_pfn[p] && walks_before[g].tables.table_pfn[p]) require(w->tables.table_pfn[p] == walks_before[g].tables.table_pfn[p], "existing leaf not replaced");
		}
	}
	require(w->tables.leaf == leaf && w->tables.higher_none == (7U ^ leaf) && w->pmd_none == (7U ^ leaf) && !w->upper_none, "exact boundary walk without inferring from residency");
	for (unsigned int p = 0; p < 3; p++) for (unsigned int q = 0; q < p; q++)
		if (w->tables.table_pfn[p] && w->tables.table_pfn[q])
			require((w->tables.table_pfn[p] == w->tables.table_pfn[q]) == (((addresses[g]+p*PAGE)>>21) == ((addresses[g]+q*PAGE)>>21)), "leaf physical identity follows actual boundary");
}
int main(int argc, char **argv)
{
	require((KD_NEIGHBOR_TEST || KD_BOUNDARY_INTERIOR) ? argc == 4 || argc == 5 : argc == 3 || argc == 4, "native|target prefix|suffix-PAIR [error|cancel|appear|table|free-table|shared|fault|busy]");
	native = !strcmp(argv[1], "native"); resident = 1;
	require(native || !strcmp(argv[1], "target"), "native or target route");
	const char *shape = argv[2], *mode = (KD_NEIGHBOR_TEST || KD_BOUNDARY_INTERIOR) ? (argc == 5 ? argv[4] : "success") : argc == 4 ? argv[3] : "success";
#if KD_NEIGHBOR_TEST
	neighbor_parse(argv[3]);
#endif
	if (KD_BOUNDARY_INTERIOR) {
		require(!strcmp(argv[3], "left") || !strcmp(argv[3], "right"), "interior target below/above boundary");
		interior_right = !strcmp(argv[3], "right");
	}
	unsigned int shape_mask = 0, shape_zero = 0; int found = 0;
	for (unsigned int i = 0; i < sizeof(shapes) / sizeof(shapes[0]); i++)
		if (!strcmp(shape, shapes[i].name)) { found = 1; slice = shapes[i].target; shape_mask = shapes[i].mask | (KD_BOUNDARY_PRIVATE ? 1U << slice : 0); shape_zero = shapes[i].zero & (KD_BOUNDARY_ZERO ? 7U : ~(1U << slice)); }
	require(found && (KD_BOUNDARY_INTERIOR ? slice == 1 : slice == 0 || slice == 2), "declared three-page slice geometry");
	injection = KD_BOUNDARY_INTERIOR ? (!strcmp(mode,"error1") ? 1 : !strcmp(mode,"error2") ? 2 : 0) : !strcmp(mode, "error"); cancellation = !strcmp(mode, "cancel");
	free_first = KD_BOUNDARY_PRIVATE && !strcmp(mode, "free");
	near_zero = KD_BOUNDARY_SHARED && ((KD_BOUNDARY_PRIVATE && !strcmp(mode, "change-near-zero")) ||
		(KD_BOUNDARY_SHARED_MISSING && !strcmp(mode, "appear-near-zero")));
	near_private = KD_BOUNDARY_NEAR_ZERO && !strcmp(mode, "change-near-private");
	near_busy = KD_BOUNDARY_NEAR_PRIVATE && !strcmp(mode, "change-near-busy");
	far_busy = (KD_BOUNDARY_NEAR_PRIVATE || KD_BOUNDARY_INTERIOR_PRIVATE) && !strcmp(mode, "change-far-busy");
	missing_convert = KD_BOUNDARY_SHARED_MISSING && (near_zero || !strcmp(mode, "appear-zero") || !strcmp(mode, "appear-private"));
	missing_busy = KD_BOUNDARY_SHARED_MISSING && !strcmp(mode, "appear-private-busy");
	zero_convert = KD_BOUNDARY_SHARED && !KD_BOUNDARY_INTERIOR && KD_BOUNDARY_ZERO && !strcmp(mode, "change-private");
	zero_busy = KD_BOUNDARY_SHARED && KD_BOUNDARY_ZERO && !strcmp(mode, "change-private-busy");
	empty_convert = KD_BOUNDARY_SHARED && (!KD_BOUNDARY_INTERIOR || ((KD_BOUNDARY_NEAR_ZERO || KD_BOUNDARY_NEAR_PRIVATE) && !strcmp(mode, "change-zero"))) && KD_BOUNDARY_EMPTY && (!strcmp(mode, "change-zero") || !strcmp(mode, "change-private"));
	empty_busy = KD_BOUNDARY_SHARED && KD_BOUNDARY_EMPTY && !strcmp(mode, "change-private-busy");
	changing = near_busy || far_busy || near_private || missing_convert || missing_busy || empty_busy || zero_busy || near_zero || (KD_BOUNDARY_PRIVATE ? !strcmp(mode, "change-busy") : KD_BOUNDARY_ZERO ? !strcmp(mode, "change-private") : KD_BOUNDARY_EMPTY ? !strcmp(mode, "change-zero") || !strcmp(mode, "change-private") : !strcmp(mode, "appear"));
	changing_zero = near_zero || (KD_BOUNDARY_SHARED_MISSING ? !strcmp(mode, "appear-zero") : changing && !KD_BOUNDARY_PRIVATE && !KD_BOUNDARY_ZERO && (!KD_BOUNDARY_EMPTY || !strcmp(mode, "change-zero")));
	table_change = missing_convert ? (near_zero ? 16 : changing_zero ? 17 : 18) : missing_busy ? 19 : empty_convert ? (changing_zero ? 13 : 14) : empty_busy ? 15 : zero_convert ? 11 : zero_busy ? 12 : near_zero ? 1 : changing ? (KD_BOUNDARY_PRIVATE ? 10 : KD_BOUNDARY_ZERO ? 9 : KD_BOUNDARY_EMPTY ? (changing_zero ? 7 : 8) : 6) : 0;
	if (KD_BOUNDARY_INTERIOR) {
		require(!missing_convert && !missing_busy && (!near_zero || KD_BOUNDARY_INTERIOR_PRIVATE), "interior appearance uses explicit safe handback control");
		if (changing) { changing_zero = KD_BOUNDARY_ZERO ? 0 : KD_BOUNDARY_EMPTY ? !strcmp(mode, "change-zero") : 1; table_change = near_private || KD_BOUNDARY_ZERO ? 9 : KD_BOUNDARY_EMPTY ? (changing_zero ? (empty_convert ? 13 : 7) : 8) : 6; }
	}
	if (near_busy || far_busy) { changing_zero = 0; table_change = 10; }
	if (KD_BOUNDARY_INTERIOR_PRIVATE && changing) {
		changing_zero = near_zero; table_change = near_zero ? 21 : 10;
	}
	if (KD_BOUNDARY_NEAR_CREATE) {
		unsigned int near = interior_right ? 2 : 0;
		require(!strcmp(mode,"create") || !strcmp(mode,"create-busy") ||
			!strcmp(mode,"create-far-busy") || !strcmp(mode,"create-cancel") ||
			!strcmp(mode,"create-error1") || !strcmp(mode,"create-error2"), "explicit creation outcome");
		injection = !strcmp(mode,"create-error1") ? 1 : !strcmp(mode,"create-error2") ? 2 : 0;
		cancellation = !strcmp(mode,"create-cancel");
		near_create.outcome = injection ? UB_CREATE_SPLIT_ERROR : cancellation ? UB_CREATE_CANCEL :
			!strcmp(mode,"create-busy") ? UB_CREATE_NEAR_BUSY :
			!strcmp(mode,"create-far-busy") ? UB_CREATE_FAR_BUSY : UB_CREATE_OK;
		near_create.index = (native ? 0 : 3) + near;
		near_create.from_zero = !!(shape_zero & (1U << near));
		changing = 1; changing_zero = 0; table_change = 20;
	}
	fault_interaction = !strcmp(mode, "fault"); busy_page = !strcmp(mode, "busy");
	free_table = !strcmp(mode, "free-table"); present_table = !strcmp(mode, "table"); shared_edge = !strcmp(mode, "shared");
	busy = !native && (free_table || (!KD_BOUNDARY_EXISTING && present_table) || shared_edge || (changing && !near_zero && !zero_convert && !empty_convert && !missing_convert) || busy_page);
	if (KD_BOUNDARY_INTERIOR_PRIVATE && near_zero) busy = !native;
	if (KD_BOUNDARY_NEAR_CREATE) busy = !native && (near_create.outcome == UB_CREATE_NEAR_BUSY || near_create.outcome == UB_CREATE_FAR_BUSY);
	#if KD_NEIGHBOR_TEST
	busy = !native && neighbor_config.loss;
	require(!changing && !free_table && !present_table && !shared_edge && !fault_interaction && !busy_page && !free_first &&
		(!strcmp(mode,"success") || injection || cancellation) && !(neighbor_config.loss && (injection || cancellation)), "focused native neighbor replacement");
#endif
	require(!strcmp(mode, "success") || free_first || injection || cancellation || free_table || present_table || shared_edge || changing || busy_page || fault_interaction, "known edge mode");
	require(!busy_page || (slice == 0 && shape_mask == (KD_BOUNDARY_PRIVATE ? 7U : 6U)), "busy final survivor has an earlier exact hold");
	if (KD_BOUNDARY_NEAR_CREATE) {
		unsigned int near = interior_right ? 2 : 0;
		require(KD_BOUNDARY_INTERIOR && (KD_BOUNDARY_EMPTY || KD_BOUNDARY_ZERO) &&
			!(shape_mask & (1U << near)), "near creation begins untouched or shared zero");
		if (near_create.outcome == UB_CREATE_FAR_BUSY)
			require(shape_mask & (1U << (2 - near)), "late far refusal needs an existing private far page");
	} else if (KD_BOUNDARY_NEAR_PRIVATE) {
		unsigned int near = interior_right ? 2 : 0;
		require(KD_BOUNDARY_INTERIOR && (KD_BOUNDARY_EMPTY || KD_BOUNDARY_ZERO) && (shape_mask & (1U << near)) &&
			!(shape_zero & (1U << near)) && !fault_interaction && !shared_edge && !busy_page,
			"empty/zero target and ordinary resident near survivor; exact existing far subset");
		if (near_busy || far_busy) require(shape_mask == 5 && shape_zero == (KD_BOUNDARY_ZERO ? 2U : 0U), "both resident survivors for exact early/late hold refusal");
		else if (changing) require(shape_mask == (1U << near) && shape_zero == (KD_BOUNDARY_ZERO ? 2U : 0U), "target transition keeps a resident near and untouched far");
	} else if (KD_BOUNDARY_NEAR_ZERO) {
		unsigned int near = interior_right ? 2 : 0;
		require(KD_BOUNDARY_INTERIOR && (KD_BOUNDARY_ZERO || KD_BOUNDARY_EMPTY) && (shape_zero & (1U << near)) &&
			!(shape_mask & (1U << near)) && !fault_interaction && !shared_edge,
			"empty/zero target and verified zero near survivor; no private near admission");
		if (changing && !near_private) require(!shape_mask && shape_zero == ((1U << near) | (KD_BOUNDARY_ZERO ? 2U : 0)),
			"target conversion uses an untouched far survivor");
	} else if (KD_BOUNDARY_INTERIOR_PRIVATE) {
		unsigned int near = interior_right ? 2 : 0, far = 2 - near;
		require(!(shape_mask & (1U << near)) && !(shape_zero & (1U << near)) &&
			!shared_edge && !busy_page, "private interior target keeps an untouched near survivor");
		if (far_busy) require(shape_mask & (1U << far), "queued far refusal needs an existing resident far");
		else if (changing) require(shape_mask == 2 && !shape_zero, "focused target/near eligibility control uses untouched survivors");
	} else
	require(!(shared_edge || changing || fault_interaction) || (!(shape_mask & ~(1U << slice)) && !(shape_zero & ~(1U << slice))), "focused geometry/transition/fault fixtures use UU survivors");
	require(!KD_BOUNDARY_EXISTING || (!present_table && strcmp(mode, "appear")), "existing boundary fixture has its own state controls");
	require(!KD_BOUNDARY_SHARED || !shared_edge, "shared geometry is the primary fixture, not the old refusal mode");
	require(!native || !cancellation, "cancellation is a queue control");
	require(!KD_BOUNDARY_SHARED_MISSING || (!((shape_mask | shape_zero) & (KD_BOUNDARY_INTERIOR ? 1U << (interior_right ? 2 : 0) : 2U)) &&
		(KD_BOUNDARY_INTERIOR || (!present_table && strcmp(mode, "appear")))), "missing target table requires untouched near survivor and explicit appearance control");
	require(!KD_BOUNDARY_INTERIOR || KD_BOUNDARY_NEAR_ZERO || KD_BOUNDARY_NEAR_PRIVATE || KD_BOUNDARY_NEAR_CREATE || !((shape_mask | shape_zero) & (1U << (interior_right ? 2 : 0))), "interior near survivor stays untouched");
	pin(63); groups = native ? 1 : injection || cancellation || free_first ? 2 : 3;
	struct sigaction action = {.sa_sigaction = segv, .sa_flags = SA_SIGINFO};
	sigemptyset(&action.sa_mask); require(!sigaction(SIGSEGV, &action, NULL), "signal handler");
	device = open("/dev/kd_mm_unmap_test", O_RDWR | O_CLOEXEC); require(device >= 0, "probe open");
	struct ub_status initial = status();
	uintptr_t stride = 8UL << 20, boundary = initial.pgdir_size * 8 + (64UL << 20);
	uintptr_t base = boundary - (KD_BOUNDARY_INTERIOR ? (interior_right ? 1 : 2) : slice == 0 ? (KD_BOUNDARY_SHARED ? 2 : 1) : (KD_BOUNDARY_SHARED ? 1 : 2)) * PAGE;
	require(base + groups * stride + (8UL << 20) < initial.task_size, "caller address range");
	struct ub_bases bases = {0};
	for (unsigned int g = 0; g < groups; g++) {
		addresses[g] = base + g * stride;
		int selected = g == (native ? 0U : 1U);
		if (injection && !native && !g) addresses[g] = boundary - 8 * PAGE;
		if (shared_edge && selected) addresses[g] += slice == 0 ? -PAGE : PAGE;
		bases.base[g] = addresses[g];
		neighbors[g][0] = addresses[g] - 2 * PAGE;
		neighbors[g][1] = addresses[g] + 4 * PAGE;
		uintptr_t ranges[] = {addresses[g], neighbors[g][0], neighbors[g][1]};
		for (unsigned int r = 0; r < 3; r++) {
			size_t len = (r ? 1 : 3) * PAGE;
			int device_neighbor = KD_NEIGHBOR_TEST && r;
			void *p = mmap((void *)ranges[r], len, PROT_READ | (device_neighbor ? 0 : PROT_WRITE),
				MAP_PRIVATE | MAP_NORESERVE | MAP_FIXED_NOREPLACE | (device_neighbor ? 0 : MAP_ANONYMOUS),
				device_neighbor ? device : -1, device_neighbor ? (g * 2 + r - 1) * PAGE : 0);
			require(p == (void *)ranges[r] && (device_neighbor || !madvise(p, len, MADV_NOHUGEPAGE)), "mapping setup");
		}
		if (KD_BOUNDARY_ZERO)
			require(!probe_read(addresses[g] + slice * PAGE) && !observed, "read-fault shared-zero target without a private write");
		if (KD_BOUNDARY_PRIVATE)
			memset((void *)(addresses[g] + slice * PAGE), pattern(g, slice), PAGE);
		anchors[g] = (addresses[g] & ~((2UL << 20) - 1)) + (4UL << 20) + 8 * PAGE;
		require(mmap((void *)anchors[g], PAGE, PROT_READ | PROT_WRITE,
			MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0) == (void *)anchors[g] &&
			!madvise((void *)anchors[g], PAGE, MADV_NOHUGEPAGE), "independent upper-level anchor");
		require(!probe_read(anchors[g]) && !observed, "upper levels exist without touching missing slots");
		if (KD_BOUNDARY_EXISTING || ((present_table || free_table) && selected)) {
			unsigned int side = KD_BOUNDARY_INTERIOR ? interior_right : !!slice;
			if (!KD_NEIGHBOR_TEST && (!KD_BOUNDARY_SHARED_MISSING || (KD_BOUNDARY_INTERIOR && present_table))) require(!probe_read(neighbors[g][side]) && !observed, "neighbor read constructs target table without touching target");
			if (free_table && selected) {
				if (KD_BOUNDARY_EXISTING || KD_BOUNDARY_SHARED_MISSING) {
					retention_before = neighbor_state(g, side);
					struct ub_table_walk w = walk_state(g);
					retention_table_before = w.tables.table_pfn[slice];
					require(KD_BOUNDARY_SHARED_MISSING ? retention_before.none && !retention_table_before && (w.pmd_none & (1U << slice)) : retention_before.zero && retention_table_before &&
						((KD_BOUNDARY_PRIVATE ? w.tables.ptes.anon : KD_BOUNDARY_ZERO ? w.tables.ptes.zero : w.tables.ptes.none) & (1U << slice)), "retention prerequisite and target observed before native neighbor movement");
				}
				/* The original VMA still retains this target table while
				 * its outer neighbor is moved to the next table interval. */
				require(!munmap((void *)neighbors[g][side], PAGE), "remove target-side retaining VMA before opt-in");
				neighbors[g][side] += side ? (2UL << 20) : -(2UL << 20);
				require(mmap((void *)neighbors[g][side], PAGE, PROT_READ | PROT_WRITE,
					MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_FIXED_NOREPLACE, -1, 0) == (void *)neighbors[g][side] &&
					!madvise((void *)neighbors[g][side], PAGE, MADV_NOHUGEPAGE), "far neighbor is not a retention guarantee");
				if (KD_BOUNDARY_EXISTING || KD_BOUNDARY_SHARED_MISSING) {
					struct ub_table_walk w = walk_state(g);
					retention_table_after = w.tables.table_pfn[slice];
					require(retention_table_after == retention_table_before && !layout(retention_before.address).start &&
						((KD_BOUNDARY_PRIVATE ? w.tables.ptes.anon : KD_BOUNDARY_ZERO ? w.tables.ptes.zero : w.tables.ptes.none) & (1U << slice)), "prepublication neighbor change retains the still-used target table");
				}
			}
		}
		masks[g] = shape_mask; zeros[g] = shape_zero;
		if (injection && !native && !g) { masks[g] = 7; zeros[g] = 0; }
		pin_mask |= masks[g] << (g * 3);
		for (unsigned int p = 0; p < 3; p++) if (masks[g] & (1U << p)) memset((void *)(addresses[g] + p * PAGE), pattern(g, p), PAGE);
		for (unsigned int p = 0; p < 3; p++) if (zeros[g] & (1U << p))
			require(!probe_read(addresses[g] + p * PAGE) && !observed, "read-fault intended zero slot without writing");
		original[g] = layout(addresses[g]); roots[g] = rmap(addresses[g]);
		if (masks[g] || inherited) require(roots[g].anon && roots[g].anon == roots[g].root && roots[g].links == 1 && roots[g].active == 1 && roots[g].intervals == 1, "one original reverse-map chain");
		else require(!roots[g].anon && !roots[g].links, "no private page means no fabricated reverse map");
	}
	require(!probe_read(KD_TEST_TABLE ? anchors[0] : addresses[0] - 2 * PAGE) && !observed, "read-fault independent zero mapping");
	independent_before = independent();
	struct ub_experiment e = {{boundary - (4UL << 20), anchors[groups - 1] + PAGE, base, stride}, native ? 0 : resident ? 2 : 1, groups, injection};
	require(!ioctl(device, UB_EXPERIMENT, &e), "explicit experiment opt-in");
	require(!ioctl(device, UB_EDGE_BASES, &bases), "explicit fixture bases preserve same-table error head");
	for (unsigned int g = 0; g < groups; g++) for (unsigned int side = 0; side < 2; side++) neighbor_before[g][side] = neighbor_state(g, side);
	if (resident) {
		require((!pin_mask || !ioctl(device, UB_PIN_MASK, (unsigned long)pin_mask)) && !ioctl(device, UB_PAGESTATE, &pages_before), "exact original page references, including zero owned pages");
		for (unsigned int i = 0; i < pages_before.count; i++) if (pin_mask & (1U << i)) require(pages_before.page[i].mapcount == 1 && pages_before.page[i].refs == 2 && !pages_before.page[i].locked, "initial page ownership");
		if (free_first) require(!ioctl(device, UB_UNPIN_MAPPED), "drop test references before real final release");
		if (busy_page) require(!ioctl(device, UB_BUSY_LOCK), "make final page busy before admission");
	}
	for (unsigned int g = 0; g < groups; g++) {
		walks_before[g] = walk_state(g); edge_walk(g, &walks_before[g], 0);
		tables_before[g] = walks_before[g].tables; ptes_before[g] = tables_before[g].ptes;
		check_ptes(g, ptes_before[g], masks[g], zeros[g]);
	}

	smaps = fopen("/proc/self/smaps", "r"); require(smaps != NULL, "open per-VMA resident accounting");
	account(0); /* Allocate/warm the observation buffer before global mm counters. */
	while (late_slot < 3 && ((masks[1] | zeros[1] | (1U << slice)) & (1U << late_slot))) late_slot++;
	if (late_slot == 3) late_slot = 4; /* Existing, untouched neighbor VMA. */
	if (KD_BOUNDARY_SHARED && fault_interaction) late_slot = KD_BOUNDARY_INTERIOR ? (interior_right ? 2 : 0) : KD_BOUNDARY_SHARED_MISSING ? 1 : slice ? 0 : 2;
	if (KD_BOUNDARY_NEAR_CREATE) require(!ioctl(device, UB_NEAR_CREATE_ARM, &near_create), "arm native survivor creation before publication");
	else if (changing) require(!ioctl(device, KD_BOUNDARY_INTERIOR_PRIVATE && near_zero ? UB_CHANGE_INTERIOR_PRIVATE_NEAR_ZERO_ARM : KD_BOUNDARY_INTERIOR_PRIVATE && !far_busy ? UB_CHANGE_INTERIOR_PRIVATE_BUSY_ARM : near_busy || far_busy ? UB_CHANGE_EDGE_PRIVATE_BUSY_ARM : KD_BOUNDARY_INTERIOR ? (near_private ? UB_CHANGE_INTERIOR_NEAR_PRIVATE_ARM : KD_BOUNDARY_ZERO ? UB_CHANGE_INTERIOR_ZERO_PRIVATE_ARM : KD_BOUNDARY_EMPTY ? (changing_zero ? (empty_convert ? UB_CHANGE_INTERIOR_EMPTY_ZERO_ADMIT_ARM : UB_CHANGE_INTERIOR_EMPTY_ZERO_ARM) : UB_CHANGE_INTERIOR_EMPTY_PRIVATE_ARM) : UB_CHANGE_INTERIOR_TABLE_ARM) : missing_convert ? (near_zero ? UB_CHANGE_SHARED_MISSING_NEAR_ARM : changing_zero ? UB_CHANGE_SHARED_MISSING_ZERO_ARM : UB_CHANGE_SHARED_MISSING_PRIVATE_ARM) : missing_busy ? UB_CHANGE_SHARED_MISSING_BUSY_ARM : empty_convert ? (changing_zero ? UB_CHANGE_SHARED_EMPTY_ZERO_ARM : UB_CHANGE_SHARED_EMPTY_PRIVATE_ARM) : empty_busy ? UB_CHANGE_SHARED_EMPTY_BUSY_ARM : zero_convert ? UB_CHANGE_SHARED_ZERO_PRIVATE_ARM : zero_busy ? UB_CHANGE_SHARED_ZERO_BUSY_ARM : near_zero ? UB_CHANGE_EMPTY_ZERO_ARM : KD_BOUNDARY_PRIVATE ? UB_CHANGE_EDGE_PRIVATE_BUSY_ARM : KD_BOUNDARY_ZERO ? UB_CHANGE_EDGE_ZERO_PRIVATE_ARM : KD_BOUNDARY_EMPTY ?
		(changing_zero ? UB_CHANGE_EDGE_EMPTY_ZERO_ARM : UB_CHANGE_EDGE_EMPTY_PRIVATE_ARM) : UB_CHANGE_EDGE_TABLE_ARM,
		(unsigned long)((native ? 0 : 3) + (near_busy ? (interior_right ? 2 : 0) : far_busy ? (interior_right ? 0 : 2) : near_private ? (interior_right ? 2 : 0) : near_zero ? (KD_BOUNDARY_INTERIOR_PRIVATE ? (interior_right ? 2 : 0) : 1) : slice))), "arm locked revalidation control before execution");
	extra_before = extra();
	int fault_test = !native && !injection && !busy && !cancellation && fault_interaction;
	#if KD_NEIGHBOR_TEST
	neighbor_run(base);
	#else
	if (native) {
		before = layout(base); workers[0].tid = syscall(SYS_gettid); workers[0].offset = slice; workers[0].width = 1;
        if (changing) require(!ioctl(device, UB_CHANGE_NOW), "native controlled target-table appearance");
		errno = 0; workers[0].result = munmap((void *)(addresses[0] + slice * PAGE), PAGE); workers[0].error = errno;
		workers[0].fault = KD_TEST_ABSENT && workers[0].result ? -2 : probe_read(addresses[0] + slice * PAGE);
	} else if (cancellation) {
		before = layout(base); require(!ioctl(device, KD_BOUNDARY_INTERIOR ? UB_CANCEL_PARTIAL : UB_CANCEL_EDGE, (unsigned long)slice), "queued fatal cancellation");
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
	#endif
	if (KD_BOUNDARY_NEAR_CREATE) {
		unsigned int g = native ? 0 : 1, near = interior_right ? 2 : 0;
		struct ub_near_create observed_create;
		require(!ioctl(device, UB_CHANGE_RESULT_MORE, &change_more) &&
			!ioctl(device, UB_NEAR_CREATE_RESULT, &observed_create), "queued survivor creation evidence");
		change = change_more.state;
		require(observed_create.index == near_create.index && observed_create.from_zero == near_create.from_zero &&
			observed_create.outcome == near_create.outcome, "exact requested creation control");
		near_create = observed_create;
		require(change_more.mode == 20 && change_more.before_none == !near_create.from_zero &&
			!change_more.after_zero && change.before_zero == near_create.from_zero && change.after_private &&
			change_more.table_before == walks_before[g].tables.table_pfn[near] && change_more.table_before &&
			change_more.table_after == change_more.table_before && change_more.anon_before == roots[g].anon &&
			change_more.anon_after && (!roots[g].anon || change_more.anon_after == roots[g].anon) &&
			change.done && !change.result && change.index == near_create.index &&
			change.pending == (native ? 0U : near_create.outcome == UB_CREATE_OK ? 3U : 2U) &&
			change.readers == (native ? 1U : 2U) && (native || change.admission == -1) &&
			!!change.zero_pfn == near_create.from_zero && change.page.pfn && change.page.pfn != change.zero_pfn &&
			change.page.mapcount == 1 && change.page.refs == 2 && change.page.charged_same &&
			change.page.locked == (near_create.outcome == UB_CREATE_NEAR_BUSY),
			"new near page uses native fault and an exact private reference without table replacement");
		if (near_create.outcome == UB_CREATE_FAR_BUSY) {
			unsigned int far = g * 3 + 2 - near;
			require(near_create.far_index == far && near_create.far_table == walks_before[g].tables.table_pfn[2-near] &&
				near_create.far_page.pfn == pages_before.page[far].pfn && near_create.far_page.mapcount == 1 &&
				near_create.far_page.refs == 2 && near_create.far_page.charged_same && near_create.far_page.locked,
				"far busy control retains its original exact page reference");
		} else require(!near_create.far_table && !near_create.far_page.pfn, "no unrequested far-page lock");
		pin_mask |= 1U << change.index;
	} else if (near_zero && !KD_BOUNDARY_SHARED_MISSING) {
		require(!ioctl(device, UB_CHANGE_RESULT_MORE, &change_more), "queued near-survivor read fault observation");
		change = change_more.state;
		unsigned int g = native ? 0U : 1U, slot = KD_BOUNDARY_INTERIOR_PRIVATE ? (interior_right ? 2 : 0) : 1;
		require(change_more.mode == (KD_BOUNDARY_INTERIOR_PRIVATE ? 21U : 1U) && change_more.before_none && change_more.after_zero &&
			change_more.table_before == walks_before[g].tables.table_pfn[slot] &&
			change_more.table_after == change_more.table_before && change_more.anon_before == roots[g].anon &&
			change_more.anon_after == change_more.anon_before && change.done && !change.result &&
			change.index == g * 3 + slot && change.pending == (native ? 0U : KD_BOUNDARY_INTERIOR_PRIVATE ? 2U : 3U) &&
			change.readers == (native ? 1U : 2U) && (native || change.admission == -1) &&
			!change.before_zero && change.zero_pfn && !change.after_private && !change.page.pfn,
			"real near-survivor zero fault before admission owns no private page or new table");
	} else if (changing && (KD_BOUNDARY_PRIVATE || near_busy || far_busy)) {
		require(!ioctl(device, UB_CHANGE_RESULT_MORE, &change_more), "queued private target eligibility observation");
		change = change_more.state;
		unsigned int slot = near_busy ? (interior_right ? 2 : 0) : far_busy ? (interior_right ? 0 : 2) : slice;
		unsigned int index = (native ? 0U : 3U) + slot;
		require(change_more.mode == 10 && !change_more.before_none && !change_more.after_zero &&
			change_more.table_before == walks_before[native ? 0 : 1].tables.table_pfn[slot] &&
			change_more.table_after == change_more.table_before && change_more.anon_before == roots[native ? 0 : 1].anon &&
			change_more.anon_after == change_more.anon_before && change.done && !change.result &&
			change.index == index && change.pending == (native ? 0U : 2U) && change.readers == (native ? 1U : 2U) &&
			(native || change.admission == -1) && !change.before_zero && !change.zero_pfn && change.after_private &&
			change.page.pfn == pages_before.page[index].pfn && change.page.mapcount == 1 &&
			change.page.refs == 2 && change.page.locked, "same target becomes busy before writer revalidation without new references");
	} else if (changing) {
		require(!ioctl(device, UB_CHANGE_RESULT_MORE, &change_more), "exact target-table appearance result");
		change = change_more.state;
		require(change_more.mode == table_change && change_more.before_none == (KD_BOUNDARY_EMPTY && !near_private) && change.before_zero == (KD_BOUNDARY_ZERO || near_private) &&
			change_more.after_zero == (unsigned int)changing_zero && change.after_private == !changing_zero &&
			change_more.table_after && change_more.anon_before == roots[native ? 0 : 1].anon && change.done && !change.result &&
			change.index == (native ? 0U : 3U) + (near_private ? (interior_right ? 2 : 0) : near_zero ? 1 : slice) && change.pending == (native ? 0U : zero_convert || empty_convert || missing_convert ? 3U : 2U) &&
			change.readers == (native ? 1U : 2U) && (native || change.admission == -1), "controlled target transition before locked revalidation");
		if (KD_BOUNDARY_EXISTING) require(change_more.table_before == change_more.table_after &&
			change_more.table_before == walks_before[native ? 0 : 1].tables.table_pfn[slice], "transition keeps the original target table");
		else require(!change_more.table_before, "missing target table actually appeared");
		if (changing_zero) require(change.zero_pfn && !change.page.pfn && (KD_BOUNDARY_NEAR_PRIVATE ? change_more.anon_after == roots[native ? 0 : 1].anon : !change_more.anon_after), "read fault owns no shared-zero page");
		else {
			require(!!change.zero_pfn == (KD_BOUNDARY_ZERO || near_private) && change_more.anon_after && change.page.pfn &&
				change.page.pfn != change.zero_pfn && change.page.mapcount == 1 &&
				change.page.refs == 2 && change.page.charged_same && change.page.locked == (unsigned)(zero_busy || empty_busy || missing_busy), "controlled private fault retains an exact reference");
			if (change_more.anon_before) require(change_more.anon_after == change_more.anon_before, "controlled fault preserves existing reverse-map root");
			pin_mask |= 1U << change.index;
		}
	}

	after = layout(base); extra_after = extra();
	unsigned long neighbor_growth = 0;
#if KD_NEIGHBOR_TEST
	neighbor_growth = neighbor_body.old_table && !neighbor_body.destination_table ? PAGE : 0;
#endif
	unsigned int removed_pages = injection ? (native ? 0 : 3) : cancellation ? 1 : groups;
	int map_delta = injection ? injection - !native : slice == 1 ? (int)removed_pages : 0;
	require(before.total_vm == after.total_vm + removed_pages && before.data_vm == after.data_vm + removed_pages &&
		before.exec_vm == after.exec_vm && before.stack_vm == after.stack_vm &&
		(long long)after.map_count - (long long)before.map_count == map_delta && before.pgtables + neighbor_growth + ((changing && !KD_BOUNDARY_EXISTING) || (fault_test && !(KD_BOUNDARY_INTERIOR && KD_BOUNDARY_EXISTING)) ? PAGE : 0) == after.pgtables + (free_table && !KD_BOUNDARY_SHARED ? PAGE : 0),
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
		walks_after[g] = walk_state(g); edge_walk(g, &walks_after[g], 1);
		tables_after[g] = walks_after[g].tables; ptes_after[g] = tables_after[g].ptes;
		check_ptes(g, ptes_after[g], current_mask(g) & ~gone,
			(zeros[g] & ~gone & ~current_mask(g)) | (fault_test && g == 1 && late_slot < 3 ? 1U << late_slot : 0) |
			(near_zero && g == (native ? 0U : 1U) ? (KD_BOUNDARY_INTERIOR_PRIVATE ? 1U << (interior_right ? 2 : 0) : 2U) : 0));
	}
	for (unsigned int g = 0; g < groups; g++) for (unsigned int side = 0; side < 2; side++) {
		neighbor_after[g][side] = neighbor_state(g, side);
#if KD_NEIGHBOR_TEST
		if (neighbor_selected(g, side)) {
			struct neighbor a = neighbor_before[g][side], *b = &neighbor_after[g][side];
			a.address = a.start = neighbor_config.new_address; a.end = a.start + PAGE;
			require(!memcmp(&a,b,sizeof(a)) && !mapped(neighbor_config.old_address) &&
				probe_read(neighbor_config.old_address) == SEGV_MAPERR, "native replacement exact; old address inaccessible");
		} else
#endif
		require(!memcmp(&neighbor_before[g][side], &neighbor_after[g][side], sizeof(struct neighbor)), "retaining-neighbor mapping and PTE remain exact");
	}
	account(1); /* No survivor read by this controller precedes this snapshot. */
	verify_mappings();
	if (KD_BOUNDARY_SHARED_MISSING || KD_NEIGHBOR_TEST || KD_BOUNDARY_INTERIOR) for (unsigned int g = 0; g < groups; g++)
		if (removed(g, slice)) {
			require(probe_read(addresses[g] + slice * PAGE) == SEGV_MAPERR,
				"near-survivor fault must not restore the removed target");
			target_rechecks_accessed++;
		}
	for (unsigned int g = 0; g < groups; g++) {
		walks_accessed[g] = walk_state(g); edge_walk(g, &walks_accessed[g], 2);
	}
	if ((KD_BOUNDARY_NEAR_CREATE && (near_create.outcome == UB_CREATE_NEAR_BUSY || near_create.outcome == UB_CREATE_FAR_BUSY)) || near_busy || far_busy || busy_page || zero_busy || empty_busy || missing_busy || (changing && KD_BOUNDARY_PRIVATE && !near_zero)) require(!ioctl(device, UB_BUSY_UNLOCK), "release original busy-page lock");
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
		for (unsigned int p = 0; p < 3; p++) if (!removed(g, p) && !(current_mask(g) & (1U << p))) {
			memset((void *)(addresses[g] + p * PAGE), pattern(g, p), PAGE); written |= 1U << p;
			struct ub_ptes r = ptes(g);
			unsigned int anon = (current_mask(g) | written) & ~gone, zero = 7U & ~(anon | gone);
			require(r.anon == anon && r.zero == zero && r.none == gone && !r.other, "one private write converts exactly one zero PTE");
			for (unsigned int q = 0; q < 3; q++) if (!removed(g, q)) {
				check_page(addresses[g] + q * PAGE, (anon & (1U << q)) ? pattern(g, q) : 0);
				if (anon & (1U << q)) {
					require(r.pfn[q] && (!(current_mask(g) & (1U << q)) || r.pfn[q] == expected_pfn(g, q)), "private physical identity after write");
					for (unsigned int t = 0; t < q; t++) if (anon & (1U << t)) require(r.pfn[q] != r.pfn[t], "private survivors do not alias");
				}
			}
			require(write_count < 9, "bounded write observations");
			writes[write_count].group = g; writes[write_count].slot = p;
			writes[write_count].state = r; writes[write_count++].independent = independent();
		}
		if ((KD_BOUNDARY_NEAR_PRIVATE || (KD_BOUNDARY_NEAR_CREATE && g == (native ? 0U : 1U))) && !removed(g, interior_right ? 2 : 0)) {
			unsigned int near = interior_right ? 2 : 0;
			unsigned char changed = pattern(g, near) ^ 0x5a;
			memset((void *)(addresses[g] + near * PAGE), changed, PAGE);
			for (unsigned int q = 0; q < 3; q++) if (!removed(g, q))
				check_page(addresses[g] + q * PAGE, q == near ? changed : pattern(g, q));
			struct ub_ptes written_near = ptes(g);
			require(written_near.pfn[near] == expected_pfn(g, near) &&
				written_near.anon == (7U & ~gone) && written_near.none == gone,
				"private near remains writable without replacing its page or restoring target");
			struct ub_ptes independent_now = independent();
			require(independent_now.zero == independent_before.zero && independent_now.pfn[0] == independent_before.pfn[0],
				"private near write leaves independent zero mapping intact");
			memset((void *)(addresses[g] + near * PAGE), pattern(g, near), PAGE);
			check_page(addresses[g] + near * PAGE, pattern(g, near));
			near_private_write_checks++;
		}
		ptes_written[g] = ptes(g);
		require(ptes_written[g].anon == (7U & ~gone) && ptes_written[g].none == gone &&
			!ptes_written[g].zero && !ptes_written[g].other, "survivors end as private writable pages");
	}
	for (unsigned int g = 0; g < groups; g++) {
		walks_written[g] = walk_state(g); edge_walk(g, &walks_written[g], 3);
		for (unsigned int p = 0; p < 3; p++) require(walks_written[g].tables.table_pfn[p] == walks_accessed[g].tables.table_pfn[p], "writes retain exact tables");
	}
	if (KD_BOUNDARY_SHARED_MISSING || KD_NEIGHBOR_TEST || KD_BOUNDARY_INTERIOR) for (unsigned int g = 0; g < groups; g++)
		if (removed(g, slice)) {
			require(probe_read(addresses[g] + slice * PAGE) == SEGV_MAPERR,
				"isolated survivor writes must not restore the removed target");
			target_rechecks_written++;
		}
	independent_after = independent();
	account(2);
	require(!fclose(smaps), "close resident accounting observer");
	struct ub_status done = status();
	require(done.idle && !done.pending && !done.errors && (native || done.reader_peak == (KD_NEIGHBOR_TEST ? 0 : 2)) &&
		done.counts.handbacks == done.counts.acks, "no stranded ownership/ACK");
	#if KD_NEIGHBOR_TEST
	neighbor_snapshot(&neighbor_accessed, groups * 2, groups * 2);
	require(!mapped(neighbor_config.old_address) && probe_read(neighbor_config.old_address) == SEGV_MAPERR, "neighbor reads do not restore old mapping");
	#endif
	atomic_store(&leave_threads, 1);
	if (!native && !cancellation) {
		for (unsigned int g = 0; g < groups; g++) require(!pthread_join(workers[g].thread, NULL), "join origins");
		if (!KD_NEIGHBOR_TEST) require(!pthread_join(holder, NULL), "join controller");
		if (fault_test) require(!pthread_join(late_thread, NULL) && !close(late_stack_fd), "join fault observer");
	}
	#if KD_NEIGHBOR_TEST
	require(!pthread_join(neighbor_thread, NULL), "join native writer");
	#endif
	unsigned int cleanup = 0, routed_cleanup = 0;
	for (unsigned int g = 0; g < groups; g++) {
		require(!munmap((void *)addresses[g], 3 * PAGE), "cleanup all target pieces"); cleanup++;
		require(!munmap((void *)(neighbors[g][0]), PAGE), "cleanup left neighbor"); cleanup++;
		require(!munmap((void *)(neighbors[g][1]), PAGE), "cleanup right neighbor"); cleanup++;
		for (unsigned int p = 0; p < 3; p++) require(!mapped(addresses[g] + p * PAGE), "cleanup target absence");
		require(!mapped(neighbors[g][0]) && !mapped(neighbors[g][1]), "cleanup neighbor absence");
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
	/* Every fixture VMA lies within the explicit opt-in interval. */
	require(routed_cleanup == cleanup, "exact cleanup entry routing by enabled interval");
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
	#if KD_NEIGHBOR_TEST
	neighbor_snapshot(&neighbor_clean, 0, 0);
	#endif
	require(!close(device), "release mm reference");
	printf("{\"boundary_edge_test\":1,\"boundary_empty_test\":%d,\"boundary_zero_test\":%d,\"boundary_private_test\":%d,\"boundary_shared_test\":%d,\"mode\":\"%s\",", KD_BOUNDARY_EMPTY, KD_BOUNDARY_ZERO, KD_BOUNDARY_PRIVATE, KD_BOUNDARY_SHARED, mode);
	if (KD_BOUNDARY_NEAR_CREATE) {
		printf("\"boundary_interior_near_create_test\":1,\"near_private_write_checks\":%u,\"near_create\":{\"index\":%llu,\"from_zero\":%llu,\"outcome\":%llu,\"far_index\":%llu,\"far_table\":%llu,\"far_page\":",
			near_private_write_checks, (unsigned long long)near_create.index, (unsigned long long)near_create.from_zero,
			(unsigned long long)near_create.outcome, (unsigned long long)near_create.far_index, (unsigned long long)near_create.far_table);
		struct ub_pages far = {.count = near_create.outcome == UB_CREATE_FAR_BUSY ? 1U : 0U};
		far.page[0] = near_create.far_page; print_pages(&far); printf("},");
	}
	if (KD_BOUNDARY_INTERIOR_PRIVATE) printf("\"boundary_interior_private_test\":1,");
	if (KD_BOUNDARY_NEAR_PRIVATE) printf("\"boundary_interior_near_private_test\":1,\"near_private_write_checks\":%u,", near_private_write_checks);
	if (KD_BOUNDARY_NEAR_ZERO) printf("\"boundary_interior_near_zero_test\":1,");
	if (KD_BOUNDARY_INTERIOR) printf("\"boundary_interior_test\":1,\"interior_right\":%u,", interior_right);
	if (KD_BOUNDARY_SHARED_MISSING) printf("\"boundary_shared_missing_test\":1,");
	if (KD_BOUNDARY_SHARED_MISSING || KD_BOUNDARY_INTERIOR) printf("\"target_rechecks_accessed\":%u,\"target_rechecks_written\":%u,", target_rechecks_accessed, target_rechecks_written);
	if (KD_BOUNDARY_EXISTING || KD_BOUNDARY_SHARED_MISSING) printf("\"retention_change\":{\"before_start\":%lu,\"before_end\":%lu,\"before_zero\":%lu,\"table_before\":%lu,\"table_after\":%lu,\"before_publication\":%d},",
		retention_before.start,retention_before.end,retention_before.zero,retention_table_before,retention_table_after,!!free_table);
	printf("\"zero_target_test\":%d,\"absent_target_test\":%d,\"shape\":\"%s\",\"no_resident\":%d,\"missing_target\":%d,\"missing_table\":%d,\"busy_page\":%d,\"changing\":%d,\"changing_zero\":%d,\"late_slot\":%u,\"masks\":[",
		!KD_TEST_ABSENT && !KD_BOUNDARY_PRIVATE,KD_TEST_ABSENT,shape,no_resident,missing_target,missing_table,busy_page,changing,changing_zero,late_slot);
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
		printf(",\"missing_table_test\":0,\"changing_empty\":%d,\"upper_refusal\":%d,\"fault_interaction\":%d,\"table_bytes_before\":%llu,\"table_bytes_after\":%llu,\"anchors\":[",
			changing_empty,upper_refusal,fault_interaction,(unsigned long long)before.pgtables,(unsigned long long)after.pgtables);
		for (unsigned int g = 0; g < groups; g++) printf("%s%lu",g ? "," : "",(unsigned long)anchors[g]);
		printf("],\"walks_before\":");print_walks(walks_before);
		printf(",\"walks_after\":");print_walks(walks_after);
		printf(",\"walks_accessed\":");print_walks(walks_accessed);
		printf(",\"walks_written\":");print_walks(walks_written);
		printf(",\"walks_cleanup\":");print_walks(walks_cleanup);
	}

	#if KD_NEIGHBOR_TEST
	neighbor_print();
	#endif
	print_neighbors();
	printf(",\"residency\":"); print_account();
	if (KD_TEST_ABSENT || KD_BOUNDARY_ZERO || KD_BOUNDARY_PRIVATE) {
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
