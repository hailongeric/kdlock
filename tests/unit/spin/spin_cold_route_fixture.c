/* Keep one acquisition decision across CPU warming/cooling, contention and
 * release. These deterministic peers check routing; they are not real MCS. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct { union { u32 val; unsigned char locked; }; } kd_spinlock_t;
static struct { void *held; unsigned int nondelegated; } kd_spin_fast_cpu;
static bool kd_spin_delegate, kd_spin_cold_fastpath, hot, warm_waiter;
static unsigned int pins, disables, enables, reads, attempts, waits;
#define preempt_disable() (++pins, ++disables)
#define preempt_enable() (--pins, ++enables)
#define this_cpu_inc(x) (++(x))
#define this_cpu_dec(x) (--(x))
#define smp_store_release(p,v) (*(p)=(v))
#define READ_ONCE(x) (x)
#define per_cpu(x,c) (x)
#define for_each_possible_cpu(c) for ((c)=0;(c)<1;(c)++)
#define _Q_LOCKED_VAL_HL 1U
static bool kd_hotlock_spin_cpu_hot_pinned(void)
{ assert(pins == 1); reads++; return hot; }
static u32 atomic_cmpxchg_acquire(u32 *p, u32 old, u32 value)
{ assert(pins == 1); attempts++; u32 found=*p; if(found==old) *p=value; return found; }
static void kd_spin_acquire_nondelegated_contended(kd_spinlock_t *lock, u32 failed)
{
 assert(pins == 1 && attempts == 1 && kd_spin_fast_cpu.nondelegated == 1);
 assert(failed == lock->val && failed); waits++;
 if(warm_waiter) hot=true;
 lock->locked=1;
}
#include "cold_route.h"
int main(void)
{
 /* A pending bit/tail can exist at acquisition, appear after CAS, or remain
  * at release; the paired release owns only the low locked byte. */
 for(unsigned int state=0;state<64;state++) {
  kd_spinlock_t lock={.val=(state&16) ? 0x12340101U : 0};
  kd_spin_cold_fastpath=state&1; kd_spin_delegate=state&2;
  hot=state&4; warm_waiter=state&8;
  bool expect_cold=kd_spin_cold_fastpath && (!kd_spin_delegate || !hot);
  pins=disables=enables=reads=attempts=waits=0;
  assert(kd_spin_fast_idle());
  unsigned int cookie=kd_spin_direct_enter(&lock);
  assert(cookie == !expect_cold && disables == 1 && pins == 1 && !enables);
  assert(reads == (kd_spin_cold_fastpath && kd_spin_delegate));
  if(cookie) {
   assert(!attempts && !waits && kd_spin_fast_idle());
   preempt_enable(); /* The hot core receives this existing pin. */
  } else {
   assert(attempts == 1 && waits == !!(state&16) && lock.locked == 1);
   assert(!kd_spin_fast_idle());
   if(state&32) hot=!hot; /* Unlock must never query a changed gate. */
   lock.val |= 0x45670100U;
   u32 queued=lock.val & ~255U;
   unsigned int before=reads;
   kd_spin_direct_native_unlock(&lock);
   assert(reads == before && lock.val == queued && kd_spin_fast_idle());
  }
  assert(!pins && disables == 1 && enables == 1);
 }
 puts("PASS cold routing: 64 gate/delegation/contention/heat-change routes; one CAS/pin, paired drain, pending/tail retained");
}
