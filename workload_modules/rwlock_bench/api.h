/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RW_BENCH_API_H
#define KD_RW_BENCH_API_H
#include <linux/ioctl.h>
#include <linux/types.h>

#define RB_VERSION 1
#define RB_MAX_WORKERS 64
#define RB_BATCH 256
#define RB_SLOTS 16
#define RB_WORKLOAD_NANO 6

struct rw_bench_config {
	__u64 started_ns, deadline_ns; /* deadline 0 selects fixed iterations */
	__u32 workers, write_percent;
};
struct rw_bench_run {
	__u64 started_ns, deadline_ns, iterations;
	__u32 worker, reserved;
	__u64 completed, reads, writes, read_errors, read_hits, checksum;
	__u64 active_started_ns, finished_ns;
	__u32 cpu, reserved2;
};
struct rw_bench_snapshot {
	__u64 values[RB_SLOTS];
	__u64 lock_addr, gate_addr, entry;
	__u32 version, backend, workload, lines, post_work_rounds, cnts, gate, active;
};
struct rw_bench_progress {
	__u64 started_ns, deadline_ns, read_started_ns, read_finished_ns;
	__u32 workers, reserved;
	__u64 completed[RB_MAX_WORKERS];
};
#define RB_CONFIG _IOW('B', 1, struct rw_bench_config)
#define RB_RUN _IOWR('B', 2, struct rw_bench_run)
#define RB_SNAPSHOT _IOR('B', 3, struct rw_bench_snapshot)
#define RB_PROGRESS _IOR('B', 4, struct rw_bench_progress)
#define RB_PREPARE _IO('B', 5)
#define RB_DRAIN _IO('B', 6)
#endif
