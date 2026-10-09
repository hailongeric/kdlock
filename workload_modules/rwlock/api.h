/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWLOCK_TEST_API_H
#define KD_RWLOCK_TEST_API_H
#include <linux/ioctl.h>
#include <linux/types.h>

struct rw_test_run {
	__u32 iterations;
	/* 0: readers only; 1: writers only; N: one write per N operations. */
	__u32 write_every;
	__u32 worker;
	__u32 reserved;
	__u64 reads;
	__u64 writes;
};

struct rw_test_snapshot {
	__u64 values[8];
	__u64 gate_address;
	__u64 entry;
	__u32 failures;
	__u32 max_readers;
	__u32 active;
	__u32 cnts;
	__u32 gate;
	__u32 reserved;
};

#define RW_TEST_RUN _IOWR('R', 1, struct rw_test_run)
#define RW_TEST_SNAPSHOT _IOR('R', 2, struct rw_test_snapshot)
#define RW_TEST_PREPARE _IO('R', 3)
#endif
