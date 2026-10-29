/* SPDX-License-Identifier: GPL-2.0 */
/* Actual versioned records and diagnostic snapshot. Kernel allocation and
 * CPU storage are substitutes; atomics and scheduled read/write windows are
 * real userspace operations. This is not a weak-memory hardware proof. */
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "exe_info.h"
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
typedef struct { unsigned long counter; } atomic_long_t;
typedef int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct task_struct;
/* This fixture exercises an ordinary path with no installed owner custody. */
#define DECLARE_PER_CPU(type, name) extern type name
#define raw_cpu_read(name) ((void)sizeof(name), 0UL)
#ifndef unlikely
#define unlikely(x) (x)
#endif
#include "mutex_count_types.h"
#define CHECK(c) do { if (!(c)) { \
 fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
#define BUG_ON(c) do { if (c) { fprintf(stderr, "BUG line %d\n", __LINE__); exit(2); } } while (0)
#define U64_MAX UINT64_MAX
#define GFP_ATOMIC 0
#define TEST_CPUS 4
#define POSSIBLE_CPUS 3 /* IDs 0, 1 and 3: scratch must cover nr_cpu_ids. */
static const int nr_cpu_ids = TEST_CPUS;
static struct kd_mutex_node kd_mutex_nodes[KD_MUTEX_MAX_NODES];
static struct kd_mutex_node remote_nodes[TEST_CPUS - 1][KD_MUTEX_MAX_NODES];
static struct kd_mutex first_lock, second_lock;
static bool allocation_failure;
static unsigned int allocations, frees, relaxations;
static _Thread_local bool observer_active;
static _Thread_local unsigned int inject, a_seq_reads, injected;
static void before_read(const void *address);
static void before_write(const void *address);
#define READ_ONCE(x) ({ before_read(&(x)); __atomic_load_n(&(x), __ATOMIC_SEQ_CST); })
#define WRITE_ONCE(x,v) do { before_write(&(x)); __atomic_store_n(&(x),(v),__ATOMIC_SEQ_CST); } while (0)
#define smp_load_acquire(p) ({ before_read(p); __atomic_load_n((p), __ATOMIC_SEQ_CST); })
#define smp_rmb() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define smp_wmb() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define atomic_read(p) __atomic_load_n(&(p)->counter, __ATOMIC_RELAXED)
#define atomic_read_acquire(p) __atomic_load_n(&(p)->counter, __ATOMIC_SEQ_CST)
#define atomic_fetch_andnot_release(v,p) __atomic_fetch_and(&(p)->counter, ~(u32)(v), __ATOMIC_RELEASE)
#define atomic_set_release(p,v) __atomic_store_n(&(p)->counter, (v), __ATOMIC_SEQ_CST)
#define atomic_cmpxchg(p,o,v) ({ int expected = (o); \
 __atomic_compare_exchange_n(&(p)->counter,&expected,(v),false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST); expected; })
#define for_each_possible_cpu(cpu) for ((cpu) = 0; (cpu) < TEST_CPUS; (cpu)++) if ((cpu) != 2)
static struct kd_mutex_node *fixture_node(struct kd_mutex_node *node, int cpu)
{
 ptrdiff_t idx = node - kd_mutex_nodes;
 CHECK(idx >= 0 && idx < KD_MUTEX_MAX_NODES && cpu >= 0 && cpu < TEST_CPUS);
 return cpu ? &remote_nodes[cpu - 1][idx] : node;
}
#define per_cpu_ptr(p,cpu) fixture_node(p,cpu)
static void *kmalloc_array(size_t count, size_t size, int flags)
{
 CHECK(flags == GFP_ATOMIC && count == TEST_CPUS * KD_MUTEX_MAX_NODES && size == sizeof(u64));
 allocations++;
 return allocation_failure ? NULL : calloc(count, size);
}
static void kfree(void *pointer) { CHECK(pointer); frees++; free(pointer); }
static void cpu_relax(void) { relaxations++; }
#include "mutex_count_actual.h"
static struct kd_mutex_node *node_a(void) { return &kd_mutex_nodes[0]; }
static struct kd_mutex_node *node_b(void) { return &remote_nodes[TEST_CPUS - 2][KD_MUTEX_MAX_NODES - 1]; }
static void before_read(const void *address)
{
 if (!observer_active)
  return;
 if (address == &node_a()->count_seq)
  a_seq_reads++;
 bool trigger = (inject == 1 || inject == 2) && address == &node_b()->count_seq;
 trigger |= inject == 3 && address == &node_a()->count_seq && a_seq_reads % 3 == 0;
 if (!trigger)
  return;
 unsigned int mode = inject;
 if (mode != 3) inject = 0;
 injected++;
 observer_active = false;
 kd_mutex_count_exit(&first_lock, node_a());
 if (mode == 1) kd_mutex_count_enter(&first_lock, node_b());
 else kd_mutex_count_enter(&first_lock, node_a());
 observer_active = true;
}
static void before_write(const void *address)
{
 /* Every identity publication must be bracketed by an odd generation. This
  * assertion is independent of snapshot acceptance and catches missing guards. */
 for (int cpu = 0; cpu < TEST_CPUS; cpu++) {
  if (cpu == 2) continue;
  for (int idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
   struct kd_mutex_node *node = fixture_node(&kd_mutex_nodes[idx], cpu);
   if (address == &node->counted_lock)
    CHECK(__atomic_load_n(&node->count_seq, __ATOMIC_SEQ_CST) & 1);
  }
 }
}
static void reset(void)
{
 memset(kd_mutex_nodes, 0, sizeof(kd_mutex_nodes));
 memset(remote_nodes, 0, sizeof(remote_nodes));
 memset(&first_lock, 0, sizeof(first_lock));
 memset(&second_lock, 0, sizeof(second_lock));
 allocation_failure = false;
 allocations = frees = relaxations = 0;
 observer_active = false; inject = a_seq_reads = injected = 0;
}
static int observe(struct kd_mutex *lock)
{
 observer_active = true;
 int result = kd_mutex_waiter_count(lock);
 observer_active = false;
 return result;
}
static void check_stable_and_idle(void)
{
 reset();
 CHECK(observe(NULL) == -EINVAL && !allocations);
 CHECK(!observe(&first_lock) && allocations == frees);
 CHECK(kd_mutex_count_records_idle() && kd_mutex_waiters_idle(&first_lock));
 CHECK(!kd_mutex_waiters_idle(NULL));
 for (int cpu = 0; cpu < TEST_CPUS; cpu++) {
  if (cpu == 2) continue;
  for (int idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
   struct kd_mutex_node *node = fixture_node(&kd_mutex_nodes[idx], cpu);
   kd_mutex_count_enter(&first_lock, node);
  }
 }
 CHECK(observe(&first_lock) == POSSIBLE_CPUS * KD_MUTEX_MAX_NODES);
 CHECK(!observe(&second_lock));
 CHECK(!kd_mutex_count_records_idle() && !kd_mutex_waiters_idle(&first_lock));
 CHECK(kd_mutex_waiters_idle(&second_lock));
 kd_mutex_count_exit(&first_lock, node_b());
 kd_mutex_count_enter(&second_lock, node_b());
 CHECK(observe(&first_lock) == POSSIBLE_CPUS * KD_MUTEX_MAX_NODES - 1);
 CHECK(observe(&second_lock) == 1);
 for (int cpu = 0; cpu < TEST_CPUS; cpu++) {
  if (cpu == 2) continue;
  for (int idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
   struct kd_mutex_node *node = fixture_node(&kd_mutex_nodes[idx], cpu);
   kd_mutex_count_exit(node == node_b() ? &second_lock : &first_lock, node);
  }
 }
 CHECK(kd_mutex_count_records_idle() && kd_mutex_waiters_idle(&first_lock));
 CHECK(kd_mutex_waiters_idle(&second_lock) && allocations == frees);
 node_a()->count_seq = 1;
 CHECK(!kd_mutex_count_records_idle()); /* A paused transition forbids global drain. */
}
static void check_interleavings_and_refusals(void)
{
 reset();
 kd_mutex_count_enter(&first_lock, node_a());
 inject = 1;
 /* A is retired before B enters: actual count never exceeds one. A single
  * sweep sees both; only the final version pass prevents impossible count2. */
 CHECK(observe(&first_lock) == 1 && injected == 1);
 CHECK(relaxations >= 1 && !node_a()->counted_lock && node_b()->counted_lock == &first_lock);
 CHECK(allocations == frees);
 reset(); kd_mutex_count_enter(&first_lock, node_a());
 inject = 2;
 CHECK(observe(&first_lock) == 1 && injected == 1);
 CHECK(a_seq_reads >= 6 && relaxations >= 1); /* Same address/key is a new generation. */
 CHECK(node_a()->count_seq == 6 && allocations == frees);
 reset(); kd_mutex_count_enter(&first_lock, node_a());
 inject = 3;
 CHECK(observe(&first_lock) == -EAGAIN);
 CHECK(injected == KD_MUTEX_COUNT_SCAN_RETRIES && relaxations == KD_MUTEX_COUNT_SCAN_RETRIES);
 CHECK(allocations == frees); /* Repeated valid reuse cannot become an estimate. */
 reset(); node_a()->count_seq = 1;
 CHECK(observe(&first_lock) == -EAGAIN);
 CHECK(relaxations == KD_MUTEX_COUNT_SCAN_RETRIES && allocations == frees);
 reset(); allocation_failure = true;
 CHECK(observe(&first_lock) == -ENOMEM && allocations == 1 && !frees && !a_seq_reads);
}
#define WORKERS 8
static pthread_barrier_t rendezvous;
static void barrier(void)
{
 int result = pthread_barrier_wait(&rendezvous);
 CHECK(!result || result == PTHREAD_BARRIER_SERIAL_THREAD);
}
static struct kd_mutex_node *worker_node(size_t worker)
{
 return fixture_node(&kd_mutex_nodes[worker % KD_MUTEX_MAX_NODES], worker / KD_MUTEX_MAX_NODES);
}
static void *count_worker(void *arg)
{
 struct kd_mutex_node *node = worker_node((size_t)arg);
 barrier();
 kd_mutex_count_enter(&first_lock, node);
 barrier(); barrier();
 kd_mutex_count_exit(&first_lock, node);
 for (int i = 0; i < 1000; i++) {
  kd_mutex_count_enter(&first_lock, node);
  kd_mutex_count_exit(&first_lock, node);
 }
 return NULL;
}
static void check_concurrent_records(void)
{
 pthread_t threads[WORKERS];
 reset();
 /* A permanent ninth record forbids zero even during unrelated slot churn. */
 kd_mutex_count_enter(&first_lock, node_b());
 CHECK(!pthread_barrier_init(&rendezvous, NULL, WORKERS + 1));
 for (size_t i = 0; i < WORKERS; i++) CHECK(!pthread_create(&threads[i], NULL, count_worker, (void *)i));
 barrier(); barrier();
 CHECK(observe(&first_lock) == WORKERS + 1);
 barrier();
 for (int i = 0; i < 1000; i++) {
  int count = observe(&first_lock);
  CHECK(count == -EAGAIN || (count >= 1 && count <= WORKERS + 1));
 }
 for (int i = 0; i < WORKERS; i++) CHECK(!pthread_join(threads[i], NULL));
 CHECK(observe(&first_lock) == 1);
 kd_mutex_count_exit(&first_lock, node_b());
 CHECK(!observe(&first_lock) && kd_mutex_count_records_idle());
 CHECK(allocations == frees && !pthread_barrier_destroy(&rendezvous));
}
int main(void)
{
 check_stable_and_idle();
 check_interleavings_and_refusals();
 check_concurrent_records();
 puts("PASS exact mutex count: stable global cut, same-key reuse, odd records, bounded EAGAIN, ENOMEM, sparse CPU slots, 8 concurrent writers and exact drain");
 return 0;
}
