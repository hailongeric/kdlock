/* SPDX-License-Identifier: GPL-2.0 */
/* Run the production final restore in guest userspace. Observe every restored
 * GPR and the final request decrement; IRQ masking remains a live-kernel test. */
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
#include "restore_types.h"
struct kd_spin_exec_request {
	struct kd_exec_frame frame;
	struct kd_spin_exec_request *packet_owner;
	int users;
};
#define noinline __attribute__((noinline))
#define notrace
#include "restore_production.h"

static struct kd_spin_exec_request execution;
static _Alignas(16) unsigned char stack[16384];
static jmp_buf caller;
static unsigned int extra_user, restores;
unsigned long observed[15];

static __attribute__((used, noipa, noreturn)) void restored(void)
{
	assert(execution.users == (int)extra_user);
	for (unsigned int i = 0; i < 15; i++)
		assert(observed[i] == 0x12340000UL + i);
	/* A different task may now recycle a completed request. No remaining
	 * assembly read may depend on these bytes. */
	memset(&execution, 0xa5, sizeof(execution));
	restores++;
	longjmp(caller, 1);
}
extern void capture(void);
asm(".text\n.type capture,@function\ncapture:\n"
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
	_Static_assert(offsetof(struct kd_spin_exec_request, frame.regs) == 64,
		       "restore packet follows the hot header");
	for (iteration = 0; iteration < 96; iteration++) {
		unsigned long flags, *packet = (void *)&execution.frame.regs;
		unsigned int mode = iteration % 3;

		memset(&execution, 0, sizeof(execution));
		for (unsigned int i = 0; i < 15; i++)
			packet[i] = 0x12340000UL + i;
		extra_user = mode == 2;
		execution.users = 1 + extra_user;
		execution.frame.spin_simple = !mode && iteration % 2;
		execution.frame.regs.ip = (unsigned long)capture;
		execution.frame.regs.sp = (unsigned long)(stack + sizeof(stack) -
							(mode ? 8 : 16));
		if (!mode)
			*(unsigned long *)execution.frame.regs.sp = (unsigned long)capture;
		asm volatile("pushfq; popq %0" : "=r"(flags));
		if (!setjmp(caller))
			kd_spin_restore_request(&execution, flags, mode);
	}
	assert(restores == 96);
	puts("production shared-request restore: completed=32 retry=32 native=32 PASS");
	return 0;
}
