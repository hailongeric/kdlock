/* SPDX-License-Identifier: GPL-2.0 */
/* Execute the production publication/poll assembly in the guest. A producer
 * overwrites the waiting CPU's actual C frames before waking it. Returning
 * through those frames must fail; completion must use the packet trampoline.
 * This is an x86 userspace stack test, not an IRQ or kernel JIT simulation. */
#include <assert.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define noinline __attribute__((noinline))
#define notrace

struct kd_spin_node {
	struct kd_spin_node *next;
	unsigned char locked, completed;
	bool native_resume;
	unsigned long rsp;
	struct { unsigned long sp; } regs;
};
#include "wait_production.h"

static _Alignas(16) unsigned char task_stack[65536];
static struct kd_spin_node node, previous;
static jmp_buf caller;
static unsigned int mode, restored;

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_spin_resume_completed(struct kd_spin_node *packet)
{
	unsigned long sp;

	asm volatile("movq %%rsp, %0" : "=r"(sp));
	assert(packet == &node && mode);
	assert(sp < node.regs.sp && sp >= (unsigned long)task_stack);
	assert(node.completed == (mode == 1));
	assert(node.native_resume == (mode == 2));
	/* The producer has overwritten every old wait/helper return address. */
	assert(task_stack[sizeof(task_stack) - 8] == 0xa7);
	restored++;
	longjmp(caller, 1);
}

static __attribute__((used, noipa, noreturn)) void test_wait_entry(void)
{
	kd_spin_publish_wait(&node, &previous);
	/* Only the unexecuted head handoff may return through ordinary C. */
	assert(mode == 0 && !node.completed && !node.native_resume);
	longjmp(caller, 1);
}

extern void enter_test_stack(void *top) __attribute__((noreturn));
asm(".text\n"
    ".type enter_test_stack,@function\n"
    "enter_test_stack:\n"
    "movq %rdi,%rsp\n"
    "andq $-16,%rsp\n"
    "call test_wait_entry\n"
    "ud2\n"
    ".size enter_test_stack,.-enter_test_stack\n");

static void *producer(void *unused)
{
	(void)unused;
	while (!__atomic_load_n(&previous.next, __ATOMIC_ACQUIRE))
		asm volatile("pause");
	assert(previous.next == &node);
	if (mode) {
		/* Include the currently executing waiter frame, the call return
		 * word and spill slots. Leave room below the final logical RSP
		 * for the fresh restoration helper to use after release. */
		memset(task_stack + sizeof(task_stack) - 8192, 0xa7, 8192);
		node.completed = mode == 1;
		node.native_resume = mode == 2;
	}
	__atomic_store_n(&node.locked, 0, __ATOMIC_RELEASE);
	return NULL;
}

int main(void)
{
	volatile unsigned int iteration;

	for (iteration = 0; iteration < 96; iteration++) {
		pthread_t worker;

		mode = iteration % 3;
		memset(&node, 0, sizeof(node));
		memset(&previous, 0, sizeof(previous));
		memset(task_stack, 0x53, sizeof(task_stack));
		node.locked = 1;
		node.rsp = (unsigned long)(task_stack + sizeof(task_stack) - 16);
		node.regs.sp = node.rsp - 2048;
		assert(pthread_create(&worker, NULL, producer, NULL) == 0);
		if (!setjmp(caller))
			enter_test_stack(task_stack + sizeof(task_stack));
		assert(pthread_join(worker, NULL) == 0);
	}
	assert(restored == 64);
	puts("production stack-free wait: head=32 completed=32 native=32 PASS");
	return 0;
}
