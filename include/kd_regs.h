/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_REGS_H
#define KD_REGS_H

/* KD-owned x86-64 software packet, layout 2. The continuation triple leads;
 * the JIT's five virtual GPR backing slots follow it. Linux pt_regs is never
 * redefined or cast to this type. Retain every FULL software field and use
 * the same packet through waiter, combiner, native recovery and final ACK.
 * Numeric constants are shared with wrapper assembly; C offsets are checked
 * when the provider builds. An image with layout-1 directory tags is rejected.
 */
#define KD_REG_IP 0
#define KD_REG_SP 8
#define KD_REG_BP 16
#define KD_REG_R15 24
#define KD_REG_R14 32
#define KD_REG_R13 40
#define KD_REG_R12 48
#define KD_REG_R11 56
#define KD_REG_BX 64
#define KD_REG_R10 72
#define KD_REG_R9 80
#define KD_REG_R8 88
#define KD_REG_AX 96
#define KD_REG_CX 104
#define KD_REG_DX 112
#define KD_REG_SI 120
#define KD_REG_DI 128
#define KD_REG_ORIG_AX 136
#define KD_REG_CS 144
#define KD_REG_FLAGS 152
#define KD_REG_SS 160

/* Only validated instruction transactions set the continuation tags below.
 * Ordinary CALL exits clear them. No packet layout or wrapper word is added. */
#define KD_REG_NATIVE_ESCAPE_TAG 0x4b44455343415045UL
/* New image contract only: a completed original-task instruction supplies
 * arithmetic flags and remaining block budget in ss for this one reentry. */
/* These two constants also appear directly in generated GAS expressions. */
#define KD_REG_ORIGIN_REENTRY_TAG 0x4b444f524947494e
/* The instruction already executed; restore after it, with arithmetic flags. */
#define KD_REG_ORIGIN_SUFFIX_TAG 0x4b444f5253554646UL
#define KD_REG_ADDRESS_GUARD_TAG 0x4b44414700000000UL
#define KD_REG_ADDRESS_GUARD_MASK 0xffffffff00000000UL
#define KD_REG_ARITHMETIC_FLAGS 0x8d5

#ifndef __ASSEMBLER__
struct kd_regs {
	unsigned long ip;
	unsigned long sp;
	unsigned long bp;
	unsigned long r15;
	unsigned long r14;
	unsigned long r13;
	unsigned long r12;
	unsigned long r11;
	unsigned long bx;
	unsigned long r10;
	unsigned long r9;
	unsigned long r8;
	unsigned long ax;
	unsigned long cx;
	unsigned long dx;
	unsigned long si;
	unsigned long di;
	unsigned long orig_ax;
	unsigned long cs;
	unsigned long flags;
	unsigned long ss;
};
_Static_assert(__builtin_offsetof(struct kd_regs, ip) == KD_REG_IP, "KD ip packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, sp) == KD_REG_SP, "KD sp packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, bp) == KD_REG_BP, "KD bp packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r15) == KD_REG_R15, "KD r15 packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r14) == KD_REG_R14, "KD r14 packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r13) == KD_REG_R13, "KD r13 packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r12) == KD_REG_R12, "KD r12 packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r11) == KD_REG_R11, "KD r11 packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, bx) == KD_REG_BX, "KD bx packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r10) == KD_REG_R10, "KD r10 packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r9) == KD_REG_R9, "KD r9 packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r8) == KD_REG_R8, "KD r8 packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, ax) == KD_REG_AX, "KD ax packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, cx) == KD_REG_CX, "KD cx packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, dx) == KD_REG_DX, "KD dx packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, si) == KD_REG_SI, "KD si packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, di) == KD_REG_DI, "KD di packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, orig_ax) == KD_REG_ORIG_AX, "KD orig_ax packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, cs) == KD_REG_CS, "KD cs packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, flags) == KD_REG_FLAGS, "KD flags packet offset");
_Static_assert(__builtin_offsetof(struct kd_regs, ss) == KD_REG_SS, "KD ss packet offset");
_Static_assert(sizeof(struct kd_regs) == 168, "KD full packet size");
#endif
#endif
