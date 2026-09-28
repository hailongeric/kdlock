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
static bool minimal;
static unsigned long expected_sp;
unsigned long observed_sp;
unsigned long observed[15];

static unsigned int unpins;
static bool expected_unpin;
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
	volatile unsigned int iteration;
	_Static_assert(offsetof(struct kd_spin_continuation, frame.regs) == 40,
		       "restore packet follows request metadata and the admission header");
	for (iteration = 0; iteration < 192; iteration++) {
		volatile unsigned int mode = iteration < 128 ? iteration % 4 : iteration % 2;

		minimal = iteration >= 128;
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
			execution.frame.entry_abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
			execution.frame.packet_state = mode ? KD_PACKET_MINIMAL : KD_PACKET_COMPLETE;
		}
		expected_sp = execution.frame.regs.sp + (!minimal && !mode ? 8 : 0);
		if (!setjmp(caller))
			kd_spin_restore_request(&execution, mode);
	}
	assert(restores == 192);
	puts("production continuation restore: completed=32 retry=32 native=32 native_retired=32 minimal_complete=32 minimal_retry=32 PASS");
	return 0;
}
