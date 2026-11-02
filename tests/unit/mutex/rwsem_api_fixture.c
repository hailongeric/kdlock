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
#define DEFINE_LOCK_GUARD_1(...)
#define DEFINE_LOCK_GUARD_1_COND(...)
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)
#include "types.h"
#include "decls.h"

static unsigned int local_calls, delegate_calls, unlocks, releases, prepare_calls;
static int prepare_result;
static unsigned long captured_ip;
static struct kd_rwsem *active;
static long atomic_long_read(const long *p) { return *p; }
static long atomic_long_xchg(long *p, long n) { long old = *p; *p = n; return old; }
static long atomic_long_dec_return(long *p) { return --*p; }
static void atomic_long_inc(long *p) { ++*p; }
static bool kd_origin_mutex_owned(struct kd_mutex *lock, void *task)
{ return (unsigned long)lock->owner == (unsigned long)task; }
static void kd_rwsem_wake(struct kd_rwsem *sem, struct kd_rwsem_condition *queue)
{
	assert(sem == active && queue == &active->phase_wait && unlocks == releases + 1);
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
{ return !sem->admission && !sem->readers && !sem->gate.owner; }
void kd_down_write(struct kd_rwsem *sem)
{
	assert(kd_rwsem_is_idle(sem));
	sem->admission = -1;
	sem->gate.owner = (unsigned long)current;
	local_calls++;
}
void kd_rwsem_delegate_enter(struct kd_rwsem *sem)
{
	assert(kd_rwsem_is_idle(sem));
	sem->admission = 1;
	delegate_calls++;
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
static unsigned long payload;
static __attribute__((noinline, noipa)) void write_body(void)
{
	kd_down_write(&sem);
	asm volatile(".globl rwsem_entry\n.set rwsem_entry, 1b\n" : : : "memory");
	payload++;
	kd_up_write(&sem);
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
	assert(payload == 2 && delegate_calls == 1 && captured_ip == (unsigned long)rwsem_entry);
	assert(kd_rwsem_is_idle(&sem));
	local(&sem);
	assert(sem.admission == -1 && sem.prepared_writes == 1);
	kd_up_write(arguments[index++]);
	assert(index == 2 && kd_rwsem_is_idle(&sem));
	kd_down_write(&sem);
	assert(sem.admission == 1);
	release(&sem);
	local(&sem);
	kd_downgrade_write(&sem);
	assert(sem.readers == 1 && !sem.admission && sem.prepared_writes == 1);
	sem.readers = 0;
	assert(kd_rwsem_is_idle(&sem) && releases == unlocks);
	puts("PASS public rwsem native facade and preparation routing");
	return 0;
}
