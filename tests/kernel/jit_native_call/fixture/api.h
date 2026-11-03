/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_NATIVE_CALL_TEST_API_H
#define KD_NATIVE_CALL_TEST_API_H
#include <linux/ioctl.h>
#include <linux/types.h>
struct native_call_run {
	__u32 iterations, worker, reserved[2];
	__u64 completed, errors;
};
struct native_call_snapshot {
	__u64 prefix, suffix, taken, lock_address, entry, call_site, native_target;
	__u64 failures, active, hot, idle;
};
#define NATIVE_CALL_RUN _IOWR('N', 1, struct native_call_run)
#define NATIVE_CALL_SNAPSHOT _IOR('N', 2, struct native_call_snapshot)
#define NATIVE_CALL_PREPARE _IO('N', 3)
#define NATIVE_CALL_HOT _IO('N', 4)
#define NATIVE_CALL_COLD _IO('N', 5)
#endif
