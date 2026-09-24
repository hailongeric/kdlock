/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SPIN_CACHELINE_API_H
#define SPIN_CACHELINE_API_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define SC_VERSION 2
#define SC_WORKLOAD_CACHELINE 0
#define SC_WORKLOAD_HASH 1
#define SC_HASH_BUCKETS 1024
#define SC_HASH_ENTRIES 4096
#define SC_HASH_KEY_RANGE (2 * SC_HASH_ENTRIES)
#define SC_LINE_BYTES 64
#define SC_SLOTS 16
#define SC_MAX_ITERATIONS 100000000ULL
#define SC_DEVICE "/dev/spin_cacheline"
#define SC_COMM "sc_worker"
#define SC_TIMED_BATCH 256U
#define SC_TIMED_MAX_WORKERS 64U
#define SC_TIMED_MAX_DURATION_NS 10000000000ULL

/* Fixed x86-64 ioctl ABI; no kdlock dependency or per-operation syscall. */
struct sc_layout {
	__u32 version, line_bytes, slots, lock_bytes;
	__u64 lock_addr, control_addr, data_addr;
	__u64 slot_addr[SC_SLOTS];
	/* resched is now always zero; preserve the v2 layout and old run metadata. */
	__u32 workload, buckets, entries, key_range, resched, reserved;
};

struct sc_run {
	__u32 cachelines, reserved;
	__u64 iterations, completed;
};

struct sc_counts {
	__u64 values[SC_SLOTS];
	__u32 active, reserved;
};

/* Timed runs have one common CLOCK_MONOTONIC deadline. Configuration clears
 * telemetry while quiescent; fixed SC_RUN neither reads nor writes it. */
struct sc_timed_config {
	__u64 started_ns, deadline_ns;
	__u32 workers, reserved;
};

struct sc_timed_run {
	__u32 cachelines, worker;
	__u64 started_ns, deadline_ns, completed, active_started_ns, finished_ns;
};

struct sc_progress {
	__u64 started_ns, deadline_ns, read_started_ns, read_finished_ns;
	__u32 workers, reserved;
	__u64 completed[SC_TIMED_MAX_WORKERS];
};

#define SC_LAYOUT _IOR(0xB7, 0, struct sc_layout)
#define SC_RUN _IOWR(0xB7, 1, struct sc_run)
#define SC_COUNTS _IOR(0xB7, 2, struct sc_counts)
/* Explicit one-time preparation, outside RUN and while workers are drained.
 * Argument is the same cacheline count used for the following RUN. */
#define SC_PREPARE _IOW(0xB7, 3, __u32)
#define SC_TIMED_CONFIG _IOW(0xB7, 4, struct sc_timed_config)
#define SC_RUN_TIMED _IOWR(0xB7, 5, struct sc_timed_run)
/* Live telemetry only: this never reads the target lock or payload counters. */
#define SC_PROGRESS _IOR(0xB7, 6, struct sc_progress)

#endif
