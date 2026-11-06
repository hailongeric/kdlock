/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "kd_regs.h"
#define noinline __attribute__((noinline))
#define notrace
#define __noreturn __attribute__((noreturn))
struct module { int unused; };
struct module fixture_owner;
static unsigned int module_put_calls;
static __attribute__((noinline)) void module_put(struct module *owner)
{
	assert(owner == &fixture_owner);
	module_put_calls++;
}
#include "production.h"

unsigned char fixture_stack[8192] __attribute__((aligned(16)));
extern struct kd_regs fixture_packet;
/* Match the observed local-packet geometry: SP=T, packet=[T-216,T-48). */
asm(".globl fixture_packet\n.set fixture_packet,fixture_stack+5928\n");
struct kd_regs result_packet;
unsigned long caller_stack, caller_flags, helper_stack;
extern void run_restore(void), continuation_landing(void);
#if defined(CONFIG_MITIGATION_RETHUNK) || defined(CONFIG_RETHUNK)
/* Exercise the configured jump route; actual kernel thunk coverage is separate. */
asm(".text\n.globl __x86_return_thunk\n__x86_return_thunk:\nretq\nint3\n");
#endif
asm(".text\n.globl run_restore\nrun_restore:\n"
    "pushq %rbp\npushq %rbx\npushq %r12\npushq %r13\npushq %r14\npushq %r15\n"
    "subq $8,%rsp\nmovq %rsp,caller_stack(%rip)\n"
    "pushfq\npopq caller_flags(%rip)\n"
    "movq helper_stack(%rip),%rsp\nleaq fixture_owner(%rip),%rdi\n"
    "leaq fixture_packet(%rip),%rsi\ncall kd_rwsem_provider_resume\nud2\n"
    ".globl continuation_landing\ncontinuation_landing:\n"
    "pushfq\npopq result_packet+152(%rip)\n"
    "movq %rsp,result_packet+8(%rip)\nmovq %rbp,result_packet+16(%rip)\n"
    "movq %r15,result_packet+24(%rip)\nmovq %r14,result_packet+32(%rip)\n"
    "movq %r13,result_packet+40(%rip)\nmovq %r12,result_packet+48(%rip)\n"
    "movq %r11,result_packet+56(%rip)\nmovq %rbx,result_packet+64(%rip)\n"
    "movq %r10,result_packet+72(%rip)\nmovq %r9,result_packet+80(%rip)\n"
    "movq %r8,result_packet+88(%rip)\nmovq %rax,result_packet+96(%rip)\n"
    "movq %rcx,result_packet+104(%rip)\nmovq %rdx,result_packet+112(%rip)\n"
    "movq %rsi,result_packet+120(%rip)\nmovq %rdi,result_packet+128(%rip)\n"
    "movq caller_stack(%rip),%rsp\naddq $8,%rsp\n"
    "popq %r15\npopq %r14\npopq %r13\npopq %r12\npopq %rbx\npopq %rbp\nretq\n");

int main(int argc, char **argv)
{
	static const unsigned int bits[] = {0, 2, 4, 6, 7, 11};
	unsigned int cases = 0;
	assert(argc == 1 || (argc == 2 && (!strcmp(argv[1], "ordinary") || !strcmp(argv[1], "tagged"))));
	for (unsigned int tagged = 0; tagged < 2; tagged++) {
		if (argc == 2 && tagged != !strcmp(argv[1], "tagged"))
			continue;
		for (unsigned int pattern = 0; pattern < (tagged ? 64U : 1U); pattern++) {
			struct kd_regs expected;
			unsigned long *words = (unsigned long *)&fixture_packet;
			unsigned long arithmetic = 0;
			memset(fixture_stack, 0xa5, sizeof(fixture_stack));
			for (unsigned int word = 0; word < sizeof(fixture_packet) / sizeof(*words); word++)
				words[word] = 0x1100000000000000UL + word * 0x01020304050607UL;
			for (unsigned int bit = 0; bit < 6; bit++)
				if (pattern & (1U << bit))
					arithmetic |= 1UL << bits[bit];
			fixture_packet.ip = (unsigned long)continuation_landing;
			fixture_packet.sp = (unsigned long)fixture_stack + 6144;
			fixture_packet.orig_ax = tagged ? KD_REG_ORIGIN_SUFFIX_TAG : 0;
			fixture_packet.flags = ~KD_REG_ARITHMETIC_FLAGS | arithmetic;
			helper_stack = fixture_packet.sp - 512;
			expected = fixture_packet;
			*(unsigned long *)expected.sp = tagged ? 0x73194286abcdef00UL : expected.ip;
			memset(&result_packet, 0, sizeof(result_packet));
			module_put_calls = 0;
			run_restore();
			if (result_packet.di != expected.di) {
				printf("DI mismatch: mode=%s expected=%lx actual=%lx\n",
				       tagged ? "tagged" : "ordinary", expected.di, result_packet.di);
				return 1;
			}
			assert(module_put_calls == 1);
			assert(result_packet.sp == expected.sp + (tagged ? 0 : 8));
			assert(!memcmp(&result_packet.bp, &expected.bp, KD_REG_ORIG_AX - KD_REG_BP));
			if (tagged) {
				assert(*(unsigned long *)expected.sp == 0x73194286abcdef00UL);
				assert((result_packet.flags & KD_REG_ARITHMETIC_FLAGS) == arithmetic);
				assert((result_packet.flags & ~KD_REG_ARITHMETIC_FLAGS) ==
				       (caller_flags & ~KD_REG_ARITHMETIC_FLAGS));
			}
#ifdef MODEL_PACKET_REUSE
			assert(fixture_packet.di == 0);
#else
			assert(!memcmp(&fixture_packet, &expected, sizeof(expected)));
#endif
			cases++;
		}
	}
	printf("builtin MM restore: %u cases; all GPRs, exact SP, tagged flags and source CALL word passed\n", cases);
	return 0;
}
