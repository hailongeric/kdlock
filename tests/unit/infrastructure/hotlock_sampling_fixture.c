/* SPDX-License-Identifier: GPL-2.0 */
/* Compile the real sampler with a deterministic clock and CPU-local state.
 * Each pthread represents one CPU; callbacks model same-CPU IRQ reentry or a
 * state transition while an evaluator is paused. This is not a kernel IRQ test. */
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned long atomic_long_t;
typedef unsigned int atomic_t;
static _Thread_local unsigned long now;
static _Thread_local unsigned int clocks, pins, shared_reads, shared_writes;
static void note_shared(const void *p, bool write);
static _Thread_local void (*during_clock)(void);
static int checks, failures;
static bool fail_alloc, fail_percpu;
static _Thread_local unsigned int cpu_id;
static size_t percpu_stride;
#define TEST_CPUS 8
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))

#define ____cacheline_aligned __attribute__((aligned(64)))
#define __percpu
#define alloc_percpu(type) (percpu_stride = sizeof(type), fail_percpu ? NULL : calloc(TEST_CPUS, sizeof(type)))
#define free_percpu(p) free(p)
#define per_cpu_ptr(p, cpu) ((__typeof__(p))((char *)(p) + percpu_stride * (cpu)))
#define for_each_possible_cpu(cpu) for ((cpu) = 0; (cpu) < TEST_CPUS; (cpu)++)
#define this_cpu_ptr(p) per_cpu_ptr(p, cpu_id)
#define this_cpu_write(p, v) WRITE_ONCE(*this_cpu_ptr(&(p)), v)
#define this_cpu_cmpxchg(p, o, n) cmpxchg(this_cpu_ptr(&(p)), o, n)
#define READ_ONCE(v) (note_shared(&(v), false), __atomic_load_n(&(v), __ATOMIC_RELAXED))
#define WRITE_ONCE(v, n) __atomic_store_n(&(v), (n), __ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define smp_store_release(p, n) __atomic_store_n((p), (n), __ATOMIC_RELEASE)
#define atomic_long_read(p) READ_ONCE(*(p))
#define atomic_long_set(p, n) WRITE_ONCE(*(p), n)
#define atomic_read(p) READ_ONCE(*(p))
#define atomic_long_cmpxchg(p, o, n) cmpxchg(p, o, n)
#define atomic_add_return(n, p) __atomic_add_fetch(p, n, __ATOMIC_SEQ_CST)
#define array_size(count, size) ((count) * (size))
#define barrier() __asm__ __volatile__("" ::: "memory")
#define preempt_disable() do { pins++; } while (0)
#define preempt_enable() do { if (!pins) abort(); pins--; } while (0)
#define cmpxchg(p, o, n) ({ \
	__typeof__(*(p)) old_ = (o); note_shared((p), true); \
	__atomic_compare_exchange_n(p, &old_, n, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); \
	old_; })
#define xchg(p, n) __atomic_exchange_n(p, n, __ATOMIC_SEQ_CST)
#define KD_PR_INFO(...) do { if (0) printf(__VA_ARGS__); } while (0)
#define CHECK(expr) do { \
	checks++; \
	if (!(expr)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expr); failures++; } \
} while (0)

static unsigned long hash_long(unsigned long value, unsigned int bits)
{
	return (value * 0x61C8864680B583EBul) >> (64 - bits);
}
static unsigned long rdtsc_ordered(void)
{
	unsigned long sampled = now;
	void (*callback)(void) = during_clock;
	clocks++;
	during_clock = NULL;
	if (callback)
		callback();
	return sampled;
}
static void *vzalloc(size_t size)
{
	void *p;
	if (fail_alloc || posix_memalign(&p, 64, size))
		return NULL;
	memset(p, 0, size);
	return p;
}
static void vfree(void *p) { free(p); }

#include "hotlock_production.h"

#define QUOTA KD_HOTLOCK_CHECK_INTERVAL

/* Count access to the actual global set (including its root pointer), not
 * CPU-local traffic or the immutable percpu allocation base. */
static void note_shared(const void *p, bool write)
{
    unsigned long value = (unsigned long)p, base = (unsigned long)kd_hotlocks;
    if (p == &kd_hotlocks || (base && value >= base &&
        value < base + KD_HOTLOCK_TABLE_SIZE * sizeof(*kd_hotlocks))) {
        if (write) shared_writes++;
        else shared_reads++;
    }
}
static void record_n(unsigned long addr, unsigned int n)
{
    for (unsigned int i = 0; i < n; i++) kd_hotlock_record(addr);
}
static struct kd_hotlock_local *local_at(unsigned long key)
{
    return &this_cpu_ptr(kd_hotlock_cpu)->slots[hash_long(key, KD_HOTLOCK_LOCAL_BITS)];
}
static void start_sampling(void)
{
    cpu_id = 0;
    CHECK(kd_hotlock_init() == 0);
    now = 100;
    clocks = pins = shared_reads = shared_writes = 0;
}
static void open_cpu(void)
{
    record_n(1, QUOTA);
    CHECK(this_cpu_ptr(kd_hotlock_cpu)->rate_hot);
    CHECK(!pins);
}
static void check_cpu_and_local_gates(void)
{
    unsigned int c, r, w;
    start_sampling();
    record_n(23, QUOTA - 1);
    CHECK(!this_cpu_ptr(kd_hotlock_cpu)->rate_hot);
    CHECK(clocks == 1 && !shared_reads && !shared_writes);
    CHECK(kd_hotlock_record(23) == 0);
    CHECK(this_cpu_ptr(kd_hotlock_cpu)->rate_hot && clocks == 2);
    CHECK(local_at(23)->samples == 1);
    CHECK(!shared_reads && !shared_writes);
    record_n(23, QUOTA - 1);
    CHECK(clocks == 2 && !shared_reads && !shared_writes);
    CHECK(local_at(23)->samples == KD_HOTLOCK_SAMPLE_TARGET);
    CHECK(kd_hotlock_record(23) == 1);
    CHECK(clocks == 3 && shared_writes == 1 && kd_hotlock_is_promoted(23));
    c = clocks; r = shared_reads; w = shared_writes;
    record_n(23, QUOTA * 3);
    CHECK(clocks == c + 3 && shared_reads == r && shared_writes == w);
    /* CPU1 neither uses CPU0's samples nor queries CPU0's shared positive. */
    cpu_id = 1;
    r = shared_reads; w = shared_writes;
    record_n(23, QUOTA * 2 - 1);
    CHECK(shared_reads == r && shared_writes == w);
    CHECK(kd_hotlock_record(23) == 1 && shared_reads > r && shared_writes == w);
    /* Cooling preserves the identity, but closes fresh root admission. */
    cpu_id = 0;
    now += KD_HOTLOCK_CPU_WINDOW;
    record_n(23, QUOTA - 1);
    CHECK(this_cpu_ptr(kd_hotlock_cpu)->rate_hot);
    CHECK(kd_hotlock_record(23) == 0 && !this_cpu_ptr(kd_hotlock_cpu)->rate_hot);
    CHECK(kd_hotlock_is_promoted(23));
    r = shared_reads; w = shared_writes;
    record_n(23, QUOTA - 1);
    CHECK(kd_hotlock_record(23) == 1);
    CHECK(shared_reads == r && shared_writes == w);
    now--;
    record_n(23, QUOTA);
    CHECK(!this_cpu_ptr(kd_hotlock_cpu)->rate_hot);
    CHECK(!pins);
    kd_hotlock_exit();
}
static void check_lock_windows(void)
{
    for (unsigned int equal = 0; equal < 2; equal++) {
        start_sampling(); open_cpu();
        record_n(23, QUOTA - 1);
        now += KD_HOTLOCK_INITIAL_WINDOW - !equal;
        CHECK(kd_hotlock_record(23) == !equal);
        CHECK(kd_hotlock_is_promoted(23) == !equal);
        if (equal) {
            unsigned int r = shared_reads, w = shared_writes;
            /* Cold discovery is wholly local and can retry a fresh window. */
            CHECK(local_at(23)->samples == 1);
            record_n(23, QUOTA - 1);
            CHECK(shared_reads == r && shared_writes == w);
            CHECK(kd_hotlock_record(23) == 1);
        }
        kd_hotlock_exit();
    }
    start_sampling(); open_cpu();
    record_n(23, QUOTA - 1);
    now--;
    CHECK(kd_hotlock_record(23) == 0);
    CHECK(!shared_reads && !shared_writes);
    CHECK(local_at(23)->samples == 0);
    record_n(23, QUOTA);
    CHECK(this_cpu_ptr(kd_hotlock_cpu)->rate_hot);
    record_n(23, QUOTA);
    CHECK(kd_hotlock_is_promoted(23));
    kd_hotlock_exit();
}
static void check_collisions_and_sparse_keys(void)
{
    unsigned long a = 23, b = a + 1;
    unsigned int c, r, w;
    while (hash_long(a, KD_HOTLOCK_LOCAL_BITS) != hash_long(b, KD_HOTLOCK_LOCAL_BITS)) b++;
    start_sampling(); open_cpu();
    c = clocks;
    for (unsigned int i = 0; i < QUOTA; i++) {
        kd_hotlock_record(a); kd_hotlock_record(b);
    }
    CHECK(clocks == c + 2 && !shared_reads && !shared_writes);
    CHECK(!local_at(b)->promoted && local_at(b)->samples == 1);
    record_n(a, QUOTA + 1);
    CHECK(kd_hotlock_is_promoted(a));
    /* A positive belongs to its exact address, never the colliding key. */
    r = shared_reads; w = shared_writes;
    CHECK(kd_hotlock_record(b) == 0);
    CHECK(!local_at(b)->promoted && local_at(b)->samples == 1);
    CHECK(shared_reads == r && shared_writes == w);
    c = clocks;
    for (unsigned int i = 0; i < QUOTA * 2; i++) kd_hotlock_record(1000000UL + i);
    CHECK(clocks == c + 2 && shared_reads == r && shared_writes == w);
    kd_hotlock_exit();
}
static void reenter(void)
{
    unsigned int saved = pins;
    CHECK(kd_hotlock_record(91) == 0);
    CHECK(pins == saved && this_cpu_ptr(kd_hotlock_cpu)->busy == 1);
    CHECK(!shared_reads && !shared_writes);
}
static void publish_elsewhere(void)
{
    CHECK(kd_hotlock_lookup(23, true));
}
static void check_reentry_and_publication(void)
{
    start_sampling();
    during_clock = reenter;
    open_cpu();
    CHECK(!during_clock && !pins && !this_cpu_ptr(kd_hotlock_cpu)->busy);
    record_n(23, QUOTA - 1);
    during_clock = publish_elsewhere;
    now += KD_HOTLOCK_INITIAL_WINDOW;
    CHECK(kd_hotlock_record(23) == 0);
    /* A late local expiry cannot undo another CPU/test's published identity. */
    CHECK(kd_hotlock_is_promoted(23) && !local_at(23)->promoted);
    record_n(23, QUOTA);
    CHECK(local_at(23)->promoted);
    kd_hotlock_exit();
}

enum { WRITERS = 4, READERS = 2, LOCKS = 4 };
static pthread_barrier_t start_workers;
static unsigned int writers_done;
static unsigned long concurrent_addr(unsigned int i)
{
    /* Keep global collisions, but leave local eviction to its own test. */
    if (i >= 3) i++;
    return KD_HOTLOCK_TABLE_SIZE - 1 + (unsigned long)i * KD_HOTLOCK_TABLE_SIZE;
}
static void *sample_concurrently(void *unused)
{
    cpu_id = (unsigned long)unused;
    now = 100000;
    pthread_barrier_wait(&start_workers);
    record_n(1, QUOTA);
    for (unsigned int n = 0; n <= QUOTA; n++)
        for (unsigned int i = 0; i < LOCKS; i++) kd_hotlock_record(concurrent_addr(i));
    __atomic_add_fetch(&writers_done, 1, __ATOMIC_RELEASE);
    return NULL;
}
static void *lookup_concurrently(void *result)
{
    bool seen[LOCKS] = { false }, *valid = result;
    *valid = true;
    pthread_barrier_wait(&start_workers);
    do {
        for (unsigned int i = 0; i < LOCKS; i++) {
            bool hot = kd_hotlock_is_promoted(concurrent_addr(i));
            if (seen[i] && !hot) *valid = false;
            seen[i] = hot;
        }
        if (kd_hotlock_is_promoted(concurrent_addr(LOCKS))) *valid = false;
    } while (smp_load_acquire(&writers_done) != WRITERS);
    return NULL;
}
static void check_concurrent_lookup(void)
{
    pthread_t writers[WRITERS], readers[READERS];
    bool valid[READERS] = { false };
    start_sampling();
    WRITE_ONCE(writers_done, 0);
    CHECK(pthread_barrier_init(&start_workers, NULL, WRITERS + READERS) == 0);
    for (unsigned int i = 0; i < WRITERS; i++)
        if (pthread_create(&writers[i], NULL, sample_concurrently, (void *)(unsigned long)(i + 1))) abort();
    for (unsigned int i = 0; i < READERS; i++)
        if (pthread_create(&readers[i], NULL, lookup_concurrently, &valid[i])) abort();
    for (unsigned int i = 0; i < WRITERS; i++) CHECK(!pthread_join(writers[i], NULL));
    for (unsigned int i = 0; i < READERS; i++) {
        CHECK(!pthread_join(readers[i], NULL)); CHECK(valid[i]);
    }
    for (unsigned int i = 0; i < LOCKS; i++) {
        unsigned int matches = 0;
        CHECK(kd_hotlock_is_promoted(concurrent_addr(i)));
        for (unsigned int j = 0; j < KD_HOTLOCK_TABLE_SIZE; j++)
            matches += kd_hotlocks[j] == concurrent_addr(i);
        CHECK(matches == 1);
    }
    CHECK(!pthread_barrier_destroy(&start_workers));
    kd_hotlock_exit();
}
static void check_lifecycle_and_capacity(void)
{
    fail_alloc = true;
    CHECK(kd_hotlock_init() == -ENOMEM && !kd_hotlocks && !kd_hotlock_cpu);
    fail_alloc = false; fail_percpu = true;
    CHECK(kd_hotlock_init() == -ENOMEM && !kd_hotlocks && !kd_hotlock_cpu);
    fail_percpu = false;
    start_sampling(); open_cpu();
    CHECK(sizeof(*kd_hotlocks) == 8 && sizeof(struct kd_hotlock_cpu) == 1600);
    CHECK(!kd_hotlock_lookup(0, true) && kd_hotlock_record(0) == 0);
    for (unsigned int i = 1; i <= KD_HOTLOCK_TABLE_SIZE; i++) CHECK(kd_hotlock_lookup(i, true));
    CHECK(!kd_hotlock_lookup(0xdeadbeef, true));
    record_n(0xdeadbeef, QUOTA * 2);
    CHECK(kd_hotlock_record(0xdeadbeef) == 0);
    CHECK(!local_at(0xdeadbeef)->promoted && !kd_hotlock_is_promoted(0xdeadbeef));
    kd_hotlock_exit();
    CHECK(!kd_hotlock_is_promoted(1) && kd_hotlock_record(1) == 0);
}
int main(void)
{
    check_cpu_and_local_gates();
    check_lock_windows();
    check_collisions_and_sparse_keys();
    check_reentry_and_publication();
    check_concurrent_lookup();
    check_lifecycle_and_capacity();
    printf("hotlock local discovery: %d checks, %d failures, shared slot=%zu bytes\n",
           checks, failures, sizeof(*kd_hotlocks));
    return failures != 0;
}
