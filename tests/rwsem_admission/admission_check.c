// SPDX-License-Identifier: GPL-2.0-only
/* Actual admission functions with controlled scheduler and atomic endpoints. */
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); abort(); } } while (0)
#define BUG_ON(x) CHECK(!(x))
#define TASK_RUNNING 0
#define TASK_UNINTERRUPTIBLE 2
#define TASK_KILLABLE 4
struct kd_rw;
struct list_head { struct list_head *next, *prev; };
static void INIT_LIST_HEAD(struct list_head *h) { h->next = h->prev = h; }
static bool list_empty(const struct list_head *h) { return h->next == h; }
static void list_add_tail(struct list_head *e, struct list_head *h)
{ e->prev = h->prev; e->next = h; h->prev->next = e; h->prev = e; }
static void list_del_init(struct list_head *e)
{ e->prev->next = e->next; e->next->prev = e->prev; INIT_LIST_HEAD(e); }
#define list_entry(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define list_for_each_entry_safe(p, n, h, m) \
	for (p = list_entry((h)->next, __typeof__(*p), m), n = list_entry(p->m.next, __typeof__(*p), m); \
	     &p->m != (h); p = n, n = list_entry(n->m.next, __typeof__(*n), m))

typedef struct { long value; } atomic_long_t;
typedef pthread_mutex_t raw_spinlock_t;
struct mock_task { pthread_mutex_t guard; pthread_cond_t changed; int state; bool signal; };
struct wait_entry { struct wait_entry *next; struct mock_task *task; bool linked; };
typedef struct { pthread_mutex_t guard; struct wait_entry *first; } wait_queue_head_t;
struct kd_mutex { void *tail, *owner; };
struct task_struct;
#include "admission_types.h"
static _Thread_local struct mock_task *current;
static _Thread_local unsigned int guards, scheduled, guard_calls;
static _Thread_local unsigned int inject_read;
static _Thread_local unsigned int published_waits;
static bool protect_final;
static size_t page_bytes;
static struct kd_rw *sem;

static void kd_rw_admission_write_put_forward(struct kd_rw *lock);
static long atomic_long_read(atomic_long_t *v)
{
	long value = __atomic_load_n(&v->value, __ATOMIC_RELAXED);
	if (inject_read && !--inject_read)
		kd_rw_admission_write_put_forward(sem);
	return value;
}
static long atomic_compare(atomic_long_t *v, long old, long next, int order)
{
	long observed = old;
	bool changed = __atomic_compare_exchange_n(&v->value, &observed, next, false, order, __ATOMIC_RELAXED);
	if (changed && (unsigned long)next - (unsigned long)old == KD_RW_ADMIT_WAIT)
		++published_waits;
	if (changed && !next && protect_final) {
		CHECK(!guards);
		CHECK(!mprotect(sem, page_bytes, PROT_NONE));
	}
	return observed;
}
#define atomic_long_cmpxchg(v, o, n) atomic_compare(v, o, n, __ATOMIC_SEQ_CST)
#define atomic_long_cmpxchg_acquire(v, o, n) atomic_compare(v, o, n, __ATOMIC_ACQUIRE)
#define atomic_long_cmpxchg_release(v, o, n) atomic_compare(v, o, n, __ATOMIC_RELEASE)
static void atomic_long_add(unsigned long n, atomic_long_t *v)
{ __atomic_fetch_add(&v->value, n, __ATOMIC_SEQ_CST); }
static long atomic_long_fetch_andnot_release(unsigned long mask, atomic_long_t *v)
{
	long old = __atomic_fetch_and(&v->value, ~mask, __ATOMIC_RELEASE);
	if (!(old & ~mask) && protect_final) {
		CHECK(!guards);
		CHECK(!mprotect(sem, page_bytes, PROT_NONE));
	}
	return old;
}
static void raw_spin_lock(raw_spinlock_t *lock)
{ CHECK(!pthread_mutex_lock(lock)); ++guards; ++guard_calls; }
static void raw_spin_unlock(raw_spinlock_t *lock)
{ CHECK(guards); --guards; CHECK(!pthread_mutex_unlock(lock)); }
static void __set_current_state(int state)
{ CHECK(!pthread_mutex_lock(&current->guard)); current->state = state; CHECK(!pthread_mutex_unlock(&current->guard)); }
#define DEFINE_WAIT(name) struct wait_entry name = { 0 }
static void prepare_to_wait(wait_queue_head_t *q, struct wait_entry *w, unsigned int state)
{
	CHECK(!pthread_mutex_lock(&q->guard));
	if (!w->linked) { w->task = current; w->next = q->first; q->first = w; w->linked = true; }
	__set_current_state(state);
	CHECK(!pthread_mutex_unlock(&q->guard));
}
static void finish_wait(wait_queue_head_t *q, struct wait_entry *w)
{
	struct wait_entry **at;
	CHECK(!pthread_mutex_lock(&q->guard));
	for (at = &q->first; *at && *at != w; at = &(*at)->next) {}
	CHECK(*at == w); *at = w->next; w->linked = false;
	__set_current_state(TASK_RUNNING);
	CHECK(!pthread_mutex_unlock(&q->guard));
}
static void wake_task(struct mock_task *task)
{
	CHECK(!pthread_mutex_lock(&task->guard)); task->state = TASK_RUNNING;
	CHECK(!pthread_cond_broadcast(&task->changed)); CHECK(!pthread_mutex_unlock(&task->guard));
}
static void wake_up_all(wait_queue_head_t *q)
{
	struct wait_entry *w;
	CHECK(!pthread_mutex_lock(&q->guard));
	for (w = q->first; w; w = w->next) wake_task(w->task);
	CHECK(!pthread_mutex_unlock(&q->guard));
}
static void schedule(void)
{
	CHECK(!guards); ++scheduled; CHECK(!pthread_mutex_lock(&current->guard));
	while (current->state != TASK_RUNNING) CHECK(!pthread_cond_wait(&current->changed, &current->guard));
	CHECK(!pthread_mutex_unlock(&current->guard));
}
static void cond_resched(void) { CHECK(!guards); sched_yield(); }
static bool signal_pending_state(unsigned int state, struct mock_task *task)
{ return state == TASK_KILLABLE && __atomic_load_n(&task->signal, __ATOMIC_ACQUIRE); }

#include "admission_functions.h"
static void kd_rw_admission_write_put_forward(struct kd_rw *lock)
{ kd_rw_admission_write_put(lock, false); }

static struct mock_task tasks[4];
static unsigned int arrived, leave_readers;
static int reader_results[2];
static unsigned int reader_wait_state = TASK_UNINTERRUPTIBLE;
static void *reader(void *argument)
{
	unsigned int index = (uintptr_t)argument;
	current = &tasks[index + 1];
	reader_results[index] = kd_rw_admission_read(sem, reader_wait_state, NULL, NULL);
	__atomic_fetch_add(&arrived, 1, __ATOMIC_RELEASE);
	while (!__atomic_load_n(&leave_readers, __ATOMIC_ACQUIRE)) sched_yield();
	if (!reader_results[index]) kd_rw_admission_read_put(sem);
	return NULL;
}
static void await_bits(unsigned long mask, unsigned long value)
{
	while (((unsigned long)atomic_long_read(&sem->admission) & mask) != value) sched_yield();
}
static void join_readers(pthread_t *threads, unsigned int count)
{
	unsigned int i;
	__atomic_store_n(&leave_readers, 1, __ATOMIC_RELEASE);
	for (i = 0; i < count; ++i) CHECK(!pthread_join(threads[i], NULL));
}
static void setup(void)
{
	unsigned int i;
	page_bytes = sysconf(_SC_PAGESIZE);
	CHECK(sizeof(*sem) <= page_bytes);
	sem = mmap(NULL, page_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(sem != MAP_FAILED);
	sem->atomic_admission = true;
	CHECK(!pthread_mutex_init(&sem->guard, NULL));
	CHECK(!pthread_mutex_init(&sem->changed.guard, NULL));
	INIT_LIST_HEAD(&sem->read_waiters);
	for (i = 0; i < 4; ++i) {
		CHECK(!pthread_mutex_init(&tasks[i].guard, NULL));
		CHECK(!pthread_cond_init(&tasks[i].changed, NULL));
	}
	current = &tasks[0];
}

int main(int argc, char **argv)
{
	pthread_t threads[2];
	const struct rlimit no_core = { 0, 0 };
	unsigned int i;
	CHECK(argc == 2); CHECK(!setrlimit(RLIMIT_CORE, &no_core)); alarm(8); setup();
	if (!strcmp(argv[1], "fast")) {
		CHECK(kd_rw_admission_read_try(sem)); CHECK(kd_rw_admission_read_try(sem));
		CHECK(!kd_rw_admission_write_try(sem, false));
		kd_rw_admission_read_put(sem); kd_rw_admission_read_put(sem);
		CHECK(kd_rw_admission_write_try(sem, false)); CHECK(!kd_rw_admission_read_try(sem));
		kd_rw_admission_write_put(sem, false); CHECK(!guard_calls && !scheduled);
	} else if (!strcmp(argv[1], "publish_recheck")) {
		CHECK(kd_rw_admission_write_try(sem, false));
		/* The second load is the failed read probe under the family guard.
		 * Return its old WRITE value after completing the writer's release.
		 */
		inject_read = 2;
		CHECK(!kd_rw_admission_read(sem, TASK_UNINTERRUPTIBLE, NULL, NULL));
		CHECK(!inject_read && published_waits == 1 && !scheduled && kd_rw_admission_readers(sem) == 1);
		CHECK(!(atomic_long_read(&sem->admission) & KD_RW_ADMIT_WAIT_MASK));
		kd_rw_admission_read_put(sem);
	} else if (!strcmp(argv[1], "reader_phase")) {
		kd_rw_admission_queue_get(sem); CHECK(kd_rw_admission_write_try(sem, true));
		for (i = 0; i < 2; ++i) CHECK(!pthread_create(&threads[i], NULL, reader, (void *)(uintptr_t)i));
		await_bits(KD_RW_ADMIT_WAIT_MASK, 2 * KD_RW_ADMIT_WAIT);
		kd_rw_admission_write_put(sem, false);
		while (__atomic_load_n(&arrived, __ATOMIC_ACQUIRE) != 2) sched_yield();
		CHECK(!reader_results[0] && !reader_results[1] && kd_rw_admission_readers(sem) == 2);
		CHECK(!kd_rw_admission_read_try(sem) && !kd_rw_admission_write_try(sem, true));
		join_readers(threads, 2);
		CHECK(kd_rw_admission_write_try(sem, true));
		kd_rw_admission_write_put(sem, false); kd_rw_admission_queue_put(sem);
	} else if (!strcmp(argv[1], "cancel_read")) {
		CHECK(kd_rw_admission_write_try(sem, false)); reader_wait_state = TASK_KILLABLE;
		CHECK(!pthread_create(&threads[0], NULL, reader, NULL));
		await_bits(KD_RW_ADMIT_WAIT_MASK, KD_RW_ADMIT_WAIT);
		__atomic_store_n(&tasks[1].signal, true, __ATOMIC_RELEASE); wake_task(&tasks[1]);
		join_readers(threads, 1); CHECK(reader_results[0] == -EINTR);
		CHECK((unsigned long)atomic_long_read(&sem->admission) == KD_RW_ADMIT_WRITE);
		kd_rw_admission_write_put(sem, false);
	} else if (!strcmp(argv[1], "cancel_queue")) {
		CHECK(kd_rw_admission_read_try(sem)); kd_rw_admission_queue_get(sem);
		CHECK(!pthread_create(&threads[0], NULL, reader, NULL));
		await_bits(KD_RW_ADMIT_WAIT_MASK, KD_RW_ADMIT_WAIT);
		kd_rw_admission_queue_put(sem);
		while (!__atomic_load_n(&arrived, __ATOMIC_ACQUIRE)) sched_yield();
		CHECK(!reader_results[0] && kd_rw_admission_readers(sem) == 2);
		join_readers(threads, 1); kd_rw_admission_read_put(sem);
	} else if (!strcmp(argv[1], "downgrade")) {
		CHECK(kd_rw_admission_write_try(sem, false)); kd_rw_admission_write_put(sem, true);
		CHECK(kd_rw_admission_readers(sem) == 1 && !kd_rw_admission_write_try(sem, false));
		CHECK(kd_rw_admission_read_try(sem)); kd_rw_admission_read_put(sem); kd_rw_admission_read_put(sem);
	} else if (!strcmp(argv[1], "final")) {
		CHECK(kd_rw_admission_read_try(sem)); protect_final = true;
		kd_rw_admission_read_put(sem);
		CHECK(!mprotect(sem, page_bytes, PROT_READ | PROT_WRITE)); protect_final = false;
	} else if (!strcmp(argv[1], "bounds")) {
		for (i = 0; i < 3; ++i) {
			pid_t child = fork(); int status;
			CHECK(child >= 0);
			if (!child) {
				alarm(3);
				if (!i) { sem->admission.value = KD_RW_ADMIT_READ_MASK; kd_rw_admission_read_try(sem); }
				else if (i == 1) { sem->admission.value = KD_RW_ADMIT_QUEUE_MASK; kd_rw_admission_queue_get(sem); }
				else { sem->admission.value = KD_RW_ADMIT_WAIT_MASK | KD_RW_ADMIT_WRITE;
					kd_rw_admission_read(sem, TASK_UNINTERRUPTIBLE, NULL, NULL); }
				_exit(2);
			}
			CHECK(waitpid(child, &status, 0) == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
		}
	} else { CHECK(false); }
	CHECK(!atomic_long_read(&sem->admission));
	CHECK(list_empty(&sem->read_waiters) && !sem->changed.first);
	printf("PASS %s\n", argv[1]); return 0;
}
