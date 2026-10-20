/* SPDX-License-Identifier: GPL-2.0 */
/* Compile the public facade and compatibility aliases unchanged. Narrow
 * userspace primitives substitute physical locking; destructive ABI2 callees
 * check real compiler spills and continuation arguments. Generated executions
 * below use the production translator/wrapper, with only control services
 * substituted. Owner/ACK concurrency belongs to the protocol fixtures. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "kd_regs.h"

struct kd_mutex {
	unsigned long owner;
	unsigned int delegation_state;
};
typedef struct { int counter; } atomic_t;
struct lock_class_key { unsigned int unused; };
#define current ((void *)0x8000UL)
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x, value) (*(volatile __typeof__(x) *)&(x) = (value))
#define API_JOIN_RAW(left, right) left##right
#define API_JOIN(left, right) API_JOIN_RAW(left, right)
#define __UNIQUE_ID(prefix) API_JOIN(prefix, __COUNTER__)
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)
#define might_sleep() do { } while (0)
#define atomic_long_read(p) READ_ONCE(*(p))
#define atomic_read_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
static inline bool atomic_long_try_cmpxchg_acquire(unsigned long *word,
						  unsigned long *old,
						  unsigned long value)
{
	return __atomic_compare_exchange_n(word, old, value, false,
					  __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
}
static inline void cpu_relax(void)
{
	asm volatile("pause" : : : "memory");
}
static inline void kd_hotlock_mutex_entry(void) { }

unsigned long direct_locks, direct_unlocks, c_locks, c_unlocks, local_locks;
static int cancel_result;
void kd_mutex_local_lock(struct kd_mutex *lock)
{
	assert(!lock->owner);
	lock->owner = (unsigned long)current;
	local_locks++;
}
void kd_mutex_local_unlock(struct kd_mutex *lock)
{
	assert(lock->owner == (unsigned long)current);
	lock->owner = 0;
}
__attribute__((noinline, noipa)) void kd_mutex_api_lock(struct kd_mutex *lock)
{
	c_locks++;
	kd_mutex_local_lock(lock);
}
__attribute__((noinline, noipa)) void kd_mutex_api_unlock(struct kd_mutex *lock)
{
	c_unlocks++;
	kd_mutex_local_unlock(lock);
}
int kd_mutex_lock_interruptible(struct kd_mutex *lock)
{
	if (!cancel_result)
		kd_mutex_local_lock(lock);
	return cancel_result;
}
int kd_mutex_lock_killable(struct kd_mutex *lock)
{
	return kd_mutex_lock_interruptible(lock);
}
void kd_mutex_lock_io(struct kd_mutex *lock)
{
	kd_mutex_local_lock(lock);
}
int kd_mutex_trylock(struct kd_mutex *lock)
{
	if (lock->owner)
		return 0;
	kd_mutex_local_lock(lock);
	return 1;
}
int kd_atomic_dec_and_mutex_lock(atomic_t *count, struct kd_mutex *lock)
{
	assert(count->counter > 0);
	if (--count->counter)
		return 0;
	kd_mutex_local_lock(lock);
	return 1;
}
bool kd_mutex_is_locked(struct kd_mutex *lock)
{
	return !!lock->owner;
}
void kd_mutex_init(struct kd_mutex *lock)
{
	memset(lock, 0, sizeof(*lock));
}
void __kd_mutex_init(struct kd_mutex *lock, const char *name,
		     struct lock_class_key *key)
{
	(void)name;
	(void)key;
	kd_mutex_init(lock);
}
void kd_mutex_destroy(struct kd_mutex *lock)
{
	assert(!lock->owner);
}

/* Cleanup infrastructure is compiled by the real kernel build. These tests
 * exercise its conventional function targets rather than modeling scope exit. */
#define DEFINE_GUARD(...)
#define DEFINE_FREE(...)
#include "mutex_api.h"
#include "mutex_compat.h"

#define __KERNEL__
#include "kd_jit_batch.h"
extern void main_wrapper(struct kd_regs *, unsigned long *) __attribute__((weak));

unsigned long capture_enabled, captured_sp, captured_bp, captured_ip;
unsigned long captured_bytes, captured_stack[64];
asm(".text\n"
    ".globl kd_mutex_direct_lock_clobber_v1\n"
    "kd_mutex_direct_lock_clobber_v1:\n"
    "cmpq $0,(%rdi)\n jne .Lapi_bad\n"
    "movq $0x8000,(%rdi)\n incq direct_locks(%rip)\n"
    "movq $1,%r8\n jmp .Lapi_metadata\n"
    ".globl kd_mutex_direct_unlock_clobber_v1\n"
    "kd_mutex_direct_unlock_clobber_v1:\n"
    "cmpq $0x8000,(%rdi)\n jne .Lapi_bad\n"
    "movq $0,(%rdi)\n incq direct_unlocks(%rip)\n xorq %r8,%r8\n"
    ".Lapi_metadata:\n"
    "leaq 8(%rsp),%rax\n cmpq %rax,%rsi\n jne .Lapi_bad\n"
    "cmpq (%rsp),%rdx\n jne .Lapi_bad\n"
    "cmpq %rbp,%rcx\n jne .Lapi_bad\n"
    "testq %r8,%r8\n je .Lapi_poison\n"
    "cmpq $0,capture_enabled(%rip)\n je .Lapi_poison\n"
    "cmpq $0,captured_ip(%rip)\n jne .Lapi_poison\n"
    "movq %rsi,captured_sp(%rip)\n movq %rcx,captured_bp(%rip)\n"
    "movq %rdx,captured_ip(%rip)\n"
    "movq %rcx,%rax\n subq %rsi,%rax\n addq $16,%rax\n"
    "cmpq $512,%rax\n ja .Lapi_bad\n movq %rax,captured_bytes(%rip)\n"
    "movq %rax,%rcx\n shrq $3,%rcx\n"
    "leaq captured_stack(%rip),%rdi\n rep movsq\n"
    ".Lapi_poison:\n"
    "movq $17,%rbx\n movq $18,%r12\n movq $19,%r13\n"
    "movq $20,%r14\n movq $21,%r15\n"
    "movq $22,%rax\n movq $23,%rdi\n movq $24,%rsi\n"
    "movq $25,%rdx\n movq $26,%rcx\n movq $27,%r8\n"
    "movq $28,%r9\n movq $29,%r10\n movq $30,%r11\n ret\n"
    ".Lapi_bad: ud2\n");

static struct mutex test_lock __attribute__((section(".api_lock")));
static struct mutex inner_lock __attribute__((section(".api_lock")));

/* There is deliberately no named assembler continuation or prepare() call.
 * The driver obtains the actual captured provider argument from the first
 * executable, then translates this unchanged compiler-produced region. */
__attribute__((noinline, noipa)) unsigned long api_jit_case(void)
{
	volatile unsigned long body = 0x115;

	mutex_lock(&test_lock);
	body++;
#if CASE_NESTED
	mutex_lock(&inner_lock);
	body += 2;
#if CASE_NESTED == 2
	mutex_unlock(&test_lock);
	body += 4;
	mutex_unlock(&inner_lock);
#else
	mutex_unlock(&inner_lock);
	body += 4;
	mutex_unlock(&test_lock);
#endif
#else
	mutex_unlock(&test_lock);
#endif
	return body;
}

static unsigned int evaluations;
__attribute__((noinline, noipa)) static struct mutex *once(struct mutex *lock)
{
	evaluations++;
	return lock;
}

__attribute__((noinline, noipa)) static unsigned long stress(unsigned long seed)
{
	struct mutex lock = { 0 };
	unsigned long a = seed + 1, b = seed + 2, c = seed + 3;
	unsigned long d = seed + 4, e = seed + 5;
	unsigned int before = evaluations;

	_Static_assert(__builtin_types_compatible_p(
		__typeof__(kd_mutex_lock(&lock)), void), "lock is a void expression");
	_Static_assert(__builtin_types_compatible_p(
		__typeof__(kd_mutex_unlock(&lock)), void), "unlock is a void expression");
	asm volatile("" : "+r"(a), "+r"(b), "+r"(c), "+r"(d), "+r"(e)
		     : : "memory");
	(void)(mutex_lock(once(&lock)), 0);
	assert(evaluations == before + 1 && mutex_is_locked(&lock));
	asm volatile("" : "+r"(a), "+r"(b), "+r"(c), "+r"(d), "+r"(e)
		     : : "memory");
	(void)(mutex_unlock(once(&lock)), 0);
	assert(evaluations == before + 2 && !mutex_is_locked(&lock));
	return a + b + c + d + e;
}

static void check_source_api(void)
{
	struct mutex outer = { 0 }, inner = { 0 };
	void (*lock_fn)(struct mutex *) = &mutex_lock;
	void (*unlock_fn)(struct mutex *) = &mutex_unlock;
	unsigned long locks = direct_locks, unlocks = direct_unlocks;
	unsigned int annotations = 0;

	for (unsigned int early = 0; early < 2; early++) {
		mutex_lock(&outer);
		mutex_lock(&inner);
		assert(outer.owner == (unsigned long)current &&
		       inner.owner == (unsigned long)current);
		if (early) {
			mutex_unlock(&outer);
			assert(!outer.owner && inner.owner);
			mutex_unlock(&inner);
		} else {
			mutex_unlock(&inner);
			assert(outer.owner && !inner.owner);
			mutex_unlock(&outer);
		}
	}
	assert(direct_locks == locks + 4 && direct_unlocks == unlocks + 4);
	lock_fn(&outer);
	unlock_fn(&outer);
	(mutex_lock)(&outer);
	(mutex_unlock)(&outer);
	assert(c_locks == 2 && c_unlocks == 2);
	locks = direct_locks;
	mutex_lock_nested(&outer, ++annotations);
	mutex_unlock(&outer);
	mutex_lock_nest_lock(&outer, ++annotations);
	mutex_unlock(&outer);
	assert(!annotations && direct_locks == locks + 2);

	/* Local variants keep their result contracts; each successful acquisition
	 * uses the same public unlock spelling. Physical semantics are substituted
	 * here; production routing/ACK fixtures exercise their real implementation. */
	assert(mutex_trylock(&outer) == 1);
	assert(mutex_trylock(&outer) == 0);
	mutex_unlock(&outer);
	cancel_result = -4;
	assert(mutex_lock_interruptible(&outer) == -4 && !outer.owner);
	assert(mutex_lock_killable(&outer) == -4 && !outer.owner);
	cancel_result = 0;
	assert(!mutex_lock_interruptible(&outer));
	mutex_unlock(&outer);
	assert(!mutex_lock_killable(&outer));
	mutex_unlock(&outer);
	mutex_lock_io(&outer);
	mutex_unlock(&outer);
	assert(!mutex_lock_interruptible_nested(&outer, ++annotations));
	mutex_unlock(&outer);
	assert(!mutex_lock_killable_nested(&outer, ++annotations));
	mutex_unlock(&outer);
	mutex_lock_io_nested(&outer, ++annotations);
	mutex_unlock(&outer);
	assert(!annotations);
	atomic_t count = { 2 };
	assert(!atomic_dec_and_mutex_lock(&count, &outer) && !outer.owner);
	assert(atomic_dec_and_mutex_lock(&count, &outer) && outer.owner);
	mutex_unlock(&outer);
	assert(!outer.owner && !inner.owner);
	unsigned int before = evaluations, device_evaluations = 0;
	outer.owner = (unsigned long)current;
	assert(!devm_mutex_init((assert(!outer.owner), ++device_evaluations,
				(struct device *)0), once(&outer)));
	assert(evaluations == before + 1 && device_evaluations == 1);
	struct lock_class_key key = { 0 };
	__mutex_init(&outer, "fixture", &key);
	mutex_destroy(&outer);
	puts("PASS unified source API: single evaluation, void expression, nested/early release, addressable C symbols and local-result variants");
}

static void check_temporary_names(void)
{
	struct mutex selected[3] = { { 0 }, { 0 }, { 0 } };
	struct mutex *kd_arg = &selected[0];
	struct mutex *kd_lock_arg = &selected[1];
	struct mutex *kd_devm_lock = &selected[2];
	unsigned int before = evaluations;
	unsigned int device_evaluations = 0;
	unsigned long locks = direct_locks, unlocks = direct_unlocks;

	/* Caller identifiers must resolve before the wrapper's temporaries enter
	 * scope. These names intentionally match the production macro locals. */
	mutex_lock(once(kd_arg));
	assert(selected[0].owner && !selected[1].owner && !selected[2].owner);
	mutex_unlock(once(kd_arg));
	mutex_lock(once(kd_lock_arg));
	assert(!selected[0].owner && selected[1].owner && !selected[2].owner);
	mutex_unlock(once(kd_lock_arg));
	selected[2].owner = (unsigned long)current;
	assert(!devm_mutex_init((struct device *)0, once(kd_devm_lock)));
	assert(!selected[0].owner && !selected[1].owner && !selected[2].owner);
	selected[0].owner = (unsigned long)current;
	assert(!devm_mutex_init(
		(assert(!selected[0].owner),
		 assert(kd_devm_lock == &selected[2]),
		 ++device_evaluations, (struct device *)kd_devm_lock),
		once(&selected[0])));
	assert(!selected[0].owner && device_evaluations == 1);
	assert(evaluations == before + 6);
	assert(direct_locks == locks + 2 && direct_unlocks == unlocks + 2);
	puts("PASS unified macro hygiene: caller temporary names, selected object and once-only argument evaluation");
}

#if CASE_NESTED
static void resume_control(struct kd_regs *regs)
{
	assert(regs->si == regs->sp + sizeof(unsigned long));
	assert(regs->cx == regs->bp);
	assert(regs->dx == *(unsigned long *)regs->sp);
	regs->ip = *(unsigned long *)regs->sp;
	regs->sp += sizeof(unsigned long);
}
#endif

static void check_generated(void)
{
	if (!main_wrapper)
		return;
	assert(captured_bytes && captured_bytes <= sizeof(captured_stack));
	for (unsigned int full = 0; full < 2; full++) {
		unsigned long memory[128], *sp = &memory[16];
		unsigned int body_slot = ~0U, state = 1;
		struct kd_regs regs;

		memset(memory, 0xa3, sizeof(memory));
		memcpy(sp, captured_stack, captured_bytes);
		for (unsigned int i = 0; i < captured_bytes / 8; i++) {
			if (sp[i] == 0x115) {
				assert(body_slot == ~0U);
				body_slot = i;
			}
			if (sp[i] >= captured_sp &&
			    sp[i] < captured_sp + captured_bytes)
				sp[i] = (unsigned long)sp + sp[i] - captured_sp;
		}
		assert(body_slot != ~0U);
		memset(&regs, 0xde, sizeof(regs));
		regs.ip = captured_ip;
		regs.sp = (unsigned long)sp;
		regs.bp = (unsigned long)sp + captured_bp - captured_sp;
		test_lock.owner = (unsigned long)current;
		inner_lock.owner = 0;
		unsigned long locks = direct_locks, unlocks = direct_unlocks;
		struct kd_jit_batch_call call = {
			.regs = &regs, .args = { 0, 0 },
			.code = (char *)main_wrapper + KD_JIT_CLOBBER_OFFSET,
			.lock = (unsigned long)&test_lock,
			.unlock = (unsigned long)kd_mutex_direct_unlock_clobber_v1,
			.entry_sp = (unsigned long)sp, .entry_abi = 2,
			.packet_state = &state, .complete = !full,
		};

		kd_jit_clobber_call_v1(&call);
		assert(call.args[1] && sp[body_slot] == 0x116);
		assert(test_lock.owner == (unsigned long)current);
#if CASE_NESTED
		assert(call.args[0] == 1 && state == 0);
		assert(regs.ip == (unsigned long)kd_mutex_direct_lock_clobber_v1);
		assert(regs.di == (unsigned long)&inner_lock && !inner_lock.owner);
		/* Simulate the known-control service, retaining the exact packet
		 * and return token. No native callee repairs the compiled ABI. */
		inner_lock.owner = (unsigned long)current;
		resume_control(&regs);
		call.args[0] = call.args[1] = 0;
		main_wrapper(&regs, call.args);
		assert(call.args[0] == 1 && call.args[1]);
		assert(regs.ip == (unsigned long)kd_mutex_direct_unlock_clobber_v1);
		assert(sp[body_slot] == 0x118);
#if CASE_NESTED == 2
		assert(regs.di == (unsigned long)&test_lock);
		test_lock.owner = 0;
#else
		assert(regs.di == (unsigned long)&inner_lock);
		inner_lock.owner = 0;
#endif
		resume_control(&regs);
		call.args[0] = call.args[1] = 0;
		main_wrapper(&regs, call.args);
		assert(call.args[0] == 1 && call.args[1] && state == 0);
		assert(regs.ip == (unsigned long)kd_mutex_direct_unlock_clobber_v1);
		assert(sp[body_slot] == 0x11c);
#if CASE_NESTED == 2
		assert(regs.di == (unsigned long)&inner_lock && !test_lock.owner);
		assert(inner_lock.owner == (unsigned long)current);
#else
		assert(regs.di == (unsigned long)&test_lock && !inner_lock.owner);
		assert(test_lock.owner == (unsigned long)current);
#endif
		assert(regs.sp == (unsigned long)sp - 8);
		assert(regs.dx == *(unsigned long *)regs.sp);
#else
		if (full) {
			assert(call.args[0] == 1 && state == 0);
			assert(regs.ip == (unsigned long)kd_mutex_direct_unlock_clobber_v1);
			assert(regs.sp == (unsigned long)sp - 8);
			assert(*(unsigned long *)regs.sp == regs.dx);
		} else {
			assert(call.args[0] == 7 && state == 2);
			assert(regs.sp == (unsigned long)sp);
		}
#endif
		assert(direct_locks == locks && direct_unlocks == unlocks);
		test_lock.owner = inner_lock.owner = 0;
	}
#if CASE_NESTED
	puts("PASS compiled unified nested entry: strict admission, exact B control exits, FULL resume and no replay");
#else
	puts("PASS compiled unified root entry: anonymous continuation, poisoned GPRs, untouched owner, COMPLETE and exact FULL");
#endif
}

int main(void)
{
	check_source_api();
	check_temporary_names();
	for (unsigned long seed = 0; seed < 100; seed++)
		assert(stress(seed) == 5 * seed + 15);
	capture_enabled = 1;
	assert(api_jit_case() == (CASE_NESTED ? 0x11c : 0x116));
	capture_enabled = 0;
	assert(!test_lock.owner && !inner_lock.owner && captured_ip);
	printf("ENTRY %lx\n", captured_ip);
	check_generated();
	puts("PASS unified ABI2 facade: preserved compiler live values and exact SP/IP/BP");
}
