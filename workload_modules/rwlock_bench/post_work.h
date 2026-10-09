/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RW_BENCH_POST_WORK_H
#define KD_RW_BENCH_POST_WORK_H

#if RB_POST_WORK_ROUNDS < 1 || RB_POST_WORK_ROUNDS > 256
#error "RB_POST_WORK_ROUNDS must be 1..256"
#endif
/* Same dependent multiply/add work as the earlier KD cacheline benchmarks.
 * Compile the selected count so every backend has identical work outside
 * its lock. Volatile asm retains it without shared-memory writes or yielding. */
static __always_inline u64 rb_post_work(u64 state)
{
#define RB_STRING_INNER(value) #value
#define RB_STRING(value) RB_STRING_INNER(value)
	asm volatile(".rept " RB_STRING(RB_POST_WORK_ROUNDS) "\n\t"
		     "imulq $1664525, %0, %0\n\taddq $1013904223, %0\n\t.endr\n\t"
		     : "+r" (state) : : "cc");
#undef RB_STRING
#undef RB_STRING_INNER
	return state;
}
#endif
