/* Deterministic scheduler/wake fixture for the real owned mutex core. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

typedef uint32_t u32;
typedef struct { unsigned long counter; } atomic_long_t;
typedef struct { unsigned int counter; } atomic_t;
typedef struct { unsigned int locked; } raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct list_head { struct list_head *next, *prev; };
struct mutex {
	atomic_long_t owner;
	raw_spinlock_t wait_lock;
	struct optimistic_spin_queue osq;
	struct list_head wait_list;
};
struct wake_q_node { struct wake_q_node *next; };
struct task_struct {
	struct wake_q_node wake_q;
	int refs, state, on_cpu, wakes, owned_holds;
} __attribute__((aligned(64)));
static struct task_struct tasks[3];
static struct task_struct *current;
static int pin_count, schedules, spins, combine_calls, osq_locks, osq_unlocks;
static bool resched, release_before_waiters;
static void (*schedule_action)(void), (*osq_action)(void);

#define CONFIG_X86_64 1
#define CONFIG_MUTEX_SPIN_ON_OWNER 1
#undef static_assert
#define static_assert(expr, ...) _Static_assert(expr, #expr)
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define noinline __attribute__((noinline))
#define likely(x) (x)
#define unlikely(x) (x)
#define BUG_ON(x) assert(!(x))
#define BUG() assert(false)
#define EXPORT_SYMBOL_GPL(x)
#define TASK_RUNNING 0
#define TASK_UNINTERRUPTIBLE 2
#define OSQ_UNLOCKED_VAL 0
#define ATOMIC_LONG_INIT(x) { (x) }
#define OSQ_LOCK_UNLOCKED { { 0 } }
#define __RAW_SPIN_LOCK_UNLOCKED(name) { 0 }
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x, v) __atomic_store_n(&(x), (v), __ATOMIC_RELAXED)
#define smp_store_release(p, v) __atomic_store_n((p), (v), __ATOMIC_RELEASE)
#define smp_mb__before_atomic() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define barrier() __asm__ __volatile__("" ::: "memory")
#define cmpxchg_relaxed(p, old, val) ({ \
	__typeof__(*(p)) expected = (old); \
	__atomic_compare_exchange_n((p), &expected, (val), false, \
				    __ATOMIC_RELAXED, __ATOMIC_RELAXED); expected; })
#define atomic_long_read(p) READ_ONCE((p)->counter)
#define atomic_long_set(p, v) WRITE_ONCE((p)->counter, (v))
#define atomic_read(p) READ_ONCE((p)->counter)
#define atomic_set(p, v) WRITE_ONCE((p)->counter, (v))
#define atomic_long_or(v, p) ({ \
	if (release_before_waiters) { \
		assert((p)->counter == (unsigned long)&tasks[0]); \
		(p)->counter = 0; tasks[0].owned_holds--; release_before_waiters = false; \
	} \
	__atomic_fetch_or(&(p)->counter, (v), __ATOMIC_SEQ_CST); })
#define atomic_long_andnot(v, p) __atomic_fetch_and(&(p)->counter, ~(v), __ATOMIC_SEQ_CST)
#define atomic_long_try_cmpxchg_acquire(p, old, val) \
	__atomic_compare_exchange_n(&(p)->counter, (old), (val), false, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)
#define atomic_long_try_cmpxchg_release(p, old, val) \
	__atomic_compare_exchange_n(&(p)->counter, (old), (val), false, __ATOMIC_RELEASE, __ATOMIC_RELAXED)
#define LIST_HEAD_INIT(name) { &(name), &(name) }
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define list_first_entry(p, type, member) container_of((p)->next, type, member)
static void INIT_LIST_HEAD(struct list_head *p) { p->next = p->prev = p; }
static bool list_empty(const struct list_head *p) { return p->next == p; }
static void list_add_tail(struct list_head *p, struct list_head *head)
{
	p->next = head; p->prev = head->prev;
	head->prev->next = p; head->prev = p;
}
static void list_del_init(struct list_head *p)
{
	p->prev->next = p->next; p->next->prev = p->prev; INIT_LIST_HEAD(p);
}
static void raw_spin_lock_init(raw_spinlock_t *p) { p->locked = 0; }
static void preempt_disable(void) { pin_count++; }
static void preempt_count_dec(void) { assert(pin_count > 0); pin_count--; }
static void preempt_enable(void) { preempt_count_dec(); }
static void raw_spin_lock(raw_spinlock_t *p)
{
	assert(!p->locked); preempt_disable(); p->locked = 1;
}
static void raw_spin_unlock(raw_spinlock_t *p)
{
	assert(p->locked); p->locked = 0; preempt_enable();
}
static void might_sleep(void) { assert(pin_count == 0); }
static void lockdep_assert_preemption_disabled(void) { assert(pin_count > 0); }
static bool need_resched(void) { return resched; }
static bool owner_on_cpu(struct task_struct *p) { assert(pin_count); return p->on_cpu; }
static void cpu_relax(void) { assert(++spins < 1000); }
static void set_current_state(int state) { current->state = state; }
#define __set_current_state set_current_state
static void schedule(void)
{
	assert(pin_count == 0 && schedule_action); schedules++; schedule_action();
}
static void get_task_struct(struct task_struct *p) { p->refs++; }
struct wake_q_head { struct wake_q_node *first, **lastp; };
#define WAKE_Q_TAIL ((struct wake_q_node *)1)
#define DEFINE_WAKE_Q(name) struct wake_q_head name = { WAKE_Q_TAIL, &name.first }
static void wake_up_q(struct wake_q_head *q)
{
	struct wake_q_node *p = q->first;
	while (p != WAKE_Q_TAIL) {
		struct task_struct *task = container_of(p, struct task_struct, wake_q);
		struct wake_q_node *next = p->next;
		assert(task->refs > 0); task->refs--; task->wakes++;
		task->state = TASK_RUNNING; p->next = NULL; p = next;
	}
}

static bool route_borrowed;
static int owner_ack_requests;
bool kd_mutex_task_reroute(struct task_struct *task);
bool kd_exec_native_unlock(unsigned long address, bool mutex);
void kd_owned_mutex_task_enter(void) { current->owned_holds++; }
void kd_owned_mutex_task_leave(void) { assert(current->owned_holds > 0); current->owned_holds--; }
#include "owned_production.h"

bool kd_mutex_task_reroute(struct task_struct *task)
{
	assert(task == current);
	return route_borrowed;
}
bool kd_exec_native_unlock(unsigned long address, bool mutex)
{
	assert(address && mutex && route_borrowed);
	owner_ack_requests++;
	return true;
}
static bool combine_handles;
bool kd_owned_mutex_combine(struct kd_mutex *lock)
{
	combine_calls++;
	if (!combine_handles)
		return false;
	kd_owned_mutex_release(lock);
	return true;
}
bool kd_owned_osq_lock(struct optimistic_spin_queue *lock)
{
	assert(pin_count && !atomic_read(&lock->tail));
	osq_locks++; atomic_set(&lock->tail, 1);
	if (osq_action)
		osq_action();
	return true;
}
void kd_owned_osq_unlock(struct optimistic_spin_queue *lock)
{
	assert(pin_count && atomic_read(&lock->tail));
	osq_unlocks++; atomic_set(&lock->tail, 0);
}

static struct kd_mutex lock;
static DEFINE_KD_MUTEX(static_lock);
static struct kd_owned_mutex_waiter wb, wc;
static void reset(void)
{
	assert(!pin_count);
	for (unsigned int i = 0; i < 3; i++) {
		assert(!tasks[i].refs && !tasks[i].wake_q.next && !tasks[i].owned_holds);
		tasks[i].state = TASK_RUNNING; tasks[i].on_cpu = 0;
	}
	current = &tasks[0]; resched = false; combine_handles = false;
	release_before_waiters = false;
	route_borrowed = false;
	schedule_action = osq_action = NULL; spins = 0;
	kd_mutex_init(&lock);
}
static void publish(struct kd_owned_mutex_waiter *w, unsigned int task, u32 kind)
{
	current = &tasks[task]; w->task = current; w->kind = kind;
	assert(!kd_owned_mutex_publish(&lock, w));
	assert(w->state == KD_OWNED_MUTEX_QUEUED && !list_empty(&w->list));
}
static void release_from_owner(void)
{
	struct task_struct *waiter = current;
	current = &tasks[0]; kd_mutex_unlock(&lock); current = waiter;
	resched = false;
}
static void release_for_spinner(void)
{
	/* The holder runs on another CPU: its ordinary fast release changes only
	 * owner, while this fixture's current CPU remains inside its private OSQ. */
	assert(kd_owned_mutex_owner(&lock) == &tasks[0]);
	atomic_long_set(&lock.owner, 0);
	tasks[0].owned_holds--;
}

int main(void)
{
	assert(kd_owned_mutex_is_idle(&static_lock));
	reset(); kd_mutex_lock(&lock);
	assert(kd_owned_mutex_owned(&lock, current) && !kd_mutex_trylock(&lock));
	current = &tasks[1]; assert(!kd_mutex_trylock(&lock));
	current = &tasks[0]; kd_mutex_unlock(&lock);
	assert(!combine_calls && kd_owned_mutex_is_idle(&lock));

	/* A logical caller's FULL nested unlock requests an ACK without touching
	 * the physical owner's lock, even when its owner word has no flags. */
	reset(); kd_mutex_lock(&lock); current = &tasks[1]; route_borrowed = true;
	kd_mutex_unlock(&lock);
	assert(owner_ack_requests == 1 && kd_owned_mutex_owner(&lock) == &tasks[0]);
	current = &tasks[0]; route_borrowed = false; kd_mutex_unlock(&lock);

	/* SELF wake permits stealing until the first waiter requests handoff. */
	reset(); kd_mutex_lock(&lock); publish(&wb, 1, KD_OWNED_MUTEX_SELF);
	current = &tasks[0]; kd_mutex_unlock(&lock);
	assert(!kd_mutex_is_locked(&lock) && !kd_owned_mutex_is_idle(&lock));
	assert(wb.state == KD_OWNED_MUTEX_QUEUED);
	current = &tasks[2]; assert(kd_mutex_trylock(&lock));
	current = &tasks[1];
	assert(kd_owned_mutex_trylock_common(&lock, true) == &tasks[2]);
	assert(atomic_long_read(&lock.owner) & KD_OWNED_MUTEX_FLAG_HANDOFF);
	current = &tasks[2]; kd_mutex_unlock(&lock);
	assert(wb.state == KD_OWNED_MUTEX_GRANTED && !kd_mutex_trylock(&lock));
	current = &tasks[1]; assert(kd_owned_mutex_pickup(&lock, &wb));
	assert(!kd_owned_mutex_pickup(&lock, &wb));
	assert(atomic_long_read(&lock.owner) == (unsigned long)current);
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* An unstarted delegate becomes SELF; neither it nor a younger waiter
	 * can execute until the directed owner's acquire pickup succeeds. */
	reset(); kd_mutex_lock(&lock); publish(&wb, 1, KD_OWNED_MUTEX_DELEGATE);
	publish(&wc, 2, KD_OWNED_MUTEX_SELF);
	current = &tasks[0]; kd_mutex_unlock(&lock);
	assert(wb.kind == KD_OWNED_MUTEX_SELF && wb.state == KD_OWNED_MUTEX_GRANTED);
	current = &tasks[2]; assert(!kd_mutex_trylock(&lock));
	assert(!kd_owned_mutex_pickup(&lock, &wc));
	current = &tasks[1]; assert(kd_owned_mutex_pickup(&lock, &wb));
	assert(lock.wait_list.next == &wc.list);
	kd_owned_mutex_release(&lock);
	current = &tasks[2]; assert(kd_owned_mutex_pickup(&lock, &wc));
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	reset(); wb.task = current; wb.kind = KD_OWNED_MUTEX_DELEGATE;
	assert(kd_owned_mutex_publish(&lock, &wb) && list_empty(&wb.list));
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* The owner may fast-release after the under-lock retry, before the
	 * publisher sets WAITERS. A delegate must acquire instead of stranding. */
	reset(); kd_mutex_lock(&lock); current = &tasks[1];
	wb.task = current; wb.kind = KD_OWNED_MUTEX_DELEGATE;
	release_before_waiters = true;
	assert(kd_owned_mutex_publish(&lock, &wb));
	assert(!release_before_waiters && list_empty(&wb.list));
	assert(atomic_long_read(&lock.owner) == (unsigned long)current);
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* Actual production SELF enqueue/state/schedule/remove sequence. */
	reset(); kd_mutex_lock(&lock); current = &tasks[1];
	schedule_action = release_from_owner;
	kd_mutex_lock(&lock);
	assert(schedules == 1 && !pin_count && current->state == TASK_RUNNING);
	assert(atomic_long_read(&lock.owner) == (unsigned long)current);
	kd_mutex_unlock(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* need_resched may schedule before publication, then acquire cleanly. */
	reset(); kd_mutex_lock(&lock); current = &tasks[1]; resched = true;
	schedule_action = release_from_owner; kd_mutex_lock(&lock);
	assert(schedules == 2 && !pin_count && list_empty(&lock.wait_list));
	kd_mutex_unlock(&lock);

	/* Exercise the production OSQ entry/exit branch without replacing any
	 * mutex code; private OSQ races require the separate live kernel test. */
	reset(); kd_mutex_lock(&lock); tasks[0].on_cpu = 1;
	current = &tasks[1]; osq_action = release_for_spinner;
	kd_mutex_lock(&lock);
	assert(osq_locks == 1 && osq_unlocks == 1 && !pin_count);
	kd_mutex_unlock(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* Releasing ordinary B is not a batching boundary while explicit outer
	 * A remains held, even though B was the final tracked ordinary hold. */
	{
		struct kd_mutex outer;
		int before;

		reset(); kd_mutex_init(&outer);
		assert(kd_owned_mutex_trylock_fast(&outer));
		assert(!current->owned_holds);
		kd_mutex_lock(&lock); assert(current->owned_holds == 1);
		publish(&wb, 1, KD_OWNED_MUTEX_DELEGATE);
		current = &tasks[0]; combine_handles = true; before = combine_calls;
		kd_mutex_unlock(&lock);
		assert(combine_calls == before && !current->owned_holds);
		assert(kd_owned_mutex_owned(&outer, current));
		assert(wb.kind == KD_OWNED_MUTEX_SELF && wb.state == KD_OWNED_MUTEX_GRANTED);
		current = &tasks[1]; assert(kd_owned_mutex_pickup(&lock, &wb));
		assert(!kd_mutex_trylock(&outer));
		current = &tasks[0]; kd_owned_mutex_outer_unlock_v1(&outer);
		current = &tasks[1]; assert(kd_mutex_trylock(&outer));
		kd_mutex_unlock(&outer);
		kd_owned_mutex_outer_unlock_v1(&lock);
		assert(kd_owned_mutex_is_idle(&outer) && kd_owned_mutex_is_idle(&lock));
	}

	reset(); kd_owned_mutex_lock_self(&lock); publish(&wb, 1, KD_OWNED_MUTEX_DELEGATE);
	current = &tasks[0]; combine_handles = true;
	{
		int before = combine_calls;

		kd_owned_mutex_outer_unlock_v1(&lock);
		assert(combine_calls == before + 1);
	}
	current = &tasks[1]; assert(kd_owned_mutex_pickup(&lock, &wb));
	combine_handles = false; kd_owned_mutex_outer_unlock_v1(&lock);
	assert(kd_owned_mutex_is_idle(&lock)); reset();
	puts("[PASS] owned mutex layout, SELF barging/handoff, typed FIFO, pickup, sleep, OSQ branch and wake lifetime");
	return 0;
}
