/* SPDX-License-Identifier: GPL-2.0 */
/* Run the production final restore in guest userspace. Observe every restored
 * GPR, retirement and final unpin; the live kernel checks IRQ state. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
struct task_struct { int pid; };
struct list_head { struct list_head *next, *prev; };
typedef int atomic_t;
typedef uint64_t u64;
typedef uint8_t u8;
typedef uint16_t u16;
#include "restore_types.h"

#define noinline __attribute__((noinline))
#define BUG_ON(x) assert(!(x))
#define notrace

static struct kd_spin_continuation_stack storage;
#define execution storage.records[0]
static _Alignas(16) unsigned char stack[16384];
static jmp_buf caller;
static unsigned int extra_user, restores, initial_top;
static bool minimal, marker;
static unsigned long expected_sp;
unsigned long observed_sp;
unsigned long observed[15];
unsigned long observed_flags;
static unsigned long expected_arithmetic, caller_flags;
static struct kd_jit_image marker_image = {
	.requirements = KD_IMAGE_REQUIRE_NATIVE_ESCAPE | KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE,
	.immutable = 1,
};
static struct kd_jit_image ordinary_image;

static unsigned int unpins;
static bool expected_unpin;
#ifdef CONFIG_RETHUNK
/* The live probe separately exercises the kernel's actual configured thunk. */
asm(".text\n.globl __x86_return_thunk\n__x86_return_thunk:\nretq\nint3\n");
#endif
static void final_unpin(void)
{
	assert(execution.retired && !storage.top);
	unpins++;
	/* A schedule may immediately reuse per-CPU packets after this point. */
	memset(&execution.frame.regs, 0xa5, sizeof(execution.frame.regs));
}
#define preempt_enable() final_unpin()
#undef execution
#include "restore_production.h"
#define execution storage.records[0]

static __attribute__((used, noipa, noreturn)) void restored(void)
{
	assert(unpins == expected_unpin);
	assert(execution.retired == !extra_user);
	assert(storage.top == (extra_user ? initial_top : 0));
	assert(observed_sp == expected_sp);
	if (marker) {
		assert((observed_flags & KD_REG_ARITHMETIC_FLAGS) == expected_arithmetic);
		assert((observed_flags & ~KD_REG_ARITHMETIC_FLAGS) ==
		       (caller_flags & ~KD_REG_ARITHMETIC_FLAGS));
		assert(execution.frame.regs.orig_ax == KD_REG_NATIVE_ESCAPE_TAG);
	}
	for (unsigned int i = 0; i < 15; i++)
		if (!minimal || i == 4)
			assert(observed[i] == 0x12340000UL + i);
	if (minimal)
		assert(observed[14] != 0x12340000UL + 14);
	/* A different task may now recycle a completed request. No remaining
	 * assembly read may depend on these bytes. */
	memset(&execution, 0xa5, sizeof(execution));
	restores++;
	longjmp(caller, 1);
}
extern void capture(void);
asm(".text\n.type capture,@function\ncapture:\n"
    "pushfq\npopq observed_flags(%rip)\n"
    "movq %rsp,observed_sp(%rip)\n"
    "movq %r15,observed+0(%rip)\n"
    "movq %r14,observed+8(%rip)\n"
    "movq %r13,observed+16(%rip)\n"
    "movq %r12,observed+24(%rip)\n"
    "movq %rbp,observed+32(%rip)\n"
    "movq %rbx,observed+40(%rip)\n"
    "movq %r11,observed+48(%rip)\n"
    "movq %r10,observed+56(%rip)\n"
    "movq %r9,observed+64(%rip)\n"
    "movq %r8,observed+72(%rip)\n"
    "movq %rax,observed+80(%rip)\n"
    "movq %rcx,observed+88(%rip)\n"
    "movq %rdx,observed+96(%rip)\n"
    "movq %rsi,observed+104(%rip)\n"
    "movq %rdi,observed+112(%rip)\n"
    "jmp restored\n.size capture,.-capture\n");

int main(void)
{
	static const unsigned int bits[] = {0, 2, 4, 6, 7, 11};
	volatile unsigned int iteration;
	_Static_assert(offsetof(struct kd_spin_continuation, frame.regs) == 40,
		       "restore packet follows request metadata and the admission header");
	for (iteration = 0; iteration < 320; iteration++) {
		volatile unsigned int mode = iteration < 128 ? iteration % 4 :
			iteration < 192 ? iteration % 2 : 2;

		minimal = iteration >= 128 && iteration < 192;
		marker = iteration >= 192;
		unpins = 0;
		expected_unpin = mode == 0 || mode == 3;

		memset(&execution, 0, sizeof(execution));
		execution.frame.regs.r15 = 0x12340000UL + 0;
		execution.frame.regs.r14 = 0x12340000UL + 1;
		execution.frame.regs.r13 = 0x12340000UL + 2;
		execution.frame.regs.r12 = 0x12340000UL + 3;
		execution.frame.regs.bp = 0x12340000UL + 4;
		execution.frame.regs.bx = 0x12340000UL + 5;
		execution.frame.regs.r11 = 0x12340000UL + 6;
		execution.frame.regs.r10 = 0x12340000UL + 7;
		execution.frame.regs.r9 = 0x12340000UL + 8;
		execution.frame.regs.r8 = 0x12340000UL + 9;
		execution.frame.regs.ax = 0x12340000UL + 10;
		execution.frame.regs.cx = 0x12340000UL + 11;
		execution.frame.regs.dx = 0x12340000UL + 12;
		execution.frame.regs.si = 0x12340000UL + 13;
		execution.frame.regs.di = 0x12340000UL + 14;
		/* An ordinary image's stale bytes and a normal ROOT image's FULL
		 * completion must never select the flags-aware native path. */
		execution.frame.regs.orig_ax = KD_REG_NATIVE_ESCAPE_TAG;
		if (iteration < 128 && (mode == 0 || (mode == 2 && iteration % 8 == 2))) {
			execution.frame.image = &marker_image;
			execution.frame.entry_abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
			marker_image.entry_abi = execution.frame.entry_abi;
			if (mode == 2)
				execution.frame.regs.orig_ax = 0; /* ordinary native CALL */
		}
		if (iteration < 128 && mode == 2 && iteration % 8 == 6) {
			/* A real ordinary descriptor must ignore stale marker bytes.
			 * NULL alone would not exercise the image requirement filter. */
			execution.frame.entry_abi = iteration & 8 ?
				KD_ENTRY_ABI_SPIN_CLOBBER_V1 : KD_ENTRY_ABI_RWLOCK_CLOBBER_V1;
			ordinary_image.entry_abi = execution.frame.entry_abi;
			execution.frame.image = &ordinary_image;
		}
		if (mode == 2)
			execution.result = KD_SPIN_RES_NATIVE_READY;
		extra_user = mode == 2;
		execution.storage = &storage;
		initial_top = iteration & 1 ? 3 : 1;
		storage.top = initial_top;
		storage.records[1].retired = storage.records[2].retired = true;
		execution.frame.spin_simple = !mode && iteration % 2;
		execution.frame.regs.ip = (unsigned long)capture;
		execution.frame.regs.sp = (unsigned long)(stack + sizeof(stack) -
							(mode ? 8 : 16));
		if (!mode)
			*(unsigned long *)execution.frame.regs.sp = (unsigned long)capture;
		if (minimal) {
			execution.frame.regs.sp = (unsigned long)(stack + sizeof(stack) - 8);
			execution.frame.entry_abi = iteration & 1 ? KD_ENTRY_ABI_SPIN_CLOBBER_V1 :
				KD_ENTRY_ABI_RWLOCK_CLOBBER_V1;
			execution.frame.packet_state = mode ? KD_PACKET_MINIMAL : KD_PACKET_COMPLETE;
		}
		if (marker) {
			expected_arithmetic = 0;
			for (unsigned int bit = 0; bit < 6; bit++)
				if ((iteration - 192) % 64 & (1U << bit))
					expected_arithmetic |= 1UL << bits[bit];
			execution.frame.entry_abi = iteration < 256 ?
				KD_ENTRY_ABI_SPIN_CLOBBER_V1 : KD_ENTRY_ABI_RWLOCK_CLOBBER_V1;
			marker_image.entry_abi = execution.frame.entry_abi;
			execution.frame.image = &marker_image;
			execution.frame.spin_kind = KD_SPIN_CONT_ROOT;
			execution.frame.regs.flags = ~KD_REG_ARITHMETIC_FLAGS | expected_arithmetic;
		}
		expected_sp = execution.frame.regs.sp + (!minimal && !mode ? 8 : 0);
		if (!setjmp(caller)) {
			asm volatile("pushfq\npopq %0" : "=m"(caller_flags) : : "memory");
			kd_spin_restore_request(&execution, mode);
		}
	}
	assert(restores == 320);
	puts("production continuation restore: 192 ordinary/stale-tag cases, ABI1/ABI3 64 arithmetic patterns each, exact GPR/SP, retained mode2 storage and zero premature unpins PASS");
	return 0;
}
