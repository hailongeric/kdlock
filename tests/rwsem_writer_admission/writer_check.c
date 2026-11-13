// SPDX-License-Identifier: GPL-2.0-only
/* Production family admission/release with controlled wait and progress points.
 * Queue turns and adjacent owner records are explicit fixture inputs; this is
 * not a scheduler, MCS handoff or complete source-runtime implementation.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/mman.h>
#include <unistd.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#define BUG_ON(x) CHECK(!(x))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define smp_load_acquire(p) (*(p))
#define TASK_RUNNING 0
#define TASK_UNINTERRUPTIBLE 2
#define TASK_KILLABLE 3
#define KD_GRANT_PHYSICAL_READ 1

struct list_head { struct list_head *next, *prev; };
static void INIT_LIST_HEAD(struct list_head *h) { h->next = h->prev = h; }
static bool list_empty(const struct list_head *h) { return h->next == h; }
static void list_add_tail(struct list_head *e, struct list_head *h)
{ e->prev = h->prev; e->next = h; h->prev->next = e; h->prev = e; }
static void list_del_init(struct list_head *e)
{ e->prev->next = e->next; e->next->prev = e->prev; INIT_LIST_HEAD(e); }

typedef struct { bool held; } raw_spinlock_t;
static void after_unlock(raw_spinlock_t *guard);
static void raw_spin_lock_init(raw_spinlock_t *g) { g->held = false; }
static void raw_spin_lock(raw_spinlock_t *g) { CHECK(!g->held); g->held = true; }
static void raw_spin_unlock(raw_spinlock_t *g)
{ CHECK(g->held); g->held = false; after_unlock(g); }
typedef int atomic_t;
typedef long atomic_long_t;
static void atomic_set(atomic_t *value, int next) { *value = next; }

struct task_struct { unsigned int state; unsigned int refs; bool fatal;
	struct kd_task_root_context *kd_root_context; };
struct kd_task_root_context { struct list_head rwsem_reads; };
struct kd_execution_binding;
struct kd_thread_state { struct task_struct *origin; struct kd_execution_binding *binding; };
struct kd_execution_binding { struct kd_thread_state *state; };
struct test_wait;
typedef struct { struct test_wait *entry; } wait_queue_head_t;
struct kd_mutex_node;
struct kd_mutex_batch;
struct kd_mutex { struct kd_mutex_node *tail; struct kd_mutex_batch *owner; };
#include "writer_types.h"
struct kd_mutex_ops {
	int (*wait_progress)(struct kd_mutex_node *, void *, bool *);
	bool (*wait_ready)(struct kd_mutex_node *, void *);
};
struct kd_mutex_node {
	bool atomic_spin, cancel_requested;
	unsigned int wait_state;
	enum kd_mutex_admission admission;
	atomic_t cancel_users;
	struct task_struct *requester, *cancel_waiter;
	struct kd_thread_state *state;
	const struct kd_mutex_ops *ops;
	void *context;
	struct kd_rw *rw;
	struct kd_mutex_node *next;
	unsigned int turn;
};
struct kd_mutex_batch {
	struct kd_mutex_node *head, *candidate;
	struct kd_mutex *lock;
	struct { struct task_struct *task; } release_owner;
};
static struct task_struct *current;
static bool atomic_context;
static bool in_task(void) { return current != NULL; }
static bool irqs_disabled(void) { return false; }
static bool in_atomic(void) { return atomic_context; }
static void __set_current_state(unsigned int state) { current->state = state; }
static bool kd_state_is_current(struct kd_thread_state *s, struct kd_execution_binding *b)
{ return s && b && s->binding == b; }
static bool fatal_signal_pending(struct task_struct *task) { CHECK(task); return task->fatal; }
static void get_task_struct(struct task_struct *task) { CHECK(task->refs); ++task->refs; }
static void put_task_struct(struct task_struct *task) { CHECK(task->refs > 1); --task->refs; }

struct test_wait { wait_queue_head_t *queue; struct task_struct *task; bool linked; };
#define DEFINE_WAIT(name) struct test_wait name = {0}
static unsigned int prepares, finishes, schedules, relaxes, wakeups, last_wait_state;
static void (*before_wait)(wait_queue_head_t *queue);
static void (*while_scheduled)(void);
static void (*while_relaxing)(void);
static void prepare_to_wait(wait_queue_head_t *queue, struct test_wait *wait, unsigned int state)
{
	CHECK(++prepares <= 16);
	if (before_wait)
		before_wait(queue);
	CHECK(!queue->entry || queue->entry == wait);
	if (wait->linked)
		CHECK(wait->queue == queue && wait->task == current);
	wait->queue = queue; wait->task = current; wait->linked = true;
	queue->entry = wait; last_wait_state = state;
	__set_current_state(state);
}
static void finish_wait(wait_queue_head_t *queue, struct test_wait *wait)
{
	CHECK(wait->linked && queue->entry == wait && wait->task == current);
	queue->entry = NULL; wait->linked = false; ++finishes;
	__set_current_state(TASK_RUNNING);
}
static void wake_up_all(wait_queue_head_t *queue)
{
	++wakeups;
	if (queue->entry)
		queue->entry->task->state = TASK_RUNNING;
}
static void schedule(void)
{
	CHECK(current->state != TASK_RUNNING && ++schedules <= 8 && while_scheduled);
	while_scheduled();
}
static void cpu_relax(void)
{
	CHECK(atomic_context && ++relaxes <= 8 && while_relaxing);
	while_relaxing();
}
static struct kd_observation events[64];
static unsigned int event_count;
#define kd_observe(k, ...) do { \
	CHECK(event_count < 64); \
	events[event_count++] = (struct kd_observation){ .kind = (k), .task = (unsigned long)current, __VA_ARGS__ }; \
} while (0)
/* Retained guard controls and one writer wake interval are checked here.
 * Atomic admission itself has a separate production-function fixture.
 */
static struct kd_rw *wake_window;
static bool wake_pending, wake_sampled;
static unsigned int reschedules;
static bool kd_rw_admission_read_try(struct kd_rw *lock)
{ CHECK(!lock->atomic_admission); return false; }
static void kd_rw_admission_read_put(struct kd_rw *lock) { CHECK(!lock->atomic_admission); }
static bool kd_rw_admission_write_try(struct kd_rw *lock, bool queued)
{
	if (lock == wake_window) { CHECK(queued && lock->guard.held); return !wake_pending; }
	CHECK(!lock->atomic_admission); return false;
}
static void kd_rw_admission_write_put(struct kd_rw *lock, bool downgrade)
{
	if (lock == wake_window) { CHECK(!downgrade && !wake_pending); return; }
	CHECK(!lock->atomic_admission);
}
static bool kd_rw_admission_waking(struct kd_rw *lock)
{
	if (lock == wake_window) {
		CHECK(lock->guard.held);
		wake_sampled = true;
		return wake_pending;
	}
	CHECK(!lock->atomic_admission); return false;
}
static void cond_resched(void) { CHECK(current->state == TASK_RUNNING); ++reschedules; }
#include "writer_functions.h"

struct fixture {
	struct kd_rw lock;
	struct task_struct writer, reader, candidate_task;
	struct kd_thread_state writer_state, reader_state, candidate_state;
	struct kd_execution_binding writer_binding, reader_binding;
	struct kd_mutex_node node, candidate, queued;
	struct kd_mutex_batch batch;
	struct kd_rw_read_credit reader_credit, probe_credit;
	unsigned int progress_calls, blocked_calls;
	bool ready;
	struct kd_rw *outer;
	struct kd_mutex_batch *outer_batch;
};
static struct fixture *draining;
static struct kd_rw *retire_lock;
static size_t retire_size;
static bool retired;

static void after_unlock(raw_spinlock_t *guard)
{
	if (wake_window && guard == &wake_window->guard && wake_sampled)
		wake_pending = false;
	if (retire_lock && guard == &retire_lock->guard) {
		CHECK(!retired && !retire_lock->writer && !retire_lock->readers && wakeups);
		CHECK(!mprotect(retire_lock, retire_size, PROT_NONE));
		retire_lock = NULL; retired = true;
	}
}
static void try_new_reader(struct fixture *f)
{
	struct task_struct *saved = current;
	bool saved_atomic = atomic_context;
	current = &f->reader; atomic_context = false;
	CHECK(!kd_rw_fast_read_trylock(&f->lock, &f->probe_credit));
	CHECK(!f->probe_credit.lock && !f->probe_credit.active);
	current = saved; atomic_context = saved_atomic;
}
static int progress(struct kd_mutex_node *node, void *context, bool *blocked)
{
	struct fixture *f = context;
	CHECK(node == &f->node && node->turn == 1 && node->rw == &f->lock);
	CHECK(!f->lock.guard.held && f->lock.writer_pending && !f->lock.writer);
	CHECK(current->state == TASK_RUNNING && ++f->progress_calls <= 8);
	if (f->outer) {
		CHECK(f->outer->writer == f->outer_batch);
		CHECK(f->outer_batch->head->admission == KD_MUTEX_ADMISSION_GRANTED);
		CHECK(f->outer_batch->head->state == node->state);
	}
	try_new_reader(f);
	*blocked = f->progress_calls <= f->blocked_calls;
	return 0;
}
static bool ready(struct kd_mutex_node *node, void *context)
{
	struct fixture *f = context;
	CHECK(node == &f->node);
	return f->ready;
}
static const struct kd_mutex_ops operations = { .wait_progress = progress, .wait_ready = ready };
static void setup(struct fixture *f)
{
	raw_spin_lock_init(&f->lock.guard);
	INIT_LIST_HEAD(&f->lock.active_reads);
	f->writer.refs = f->reader.refs = f->candidate_task.refs = 1;
	f->writer_state.origin = &f->writer; f->writer_state.binding = &f->writer_binding;
	f->reader_state.origin = &f->reader; f->reader_state.binding = &f->reader_binding;
	f->writer_binding.state = &f->writer_state; f->reader_binding.state = &f->reader_state;
	f->candidate_state.origin = &f->candidate_task;
	f->node.wait_state = TASK_UNINTERRUPTIBLE;
	f->node.admission = KD_MUTEX_ADMISSION_PENDING; f->node.cancel_users = 1;
	f->node.requester = &f->writer; f->node.state = &f->writer_state;
	f->node.ops = &operations; f->node.context = f; f->node.rw = &f->lock; f->node.turn = 1;
	f->candidate.wait_state = TASK_KILLABLE;
	f->candidate.admission = KD_MUTEX_ADMISSION_PENDING;
	f->candidate.state = &f->candidate_state; f->candidate.requester = &f->candidate_task;
	f->candidate.rw = &f->lock;
	f->queued.admission = KD_MUTEX_ADMISSION_PENDING; f->queued.rw = &f->lock;
	f->lock.queue.tail = &f->node;
	f->batch.head = &f->node; f->batch.lock = &f->lock.queue;
	f->batch.release_owner.task = &f->writer;
	kd_rw_fast_read_init(&f->reader_credit, &f->reader_state);
	kd_rw_fast_read_init(&f->probe_credit, &f->reader_state);
	current = &f->writer;
}
static void hold_reader(struct fixture *f)
{
	/* The reader predates the writer's supplied MCS turn. */
	f->lock.queue.tail = NULL;
	current = &f->reader;
	CHECK(kd_rw_fast_read_trylock(&f->lock, &f->reader_credit));
	f->lock.queue.tail = &f->node;
	current = &f->writer;
}
static void drop_reader(void)
{
	struct task_struct *saved = current;
	bool saved_atomic = atomic_context;
	struct fixture *f = draining;
	CHECK(f && f->lock.writer_pending && !f->lock.writer && f->lock.readers == 1);
	CHECK(f->node.admission == KD_MUTEX_ADMISSION_PENDING);
	current = &f->reader; atomic_context = false;
	CHECK(!kd_rw_read_release(&f->reader_credit, &f->reader_state, &f->reader_binding,
		&f->reader_credit, &f->reader_credit));
	current = saved; atomic_context = saved_atomic;
	draining = NULL;
}
static void drain_before_wait(wait_queue_head_t *queue)
{
	CHECK(draining && queue == &draining->lock.changed && !queue->entry);
	before_wait = NULL;
	drop_reader();
	CHECK(!queue->entry);
}
static void check_granted(struct fixture *f)
{
	CHECK(f->lock.writer == &f->batch && !f->lock.writer_pending && !f->lock.readers);
	CHECK(f->node.admission == KD_MUTEX_ADMISSION_GRANTED && !f->node.cancel_users);
	CHECK(!f->lock.changed.entry && !f->lock.guard.held);
	CHECK(current->state == TASK_RUNNING && f->writer.refs == 1 && !f->node.cancel_waiter);
}
static void check_immediate(void)
{
	struct fixture f = {0}; setup(&f);
	CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
	check_granted(&f);
	CHECK(f.progress_calls == 1 && !prepares && !finishes && !schedules);
	CHECK(f.lock.queue.tail == &f.node && !f.lock.queue.owner);
	kd_rw_writer_exit(&f.lock, &f.batch, NULL);
	CHECK(!f.lock.writer && wakeups == 1);
}
static void check_drain_before_wait(void)
{
	struct fixture f = {0}; setup(&f); hold_reader(&f);
	draining = &f; before_wait = drain_before_wait;
	CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
	check_granted(&f);
	CHECK(f.progress_calls == 1 && prepares == 1 && finishes == 1 && !schedules);
	CHECK(f.reader_credit.released && !f.reader_credit.active && !draining);
	kd_rw_writer_exit(&f.lock, &f.batch, NULL);
}
static void check_drain_after_wait(void)
{
	struct fixture f = {0}; setup(&f); hold_reader(&f);
	draining = &f; while_scheduled = drop_reader;
	CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
	check_granted(&f);
	CHECK(f.progress_calls == 2 && prepares == 2 && finishes == 1 && schedules == 1);
	CHECK(f.reader_credit.released && !draining);
	kd_rw_writer_exit(&f.lock, &f.batch, NULL);
}
static void check_queued(void)
{
	struct fixture f = {0}; setup(&f);
	f.node.next = &f.queued; f.lock.queue.tail = &f.queued;
	CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
	check_granted(&f); try_new_reader(&f);
	CHECK(!prepares && !finishes && f.lock.queue.tail == &f.queued);
	CHECK(f.node.next == &f.queued && f.queued.admission == KD_MUTEX_ADMISSION_PENDING && !f.queued.turn);
	kd_rw_writer_exit(&f.lock, &f.batch, NULL);
	/* Family release leaves the queued successor and its reader gate intact.
	 * The unchanged MCS implementation, exercised live, owns turn publication.
	 */
	try_new_reader(&f);
	CHECK(f.lock.queue.tail == &f.queued && f.queued.admission == KD_MUTEX_ADMISSION_PENDING);
}
static void check_blocked(void)
{
	struct fixture f = {0}; setup(&f);
	f.blocked_calls = 1; f.ready = true;
	CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
	check_granted(&f);
	CHECK(f.progress_calls == 2 && prepares == 2 && finishes == 1 && !schedules);
	kd_rw_writer_exit(&f.lock, &f.batch, NULL);
}
static void check_wake_clear(void)
{
	struct fixture f = {0}; setup(&f);
	f.node.ops = NULL; f.lock.atomic_admission = true;
	wake_window = &f.lock; wake_pending = true;
	/* The wake predates registration, but WAKE survives until the guarded
	 * probe. after_unlock clears it before the writer chooses whether to sleep.
	 */
	CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
	check_granted(&f);
	CHECK(wake_sampled && !wake_pending && reschedules == 1 && !schedules &&
	      prepares == 2 && finishes == 1);
	kd_rw_writer_exit(&f.lock, &f.batch, NULL);
}
static void check_cancel(void)
{
	struct fixture available = {0}, held = {0}, cancelled = {0};
	setup(&available);
	available.node.wait_state = TASK_KILLABLE; available.writer.fatal = true;
	CHECK(!kd_rw_writer_enter(&available.lock, &available.batch, &available.node));
	check_granted(&available);
	CHECK(prepares == 1 && finishes == 1 && last_wait_state == TASK_KILLABLE);
	kd_rw_writer_exit(&available.lock, &available.batch, NULL);
	setup(&held); hold_reader(&held);
	held.node.wait_state = TASK_KILLABLE; held.writer.fatal = true;
	CHECK(kd_rw_writer_enter(&held.lock, &held.batch, &held.node) == -EINTR);
	CHECK(held.node.admission == KD_MUTEX_ADMISSION_CANCELLED && held.node.cancel_requested);
	CHECK(held.node.cancel_users == 1 && !held.node.cancel_waiter && held.writer.refs == 1);
	CHECK(!held.lock.writer && !held.lock.writer_pending && held.lock.readers == 1);
	CHECK(prepares == 2 && finishes == 2 && !held.lock.changed.entry && !schedules);
	current = &held.reader;
	CHECK(!kd_rw_read_release(&held.reader_credit, &held.reader_state, &held.reader_binding,
		&held.reader_credit, &held.reader_credit));
	setup(&cancelled); cancelled.node.admission = KD_MUTEX_ADMISSION_CANCELLED;
	CHECK(kd_rw_writer_enter(&cancelled.lock, &cancelled.batch, &cancelled.node) == -EINTR);
	CHECK(!cancelled.lock.writer && !cancelled.lock.writer_pending);
	CHECK(cancelled.node.cancel_users == 1 && prepares == 3 && finishes == 3 && !schedules);
}
static void check_cohort(void)
{
	for (unsigned int signalled = 0; signalled < 2; ++signalled) {
		struct fixture f = {0}; setup(&f);
		f.batch.candidate = &f.candidate; f.candidate_task.fatal = signalled;
		current = &f.candidate_task; f.batch.release_owner.task = current;
		CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
		check_granted(&f);
		CHECK(prepares == signalled + 1 && finishes == signalled + 1 && !schedules);
		CHECK(last_wait_state == TASK_KILLABLE && f.candidate_task.refs == 1);
		CHECK(f.candidate.admission == (signalled ? KD_MUTEX_ADMISSION_CANCELLED : KD_MUTEX_ADMISSION_PENDING));
		CHECK(kd_rw_write_grant(&f.lock, &f.batch, &f.candidate) == (signalled ? -EINTR : 0));
		kd_rw_writer_exit(&f.lock, &f.batch, NULL);
	}
}
static void check_nested(void)
{
	struct fixture outer = {0}, inner = {0}; setup(&outer);
	CHECK(!kd_rw_writer_enter(&outer.lock, &outer.batch, &outer.node));
	check_granted(&outer);
	setup(&inner);
	inner.node.state = outer.node.state; inner.node.requester = &outer.writer;
	inner.outer = &outer.lock; inner.outer_batch = &outer.batch;
	current = &outer.writer; inner.batch.release_owner.task = current;
	CHECK(!kd_rw_writer_enter(&inner.lock, &inner.batch, &inner.node));
	check_granted(&inner);
	CHECK(inner.progress_calls == 1 && outer.progress_calls == 1 && !prepares && !finishes);
	kd_rw_writer_exit(&inner.lock, &inner.batch, NULL);
	CHECK(outer.lock.writer == &outer.batch && outer.node.state == inner.node.state);
	kd_rw_writer_exit(&outer.lock, &outer.batch, NULL);
}
static void check_downgrade(void)
{
	struct fixture f = {0}; struct kd_rw_read_credit conversion = {0}; setup(&f);
	CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
	check_granted(&f);
	kd_rw_read_credit_init(&conversion);
	conversion.lock = &f.lock; conversion.state = &f.writer_state;
	conversion.acquisition = &f.node; conversion.user = &f.batch;
	conversion.active_read.logical_owner = &f.writer;
	kd_rw_writer_exit(&f.lock, &f.batch, &conversion);
	CHECK(!f.lock.writer && f.lock.readers == 1 && conversion.active && !conversion.released);
	CHECK(f.lock.active_reads.next == &conversion.active_read.link);
	CHECK(events[event_count - 1].kind == KD_OBS_WRITE_DOWNGRADE_REAL);
	CHECK(events[event_count - 1].acquisition == (unsigned long)&f.node);
	/* Supply the completed old queue turn, then admit a concurrent reader. */
	f.lock.queue.tail = NULL; current = &f.reader;
	CHECK(kd_rw_fast_read_trylock(&f.lock, &f.reader_credit) && f.lock.readers == 2);
	CHECK(!kd_rw_read_release(&f.reader_credit, &f.reader_state, &f.reader_binding,
		&f.reader_credit, &f.reader_credit));
	CHECK(f.lock.readers == 1 && conversion.active);
	current = &f.writer;
	CHECK(!kd_rw_read_release(&conversion, &f.writer_state, &f.writer_binding, &f.node, &f.batch));
	CHECK(!f.lock.readers && list_empty(&f.lock.active_reads) && conversion.released);
	CHECK(kd_rw_read_release(&conversion, &f.writer_state, &f.writer_binding, &f.node, &f.batch) == -ESTALE);
	CHECK(!prepares && !finishes && !schedules);
}
static void check_atomic(void)
{
	struct fixture f = {0}; setup(&f); hold_reader(&f);
	f.node.atomic_spin = true; atomic_context = true;
	draining = &f; while_relaxing = drop_reader;
	CHECK(!kd_rw_writer_enter(&f.lock, &f.batch, &f.node));
	check_granted(&f);
	CHECK(f.progress_calls == 2 && !prepares && !finishes && !schedules && relaxes == 1);
	kd_rw_writer_exit(&f.lock, &f.batch, NULL);
}
static void check_final(void)
{
	struct fixture f = {0}; setup(&f);
	long page = sysconf(_SC_PAGESIZE);
	CHECK(page > 0 && sizeof(struct kd_rw) <= (size_t)page);
	struct kd_rw *lock = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(lock != MAP_FAILED);
	raw_spin_lock_init(&lock->guard); INIT_LIST_HEAD(&lock->active_reads);
	f.node.rw = lock; f.node.ops = NULL; f.batch.lock = &lock->queue;
	lock->queue.tail = &f.node;
	CHECK(!kd_rw_writer_enter(lock, &f.batch, &f.node));
	CHECK(lock->writer == &f.batch && !prepares && !finishes);
	retire_lock = lock; retire_size = page;
	kd_rw_writer_exit(lock, &f.batch, NULL);
	CHECK(retired && !retire_lock && !munmap(lock, page));
}
int main(int argc, char **argv)
{
	CHECK(argc == 2);
	if (!strcmp(argv[1], "immediate")) check_immediate();
	else if (!strcmp(argv[1], "drain_before_wait")) check_drain_before_wait();
	else if (!strcmp(argv[1], "drain_after_wait")) check_drain_after_wait();
	else if (!strcmp(argv[1], "queued")) check_queued();
	else if (!strcmp(argv[1], "blocked")) check_blocked();
	else if (!strcmp(argv[1], "wake_clear")) check_wake_clear();
	else if (!strcmp(argv[1], "cancel")) check_cancel();
	else if (!strcmp(argv[1], "cohort")) check_cohort();
	else if (!strcmp(argv[1], "nested")) check_nested();
	else if (!strcmp(argv[1], "downgrade")) check_downgrade();
	else if (!strcmp(argv[1], "atomic")) check_atomic();
	else if (!strcmp(argv[1], "final")) check_final();
	else CHECK(false);
	printf("PASS %s\n", argv[1]);
	return 0;
}
