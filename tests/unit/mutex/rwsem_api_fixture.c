/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>

typedef uint32_t u32;
typedef uint64_t u64;
typedef long atomic_long_t;
typedef int atomic_t;
typedef int raw_spinlock_t;
typedef struct { long words[3]; } wait_queue_head_t;
struct optimistic_spin_queue { int tail; };
struct lock_class_key { int unused; };
#define __aligned(n) __attribute__((aligned(n)))
#define ATOMIC_INIT(n) (n)
#define ATOMIC_LONG_INIT(n) (n)
#define OSQ_LOCK_UNLOCKED { 0 }
#define __RAW_SPIN_LOCK_UNLOCKED(name) 0
#define __WAIT_QUEUE_HEAD_INITIALIZER(name) { { 0 } }
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x, value) (*(volatile __typeof__(x) *)&(x) = (value))
#define BUILD_BUG_ON(x) _Static_assert(!(x), #x)
#define BUG_ON(x) assert(!(x))
#define current ((void *)0x8000UL)
#define KD_RWSEM_LOCAL_WRITER (-1L)
#define KD_ENTRY_ABI_MUTEX_CLOBBER_V1 2
#define TASK_UNINTERRUPTIBLE 1U
#define TASK_INTERRUPTIBLE 2U
#define TASK_KILLABLE 4U
#define DEFINE_LOCK_GUARD_1(...)
#define DEFINE_LOCK_GUARD_1_COND(...)
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)
#include "types.h"
#include "decls.h"

static unsigned int local_calls, delegate_calls, unlocks, releases, prepare_calls;
static int prepare_result;
static int cancel_result;
static unsigned int last_wait_state;
static unsigned long captured_ip;
static struct kd_rwsem *active;
/* This local API fixture has no retained Native service registration. Keep
 * the production route visible and check its exact object/operation inputs. */
static bool kd_exec_native_service_unlock(unsigned long object,
					 enum kd_exec_native_operation operation)
{
	assert(object == (unsigned long)active);
	assert(operation == KD_NATIVE_OPERATION_RWSEM_UP_WRITE ||
	       operation == KD_NATIVE_OPERATION_RWSEM_DOWNGRADE);
	return false;
}
struct kd_wait_queue { raw_spinlock_t *guard; struct kd_wait_node **head; };
struct wake_q_head { bool collected; };
#define DEFINE_WAKE_Q(name) struct wake_q_head name = { false }
static long atomic_long_read(const long *p) { return *p; }
static long atomic_long_xchg(long *p, long n)
{
	long old = *p;

	assert(p == &active->admission && n == 0 && !active->gate.wait_lock);
	assert(active->selected_kind == KD_RWSEM_PHASE_NONE &&
	       !active->selected_owner && !active->selected_identity);
	*p = n;
	return old;
}
static long atomic_long_inc_return(long *p)
{
	assert(p == &active->readers && !*p && active->admission == -1);
	assert(active->gate.owner == (unsigned long)current);
	return ++*p;
}
static bool kd_origin_mutex_owned(struct kd_mutex *lock, void *task)
{ return (unsigned long)lock->owner == (unsigned long)task; }
static struct kd_wait_queue kd_wait_queue_view(raw_spinlock_t *guard,
					       struct kd_wait_node **head)
{
	assert(guard == &active->gate.wait_lock && head == &active->phase_wait.head);
	return (struct kd_wait_queue) { guard, head };
}
static unsigned long _raw_spin_lock_irqsave(raw_spinlock_t *guard)
{
	assert(guard == &active->gate.wait_lock && !*guard);
	assert(!active->gate.owner && unlocks == releases + 1);
	*guard = 1;
	return 0;
}
static void _raw_spin_unlock_irqrestore(raw_spinlock_t *guard, unsigned long flags)
{
	assert(guard == &active->gate.wait_lock && *guard == 1 && !flags);
	*guard = 0;
}
static void kd_wait_collect_wake_locked(struct kd_wait_queue *queue,
				        struct wake_q_head *wake)
{
	assert(*queue->guard == 1 && active->admission == -1 && !wake->collected);
	assert(active->selected_kind == KD_RWSEM_PHASE_NONE &&
	       !active->selected_owner && !active->selected_identity);
	wake->collected = true;
}
static void wake_up_q(struct wake_q_head *wake)
{
	assert(wake->collected && !active->gate.wait_lock && !active->admission);
	assert(!active->gate.owner && unlocks == releases + 1);
	releases++;
}
void kd_mutex_local_unlock(struct kd_mutex *lock)
{
	assert((unsigned long)lock->owner == (unsigned long)current);
	lock->owner = 0;
	unlocks++;
}
void kd_mutex_api_unlock(struct kd_mutex *lock) { kd_mutex_local_unlock(lock); }
void kd_rwsem_init(struct kd_rwsem *sem) { memset(sem, 0, sizeof(*sem)); }
bool kd_rwsem_is_idle(struct kd_rwsem *sem)
{
	return !sem->admission && !sem->readers && !sem->gate.owner &&
		sem->selected_kind == KD_RWSEM_PHASE_NONE &&
		!sem->selected_owner && !sem->selected_identity;
}
void kd_down_write(struct kd_rwsem *sem)
{
	assert(kd_rwsem_is_idle(sem));
	sem->admission = -1;
	sem->gate.owner = (unsigned long)current;
	sem->selected_kind = KD_RWSEM_PHASE_LOCAL;
	sem->selected_owner = current;
	sem->selected_identity = current;
	sem->phase_generation++;
	local_calls++;
}
int kd_down_write_interruptible(struct kd_rwsem *sem)
{
	if (!cancel_result)
		kd_down_write(sem);
	return cancel_result;
}
int kd_down_write_killable(struct kd_rwsem *sem)
{ return kd_down_write_interruptible(sem); }
enum kd_admission_kind { KD_ADMISSION_MUTEX, KD_ADMISSION_RWSEM_WRITE };
int kd_service_capture(void *object, enum kd_admission_kind kind,
	unsigned int state, unsigned long sp, unsigned long ip, unsigned long bp)
{
	struct kd_rwsem *sem = object;

	assert(sem == active && sem->prepared_writes &&
	       kind == KD_ADMISSION_RWSEM_WRITE && sp && ip && bp);
	assert(kd_rwsem_is_idle(sem));
	delegate_calls++;
	captured_ip = ip;
	last_wait_state = state;
	if (state != TASK_UNINTERRUPTIBLE) {
		const unsigned char *success = (const unsigned char *)ip;

		assert(success[0] == 0x31 && success[1] == 0xc0);
		if (cancel_result)
			return cancel_result;
	}
	/* This substitutes the engine's Native fast grant. Actual other-task
	 * selection/execution belongs to the retained service correctness fixture. */
	kd_down_write(sem);
	local_calls--;
	return 0;
}
int kd_mutex_prepare(struct kd_mutex *lock, unsigned long ip, unsigned int abi)
{
	assert(lock == &active->gate && ip && abi == 2);
	prepare_calls++;
	return prepare_result;
}
void kd_mutex_direct_lock_clobber_v1(struct kd_mutex *lock, unsigned long sp,
                                    unsigned long ip, unsigned long bp)
{
	assert(lock == &active->gate && !lock->owner && sp && bp && ip);
	lock->owner = (unsigned long)current;
	captured_ip = ip;
}
void kd_mutex_direct_unlock_clobber_v1(struct kd_mutex *lock, unsigned long sp,
                                      unsigned long ip, unsigned long bp)
{
	assert(sp && bp && ip);
	kd_mutex_api_unlock(lock);
}
#include "core.h"
#include "api.h"
#include "provider.h"

static DEFINE_KD_RWSEM(sem);
extern char rwsem_entry[];
extern char rwsem_interruptible_entry[], rwsem_killable_entry[];
static unsigned long payload;
static __attribute__((noinline, noipa)) void write_body(void)
{
	kd_down_write(&sem);
	asm volatile(".globl rwsem_entry\n.set rwsem_entry, 1b\n" : : : "memory");
	payload++;
	kd_up_write(&sem);
}

static __attribute__((noinline, noipa)) int interruptible_body(void)
{
	int result = kd_down_write_interruptible(&sem);

	asm volatile(".globl rwsem_interruptible_entry\n.set rwsem_interruptible_entry, 1b\n" : : : "memory");
	if (result)
		return result;
	payload++;
	kd_up_write(&sem);
	return 0;
}

static __attribute__((noinline, noipa)) int killable_body(void)
{
	int result = kd_down_write_killable(&sem);

	asm volatile(".globl rwsem_killable_entry\n.set rwsem_killable_entry, 1b\n" : : : "memory");
	if (result)
		return result;
	payload++;
	kd_up_write(&sem);
	return 0;
}

int main(void)
{
	struct kd_rwsem *arguments[] = { &sem, &sem };
	int index = 0, annotation = 0;
	void (*local)(struct kd_rwsem *) = kd_down_write;
	void (*release)(struct kd_rwsem *) = kd_up_write;

	active = &sem;
	assert(sizeof(sem) == 320 && offsetof(struct kd_rwsem, readers) == 64);
	write_body();
	assert(payload == 1 && local_calls == 1 && !delegate_calls && kd_rwsem_is_idle(&sem));
	cancel_result = -EINTR;
	assert(interruptible_body() == -EINTR && killable_body() == -EINTR);
	assert(payload == 1 && !delegate_calls && kd_rwsem_is_idle(&sem));
	cancel_result = 0;
	assert(!interruptible_body() && !killable_body());
	assert(payload == 3 && local_calls == 3 && kd_rwsem_is_idle(&sem));
	kd_down_write_nested(arguments[index++], annotation++);
	assert(index == 1 && !annotation && sem.admission == -1);
	assert(kd_rwsem_prepare(&sem, (unsigned long)rwsem_entry, 2) == -EBUSY);
	assert(!sem.prepared_writes && !prepare_calls);
	kd_downgrade_write(&sem);
	assert(sem.readers == 1 && !sem.admission && !sem.gate.owner);
	sem.readers = 0;
	prepare_result = -EOPNOTSUPP;
	assert(kd_rwsem_prepare(&sem, (unsigned long)rwsem_entry, 2) == -EOPNOTSUPP);
	assert(!sem.prepared_writes);
	prepare_result = 0;
	assert(!kd_rwsem_prepare(&sem, (unsigned long)rwsem_entry, 2));
	assert(sem.prepared_writes == 1);
	write_body();
	assert(payload == 4 && delegate_calls == 1 && captured_ip == (unsigned long)rwsem_entry);
	assert(last_wait_state == TASK_UNINTERRUPTIBLE);
	assert(kd_rwsem_is_idle(&sem));
	cancel_result = -EINTR;
	assert(interruptible_body() == -EINTR);
	assert(last_wait_state == TASK_INTERRUPTIBLE && kd_rwsem_is_idle(&sem));
	assert(killable_body() == -EINTR);
	assert(last_wait_state == TASK_KILLABLE && kd_rwsem_is_idle(&sem));
	assert(payload == 4 && delegate_calls == 3);
	cancel_result = 0;
	assert(!interruptible_body() && !killable_body());
	assert(payload == 6 && delegate_calls == 5 && kd_rwsem_is_idle(&sem));
	local(&sem);
	assert(sem.admission == -1 && sem.prepared_writes == 1);
	kd_up_write(arguments[index++]);
	assert(index == 2 && kd_rwsem_is_idle(&sem));
	kd_down_write(&sem);
	assert(sem.admission == -1);
	release(&sem);
	local(&sem);
	kd_downgrade_write(&sem);
	assert(sem.readers == 1 && !sem.admission && sem.prepared_writes == 1);
	sem.readers = 0;
	assert(kd_rwsem_is_idle(&sem) && releases == unlocks);
	puts("PASS public rwsem native facade and preparation routing");
	return 0;
}
