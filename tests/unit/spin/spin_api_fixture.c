/* Real public compiler boundaries with destructive provider substitutes.
 * This checks emitted CALL metadata and spills, not physical/JIT ownership. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

typedef struct { uint32_t val; } kd_spinlock_t;
struct kd_mutex { uint32_t val; };
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)
#include "caller.h"

#ifdef KD_TEST_PUBLIC_API
#include "api.h"
#define SPIN_LOCK(lock) kd_spin_lock(lock)
#define SPIN_UNLOCK(lock) kd_spin_unlock(lock)
#else
#define SPIN_LOCK(lock) KD_SPIN_DIRECT_CALL(kd_spin_lock_clobber_v1, lock, "")
#define SPIN_UNLOCK(lock) KD_SPIN_DIRECT_CALL(kd_spin_unlock_clobber_v1, lock, "")
#endif

unsigned int pins, mutex_depth;
unsigned long spin_locks, spin_unlocks, mutex_locks, mutex_unlocks;
asm(".text\n"
    ".globl kd_spin_lock_clobber_v1\n"
    "kd_spin_lock_clobber_v1:\n"
    "cmpl $0,(%rdi)\n jne .Lbad\n movl $1,(%rdi)\n"
    "incl pins(%rip)\n incq spin_locks(%rip)\n jmp .Ldamage\n"
    ".globl kd_spin_unlock_clobber_v1\n"
    "kd_spin_unlock_clobber_v1:\n"
    "cmpl $0,pins(%rip)\n je .Lbad\n"
    "cmpl $1,(%rdi)\n jne .Lbad\n movl $0,(%rdi)\n"
    "decl pins(%rip)\n incq spin_unlocks(%rip)\n jmp .Ldamage\n"
    ".globl kd_mutex_direct_lock_clobber_v1\n"
    "kd_mutex_direct_lock_clobber_v1:\n"
    "cmpl $0,pins(%rip)\n jne .Lbad\n"
    "cmpl $0,(%rdi)\n jne .Lbad\n movl $1,(%rdi)\n"
    "incl mutex_depth(%rip)\n incq mutex_locks(%rip)\n jmp .Ldamage\n"
    ".globl kd_mutex_direct_unlock_clobber_v1\n"
    "kd_mutex_direct_unlock_clobber_v1:\n"
    "cmpl $0,pins(%rip)\n jne .Lbad\n"
    "cmpl $1,(%rdi)\n jne .Lbad\n movl $0,(%rdi)\n"
    "decl mutex_depth(%rip)\n incq mutex_unlocks(%rip)\n"
    ".Ldamage:\n"
    /* RSI is the source stack before CALL, RDX its precise return address. */
    "leaq 8(%rsp),%rax\n cmpq %rax,%rsi\n jne .Lbad\n"
    "cmpq (%rsp),%rdx\n jne .Lbad\n cmpq %rbp,%rcx\n jne .Lbad\n"
    "movq $17,%rbx\n movq $18,%r12\n movq $19,%r13\n"
    "movq $20,%r14\n movq $21,%r15\n"
    "movq $22,%rax\n movq $23,%rdi\n movq $24,%rsi\n"
    "movq $25,%rdx\n movq $26,%rcx\n movq $27,%r8\n"
    "movq $28,%r9\n movq $29,%r10\n movq $30,%r11\n ret\n"
    ".Lbad: ud2\n");

/* Compare these functions with the raw unpinned clobber shell, including
 * relocations. No caller pin or heat read belongs before a nested spin CALL. */
__attribute__((noinline,noipa))
unsigned long api_root_pair(kd_spinlock_t *lock, unsigned long seed)
{
 unsigned long a=seed+1, b=seed+2, c=seed+3, d=seed+4, e=seed+5;
 unsigned long stack[3]={seed+6,seed+7,seed+8};
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : "m"(stack) : "memory");
 SPIN_LOCK(lock);
 assert(pins==1 && lock->val==1 && !mutex_depth);
 a+=stack[0]; b+=stack[1]; c+=stack[2]; d+=seed; e+=seed;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 SPIN_UNLOCK(lock);
 assert(!pins && !lock->val);
 return a+b+c+d+e;
}

__attribute__((noinline,noipa))
unsigned long api_nested_pair(struct kd_mutex *outer, kd_spinlock_t *inner,
                              unsigned long seed)
{
 unsigned long a=seed+1, b=seed+2, c=seed+3, d=seed+4, e=seed+5;
 unsigned long stack[3]={seed+6,seed+7,seed+8};
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : "m"(stack) : "memory");
 kd_mutex_lock(outer);
 assert(!pins && mutex_depth==1 && outer->val==1);
 SPIN_LOCK(inner);
 assert(pins==1 && inner->val==1 && mutex_depth==1 && outer->val==1);
 a+=stack[0]; b+=stack[1]; c+=stack[2]; d+=seed; e+=seed;
 asm volatile("" : "+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e) : : "memory");
 SPIN_UNLOCK(inner);
 assert(!pins && !inner->val && mutex_depth==1);
 kd_mutex_unlock(outer);
 assert(!pins && !mutex_depth && !outer->val);
 return a+b+c+d+e;
}

static void nested_spin(void)
{
 kd_spinlock_t outer={0}, inner={0};
 SPIN_LOCK(&outer);
 assert(pins==1);
 SPIN_LOCK(&inner);
 assert(pins==2);
 SPIN_UNLOCK(&inner);
 assert(pins==1);
 SPIN_UNLOCK(&outer);
 assert(!pins && !outer.val && !inner.val);
}

#if defined(KD_TEST_PUBLIC_API) && !defined(KD_TEST_SPIN_API_EQUIVALENCE)
static unsigned int evaluations;
static kd_spinlock_t *once(kd_spinlock_t *lock)
{
 evaluations++;
 return lock;
}
static void public_contract(void)
{
 kd_spinlock_t locks[3]={{0}};
 kd_spinlock_t *kd_arg=&locks[0], *kd_spin_api_arg=&locks[1];
 kd_spinlock_t *kd_spin_api_word=&locks[2];
 _Static_assert(__builtin_types_compatible_p(
  __typeof__(kd_spin_lock(&locks[0])), void), "lock is a void expression");
 _Static_assert(__builtin_types_compatible_p(
  __typeof__(kd_spin_unlock(&locks[0])), void), "unlock is a void expression");
 (void)(kd_spin_lock(once(kd_arg)), 0);
 assert(pins==1 && locks[0].val==1);
 kd_spin_unlock(once(kd_arg));
 kd_spin_lock(once(kd_spin_api_arg));
 assert(pins==1 && locks[1].val==1);
 kd_spin_unlock(once(kd_spin_api_arg));
 kd_spin_lock(once(kd_spin_api_word));
 assert(pins==1 && locks[2].val==1);
 kd_spin_unlock(once(kd_spin_api_word));
 assert(evaluations==6 && !pins);
 for(unsigned int i=0;i<3;i++) assert(!locks[i].val);
}
#endif

#ifdef KD_TEST_SPIN_API_BAD_LOCK
void wrong_lock(void) { struct kd_mutex wrong; kd_spin_lock(&wrong); }
#endif
#ifdef KD_TEST_SPIN_API_BAD_UNLOCK
void wrong_unlock(void) { struct kd_mutex wrong; kd_spin_unlock(&wrong); }
#endif

int main(void)
{
 kd_spinlock_t spin={0};
 struct kd_mutex mutex={0};
 for(unsigned long i=0;i<1000;i++) {
  assert(api_root_pair(&spin,i)==10*i+36);
  assert(api_nested_pair(&mutex,&spin,i)==10*i+36);
 }
 nested_spin();
 assert(spin_locks==2002 && spin_unlocks==2002);
 assert(mutex_locks==1000 && mutex_unlocks==1000);
#if defined(KD_TEST_PUBLIC_API) && !defined(KD_TEST_SPIN_API_EQUIVALENCE)
 public_contract();
 assert(spin_locks==2005 && spin_unlocks==2005);
#endif
 assert(!pins && !mutex_depth && !spin.val && !mutex.val);
 puts("PASS public spin ABI: destructive root/mutex-nested/spin-nested CALLs, exact SP/IP/BP and balanced provider pins");
}
