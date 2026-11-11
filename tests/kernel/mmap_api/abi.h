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

/* ABI2 is an independent opt-in profile. ABI1 layouts and commands above are
 * unchanged. START_JIT performs metadata/setup only: the original owner enters
 * the managed runtime before pthread creation, then ordinary userspace syscalls
 * supply all MM activity. No ioctl executes an MM body.
 *
 * Every source region belongs to built-in text or this provider. Caller proves
 * complete immutable text, actual GS identity, auxiliary/context bounds, finite
 * capacity availability, and same-mm-only activity without exec, process fork,
 * foreign mm users or asynchronous lock users. Flags declare these contracts;
 * neither hashes, mmgrab nor a thread count establish them. All unsupported
 * hardware/current/per-CPU/RCU/fixup paths retain their native frontiers. This
 * initial profile can establish a reached prefix, not meaningful MM-body JIT.
 */
#define KD_MMAP_JIT_ABI 2ULL
#define KD_MMAP_JIT_IMMUTABLE_TEXT (1ULL << 1)
#define KD_MMAP_JIT_GS_IDENTITY (1ULL << 2)
#define KD_MMAP_JIT_AUXILIARY_CONTEXT (1ULL << 3)
#define KD_MMAP_JIT_SAME_MM (1ULL << 4)
#define KD_MMAP_JIT_NO_EXEC_PROCESS_FORK (1ULL << 5)
#define KD_MMAP_JIT_NO_FOREIGN_MM_USERS (1ULL << 6)
#define KD_MMAP_JIT_CAPACITY_AVAILABLE (1ULL << 7)
/* A killable combiner drains an already running borrower before EINTR. The
 * dependency R holding READ until C-EINTR while C serves W waiting for R is
 * excluded. Initial killable source capture is original/root-only; nested
 * killable operations hand back before the operation to the original task.
 */
#define KD_MMAP_JIT_DELAYED_CANCEL (1ULL << 8)
#define KD_MMAP_JIT_CONTRACTS (KD_MMAP_API_QUIESCENT_CHANGE | \
	KD_MMAP_JIT_IMMUTABLE_TEXT | KD_MMAP_JIT_GS_IDENTITY | \
	KD_MMAP_JIT_AUXILIARY_CONTEXT | KD_MMAP_JIT_SAME_MM | \
	KD_MMAP_JIT_NO_EXEC_PROCESS_FORK | KD_MMAP_JIT_NO_FOREIGN_MM_USERS | \
	KD_MMAP_JIT_CAPACITY_AVAILABLE | KD_MMAP_JIT_DELAYED_CANCEL)

struct kd_mmap_jit_region { __u64 start, length; };
struct kd_mmap_jit_config {
	__u64 native_capacity, event_capacity, metadata_capacity, source_byte_capacity;
 /* The source_regions and source_version fields are userspace addresses, copied only at START.
  * They are never retained as leases or read again during source execution.
  */
	__u64 source_regions, source_region_count, source_version, source_version_bytes;
	__u64 current_task_gs_offset, configuration_identity[4], load_identity[4];
	__u64 feedback_capacity, cycle_capacity, image_capacity, claim_capacity;
	__u64 code_capacity, artifact_capacity, flat_capacity;
	__u64 entry_capacity, source_capacity, observation_capacity;
	__u64 frame_capacity, request_capacity, auxiliary_bytes, required_control_bytes, proxy_limit;
};

enum kd_mmap_jit_state {
	KD_MMAP_JIT_IDLE, KD_MMAP_JIT_SETTING_UP, KD_MMAP_JIT_SELECTED,
	KD_MMAP_JIT_OWNER_LEFT, KD_MMAP_JIT_RETAINED, KD_MMAP_JIT_RETIRED,
};
#define KD_MMAP_JIT_ROLE_NATIVE (1ULL << 0)
#define KD_MMAP_JIT_ROLE_OBSERVER (1ULL << 1)
#define KD_MMAP_JIT_ROLE_SOURCE (1ULL << 2)
#define KD_MMAP_JIT_ROLE_RUNTIME (1ULL << 3)
#define KD_MMAP_JIT_ROLE_OWNER (1ULL << 4)
#define KD_MMAP_JIT_ROLE_BINDING (1ULL << 5)

struct kd_mmap_jit_status {
	struct kd_mmap_api_status native;
	__u64 state, roles, last_error, setup_error, killable_source_calls, source_closing;
	__u64 owner_left, source_identity, runtime_identity, storage_identity, origin_gs;
	__u64 event_capacity, event_count, event_overflow, event_readers;
	__u64 source_regions, source_bytes;
};

/* START uses exact CONTRACTS and positive explicit capacities (source and
 * observation table counts may be zero as permitted by compiled_image).
 * QUERY uses zero config/contracts. LEAVE and END use zero config and
 * QUIESCENT_CHANGE. Every reply reports retained roles even when the operation
 * fails; failed output copies are reconciled by QUERY, never replayed blindly.
 * LEAVE closes original owner source admission and attempts exact storage
 * retirement after worker joins. It keeps the binding/native pool/channel.
 * Host then finishes claims, SHUTDOWN, durable archive/SETTLE/END and channel
 * close. END refuses live observer fds or retained runtime/source users; it
 * never fabricates ACK, settlement, task drain or a source/code lease.
 */
struct kd_mmap_jit_request {
	__u64 abi, contract_flags;
	struct kd_mmap_jit_config config;
	struct kd_mmap_jit_status status;
};
#define KD_MMAP_API_START_JIT _IOWR('M', 0x43, struct kd_mmap_jit_request)
#define KD_MMAP_API_QUERY_JIT _IOWR('M', 0x44, struct kd_mmap_jit_request)
#define KD_MMAP_API_LEAVE_JIT _IOWR('M', 0x45, struct kd_mmap_jit_request)
#define KD_MMAP_API_END_JIT _IOWR('M', 0x46, struct kd_mmap_jit_request)

#endif
