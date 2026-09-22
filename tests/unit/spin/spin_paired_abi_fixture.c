/* Compile and execute the exact paired macros. Hot callees intentionally
 * violate C callee-save rules; only the hot shell repairs those registers. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef union { unsigned int val; unsigned char locked; } kd_spinlock_t;
#define KD_SPIN_DIRECT_NATIVE_HELD 5U
#define READ_ONCE(x) (x)
#define __percpu
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)
/* Only the heat sampler owns cookie writes. The actual paired macros may
 * observe heat for acquisition; they must neither store nor latch it. */
static unsigned int cpu_id;
static unsigned int heat[2];
static unsigned int *kd_hotlock_spin_gate = heat;
#include "paired.h"
static unsigned int hot, cold_unlocks;
static volatile unsigned int pins;
unsigned long hot_calls;
__attribute__((noinline,noipa)) unsigned int kd_spin_direct_enter(kd_spinlock_t *lock,
                                                               unsigned int **cookie)
{ assert(!lock->val && cookie==&kd_hotlock_spin_gate); pins++;
  unsigned int path=(*cookie)[cpu_id];
  if(!path) lock->locked=KD_SPIN_DIRECT_NATIVE_HELD;
  return path; }
__attribute__((noinline,noipa)) void kd_spin_direct_native_unlock(kd_spinlock_t *lock)
{ assert(pins && lock->locked==KD_SPIN_DIRECT_NATIVE_HELD); pins--; lock->locked=0; cold_unlocks++; }
/* Metadata must describe the stack before CALL and its exact continuation.
 * The incoming saved values begin at RSI, outside the return-address slot. */
asm(".text\n"
    ".globl kd_spin_lock_pinned_clobber_v1\n"
    "kd_spin_lock_pinned_clobber_v1:\n"
    "movl $1, (%rdi)\n jmp .Ldamage\n"
    ".globl kd_spin_unlock_clobber_v1\n"
    "kd_spin_unlock_clobber_v1:\n"
    "movl $0, (%rdi)\n decl pins(%rip)\n"
    ".Ldamage:\n"
    "leaq 8(%rsp), %rax\n cmpq %rax, %rsi\n jne .Lbad\n"
    "cmpq (%rsp), %rdx\n jne .Lbad\n cmpq %rbp, %rcx\n jne .Lbad\n"
    "incq hot_calls(%rip)\n"
    "movq $17,%rbx\n movq $18,%r12\n movq $19,%r13\n"
    "movq $20,%r14\n movq $21,%r15\n"
    "movq $22,%rax\n movq $23,%rdi\n movq $24,%rsi\n"
    "movq $25,%rdx\n movq $26,%rcx\n movq $27,%r8\n"
    "movq $28,%r9\n movq $29,%r10\n movq $30,%r11\n ret\n"
    ".Lbad: ud2\n");
__attribute__((noinline,noipa)) static unsigned long stress(unsigned long seed)
{
 register unsigned long a asm("rbx")=seed+1, b asm("r12")=seed+2;
 register unsigned long c asm("r13")=seed+3, d asm("r14")=seed+4;
 register unsigned long e asm("r15")=seed+5;
 unsigned long stack[3]={seed+6,seed+7,seed+8};
 kd_spinlock_t lock={0};
 unsigned int other_cookie=heat[cpu_id^1];
 heat[cpu_id]=hot;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : "m"(stack) : "memory");
 KD_SPIN_DIRECT_LOCK(&lock,kd_spin_direct_cookie,"");
 assert(heat[cpu_id]==hot && heat[cpu_id^1]==other_cookie);
 heat[cpu_id]^=1;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 /* Fresh values, not the entry values, must survive the unlock shell. */
 a+=stack[0]; b+=stack[1]; c+=stack[2]; d+=seed; e+=seed;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 KD_SPIN_DIRECT_UNLOCK(&lock,kd_spin_direct_cookie);
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 assert(!lock.val && !pins && heat[cpu_id^1]==other_cookie && heat[cpu_id]!=hot);
 return a+b+c+d+e;
}
static void nested_cookies(unsigned int outer_hot, unsigned int inner_hot)
{
 kd_spinlock_t outer={0}, inner={0};
 heat[cpu_id]=outer_hot;
 KD_SPIN_DIRECT_LOCK(&outer,kd_spin_direct_cookie,"");
 heat[cpu_id]=inner_hot;
 KD_SPIN_DIRECT_LOCK(&inner,kd_spin_direct_cookie,"");
 assert(pins==2 && heat[cpu_id]==inner_hot);
 heat[cpu_id]^=1;
 KD_SPIN_DIRECT_UNLOCK(&inner,kd_spin_direct_cookie);
 assert(pins==1 && heat[cpu_id]!=inner_hot);
 KD_SPIN_DIRECT_UNLOCK(&outer,kd_spin_direct_cookie);
 assert(!pins && !outer.val && !inner.val);
}
int main(void)
{
 for(cpu_id=0;cpu_id<2;cpu_id++) for(hot=0;hot<2;hot++) for(unsigned long i=0;i<1000;i++)
  assert(stress(i)==10*i+36);
 assert(cold_unlocks==2000 && hot_calls==4000);
 for(cpu_id=0;cpu_id<2;cpu_id++) for(unsigned int a=0;a<2;a++)
  for(unsigned int b=0;b<2;b++) nested_cookies(a,b);
 assert(cold_unlocks==2008 && hot_calls==4016);
 puts("PASS paired ABI: per-CPU cookies, live rbx/r12-r15 and stack across cold/hot lock and unlock; exact SP/IP/BP");
}
