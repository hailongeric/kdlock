/* SPDX-License-Identifier: GPL-2.0 */
/* Actual queue/admission/owner attempts with deterministic primitive services.
 * No translated body, remote executor or concurrent scheduler is modeled. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

typedef uint32_t u32;
typedef uint64_t u64;
typedef long atomic_long_t;
typedef int atomic_t;
typedef struct { bool valid, held; } raw_spinlock_t;
struct optimistic_spin_queue { int tail; };
struct wake_q_node { struct wake_q_node *next; };
struct task_struct {
	struct wake_q_node wake_q;
	bool ordinary, fatal;
	unsigned int refs, wakes;
};
struct wake_q_head { struct wake_q_node *first, **lastp; };
#define U64_MAX UINT64_MAX
#define TASK_RUNNING 0U
#define TASK_UNINTERRUPTIBLE 1U
#define TASK_INTERRUPTIBLE 2U
#define TASK_KILLABLE 4U
#define WAKE_Q_TAIL ((struct wake_q_node *)1UL)
#define DEFINE_WAKE_Q(name) struct wake_q_head name = { WAKE_Q_TAIL, &(name).first }
#define __aligned(n) __attribute__((aligned(n)))
#define ATOMIC_INIT(n) (n)
#define ATOMIC_LONG_INIT(n) (n)
#define OSQ_LOCK_UNLOCKED { 0 }
#define __RAW_SPIN_LOCK_UNLOCKED(name) { true, false }
#define BUG_ON(value) assert(!(value))
#define BUG() assert(false)
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define WRITE_ONCE(value, next) __atomic_store_n(&(value), (next), __ATOMIC_RELAXED)
#define smp_store_release(ptr, value) __atomic_store_n((ptr), (value), __ATOMIC_RELEASE)
#define lockdep_assert_held(guard) assert((guard)->valid && (guard)->held)
#define DEFINE_PER_CPU(type, name) type name
#define this_cpu_ptr(ptr) (ptr)
#define cmpxchg_relaxed(ptr, old, next) ({ \
	__typeof__(*(ptr)) expected = (old); \
	__atomic_compare_exchange_n((ptr), &expected, (next), false, \
				   __ATOMIC_RELAXED, __ATOMIC_RELAXED); expected; })
#define cmpxchg(ptr, old, next) ({ \
	__typeof__(*(ptr)) expected = (old); \
	__atomic_compare_exchange_n((ptr), &expected, (next), false, \
				   __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); expected; })
static bool irq_disabled;
static unsigned int pins, held_guards, pauses, schedules, cases, head_wakes;
static unsigned int scheduler_state;
static struct task_struct origin, other_origin, executor, holder;
static struct task_struct *current;
#define local_irq_save(flags) do { (flags) = irq_disabled; irq_disabled = true; } while (0)
#define local_irq_restore(flags) do { irq_disabled = (flags); } while (0)
static void preempt_disable(void) { ++pins; }
static void preempt_enable(void) { assert(pins); --pins; }
static void smp_mb__before_atomic(void) { __atomic_thread_fence(__ATOMIC_SEQ_CST); }
static bool signal_pending_state(unsigned int state, struct task_struct *task)
{ return state == TASK_INTERRUPTIBLE ? task->ordinary || task->fatal : state == TASK_KILLABLE && task->fatal; }
static bool signal_pending(struct task_struct *task) { return task->ordinary || task->fatal; }
static void get_task_struct(struct task_struct *task) { assert(task->refs); ++task->refs; }
static void raw_spin_lock_init(raw_spinlock_t *guard) { *guard = (raw_spinlock_t) { true, false }; }
static unsigned long _raw_spin_lock_irqsave(raw_spinlock_t *guard)
{
	unsigned long old = irq_disabled;
	assert(guard->valid && !guard->held);
	irq_disabled = true; guard->held = true; ++held_guards;
	return old;
}
static void _raw_spin_unlock_irqrestore(raw_spinlock_t *guard, unsigned long flags)
{
	assert(guard->valid && guard->held && held_guards && irq_disabled);
	guard->held = false; --held_guards; irq_disabled = flags;
}
static void wake_up_q(struct wake_q_head *wake)
{
	struct wake_q_node *node = wake->first;
	assert(!held_guards);
	while (node != WAKE_Q_TAIL) {
		struct wake_q_node *next = node->next;
		struct task_struct *task = (void *)((char *)node - offsetof(struct task_struct, wake_q));
		assert(task->refs > 1); node->next = NULL; --task->refs; ++task->wakes; node = next;
	}
	wake->first = WAKE_Q_TAIL; wake->lastp = &wake->first;
}
static long atomic_long_read(const atomic_long_t *p) { return READ_ONCE(*p); }
static long atomic_long_read_acquire(const atomic_long_t *p)
{ return __atomic_load_n(p, __ATOMIC_ACQUIRE); }
static long atomic_long_cmpxchg(atomic_long_t *p, long old, long next)
{ return cmpxchg(p, old, next); }
static long atomic_long_xchg(atomic_long_t *p, long next)
{ return __atomic_exchange_n(p, next, __ATOMIC_SEQ_CST); }
static long atomic_long_inc_return(atomic_long_t *p)
{ return __atomic_add_fetch(p, 1, __ATOMIC_SEQ_CST); }
static long atomic_long_dec_return(atomic_long_t *p)
{ return (long)__atomic_sub_fetch(p, 1, __ATOMIC_SEQ_CST); }
static void atomic_long_or(unsigned long bits, atomic_long_t *p) { *p |= bits; }
static void atomic_long_andnot(unsigned long bits, atomic_long_t *p) { *p &= ~bits; }
static bool atomic_long_try_cmpxchg_acquire(atomic_long_t *p, unsigned long *old, unsigned long next)
{ return __atomic_compare_exchange_n(p, old, next, false, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED); }
static bool atomic_long_try_cmpxchg_release(atomic_long_t *p, unsigned long *old, unsigned long next)
{ return __atomic_compare_exchange_n(p, old, next, false, __ATOMIC_RELEASE, __ATOMIC_RELAXED); }
static void might_sleep(void) { assert(!held_guards && !pins); }
static void set_current_state(unsigned int state) { scheduler_state = state; }
static void __set_current_state(unsigned int state) { scheduler_state = state; }
static bool need_resched(void) { return false; }
static void cpu_relax(void) { assert(++pauses < 100); }
static void schedule_timeout(unsigned long ticks)
{ assert(ticks == 1 && !held_guards && !pins && ++schedules < 3); }

#include "admission_types.h"
static struct kd_wait_queue kd_mutex_wait_queue(struct kd_mutex *lock)
{ return kd_wait_queue_view(&lock->wait_lock, &lock->wait_head); }
#define KD_WAITERS 1UL
#define KD_HANDOFF 2UL
#define KD_PICKUP 4UL
#define KD_FLAGS 7UL
#include "admission_physical.h"
static void kd_mutex_wake_head_locked(struct kd_mutex *lock)
{ lockdep_assert_held(&lock->wait_lock); ++head_wakes; }
static void kd_mutex_local_unlock(struct kd_mutex *lock)
{
	assert(!held_guards && (lock->owner & ~KD_FLAGS) == (unsigned long)current);
	assert(!(lock->owner & KD_PICKUP));
	lock->owner &= KD_WAITERS;
}
static void kd_mutex_api_unlock(struct kd_mutex *lock) { kd_mutex_local_unlock(lock); }
#include "admission_production.h"

struct invocation { struct kd_wait_request request; struct kd_admission admission; };
static u64 next_generation;
static void reset_tasks(void)
{
	assert(!held_guards && !pins && !irq_disabled);
	assert(!origin.refs || (origin.refs == 1 && other_origin.refs == 1 &&
			       executor.refs == 1 && holder.refs == 1));
	origin = other_origin = executor = holder = (struct task_struct) { .refs = 1 };
	current = &executor; pauses = schedules = 0; scheduler_state = TASK_RUNNING;
}
static void init_sem(struct kd_rwsem *sem)
{ memset(sem, 0, sizeof(*sem)); raw_spin_lock_init(&sem->gate.wait_lock); }
static void init_mutex(struct kd_mutex *lock)
{ memset(lock, 0, sizeof(*lock)); raw_spin_lock_init(&lock->wait_lock); }
static void init_invocation(struct invocation *item, void *object, enum kd_admission_kind kind,
			   struct task_struct *logical, unsigned int state, bool delegate)
{
	memset(item, 0, sizeof(*item));
	kd_wait_request_init(&item->request, &item->request, ++next_generation,
		logical, delegate ? logical : current, state, delegate, NULL);
	kd_admission_init(&item->admission, &item->request, kind, object, NULL);
}
static enum kd_wait_decision publish_step(struct invocation *item)
{
	struct kd_admission *a = &item->admission;
	unsigned long flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	kd_admission_publish_locked(a);
	enum kd_wait_decision result = kd_admission_step_locked(a);
	_raw_spin_unlock_irqrestore(&a->gate->wait_lock, flags);
	return result;
}
static void retain_execution(struct invocation *item)
{
	struct kd_admission *a = &item->admission;
	unsigned long flags = _raw_spin_lock_irqsave(&a->gate->wait_lock);
	kd_admission_transfer_owned_locked(a);
	raw_spinlock_t *old = kd_wait_rebind_locked(&item->request, a->retained_guard);
	_raw_spin_unlock_irqrestore(old, flags);
	flags = _raw_spin_lock_irqsave(a->retained_guard);
	kd_wait_set_state_locked(&item->request, KD_WAIT_EXECUTING);
	_raw_spin_unlock_irqrestore(a->retained_guard, flags);
}
static void finish_execution(struct invocation *item)
{
	struct kd_admission *a = &item->admission;
	kd_admission_release(a);
	unsigned long flags = _raw_spin_lock_irqsave(a->retained_guard);
	kd_wait_set_state_locked(&item->request, KD_WAIT_RELEASED);
	kd_wait_set_state_locked(&item->request, KD_WAIT_RETURN_ACK);
	kd_wait_set_state_locked(&item->request, KD_WAIT_RETIRED);
	_raw_spin_unlock_irqrestore(a->retained_guard, flags);
}
static void finish_cancel(struct invocation *item)
{
	assert(item->request.state == KD_WAIT_CANCEL_ACK && !item->admission.committed);
	assert(!item->request.memberships && !item->request.acquisition &&
	       !item->request.selection && !item->request.cleanup);
	assert(item->request.guard == item->admission.retained_guard);
	unsigned long flags = _raw_spin_lock_irqsave(item->request.guard);
	kd_wait_set_state_locked(&item->request, KD_WAIT_RETIRED);
	_raw_spin_unlock_irqrestore(item->request.guard, flags);
}
static void test_ready_before_fatal(void)
{
	for (unsigned int kind = 0; kind < 2; ++kind) {
		struct kd_rwsem sem; struct invocation item;
		reset_tasks(); init_sem(&sem); origin.fatal = true;
		init_invocation(&item, kind ? (void *)&sem : (void *)&sem.gate,
			kind ? KD_ADMISSION_RWSEM_WRITE : KD_ADMISSION_MUTEX,
			&origin, TASK_KILLABLE, true);
		sem.gate.owner = (unsigned long)&origin | KD_PICKUP | KD_WAITERS;
		assert(publish_step(&item) == KD_WAIT_GRANTED);
		assert(item.admission.committed && item.request.state == KD_WAIT_ACQUIRED);
		assert((sem.gate.owner & ~KD_FLAGS) == (unsigned long)current && !(sem.gate.owner & KD_PICKUP));
		if (kind) assert((long)sem.admission == -1 && sem.selected_identity == item.request.identity);
		retain_execution(&item); finish_execution(&item);
		assert(!sem.admission && !sem.gate.owner && !sem.gate.wait_head); ++cases;
	}
}
static void signal_origin(void *argument)
{
	struct invocation *item = argument;
	assert((item->admission.gate->owner & ~KD_FLAGS) == (unsigned long)&holder);
	assert(scheduler_state == TASK_UNINTERRUPTIBLE);
	item->request.logical_origin->fatal = true;
}
static void test_queued_return_before_holder(void)
{
	struct kd_mutex lock; struct invocation item; unsigned int prefix = 0;
	reset_tasks(); init_mutex(&lock); lock.owner = (unsigned long)&holder;
	init_invocation(&item, &lock, KD_ADMISSION_MUTEX, &origin, TASK_KILLABLE, true);
	int result = kd_admission_wait(&item.admission, signal_origin, &item);
	if (!result) ++prefix;
	assert(result == -EINTR && !prefix && !lock.wait_head);
	assert((lock.owner & ~KD_FLAGS) == (unsigned long)&holder);
	assert(!item.admission.gate_held && !schedules); finish_cancel(&item);
	current = &holder; kd_mutex_local_unlock(&lock); current = &executor;
	assert(!lock.owner); ++cases;
}
static void test_reader_pickup_cancel_and_successor(void)
{
	struct kd_rwsem sem; struct invocation item, next; unsigned int prefix = 0;
	reset_tasks(); init_sem(&sem); sem.readers = 1; origin.fatal = true;
	init_invocation(&item, &sem, KD_ADMISSION_RWSEM_WRITE, &origin, TASK_KILLABLE, true);
	init_invocation(&next, &sem, KD_ADMISSION_RWSEM_WRITE, &other_origin, TASK_KILLABLE, true);
	sem.gate.owner = (unsigned long)&origin | KD_PICKUP | KD_WAITERS;
	unsigned long flags = _raw_spin_lock_irqsave(&sem.gate.wait_lock);
	kd_admission_publish_locked(&item.admission); kd_admission_publish_locked(&next.admission);
	assert(kd_admission_step_locked(&item.admission) == KD_WAIT_CLEANUP_REQUIRED);
	assert(item.request.state == KD_WAIT_CANCELING && !item.admission.committed);
	assert(item.request.cleanup == &item.admission.cleanup && item.admission.phase_held);
	assert(sem.selected_identity == item.request.identity && sem.phase_generation == item.admission.phase_generation);
	assert(!kd_wait_cancel_ack_locked(&item.request) && sem.reader_drain.head == &item.admission.condition);
	u64 generation = sem.phase_generation;
	_raw_spin_unlock_irqrestore(&sem.gate.wait_lock, flags);
	int result = kd_admission_wait(&item.admission, NULL, NULL);
	if (!result) ++prefix;
	assert(result == -EINTR && !prefix && sem.readers == 1 && !sem.admission);
	assert(sem.selected_kind == KD_RWSEM_PHASE_NONE && !sem.selected_owner && !sem.selected_identity);
	assert(sem.phase_generation == generation && !sem.reader_drain.head);
	assert(sem.gate.wait_head == &next.admission.member && next.request.state == KD_WAIT_QUEUED);
	finish_cancel(&item);
	flags = _raw_spin_lock_irqsave(&sem.gate.wait_lock);
	assert(kd_admission_step_locked(&next.admission) == KD_WAIT_PENDING);
	assert(next.admission.phase_held && sem.phase_generation == generation + 1);
	assert(sem.selected_identity == next.request.identity && sem.readers == 1);
	sem.readers = 0;
	assert(kd_admission_step_locked(&next.admission) == KD_WAIT_GRANTED);
	_raw_spin_unlock_irqrestore(&sem.gate.wait_lock, flags);
	retain_execution(&next); finish_execution(&next); ++cases;
}
static void test_origin_signals(void)
{
	for (unsigned int interruptible = 0; interruptible < 2; ++interruptible) {
		struct kd_rwsem sem; struct invocation item;
		reset_tasks(); init_sem(&sem); sem.readers = 1;
		origin.ordinary = true; executor.fatal = true;
		init_invocation(&item, &sem, KD_ADMISSION_RWSEM_WRITE, &origin,
			interruptible ? TASK_INTERRUPTIBLE : TASK_KILLABLE, true);
		enum kd_wait_decision decision = publish_step(&item);
		if (!interruptible) {
			assert(decision == KD_WAIT_PENDING && item.request.state == KD_WAIT_SELECTED_DRAINING);
			origin.fatal = true;
		} else assert(decision == KD_WAIT_CLEANUP_REQUIRED);
		assert(kd_admission_wait(&item.admission, NULL, NULL) == -EINTR);
		assert(sem.readers == 1 && !sem.admission && !sem.gate.owner);
		finish_cancel(&item); ++cases;
	}
}
static void test_nested_identity_and_parent(void)
{
	struct kd_mutex parent_lock, child_lock; struct invocation parent, child;
	reset_tasks(); init_mutex(&parent_lock); init_mutex(&child_lock);
	init_invocation(&parent, &parent_lock, KD_ADMISSION_MUTEX, &origin, TASK_KILLABLE, true);
	assert(publish_step(&parent) == KD_WAIT_GRANTED); retain_execution(&parent);
	init_invocation(&child, &child_lock, KD_ADMISSION_MUTEX, &origin, TASK_KILLABLE, false);
	child.request.context = &parent;
	assert(child.request.identity != parent.request.identity && child.request.generation != parent.request.generation);
	child_lock.owner = (unsigned long)&holder; origin.fatal = true;
	assert(kd_admission_wait(&child.admission, NULL, NULL) == -EINTR); finish_cancel(&child);
	assert(parent.request.state == KD_WAIT_EXECUTING && parent.admission.committed);
	assert((unsigned long)parent_lock.owner == (unsigned long)current &&
	       (unsigned long)child_lock.owner == (unsigned long)&holder);
	assert(child.request.context == &parent); /* Runtime anchor references remain a separate check. */
	finish_execution(&parent);
	current = &holder; kd_mutex_local_unlock(&child_lock); current = &executor;
	assert(!parent_lock.owner && !child_lock.owner); ++cases;
}
static void test_local_child_and_early_parent_release(void)
{
	struct kd_mutex parent_lock, child_lock; struct invocation parent, child;
	reset_tasks(); init_mutex(&parent_lock); init_mutex(&child_lock);
	init_invocation(&parent, &parent_lock, KD_ADMISSION_MUTEX, &origin, TASK_KILLABLE, true);
	assert(publish_step(&parent) == KD_WAIT_GRANTED); retain_execution(&parent);
	init_invocation(&child, &child_lock, KD_ADMISSION_MUTEX, &origin, TASK_KILLABLE, false);
	current = &holder;
	assert(publish_step(&child) == KD_WAIT_PENDING);
	assert(child.request.state == KD_WAIT_QUEUED && !child.request.selection);
	assert(!(child_lock.owner & ~KD_FLAGS) && (child_lock.owner & KD_WAITERS));
	current = &executor; origin.fatal = true;
	assert(!kd_admission_wait(&child.admission, NULL, NULL)); retain_execution(&child);
	finish_execution(&parent);
	assert(child.request.state == KD_WAIT_EXECUTING && child.admission.committed);
	assert((unsigned long)child_lock.owner == (unsigned long)current);
	finish_execution(&child); assert(!parent_lock.owner && !child_lock.owner); ++cases;
}
int main(void)
{
	test_ready_before_fatal(); test_queued_return_before_holder();
	test_reader_pickup_cancel_and_successor(); test_origin_signals();
	test_nested_identity_and_parent(); test_local_child_and_early_parent_release();
	assert(!held_guards && !pins && !irq_disabled && scheduler_state == TASK_RUNNING);
	assert(origin.refs == 1 && other_origin.refs == 1 && executor.refs == 1 && holder.refs == 1);
	printf("PASS production canonical admission: %u cases; actual queue, phase, PICKUP and cancellation paths; deterministic primitives only\n", cases);
	return 0;
}
