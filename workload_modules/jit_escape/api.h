/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_JIT_ESCAPE_TEST_API_H
#define KD_JIT_ESCAPE_TEST_API_H

#include <linux/ioctl.h>
#include <linux/types.h>

struct jit_escape_run {
	__u32 iterations;
	__u32 worker;
	__u32 reserved[2];
	__u64 completed;
	__u64 errors;
};

struct jit_escape_snapshot {
	__u64 prefix;
	__u64 suffix;
	__u64 hot_taken;
	__u64 lock_address;
	__u64 entry;
	__u64 marker;
	__u64 failures;
	__u64 active;
	__u64 hot;
	__u64 idle;
};

#define JIT_ESCAPE_RUN _IOWR('E', 1, struct jit_escape_run)
#define JIT_ESCAPE_SNAPSHOT _IOR('E', 2, struct jit_escape_snapshot)
#define JIT_ESCAPE_PREPARE _IO('E', 3)
#define JIT_ESCAPE_HOT _IO('E', 4)
#endif
