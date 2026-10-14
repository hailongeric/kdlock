/* SPDX-License-Identifier: GPL-2.0 */
/* Actual ordinary-C caller/entry and generated JIT; no scheduler model. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include "kd_regs.h"
#include "exe_info.h"
#include "kd_owned_mutex_cabi.h"
struct kd_mutex { unsigned long owner; };
void *current_task=(void *)0x8000;
#define current current_task
#define might_sleep() ((void)0)
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x,v) (*(volatile __typeof__(x) *)&(x)=(v))
#define __always_inline inline __attribute__((always_inline))
#define ASM_CALL_CONSTRAINT "+r"(current_stack_pointer)
register unsigned long current_stack_pointer asm("rsp");
static unsigned long atomic_long_read(unsigned long *p) { return *p; }
static bool atomic_long_try_cmpxchg_acquire(unsigned long *p,unsigned long *old,unsigned long value) {
 if(*p!=*old) { *old=*p;return false; } *p=value;return true;
}
unsigned long kd_hotlock_owned_mutex_entries,gate_calls,capture_calls,unlock_calls;
static unsigned long slow_unlock_calls,ack_calls,bug_calls,last_core_owner;
static bool borrowed_route,ack_result,expect_bug;
static jmp_buf bug_return;
static __attribute__((noreturn)) void fixture_bug(void) {
 if(!expect_bug) abort();
 bug_calls++;longjmp(bug_return,1);
}
#define BUG_ON(condition) do { if(condition) fixture_bug(); } while(0)
static inline void kd_hotlock_owned_mutex_entry(void) { kd_hotlock_owned_mutex_entries++; }
#define KD_OWNED_MUTEX_CABI 1
#include "outer_api.h"
#define __KERNEL__
#include "kd_jit_batch.h"
static struct kd_mutex test_lock __attribute__((section(".owned_lock")));
static unsigned long gate_mode;
/* The JIT embeds these source addresses. The second link adds a wrapper, so
 * keep its observed state in a pinned section just like the public lock. */
static unsigned long continuation_hits __attribute__((section(".owned_state")));
static unsigned long bodies __attribute__((section(".owned_state")));
static unsigned long cookie_override __attribute__((section(".owned_state")));
static struct kd_owned_mutex_cabi_state captured;
static unsigned long captured_stack[96],captured_bytes,actual_return_ip;
static unsigned long expected_caller_sp __attribute__((section(".owned_state")));
static unsigned long expected_caller_bp __attribute__((section(".owned_state")));
static unsigned long *cookie_address __attribute__((section(".owned_state")));
extern char cabi_entry[];
extern void main_wrapper(struct kd_regs *,unsigned long *) __attribute__((weak));
extern void check_cabi_restore(void);
extern void check_cabi_unlock(struct kd_mutex *,unsigned long);
typedef uint8_t u8;typedef int32_t s32;
static unsigned long nofault_low,nofault_high;
static int copy_from_kernel_nofault(void *to,const void *from,size_t n) {
 unsigned long address=(unsigned long)from;
 if(nofault_low && (address<nofault_low || address>nofault_high || n>nofault_high-address)) return -1;
 memcpy(to,from,n);return 0;
}
#include "cabi_stub.inc"
static void check_stub(void) {
 u8 bytes[16]={0x48,0x85,0xc0,0x0f,0x85,2,0,0,0,0x31,0xc0};
 nofault_low=(unsigned long)bytes;nofault_high=nofault_low+sizeof(bytes);
 assert(kd_owned_mutex_cabi_stub_valid(nofault_low));
 bytes[0]=0x49;assert(!kd_owned_mutex_cabi_stub_valid(nofault_low));bytes[0]=0x48;
 bytes[5]=1;assert(!kd_owned_mutex_cabi_stub_valid(nofault_low));bytes[5]=2;
 bytes[9]=0x90;assert(!kd_owned_mutex_cabi_stub_valid(nofault_low));bytes[9]=0x31;
 bytes[5]=127;assert(!kd_owned_mutex_cabi_stub_valid(nofault_low));
 assert(!kd_owned_mutex_cabi_stub_valid(~0UL-4));
 nofault_low=nofault_high=0;
}
__attribute__((noipa)) unsigned long
kd_owned_mutex_outer_cabi_gate(struct kd_mutex *lock,unsigned long ip) {
 gate_calls++;actual_return_ip=ip;
 if(gate_mode==1) { lock->owner=(unsigned long)current;return (unsigned long)current; }
 return 0;
}
__attribute__((noipa)) unsigned long
kd_owned_mutex_outer_cabi_capture(struct kd_mutex *lock,const struct kd_owned_mutex_cabi_state *p) {
 capture_calls++;captured=*p;
 assert(captured.ip==actual_return_ip);
 assert(p->sp==(unsigned long)p+80);
 assert(p->sp==expected_caller_sp && p->bp==expected_caller_bp);
 captured_bytes=p->bp+16-p->sp;
 assert(captured_bytes<=sizeof(captured_stack));
 memcpy(captured_stack,(void *)p->sp,captured_bytes);
 lock->owner=(unsigned long)current;
 return (unsigned long)current;
}
/* Extract the real C fallback, with deterministic owner/ACK dependencies.
 * These counters distinguish a leaf release from merely succeeding via C. */
static bool kd_mutex_task_reroute(void *task) {
 assert(task==current);return borrowed_route;
}
static bool kd_exec_native_unlock(unsigned long lock,bool mutex) {
 assert(lock==(unsigned long)&test_lock && mutex);ack_calls++;return ack_result;
}
void kd_owned_mutex_outer_unlock_v1(struct kd_mutex *lock) {
 unlock_calls++;last_core_owner=lock->owner;
 BUG_ON((lock->owner&~15UL)!=(unsigned long)current || (lock->owner&4));
 lock->owner=0;
}
#define kd_owned_mutex_outer_cabi_unlock_slow production_cabi_unlock_slow
#include "cabi_unlock.inc"
#undef kd_owned_mutex_outer_cabi_unlock_slow
__attribute__((noipa)) void
kd_owned_mutex_outer_cabi_unlock_slow(struct kd_mutex *lock,unsigned long owner) {
 slow_unlock_calls++;production_cabi_unlock_slow(lock,owner);
}

static void check_bad_unlock(unsigned long owner,unsigned long cookie,
                             bool route,bool ack,unsigned long core_delta,
                             unsigned long ack_delta) {
 unsigned long old_slow=slow_unlock_calls,old_core=unlock_calls;
 unsigned long old_acks=ack_calls,old_bugs=bug_calls;
 test_lock.owner=owner;borrowed_route=route;ack_result=ack;expect_bug=true;
 if(!setjmp(bug_return)) {
  kd_owned_mutex_outer_unlock_cabi_v2(&test_lock,cookie);
  assert(!"invalid unlock returned without BUG");
 }
 expect_bug=false;
 assert(test_lock.owner==owner && bug_calls==old_bugs+1);
 assert(slow_unlock_calls==old_slow+1 && unlock_calls==old_core+core_delta);
 assert(ack_calls==old_acks+ack_delta);
}

static void check_unlock_routes(void) {
 unsigned long owner=(unsigned long)current;
 unsigned long old_slow=slow_unlock_calls,old_core=unlock_calls,old_acks=ack_calls;
 borrowed_route=false;ack_result=false;test_lock.owner=owner;
 check_cabi_unlock(&test_lock,owner);
 assert(!test_lock.owner && slow_unlock_calls==old_slow &&
        unlock_calls==old_core && ack_calls==old_acks);
 /* WAITERS, HANDOFF and the delegation guard all require the C fallback. */
 const unsigned long flags[]={1,3,9};
 for(unsigned i=0;i<sizeof(flags)/sizeof(flags[0]);i++) {
  test_lock.owner=owner|flags[i];check_cabi_unlock(&test_lock,owner);
  assert(!test_lock.owner && slow_unlock_calls==old_slow+i+1 &&
         unlock_calls==old_core+i+1 && ack_calls==old_acks &&
         last_core_owner==(owner|flags[i]));
 }
 /* A borrowed zero cookie never writes another task's owner word. */
 test_lock.owner=0x9001;borrowed_route=true;ack_result=true;
 check_cabi_unlock(&test_lock,0);
 assert(test_lock.owner==0x9001 && slow_unlock_calls==old_slow+4 &&
        unlock_calls==old_core+3 && ack_calls==old_acks+1);
 check_bad_unlock(owner,0x9000,false,false,0,0);
 check_bad_unlock(0x9000,0x9000,false,false,0,0);
 check_bad_unlock(owner,0,false,false,0,0);
 check_bad_unlock(0x9001,0,true,false,0,1);
 check_bad_unlock(0x9000,owner,false,false,1,0);
 check_bad_unlock(owner|5,owner,false,false,1,0);
 borrowed_route=false;ack_result=false;test_lock.owner=0;
 puts("PASS actual ABI4 unlock leaf and flagged/ACK fallbacks preserve callee registers; invalid cookies preserve ownership");
}
__attribute__((noipa)) unsigned long cabi_case(void) {
 register unsigned long a asm("rbx")=0x111;
 register unsigned long b asm("r12")=0x222;
 register unsigned long c asm("r13")=0x333;
 register unsigned long d asm("r14")=0x444;
 register unsigned long e asm("r15")=0x555;
 struct kd_owned_mutex_outer_cookie cookie;
 cookie_address=&cookie.owner;
 expected_caller_bp=(unsigned long)__builtin_frame_address(0);
 asm volatile("mov %%rsp,%0":"=m"(expected_caller_sp)::"memory");
 asm volatile("":"+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e)::"memory");
 KD_OWNED_MUTEX_OUTER_LOCK(&test_lock,cookie,
   ".globl cabi_entry\ncabi_entry:\nincq continuation_hits(%%rip)\n");
 asm volatile("":"+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e)::"memory");
 a+=0x10;b+=0x20;c+=0x30;d+=0x40;e+=0x50;
 if(cookie_override) cookie.owner=cookie_override;
 bodies++;
 asm volatile("":"+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e)::"memory");
 KD_OWNED_MUTEX_OUTER_UNLOCK(&test_lock,cookie);
 asm volatile("":"+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e)::"memory");
 return a+b+c+d+e;
}
/* This body needs no nonvolatile working register: the ABI shell itself must
 * not force five extra save/restore pairs as ABI2 does. */
__attribute__((noipa)) void cabi_tiny(void) {
 struct kd_owned_mutex_outer_cookie cookie;
 KD_OWNED_MUTEX_OUTER_LOCK(&test_lock,cookie,"");
 bodies++;
 KD_OWNED_MUTEX_OUTER_UNLOCK(&test_lock,cookie);
}
static void check_jit(void) {
 if(!main_wrapper) return;
 assert(captured.ip==KD_OWNED_MUTEX_PREPARE_IP(cabi_entry));
 assert(kd_owned_mutex_cabi_stub_valid(captured.ip));
 assert(!memcmp((void *)captured.ip,"\x48\x85\xc0\x0f\x85",5));
 unsigned long cookie_offset=(unsigned long)cookie_address-captured.sp;
 assert(cookie_offset+8<=captured_bytes);
 for(unsigned full=0;full<3;full++) {
  unsigned long memory[128],*sp=&memory[16];struct kd_regs regs;
  unsigned int state=KD_PACKET_CALLEE_ENTRY;
  cookie_override=full==2?0x123:0;
  memset(memory,0xa3,sizeof(memory));memcpy(sp,captured_stack,captured_bytes);
  for(unsigned i=0;i<captured_bytes/8;i++)
   if(sp[i]>=captured.sp && sp[i]<captured.sp+captured_bytes)
    sp[i]=(unsigned long)sp+sp[i]-captured.sp;
  memset(&regs,0xde,sizeof(regs));
  regs.ip=captured.ip;regs.sp=(unsigned long)sp;
  regs.bp=(unsigned long)sp+captured.bp-captured.sp;
  regs.bx=captured.bx;regs.r12=captured.r12;regs.r13=captured.r13;
  regs.r14=captured.r14;regs.r15=captured.r15;
  unsigned long before=bodies,old_continuations=continuation_hits,old_unlocks=unlock_calls;
  test_lock.owner=(unsigned long)current;
  *(unsigned long *)((char *)sp+cookie_offset)=(unsigned long)current;
  struct kd_jit_batch_call call={.regs=&regs,.args={0,0},
   .code=(char *)main_wrapper+32,.lock=(unsigned long)&test_lock,
   .unlock=(unsigned long)kd_owned_mutex_outer_unlock_cabi_v2,
   .entry_sp=(unsigned long)sp,.entry_abi=4,.packet_state=&state,.complete=full!=1};
  kd_jit_clobber_call_v1(&call);
  assert(bodies==before+1 && continuation_hits==old_continuations+1);
  assert(call.args[1]==1 && unlock_calls==old_unlocks);
  assert(*(unsigned long *)((char *)sp+cookie_offset)==cookie_override);
  assert(test_lock.owner==(unsigned long)current);
  assert(regs.bx==0x121 && regs.r12==0x242 && regs.r13==0x363 &&
         regs.r14==0x484 && regs.r15==0x5a5);
  assert(regs.bp==(unsigned long)sp+captured.bp-captured.sp);
  if(full) {
   assert(call.args[0]==1 && state==KD_PACKET_FULL);
   assert(regs.ip==(unsigned long)kd_owned_mutex_outer_unlock_cabi_v2);
   assert(regs.sp==(unsigned long)sp-8);
   assert(*(unsigned long *)regs.sp>captured.ip);
   assert(regs.di==(unsigned long)&test_lock && regs.si==cookie_override);
  } else {
   assert(call.args[0]==7 && state==KD_PACKET_CALLEE_COMPLETE);
   assert(regs.sp==(unsigned long)sp && regs.ip>captured.ip);
   assert(regs.ip!= (unsigned long)kd_owned_mutex_outer_unlock_cabi_v2);
  }
 }
 cookie_override=0;
 puts("PASS actual ABI4 compiled/JIT entry: poisoned volatile registers, updated callee COMPLETE, exact FULL, cookie and source-return identity");
}
int main(void) {
 for(unsigned mode=0;mode<3;mode++) {
  gate_mode=mode;test_lock.owner=mode?0x9000:0;
  unsigned long entries=kd_hotlock_owned_mutex_entries,gates=gate_calls,captures=capture_calls;
  assert(cabi_case()==0x10ef && !test_lock.owner);
  assert(kd_hotlock_owned_mutex_entries==entries);
  assert(gate_calls==gates+(mode!=0));assert(capture_calls==captures+(mode==2));
  assert(continuation_hits==0);
 }
 check_stub();check_cabi_restore();check_unlock_routes();check_jit();
 puts("PASS actual ABI4 leaf/SELF/late-capture preserves callee registers; production eight-word restore");
 return 0;
}
