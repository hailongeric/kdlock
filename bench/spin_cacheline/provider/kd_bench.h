/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_BENCH_H
#define KD_BENCH_H

#include <linux/percpu.h>
#include <linux/types.h>

/* Load-time observation only. A reader must first drain workers/frames;
 * summing CPU slots is not an atomic snapshot of a running workload. */
extern bool kd_bench_quiet;
extern unsigned long kd_bench_lock_addr;
DECLARE_PER_CPU(u64, kd_bench_bodies);
extern bool kd_bench_complete_probe;
DECLARE_PER_CPU(u64, kd_bench_completions);

static inline void kd_bench_note_body(unsigned long lock_addr)
{
	if (unlikely(kd_bench_lock_addr && lock_addr == kd_bench_lock_addr))
		this_cpu_inc(kd_bench_bodies);
}

/* Only a pristine batch wrapper that reaches its matching outer unlock in
 * that same invocation calls this. Entry witnesses alone also count partial
 * execution followed by native fallback; they cannot prove a full snapshot. */
static inline void kd_bench_note_completion(unsigned long lock_addr)
{
	if (unlikely(kd_bench_complete_probe && kd_bench_lock_addr &&
		     lock_addr == kd_bench_lock_addr))
		this_cpu_inc(kd_bench_completions);
}

#endif
