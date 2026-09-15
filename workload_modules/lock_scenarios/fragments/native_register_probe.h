/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_NATIVE_REGISTER_PROBE_H
#define KD_NATIVE_REGISTER_PROBE_H

/* Native callee entry, before any C prologue. RBP/RSP stay valid stack pointers.
 * This tests GPR/CALL-stack state, deliberately not arithmetic flags. */
#define KD_REG_STAMPS(X)               \
	X(rax, 0, 0x1122334455667788)  \
	X(rbx, 1, 0x2233445566778899)  \
	X(rcx, 2, 0x33445566778899aa)  \
	X(rdx, 3, 0x445566778899aabb)  \
	X(rsi, 4, 0x5566778899aabbcc)  \
	X(r8, 8, 0x66778899aabbccdd)   \
	X(r9, 9, 0x778899aabbccddee)   \
	X(r10, 10, 0x8899aabbccddeeff) \
	X(r11, 11, 0x99aabbccddeeff00) \
	X(r12, 12, 0xaabbccddeeff0011) \
	X(r13, 13, 0xbbccddeeff001122) \
	X(r14, 14, 0xccddeeff00112233) \
	X(r15, 15, 0xddeeff0011223344)
#define KD_REG_TAG0 0x13579bdf2468ace0
#define KD_REG_TAG1 0xfedcba9876543210
#define KD_REG_RETURN 0x5a3cc396a5696996
#define KD_REG_STRING_(value) #value
#define KD_REG_STRING(value) KD_REG_STRING_(value)

struct kd_register_sample {
	unsigned long gpr[16];
	unsigned long return_ip, tag0, tag1;
	unsigned long expected_sp, expected_bp, expected_ip;
	unsigned long returned_ax, calls, seed, pid, marked;
};

_Static_assert(sizeof(unsigned long) == 8, "x86-64 probe only");
_Static_assert(sizeof(struct kd_register_sample) == 216, "probe layout");
_Static_assert(__builtin_offsetof(struct kd_register_sample, return_ip) == 128,
	       "capture offsets");
_Static_assert(__builtin_offsetof(struct kd_register_sample, expected_sp) ==
		       152,
	       "caller offsets");
_Static_assert(__builtin_offsetof(struct kd_register_sample, seed) == 192,
	       "seed offset");

#define KD_REG_CAPTURE(reg, index, value) \
	"movq %" #reg ", 8*" #index "(%rdi)\n\t"
asm(".pushsection .text,\"ax\",@progbits\n\t"
    ".balign 16\n\t"
    ".globl kd_resume_register_capture\n\t"
    ".type kd_resume_register_capture,@function\n"
    "kd_resume_register_capture:\n\t"
    "endbr64\n\t" KD_REG_STAMPS(
	    KD_REG_CAPTURE) "movq %rdi, 40(%rdi)\n\t"
			    "movq %rbp, 48(%rdi)\n\t"
			    "movq %rsp, 56(%rdi)\n\t"
			    "movq (%rsp), %rax\n\t"
			    "movq %rax, 128(%rdi)\n\t"
			    "movq 8(%rsp), %rax\n\t"
			    "movq %rax, 136(%rdi)\n\t"
			    "movq 16(%rsp), %rax\n\t"
			    "movq %rax, 144(%rdi)\n\t"
			    "incq 184(%rdi)\n\t"
			    "movabsq $" KD_REG_STRING(
				    KD_REG_RETURN) ", %rax\n\t"
						   "xorq 192(%rdi), %rax\n\t" ASM_RET
						   ".size kd_resume_register_capture,.-kd_resume_register_capture\n\t"
						   ".popsection\n");
#undef KD_REG_CAPTURE

#define KD_REG_SET(reg, index, value)         \
	"movabsq $" #value ", %%" #reg "\n\t" \
	"xorq 192(%%rdi), %%" #reg "\n\t"
static inline __attribute__((always_inline)) void
kd_register_probe(struct kd_register_sample *sample)
{
	asm volatile(
		"pushq %%rbx\n\t"
		"pushq %%r12\n\t"
		"pushq %%r13\n\t"
		"pushq %%r14\n\t"
		"pushq %%r15\n\t"
		"subq $24, %%rsp\n\t"
		"leaq -8(%%rsp), %%rax\n\t"
		"movq %%rax, 152(%%rdi)\n\t"
		"movq %%rbp, 160(%%rdi)\n\t"
		"leaq 1f(%%rip), %%rax\n\t"
		"movq %%rax, 168(%%rdi)\n\t"
		"movabsq $" KD_REG_STRING(
			KD_REG_TAG0) ", %%rax\n\t"
				     "xorq 192(%%rdi), %%rax\n\t"
				     "movq %%rax, (%%rsp)\n\t"
				     "movabsq $" KD_REG_STRING(
					     KD_REG_TAG1) ", %%rax\n\t"
							  "xorq 192(%%rdi), %%rax\n\t"
							  "movq %%rax, 8(%%rsp)\n\t" KD_REG_STAMPS(
								  KD_REG_SET) "call kd_resume_register_capture\n"
									      "1:\n\t"
									      "movq %%rax, 176(%%rdi)\n\t"
									      "addq $24, %%rsp\n\t"
									      "popq %%r15\n\t"
									      "popq %%r14\n\t"
									      "popq %%r13\n\t"
									      "popq %%r12\n\t"
									      "popq %%rbx\n\t"
		: "+D"(sample)
		:
		: "rax", "rcx", "rdx", "rsi", "r8", "r9", "r10", "r11",
		  "memory", "cc");
}
#undef KD_REG_SET

static unsigned long kd_register_mismatch(const struct kd_register_sample *s,
					  unsigned long seed)
{
#define KD_REG_EXPECT(reg, index, value) [index] = (value) ^ seed,
	unsigned long expected[16] = { KD_REG_STAMPS(KD_REG_EXPECT) };
#undef KD_REG_EXPECT
	unsigned long errors = 0;
	unsigned int i;

	expected[5] = (unsigned long)s;
	expected[6] = s->expected_bp;
	expected[7] = s->expected_sp;
	for (i = 0; i < 16; i++)
		if (s->gpr[i] != expected[i])
			errors |= 1UL << i;
	if (!s->expected_bp)
		errors |= 1UL << 6;
	if (!s->expected_sp)
		errors |= 1UL << 7;
	if (!s->expected_ip || s->return_ip != s->expected_ip)
		errors |= 1UL << 16;
	if (s->tag0 != (KD_REG_TAG0 ^ seed))
		errors |= 1UL << 17;
	if (s->tag1 != (KD_REG_TAG1 ^ seed))
		errors |= 1UL << 18;
	if (s->returned_ax != (KD_REG_RETURN ^ seed))
		errors |= 1UL << 19;
	if (s->calls != 1)
		errors |= 1UL << 20;
	if (s->seed != seed)
		errors |= 1UL << 21;
	return errors;
}

#endif /* KD_NATIVE_REGISTER_PROBE_H */
