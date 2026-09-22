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
static unsigned int rate_hot;
static unsigned int *cpu_hot = &rate_hot;
#define __percpu
#define KD_SPIN_DIRECT_NATIVE_HELD 5U
#define preempt_disable() (++pins, ++disables)
#define preempt_enable() (--pins, ++enables)
#define this_cpu_inc(x) (++(x))
#define this_cpu_dec(x) (--(x))
#define this_cpu_read(x) (++reads, (x))
#define smp_store_release(p,v) (*(p)=(v))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define per_cpu(x,c) (x)
#define for_each_possible_cpu(c) for ((c)=0;(c)<1;(c)++)
#define _Q_LOCKED_VAL_HL 1U
static u32 atomic_cmpxchg_acquire(u32 *p, u32 old, u32 value)
{ assert(pins); attempts++; u32 found=*p; if(found==old) *p=value; return found; }
static void kd_spin_acquire_nondelegated_contended(kd_spinlock_t *lock, u32 failed)
{
 assert(pins == 1 && attempts == 1 && kd_spin_fast_cpu.nondelegated == 1);
 assert(failed == lock->val && failed); waits++;
 if(warm_waiter) rate_hot=true;
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
  rate_hot=hot;
  bool expect_cold=kd_spin_cold_fastpath && (!kd_spin_delegate || !hot);
  pins=disables=enables=reads=attempts=waits=0;
  assert(kd_spin_fast_idle());
  unsigned int hot_entry=kd_spin_direct_enter(&lock, &cpu_hot);
  assert(hot_entry == !expect_cold && disables == 1 && pins == 1 && !enables);
  assert(reads == (kd_spin_cold_fastpath && kd_spin_delegate));
  if(hot_entry) {
   assert(!attempts && !waits && kd_spin_fast_idle());
   preempt_enable(); /* The hot core receives this existing pin. */
  } else {
   assert(attempts == 1 && waits == !!(state&16) && lock.locked == KD_SPIN_DIRECT_NATIVE_HELD);
   assert(!kd_spin_fast_idle());
   if(state&32) rate_hot=!rate_hot; /* Unlock never queries a changed gate. */
   lock.val |= 0x45670100U;
   u32 queued=lock.val & ~255U;
   unsigned int before=reads;
   kd_spin_direct_native_unlock(&lock);
   assert(reads == before && lock.val == queued && kd_spin_fast_idle());
  }
  assert(!pins && disables == 1 && enables == 1);
 }
 /* One current-CPU heat value is shared by both locks, even when it changes
  * between acquisitions. Neither the selector nor unlock writes that value. */
 for(unsigned int outer_hot=0;outer_hot<2;outer_hot++)
  for(unsigned int inner_hot=0;inner_hot<2;inner_hot++)
   for(unsigned int early=0;early<2;early++) {
    kd_spinlock_t lock[2]={{.val=0},{.val=0}};
    unsigned int kinds[2]={outer_hot,inner_hot};
    kd_spin_cold_fastpath=kd_spin_delegate=true;
    pins=disables=enables=reads=attempts=waits=0;
    for(unsigned int i=0;i<2;i++) {
     rate_hot=kinds[i];
     assert(kd_spin_direct_enter(&lock[i],&cpu_hot)==kinds[i]);
     assert(rate_hot==kinds[i]);
     if(kinds[i]) lock[i].locked=1; /* Existing pinned hot core. */
    }
    assert(pins==2 && attempts==2-outer_hot-inner_hot && reads==2);
    for(unsigned int step=0;step<2;step++) {
     unsigned int i=early?step:1-step;
     rate_hot=!kinds[i];
     if(lock[i].locked==KD_SPIN_DIRECT_NATIVE_HELD)
      kd_spin_direct_native_unlock(&lock[i]);
     else { lock[i].locked=0; preempt_enable(); }
     assert(reads==2 && rate_hot==!kinds[i]);
    }
    assert(!pins && enables==2 && disables==2 && kd_spin_fast_idle());
   }
 puts("PASS cold routing: 64 gate/delegation/contention/heat-change routes; one CAS/pin, paired drain, pending/tail retained");
 puts("PASS one shared CPU-hot cookie: nested/early unlock across different acquisition heat; no cookie writes");
}
