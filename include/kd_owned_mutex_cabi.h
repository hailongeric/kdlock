/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_OWNED_MUTEX_CABI_H
#define KD_OWNED_MUTEX_CABI_H

/* Late-capture record; allocated only after Linux local acquisition fails and
 * the C SELF gate requests capture. Successful SELF never needs this record.
 * Keep the eight-word contract separate from ABI2's three-word continuation. */
#define KD_CABI_IP 0
#define KD_CABI_SP 8
#define KD_CABI_BP 16
#define KD_CABI_R15 24
#define KD_CABI_R14 32
#define KD_CABI_R13 40
#define KD_CABI_R12 48
#define KD_CABI_BX 56
#define KD_CABI_SIZE 64
/* Explicit TEST RAX,RAX + near JNZ between return PC and continuation label. */
#define KD_CABI_CALL_STUB_SIZE 9

#ifndef __ASSEMBLER__
struct kd_owned_mutex_cabi_state {
	unsigned long ip, sp, bp, r15, r14, r13, r12, bx;
};
_Static_assert(sizeof(struct kd_owned_mutex_cabi_state) == KD_CABI_SIZE,
	       "owned C ABI capture size");
struct kd_mutex;
unsigned long kd_owned_mutex_outer_cabi_gate(struct kd_mutex *, unsigned long);
unsigned long kd_owned_mutex_outer_cabi_capture(struct kd_mutex *,
		const struct kd_owned_mutex_cabi_state *);
void kd_owned_mutex_outer_cabi_unlock_slow(struct kd_mutex *, unsigned long);
void kd_owned_mutex_resume_cabi(const struct kd_owned_mutex_cabi_state *)
	__attribute__((noreturn));
#endif
#endif
