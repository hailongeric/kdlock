/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_MMAP_API_ABI_H
#define KDLOCK_MMAP_API_ABI_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define KD_MMAP_API_ABI 1ULL
/* Caller excludes ALL mm-lock entries, waiters, grants, callbacks and observers
 * across a backend selection change. Thread/count/idle checks do not prove it.
 * Later MM calls after the completed unbind use the original native backend.
 */
#define KD_MMAP_API_QUIESCENT_CHANGE 1ULL

enum kd_mmap_api_selection_state {
	KD_MMAP_API_IDLE = 0,
	KD_MMAP_API_SELECTED = 1,
	KD_MMAP_API_RETIRED = 2,
};

struct kd_mmap_api_status {
	__u64 state, cleanup_required, native_capacity, record_bytes;
	__u64 owner_pid, owner_tgid, owner_is_current, owner_threads;
	__u64 mm_identity, object_identity, gate_identity;
	__u64 source_calls, pool_idle, gate_locked, gate_write_locked, gate_contended;
	__u64 native_read_acquires, native_read_releases;
	__u64 native_write_acquires, native_write_releases, native_downgrades;
	__u64 native_cancels, native_try_misses, queue_enqueues, local_selections;
	__u64 physical_begins, physical_ends, jit_entries, jit_observation_available;
	__u64 observed_events, count_overflow;
};

/* Fixed-width metadata only, with no embedded user pointer. START requires a
 * positive explicit native_capacity and QUIESCENT_CHANGE. END requires capacity0
 * and the same contract flag, on the exact original owner/mm after workers join.
 * QUERY uses capacity0/flags0. reserved is always0. No ioctl performs MM work.
 *
 * START/END can finish before a failed output copy. QUERY reconciles actual
 * selection metadata; callers never assume an ioctl error undid an operation.
 * Closing a selected fd leaves cleanup_required and the binding/module hold.
 */
struct kd_mmap_api_request {
	__u64 abi, native_capacity, contract_flags, reserved;
	struct kd_mmap_api_status status;
};

#define KD_MMAP_API_START _IOWR('M', 0x40, struct kd_mmap_api_request)
#define KD_MMAP_API_QUERY _IOWR('M', 0x41, struct kd_mmap_api_request)
#define KD_MMAP_API_END   _IOWR('M', 0x42, struct kd_mmap_api_request)

#endif
