/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>

typedef uint32_t u32;
typedef uint8_t u8;
typedef struct { int counter; } atomic_t;
#define ATOMIC_INIT(n) { (n) }
#define likely(x) (x)
#define atomic_set(p, n) __atomic_store_n(&(p)->counter, (n), __ATOMIC_RELAXED)
#define atomic_read(p) __atomic_load_n(&(p)->counter, __ATOMIC_ACQUIRE)
#define atomic_add(n, p) ((void)__atomic_fetch_add(&(p)->counter, (n), __ATOMIC_RELAXED))
#define atomic_sub(n, p) atomic_add(-(n), (p))
#define atomic_add_return_acquire(n, p) __atomic_add_fetch(&(p)->counter, (n), __ATOMIC_ACQUIRE)
#define atomic_sub_return_release(n, p) __atomic_sub_fetch(&(p)->counter, (n), __ATOMIC_RELEASE)
static int cmpxchg_count(atomic_t *p, int old, int next, int order)
{
	__atomic_compare_exchange_n(&p->counter, &old, next, 0, order, __ATOMIC_RELAXED);
	return old;
}
#define atomic_cmpxchg_acquire(p, old, next) cmpxchg_count(p, old, next, __ATOMIC_ACQUIRE)
#define atomic_cmpxchg_relaxed(p, old, next) cmpxchg_count(p, old, next, __ATOMIC_RELAXED)
#define atomic_cond_read_acquire(p, condition) ({ \
	int VAL; do { VAL = atomic_read(p); if (!(condition)) sched_yield(); \
	} while (!(condition)); VAL; })
#define smp_store_release(p, n) __atomic_store_n((p), (n), __ATOMIC_RELEASE)
static _Thread_local unsigned int pins, gates;
static void preempt_disable(void) { pins++; }
static void preempt_enable(void) { assert(pins); pins--; }
typedef struct { atomic_t val; } kd_spinlock_t;
#define KD_SPINLOCK_INITIALIZER { .val = ATOMIC_INIT(0) }
static void kd_spin_init(kd_spinlock_t *p) { atomic_set(&p->val, 0); }
static void kd_spin_direct_native_lock_inline(kd_spinlock_t *p)
{
	assert(pins);
	while (atomic_cmpxchg_acquire(&p->val, 0, 1)) sched_yield();
	gates++;
}
static void kd_spin_direct_native_release_inline(kd_spinlock_t *p)
{
	assert(pins && gates);
	gates--;
	smp_store_release(&p->val.counter, 0);
}
#define KD_SPIN_DIRECT_LOCK(p, cookie, continuation) do { \
	(void)(cookie); (void)(continuation); preempt_disable(); \
	kd_spin_direct_native_lock_inline(p); } while (0)
#define KD_SPIN_DIRECT_UNLOCK(p, cookie) do { \
	(void)(cookie); kd_spin_direct_native_release_inline(p); \
	preempt_enable(); } while (0)
static kd_spinlock_t *prepared;
static int kd_spin_prepare(kd_spinlock_t *p, unsigned long ip, unsigned int abi)
{
	prepared = p;
	return ip == 0x1234 && abi == 1 ? 0 : -EINVAL;
}
#include "rwlock_production.h"

static DEFINE_KD_RWLOCK(lock);
static atomic_t active_readers, active_writers, data, mirror;
static atomic_t ready, release_readers, writer_inside, release_writer, late_inside;
static pthread_barrier_t start;

static void wait_nonzero(atomic_t *p)
{
	while (!atomic_read(p)) sched_yield();
}

static void *overlapping_reader(void *unused)
{
	(void)unused;
	kd_read_lock(&lock);
	assert(pins == 1 && !gates);
	atomic_add(1, &ready);
	wait_nonzero(&release_readers);
	kd_read_unlock(&lock);
	assert(!pins && !gates);
	return NULL;
}

static void *waiting_writer(void *unused)
{
	(void)unused;
	KD_RWLOCK_DIRECT_WRITE_LOCK(&lock, 0, "");
	assert(pins == 1 && gates == 1);
	smp_store_release(&writer_inside.counter, 1);
	wait_nonzero(&release_writer);
	KD_RWLOCK_DIRECT_WRITE_UNLOCK(&lock, 0);
	assert(!pins && !gates);
	return NULL;
}

static void *late_reader(void *unused)
{
	(void)unused;
	kd_read_lock(&lock);
	assert(atomic_read(&release_writer));
	atomic_add(1, &late_inside);
	kd_read_unlock(&lock);
	assert(!pins && !gates);
	return NULL;
}

static void ordering(void)
{
	pthread_t a, b, writer, late;
	assert(!pthread_create(&a, NULL, overlapping_reader, NULL));
	assert(!pthread_create(&b, NULL, overlapping_reader, NULL));
	while (atomic_read(&ready) != 2) sched_yield();
	assert(atomic_read(&lock.cnts) == 2 * KD_RWLOCK_READER_BIAS);
	assert(!pthread_create(&writer, NULL, waiting_writer, NULL));
	while (!(atomic_read(&lock.cnts) & KD_RWLOCK_WRITER_WAITING)) sched_yield();
	assert(!atomic_read(&writer_inside));
	assert(!pthread_create(&late, NULL, late_reader, NULL));
	smp_store_release(&release_readers.counter, 1);
	wait_nonzero(&writer_inside);
	assert(!atomic_read(&late_inside));
	smp_store_release(&release_writer.counter, 1);
	assert(!pthread_join(a, NULL) && !pthread_join(b, NULL));
	assert(!pthread_join(writer, NULL) && !pthread_join(late, NULL));
	assert(atomic_read(&late_inside) == 1 && !atomic_read(&lock.cnts));
}

#define ITERATIONS 20000
static void *stress(void *arg)
{
	uintptr_t id = (uintptr_t)arg;
	pthread_barrier_wait(&start);
	for (int i = 0; i < ITERATIONS; i++) {
		if (id < 4) {
			if (id & 1) kd_write_lock(&lock);
			else KD_RWLOCK_DIRECT_WRITE_LOCK(&lock, 1, "");
			assert(!__atomic_fetch_add(&active_writers.counter, 1, __ATOMIC_SEQ_CST));
			assert(!atomic_read(&active_readers));
			int next = atomic_read(&data) + 1;
			atomic_set(&data, next);
			atomic_set(&mirror, next);
			assert(__atomic_fetch_sub(&active_writers.counter, 1, __ATOMIC_SEQ_CST) == 1);
			if (id & 1) kd_write_unlock(&lock);
			else KD_RWLOCK_DIRECT_WRITE_UNLOCK(&lock, 1);
		} else {
			kd_read_lock(&lock);
			__atomic_fetch_add(&active_readers.counter, 1, __ATOMIC_SEQ_CST);
			assert(!atomic_read(&active_writers));
			assert(atomic_read(&data) == atomic_read(&mirror));
			__atomic_fetch_sub(&active_readers.counter, 1, __ATOMIC_SEQ_CST);
			kd_read_unlock(&lock);
		}
		assert(!pins && !gates);
	}
	return NULL;
}

int main(void)
{
	pthread_t workers[10];
	assert(!kd_rwlock_prepare(&lock, 0x1234, 1) && prepared == &lock.gate);
	assert(kd_rwlock_prepare(NULL, 0x1234, 1) == -EINVAL);
	assert(kd_rwlock_prepare(&lock, 0, 1) == -EINVAL);
	ordering();
	assert(!pthread_barrier_init(&start, NULL, 10));
	for (uintptr_t i = 0; i < 10; i++)
		assert(!pthread_create(&workers[i], NULL, stress, (void *)i));
	for (int i = 0; i < 10; i++) assert(!pthread_join(workers[i], NULL));
	assert(atomic_read(&data) == 4 * ITERATIONS);
	assert(!atomic_read(&lock.cnts) && !atomic_read(&lock.gate.val));
	/* Writer release must preserve speculative reader increments. */
	atomic_set(&lock.cnts, KD_RWLOCK_WRITER_LOCKED + 3 * KD_RWLOCK_READER_BIAS);
	kd_rwlock_writer_exit(&lock);
	assert(atomic_read(&lock.cnts) == 3 * KD_RWLOCK_READER_BIAS);
	kd_rwlock_init(&lock);
	/* Each macro argument is evaluated once; nesting preserves outer pins. */
	kd_rwlock_t *locks[] = { &lock, &lock };
	int index = 0;
	preempt_disable();
	KD_RWLOCK_DIRECT_WRITE_LOCK(locks[index++], 0, "");
	assert(index == 1 && pins == 2);
	KD_RWLOCK_DIRECT_WRITE_UNLOCK(locks[index++], 0);
	assert(index == 2 && pins == 1);
	preempt_enable();
	puts("PASS rwlock: concurrent readers, writer exclusion/intent, mixed progress, release ordering and balanced pins");
}
