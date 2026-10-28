/* Execute the exact inline GS gate and broad-clobber macros. The hot lock
 * and every unlock destroy declared GPRs; compiler spills must preserve C values.
 * No fixture save/restore shell repairs the production call convention. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <asm/prctl.h>
#include <sys/syscall.h>
/* Match Linux 7's missing trailing newline without depending on its headers. */
#define TEST_ANNOTATION ".pushsection .discard.kd_boundary,\"a\",@progbits; .byte 0; .popsection"
typedef uint32_t u32;
typedef union { u32 val; unsigned char locked; } kd_spinlock_t;
#define KD_SPIN_DIRECT_NATIVE_HELD 5U
#define READ_ONCE(x) (x)
#define __percpu
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)
static volatile unsigned int pins;
#define preempt_disable() (++pins)
#define preempt_enable() (--pins)
/* This fixture executes only the plain clobber ABI. IRQ/BH behavior has its
 * own fixture; fail if one of those APIs accidentally enters this workload. */
#define _RET_IP_ 0UL
#define SOFTIRQ_LOCK_OFFSET 0x201U
#define typecheck(type, value) ((void)sizeof(type), (void)sizeof(value))
#define local_irq_save(flags) do { (flags) = 0; assert(!"IRQ API in plain ABI fixture"); } while (0)
#define local_irq_restore(flags) do { (void)(flags); assert(!"IRQ API in plain ABI fixture"); } while (0)
#define local_irq_disable() assert(!"IRQ API in plain ABI fixture")
#define local_irq_enable() assert(!"IRQ API in plain ABI fixture")
#define __local_bh_disable_ip(ip, count) assert(!"BH API in plain ABI fixture")
#define __local_bh_enable_ip(ip, count) assert(!"BH API in plain ABI fixture")
#define smp_store_release(p, value) (*(p) = (value))
#define this_cpu_dec(value) (--(value))
/* Policy remains in the provider; this shell reads heat and counts its hold. */
static unsigned int cpu_id;
unsigned int heat[2];
/* The production symbol names the scalar itself. GS offsets 0/4 select
 * distinct CPU gates without any pointer load or second heat flag. */
extern unsigned int kd_hotlock_spin_gate;
asm(".globl kd_hotlock_spin_gate\n.set kd_hotlock_spin_gate,heat\n");
/* Substitute only the kernel per-CPU primitive, retaining the real C gate
 * and GS addressing. A userspace global alone would miss CPU selection.
 * The assembler alias and GS offset hide heat[cpu_id] from C alias analysis;
 * the memory clobber orders the fixture's gate stores before this read. */
#define this_cpu_read(slot) ({ \
 __typeof__(slot) value; \
 assert(pins); \
 asm volatile("movl %%gs:%1, %0" : "=r"(value) : "m"(slot) : "memory"); \
 value; \
})
/* These primitive substitutes let the real inline CAS/count sequence run.
 * The native count is shared only because this fixture's CPUs run serially. */
static struct { unsigned int nondelegated; } kd_spin_fast_cpu;
static unsigned int hot, cold_locks, entry_calls;
#define this_cpu_inc(x) (++(x))
static u32 atomic_cmpxchg_acquire(u32 *word, u32 old, u32 new)
{
 u32 found=*word;
 assert(pins && kd_spin_fast_cpu.nondelegated);
 cold_locks++;
 if(found==old) *word=new;
 return found;
}
static void kd_hotlock_spin_entry_pinned(void)
{ assert(pins); entry_calls++; }
#include "paired.h"
#ifdef KD_TEST_PUBLIC_API
#include "api.h"
#define PAIR_LOCK(lock, cookie, continuation) kd_spin_lock(lock)
#define PAIR_UNLOCK(lock, cookie) kd_spin_unlock(lock)
#else
#define PAIR_LOCK(lock, cookie, continuation) \
 KD_SPIN_DIRECT_LOCK(lock, cookie, continuation)
#define PAIR_UNLOCK(lock, cookie) KD_SPIN_DIRECT_UNLOCK(lock, cookie)
#endif
unsigned long hot_calls, generic_unlocks, native_releases;
__attribute__((noinline,noipa)) void kd_spin_direct_native_lock(kd_spinlock_t *lock)
{ (void)lock; assert(!"caller bypassed inline cold acquisition"); }
__attribute__((noinline,noipa)) void kd_spin_direct_native_contended(kd_spinlock_t *lock, u32 failed)
{ (void)lock; (void)failed; assert(!"unexpected contention in ABI fixture"); }
__attribute__((noinline,noipa)) void kd_spin_direct_native_unlock(kd_spinlock_t *lock)
{ (void)lock; assert(!"caller bypassed the generic clobber unlock"); }
/* Metadata describes the unchanged pre-CALL stack and exact continuation.
 * No hidden pushed register area exists at RSI in this ABI. */
asm(".text\n"
    ".globl kd_spin_lock_pinned_clobber_v1\n"
    "kd_spin_lock_pinned_clobber_v1:\n"
    "movl $1, (%rdi)\n incq hot_calls(%rip)\n jmp .Ldamage\n"
    ".globl kd_spin_unlock_clobber_v1\n"
    "kd_spin_unlock_clobber_v1:\n"
    "cmpl $0, pins(%rip)\n je .Lbad\n"
    "cmpb $5, (%rdi)\n jne .Lhot_release\n"
    "decl kd_spin_fast_cpu(%rip)\n incq native_releases(%rip)\n jmp .Lrelease\n"
    ".Lhot_release:\n cmpb $1, (%rdi)\n jne .Lbad\n"
    "incq hot_calls(%rip)\n"
    ".Lrelease:\n movb $0, (%rdi)\n decl pins(%rip)\n"
    "incq generic_unlocks(%rip)\n"
    ".Ldamage:\n"
    "leaq 8(%rsp), %rax\n cmpq %rax, %rsi\n jne .Lbad\n"
    "cmpq (%rsp), %rdx\n jne .Lbad\n cmpq %rbp, %rcx\n jne .Lbad\n"
    "movq $17,%rbx\n movq $18,%r12\n movq $19,%r13\n"
    "movq $20,%r14\n movq $21,%r15\n"
    "movq $22,%rax\n movq $23,%rdi\n movq $24,%rsi\n"
    "movq $25,%rdx\n movq $26,%rcx\n movq $27,%r8\n"
    "movq $28,%r9\n movq $29,%r10\n movq $30,%r11\n ret\n"
    ".Lbad: ud2\n");

__attribute__((noinline,noipa)) static unsigned long stress(unsigned long seed,
                                                         bool helpers)
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
 if(helpers)
  KD_SPIN_DIRECT_HELPER_LOCK(&lock,kd_spin_direct_cookie,TEST_ANNOTATION);
 else
  PAIR_LOCK(&lock,kd_spin_direct_cookie,TEST_ANNOTATION);
 assert(pins==1 && lock.locked==(cold?KD_SPIN_DIRECT_NATIVE_HELD:1));
 assert(heat[cpu_id]==hot && heat[cpu_id^1]==other_cookie);
 heat[cpu_id]^=1;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 /* Updated values must also survive the independently clobbering unlock. */
 a+=stack[0]; b+=stack[1]; c+=stack[2]; d+=seed; e+=seed;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 PAIR_UNLOCK(&lock,kd_spin_direct_cookie);
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 assert(!lock.val && !pins && !kd_spin_fast_cpu.nondelegated);
 assert(heat[cpu_id^1]==other_cookie && heat[cpu_id]!=hot);
 return a+b+c+d+e;
}

__attribute__((noinline,noipa)) static void helper_seed(void)
{
 kd_spinlock_t lock={0};
 unsigned long bx;
 register unsigned long r12 asm("r12"), r13 asm("r13");
 register unsigned long r14 asm("r14"), r15 asm("r15");
 heat[cpu_id]=hot;
 KD_SPIN_DIRECT_HELPER_LOCK(&lock,kd_spin_direct_cookie,TEST_ANNOTATION);
 /* Read the actual inline-asm outputs before C can reuse these registers.
  * The destructive hot callee sets all five to nonzero values; only the
  * production continuation can make this assertion pass. */
 asm volatile("" : "=b"(bx), "=r"(r12), "=r"(r13), "=r"(r14), "=r"(r15));
 if(hot) assert(!(bx|r12|r13|r14|r15));
 PAIR_UNLOCK(&lock,kd_spin_direct_cookie);
 assert(!lock.val && !pins && !kd_spin_fast_cpu.nondelegated);
}

static void nested_cookies(unsigned int outer_hot, unsigned int inner_hot,
                           unsigned int early)
{
 kd_spinlock_t outer={0}, inner={0};
 unsigned int other_cookie=heat[cpu_id^1];
 heat[cpu_id]=outer_hot;
 PAIR_LOCK(&outer,kd_spin_direct_cookie,"");
 heat[cpu_id]=inner_hot;
 PAIR_LOCK(&inner,kd_spin_direct_cookie,"");
 assert(pins==2 && heat[cpu_id]==inner_hot);
 assert(outer.locked==(outer_hot?1:KD_SPIN_DIRECT_NATIVE_HELD));
 assert(inner.locked==(inner_hot?1:KD_SPIN_DIRECT_NATIVE_HELD));
 heat[cpu_id]^=1;
 if(early) {
  PAIR_UNLOCK(&outer,kd_spin_direct_cookie);
  assert(pins==1);
  PAIR_UNLOCK(&inner,kd_spin_direct_cookie);
 } else {
  PAIR_UNLOCK(&inner,kd_spin_direct_cookie);
  assert(pins==1);
  PAIR_UNLOCK(&outer,kd_spin_direct_cookie);
 }
 assert(!pins && !outer.val && !inner.val && !kd_spin_fast_cpu.nondelegated);
 assert(heat[cpu_id]!=inner_hot && heat[cpu_id^1]==other_cookie);
}


#if defined(KD_TEST_PUBLIC_API) && !defined(KD_TEST_SPIN_API_EQUIVALENCE)
static unsigned int argument_evaluations;
static kd_spinlock_t *once(kd_spinlock_t *lock)
{
 argument_evaluations++;
 return lock;
}

static unsigned int public_api_contract(void)
{
 kd_spinlock_t locks[5] = {{0}};
 kd_spinlock_t *kd_lock_word = &locks[0];
 kd_spinlock_t *kd_unlock_word = &locks[1];
 kd_spinlock_t *kd_arg = &locks[2];
 kd_spinlock_t *kd_spin_api_arg = &locks[3];
 kd_spinlock_t *kd_spin_api_word = &locks[4];
 unsigned int before = argument_evaluations;
 _Static_assert(__builtin_types_compatible_p(
  __typeof__(kd_spin_lock(&locks[0])), void), "lock is a void expression");
 _Static_assert(__builtin_types_compatible_p(
  __typeof__(kd_spin_unlock(&locks[0])), void), "unlock is a void expression");
 heat[cpu_id] = 0;
 /* Caller names deliberately match DIRECT and facade temporary names. */
 (void)(kd_spin_lock(once(kd_lock_word)), 0);
 assert(locks[0].locked == KD_SPIN_DIRECT_NATIVE_HELD && pins == 1);
 kd_spin_unlock(once(kd_lock_word));
 kd_spin_lock(once(kd_unlock_word));
 assert(locks[1].locked == KD_SPIN_DIRECT_NATIVE_HELD && pins == 1);
 kd_spin_unlock(once(kd_unlock_word));
 kd_spin_lock(once(kd_arg));
 assert(locks[2].locked == KD_SPIN_DIRECT_NATIVE_HELD && pins == 1);
 kd_spin_unlock(once(kd_arg));
 kd_spin_lock(once(kd_spin_api_arg));
 assert(locks[3].locked == KD_SPIN_DIRECT_NATIVE_HELD && pins == 1);
 kd_spin_unlock(once(kd_spin_api_arg));
 kd_spin_lock(once(kd_spin_api_word));
 assert(locks[4].locked == KD_SPIN_DIRECT_NATIVE_HELD && pins == 1);
 kd_spin_unlock(once(kd_spin_api_word));
 assert(argument_evaluations == before + 10 && !pins);
 for (unsigned int i = 0; i < 5; i++) assert(!locks[i].val);
 return 5;
}
#endif

#ifdef KD_TEST_SPIN_API_EQUIVALENCE
/* The driver compares both code bytes and relocation records against DIRECT,
 * so the ordinary facade must not add a call, branch or register capture. */
__attribute__((noinline,noipa)) void api_equivalent_pair(kd_spinlock_t *lock)
{
 PAIR_LOCK(lock, kd_spin_direct_cookie, "");
 asm volatile("" : : : "memory");
 PAIR_UNLOCK(lock, kd_spin_direct_cookie);
}
#endif

#ifdef KD_TEST_SPIN_API_BAD_TYPE
void api_wrong_object(void)
{
 struct { unsigned int native_word; } wrong;
 kd_spin_lock(&wrong);
}
#endif

int main(void)
{
 unsigned long old_gs, expected_cold=0, expected_hot=0;
 assert(!syscall(SYS_arch_prctl,ARCH_GET_GS,&old_gs));
 for(cpu_id=0;cpu_id<2;cpu_id++) {
  assert(!syscall(SYS_arch_prctl,ARCH_SET_GS,cpu_id*sizeof(heat[0])));
#if defined(KD_TEST_PUBLIC_API) && !defined(KD_TEST_SPIN_API_EQUIVALENCE)
  expected_cold += public_api_contract();
#endif
  for(hot=0;hot<2;hot++) {
   for(unsigned int helpers=0;helpers<2;helpers++)
    for(unsigned long i=0;i<1000;i++) assert(stress(i,helpers)==10*i+36);
   helper_seed();
   if(!hot) expected_cold+=2001;
   else expected_hot+=4002;
  }
  for(unsigned int a=0;a<2;a++) for(unsigned int b=0;b<2;b++)
   for(unsigned int early=0;early<2;early++) {
    nested_cookies(a,b,early);
    expected_cold+=2-a-b; expected_hot+=2*(a+b);
   }
 }
 assert(!syscall(SYS_arch_prctl,ARCH_SET_GS,old_gs));
 assert(cold_locks==expected_cold && entry_calls==expected_cold);
 assert(native_releases==expected_cold && hot_calls==expected_hot);
 assert(generic_unlocks==expected_cold+expected_hot/2);
 puts("PASS inline cold acquisition: actual GS gate, two CPUs, one CAS/count and paired native drain");
 puts("PASS generic cold/hot clobber unlock: live C values/stack, exact SP/IP/BP, provenance, heat changes and nested/early unlock");
 puts("PASS opt-in helper entry: five source-defined scratch registers, preserved compiler spills and unchanged cold accounting");
}
