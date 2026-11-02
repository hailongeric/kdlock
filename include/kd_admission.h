/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_ADMISSION_H
#define KD_ADMISSION_H

#include "kd_wait_queue.h"

struct kd_mutex;
struct kd_rwsem;

enum kd_admission_kind {
	KD_ADMISSION_MUTEX,
	KD_ADMISSION_RWSEM_WRITE,
};

enum kd_admission_read_state {
	KD_ADMISSION_READ_NONE,
	KD_ADMISSION_READ_LIVE,
	KD_ADMISSION_READ_CONSUMING,
	KD_ADMISSION_READ_RELEASED,
};

/* One supplied canonical request spans physical admission and reader drainage.
 * The transport retains this record through actual unlock/read-credit ACK.
 * Local C calls transfer their acquired authority to the object's owner/phase
 * record before retiring their stack descriptor. */
struct kd_admission {
	struct kd_wait_request *request;
	struct kd_wait_node member;
	struct kd_wait_node condition;
	struct kd_wait_selection selection;
	struct kd_wait_cleanup cleanup;
	enum kd_admission_kind kind;
	void *object;
	struct kd_mutex *gate;
	struct kd_rwsem *sem;
	struct task_struct *physical_owner;
	struct task_struct *phase_owner;
	void *phase_identity;
	u64 phase_generation;
	u64 request_generation;
	unsigned int phase_kind;
	unsigned int read_state;
	bool gate_held;
	bool pickup_pending;
	bool phase_held;
	bool phase_release_pending;
	bool cleanup_prepared;
	bool scheduling_gate_held;
	bool committed;
	raw_spinlock_t local_guard;
	raw_spinlock_t *retained_guard;
};

void kd_admission_init(struct kd_admission *admission,
		       struct kd_wait_request *request, enum kd_admission_kind kind,
		       void *object, raw_spinlock_t *retained_guard);
void kd_admission_publish_locked(struct kd_admission *admission);
enum kd_wait_decision kd_admission_step_locked(struct kd_admission *admission);
/* Actual acquisition is already committed. Transfer tentative selection and
 * cleanup custody to this retained acquired record before lifecycle rebind.
 * The transport separately proves old-guard actor retirement. */
void kd_admission_transfer_owned_locked(struct kd_admission *admission);
/* These operations run only on the exact actual physical owner. Transfer puts
 * the designated task into PICKUP; its next step consumes that exact request.
 * No caller may replace an unrelated actual owner. */
bool kd_admission_owner_transfer_locked(struct kd_admission *admission,
				       struct task_struct *target);
bool kd_admission_owner_pickup_locked(struct kd_admission *admission);
void kd_admission_select_executor_locked(struct kd_admission *admission,
					struct task_struct *executor);
void kd_admission_owner_release(struct kd_admission *admission);
/* Retire phase metadata and guarded access before physical release. Admission
 * remains closed until the physical ACK and final complete_phase_release.
 * A tentative owner keeps its cleanup token across retained guard handover. */
bool kd_admission_finish_cleanup_locked(struct kd_admission *admission,
				       struct wake_q_head *wake);
/* After unlocking the object guard, open the retired phase as the final object
 * access. A cancellation has first rebound to retained state; its cleanup token
 * is dropped there only after this final release. */
void kd_admission_complete_phase_release(struct kd_admission *admission);
/* Retained metadata only: drop exact cancellation cleanup after physical and
 * phase release ACKs. This does not publish cancellation result/return ACK. */
void kd_admission_complete_cleanup(struct kd_admission *admission);
raw_spinlock_t *kd_admission_terminal_cancel_locked(struct kd_admission *admission);
/* Blocking task-context adapter. The optional callback services retained owner
 * commands, never another body. Remote-origin waits recheck that origin on a
 * timer and cannot consume the executor's own signals as cancellation. */
int kd_admission_wait(struct kd_admission *admission,
		      void (*service)(void *argument), void *argument);
void kd_admission_detach_local_locked(struct kd_admission *admission);
/* Move an already committed native-stack invocation to retained storage with
 * the same immutable UID/generation. No second gate/phase grant is attempted. */
void kd_admission_move_owned_locked(struct kd_admission *source,
				    struct kd_admission *destination);
/* Acquired owner operations do not publish request completion. The runtime
 * retains its packet/source through the later returned-body acknowledgment. */
void kd_admission_release(struct kd_admission *admission);
void kd_admission_downgrade(struct kd_admission *admission);
void kd_admission_finish_read(struct kd_admission *admission);

#endif /* KD_ADMISSION_H */
