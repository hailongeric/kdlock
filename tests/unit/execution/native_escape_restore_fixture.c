/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "kd_regs.h"
#define noinline __attribute__((noinline))
#define notrace
#include "production.h"

struct kd_regs resume_packet, result_packet;
unsigned long caller_stack, caller_flags;
static unsigned char target_stack[4096] __attribute__((aligned(16)));
extern void run_restore(void), escaped_landing(void);

#if defined(CONFIG_MITIGATION_RETHUNK) || defined(CONFIG_RETHUNK)
/* A flags-neutral stand-in exercises the provider's configured jump path.
 * The live kernel probe separately executes the real selected return thunk. */
asm(".text\n.globl __x86_return_thunk\n__x86_return_thunk:\nretq\nint3\n");
#endif

/* Capture every restored register using RIP-relative stores before any test
 * instruction. The C caller's own preserved registers and stack are restored
 * separately, so the tested packet can contain arbitrary distinct values. */
asm(".text\n"
    ".globl run_restore\nrun_restore:\n"
    "pushq %rbp\npushq %rbx\npushq %r12\npushq %r13\npushq %r14\npushq %r15\n"
    "subq $8,%rsp\nmovq %rsp,caller_stack(%rip)\n"
    "pushfq\npopq caller_flags(%rip)\n"
    "leaq resume_packet(%rip),%rdi\ncall jump_to_saved_regs_in_cs\nud2\n"
    ".globl escaped_landing\nescaped_landing:\n"
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

int main(void)
{
	static const unsigned int bits[] = {0, 2, 4, 6, 7, 11};
	for (unsigned int pattern = 0; pattern < 64; pattern++) {
		struct kd_regs unchanged;
		unsigned long *input = (unsigned long *)&resume_packet;
		unsigned long arithmetic = 0;
		for (unsigned int bit = 0; bit < 6; bit++)
			if (pattern & (1U << bit))
				arithmetic |= 1UL << bits[bit];
		for (unsigned int word = 0; word < sizeof(resume_packet) / sizeof(*input); word++)
			input[word] = 0x1100000000000000UL + word * 0x01020304050607UL;
		resume_packet.ip = (unsigned long)escaped_landing;
		resume_packet.sp = (unsigned long)(target_stack + sizeof(target_stack) - 64);
		resume_packet.orig_ax = KD_REG_NATIVE_ESCAPE_TAG;
		/* Poison every control bit: none may be installed on the waiter. */
		resume_packet.flags = ~KD_REG_ARITHMETIC_FLAGS | arithmetic;
		unchanged = resume_packet;
		memset(target_stack, 0xa5, sizeof(target_stack));
		memset(&result_packet, 0, sizeof(result_packet));
		run_restore();
		assert(!memcmp(&resume_packet, &unchanged, sizeof(unchanged)));
		for (size_t byte = 0; byte < sizeof(target_stack); byte++)
			if (byte < sizeof(target_stack) - 80 || byte >= sizeof(target_stack) - 64)
				assert(target_stack[byte] == 0xa5);
		assert(!memcmp(&result_packet.sp, &resume_packet.sp,
			       KD_REG_ORIG_AX - KD_REG_SP));
		assert((result_packet.flags & KD_REG_ARITHMETIC_FLAGS) == arithmetic);
		assert((result_packet.flags & ~KD_REG_ARITHMETIC_FLAGS) ==
		       (caller_flags & ~KD_REG_ARITHMETIC_FLAGS));
	}
	printf("native marker restore: 64 arithmetic-flag combinations, all GPRs, exact SP and waiter control flags passed; return=%s\n",
#if defined(CONFIG_MITIGATION_RETHUNK) || defined(CONFIG_RETHUNK)
	       "configured-thunk-stand-in"
#else
	       "direct"
#endif
	);
	return 0;
}
