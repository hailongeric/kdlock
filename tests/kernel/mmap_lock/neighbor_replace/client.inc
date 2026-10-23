/* SPDX-License-Identifier: GPL-2.0 */
/* Only the native mremap callback holds the gate. The controller never lends
 * write ownership; it publishes real munmap callers and releases scheduling. */
static struct ub_neighbor_config neighbor_config;
static struct ub_neighbor neighbor_body, neighbor_accessed, neighbor_clean;
static pthread_t neighbor_thread;
static _Atomic int neighbor_ready, neighbor_go, neighbor_done;
static uintptr_t neighbor_return;
static int neighbor_errno;

static int neighbor_selected(unsigned int group, unsigned int side)
{
	return group == (native ? 0U : 1U) && side == neighbor_config.side;
}
static void neighbor_parse(const char *mode)
{
	require(!strcmp(mode,"keep-left") || !strcmp(mode,"keep-right") ||
		!strcmp(mode,"lose-left") || !strcmp(mode,"lose-right"), "replacement direction/retention");
	neighbor_config.side = strstr(mode,"right") != NULL;
	neighbor_config.loss = !strncmp(mode,"lose",4);
}
static void *neighbor_move(void *unused)
{
	(void)unused; pin(62);
	if (probe_read((uintptr_t)&warm_byte)) _exit(94);
	atomic_store(&neighbor_ready,1);
	while (!atomic_load(&neighbor_go)) usleep(1000);
	errno = 0;
	neighbor_return = (uintptr_t)mremap((void *)neighbor_config.old_address, PAGE, PAGE,
		MREMAP_MAYMOVE | MREMAP_FIXED, (void *)neighbor_config.new_address);
	neighbor_errno = errno;
	atomic_store(&neighbor_done,1);
	while (!atomic_load(&leave_threads)) usleep(1000);
	return NULL;
}
static void neighbor_snapshot(struct ub_neighbor *r, unsigned int vmas, unsigned int maps)
{
	require(!ioctl(device,UB_NEIGHBOR_RESULT,r), "native writer receipt");
	require(r->armed && r->queued && r->released && r->retired && !r->result &&
		r->reader_blocked && r->writer_blocked && r->vmas == vmas && r->page_maps == maps &&
		r->page_refs == maps + 1 && r->faults == (maps ? maps : vmas ? 0 : groups * 2),
		"native replacement VMA/page lifetime and real writer exclusion");
}
static void neighbor_run(uintptr_t base)
{
	unsigned int victim = native ? 0 : 1;
	neighbor_config.old_address = neighbors[victim][neighbor_config.side];
	neighbor_config.new_address = neighbor_config.side ? neighbor_config.old_address + (neighbor_config.loss ? 2UL<<20 : PAGE) :
		neighbor_config.old_address - (neighbor_config.loss ? 2UL<<20 : PAGE);
	neighbor_config.target_start = addresses[victim]; neighbor_config.target_end = addresses[victim] + 3 * PAGE;
	neighbor_config.count = native ? 0 : busy || injection || cancellation ? 2 : 3;
	neighbor_config.cancel = cancellation; neighbor_config.offset = slice;
	if (!native && !cancellation) for (unsigned int g = 0; g < groups; g++) {
		workers[g].group = g; workers[g].offset = injection && !g ? 0 : slice; workers[g].width = injection && !g ? 3 : 1;
		require(!pthread_create(&workers[g].thread,NULL,ex_origin,&workers[g]), "create origin");
		wait_atomic(&workers[g].ready);
	}
	require(!pthread_create(&neighbor_thread,NULL,neighbor_move,NULL), "create native replacement writer");
	wait_atomic(&neighbor_ready);
	before = layout(base);
	require(!ioctl(device,UB_NEIGHBOR_ARM,&neighbor_config), "arm exact old/new neighbor while idle");
	atomic_store(&neighbor_go,1); wait_state(0,0);
	require(!ioctl(device,UB_NEIGHBOR_PROBE), "real writer excludes local read/write trylocks");
	if (!native && !cancellation) for (unsigned int g = 0; g < neighbor_config.count; g++) {
		atomic_store(&workers[g].go,1);
		if (!g) wait_state(2,1); /* The second request must be genuinely remote. */
	}
	wait_state(1,0);
	require(!ioctl(device,UB_RELEASE), "release native mremap callback scheduling gate");
	wait_atomic(&neighbor_done);
	require(neighbor_return == neighbor_config.new_address && !neighbor_errno, "native mremap completed source retirement");
	if (!native && !cancellation) {
		for (unsigned int g = 0; g < neighbor_config.count; g++) wait_atomic(&workers[g].done);
		if (busy) { atomic_store(&workers[2].go,1); wait_atomic(&workers[2].done); }
	}
	require(!ioctl(device,UB_NEIGHBOR_FINISH), "native writer and pending cancellation drained");
	neighbors[victim][neighbor_config.side] = neighbor_config.new_address;
	if (native) {
		workers[0].tid = syscall(SYS_gettid); workers[0].offset = slice; workers[0].width = 1;
		errno = 0; workers[0].result = munmap((void *)(addresses[0]+slice*PAGE),PAGE); workers[0].error = errno;
		workers[0].fault = KD_TEST_ABSENT && workers[0].result ? -2 : probe_read(addresses[0]+slice*PAGE);
	}
	neighbor_snapshot(&neighbor_body,groups * 2,0);
}
static void neighbor_print_receipt(const struct ub_neighbor *r)
{
	printf("{");
#define FIELD(name) printf("\"" #name "\":%llu,",(unsigned long long)r->name)
	FIELD(armed); FIELD(actor); FIELD(owner); FIELD(old_vma); FIELD(new_vma); FIELD(old_flags); FIELD(new_flags); FIELD(pgoff);
	FIELD(pending); FIELD(readers); FIELD(queued); FIELD(released); FIELD(retired); FIELD(close_owner); FIELD(close_pending);
	FIELD(old_table); FIELD(destination_table); FIELD(tables_before); FIELD(tables_queued); FIELD(tables_closed);
	FIELD(maps_before); FIELD(maps_queued); FIELD(maps_closed); FIELD(pages_before); FIELD(pages_closed);
	FIELD(reader_blocked); FIELD(writer_blocked); FIELD(probe_actor); FIELD(vmas); FIELD(faults); FIELD(page_refs); FIELD(page_maps);
#undef FIELD
	printf("\"admission\":%lld,\"result\":%lld}",(long long)r->admission,(long long)r->result);
}
static void neighbor_print(void)
{
	printf(",\"neighbor_gate_test\":1,\"neighbor_loss\":%llu,\"neighbor_config\":{",(unsigned long long)neighbor_config.loss);
#define FIELD(name) printf("\"" #name "\":%llu,",(unsigned long long)neighbor_config.name)
	FIELD(old_address); FIELD(new_address); FIELD(target_start); FIELD(target_end); FIELD(side); FIELD(loss); FIELD(count); FIELD(cancel);
#undef FIELD
	printf("\"offset\":%llu},\"neighbor_old_inaccessible\":1,\"neighbor_body\":",(unsigned long long)neighbor_config.offset);
	neighbor_print_receipt(&neighbor_body); printf(",\"neighbor_accessed\":"); neighbor_print_receipt(&neighbor_accessed);
	printf(",\"neighbor_clean\":"); neighbor_print_receipt(&neighbor_clean);
	printf(",\"neighbor_rechecks_accessed\":%u,\"neighbor_rechecks_written\":%u",target_rechecks_accessed,target_rechecks_written);
}
