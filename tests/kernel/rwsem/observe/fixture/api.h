/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_OBSERVE_API_H
#define KD_RWSEM_OBSERVE_API_H
#include <linux/ioctl.h>
#include <linux/types.h>

#define KD_RWSEM_OBSERVE_ABI 1
#define KD_RWSEM_OBSERVE_APIS 11
#define KD_RWSEM_OBSERVE_TIDS 64
#define KD_RWSEM_OBSERVE_NAME 128

enum kd_rwsem_observe_event_kind {
	KD_RWSEM_ACQUIRE_INVOKE = 1,
	KD_RWSEM_ACQUIRE_SUCCESS,
	KD_RWSEM_ACQUIRE_FAILURE,
	KD_RWSEM_DOWNGRADE_INVOKE,
	KD_RWSEM_DOWNGRADE_RETURN,
	KD_RWSEM_RELEASE_INVOKE,
	KD_RWSEM_RELEASE_RETURN,
};
enum kd_rwsem_observe_category {
	KD_RWSEM_WRITE = 1, KD_RWSEM_READ, KD_RWSEM_DOWNGRADE,
	KD_RWSEM_WRITE_RELEASE, KD_RWSEM_READ_RELEASE,
};
enum kd_rwsem_observe_return {
	KD_RWSEM_VOID = 1, KD_RWSEM_ZERO_SUCCESS, KD_RWSEM_NONZERO_SUCCESS,
};
struct kd_rwsem_observe_arm {
	__u64 abi, duration_ms, nr_tids, reserved;
	__u32 tids[KD_RWSEM_OBSERVE_TIDS];
};
struct kd_rwsem_observe_header {
	__u64 abi, header_bytes, event_bytes, symbol_bytes, symbol_count;
	__u64 capacity, reserved, count, overflow, missed, inflight, errors;
	__u64 armed, stopped, start_ns, stop_ns, proxy_proof, duration_ms, cutoff_ns;
};
struct kd_rwsem_observe_symbol {
	__u32 api, category, return_kind, registered;
	char name[KD_RWSEM_OBSERVE_NAME];
};
struct kd_rwsem_observe_event {
	__u64 sequence, time_ns, lock, pairing_id, task_start_boottime_ns;
	__s64 result;
	__u32 tid, tgid, cpu, event, api, reserved;
};
#define KD_RWSEM_OBSERVE_ARM _IOW('R', 0x71, struct kd_rwsem_observe_arm)
#define KD_RWSEM_OBSERVE_STOP _IO('R', 0x72)
#define KD_RWSEM_OBSERVE_HEADER _IOR('R', 0x73, struct kd_rwsem_observe_header)
#endif
