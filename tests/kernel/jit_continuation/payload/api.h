/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_JIT_CONTINUATION_TEST_API_H
#define KD_JIT_CONTINUATION_TEST_API_H

#include <linux/ioctl.h>
#include <linux/types.h>

struct jit_continuation_run {
	__u32 iterations;
	__u32 worker;
	__u32 reserved[2];
	__u64 completed;
	__u64 errors;
};

struct jit_continuation_snapshot {
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

struct jit_origin_snapshot {
	__u64 effects[4];
	__u64 instructions[4];
};

#define JIT_CONTINUATION_RUN _IOWR('E', 1, struct jit_continuation_run)
#define JIT_CONTINUATION_SNAPSHOT _IOR('E', 2, struct jit_continuation_snapshot)
#define JIT_CONTINUATION_PREPARE _IO('E', 3)
#define JIT_CONTINUATION_HOT _IO('E', 4)
/* Rwlock/rwsem shared-reader control; the command layouts stay fixed. */
#define JIT_CONTINUATION_READ _IOWR('E', 5, struct jit_continuation_run)
/* Change only the next idle phase; existing RUN/SNAPSHOT layouts stay fixed. */
#define JIT_CONTINUATION_COLD _IO('E', 6)
#define JIT_CONTINUATION_ORIGIN_SNAPSHOT _IOR('E', 7, struct jit_origin_snapshot)
#endif
