/* Execute the exact inline GS gate and broad-clobber macros. Hot callees
 * destroy every declared GPR; compiler-owned spills must preserve C values.
 * No fixture save/restore shell repairs the production call convention. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <asm/prctl.h>
#include <sys/syscall.h>
typedef union { unsigned int val; unsigned char locked; } kd_spinlock_t;
#define KD_SPIN_DIRECT_NATIVE_HELD 5U
#define READ_ONCE(x) (x)
#define __percpu
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)
static volatile unsigned int pins;
#define preempt_disable() (++pins)
/* No provider policy symbols: the public shell needs only CPU heat. */
static unsigned int cpu_id, heat[2];
/* The production symbol names one per-CPU pointer slot. A GS offset of 0/8
 * selects two contiguous slots here, both pointing at their own rate_hot. */
unsigned int *cpu_gates[2] = {&heat[0], &heat[1]};
extern unsigned int *kd_hotlock_spin_gate;
asm(".globl kd_hotlock_spin_gate\n.set kd_hotlock_spin_gate,cpu_gates\n");
/* Substitute only the kernel per-CPU primitive, retaining the real C gate
 * and GS addressing. A userspace global alone would miss CPU selection. */
#define this_cpu_read(slot) ({ \
 __typeof__(slot) value; \
 assert(pins); \
 asm volatile("movq %%gs:%1, %0" : "=r"(value) : "m"(slot)); \
 value; \
})
#include "paired.h"
static unsigned int hot, cold_locks, cold_unlocks;
unsigned long hot_calls;
__attribute__((noinline,noipa)) void kd_spin_direct_native_lock(kd_spinlock_t *lock)
{ assert(pins && !lock->val); cold_locks++; lock->locked=KD_SPIN_DIRECT_NATIVE_HELD; }
__attribute__((noinline,noipa)) void kd_spin_direct_native_unlock(kd_spinlock_t *lock)
{ assert(pins && lock->locked==KD_SPIN_DIRECT_NATIVE_HELD); pins--; lock->locked=0; cold_unlocks++; }
/* Metadata describes the unchanged pre-CALL stack and exact continuation.
 * No hidden pushed register area exists at RSI in this ABI. */
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
 unsigned long a=seed+1, b=seed+2, c=seed+3, d=seed+4, e=seed+5;
 unsigned long stack[3]={seed+6,seed+7,seed+8};
 kd_spinlock_t lock={0};
 unsigned int other_cookie=heat[cpu_id^1];
 unsigned int cold=!hot;
 heat[cpu_id]=hot;
 /* Opaque ordinary C live values force the compiler to honor the declared
  * clobbers. Fixed register variables cannot legally survive those clobbers. */
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : "m"(stack) : "memory");
 KD_SPIN_DIRECT_LOCK(&lock,kd_spin_direct_cookie,"");
 assert(pins==1 && lock.locked==(cold?KD_SPIN_DIRECT_NATIVE_HELD:1));
 assert(heat[cpu_id]==hot && heat[cpu_id^1]==other_cookie);
 heat[cpu_id]^=1;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 /* Updated values must also survive the independently clobbering unlock. */
 a+=stack[0]; b+=stack[1]; c+=stack[2]; d+=seed; e+=seed;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 KD_SPIN_DIRECT_UNLOCK(&lock,kd_spin_direct_cookie);
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 assert(!lock.val && !pins && heat[cpu_id^1]==other_cookie && heat[cpu_id]!=hot);
 return a+b+c+d+e;
}

static void nested_cookies(unsigned int outer_hot, unsigned int inner_hot,
                           unsigned int early)
{
 kd_spinlock_t outer={0}, inner={0};
 unsigned int other_cookie=heat[cpu_id^1];
 heat[cpu_id]=outer_hot;
 KD_SPIN_DIRECT_LOCK(&outer,kd_spin_direct_cookie,"");
 heat[cpu_id]=inner_hot;
 KD_SPIN_DIRECT_LOCK(&inner,kd_spin_direct_cookie,"");
 assert(pins==2 && heat[cpu_id]==inner_hot);
 assert(outer.locked==(outer_hot?1:KD_SPIN_DIRECT_NATIVE_HELD));
 assert(inner.locked==(inner_hot?1:KD_SPIN_DIRECT_NATIVE_HELD));
 heat[cpu_id]^=1;
 if(early) {
  KD_SPIN_DIRECT_UNLOCK(&outer,kd_spin_direct_cookie);
  assert(pins==1);
  KD_SPIN_DIRECT_UNLOCK(&inner,kd_spin_direct_cookie);
 } else {
  KD_SPIN_DIRECT_UNLOCK(&inner,kd_spin_direct_cookie);
  assert(pins==1);
  KD_SPIN_DIRECT_UNLOCK(&outer,kd_spin_direct_cookie);
 }
 assert(!pins && !outer.val && !inner.val);
 assert(heat[cpu_id]!=inner_hot && heat[cpu_id^1]==other_cookie);
}

int main(void)
{
 unsigned long old_gs, expected_cold=0, expected_hot=0;
 assert(!syscall(SYS_arch_prctl,ARCH_GET_GS,&old_gs));
 for(cpu_id=0;cpu_id<2;cpu_id++) {
  assert(!syscall(SYS_arch_prctl,ARCH_SET_GS,cpu_id*sizeof(cpu_gates[0])));
  for(hot=0;hot<2;hot++) {
   for(unsigned long i=0;i<1000;i++) assert(stress(i)==10*i+36);
   if(!hot) expected_cold+=1000;
   else expected_hot+=2000;
  }
  for(unsigned int a=0;a<2;a++) for(unsigned int b=0;b<2;b++)
   for(unsigned int early=0;early<2;early++) {
    nested_cookies(a,b,early);
    expected_cold+=2-a-b; expected_hot+=2*(a+b);
   }
 }
 assert(!syscall(SYS_arch_prctl,ARCH_SET_GS,old_gs));
 assert(cold_locks==expected_cold && cold_unlocks==expected_cold && hot_calls==expected_hot);
 puts("PASS inline cold gate: actual GS read, two CPUs, heat-only routing without provider policy symbols");
 puts("PASS compiler-owned clobber ABI: live C values/stack, exact SP/IP/BP, heat changes and nested/early unlock");
}
