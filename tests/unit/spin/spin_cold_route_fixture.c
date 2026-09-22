/* After inline admission chose cold, the pinned native entry must complete
 * through CAS/pending/MCS independently of subsequent CPU heat. These peers
 * check ownership/accounting; the pthread fixture separately runs real MCS. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
typedef struct { union { u32 val; unsigned char locked; }; } kd_spinlock_t;
static struct { void *held; unsigned int nondelegated; } kd_spin_fast_cpu;
static bool warm_waiter;
static unsigned int pins, disables, enables, reads, attempts, waits;
static unsigned int rate_hot;
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
 for(unsigned int state=0;state<8;state++) {
  kd_spinlock_t lock={.val=(state&1) ? 0x12340101U : 0};
  warm_waiter=state&2;
  rate_hot=0;
  pins=disables=enables=reads=attempts=waits=0;
  assert(kd_spin_fast_idle());
  preempt_disable(); /* The public macro owns the only acquisition pin. */
  kd_spin_direct_native_lock(&lock);
  assert(disables == 1 && pins == 1 && !enables && !reads);
  assert(attempts == 1 && waits == !!(state&1) && lock.locked == KD_SPIN_DIRECT_NATIVE_HELD);
  assert(rate_hot == (!!(state&1) && warm_waiter));
  assert(!kd_spin_fast_idle());
  if(state&4) rate_hot=!rate_hot; /* Unlock never queries a changed gate. */
  lock.val |= 0x45670100U;
  u32 queued=lock.val & ~255U;
  kd_spin_direct_native_unlock(&lock);
  assert(!reads && lock.val == queued && kd_spin_fast_idle());
  assert(!pins && disables == 1 && enables == 1);
 }
 /* Two independent cold holds count through ordinary/early release. The
  * gate may change after either choice; the native entry never rereads it. */
 for(unsigned int early=0;early<2;early++) {
    kd_spinlock_t lock[2]={{.val=0},{.val=0}};
    pins=disables=enables=reads=attempts=waits=0;
    for(unsigned int i=0;i<2;i++) {
     rate_hot=i;
     preempt_disable();
     kd_spin_direct_native_lock(&lock[i]);
     assert(rate_hot==i && lock[i].locked==KD_SPIN_DIRECT_NATIVE_HELD);
    }
    assert(pins==2 && attempts==2 && !reads && kd_spin_fast_cpu.nondelegated==2);
    for(unsigned int step=0;step<2;step++) {
     unsigned int i=early?step:1-step;
     rate_hot=!i;
     kd_spin_direct_native_unlock(&lock[i]);
     assert(!reads && rate_hot==!i && kd_spin_fast_cpu.nondelegated==1-step);
    }
    assert(!pins && enables==2 && disables==2 && kd_spin_fast_idle());
   }
 puts("PASS pinned cold entry: one CAS/pin, contention/heat changes, paired drain, pending/tail retained");
 puts("PASS independent native ownership: nested/early release, no CPU-heat reads or writes");
}
