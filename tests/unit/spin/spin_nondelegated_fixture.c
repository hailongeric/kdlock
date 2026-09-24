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
typedef struct qspinlock kd_spinlock_t;
#define __percpu
#define KD_SPIN_DIRECT_NATIVE_HELD 5U
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
static _Thread_local unsigned int pins, rate_hot;
static _Thread_local struct { unsigned int nondelegated; } kd_spin_fast_cpu;
#define preempt_disable() (++pins)
#define preempt_enable() (--pins)
#define kd_spin_nodes (pool[cpu])
#define kd_spin_cpu (states[cpu])
#define this_cpu_ptr(p) (p)
#define this_cpu_inc_return(x) (++(x))
#define this_cpu_dec(x) (--(x))
#define this_cpu_inc(x) (++(x))
#define this_cpu_read(x) (x)
#define smp_processor_id() cpu
#define barrier() __asm__ __volatile__("" ::: "memory")
#define cpu_relax() __asm__ __volatile__("pause" ::: "memory")
#define unlikely(x) (x)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x), v, __ATOMIC_RELAXED)
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
/* Run the production publication boundary; only atomic primitives and the
 * CPU clock are substituted. Each MCS publication must count exactly once. */
#define _Q_TAIL_OFFSET_HL 16
static bool kd_spin_delegate = true;
static unsigned int thread_count;
static _Thread_local unsigned long mcs_samples;
static _Thread_local unsigned long physical_entries;
static void kd_hotlock_record_spin_mcs_pinned(void) { mcs_samples++; rate_hot=1; }
static void kd_hotlock_spin_entry_pinned(void)
{ assert(pins); physical_entries++; }
#define in_task() true
#define smp_load_acquire(p) __atomic_load_n(p, __ATOMIC_ACQUIRE)
#define xchg(p,v) (queued++, swaps++, __atomic_exchange_n(p,v,__ATOMIC_ACQ_REL))
#include "spin_mcs_tail.h"
static u32 kd_spin_fetch_set_pending_acquire(struct qspinlock *p)
{ return __atomic_fetch_or(&p->val.counter, 256, __ATOMIC_ACQUIRE); }
static void clear_pending(struct qspinlock *p) { __atomic_fetch_and(&p->val.counter, ~256U, __ATOMIC_RELAXED); }
static void clear_pending_set_locked(struct qspinlock *p) { __atomic_store_n(&p->locked_pending, 1, __ATOMIC_RELAXED); }
static void set_locked(struct qspinlock *p) { __atomic_store_n(&p->locked, 1, __ATOMIC_RELAXED); }
#include "kernel_module/spin/nondelegated.inc"
#include "spin_direct_native.h"

static struct qspinlock lock;
static pthread_barrier_t start;
static unsigned long value, queue_total, read_total, sample_total;
static unsigned int inside;
static void *worker(void *arg)
{
 cpu = (long)arg;
 pthread_barrier_wait(&start);
 for (int i=0;i<50000;i++) {
  /* Mix ordinary owners with the exact pinned cold entry/byte state.
   * An MCS publication can warm this CPU after selection; the operation
   * must still finish natively with its original pin and ownership. */
  preempt_disable();
  if(cpu&1) {
   /* This cohort invokes the core directly; model its omitted public entry.
    * The paired cohort below must obtain its count from production code. */
   kd_hotlock_spin_entry_pinned();
   kd_spin_acquire_nondelegated(&lock);
  }
  else {
   kd_spin_direct_native_lock(&lock);
   assert(lock.locked==KD_SPIN_DIRECT_NATIVE_HELD && pins==1);
  }
  assert(!__atomic_fetch_add(&inside, 1, __ATOMIC_RELAXED));
  value++;
  assert(__atomic_fetch_sub(&inside, 1, __ATOMIC_RELAXED)==1);
  if(cpu&1) {
   smp_store_release(&lock.locked, 0);
   preempt_enable();
  }
  else kd_spin_direct_native_unlock(&lock);
  assert(states[cpu].node_count==0);
  assert(!pins && !kd_spin_fast_cpu.nondelegated);
  assert(physical_entries==(unsigned long)i+1);
 }
 /* One initial CAS, and at most one queue-tail claim CAS per operation.
  * Failed contender retries must be loads/local waits, not global RMWs. */
 assert(cas_calls>=50000 && cas_calls<=100000 && swaps==queued && mcs_samples==queued);
 assert(physical_entries==50000 && mcs_samples<=physical_entries);
 assert(rate_hot == (queued != 0));
 __atomic_fetch_add(&queue_total, queued, __ATOMIC_RELAXED);
 __atomic_fetch_add(&read_total, local_reads, __ATOMIC_RELAXED);
 __atomic_fetch_add(&sample_total, mcs_samples, __ATOMIC_RELAXED);
 return NULL;
}
int main(int argc, char **argv)
{
 pthread_t threads[CPUS];
 assert(argc==2);
 thread_count=strtoul(argv[1],NULL,10);
 assert(thread_count && thread_count<=CPUS);
 /* Delegation-off preserves the protocol but disables CPU statistics. */
 struct qspinlock disabled={0};
 kd_spin_delegate=false;
 assert(!xchg_tail(&disabled,1U<<16) && disabled.tail==1 && !mcs_samples);
 kd_spin_delegate=true; queued=swaps=0;
 pthread_barrier_init(&start, NULL, thread_count);
 for (unsigned long i=0;i<thread_count;i++) assert(!pthread_create(&threads[i], NULL, worker, (void *)i));
 for (unsigned int i=0;i<thread_count;i++) assert(!pthread_join(threads[i], NULL));
 assert(value==thread_count*50000UL && !lock.val.counter);
 if(thread_count==1) assert(!queue_total && !read_total && !sample_total);
 if(thread_count==CPUS) assert(queue_total && read_total);
 assert(sample_total==queue_total);
 pthread_barrier_destroy(&start);
 /* A pre-existing reserved slot must survive a later nondelegating waiter. */
 cpu=0; states[0].node_count=1; pool[0][0].rsp=0x1234;
 kd_spin_acquire_nondelegated(&lock);
 assert(states[0].node_count==1 && pool[0][0].rsp==0x1234);
 smp_store_release(&lock.locked,0); states[0].node_count=0;
 printf("PASS mixed native MCS (ordinary/paired byte 5): %u threads, MCS-entry sampling, %lu exact operations, %lu queued, %lu local waits, %lu CPU samples, balanced pins/counts, no CAS retry storm\n",thread_count,value,queue_total,read_total,sample_total);
}
