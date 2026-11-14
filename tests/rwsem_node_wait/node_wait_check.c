// SPDX-License-Identifier: GPL-2.0-only
/* Actual writer loop, turn publication and control retirement with controlled
 * wait/admission endpoints. Single-thread ordering checks are not a scheduler
 * or weak-memory implementation and do not establish live queue progress.
 */
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "kd_rw_wait_diag.h"
#include "node_wait_phase.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#define TASK_RUNNING 0
#define TASK_UNINTERRUPTIBLE 2
#define TASK_KILLABLE 4
#define KD_GRANT_PHYSICAL_WRITE 1
#define KD_OBS_NATIVE_WRITE_ACQUIRE 1
#define KD_OBS_NATIVE_TRY_MISS 2
#define KD_OBS_NATIVE_CANCEL 3
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, v) (*(p) = (v))

struct list_head { unsigned int entries; };
static void list_add(struct list_head *link, struct list_head *head)
{ CHECK(!link->entries); link->entries = 1; ++head->entries; }
typedef struct { bool held; } raw_spinlock_t;
struct task_struct { unsigned int state, refs; bool fatal; };
struct test_wait { bool linked; };
typedef struct { struct test_wait *entry; } wait_queue_head_t;
struct kd_rw;
struct kd_rw_native_record;
struct kd_mutex_node {
	int turn;
	bool atomic_spin;
	struct task_struct *requester;
	struct kd_rw *rw;
};
struct kd_mutex_batch { bool initialized; };
struct kd_mutex { unsigned int queued; };
struct kd_rw_native_pool { raw_spinlock_t guard; struct list_head *ordinary_free; };
struct kd_rw_native_record {
	struct kd_rw_native_pool *pool;
	struct task_struct *task;
	struct list_head free_link;
	struct kd_mutex_node node;
	struct kd_mutex_batch batch;
	enum kd_rw_native_phase phase;
	bool caller_user, queue_user, grant_user, turn_owned, ordinary_write, ordinary_queued;
};
struct kd_rw {
	raw_spinlock_t guard;
	wait_queue_head_t changed;
	struct kd_mutex queue;
	struct kd_mutex_batch *writer;
	bool atomic_admission, writer_pending, waking;
	unsigned int readers;
};
static struct task_struct task = { .refs = 1 }, *current = &task;
static struct list_head free_records;
static struct kd_rw_native_pool pool = { .ordinary_free = &free_records };
static struct kd_rw_native_record record = { .pool = &pool, .task = &task,
	.ordinary_write = true, .ordinary_queued = true };
static struct kd_rw lock = { .atomic_admission = true };
static const char *scenario;
static unsigned int prepares, finishes, schedules, probes, starts, departures;
static unsigned int state_stores, checks, wake_retries, relaxes;
static bool injected, clear_wake, start_error;

static bool is(const char *name) { return !strcmp(scenario, name); }
static bool separate_wait(void)
{
#ifdef CONFIG_KDLOCK_RWSEM_NODE_WAIT
	return record.ordinary_write && record.ordinary_queued && pool.ordinary_free && lock.atomic_admission;
#else
	return false;
#endif
}
static void publish_condition(struct kd_mutex_node *node, int *condition);
bool kd_rw_native_select_turn(struct kd_rw_native_record *r);
void kd_rw_native_queue_depart(struct kd_rw_native_record *r);
static void after_unlock(raw_spinlock_t *guard);
static void publish_turn(void)
{
	CHECK(kd_rw_native_select_turn(&record));
	publish_condition(&record.node, &record.node.turn);
}
static void get_task_struct(struct task_struct *t) { CHECK(t->refs); ++t->refs; }
static void put_task_struct(struct task_struct *t) { CHECK(t->refs > 1); --t->refs; }
static int wake_up_process(struct task_struct *t)
{
	bool accepted = t->state != TASK_RUNNING;
	t->state = TASK_RUNNING;
	return accepted;
}
static void __set_current_state(unsigned int state) { current->state = state; }
static void set_current_state(unsigned int state)
{
	CHECK(++state_stores < 32);
	__set_current_state(state);
	if (is("turn_after_state") && !injected) {
		injected = true;
		publish_turn();
	}
}
static void raw_spin_lock(raw_spinlock_t *g)
{
	CHECK(!g->held);
	if (g == &lock.guard)
		CHECK(++checks < 32);
	g->held = true;
}
static void raw_spin_unlock(raw_spinlock_t *g)
{ CHECK(g->held); g->held = false; after_unlock(g); }
#define DEFINE_WAIT(name) struct test_wait name = { 0 }
static void prepare_to_wait(wait_queue_head_t *queue, struct test_wait *wait, unsigned int state)
{
	CHECK(!queue->entry || queue->entry == wait);
	++prepares;
	queue->entry = wait;
	wait->linked = true;
	set_current_state(state);
}
static void finish_wait(wait_queue_head_t *queue, struct test_wait *wait)
{
	__set_current_state(TASK_RUNNING);
	if (wait->linked) {
		CHECK(queue->entry == wait);
		queue->entry = NULL;
		wait->linked = false;
	}
	++finishes;
}
static void wake_up_all(wait_queue_head_t *queue)
{
	if (queue->entry && wake_up_process(current)) {
		queue->entry->linked = false;
		queue->entry = NULL;
	}
}
static void release_reader(void)
{
	CHECK(lock.readers == 1);
	lock.readers = 0;
	wake_up_all(&lock.changed);
}
static void after_unlock(raw_spinlock_t *g)
{
	if (g != &lock.guard)
		return;
	if (is("turn_after_check") && !injected && !record.turn_owned) {
		injected = true;
		publish_turn();
	}
	if (is("reader_before_registration") && !injected && record.batch.initialized && probes) {
		injected = true;
		if (separate_wait())
			CHECK(!lock.changed.entry && !prepares);
		release_reader();
	}
	if (clear_wake) {
		/* Model the last WAKE clear after its broadcast and guarded sample. */
		clear_wake = false;
		lock.waking = false;
	}
}
static void schedule(void)
{
	CHECK(!lock.guard.held && !pool.guard.held);
	CHECK(++schedules < 16);
	if (current->state == TASK_RUNNING)
		return;
	if (!record.turn_owned) {
		if (separate_wait()) {
			CHECK(!lock.changed.entry && !prepares);
			wake_up_all(&lock.changed);
			CHECK(current->state != TASK_RUNNING);
		} else {
			CHECK(lock.changed.entry && prepares);
			wake_up_all(&lock.changed);
		}
		publish_turn();
	} else {
		CHECK(lock.changed.entry && lock.readers && !lock.waking);
		release_reader();
		if (is("cached_wake")) {
			lock.waking = true;
			clear_wake = true;
		}
	}
	CHECK(current->state == TASK_RUNNING);
}
static void cond_resched(void)
{ CHECK(current->state == TASK_RUNNING); ++wake_retries; }
static void cpu_relax(void)
{
	CHECK(is("selection_before_turn") && !record.node.turn && ++relaxes == 1);
	publish_turn();
}
static bool signal_pending_state(unsigned int state, struct task_struct *t)
{ return state == TASK_KILLABLE && t->fatal; }
static bool kd_rw_admission_waking(struct kd_rw *rw)
{ CHECK(rw->guard.held); return rw->waking; }
static bool kd_rw_admission_write_try(struct kd_rw *rw, bool queued)
{
	CHECK(rw->guard.held && pool.guard.held);
	if (queued)
		CHECK(record.turn_owned && record.batch.initialized);
	++probes;
	return !rw->readers && !rw->waking && !rw->writer;
}
static void kd_rw_admission_write_put(struct kd_rw *rw, bool downgrade)
{ CHECK(rw == &lock && !downgrade); }
static void kd_mutex_batch_init(struct kd_mutex_batch *batch) { batch->initialized = false; }
static int kd_mutex_native_node_init(struct kd_mutex_node *node, struct kd_rw_native_record *r)
{ CHECK(r == &record); node->requester = current; node->rw = &lock; return 0; }
static int reserve_record(struct kd_rw *rw, enum kd_rw_native_phase phase,
		bool nonowner, struct kd_rw_native_record **out)
{
	CHECK(rw == &lock && !nonowner);
	pool.ordinary_free = NULL;
	record.ordinary_write = record.ordinary_queued = false;
	record.phase = phase;
	record.caller_user = true;
	get_task_struct(current);
	*out = &record;
	return 0;
}
static int kd_mutex_native_enqueue(struct kd_mutex *queue, struct kd_mutex_node *node, bool try_only)
{
	CHECK(queue == &lock.queue && record.queue_user && !try_only);
	++queue->queued;
	if (is("head") || is("reader_wait") || is("reader_before_registration") ||
	    is("cached_wake") || is("cancel_selected") || is("grant_before_signal") || is("start_error"))
		node->turn = 1;
	else if (is("turn_before_state"))
		publish_turn();
	else if (is("selection_before_turn"))
		CHECK(kd_rw_native_select_turn(&record));
	return 1;
}
static int kd_mutex_native_start(struct kd_mutex_node *node, struct kd_mutex_batch *batch)
{
	CHECK(node->turn && record.turn_owned && current->state == TASK_RUNNING);
	++starts;
	if (start_error)
		return -EIO;
	batch->initialized = true;
	return 0;
}
static int kd_mutex_native_finish(struct kd_mutex_node *node, struct kd_mutex_batch *batch)
{
	CHECK(node->turn && batch->initialized && record.queue_user && !record.grant_user);
	CHECK(current->state == TASK_RUNNING && lock.queue.queued == 1);
	lock.queue.queued = 0;
	batch->initialized = false;
	++departures;
	kd_rw_native_queue_depart(&record);
	return 0;
}
static void native_grant_link(struct kd_rw_native_record *r)
{ CHECK(r->grant_user && r->phase == KD_RW_NATIVE_WRITE_HELD); }
static void observe_native(unsigned long kind, struct kd_rw *rw,
		struct kd_rw_native_record *r, bool writer, unsigned long phase, long result)
{ (void)kind; (void)result; CHECK(rw == &lock && r == &record && writer && phase == KD_GRANT_PHYSICAL_WRITE); }

#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
struct kd_rw_wait_diag_row { struct kd_rw_wait_diag_counts counts; };
static struct kd_rw_wait_diag_row row;
static struct kd_rw_wait_diag_row *kd_rw_wait_diag_current(struct kd_rw *rw)
{ CHECK(rw == &lock); return &row; }
static void kd_rw_wait_diag_add(struct kd_rw_wait_diag_row *r, unsigned int index, unsigned long n)
{ CHECK(r == &row && index < KD_RW_DIAG_COUNT); r->counts.value[index] += n; }
static void kd_rw_wait_diag_prepare(struct kd_rw_wait_diag_row *r, bool writer, bool *registered,
		wait_queue_head_t *queue, struct test_wait *wait, unsigned int state)
{
	CHECK(writer);
	kd_rw_wait_diag_add(r, KD_RW_DIAG_WRITE_PREPARE, 1);
	kd_rw_wait_diag_add(r, !*registered ? KD_RW_DIAG_WRITE_FIRST :
		(wait->linked ? KD_RW_DIAG_WRITE_LINKED : KD_RW_DIAG_WRITE_REINSERT), 1);
	*registered = true;
	prepare_to_wait(queue, wait, state);
}
static void kd_rw_wait_diag_wake(struct kd_rw_wait_diag_row *r, wait_queue_head_t *queue, unsigned int index)
{ kd_rw_wait_diag_add(r, index, 1); wake_up_all(queue); }
#endif

#include "node_wait_functions.h"

int main(int argc, char **argv)
{
	struct kd_rw_native_record *reserved = &record;
	unsigned int wait_state = TASK_UNINTERRUPTIBLE;
	bool try_only = false;
	int result;

	CHECK(argc == 2);
	scenario = argv[1];
	if (is("callable") || is("cancel_queued") || is("cancel_selected") ||
	    is("grant_before_signal") || is("try_miss")) {
		reserved = NULL;
		wait_state = TASK_KILLABLE;
	}
	if (is("cancel_queued") || is("cancel_selected") || is("grant_before_signal"))
		task.fatal = true;
	if (is("reader_wait") || is("reader_before_registration") || is("cached_wake") ||
	    is("cancel_selected") || is("try_miss"))
		lock.readers = 1;
	if (is("non_atomic"))
		lock.atomic_admission = false;
	if (is("unmarked"))
		record.ordinary_write = false;
	if (is("start_error"))
		start_error = true;
	if (is("try_miss"))
		try_only = true;
	result = write_lock_common(&lock, wait_state, try_only, reserved);
	CHECK(!lock.changed.entry && current->state == TASK_RUNNING);
	CHECK(!lock.guard.held && !pool.guard.held);
	if (is("start_error")) {
		CHECK(result == -EIO && record.caller_user && record.queue_user && task.refs == 2);
		CHECK(!record.grant_user && finishes == 1);
	} else if (is("try_miss")) {
		CHECK(!result && record.phase == KD_RW_NATIVE_FREE && task.refs == 1);
		CHECK(!prepares && !finishes && !schedules && !lock.queue.queued);
	} else if (is("cancel_queued") || is("cancel_selected")) {
		CHECK(result == -EINTR && !record.caller_user && !record.grant_user && finishes == 1);
		CHECK(prepares && !lock.writer_pending);
		if (is("cancel_queued")) {
			CHECK(record.queue_user && !record.turn_owned && task.refs == 2 && !departures);
			CHECK(!kd_rw_native_select_turn(&record));
			/* The modeled predecessor ends its final node use before depart. */
			lock.queue.queued = 0;
			kd_rw_native_queue_depart(&record);
		} else {
			CHECK(departures == 1 && !record.queue_user);
		}
		CHECK(task.refs == 1 && record.phase == KD_RW_NATIVE_FREE);
	} else {
		CHECK(!result && record.grant_user && record.queue_user && !record.caller_user);
		CHECK(record.turn_owned && record.phase == KD_RW_NATIVE_WRITE_HELD);
		CHECK(starts == 1 && finishes == 1 && task.refs == 2);
		if (separate_wait() && !is("reader_wait") && !is("reader_before_registration") && !is("cached_wake"))
			CHECK(!prepares);
		else
			CHECK(prepares);
		if (is("reader_before_registration") && separate_wait())
			CHECK(prepares == 1 && !schedules && probes == 2);
		if (is("cached_wake"))
			CHECK(wake_retries && !lock.waking);
		if (is("selection_before_turn"))
			CHECK(relaxes == 1);
		record.grant_user = false;
		lock.writer = NULL;
		CHECK(!kd_mutex_native_finish(&record.node, &record.batch));
		CHECK(task.refs == 1 && record.phase == KD_RW_NATIVE_FREE);
	}
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
	CHECK(row.counts.value[KD_RW_DIAG_WRITE_PREPARE] == prepares);
	CHECK(row.counts.value[KD_RW_DIAG_WRITE_FIRST] == !!prepares);
	CHECK(row.counts.value[KD_RW_DIAG_WRITE_BEGIN] == !try_only);
	CHECK(row.counts.value[KD_RW_DIAG_WRITE_RETURN] + row.counts.value[KD_RW_DIAG_WRITE_CANCEL] +
	      row.counts.value[KD_RW_DIAG_WRITE_ERROR] == !try_only);
#endif
	printf("PASS %s\n", scenario);
	return 0;
}
