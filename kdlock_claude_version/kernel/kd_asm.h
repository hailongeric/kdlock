/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Structure offsets shared by kd_entry.S and C. kd_core.c checks every
 * value with static_assert, so a layout change fails the build instead of
 * producing a wrong stub.
 */
#ifndef KD_ASM_H
#define KD_ASM_H

/* struct kd_regs */
#define KD_R_rax		0
#define KD_R_rbx		8
#define KD_R_rcx		16
#define KD_R_rdx		24
#define KD_R_rsi		32
#define KD_R_rdi		40
#define KD_R_rbp		48
#define KD_R_rsp		56
#define KD_R_r8			64
#define KD_R_r9			72
#define KD_R_r10		80
#define KD_R_r11		88
#define KD_R_r12		96
#define KD_R_r13		104
#define KD_R_r14		112
#define KD_R_r15		120
#define KD_R_rip		128
#define KD_R_rflags		136
#define KD_R_SIZE		232

/* struct kd_cpu */
#define KD_CPU_task		0
#define KD_CPU_canary		8
#define KD_CPU_stack_top	16
#define KD_CPU_root		24
#define KD_CPU_cur		32
#define KD_CPU_host_rsp		40
#define KD_CPU_tmp		48
#define KD_CPU_exit_ip		56
#define KD_CPU_resume		64
#define KD_CPU_aux		72
#define KD_CPU_exit_code	80
#define KD_CPU_busy		84
#define KD_CPU_wait_stack	88
#define KD_CPU_regs		96

/* struct kd_mutex */
#define KD_MUTEX_owner		8

/* Values the stubs compare-and-swap into the lock word. */
#define KD_ASM_SPIN_LOCKED	1
#define KD_ASM_RW_WLOCKED	0xff
#define KD_ASM_RWSEM_WLOCKED	1

/* SOFTIRQ_DISABLE_OFFSET + PREEMPT_LOCK_OFFSET, as used by spin_lock_bh(). */
#define KD_ASM_SOFTIRQ_LOCK_OFFSET	0x201

/* KD_X_NESTED and the nested ops of enum kd_op, for the _jit entries. */
#define KD_ASM_X_NESTED		9
#define KD_ASM_OP_NEST_SPIN	10
#define KD_ASM_OP_NEST_WRITE	11

/* Return values of the C wait functions called by the stubs. */
#define KD_WAIT_LOCAL		0	/* lock acquired; caller runs its own section */
#define KD_WAIT_RESUMED		1	/* section was executed elsewhere; resume from packet */
#define KD_WAIT_SLEEP		(-1)	/* left the queue; take the sleeping path */
#define KD_WAIT_SLEEP_HELD	(-2)	/* rwsem: queue mutex held, must sleep for count */

#endif /* KD_ASM_H */
