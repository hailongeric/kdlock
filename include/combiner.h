// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
#ifndef __COMBINER_H_
#define __COMBINER_H_
/*
 * incoming_rsp_ptr -> rdi
 * outgoing_rsp_ptr -> rsi
 *
 * Assume IRQ is disabled. Will enable when returning.
 */

#include <linux/kernel.h>
#include <linux/percpu.h>

// #define NUMA_AWARE 1
// #define PREFETCHING 1
// #define WWJUMP 1

#define NUM_PREFETCH_LINES 6

#define LOCK_START_TIMING_DISABLE(name, start)
#define LOCK_START_TIMING_PER_CPU_DISABLE(name)
#define LOCK_END_TIMING_DISABLE(name, start)
#define LOCK_END_TIMING_PER_CPU_DISABLE(name)

extern long kd_combiner_batch_size;
extern long kd_mutex_batch_size;

void kd_context_switch(void *incoming_rsp_ptr, void *outgoing_rsp_ptr);

#ifdef KD_SPIN_STATS
DECLARE_PER_CPU_ALIGNED(u64, combiner_count);
DECLARE_PER_CPU_ALIGNED(u64, waiter_combined);
DECLARE_PER_CPU_ALIGNED(u64, ooo_combiner_count);
DECLARE_PER_CPU_ALIGNED(u64, ooo_waiter_combined);
DECLARE_PER_CPU_ALIGNED(u64, ooo_unlocks);
DECLARE_PER_CPU_ALIGNED(u64, lock_not_in_task);
#endif

#endif
