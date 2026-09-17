/* SPDX-License-Identifier: GPL-2.0 */
/* Execute the production shadow-stack/publication/poll assembly in the guest.
 * A signal delivered on an alternate stack samples the actual polling RSP.
 * A producer
 * overwrites the waiting CPU's actual C frames before waking it. Returning
 * through those frames must fail; completion must use the packet trampoline.
 * This is an x86 userspace stack test, not an IRQ or kernel JIT simulation. */
#define _GNU_SOURCE
#include <assert.h>
#include <pthread.h>
#include <setjmp.h>
#include <signal.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <ucontext.h>

#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define noinline __attribute__((noinline))
#define notrace

struct pt_regs { unsigned long sp; };
struct kd_spin_exec_request {
	struct { struct pt_regs *regs_ref; } frame;
	bool native_resume;
};
struct kd_spin_node {
	struct kd_spin_node *next;
	unsigned char locked, completed;
	unsigned long rsp;
	struct kd_spin_exec_request *execution;
};
#include "wait_production.h"

static _Alignas(16) unsigned char task_stack[65536];
static _Alignas(16) unsigned char shadow_stack[8192];
static _Alignas(16) unsigned char signal_stack[65536];
static struct kd_spin_node node, previous;
static struct pt_regs packet;
static struct kd_spin_exec_request execution;
static jmp_buf caller;
static unsigned int mode, restored;
static pthread_t waiter;
static unsigned long polling_rsp;
static sig_atomic_t sampled;

/* Observe the interrupted machine context, not the signal handler's own RSP.
 * The producer keeps locked set until this observation completes. */
static void sample_polling_rsp(int signal, siginfo_t *info, void *context)
{
	ucontext_t *uc = context;

	(void)signal;
	(void)info;
	polling_rsp = uc->uc_mcontext.gregs[REG_RSP];
	__atomic_store_n(&sampled, 1, __ATOMIC_RELEASE);
}

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_spin_resume_completed(struct kd_spin_node *packet)
{
	unsigned long sp;

	asm volatile("movq %%rsp, %0" : "=r"(sp));
	assert(packet == &node && mode);
	assert(sp < execution.frame.regs_ref->sp && sp >= (unsigned long)task_stack);
	assert(node.completed == (mode == 1));
	assert(execution.native_resume == (mode == 2));
	/* The producer has overwritten every old wait/helper return address. */
	assert(task_stack[sizeof(task_stack) - 8] == 0xa7);
	restored++;
	longjmp(caller, 1);
}

static __attribute__((used, noipa, noreturn)) void test_wait_entry(void)
{
	unsigned long before, after;

	asm volatile("movq %%rsp, %0" : "=r"(before));
	kd_spin_publish_wait(&node, &previous, shadow_stack + sizeof(shadow_stack));
	asm volatile("movq %%rsp, %0" : "=r"(after));
	/* Only the unexecuted head handoff may return through ordinary C. */
	assert(before == after);
	assert(mode == 0 && !node.completed && !execution.native_resume);
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
	assert(pthread_kill(waiter, SIGUSR1) == 0);
	while (!__atomic_load_n(&sampled, __ATOMIC_ACQUIRE))
		asm volatile("pause");
	assert(polling_rsp == (unsigned long)(shadow_stack + sizeof(shadow_stack) - 8));
	/* The only saved wait state is the old C RSP; no frame/GPR copy. */
	unsigned long saved_rsp;
	memcpy(&saved_rsp, (void *)polling_rsp, sizeof(saved_rsp));
	assert(saved_rsp >= (unsigned long)task_stack);
	assert(saved_rsp < (unsigned long)(task_stack + sizeof(task_stack)));
	if (mode) {
		/* Include the currently executing waiter frame, the call return
		 * word and spill slots. Leave room below the final logical RSP
		 * for the fresh restoration helper to use after release. */
		memset(task_stack + sizeof(task_stack) - 8192, 0xa7, 8192);
		node.completed = mode == 1;
		execution.native_resume = mode == 2;
	}
	__atomic_store_n(&node.locked, 0, __ATOMIC_RELEASE);
	return NULL;
}

int main(void)
{
	volatile unsigned int iteration;
	stack_t alternate = { .ss_sp = signal_stack, .ss_size = sizeof(signal_stack) };
	struct sigaction action = {
		.sa_sigaction = sample_polling_rsp,
		.sa_flags = SA_SIGINFO | SA_ONSTACK,
	};

	assert(sigaltstack(&alternate, NULL) == 0);
	sigemptyset(&action.sa_mask);
	assert(sigaction(SIGUSR1, &action, NULL) == 0);
	waiter = pthread_self();

	for (iteration = 0; iteration < 96; iteration++) {
		pthread_t worker;

		mode = iteration % 3;
		__atomic_store_n(&sampled, 0, __ATOMIC_RELAXED);
		memset(&node, 0, sizeof(node));
		memset(&previous, 0, sizeof(previous));
		memset(task_stack, 0x53, sizeof(task_stack));
		node.execution = &execution;
		execution.native_resume = false;
		execution.frame.regs_ref = &packet;
		node.locked = 1;
		node.rsp = (unsigned long)(task_stack + sizeof(task_stack) - 16);
		execution.frame.regs_ref->sp = node.rsp - 2048;
		assert(pthread_create(&worker, NULL, producer, NULL) == 0);
		if (!setjmp(caller))
			enter_test_stack(task_stack + sizeof(task_stack));
		assert(pthread_join(worker, NULL) == 0);
	}
	assert(restored == 64);
	puts("production shadow-stack wait: sampled=96 head=32 completed=32 native=32 PASS");
	return 0;
}
