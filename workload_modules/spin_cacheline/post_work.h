/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SPIN_CACHELINE_POST_WORK_H
#define SPIN_CACHELINE_POST_WORK_H

/* Keep the amount identical across every backend in a comparison. */
#define SC_POST_WORK_ROUNDS 64

/* Dependent multiply/add rounds after sc_body_N has unlocked and returned.
 * This x86-64 register-only work separates consecutive acquisitions;
 * it neither yields the CPU nor guarantees a handoff. All arms execute it.
 * Volatile asm keeps even an unused final result, without a shared-memory sink,
 * clock read, pause instruction or extra function call. Arithmetic wraps at 64
 * bits; the state belongs to one ioctl and is carried between its iterations.
 */
static __attribute__((always_inline)) inline __u64 sc_post_work(__u64 state)
{
#define SC_POST_ROUND "imulq $1664525, %0, %0\n\taddq $1013904223, %0\n\t"
#define SC_POST_STRINGIFY_INNER(value) #value
#define SC_POST_STRINGIFY(value) SC_POST_STRINGIFY_INNER(value)
	__asm__ __volatile__(".rept " SC_POST_STRINGIFY(SC_POST_WORK_ROUNDS) "\n\t"
			     SC_POST_ROUND ".endr\n\t"
			     : "+r" (state) : : "cc");
#undef SC_POST_STRINGIFY
#undef SC_POST_STRINGIFY_INNER
#undef SC_POST_ROUND
	return state;
}

#endif
