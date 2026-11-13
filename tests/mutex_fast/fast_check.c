// SPDX-License-Identifier: GPL-2.0-only
/* Controlled publication/reuse around unchanged production function excerpts. */
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <sys/mman.h>
#include <unistd.h>

#define CHECK(value) do { if (!(value)) { \
	fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #value); exit(1); \
} } while (0)
#define BUG_ON(value) CHECK(!(value))
#define TASK_RUNNING 0
#define TASK_UNINTERRUPTIBLE 2
#define TASK_KILLABLE 3
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define WRITE_ONCE(value, next) __atomic_store_n(&(value), (next), __ATOMIC_RELAXED)
#define smp_load_acquire(ptr) __atomic_load_n((ptr), __ATOMIC_ACQUIRE)
static void after_store(const void *pointer);
static void after_cmpxchg(const void *pointer, bool removed);
#define smp_store_release(ptr, value) do { \
	__atomic_store_n((ptr), (value), __ATOMIC_RELEASE); after_store(ptr); \
} while (0)
#define cmpxchg(ptr, old, value) ({ \
	__typeof__(*(ptr)) expected = (old); \
	__typeof__(*(ptr)) replacement = (value); \
	bool changed = __atomic_compare_exchange_n((ptr), &expected, replacement, false, \
		__ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); \
	after_cmpxchg((ptr), changed && !replacement); expected; \
})
#define cmpxchg_release cmpxchg
typedef int atomic_t;
static int atomic_cmpxchg(atomic_t *ptr, int old, int value)
{
	__atomic_compare_exchange_n(ptr, &old, value, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
	return old;
}

struct list_head { struct list_head *next, *prev; };
static void INIT_LIST_HEAD(struct list_head *head) { head->next = head->prev = head; }
static bool list_empty(const struct list_head *head) { return head->next == head; }
struct task_struct;
struct kd_thread_state;
struct kd_mutex_batch;
struct kd_mutex_node {
	void *native_local, *rw;
	struct kd_mutex_node *next;
	atomic_t selection;
	int turn;
	bool atomic_spin;
	unsigned int wait_state;
	struct task_struct *requester;
	struct kd_thread_state *state;
};
#include "fast_types.h"
struct kd_task_root_context;
struct task_struct {
	unsigned long __state;
	int refs, wakes;
	struct kd_task_root_context *kd_root_context;
};
struct kd_execution_binding {
	struct kd_thread_state *state;
	struct task_struct *task;
	const void *control;
	enum kd_execution_kind kind;
};
struct kd_request_pool { struct kd_thread_state *state; };
struct kd_episode_resources {
	struct kd_request_pool *pool;
	struct { enum kd_lock_family family; } config;
};
struct test_fast_read { void *lock; };
struct kd_thread_state {
	struct task_struct *origin;
	struct kd_execution_binding *binding;
	struct kd_request_pool *requests;
	void *exit_image, *exit_use, *exit_holder;
	struct list_head grants;
	struct { enum kd_operation_phase phase; } operation;
};
struct kd_task_root_context {
	struct kd_thread_state core;
	struct kd_execution_binding initial_native;
	struct task_struct *task;
	struct { struct list_head batches; struct task_struct *task; bool atomic_spin; } owners;
	struct list_head native_grants;
	struct kd_mutex_fast mutex_fast;
	struct test_fast_read rwsem_fast;
	void *aux_entry, *lifecycle, *storage;
	struct kd_episode_resources *mutex_resources;
	struct kd_request_pool pool;
	unsigned long mutex_control_bytes;
	unsigned int native_spin_depth;
	bool attached, source_closing;
};
static _Thread_local struct task_struct *current;
static bool task_context = true, irq_off, atomic_context;
static bool in_task(void) { return task_context; }
static bool irqs_disabled(void) { return irq_off; }
static bool in_atomic(void) { return atomic_context; }
static void get_task_struct(struct task_struct *task) { CHECK(task->refs > 0); ++task->refs; }
static void put_task_struct(struct task_struct *task) { CHECK(task->refs > 0); --task->refs; }
static void wake_up_process(struct task_struct *task) { CHECK(task->refs >= 2); ++task->wakes; }
static void cpu_relax(void) { __asm__ volatile("pause" ::: "memory"); }
static int exchanged, allow_link, producer_done, poll_count;
static void cond_resched(void)
{
	++poll_count;
	__atomic_store_n(&allow_link, 1, __ATOMIC_RELEASE);
	sched_yield();
}
static struct kd_observation events[64];
static unsigned int event_count;
#define kd_observe(event_kind, ...) do { \
	CHECK(event_count < 64); \
	events[event_count++] = (struct kd_observation) { \
		.kind = (event_kind), .task = (unsigned long)current, __VA_ARGS__ }; \
} while (0)
static struct kd_execution_binding *kd_state_current_binding(struct kd_thread_state *state)
{
	return state->binding;
}
static bool kd_state_is_current(struct kd_thread_state *state, struct kd_execution_binding *binding)
{
	return state->binding == binding;
}
static bool kd_request_pool_empty(void *pool) { CHECK(pool); return true; }
static void kd_request_pool_collect(void *pool) { CHECK(pool); }
static int kd_request_pool_detach(void *pool, struct kd_execution_binding *binding)
{
	CHECK(pool && binding->state->binding == binding);
	binding->state->binding = NULL;
	return 0;
}
static int kd_request_pool_revoke_cancelled(void *pool, struct kd_execution_binding *binding,
					   struct list_head *actors)
{
	CHECK(actors);
	return kd_request_pool_detach(pool, binding);
}
#include "fast_functions.h"

static struct task_struct owner = { .refs = 1 }, waiter = { .refs = 1 };
static struct kd_task_root_context root;
static struct kd_mutex *lock;
static struct kd_mutex_node *successor;
static size_t page_size;
static const void *retire_turn, *retire_tail;
static bool object_inaccessible, successor_inaccessible;

static void protect_object(void)
{
	CHECK(!object_inaccessible && mprotect(lock, page_size, PROT_NONE) == 0);
	object_inaccessible = true;
}
static void after_store(const void *pointer)
{
	if (pointer != retire_turn || !retire_turn)
		return;
	CHECK(waiter.refs == 2 && smp_load_acquire(&successor->turn) == 1);
	CHECK(mprotect(successor, page_size, PROT_NONE) == 0);
	successor_inaccessible = true;
	protect_object();
}
static void after_cmpxchg(const void *pointer, bool removed)
{
	if (pointer == retire_tail && removed)
		protect_object();
}
static void setup_root(struct kd_task_root_context *context, struct task_struct *task)
{
	memset(context, 0, sizeof(*context));
	context->task = task;
	context->attached = true;
	context->core.origin = task;
	context->core.requests = &context->pool;
	context->pool.state = &context->core;
	context->owners.task = task;
	context->core.binding = &context->initial_native;
	context->initial_native = (struct kd_execution_binding) {
		.state = &context->core, .task = task, .control = context, .kind = KD_EXECUTION_NATIVE,
	};
	INIT_LIST_HEAD(&context->core.grants);
	INIT_LIST_HEAD(&context->owners.batches);
	INIT_LIST_HEAD(&context->native_grants);
	kd_mutex_fast_init(&context->mutex_fast, task, &context->core);
	task->kd_root_context = context;
}
static void setup(void)
{
	page_size = sysconf(_SC_PAGESIZE);
	lock = mmap(NULL, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	successor = mmap(NULL, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(lock != MAP_FAILED && successor != MAP_FAILED);
	CHECK(sizeof(*lock) <= page_size && sizeof(*successor) <= page_size);
	current = &owner;
	setup_root(&root, &owner);
	successor->requester = &waiter;
	successor->selection = KD_MUTEX_OFFERED;
	successor->wait_state = TASK_UNINTERRUPTIBLE;
}
static void check_pair(unsigned int start)
{
	struct kd_observation *acquire = &events[start], *release = &events[start + 1];
	CHECK(event_count == start + 2);
	CHECK(acquire->kind == KD_OBS_FAST_ACQUIRE && release->kind == KD_OBS_FAST_RELEASE);
	CHECK(acquire->task == (unsigned long)&owner && release->task == acquire->task);
	CHECK(acquire->state == (unsigned long)&root.core && release->state == acquire->state);
	CHECK(acquire->node == (unsigned long)&root.mutex_fast.head && release->node == acquire->node);
	CHECK(acquire->object == (unsigned long)lock && release->object == acquire->object);
	CHECK(acquire->acquisition == (unsigned long)&root.mutex_fast && release->acquisition == acquire->acquisition);
	CHECK(acquire->flags == KD_OBS_FLAG_ENQUEUED);
	CHECK(release->flags == (KD_OBS_FLAG_QUEUE_DONE | KD_OBS_FLAG_NODE_RETIRABLE));
	CHECK(!root.mutex_fast.lock && !release->source_user && !release->return_user && !release->notifier);
}
static void check_reuse(void)
{
	CHECK(kd_mutex_fast_trylock(lock, &root.mutex_fast));
	CHECK(lock->tail == &root.mutex_fast.head && !lock->owner);
	kd_mutex_fast_unlock(&root.mutex_fast);
	CHECK(!lock->tail);
	check_pair(0);
	CHECK(kd_mutex_fast_trylock(lock, &root.mutex_fast));
	retire_tail = &lock->tail;
	kd_mutex_fast_unlock(&root.mutex_fast);
	CHECK(object_inaccessible);
	check_pair(2);
}
static void check_failed(void)
{
	lock->tail = successor;
	CHECK(!kd_mutex_fast_trylock(lock, &root.mutex_fast));
	CHECK(lock->tail == successor && !successor->next && !root.mutex_fast.lock && !event_count);
	CHECK(successor->selection == KD_MUTEX_OFFERED && !successor->turn && waiter.refs == 1);
}
static void check_linked(void)
{
	CHECK(kd_mutex_fast_trylock(lock, &root.mutex_fast));
	struct kd_mutex_node *previous = __atomic_exchange_n(&lock->tail, successor, __ATOMIC_SEQ_CST);
	CHECK(previous == &root.mutex_fast.head);
	smp_store_release(&previous->next, successor);
	retire_turn = &successor->turn;
	kd_mutex_fast_unlock(&root.mutex_fast);
	CHECK(object_inaccessible && successor_inaccessible && waiter.wakes == 1 && waiter.refs == 1);
	check_pair(0);
	CHECK(events[1].related == (unsigned long)successor);
}
static void *publish_delayed(void *unused)
{
	(void)unused;
	struct kd_mutex_node *previous = __atomic_exchange_n(&lock->tail, successor, __ATOMIC_SEQ_CST);
	CHECK(previous == &root.mutex_fast.head);
	__atomic_store_n(&exchanged, 1, __ATOMIC_RELEASE);
	while (!__atomic_load_n(&allow_link, __ATOMIC_ACQUIRE))
		sched_yield();
	smp_store_release(&previous->next, successor);
	/* No predecessor access after this actual final link store. */
	__atomic_store_n(&producer_done, 1, __ATOMIC_RELEASE);
	return NULL;
}
static void check_delayed(void)
{
	pthread_t producer;
	CHECK(kd_mutex_fast_trylock(lock, &root.mutex_fast));
	successor->selection = KD_MUTEX_SELECTED_LOCAL;
	CHECK(!pthread_create(&producer, NULL, publish_delayed, NULL));
	while (!__atomic_load_n(&exchanged, __ATOMIC_ACQUIRE))
		sched_yield();
	CHECK(!smp_load_acquire(&root.mutex_fast.head.next));
	kd_mutex_fast_unlock(&root.mutex_fast);
	CHECK(!pthread_join(producer, NULL));
	CHECK(producer_done && poll_count && successor->turn == 1 && waiter.wakes == 1 && waiter.refs == 1);
	CHECK(lock->tail == successor);
	check_pair(0);
}
static void check_eligibility(void)
{
	CHECK(native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
	for (int kind = KD_OPERATION_NONE; kind <= KD_OPERATION_RWSEM_IS_WRITE_LOCKED; ++kind)
		if (kind != KD_OPERATION_MUTEX_LOCK && kind != KD_OPERATION_RWSEM_DOWN_READ)
			CHECK(!native_fast_eligible(&root, kind));
	CHECK(native_fast_eligible(&root, KD_OPERATION_RWSEM_DOWN_READ));
	root.rwsem_fast.lock = lock;
	CHECK(!native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
	CHECK(!native_fast_eligible(&root, KD_OPERATION_RWSEM_DOWN_READ));
	root.rwsem_fast.lock = NULL;
	root.core.operation.phase = KD_OPERATION_RESUMABLE;
	CHECK(native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
	for (int phase = KD_OPERATION_TARGET_READY; phase <= KD_OPERATION_DONE; ++phase) {
		root.core.operation.phase = phase;
		CHECK(!native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
	}
	root.core.operation.phase = KD_OPERATION_IDLE;
	bool *contexts[] = { &irq_off, &atomic_context };
	for (unsigned int index = 0; index < sizeof(contexts) / sizeof(contexts[0]); ++index) {
		*contexts[index] = true;
		CHECK(!native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
		*contexts[index] = false;
	}
	task_context = false;
	CHECK(!native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
	task_context = true;
	owner.__state = TASK_UNINTERRUPTIBLE;
	CHECK(!native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
	owner.__state = TASK_RUNNING;
	struct list_head marker, *lists[] = { &root.core.grants, &root.owners.batches, &root.native_grants };
	for (unsigned int index = 0; index < sizeof(lists) / sizeof(lists[0]); ++index) {
		lists[index]->next = &marker;
		CHECK(!native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
		INIT_LIST_HEAD(lists[index]);
	}
	void **actors[] = { &root.core.exit_image, &root.core.exit_use, &root.core.exit_holder };
	for (unsigned int index = 0; index < sizeof(actors) / sizeof(actors[0]); ++index) {
		*actors[index] = &marker;
		CHECK(!native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
		*actors[index] = NULL;
	}
	CHECK(kd_mutex_fast_trylock(lock, &root.mutex_fast));
	CHECK(!native_fast_eligible(&root, KD_OPERATION_MUTEX_LOCK));
	kd_mutex_fast_unlock(&root.mutex_fast);
}
static void check_lifetime(void)
{
	struct kd_task_root_context child;
	struct list_head actors;
	INIT_LIST_HEAD(&actors);
	CHECK(kd_mutex_fast_trylock(lock, &root.mutex_fast));
	CHECK(kd_task_root_detach(&root, &root.initial_native) == -EBUSY);
	root.source_closing = true;
	CHECK(kd_task_root_revoke_cancelled(&root, &root.initial_native, &actors) == -EBUSY);
	CHECK(root.attached && owner.refs == 1 && owner.kd_root_context == &root);
	CHECK(root.core.binding == &root.initial_native);
	setup_root(&child, &waiter);
	child.mutex_fast.lock = lock;
	CHECK(kd_task_root_detach_unpublished(&child, &waiter) == -EBUSY);
	CHECK(child.attached && waiter.refs == 1 && waiter.kd_root_context == &child);
	child.mutex_fast.lock = NULL;
	child.rwsem_fast.lock = lock;
	CHECK(kd_task_root_detach_unpublished(&child, &waiter) == -EBUSY);
	child.rwsem_fast.lock = NULL;
	CHECK(!kd_task_root_detach_unpublished(&child, &waiter));
	CHECK(!waiter.kd_root_context && !waiter.refs);
	kd_mutex_fast_unlock(&root.mutex_fast);
	root.rwsem_fast.lock = lock;
	CHECK(kd_task_root_detach(&root, &root.initial_native) == -EBUSY);
	CHECK(kd_task_root_revoke_cancelled(&root, &root.initial_native, &actors) == -EBUSY);
	root.rwsem_fast.lock = NULL;
	CHECK(!kd_task_root_detach(&root, &root.initial_native));
	CHECK(!owner.kd_root_context && !root.attached && !owner.refs);
}
static void check_native_checks(void)
{
	struct kd_execution_binding *binding = &root.initial_native;
	struct kd_episode_resources resources = { .pool = &root.pool };
	CHECK(!kd_task_validate_native(&root, binding));
	root.mutex_resources = &resources;
	CHECK(!kd_task_validate_native(&root, binding));
	resources.pool = NULL;
	CHECK(kd_task_validate_native(&root, binding) == -EUCLEAN);
	resources.pool = &root.pool;
	root.owners.task = &waiter;
	CHECK(kd_task_validate_native(&root, binding) == -EUCLEAN);
	root.owners.task = &owner;
	root.pool.state = NULL;
	CHECK(kd_task_validate_native(&root, binding) == -EUCLEAN);
	root.pool.state = &root.core;
	root.core.requests = NULL;
	CHECK(kd_task_validate_native(&root, binding) == -EUCLEAN);
	root.core.requests = &root.pool;
	root.aux_entry = &root;
	CHECK(kd_task_validate_native(&root, binding) == -EBUSY);
	root.aux_entry = NULL;
	root.core.exit_holder = &root;
	CHECK(kd_task_validate_native(&root, binding) == -EBUSY);
	root.core.exit_holder = NULL;
	root.core.operation.phase = KD_OPERATION_ENTERED;
	CHECK(kd_task_validate_native(&root, binding) == -EBUSY);
	root.core.operation.phase = KD_OPERATION_IDLE;
	binding->kind = KD_EXECUTION_JIT;
	CHECK(kd_task_validate_native(&root, binding) == -EPERM);
	binding->kind = KD_EXECUTION_NATIVE;
	root.task = &waiter;
	CHECK(kd_task_validate_native(&root, binding) == -EPERM);
	root.task = &owner;
	owner.__state = TASK_UNINTERRUPTIBLE;
	CHECK(kd_task_validate_native(&root, binding) == -EWOULDBLOCK);
	owner.__state = TASK_RUNNING;
	CHECK(!kd_task_validate_native(&root, binding));
}
/* Actual native wrapper and operation predicates. Controlled progress exposes
 * the eligibility transition; it does not model physical owner retirement.
 * The existing reader cases exercise the actual family gate and final release.
 */
struct kd_rw { struct kd_mutex queue; };
struct kd_mutex_entry { int unused; };
struct test_entry_slot { struct kd_mutex_entry entry; };
struct kd_episode_frame { struct test_entry_slot *slot; unsigned long source_target; };
static struct kd_rw entry_rw;
static struct kd_episode_resources entry_resources;
static struct test_entry_slot entry_slot;
static struct kd_episode_frame entry_frame = { .slot = &entry_slot };
static struct list_head retained_marker;
static unsigned int entry_progress, read_attempts, early_read_attempts, frame_prepares, captures;
static bool progress_clears_owner, read_gate_available, progress_opens_gate;
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define PREEMPT_OFFSET 1
#define PREEMPT_MASK 255
static unsigned int preempt_count(void) { return 0; }
static void preempt_disable(void) { CHECK(false); }
static void preempt_enable(void) { CHECK(false); }
static enum kd_operation_kind resolve_source_target(unsigned long target)
{ return (enum kd_operation_kind)target; }
static bool kd_rw_fast_read_is_last(struct test_fast_read *credit, struct kd_rw *rw,
		struct task_struct *task)
{ (void)credit; (void)rw; (void)task; return false; }
static int kd_rw_fast_read_release(struct test_fast_read *credit, struct kd_thread_state *state,
		struct kd_execution_binding *binding)
{ (void)credit; (void)state; (void)binding; CHECK(false); return 0; }
static bool kd_rw_fast_read_trylock(struct kd_rw *rw, struct test_fast_read *credit)
{
	CHECK(rw == &entry_rw && credit == &root.rwsem_fast);
	CHECK(native_fast_eligible(&root, KD_OPERATION_RWSEM_DOWN_READ));
	++read_attempts;
	if (!entry_progress) ++early_read_attempts;
	if (!read_gate_available) return false;
	credit->lock = rw;
	return true;
}
static int kd_task_progress_native(struct kd_task_root_context *context,
		struct kd_execution_binding *binding, bool *pending)
{
	CHECK(context == &root && !kd_task_validate_native(context, binding));
	++entry_progress;
	if (progress_clears_owner) INIT_LIST_HEAD(&context->owners.batches);
	if (progress_opens_gate) read_gate_available = true;
	/* A current native endpoint may keep storage pending after duty drain. */
	*pending = true;
	return 0;
}
static int kd_episode_unlock_native(struct kd_episode_resources *resources,
		struct kd_task_root_context *context, struct kd_execution_binding *binding,
		struct kd_mutex *mutex, enum kd_operation_kind operation)
{
	(void)resources; (void)context; (void)binding; (void)mutex; (void)operation;
	CHECK(false); return 0;
}
static int kd_episode_downgrade_native(struct kd_episode_resources *resources,
		struct kd_task_root_context *context, struct kd_execution_binding *binding,
		struct kd_mutex *mutex, enum kd_operation_kind operation)
{
	(void)resources; (void)context; (void)binding; (void)mutex; (void)operation;
	CHECK(false); return 0;
}
static int kd_episode_prepare_root(struct kd_episode_resources *resources,
		struct kd_execution_binding *binding, enum kd_operation_kind operation,
		struct kd_episode_frame **frame)
{
	CHECK(resources == &entry_resources && binding == &root.initial_native);
	CHECK(operation == KD_OPERATION_RWSEM_DOWN_READ || operation == KD_OPERATION_RWSEM_DOWN_WRITE);
	++frame_prepares; *frame = &entry_frame; return 0;
}
static void run_native(void) { CHECK(false); }
static int kd_mutex_prepare_entry(struct kd_mutex_entry *entry, struct kd_execution_binding *binding,
		void (*run)(void), void *context, unsigned long required_control_bytes)
{
	CHECK(entry == &entry_slot.entry && binding == &root.initial_native && run == run_native &&
	      context == &entry_frame && required_control_bytes == root.mutex_control_bytes);
	++captures; return 0;
}
#include "entry_functions.h"

static void setup_entry(bool retained_owner, bool drain, bool gate)
{
	setup_root(&root, &owner);
	entry_resources.pool = &root.pool;
	entry_resources.config.family = KD_LOCK_FAMILY_RWSEM;
	root.mutex_resources = &entry_resources;
	if (retained_owner) root.owners.batches.next = &retained_marker;
	entry_progress = read_attempts = early_read_attempts = frame_prepares = captures = 0;
	progress_clears_owner = drain; read_gate_available = gate; progress_opens_gate = false;
}
static struct kd_mutex_entry *enter_read(void)
{
	return prepare_current(&entry_rw.queue, KD_OPERATION_RWSEM_DOWN_READ,
		(unsigned long)KD_OPERATION_RWSEM_DOWN_READ);
}
static void check_read_recheck(void)
{
	setup_entry(true, true, true);
	CHECK(!enter_read());
	CHECK(entry_progress == 1 && read_attempts == 1 && !early_read_attempts &&
	      !frame_prepares && !captures && root.rwsem_fast.lock == &entry_rw);
	setup_entry(true, false, true);
	CHECK(enter_read() == &entry_slot.entry);
	CHECK(entry_progress == 1 && !read_attempts && frame_prepares == 1 && captures == 1);
	setup_entry(true, true, true);
	root.core.grants.next = &retained_marker;
	CHECK(enter_read() == &entry_slot.entry);
	CHECK(entry_progress == 1 && !read_attempts && frame_prepares == 1 && captures == 1);
	setup_entry(false, false, false);
	progress_opens_gate = true;
	CHECK(enter_read() == &entry_slot.entry);
	CHECK(entry_progress == 1 && read_attempts == 1 && early_read_attempts == 1 &&
	      read_gate_available && frame_prepares == 1 && captures == 1);
	setup_entry(true, true, false);
	CHECK(enter_read() == &entry_slot.entry);
	CHECK(entry_progress == 1 && read_attempts == 1 && !early_read_attempts &&
	      frame_prepares == 1 && captures == 1);
	setup_entry(true, true, true);
	CHECK(prepare_current(&entry_rw.queue, KD_OPERATION_RWSEM_DOWN_WRITE,
		(unsigned long)KD_OPERATION_RWSEM_DOWN_WRITE) == &entry_slot.entry);
	CHECK(entry_progress == 1 && !read_attempts && frame_prepares == 1 && captures == 1);
}
int main(int argc, char **argv)
{
	CHECK(argc == 2);
	setup();
	if (!strcmp(argv[1], "reuse")) check_reuse();
	else if (!strcmp(argv[1], "failed")) check_failed();
	else if (!strcmp(argv[1], "linked")) check_linked();
	else if (!strcmp(argv[1], "delayed")) check_delayed();
	else if (!strcmp(argv[1], "eligibility")) check_eligibility();
	else if (!strcmp(argv[1], "lifetime")) check_lifetime();
	else if (!strcmp(argv[1], "native_checks")) check_native_checks();
	else if (!strcmp(argv[1], "read_recheck")) check_read_recheck();
	else CHECK(false);
	CHECK(!munmap(lock, page_size) && !munmap(successor, page_size));
	printf("PASS %s\n", argv[1]);
	return 0;
}
