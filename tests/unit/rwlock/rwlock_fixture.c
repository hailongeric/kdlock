/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32;
typedef uint16_t u16;
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
#include "rwlock_spin_type.h"

static _Thread_local unsigned int pins, gates, hardirq_depth, bh_depth, heat_calls;
static _Thread_local unsigned int context_reads, gate_attempts, gate_acquires;
static _Thread_local unsigned int gate_releases, contended_calls;
static _Thread_local u32 last_contended_failed;
static _Thread_local bool irq_off, last_unpin_irq;
static _Thread_local struct { unsigned int nondelegated; } kd_spin_fast_cpu;
static _Thread_local atomic_t *held_gates[8];
static _Thread_local bool check_reservation;
static _Thread_local unsigned int expected_reservation, expected_queue_heat;
static _Thread_local void (*failed_gate_observer)(atomic_t *, u32);
static _Thread_local void (*context_observer)(void);
static _Thread_local void (*wait_observer)(atomic_t *, int);

/* Observe the physical primitives, not a second implementation of the
 * production acquisition-reference or heat accounting. */
static void observe_gate_acquire(atomic_t *word)
{
	assert(pins && kd_spin_fast_cpu.nondelegated);
	if (check_reservation)
		assert(kd_spin_fast_cpu.nondelegated == expected_reservation);
	assert(gates < sizeof(held_gates) / sizeof(held_gates[0]));
	held_gates[gates++] = word;
	gate_acquires++;
}

static void observe_release(void *address, size_t size, unsigned long value)
{
	for (unsigned int i = 0; i < gates; i++) {
		if ((void *)held_gates[i] != address)
			continue;
		assert(size == sizeof(u8) && !value && pins);
		assert((atomic_read(held_gates[i]) & 0xff) == KD_SPIN_DIRECT_NATIVE_HELD);
		assert(kd_spin_fast_cpu.nondelegated);
		if (check_reservation)
			assert(kd_spin_fast_cpu.nondelegated == expected_reservation);
		held_gates[i] = held_gates[--gates];
		held_gates[gates] = NULL;
		gate_releases++;
		return;
	}
}
#define smp_store_release(p, n) do { \
	__auto_type kd_store_p = (p); \
	__typeof__(*kd_store_p) kd_store_n = (n); \
	observe_release((void *)kd_store_p, sizeof(*kd_store_p), kd_store_n); \
	__atomic_store_n(kd_store_p, kd_store_n, __ATOMIC_RELEASE); \
} while (0)

/* A one-shot primitive observer lets another real writer win between the
 * production speculative rollback and interrupt-reader re-admission. */
static _Thread_local atomic_t *rollback_target;
static _Thread_local void (*rollback_observer)(atomic_t *);
static void subtract_count(int n, atomic_t *p)
{
	atomic_add(-n, p);
	if (p == rollback_target && rollback_observer) {
		void (*observe)(atomic_t *) = rollback_observer;

		rollback_observer = NULL;
		observe(p);
	}
}
#define atomic_sub(n, p) subtract_count((n), (p))
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
	bool gate = !old && next == KD_SPIN_DIRECT_NATIVE_HELD;

	if (inject_writer_race) {
		inject_writer_race = false;
		atomic_set(p, 0x200); /* A reader won after trylock's read. */
	}
	if (gate) {
		assert(pins && kd_spin_fast_cpu.nondelegated);
		if (check_reservation)
			assert(kd_spin_fast_cpu.nondelegated == expected_reservation);
		gate_attempts++;
	}
	__atomic_compare_exchange_n(&p->counter, &old, next, 0, order, __ATOMIC_RELAXED);
	if (gate && !old)
		observe_gate_acquire(p);
	else if (gate && failed_gate_observer) {
		void (*observe)(atomic_t *, u32) = failed_gate_observer;

		failed_gate_observer = NULL;
		observe(p, old);
	}
	return old;
}
#define atomic_cmpxchg_acquire(p, old, next) cmpxchg_count(p, old, next, __ATOMIC_ACQUIRE)
#define atomic_cmpxchg_relaxed(p, old, next) cmpxchg_count(p, old, next, __ATOMIC_RELAXED)
#define atomic_cond_read_acquire(p, condition) ({ \
	int VAL; do { VAL = atomic_read(p); \
		if (wait_observer) { \
			void (*kd_observe)(atomic_t *, int) = wait_observer; \
			wait_observer = NULL; kd_observe((p), VAL); \
		} \
		if (!(condition)) sched_yield(); \
	} while (!(condition)); VAL; })
static bool interrupt_context(void)
{
	context_reads++;
	if (context_observer)
		context_observer();
	return hardirq_depth || bh_depth;
}
#define in_interrupt() interrupt_context()
#define _RET_IP_ 0UL
#define SOFTIRQ_LOCK_OFFSET 1
#define typecheck(type, value) ((void)sizeof((type){value}))
#define local_irq_save(flags) do { (flags) = irq_off; irq_off = true; } while (0)
#define local_irq_restore(flags) do { irq_off = !!(flags); } while (0)
#define local_irq_disable() do { irq_off = true; } while (0)
#define local_irq_enable() do { irq_off = false; } while (0)
#define this_cpu_inc(value) ((void)++(value))
#define this_cpu_dec(value) do { assert(value); --(value); } while (0)
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

/* Only the hardware pending/MCS engine is substituted. It acquires the word;
 * reserve/finish/cancel/release below are extracted production definitions. */
static void kd_spin_direct_native_contended(kd_spinlock_t *p, u32 failed)
{
	int old;

	assert(failed && pins && kd_spin_fast_cpu.nondelegated);
	if (check_reservation)
		assert(kd_spin_fast_cpu.nondelegated == expected_reservation);
	if (check_reservation)
		assert(heat_calls == expected_queue_heat);
	contended_calls++;
	last_contended_failed = failed;
	do {
		old = 0;
		if (__atomic_compare_exchange_n(&p->val.counter, &old,
				KD_SPIN_DIRECT_NATIVE_HELD, 0,
				__ATOMIC_ACQUIRE, __ATOMIC_RELAXED))
			break;
		sched_yield();
	} while (true);
	observe_gate_acquire(&p->val);
}
#include "rwlock_native_gate.h"
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
static atomic_t fast_released, fast_reader_inside, fast_reader_waiting;
static atomic_t gap_rolled_back, gap_writer_inside, gap_release_writer, gap_reader_inside;
static unsigned int gap_value;
static pthread_barrier_t start;

struct route_snapshot {
	unsigned int native, held, heat, context, attempts, acquired, released, queued;
};
static struct route_snapshot route_snapshot(void)
{
	return (struct route_snapshot) {
		.native = kd_spin_fast_cpu.nondelegated, .held = gates,
		.heat = heat_calls, .context = context_reads, .attempts = gate_attempts,
		.acquired = gate_acquires, .released = gate_releases,
		.queued = contended_calls,
	};
}
static void assert_route(struct route_snapshot before, unsigned int attempts,
			 unsigned int context, unsigned int heat, unsigned int queued,
			 unsigned int owned)
{
	assert(kd_spin_fast_cpu.nondelegated == before.native && gates == before.held);
	assert(gate_attempts == before.attempts + attempts);
	assert(context_reads == before.context + context);
	assert(heat_calls == before.heat + heat);
	assert(contended_calls == before.queued + queued);
	assert(gate_acquires == before.acquired + owned);
	assert(gate_releases == before.released + owned);
}
static void expect_reservation(struct route_snapshot before)
{
	expected_reservation = before.native + 1;
	expected_queue_heat = before.heat + 1;
	check_reservation = true;
}
static _Thread_local struct route_snapshot fast_before;
static void fast_wait(atomic_t *count, int value)
{
	assert(count == &lock.cnts);
	assert(value == KD_RWLOCK_WRITER_FAST + KD_RWLOCK_READER_BIAS);
	assert(kd_spin_fast_cpu.nondelegated == fast_before.native + 1);
	assert(gates == fast_before.held + 1 && heat_calls == fast_before.heat + 1);
	assert(context_reads == fast_before.context);
	assert(gate_attempts == fast_before.attempts + 1);
	assert(contended_calls == fast_before.queued);
	smp_store_release(&fast_reader_waiting.counter, 1);
}

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

static void *fast_reader(void *argument)
{
	uintptr_t mode = (uintptr_t)argument;

	fast_before = route_snapshot();
	expect_reservation(fast_before);
	wait_observer = fast_wait;
	if (mode == 2) kd_read_lock_bh(&lock);
	else {
		if (mode == 1) hardirq_depth++;
		kd_read_lock(&lock);
	}
	assert(!wait_observer && atomic_read(&fast_released));
	assert_route(fast_before, 1, 0, 1, 0, 1);
	check_reservation = false;
	atomic_set(&fast_reader_inside, 1);
	if (mode == 2) kd_read_unlock_bh(&lock);
	else {
		kd_read_unlock(&lock);
		if (mode == 1) hardirq_depth--;
	}
	assert(!pins && !gates && !hardirq_depth && !bh_depth);
	return NULL;
}

static void fast_ordering(void)
{
	pthread_t reader, writer;

	atomic_set(&fast_released, 0);
	atomic_set(&fast_reader_inside, 0);
	atomic_set(&fast_reader_waiting, 0);
	kd_write_lock(&lock);
	assert(!gates && kd_spin_fast_cpu.nondelegated == 1);
	assert(atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_FAST);
	assert(!pthread_create(&reader, NULL, fast_reader, NULL));
	wait_nonzero(&fast_reader_waiting);
	assert(atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_FAST + KD_RWLOCK_READER_BIAS);
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
	for (uintptr_t mode = 1; mode <= 2; mode++) {
		pthread_t reader;

		atomic_set(&fast_released, 0);
		atomic_set(&fast_reader_inside, 0);
		atomic_set(&fast_reader_waiting, 0);
		kd_write_lock_irq(&lock);
		assert(!pthread_create(&reader, NULL, fast_reader, (void *)mode));
		wait_nonzero(&fast_reader_waiting);
		assert(atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_FAST + KD_RWLOCK_READER_BIAS);
		assert(!atomic_read(&fast_reader_inside));
		atomic_set(&fast_released, 1);
		kd_write_unlock_irq(&lock);
		assert(!pthread_join(reader, NULL));
		assert(atomic_read(&fast_reader_inside) && !atomic_read(&lock.cnts));
		assert(!pins && !irq_off && !kd_spin_fast_cpu.nondelegated);
	}
}

/* This is the deadlock boundary: the writer already owns the gate and is
 * draining our outer read. A simulated interrupt/BH reader must not queue. */
static void interrupt_readers(void)
{
	pthread_t writer;

	for (unsigned int bh = 0; bh < 2; bh++) {
		struct route_snapshot before = route_snapshot();

		atomic_set(&writer_inside, 0);
		atomic_set(&release_writer, 0);
		kd_read_lock(&lock);
		assert(!pthread_create(&writer, NULL, waiting_writer, NULL));
		while (!(atomic_read(&lock.cnts) & KD_RWLOCK_WRITER_WAITING)) sched_yield();
		expect_reservation(before);
		if (bh) kd_read_lock_bh(&lock);
		else { hardirq_depth++; kd_read_lock(&lock); }
		assert_route(before, 1, 1, 0, 0, 0);
		check_reservation = false;
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

static void gap_on_rollback(atomic_t *count)
{
	/* The main thread's preholder is still counted. Our speculative reader
	 * is absent; the real queued writer may enter only after main releases. */
	assert(count == &lock.cnts);
	assert(atomic_read(count) == KD_RWLOCK_READER_BIAS + KD_RWLOCK_WRITER_WAITING);
	smp_store_release(&gap_rolled_back.counter, 1);
	wait_nonzero(&gap_writer_inside);
}

static void *gap_writer(void *unused)
{
	(void)unused;
	kd_write_lock(&lock);
	assert(pins == 1 && gates == 1 && !atomic_read(&gap_reader_inside));
	smp_store_release(&gap_writer_inside.counter, 1);
	wait_nonzero(&gap_release_writer);
	gap_value = 0x12345678;
	kd_write_unlock(&lock);
	assert(!pins && !gates && !kd_spin_fast_cpu.nondelegated);
	return NULL;
}

static void *gap_interrupt_reader(void *argument)
{
	bool bh = (uintptr_t)argument;
	struct route_snapshot before = route_snapshot();

	expect_reservation(before);
	rollback_target = &lock.cnts;
	rollback_observer = gap_on_rollback;
	if (bh) kd_read_lock_bh(&lock);
	else { hardirq_depth++; kd_read_lock(&lock); }
	assert(!rollback_observer && pins == 1 && !gates);
	assert_route(before, 1, 1, 0, 0, 0);
	check_reservation = false;
	assert(atomic_read(&gap_release_writer) && gap_value == 0x12345678);
	assert(atomic_read(&lock.cnts) == KD_RWLOCK_READER_BIAS);
	atomic_set(&gap_reader_inside, 1);
	if (bh) kd_read_unlock_bh(&lock);
	else { kd_read_unlock(&lock); hardirq_depth--; }
	rollback_target = NULL;
	assert(!pins && !gates && !hardirq_depth && !bh_depth);
	return NULL;
}

static void interrupt_writer_wins_gap(void)
{
	for (uintptr_t bh = 0; bh < 2; bh++) {
		pthread_t writer, reader;

		atomic_set(&gap_rolled_back, 0);
		atomic_set(&gap_writer_inside, 0);
		atomic_set(&gap_release_writer, 0);
		atomic_set(&gap_reader_inside, 0);
		gap_value = 0;
		kd_read_lock(&lock);
		assert(!pthread_create(&writer, NULL, gap_writer, NULL));
		while (!(atomic_read(&lock.cnts) & KD_RWLOCK_WRITER_WAITING)) sched_yield();
		assert(!pthread_create(&reader, NULL, gap_interrupt_reader, (void *)bh));
		wait_nonzero(&gap_rolled_back);
		assert(!atomic_read(&gap_writer_inside));
		kd_read_unlock(&lock);
		wait_nonzero(&gap_writer_inside);
		/* IRQ/BH must re-publish its count, then wait on actual ownership.
		 * It must neither enter under this writer nor join the occupied gate. */
		while (atomic_read(&lock.cnts) != KD_RWLOCK_WRITER_LOCKED + KD_RWLOCK_READER_BIAS)
			sched_yield();
		assert(!atomic_read(&gap_reader_inside) && atomic_read(&lock.gate.val));
		smp_store_release(&gap_release_writer.counter, 1);
		assert(!pthread_join(writer, NULL) && !pthread_join(reader, NULL));
		assert(atomic_read(&gap_reader_inside));
		assert(!pins && !gates && !atomic_read(&lock.cnts) && !atomic_read(&lock.gate.val));
	}
}

static _Thread_local struct route_snapshot failed_before;
static _Thread_local u32 observed_failed;
static void release_writer_after_failed_gate(atomic_t *word, u32 failed)
{
	assert(word == &lock.gate.val && failed == KD_SPIN_DIRECT_NATIVE_HELD);
	assert(kd_spin_fast_cpu.nondelegated == failed_before.native + 1);
	assert(context_reads == failed_before.context);
	observed_failed = failed;
	smp_store_release(&release_writer.counter, 1);
	while (atomic_read(word)) sched_yield();
}
static void observe_context_after_release(void)
{
	assert(!atomic_read(&lock.gate.val));
	assert(gate_attempts == failed_before.attempts + 1);
	assert(kd_spin_fast_cpu.nondelegated == failed_before.native + 1);
	assert(heat_calls == failed_before.heat);
}

/* The actual writer releases between the single failed reserve CAS and the
 * context query. IRQ/BH must cancel and bypass, even though a retry could now
 * acquire the gate. Task context must finish the same reservation exactly once.
 * A separately held native gate makes lost/doubled references observable. */
static void gate_becomes_free(void)
{
	for (uintptr_t mode = 0; mode < 3; mode++) {
		kd_spinlock_t outer = KD_SPINLOCK_INITIALIZER;
		pthread_t writer;

		preempt_disable();
		kd_spin_direct_native_lock_inline(&outer);
		atomic_set(&writer_inside, 0);
		atomic_set(&release_writer, 0);
		/* Force the writer through real gate admission, not ungated FAST. */
		kd_read_lock(&lock);
		assert(!pthread_create(&writer, NULL, waiting_writer, NULL));
		while (!(atomic_read(&lock.cnts) & KD_RWLOCK_WRITER_WAITING)) sched_yield();
		kd_read_unlock(&lock);
		wait_nonzero(&writer_inside);
		failed_before = route_snapshot();
		assert(failed_before.native == 1 && failed_before.held == 1);
		expect_reservation(failed_before);
		observed_failed = 0;
		failed_gate_observer = release_writer_after_failed_gate;
		context_observer = observe_context_after_release;
		if (mode == 2) kd_read_lock_bh(&lock);
		else {
			if (mode == 1) hardirq_depth++;
			kd_read_lock(&lock);
		}
		assert(!failed_gate_observer && observed_failed == KD_SPIN_DIRECT_NATIVE_HELD);
		assert_route(failed_before, 1, 1, mode == 0, mode == 0, mode == 0);
		if (!mode) assert(last_contended_failed == observed_failed);
		assert(pins == 2 && atomic_read(&lock.cnts) == KD_RWLOCK_READER_BIAS);
		assert(!atomic_read(&lock.gate.val));
		check_reservation = false;
		context_observer = NULL;
		if (mode == 2) kd_read_unlock_bh(&lock);
		else {
			kd_read_unlock(&lock);
			if (mode == 1) hardirq_depth--;
		}
		assert(!pthread_join(writer, NULL));
		assert(pins == 1 && gates == 1 && kd_spin_fast_cpu.nondelegated == 1);
		kd_spin_direct_native_release_inline(&outer);
		preempt_enable();
		assert(!pins && !gates && !kd_spin_fast_cpu.nondelegated);
		assert(!hardirq_depth && !bh_depth && !atomic_read(&lock.cnts));
	}
}

/* These gate-word states model another CPU's locked/pending/tail publication.
 * Interrupt bypass has no ownership of any byte and must leave all of it alone.
 * The real reserve/cancel helpers still operate above a live outer reference. */
static void interrupt_pending_tail(void)
{
	const u32 words[] = { 0x00000100, 0x12340000, 0x12340105 };
	kd_spinlock_t outer = KD_SPINLOCK_INITIALIZER;

	preempt_disable();
	kd_spin_direct_native_lock_inline(&outer);
	for (unsigned int bh = 0; bh < 2; bh++) {
		for (unsigned int i = 0; i < sizeof(words) / sizeof(words[0]); i++) {
			struct route_snapshot before = route_snapshot();

			atomic_set(&lock.gate.val, words[i]);
			atomic_set(&lock.cnts, KD_RWLOCK_WRITER_WAITING);
			expect_reservation(before);
			if (bh) kd_read_lock_bh(&lock);
			else { hardirq_depth++; kd_read_lock(&lock); }
			assert_route(before, 1, 1, 0, 0, 0);
			assert((u32)atomic_read(&lock.gate.val) == words[i]);
			assert(atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_WAITING + KD_RWLOCK_READER_BIAS);
			check_reservation = false;
			if (bh) kd_read_unlock_bh(&lock);
			else { kd_read_unlock(&lock); hardirq_depth--; }
			assert(atomic_read(&lock.cnts) == KD_RWLOCK_WRITER_WAITING);
			assert((u32)atomic_read(&lock.gate.val) == words[i]);
			atomic_set(&lock.cnts, 0);
			atomic_set(&lock.gate.val, 0);
		}
	}
	kd_spin_direct_native_release_inline(&outer);
	preempt_enable();
	assert(!pins && !gates && !kd_spin_fast_cpu.nondelegated);
}

static void native_gate_release_bytes(void)
{
	kd_spinlock_t gate = KD_SPINLOCK_INITIALIZER;
	struct route_snapshot before = route_snapshot();

	preempt_disable();
	expect_reservation(before);
	kd_spin_direct_native_lock_inline(&gate);
	/* A pending waiter and encoded tail may be published after acquisition. */
	atomic_add(0x12340100, &gate.val);
	kd_spin_direct_native_release_inline(&gate);
	assert((u32)atomic_read(&gate.val) == 0x12340100);
	assert_route(before, 1, 0, 1, 0, 1);
	check_reservation = false;
	preempt_enable();
	atomic_set(&gate.val, 0);
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

int main(int argc, char **argv)
{
	pthread_t workers[10];
	struct route_snapshot before = route_snapshot();

	/* Fast reads must not reserve a gate, sample heat, or inspect context. */
	kd_read_lock(&lock);
	assert_route(before, 0, 0, 0, 0, 0);
	kd_read_unlock(&lock);
	gate_becomes_free();
	interrupt_pending_tail();
	native_gate_release_bytes();
	fast_ordering();
	interrupt_active_writer();
	interrupt_readers();
	interrupt_writer_wins_gap();
	if (argc > 1) {
		assert(argc == 2 && !strcmp(argv[1], "--routes-only"));
		puts("PASS rwlock native gate routes: exact references, context/heat, IRQ/BH bypass and writer-gap ordering");
		return 0;
	}
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
	/* The earlier route cases used the same bounded writer controls. */
	atomic_set(&writer_inside, 0);
	atomic_set(&release_writer, 0);
	ordering();
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
	puts("PASS rwlock: concurrent readers, writer exclusion/intent, mixed progress, release ordering, IRQ/BH/try APIs, interrupt reader bypass, writer-wins-gap, production gate accounting and balanced pins");
}
