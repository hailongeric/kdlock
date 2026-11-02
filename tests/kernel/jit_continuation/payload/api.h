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

#define JIT_KILLABLE_SLOTS 8
enum jit_killable_operation {
	JIT_KILLABLE_ROOT,
	JIT_KILLABLE_WRITE_HOLDER,
	JIT_KILLABLE_READ_HOLDER,
	JIT_KILLABLE_INNER_HOLDER,
};
#define JIT_KILLABLE_NESTED 1U
#define JIT_KILLABLE_DOWNGRADE 2U
#define JIT_KILLABLE_DEPTH 4U
#define JIT_KILLABLE_EARLY 8U
#define JIT_KILLABLE_REUSE 16U
#define JIT_KILLABLE_TRUE 32U
#define JIT_KILLABLE_HELPER 64U
#define JIT_KILLABLE_HELPER_WAIT 128U
#define JIT_KILLABLE_NATIVE_PAIRS 256U
#define JIT_KILLABLE_NATIVE_EARLY 512U
#define JIT_KILLABLE_RELEASE_WRITE 1ULL
#define JIT_KILLABLE_RELEASE_READ 2ULL
#define JIT_KILLABLE_RELEASE_INNER 4ULL
#define JIT_KILLABLE_RELEASE_TAIL 8ULL
#define JIT_KILLABLE_RELEASE_HELPER 16ULL
struct jit_killable_run {
	__u32 operation, slot, flags, reserved;
	__s64 result;
	__u64 returned;
};
struct jit_killable_slot {
	__u64 pid, prefix, child_prefix;
	__s64 child_result;
	__u64 returned;
	__s64 result;
	__u64 tail_ready, tail_done;
};
struct jit_killable_snapshot {
	__u64 version, lock_address, inner_address, entry, active, holder_mask, release_mask;
	__s64 phase;
	__u64 readers, queue_count, inner_queue_count, errors, idle;
	__u64 queue_pid[JIT_KILLABLE_SLOTS], queue_state[JIT_KILLABLE_SLOTS];
	__u64 inner_queue_pid[JIT_KILLABLE_SLOTS], inner_queue_state[JIT_KILLABLE_SLOTS];
	struct jit_killable_slot slots[JIT_KILLABLE_SLOTS];
};
#define JIT_KILLABLE_RUN _IOWR('E', 8, struct jit_killable_run)
#define JIT_KILLABLE_SNAPSHOT _IOR('E', 9, struct jit_killable_snapshot)
#define JIT_KILLABLE_RELEASE _IOW('E', 10, __u64)
#define JIT_KILLABLE_RESET _IO('E', 11)

struct jit_helper_slot {
	__u64 origin_stack, calls, pid, stack_address, stack_low, stack_high;
	__u64 preempt_before, irqs_before, arguments[6], result, body_result, body_after;
	__u64 sleep_calls, jiffies_delta, switches_delta;
	__u64 child_acquired, child_released, signal_seen;
};
struct jit_helper_snapshot {
	__u64 version, registered, errors;
	struct jit_helper_slot slots[JIT_KILLABLE_SLOTS];
};
#define JIT_HELPER_SNAPSHOT _IOR('E', 12, struct jit_helper_snapshot)
#define JIT_HELPER_UNREGISTER _IO('E', 13)

#define JIT_NATIVE_EVENTS 24
enum jit_native_operation {
	JIT_NATIVE_SPIN_LOCK = 1,
	JIT_NATIVE_SPIN_TRY,
	JIT_NATIVE_SPIN_UNLOCK,
	JIT_NATIVE_RCU_LOCK,
	JIT_NATIVE_RCU_UNLOCK,
};
struct jit_native_event {
	__u64 operation, pid, stack_address;
	__u64 preempt_before, preempt_after, rcu_before, rcu_after;
	__u64 irqs_before, irqs_after, result;
};
struct jit_native_snapshot {
	__u64 version, count, errors, lock_address, body_after, stack_low, stack_high;
	struct jit_native_event events[JIT_NATIVE_EVENTS];
};
#define JIT_NATIVE_SNAPSHOT _IOR('E', 14, struct jit_native_snapshot)
#endif
