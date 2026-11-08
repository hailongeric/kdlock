/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_LEARNING_API_H
#define KD_LEARNING_API_H

#include <linux/ioctl.h>
#include <linux/types.h>

/* Separate control ABI: registry rows, upload packets and image protocols keep
 * their existing layouts. One writable open description owns one frozen view. */
#define KD_LEARNING_API_VERSION 1U
#define KD_LEARNING_CAPACITY 32U
#define KD_LEARNING_SNAPSHOT_HEADER_SIZE 128U
#define KD_LEARNING_RECORD_SIZE 40U
#define KD_LEARNING_SNAPSHOT_SIZE 1408U
#define KD_LEARNING_BIND_SIZE 96U
#define KD_LEARNING_CANCEL_SIZE 64U
#define KD_LEARNING_SLOT_LOOKUP ((__u32)~0U)
#define KD_LEARNING_CALL 1U
#define KD_LEARNING_IJ 2U
#define KD_LEARNING_OVERFLOW (1U << 0)

struct kd_learning_root {
	__u32 slot;
	__s32 pid;
	__u64 rip;
	__u32 lock_kind;
	__u32 entry_abi;
};

/* CALL keys use target and from=0. IJ keys use the source dispatch next-PC and
 * target. Sequence and admitted_generation retain the original observation;
 * successful replacement does not renumber records carried into a later view. */
struct kd_learning_record {
	__u64 sequence;
	__u64 admitted_generation;
	__u64 target;
	__u64 from;
	__u32 kind;
	__u32 reserved;
};

struct kd_learning_snapshot {
	__u32 version;
	__u32 header_size;
	__u32 record_size;
	__u32 capacity;
	struct kd_learning_root root;
	__u64 base_generation;
	__u64 revision;
	__u64 token;
	__u64 overflow_report_events;
	__u32 count;
	__u32 flags;
	__u64 reserved[6];
	struct kd_learning_record records[KD_LEARNING_CAPACITY];
};

struct kd_learning_bind {
	__u32 version;
	__u32 size;
	__u64 token;
	struct kd_learning_root root;
	__u64 base_generation;
	__u64 revision;
	__u64 upload_id;
	__u64 reserved[4];
};

struct kd_learning_cancel {
	__u32 version;
	__u32 size;
	__u64 token;
	struct kd_learning_root root;
	__u64 base_generation;
	__u64 reserved[2];
};

/* SNAPSHOT starts with token=0, the exact registry root/base generation and
 * slot=LOOKUP (or its known exact slot). Repeating its returned token/root/
 * generation/revision returns identical bytes until successful publication or
 * CANCEL. A failed initial copy creates no bindable view. All controls require
 * the same writable open description; dup/fork share that description.
 *
 * BIND associates that view with one nonzero upload_id before its first chunk.
 * CANCEL releases only this description's view/binding and any associated
 * private staged upload; it never acknowledges or removes learning records. */
#define KD_LEARNING_SNAPSHOT _IOWR('K', 0x74, struct kd_learning_snapshot)
#define KD_LEARNING_BIND _IOW('K', 0x75, struct kd_learning_bind)
#define KD_LEARNING_CANCEL _IOW('K', 0x76, struct kd_learning_cancel)

#endif
