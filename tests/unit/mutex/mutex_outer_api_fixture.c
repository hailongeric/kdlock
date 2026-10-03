/* Real outer API/header and destructive clobber callees. Kernel atomics,
 * current and per-CPU observations are narrow userspace substitutes. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
struct mutex { unsigned long owner; };
#define current ((void *)0x8000UL)
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x,v) (*(volatile __typeof__(x) *)&(x) = (v))
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)
static inline bool outer_test_cas(unsigned long *p, unsigned long *old, unsigned long value)
{
 return __atomic_compare_exchange_n(p,old,value,false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
}
#define atomic_long_try_cmpxchg_acquire outer_test_cas
#define atomic_long_try_cmpxchg_release outer_test_cas
#define might_sleep() do { } while (0)
unsigned long entries, routed_locks, routed_unlocks, native_unlocks;
unsigned long *test_cookie_address;
static inline void kd_hotlock_mutex_entry(void) { entries++; }
__attribute__((noinline,noipa)) void mutex_unlock(struct mutex *lock)
{
 assert((lock->owner & ~7UL) == (unsigned long)current);
 native_unlocks++;
 lock->owner=0;
}
#include "outer_api.h"
struct kd_regs { unsigned long w[21]; };
#define __KERNEL__
#include "kd_jit_batch.h"
extern void main_wrapper(struct kd_regs *, unsigned long *) __attribute__((weak));
extern char outer_jit_entry[];
unsigned long captured_sp, captured_bp, captured_ip, captured_bytes;
unsigned long captured_stack[64];
asm(".text\n"
    ".globl kd_mutex_direct_contended_clobber_v1\n"
    "kd_mutex_direct_contended_clobber_v1:\n"
    "incq routed_locks(%rip)\n incq entries(%rip)\n movq $0x8000,(%rdi)\n"
    /* Destroy any pre-entry cookie assumption. Only the after-continuation
     * production store can select routed unlock after this return. */
    "movq test_cookie_address(%rip),%rax\n movq $0x8000,(%rax)\n movq $1,%r8\n jmp .Louter_damage\n"
    ".globl kd_mutex_direct_unlock_clobber_v1\n"
    "kd_mutex_direct_unlock_clobber_v1:\n"
    "incq routed_unlocks(%rip)\n movq $0,(%rdi)\n xorq %r8,%r8\n"
    ".Louter_damage:\n"
    "leaq 8(%rsp),%rax\n cmpq %rax,%rsi\n jne .Louter_bad\n"
    "cmpq (%rsp),%rdx\n jne .Louter_bad\n cmpq %rbp,%rcx\n jne .Louter_bad\n"
    "testq %r8,%r8\n je .Louter_poison\n"
    "movq %rsi,captured_sp(%rip)\n movq %rcx,captured_bp(%rip)\n movq %rdx,captured_ip(%rip)\n"
    "movq %rcx,%rax\n subq %rsi,%rax\n addq $16,%rax\n cmpq $512,%rax\n ja .Louter_bad\n"
    "movq %rax,captured_bytes(%rip)\n movq %rax,%rcx\n shrq $3,%rcx\n"
    "leaq captured_stack(%rip),%rdi\n rep movsq\n"
    ".Louter_poison:\n"
    "movq $17,%rbx\n movq $18,%r12\n movq $19,%r13\n movq $20,%r14\n movq $21,%r15\n"
    "movq $22,%rax\n movq $23,%rdi\n movq $24,%rsi\n movq $25,%rdx\n movq $26,%rcx\n"
    "movq $27,%r8\n movq $28,%r9\n movq $29,%r10\n movq $30,%r11\n ret\n"
    ".Louter_bad: ud2\n");

/* Fixed virtual identity keeps decoded RIP-relative lock references identical
 * when the already-built fixture object is relinked with its generated JIT. */
static struct mutex test_lock __attribute__((section(".outer_lock")));
/* All live source inputs at the hot entry are compiler stack spills. This
 * function is also decoded by the actual translator, including native branch. */
__attribute__((noinline,noipa)) unsigned long outer_jit_case(void)
{
 struct kd_mutex_outer_cookie cookie;
 volatile unsigned long body=0x115;
 test_cookie_address=&cookie.owner;
 KD_MUTEX_OUTER_LOCK(&test_lock,cookie,
  ".globl outer_jit_entry\nouter_jit_entry:\n");
 body++;
 KD_MUTEX_OUTER_UNLOCK(&test_lock,cookie);
 return body;
}

__attribute__((noinline,noipa)) static unsigned long stress(unsigned long seed, int mode)
{
 struct mutex lock={ mode==1 ? 0x9000UL : 0 };
 struct kd_mutex_outer_cookie cookie;
 unsigned long a=seed+1,b=seed+2,c=seed+3,d=seed+4,e=seed+5;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 test_cookie_address=&cookie.owner;
 KD_MUTEX_OUTER_LOCK(&lock,cookie,"");
 assert(cookie.owner == (mode==1 ? 0UL : (unsigned long)current));
 if(mode==2) lock.owner |= 1; /* Original unlock retains Linux waiter/owner semantics. */
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 KD_MUTEX_OUTER_UNLOCK(&lock,cookie);
 assert(!lock.owner);
 return a+b+c+d+e;
}
/* Execute the actual compiled continuation, not just a synthetic cookie
 * branch. Relocate its saved native stack; all uncaptured packet GPRs stay
 * poisoned. A native-branch selection returns the original mutex endpoint
 * instead of the required routed endpoint; neither may change physical owner. */
static void check_generated_outer(void)
{
 if (!main_wrapper)
  return; /* First link supplies the source ELF; second link must run this. */
 assert(captured_ip == (unsigned long)outer_jit_entry);
 assert(captured_bytes <= sizeof(captured_stack));
 unsigned long cookie_offset=(unsigned long)test_cookie_address-captured_sp;
 assert(cookie_offset+sizeof(unsigned long)<=captured_bytes);
 for(unsigned int full=0;full<2;full++) {
  unsigned long memory[80], *sp=&memory[8];
  struct kd_regs regs;
  unsigned int state=1, body_slot=~0U;
  memset(memory,0xa3,sizeof(memory));
  memcpy(sp,captured_stack,captured_bytes);
  for(unsigned int i=0;i<captured_bytes/8;i++) {
   if(sp[i]==0x115) { assert(body_slot==~0U); body_slot=i; }
   if(sp[i]>=captured_sp && sp[i]<captured_sp+captured_bytes)
    sp[i]=(unsigned long)sp+sp[i]-captured_sp;
  }
  assert(body_slot!=~0U);
  /* A native-looking value must be overwritten by the hot entry itself. */
  *(unsigned long *)((char *)sp+cookie_offset)=(unsigned long)current;
  memset(&regs,0xde,sizeof(regs));
  regs.w[0]=captured_ip; regs.w[1]=(unsigned long)sp;
  regs.w[2]=(unsigned long)sp+captured_bp-captured_sp;
  test_lock.owner=(unsigned long)current;
  unsigned long old_locks=routed_locks, old_unlocks=routed_unlocks;
  struct kd_jit_batch_call call={
   .regs=&regs, .args={0,0}, .code=(char *)main_wrapper+32,
   .lock=(unsigned long)&test_lock,
   .unlock=(unsigned long)kd_mutex_direct_unlock_clobber_v1,
   .entry_sp=(unsigned long)sp,
   .entry_abi=2, .packet_state=&state, .complete=!full,
  };
  kd_jit_clobber_call_v1(&call);
  assert(call.args[1]==1 && sp[body_slot]==0x116);
  assert(*(unsigned long *)((char *)sp+cookie_offset)==0);
  assert(test_lock.owner==(unsigned long)current);
  assert(routed_locks==old_locks && routed_unlocks==old_unlocks);
  if(full) {
   assert(call.args[0]==1 && state==0);
   assert(regs.w[0]==(unsigned long)kd_mutex_direct_unlock_clobber_v1);
   assert(regs.w[1]==(unsigned long)sp-8);
   assert(*(unsigned long *)regs.w[1]==regs.w[14]);
  } else {
   assert(call.args[0]==7 && state==2 && regs.w[1]==(unsigned long)sp);
  }
 }
 puts("PASS actual compiled/JIT outer entry: poisoned registers, routed cookie, untouched Linux owner, COMPLETE and exact FULL");
}

int main(void)
{
 for(int mode=0;mode<3;mode++) {
  unsigned long before=entries, locks=routed_locks, unlocks=routed_unlocks;
  assert(stress(100,mode)==515);
  assert(entries==before+1);
  assert(routed_locks==locks+(mode==1));
  assert(routed_unlocks==unlocks+(mode==1));
 }
 assert(native_unlocks==2);
 for(int hot=0;hot<2;hot++) {
  test_lock.owner=hot?0x9000UL:0;
  assert(outer_jit_case()==0x116 && !test_lock.owner);
 }
 check_generated_outer();
 puts("PASS outer native/routed cookies, once-only observation, flags fallback, live registers and metadata");
}
