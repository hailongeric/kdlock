/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

typedef uint32_t u32;
typedef uint8_t u8;
typedef struct { int counter; } atomic_t;
#define __aligned(n) __attribute__((aligned(n)))
#define smp_mb__before_atomic() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define ATOMIC_INIT(n) { (n) }
#define likely(x) (x)
#define unlikely(x) (x)
#define atomic_set(p, n) __atomic_store_n(&(p)->counter, (n), __ATOMIC_RELAXED)
#define atomic_read(p) __atomic_load_n(&(p)->counter, __ATOMIC_ACQUIRE)
#define atomic_add(n, p) ((void)__atomic_fetch_add(&(p)->counter, (n), __ATOMIC_RELAXED))
#define atomic_sub(n, p) atomic_add(-(n), (p))
static _Thread_local bool inject_reader_race, inject_writer_race;
static int add_acquire(int n, atomic_t *p)
{
	if (inject_reader_race) {
		inject_reader_race = false;
		atomic_set(p, 0xf0); /* Another writer won after trylock's read. */
	}
	return __atomic_add_fetch(&p->counter, n, __ATOMIC_ACQUIRE);
}
#define atomic_add_return_acquire(n, p) add_acquire((n), (p))
#define atomic_sub_return_release(n, p) __atomic_sub_fetch(&(p)->counter, (n), __ATOMIC_RELEASE)
static int cmpxchg_count(atomic_t *p, int old, int next, int order)
{
	if (inject_writer_race) {
		inject_writer_race = false;
		atomic_set(p, 0x200); /* A reader won after trylock's read. */
	}
	__atomic_compare_exchange_n(&p->counter, &old, next, 0, order, __ATOMIC_RELAXED);
	return old;
}
#define atomic_cmpxchg_acquire(p, old, next) cmpxchg_count(p, old, next, __ATOMIC_ACQUIRE)
#define atomic_cmpxchg_relaxed(p, old, next) cmpxchg_count(p, old, next, __ATOMIC_RELAXED)
#define atomic_cond_read_acquire(p, condition) ({ \
	int VAL; do { VAL = atomic_read(p); if (!(condition)) sched_yield(); \
	} while (!(condition)); VAL; })
#define smp_store_release(p, n) __atomic_store_n((p), (n), __ATOMIC_RELEASE)
static _Thread_local unsigned int pins, gates, hardirq_depth, bh_depth, heat_calls;
static _Thread_local bool irq_off, last_unpin_irq;
#define in_interrupt() (hardirq_depth || bh_depth)
#define _RET_IP_ 0UL
#define SOFTIRQ_LOCK_OFFSET 1
#define typecheck(type, value) ((void)sizeof((type){value}))
#define local_irq_save(flags) do { (flags) = irq_off; irq_off = true; } while (0)
#define local_irq_restore(flags) do { irq_off = !!(flags); } while (0)
#define local_irq_disable() do { irq_off = true; } while (0)
#define local_irq_enable() do { irq_off = false; } while (0)
static _Thread_local struct { unsigned int nondelegated; } kd_spin_fast_cpu;
#define this_cpu_inc(value) ((void)++(value))
#define this_cpu_dec(value) ((void)--(value))
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define barrier() __asm__ volatile("" ::: "memory")
static void kd_hotlock_spin_entry_pinned(void) { assert(pins); heat_calls++; }
static void preempt_disable(void) { pins++; }
static void preempt_enable(void) { assert(pins); pins--; last_unpin_irq = irq_off; }
static void __local_bh_disable_ip(unsigned long ip, unsigned int offset)
{
	(void)ip; assert(offset == SOFTIRQ_LOCK_OFFSET); pins++; bh_depth++;
}
static void __local_bh_enable_ip(unsigned long ip, unsigned int offset)
{
	(void)ip; assert(offset == SOFTIRQ_LOCK_OFFSET && pins && bh_depth);
	pins--; bh_depth--;
}
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
#define KD_ENTRY_ABI_RWLOCK_CLOBBER_V1 3
#define this_cpu_read(value) (value)
#define KD_SPIN_DIRECT_CALL(symbol, p, continuation) do { \
	(void)(continuation); symbol((p), 0, 0, 0); } while (0)
static kd_spinlock_t *prepared;
static int kd_spin_prepare(kd_spinlock_t *p, unsigned long ip, unsigned int abi)
{
	prepared = p;
	return ip == 0x1234 && abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1 ? 0 : -EINVAL;
}
#include "rwlock_production.h"
#include "rwlock_native_release.h"

/* Substitute the gate engine, retaining the production writer admission. */
void kd_rwlock_lock_pinned_clobber_v1(kd_spinlock_t *gate, unsigned long sp,
				    unsigned long ip, unsigned long bp)
{
	(void)sp; (void)ip; (void)bp;
	kd_spin_direct_native_lock_inline(gate);
	kd_rwlock_writer_enter((kd_rwlock_t *)((char *)gate - offsetof(kd_rwlock_t, gate)));
}

struct kd_exec_frame {
	unsigned int entry_abi, spin_kind;
	unsigned long outer_lock_addr;
	unsigned char rwlock_admitted, executed;
};
#define KD_SPIN_CONT_ROOT 0
#define BUG_ON(value) assert(!(value))
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#include "rwlock_prelude.h"

static DEFINE_KD_RWLOCK(lock);
static atomic_t active_readers, active_writers, data, mirror;
static atomic_t ready, release_readers, writer_inside, release_writer, late_inside;
static atomic_t fast_released, fast_reader_inside;
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

static void *fast_reader(void *interrupt)
{
	if (interrupt) hardirq_depth++;
	kd_read_lock(&lock);
	assert(atomic_read(&fast_released));
	atomic_set(&fast_reader_inside, 1);
	kd_read_unlock(&lock);
	if (interrupt) hardirq_depth--;
	assert(!pins && !gates && !hardirq_depth);
	return NULL;
}

static void fast_ordering(void)
{
	pthread_t reader, writer;
	kd_write_lock(&lock);
	assert(!gates && kd_spin_fast_cpu.nondelegated == 1);
	assert(atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_FAST);
	assert(!pthread_create(&reader, NULL, fast_reader, NULL));
	while (atomic_read(&lock.cnts) != KD_RWLOCK_WRITER_FAST + KD_RWLOCK_READER_BIAS)
		sched_yield();
	assert(!atomic_read(&fast_reader_inside));
	atomic_set(&fast_released, 1);
	kd_write_unlock(&lock);
	assert(!pthread_join(reader, NULL));
	assert(!pins && !gates && !kd_spin_fast_cpu.nondelegated);

	/* A queued writer can publish intent while an ungated writer owns the
	 * low byte. Releasing that byte must retain WAITING until admission. */
	atomic_set(&writer_inside, 0);
	atomic_set(&release_writer, 0);
	kd_write_lock(&lock);
	assert(!pthread_create(&writer, NULL, waiting_writer, NULL));
	while (!(atomic_read(&lock.cnts) & KD_RWLOCK_WRITER_WAITING)) sched_yield();
	assert(!atomic_read(&writer_inside));
	kd_write_unlock(&lock);
	wait_nonzero(&writer_inside);
	atomic_set(&release_writer, 1);
	assert(!pthread_join(writer, NULL));
	assert(!atomic_read(&lock.cnts) && !atomic_read(&lock.gate.val));
}

/* The WAITING exception never bypasses an actually active writer. */
static void interrupt_active_writer(void)
{
	pthread_t reader;

	atomic_set(&fast_released, 0);
	atomic_set(&fast_reader_inside, 0);
	kd_write_lock_irq(&lock);
	assert(!pthread_create(&reader, NULL, fast_reader, (void *)1));
	while (atomic_read(&lock.cnts) != KD_RWLOCK_WRITER_FAST + KD_RWLOCK_READER_BIAS)
		sched_yield();
	assert(!atomic_read(&fast_reader_inside));
	atomic_set(&fast_released, 1);
	kd_write_unlock_irq(&lock);
	assert(!pthread_join(reader, NULL));
	assert(atomic_read(&fast_reader_inside) && !atomic_read(&lock.cnts));
	assert(!pins && !irq_off && !kd_spin_fast_cpu.nondelegated);
}

/* This is the deadlock boundary: the writer already owns the gate and is
 * draining our outer read. A simulated interrupt/BH reader must not queue. */
static void interrupt_readers(void)
{
	pthread_t writer;

	for (unsigned int bh = 0; bh < 2; bh++) {
		atomic_set(&writer_inside, 0);
		atomic_set(&release_writer, 0);
		kd_read_lock(&lock);
		assert(!pthread_create(&writer, NULL, waiting_writer, NULL));
		while (!(atomic_read(&lock.cnts) & KD_RWLOCK_WRITER_WAITING)) sched_yield();
		if (bh) kd_read_lock_bh(&lock);
		else { hardirq_depth++; kd_read_lock(&lock); }
		assert(pins == 2 && !gates && !atomic_read(&writer_inside));
		assert(atomic_read(&lock.cnts) == 2 * KD_RWLOCK_READER_BIAS + KD_RWLOCK_WRITER_WAITING);
		if (bh) kd_read_unlock_bh(&lock);
		else { kd_read_unlock(&lock); hardirq_depth--; }
		assert(pins == 1 && !bh_depth && !hardirq_depth);
		kd_read_unlock(&lock);
		wait_nonzero(&writer_inside);
		atomic_set(&release_writer, 1);
		assert(!pthread_join(writer, NULL));
		assert(!pins && !gates && !atomic_read(&lock.cnts));
	}
}

static void local_api(void)
{
	unsigned long flags;
	kd_rwlock_t other = KD_RWLOCK_INITIALIZER;
	kd_rwlock_t *locks[] = { &lock, &lock };
	int index;
	unsigned int before_heat = heat_calls;

	for (unsigned int disabled = 0; disabled < 2; disabled++) {
		irq_off = disabled;
		index = 0;
		kd_read_lock_irqsave(locks[index++], flags);
		assert(index == 1 && flags == disabled && irq_off && pins == 1);
		kd_read_unlock_irqrestore(locks[index++], flags);
		assert(index == 2 && !pins && irq_off == disabled);
		kd_write_lock_irqsave(&lock, flags);
		assert(flags == disabled && irq_off && pins == 1 && kd_spin_fast_cpu.nondelegated == 1);
		kd_write_unlock_irqrestore(&lock, flags);
		assert(!pins && irq_off == disabled && !kd_spin_fast_cpu.nondelegated);
		assert(kd_write_trylock_irqsave(&lock, flags));
		assert(flags == disabled && irq_off && pins == 1);
		kd_write_unlock_irqrestore(&lock, flags);
		kd_read_lock(&lock);
		assert(!kd_write_trylock_irqsave(&lock, flags));
		assert(flags == disabled && irq_off == disabled && pins == 1 && last_unpin_irq);
		kd_read_unlock(&lock);
	}
	irq_off = false;
	kd_read_lock_irq(&lock); assert(irq_off && pins == 1);
	kd_read_unlock_irq(&lock); assert(!irq_off && !pins);
	kd_write_lock_irq(&lock); assert(irq_off && pins == 1);
	kd_write_unlock_irq(&lock); assert(!irq_off && !pins);
	__local_bh_disable_ip(0, SOFTIRQ_LOCK_OFFSET);
	kd_read_lock_bh(&lock); assert(pins == 2 && bh_depth == 2);
	kd_write_lock_bh(&other); assert(pins == 3 && bh_depth == 3);
	kd_write_unlock_bh(&other); assert(pins == 2 && bh_depth == 2);
	kd_read_unlock_bh(&lock); assert(pins == 1 && bh_depth == 1);
	__local_bh_enable_ip(0, SOFTIRQ_LOCK_OFFSET);
	assert(kd_read_trylock(&lock));
	assert(pins == 1 && !kd_write_trylock(&lock) && pins == 1);
	kd_read_unlock(&lock);
	assert(kd_write_trylock(&lock));
	assert(pins == 1 && !kd_read_trylock(&lock) && !kd_write_trylock(&lock) && pins == 1);
	kd_write_unlock(&lock);
	inject_reader_race = true;
	assert(!kd_read_trylock(&lock));
	assert(!pins && atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_FAST);
	atomic_set(&lock.cnts, 0);
	inject_writer_race = true;
	assert(!kd_write_trylock(&lock));
	assert(!pins && !kd_spin_fast_cpu.nondelegated && atomic_read(&lock.cnts) == KD_RWLOCK_READER_BIAS);
	atomic_set(&lock.cnts, 0);
	assert(!gates && !bh_depth && !irq_off && heat_calls == before_heat);
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
		assert(!pins && !gates && !kd_spin_fast_cpu.nondelegated);
	}
	return NULL;
}

int main(void)
{
	pthread_t workers[10];
	assert(!kd_rwlock_prepare(&lock, 0x1234, 3) && prepared == &lock.gate);
	assert(kd_rwlock_prepare(NULL, 0x1234, 3) == -EINVAL);
	assert(kd_rwlock_prepare(&lock, 0, 3) == -EINVAL);
	assert(kd_rwlock_prepare(&lock, 0x1234, 1) == -EINVAL);
	/* Production prelude: refusal cancels admission under the held gate.
	 * Virtual spin children inherit ABI3 without acquiring a writer count. */
	struct kd_exec_frame frame = { .entry_abi = 3,
		.outer_lock_addr = (unsigned long)&lock.gate };
	preempt_disable();
	kd_spin_direct_native_lock_inline(&lock.gate);
	kd_spin_rw_begin(&frame);
	assert(frame.rwlock_admitted && atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_LOCKED);
	kd_spin_rw_cancel(&frame);
	assert(!frame.rwlock_admitted && !atomic_read(&lock.cnts));
	kd_spin_rw_retry(&frame, 0);
	assert(!atomic_read(&lock.cnts));
	kd_spin_rw_retry(&frame, 1);
	assert(!frame.rwlock_admitted && atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_LOCKED);
	kd_rwlock_writer_exit(&lock);
	frame.spin_kind = 1;
	kd_spin_rw_begin(&frame);
	assert(!frame.rwlock_admitted && !atomic_read(&lock.cnts));
	kd_spin_direct_native_release_inline(&lock.gate);
	preempt_enable();
	ordering();
	fast_ordering();
	interrupt_readers();
	interrupt_active_writer();
	local_api();
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
	puts("PASS rwlock: concurrent readers, writer exclusion/intent, mixed progress, release ordering, IRQ/BH/try APIs, interrupt reader bypass and balanced pins");
}
