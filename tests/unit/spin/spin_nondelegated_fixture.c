/* Real production C with pthread peers. No request/frame substitute exists:
 * attempting to use one on the native path must fail this fixture's build. */
#include <assert.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef uint32_t u32;
typedef struct { u32 counter; } atomic_t;
struct qspinlock {
 union { atomic_t val; struct { uint8_t locked, pending; uint16_t tail; }; uint16_t locked_pending; };
};
#define noinline __attribute__((noinline))
#define MAX_NODES 4
#define CPUS 8
#define IRQ_NUMA_NODE 255
#define _Q_LOCKED_VAL_HL 1U
#define _Q_LOCKED_MASK_HL 255U
#define _Q_PENDING_VAL_HL 256U
#define _Q_PENDING_MASK_HL 65280U
#define _Q_TAIL_MASK_HL 0xffff0000U
#define _Q_LOCKED_PENDING_MASK 65535U
#define _Q_PENDING_LOOPS_HL 1U
struct kd_spin_node {
 struct kd_spin_node *next;
 int socket_id, cpuid;
 unsigned long rsp;
 void *execution;
 uint8_t locked __attribute__((aligned(64)));
 bool completed;
} __attribute__((aligned(64)));
static struct kd_spin_node pool[CPUS][MAX_NODES];
static struct { int node_count; } states[CPUS];
static _Thread_local int cpu;
static _Thread_local unsigned long queued, swaps, cas_calls, local_reads;
#define kd_spin_nodes (pool[cpu])
#define kd_spin_cpu (states[cpu])
#define this_cpu_ptr(p) (p)
#define this_cpu_inc_return(x) (++(x))
#define this_cpu_dec(x) (--(x))
#define smp_processor_id() cpu
#define barrier() __asm__ __volatile__("" ::: "memory")
#define cpu_relax() __asm__ __volatile__("pause" ::: "memory")
#define unlikely(x) (x)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define smp_wmb() __atomic_thread_fence(__ATOMIC_RELEASE)
#define smp_store_release(p, v) __atomic_store_n(p, v, __ATOMIC_RELEASE)
#define LOAD_UNTIL(p, condition, order) ({ \
 __auto_type pointer = (p); __typeof__(*pointer) VAL; \
 do { VAL = __atomic_load_n(pointer, order); if (condition) break; cpu_relax(); } while (1); VAL; })
#define atomic_cond_read_relaxed(p, c) LOAD_UNTIL(&(p)->counter, c, __ATOMIC_RELAXED)
#define atomic_cond_read_acquire(p, c) LOAD_UNTIL(&(p)->counter, c, __ATOMIC_ACQUIRE)
#define smp_cond_load_relaxed_sched(p, c) LOAD_UNTIL(p, c, __ATOMIC_RELAXED)
#define smp_cond_load_acquire_sched(p, c) ({ local_reads++; LOAD_UNTIL(p, c, __ATOMIC_ACQUIRE); })
static u32 atomic_cmpxchg_acquire(atomic_t *p, u32 expected, u32 value)
{
 cas_calls++;
 __atomic_compare_exchange_n(&p->counter, &expected, value, false, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
 return expected;
}
#define atomic_try_cmpxchg_relaxed(p, expected, value) \
 (cas_calls++, __atomic_compare_exchange_n(&(p)->counter, expected, value, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED))
static u32 encode_tail(int c, int idx) { return ((c + 1) << 18) | (idx << 16); }
static struct kd_spin_node *decode_tail(u32 tail) { return &pool[(tail >> 18) - 1][(tail >> 16) & 3]; }
/* Run the production publication boundary; only its atomic primitive and
 * sampler are substituted. Every queued operation must record exactly once. */
#define _Q_TAIL_OFFSET_HL 16
static bool kd_spin_delegate = true;
static _Thread_local unsigned long mcs_samples;
static void kd_hotlock_record_spin_mcs_pinned(void) { mcs_samples++; }
#define xchg(p,v) (queued++, swaps++, __atomic_exchange_n(p,v,__ATOMIC_ACQ_REL))
#include "spin_mcs_tail.h"
static u32 kd_spin_fetch_set_pending_acquire(struct qspinlock *p)
{ return __atomic_fetch_or(&p->val.counter, 256, __ATOMIC_ACQUIRE); }
static void clear_pending(struct qspinlock *p) { __atomic_fetch_and(&p->val.counter, ~256U, __ATOMIC_RELAXED); }
static void clear_pending_set_locked(struct qspinlock *p) { __atomic_store_n(&p->locked_pending, 1, __ATOMIC_RELAXED); }
static void set_locked(struct qspinlock *p) { __atomic_store_n(&p->locked, 1, __ATOMIC_RELAXED); }
#include "kernel_module/spin/nondelegated.inc"

static struct qspinlock lock;
static pthread_barrier_t start;
static unsigned long value, queue_total, read_total;
static unsigned int inside;
static void *worker(void *arg)
{
 cpu = (long)arg;
 pthread_barrier_wait(&start);
 for (int i=0;i<50000;i++) {
  kd_spin_acquire_nondelegated(&lock);
  assert(!__atomic_fetch_add(&inside, 1, __ATOMIC_RELAXED));
  value++;
  assert(__atomic_fetch_sub(&inside, 1, __ATOMIC_RELAXED)==1);
  smp_store_release(&lock.locked, 0);
  assert(states[cpu].node_count==0);
 }
 /* One initial CAS, and at most one queue-tail claim CAS per operation.
  * Failed contender retries must be loads/local waits, not global RMWs. */
 assert(cas_calls>=50000 && cas_calls<=100000 && swaps==queued && mcs_samples==queued);
 __atomic_fetch_add(&queue_total, queued, __ATOMIC_RELAXED);
 __atomic_fetch_add(&read_total, local_reads, __ATOMIC_RELAXED);
 return NULL;
}
int main(void)
{
 pthread_t threads[CPUS];
 /* Delegation-off preserves the protocol but disables CPU statistics. */
 struct qspinlock disabled={0};
 kd_spin_delegate=false;
 assert(!xchg_tail(&disabled,1U<<16) && disabled.tail==1 && !mcs_samples);
 kd_spin_delegate=true; queued=swaps=0;
 pthread_barrier_init(&start, NULL, CPUS);
 for (long i=0;i<CPUS;i++) assert(!pthread_create(&threads[i], NULL, worker, (void *)i));
 for (int i=0;i<CPUS;i++) assert(!pthread_join(threads[i], NULL));
 assert(value==CPUS*50000UL && !lock.val.counter && queue_total && read_total);
 /* A pre-existing reserved slot must survive a later nondelegating waiter. */
 cpu=0; states[0].node_count=1; pool[0][0].rsp=0x1234;
 kd_spin_acquire_nondelegated(&lock);
 assert(states[0].node_count==1 && pool[0][0].rsp==0x1234);
 smp_store_release(&lock.locked,0); states[0].node_count=0;
 printf("PASS native MCS: %lu exact operations, %lu queued, %lu local waits, no request/frame or CAS retry storm\n",value,queue_total,read_total);
}
