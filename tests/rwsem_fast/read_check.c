// SPDX-License-Identifier: GPL-2.0-only
/* Actual reader functions; controlled wait, writer and compatibility endpoints. */
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

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#define BUG_ON(x) CHECK(!(x))
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x, v) __atomic_store_n(&(x), (v), __ATOMIC_RELAXED)
#define TASK_RUNNING 0
#define TASK_UNINTERRUPTIBLE 2
#define KD_GRANT_PHYSICAL_READ 1
#define KD_OPERATION_RWSEM_UP_READ 7

struct list_head { struct list_head *next, *prev; };
static void INIT_LIST_HEAD(struct list_head *h) { h->next = h->prev = h; }
static bool list_empty(const struct list_head *h) { return h->next == h; }
static void list_add_tail(struct list_head *e, struct list_head *h)
{ e->prev = h->prev; e->next = h; h->prev->next = e; h->prev = e; }
static void list_del_init(struct list_head *e)
{ e->prev->next = e->next; e->next->prev = e->prev; INIT_LIST_HEAD(e); }
#define list_entry(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define list_for_each_entry_reverse(p, h, m) \
	for ((p) = list_entry((h)->prev, __typeof__(*(p)), m); &(p)->m != (h); \
	     (p) = list_entry((p)->m.prev, __typeof__(*(p)), m))

typedef struct { pthread_mutex_t mutex; } raw_spinlock_t;
typedef struct { int unused; } wait_queue_head_t;
static void after_unlock(raw_spinlock_t *guard);
static void raw_spin_lock_init(raw_spinlock_t *g) { CHECK(!pthread_mutex_init(&g->mutex, NULL)); }
static void raw_spin_lock(raw_spinlock_t *g) { CHECK(!pthread_mutex_lock(&g->mutex)); }
static void raw_spin_unlock(raw_spinlock_t *g)
{ CHECK(!pthread_mutex_unlock(&g->mutex)); after_unlock(g); }
struct task_struct;
struct kd_thread_state;
struct kd_execution_binding;
struct kd_mutex_node { int unused; };
struct kd_mutex_batch { int unused; };
struct kd_mutex { struct kd_mutex_node *tail; struct kd_mutex_batch *owner; };
#include "read_types.h"
struct kd_task_root_context;
struct task_struct { int state; struct kd_task_root_context *root; };
struct kd_execution_binding { struct kd_thread_state *state; };
struct kd_thread_state { struct task_struct *origin; struct kd_execution_binding *binding; };
struct kd_task_root_context {
	struct kd_thread_state core;
	struct kd_execution_binding binding;
	struct kd_rw_read_credit rwsem_fast;
	void *mutex_resources;
};
static _Thread_local struct task_struct *current;
static bool in_task(void) { return current != NULL; }
static bool irqs_disabled(void) { return false; }
static bool in_atomic(void) { return false; }
static void __set_current_state(int state) { current->state = state; }
static bool kd_state_is_current(struct kd_thread_state *s, struct kd_execution_binding *b)
{ return s && b && s->binding == b; }
static struct kd_execution_binding *kd_state_current_binding(struct kd_thread_state *s) { return s->binding; }
static void cpu_relax(void) { __asm__ volatile("pause" ::: "memory"); }
static unsigned int wait_prepares, wait_finishes, wakeups;
struct test_wait { int unused; };
#define DEFINE_WAIT(name) struct test_wait name = {0}
static void prepare_to_wait(wait_queue_head_t *q, struct test_wait *wait, int state)
{ (void)q; (void)wait; ++wait_prepares; __set_current_state(state); }
static void finish_wait(wait_queue_head_t *q, struct test_wait *wait)
{ (void)q; (void)wait; ++wait_finishes; __set_current_state(TASK_RUNNING); }
static void wake_up_all(wait_queue_head_t *q) { (void)q; ++wakeups; }
static void schedule(void);
static struct kd_observation events[96];
static unsigned int event_count;
static pthread_mutex_t event_guard = PTHREAD_MUTEX_INITIALIZER;
#define kd_observe(k, ...) do { \
	CHECK(!pthread_mutex_lock(&event_guard)); CHECK(event_count < 96); \
	events[event_count++] = (struct kd_observation){ .kind = (k), .task = (unsigned long)current, __VA_ARGS__ }; \
	CHECK(!pthread_mutex_unlock(&event_guard)); \
} while (0)
#include "read_functions.h"

static struct kd_rwsem *sem;
static struct task_struct tasks[3];
static struct kd_task_root_context roots[3];
static struct kd_rw_read_credit managed;
static struct kd_rw_read_link native_link, nonowner_link;
static struct kd_mutex_node writer_node;
static struct kd_mutex_batch writer_batch;
static size_t page_size;
static bool release_on_wait, make_inaccessible, inaccessible;
static unsigned int managed_routes, native_routes;

static void after_unlock(raw_spinlock_t *guard)
{
	if (make_inaccessible && guard == &sem->core.guard && wakeups) {
		CHECK(!inaccessible && !sem->core.readers);
		CHECK(!mprotect(sem, page_size, PROT_NONE));
		inaccessible = true;
		make_inaccessible = false;
	}
}
static void schedule(void)
{
	CHECK(release_on_wait);
	raw_spin_lock(&sem->core.guard);
	sem->core.writer_pending = false;
	raw_spin_unlock(&sem->core.guard);
	release_on_wait = false;
}
static void setup(void)
{
	page_size = sysconf(_SC_PAGESIZE);
	CHECK(sizeof(*sem) < page_size);
	sem = mmap(NULL, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(sem != MAP_FAILED);
	raw_spin_lock_init(&sem->core.guard);
	INIT_LIST_HEAD(&sem->core.active_reads);
	for (unsigned int i = 0; i < 3; ++i) {
		tasks[i].root = &roots[i]; roots[i].core.origin = &tasks[i];
		roots[i].core.binding = &roots[i].binding; roots[i].binding.state = &roots[i].core;
		kd_rw_fast_read_init(&roots[i].rwsem_fast, &roots[i].core);
	}
	current = &tasks[0];
	kd_rw_read_credit_init(&managed);
}
static int release_fast(unsigned int i)
{
	current = &tasks[i];
	return kd_rw_fast_read_release(&roots[i].rwsem_fast, &roots[i].core, &roots[i].binding);
}
static void acquire_managed(void)
{
	CHECK(!kd_rw_read_acquire(&sem->core, &managed, &roots[0].core, &roots[0].binding,
		&managed, &managed, false, NULL, NULL));
}

/* Controlled adjacent endpoints isolate the actual Linux release dispatcher.
 * Their full pool/entry implementations remain covered by live VM fixtures.
 */
struct kd_source_grant { int unused; };
struct kd_linux_rwsem_binding { struct kd_rwsem *lock; };
struct kd_mutex_entry;
static struct kd_task_root_context *native_root(void) { return current->root; }
static struct kd_source_grant *managed_grant(struct kd_rwsem *lock, bool read)
{
	static struct kd_source_grant grant;
	const void *last;
	return read && kd_rw_last_owned_read(&lock->core, current, &last) == KD_RW_READ_MANAGED ? &grant : NULL;
}
static int kd_episode_unlock_native(void *resources, struct kd_task_root_context *root,
		struct kd_execution_binding *binding, struct kd_mutex *queue, int operation)
{
	(void)resources;
	CHECK(root == &roots[0] && queue == &sem->core.queue && operation == KD_OPERATION_RWSEM_UP_READ);
	++managed_routes;
	return kd_rw_read_release(&managed, &root->core, binding, &managed, &managed);
}
static void kd_linux_rwsem_up_read_entry_asm(void) { }
static struct kd_mutex_entry *kd_rwsem_prepare_source_current(struct kd_rwsem *lock, int operation,
		unsigned long target)
{
	struct kd_task_root_context *root = current->root;
	CHECK(lock == sem && operation == KD_OPERATION_RWSEM_UP_READ &&
	      target == (unsigned long)kd_linux_rwsem_up_read_entry_asm);
	if (kd_rw_fast_read_is_last(&root->rwsem_fast, &lock->core, current))
		CHECK(!kd_rw_fast_read_release(&root->rwsem_fast, &root->core, &root->binding));
	else
		CHECK(!kd_episode_unlock_native(NULL, root, &root->binding, &lock->core.queue, operation));
	return NULL;
}
static int kd_rw_native_read_unlock(struct kd_rw *lock, bool non_owner)
{
	const void *last;
	CHECK(!non_owner && kd_rw_last_owned_read(lock, current, &last) == KD_RW_READ_NATIVE);
	CHECK(last == &native_link);
	raw_spin_lock(&lock->guard);
	list_del_init(&native_link.link); --lock->readers; ++native_routes;
	raw_spin_unlock(&lock->guard);
	return 0;
}
#include "linux_functions.h"

static void check_credits(void)
{
	CHECK(kd_rw_fast_read_trylock(&sem->core, &roots[0].rwsem_fast));
	current = &tasks[1];
	CHECK(kd_rw_fast_read_trylock(&sem->core, &roots[1].rwsem_fast));
	CHECK(sem->core.readers == 2 && !wait_prepares && !wait_finishes);
	CHECK(!release_fast(0) && sem->core.readers == 1);
	CHECK(!release_fast(1) && !sem->core.readers && list_empty(&sem->core.active_reads));
	current = &tasks[0];
	CHECK(kd_rw_fast_read_trylock(&sem->core, &roots[0].rwsem_fast));
	CHECK(!release_fast(0));
	CHECK(event_count == 9 && events[2].kind == KD_OBS_READ_RELEASE &&
	      events[3].kind == KD_OBS_FAST_READ_DONE);
}
static void check_fallback(void)
{
	sem->core.writer = &writer_batch;
	CHECK(!kd_rw_fast_read_trylock(&sem->core, &roots[0].rwsem_fast));
	sem->core.writer = NULL; sem->core.writer_pending = true;
	CHECK(!kd_rw_fast_read_trylock(&sem->core, &roots[0].rwsem_fast));
	sem->core.writer_pending = false; sem->core.queue.tail = &writer_node;
	CHECK(!kd_rw_fast_read_trylock(&sem->core, &roots[0].rwsem_fast));
	CHECK(!event_count && !sem->core.readers && !roots[0].rwsem_fast.lock &&
	      list_empty(&roots[0].rwsem_fast.active_read.link));
	sem->core.queue.tail = NULL; sem->core.writer_pending = true; release_on_wait = true;
	acquire_managed();
	CHECK(wait_prepares && wait_finishes && sem->core.readers == 1);
	CHECK(!kd_rw_read_release(&managed, &roots[0].core, &roots[0].binding, &managed, &managed));
	CHECK(!sem->core.readers && !roots[0].rwsem_fast.lock);
}
static int writer_waiting, writer_entered;
static void *arriving_writer(void *unused)
{
	(void)unused; current = &tasks[2];
	raw_spin_lock(&sem->core.guard); sem->core.writer_pending = true;
	__atomic_store_n(&writer_waiting, 1, __ATOMIC_RELEASE); raw_spin_unlock(&sem->core.guard);
	for (;;) {
		raw_spin_lock(&sem->core.guard);
		if (!sem->core.readers) {
			sem->core.writer = &writer_batch; sem->core.writer_pending = false;
			__atomic_store_n(&writer_entered, 1, __ATOMIC_RELEASE);
			raw_spin_unlock(&sem->core.guard); return NULL;
		}
		raw_spin_unlock(&sem->core.guard); sched_yield();
	}
}
static void check_writer(void)
{
	pthread_t writer;
	CHECK(kd_rw_fast_read_trylock(&sem->core, &roots[0].rwsem_fast));
	CHECK(!pthread_create(&writer, NULL, arriving_writer, NULL));
	while (!__atomic_load_n(&writer_waiting, __ATOMIC_ACQUIRE)) sched_yield();
	current = &tasks[1];
	CHECK(!kd_rw_fast_read_trylock(&sem->core, &roots[1].rwsem_fast));
	CHECK(!__atomic_load_n(&writer_entered, __ATOMIC_ACQUIRE));
	CHECK(!release_fast(0) && !pthread_join(writer, NULL));
	CHECK(writer_entered && sem->core.writer == &writer_batch && wakeups == 1);
}
static void add_compatibility(struct kd_rw_read_link *link, enum kd_rw_read_kind kind)
{
	INIT_LIST_HEAD(&link->link); link->logical_owner = current; link->kind = kind; link->credit = link;
	raw_spin_lock(&sem->core.guard);
	list_add_tail(&link->link, &sem->core.active_reads); ++sem->core.readers;
	raw_spin_unlock(&sem->core.guard);
}
static void check_routing(void)
{
	struct kd_linux_rwsem_binding binding = { .lock = sem };
	CHECK(kd_rw_fast_read_trylock(&sem->core, &roots[0].rwsem_fast));
	acquire_managed();
	CHECK(release_fast(0) == -ESTALE && sem->core.readers == 2);
	CHECK(kd_linux_rwsem_source_release(&binding, true));
	CHECK(!kd_linux_rwsem_prepare_up_read_current(sem));
	CHECK(managed_routes == 1 && sem->core.readers == 1);
	add_compatibility(&native_link, KD_RW_READ_NATIVE);
	CHECK(!kd_linux_rwsem_source_release(&binding, true));
	kd_linux_rwsem_up_read(&binding);
	CHECK(native_routes == 1 && sem->core.readers == 1);
	add_compatibility(&nonowner_link, KD_RW_READ_NON_OWNER);
	CHECK(kd_linux_rwsem_source_release(&binding, true));
	CHECK(!kd_linux_rwsem_source_release(&binding, false));
	kd_linux_rwsem_up_read(&binding);
	CHECK(!roots[0].rwsem_fast.lock && sem->core.readers == 1 && !list_empty(&nonowner_link.link));
	/* Finish the separately supplied nonowner stand-in, by its exact link. */
	raw_spin_lock(&sem->core.guard);
	list_del_init(&nonowner_link.link); --sem->core.readers;
	raw_spin_unlock(&sem->core.guard);
}
static void check_final(void)
{
	CHECK(kd_rw_fast_read_trylock(&sem->core, &roots[0].rwsem_fast));
	make_inaccessible = true;
	CHECK(!release_fast(0) && inaccessible && !roots[0].rwsem_fast.lock);
	CHECK(release_fast(0) == -ESTALE);
	CHECK(event_count == 3 && events[2].kind == KD_OBS_FAST_READ_DONE &&
	      events[2].object == (unsigned long)sem && !events[2].source_user);
}
int main(int argc, char **argv)
{
	CHECK(argc == 2); setup();
	if (!strcmp(argv[1], "credits")) check_credits();
	else if (!strcmp(argv[1], "fallback")) check_fallback();
	else if (!strcmp(argv[1], "writer")) check_writer();
	else if (!strcmp(argv[1], "routing")) check_routing();
	else if (!strcmp(argv[1], "final")) check_final();
	else CHECK(false);
	CHECK(!munmap(sem, page_size));
	printf("PASS %s\n", argv[1]); return 0;
}
