/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_PROXY_TEST_API_H
#define KD_RWSEM_PROXY_TEST_API_H
#include <linux/ioctl.h>
#include <linux/types.h>

enum proxy_role { PROXY_HOLDER, PROXY_EXECUTOR, PROXY_WRITER, PROXY_READER,
		  PROXY_PREDECESSOR, PROXY_ROLES };
struct proxy_run { __u32 role, iterations; __u64 returned, errors; };
struct proxy_snapshot {
	__u64 sem, gate, entry, active, errors, started, ready, done;
	__u64 armed, predecessor_release, predecessor_done, holder_release;
	__u64 reader_held, reader_release, prefix, tail_done, own_bodies, warm_ops;
	__u64 warm_eligible, entry_checked, entry_eligible;
	__u64 g_task, c_task, w_task, t_task;
	__u64 owner, gate_state, tail, waiters, readers, admission;
	__u64 generation, write_generation, own_generation;
};
#define PROXY_RUN _IOWR('R', 1, struct proxy_run)
#define PROXY_SNAPSHOT _IOR('R', 2, struct proxy_snapshot)
#define PROXY_PREPARE _IO('R', 3)
#define PROXY_PREDECESSOR_RELEASE _IO('R', 4)
#define PROXY_HOLDER_RELEASE _IO('R', 5)
#define PROXY_READER_RELEASE _IO('R', 6)
#define PROXY_WARMUP _IOWR('R', 7, struct proxy_run)
#define PROXY_ARM _IO('R', 8)
#define PROXY_DRAIN _IO('R', 9)
#endif
