/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RW_BENCH_API_H
#define KD_RW_BENCH_API_H
#include <linux/ioctl.h>
#include <linux/types.h>
#include "../../include/kd_rw_wait_diag.h"

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
/* Independent evidence extension; the original workload ABI is unchanged. */
struct rb_evidence_row { __u64 count[26]; __u64 proof[6][20]; };
struct rb_evidence_snapshot {
	__u64 version, workers, delegation_enabled, proxy_limit;
	struct rb_evidence_row rows[RB_MAX_WORKERS];
};
struct rb_bind { __u64 unlock_ip, unlock_cursor; };
struct rb_recording { __u64 enabled, trace_enabled; };
/* New command for the larger ABI4 snapshot: old buffers must be refused
 * before copying, rather than discovering the version after an oversized copy.
 */
#define RB_EVIDENCE _IO('B', 13)
#define RB_BIND _IOW('B', 8, struct rb_bind)
#define RB_DESTROY _IO('B', 9)
#define RB_RECORDING _IOWR('B', 10, struct rb_recording)
/* Snapshot ABI2 adds the independent node-wait algorithm identity. */
struct rb_wait_diag_mode { __u64 enabled, supported; };
struct rb_wait_diag_snapshot {
	__u64 version, counter_count, enabled, supported, workers, backend, started_ns, complete;
	__u64 node_wait;
	struct kd_rw_wait_diag_counts rows[RB_MAX_WORKERS];
};
#define RB_WAIT_DIAG_MODE _IOWR('B', 14, struct rb_wait_diag_mode)
/* Do not copy the larger snapshot into an ABI1 command-15 buffer. */
#define RB_WAIT_DIAG_SNAPSHOT _IO('B', 16)
#endif
