/* Deterministic scheduler/wake fixture for the real owned mutex core. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
unsigned int owned_mutex_reuse_spins;

bool owned_mutex_self_route;

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
static struct task_struct tasks[4];
static struct task_struct *current;
static int pin_count, schedules, spins, combine_calls, osq_locks, osq_unlocks;
static bool resched, release_before_waiters;
static void (*schedule_action)(void), (*osq_action)(void);
static void (*store_action)(u32 *);
static void (*before_wait_lock)(raw_spinlock_t *);
static void (*before_release_cas)(atomic_long_t *, unsigned long *, unsigned long);
static void (*before_list_add)(struct list_head *, struct list_head *);

#define CONFIG_X86_64 1
#define CONFIG_MUTEX_SPIN_ON_OWNER 1
#undef static_assert
#define static_assert(expr, ...) _Static_assert(expr, #expr)
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define noinline __attribute__((noinline))
#define notrace
#define likely(x) (x)
#define unlikely(x) (x)
#define BUG_ON(x) assert(!(x))
#define BUG() assert(false)
#define EXPORT_SYMBOL_GPL(x)
#define module_param(name, type, permissions)
#define MODULE_PARM_DESC(name, text)
#define TASK_RUNNING 0
#define TASK_UNINTERRUPTIBLE 2
#define OSQ_UNLOCKED_VAL 0
#define ATOMIC_LONG_INIT(x) { (x) }
#define OSQ_LOCK_UNLOCKED { { 0 } }
#define __RAW_SPIN_LOCK_UNLOCKED(name) { 0 }
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x, v) __atomic_store_n(&(x), (v), __ATOMIC_RELAXED)
#define smp_store_release(p, v) do { \
	__atomic_store_n((p), (v), __ATOMIC_RELEASE); \
	if (store_action) store_action(p); \
} while (0)
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define smp_mb__before_atomic() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define smp_mb__after_atomic() __atomic_thread_fence(__ATOMIC_SEQ_CST)
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
static bool release_cas(atomic_long_t *p, unsigned long *old, unsigned long value)
{
	if (before_release_cas)
		before_release_cas(p, old, value);
	return __atomic_compare_exchange_n(&p->counter, old, value, false,
					   __ATOMIC_RELEASE, __ATOMIC_RELAXED);
}
#define atomic_long_try_cmpxchg_release release_cas
#define LIST_HEAD_INIT(name) { &(name), &(name) }
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define list_first_entry(p, type, member) container_of((p)->next, type, member)
static void INIT_LIST_HEAD(struct list_head *p) { p->next = p->prev = p; }
static bool list_empty(const struct list_head *p) { return p->next == p; }
static void list_add_tail(struct list_head *p, struct list_head *head)
{
	if (before_list_add)
		before_list_add(p, head);
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
	if (before_wait_lock)
		before_wait_lock(p);
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
bool kd_owned_osq_lock_bounded(struct optimistic_spin_queue *lock, unsigned int *remaining)
{ (void)lock;(void)remaining;assert(false);return false; }
bool kd_owned_osq_trylock(struct optimistic_spin_queue *lock)
{
	if (atomic_read(&lock->tail))
		return false;
	return kd_owned_osq_lock(lock);
}
void kd_owned_osq_unlock(struct optimistic_spin_queue *lock)
{
	assert(pin_count && atomic_read(&lock->tail));
	osq_unlocks++; atomic_set(&lock->tail, 0);
}

static struct kd_mutex lock;
static DEFINE_KD_MUTEX(static_lock);
static struct kd_owned_mutex_waiter wb, wc;
static u32 wb_outcome, wc_outcome;
static int immediate_pickups;
static void reset(void)
{
	assert(!pin_count);
	for (unsigned int i = 0; i < 4; i++) {
		assert(!tasks[i].refs && !tasks[i].wake_q.next && !tasks[i].owned_holds);
		tasks[i].state = TASK_RUNNING; tasks[i].on_cpu = 0;
	}
	current = &tasks[0]; resched = false; combine_handles = false;
	release_before_waiters = false;
	store_action = NULL;
	before_wait_lock = NULL; before_release_cas = NULL; before_list_add = NULL;
	route_borrowed = false;
	schedule_action = osq_action = NULL; spins = 0;
	wb.outcome = &wb_outcome; wc.outcome = &wc_outcome;
	kd_mutex_init(&lock);
}
static void publish(struct kd_owned_mutex_waiter *w, unsigned int task, u32 kind)
{
	current = &tasks[task]; w->task = current; w->kind = kind;
	w->outcome = kind == KD_OWNED_MUTEX_SELF ? &w->state :
		(w == &wb ? &wb_outcome : &wc_outcome);
	assert(!kd_owned_mutex_publish(&lock, w));
	assert(*w->outcome == KD_OWNED_MUTEX_QUEUED && !list_empty(&w->list));
}
static void pickup_self(struct kd_owned_mutex_waiter *waiter)
{
	/* The normal stack SELF loop still removes its own queued entry. */
	assert(waiter->kind == KD_OWNED_MUTEX_SELF && waiter->outcome == &waiter->state);
	raw_spin_lock(&lock.wait_lock);
	assert(!kd_owned_mutex_trylock_common(&lock, false));
	kd_owned_mutex_remove_waiter(&lock, waiter);
	raw_spin_unlock(&lock.wait_lock);
}
static void pickup_and_reuse_at_publication(u32 *outcome)
{
	struct task_struct *releaser = current;

	assert(outcome == &wb_outcome && *outcome == KD_OWNED_MUTEX_GRANTED);
	assert(lock.wait_lock.locked && tasks[1].refs == 1);
	assert(list_empty(&wb.list));
	store_action = NULL;
	current = &tasks[1];
	assert(kd_owned_mutex_pickup(&lock, &wb));
	assert(!kd_owned_mutex_pickup(&lock, &wb));
	assert(kd_owned_mutex_owned(&lock, current));
	memset(&wb, 0xaf, sizeof(wb));
	immediate_pickups++;
	current = releaser;
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

static void check_guard_before_link(struct list_head *node, struct list_head *head)
{
	assert(node == &wb.list && head == &lock.wait_list && lock.wait_lock.locked);
	assert((lock.owner.counter & KD_OWNED_MUTEX_FLAGS) ==
	       (KD_OWNED_MUTEX_FLAG_WAITERS | KD_OWNED_MUTEX_FLAG_DELEGATION));
	assert(list_empty(node));
	before_list_add = NULL;
}

static void new_owner_before_old_wake(raw_spinlock_t *queue_lock)
{
	struct task_struct *old = current;

	before_wait_lock = NULL;
	assert(queue_lock == &lock.wait_lock && !queue_lock->locked);
	assert(lock.owner.counter == KD_OWNED_MUTEX_FLAG_WAITERS);
	current = &tasks[2]; assert(kd_mutex_trylock(&lock));
	current = &tasks[1];
	assert(kd_owned_mutex_trylock_common(&lock, true) == &tasks[2]);
	publish(&wc, 3, KD_OWNED_MUTEX_DELEGATE);
	current = old;
}

static void publish_during_release(atomic_long_t *word, unsigned long *expected,
				  unsigned long next)
{
	struct task_struct *old = current;

	/* Skip the first uncontended-unlock probe; race the actual flags-only
	 * release after it has observed a SELF-only queue. */
	if (!(*expected & KD_OWNED_MUTEX_FLAG_WAITERS))
		return;
	assert(word == &lock.owner && next == KD_OWNED_MUTEX_FLAG_WAITERS);
	before_release_cas = NULL;
	publish(&wc, 3, KD_OWNED_MUTEX_DELEGATE);
	current = old;
}

static void finish_self_then_delegate(void)
{
	current = &tasks[1]; pickup_self(&wb);
	assert(lock.owner.counter & KD_OWNED_MUTEX_FLAG_DELEGATION);
	kd_owned_mutex_outer_unlock_v1(&lock);
	current = &tasks[3]; assert(kd_owned_mutex_pickup(&lock, &wc));
	assert(lock.owner.counter == (unsigned long)current);
	kd_owned_mutex_outer_unlock_v1(&lock);
	assert(kd_owned_mutex_is_idle(&lock));
}

static void check_early_release_guard(void)
{
	int before;

	/* A published delegate is guarded before its link becomes visible. The
	 * final detached grant clears the guard but retains exact-task PICKUP. */
	reset(); kd_mutex_lock(&lock);
	before_list_add = check_guard_before_link;
	publish(&wb, 1, KD_OWNED_MUTEX_DELEGATE);
	assert(!before_list_add);
	current = &tasks[0]; kd_mutex_unlock(&lock);
	assert(wb_outcome == KD_OWNED_MUTEX_GRANTED && list_empty(&wb.list));
	assert(lock.owner.counter == ((unsigned long)&tasks[1] | KD_OWNED_MUTEX_FLAG_PICKUP));
	current = &tasks[1]; assert(kd_owned_mutex_pickup(&lock, &wb));
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* The guard is deliberately sticky when only SELF remains in the suffix;
	 * last-waiter acquisition, not kind inspection, finally clears it. */
	reset(); kd_mutex_lock(&lock);
	publish(&wb, 1, KD_OWNED_MUTEX_DELEGATE); publish(&wc, 2, KD_OWNED_MUTEX_SELF);
	current = &tasks[0]; kd_mutex_unlock(&lock);
	assert(lock.owner.counter & KD_OWNED_MUTEX_FLAG_DELEGATION);
	current = &tasks[1]; assert(kd_owned_mutex_pickup(&lock, &wb));
	kd_owned_mutex_outer_unlock_v1(&lock);
	assert(lock.owner.counter == (KD_OWNED_MUTEX_FLAG_WAITERS | KD_OWNED_MUTEX_FLAG_DELEGATION));
	current = &tasks[2]; pickup_self(&wc);
	assert(lock.owner.counter == (unsigned long)current);
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* Fast release can beat the guard publication, so the second acquisition
	 * retry still has to consume ownerless flags and remove this request. */
	reset(); kd_mutex_lock(&lock);
	current = &tasks[1]; wb.task = current; wb.kind = KD_OWNED_MUTEX_DELEGATE;
	release_before_waiters = true;
	assert(kd_owned_mutex_publish(&lock, &wb));
	assert(!release_before_waiters && list_empty(&wb.list));
	assert(lock.owner.counter == (unsigned long)current);
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* The old releaser has no authority after clearing owner. A new owner,
	 * HANDOFF request and delegate may all appear before its queue lock. */
	reset(); kd_owned_mutex_lock_self(&lock);
	publish(&wb, 1, KD_OWNED_MUTEX_SELF); current = &tasks[0];
	before = combine_calls; before_wait_lock = new_owner_before_old_wake;
	kd_owned_mutex_outer_unlock_v1(&lock);
	assert(combine_calls == before && !before_wait_lock);
	assert(lock.owner.counter == ((unsigned long)&tasks[2] | KD_OWNED_MUTEX_FLAG_WAITERS |
	       KD_OWNED_MUTEX_FLAG_HANDOFF | KD_OWNED_MUTEX_FLAG_DELEGATION));
	assert(wb.state == KD_OWNED_MUTEX_QUEUED);
	current = &tasks[2]; kd_mutex_unlock(&lock);
	finish_self_then_delegate();

	/* A guard arriving between the unguarded read and release CAS prevents
	 * that release and preserves the flag through the guarded SELF wake. */
	reset(); kd_mutex_lock(&lock);
	publish(&wb, 1, KD_OWNED_MUTEX_SELF); current = &tasks[0];
	before_release_cas = publish_during_release; kd_mutex_unlock(&lock);
	assert(!before_release_cas);
	assert(lock.owner.counter == (KD_OWNED_MUTEX_FLAG_WAITERS | KD_OWNED_MUTEX_FLAG_DELEGATION));
	finish_self_then_delegate();

	/* A local-first refusal is already committed to SELF. A running owner
	 * must not cause this continuation to repeat the initial OSQ phase. */
	reset(); kd_mutex_lock(&lock); tasks[0].on_cpu = 1; current = &tasks[1];
	before = osq_locks; schedule_action = release_from_owner;
	osq_action = release_for_spinner;
	kd_owned_mutex_lock_self_wait(&lock);
	assert(osq_locks == before && !pin_count && kd_owned_mutex_owned(&lock, current));
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));
	reset();
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
	current = &tasks[1]; pickup_self(&wb);
	assert(atomic_long_read(&lock.owner) == (unsigned long)current);
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* An unstarted delegate becomes SELF; neither it nor a younger waiter
	 * can execute until the directed owner's acquire pickup succeeds. */
	reset(); kd_mutex_lock(&lock); publish(&wb, 1, KD_OWNED_MUTEX_DELEGATE);
	publish(&wc, 2, KD_OWNED_MUTEX_SELF);
	current = &tasks[0]; kd_mutex_unlock(&lock);
	assert(wb.kind == KD_OWNED_MUTEX_SELF && wb_outcome == KD_OWNED_MUTEX_GRANTED);
	assert(list_empty(&wb.list));
	current = &tasks[2]; assert(!kd_mutex_trylock(&lock));
	assert(!kd_owned_mutex_pickup(&lock, &wc));
	current = &tasks[1];
	wb_outcome = KD_OWNED_MUTEX_QUEUED;
	assert(!kd_owned_mutex_pickup(&lock, &wb));
	wb_outcome = KD_OWNED_MUTEX_GRANTED;
	{
		unsigned long granted_owner = atomic_long_read(&lock.owner);

		atomic_long_set(&lock.owner, (unsigned long)&tasks[2] |
				KD_OWNED_MUTEX_FLAG_WAITERS | KD_OWNED_MUTEX_FLAG_PICKUP);
		assert(!kd_owned_mutex_pickup(&lock, &wb));
		atomic_long_set(&lock.owner, granted_owner);
	}
	assert(kd_owned_mutex_pickup(&lock, &wb));
	assert(lock.wait_list.next == &wc.list);
	kd_owned_mutex_release(&lock);
	current = &tasks[2]; pickup_self(&wc);
	kd_owned_mutex_outer_unlock_v1(&lock); assert(kd_owned_mutex_is_idle(&lock));

	/* Publication is the final request access. Its receiver can acquire and
	 * poison the packet before the releaser drops wait_lock or wakes tasks. */
	reset(); kd_mutex_lock(&lock); publish(&wb, 1, KD_OWNED_MUTEX_DELEGATE);
	current = &tasks[0]; store_action = pickup_and_reuse_at_publication;
	kd_mutex_unlock(&lock);
	assert(immediate_pickups == 1 && !tasks[1].refs && tasks[1].wakes);
	assert(wb.kind == 0xafafafafU && wb.state == 0xafafafafU);
	assert(atomic_long_read(&lock.owner) == (unsigned long)&tasks[1]);
	current = &tasks[1]; kd_owned_mutex_outer_unlock_v1(&lock);
	assert(kd_owned_mutex_is_idle(&lock));

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
		assert(wb.kind == KD_OWNED_MUTEX_SELF && wb_outcome == KD_OWNED_MUTEX_GRANTED);
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
	check_early_release_guard();
	/* A refused local attempt continues under the original pin. Its stack
	 * waiter is consumed before returning; there is no second OSQ pass. */
	reset(); kd_mutex_lock(&lock); current = &tasks[1];
	{
		int before = osq_locks;

		preempt_disable();
		assert(!kd_owned_mutex_try_local_pinned(&lock));
		assert(pin_count == 1 && osq_locks == before);
		schedule_action = release_from_owner;
		kd_owned_mutex_lock_wait_pinned(&lock);
		assert(pin_count == 1 && osq_locks == before);
		assert(kd_owned_mutex_owned(&lock, current) && list_empty(&lock.wait_list));
		preempt_enable();
		kd_owned_mutex_outer_unlock_v1(&lock);
		assert(kd_owned_mutex_is_idle(&lock));
	}
	puts("[PASS] owned mutex layout, SELF barging/handoff, typed FIFO, pickup, sleep, OSQ, guarded release races and wake lifetime");
	return 0;
}
