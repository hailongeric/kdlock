/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_LINUX_RWSEM_H
#define KDLOCK_LINUX_RWSEM_H

#include <linux/types.h>

struct rw_semaphore;
struct kd_rwsem;
struct task_struct;

/* Source-rebuilt object binding, immutable while the object is reachable.
 * Selection changes only under caller-proved exclusion of ALL native/KD entry,
 * waiters, grants, observers and final object accesses. An unlocked count alone
 * is insufficient. Lock, native pool, records and this binding are cold caller
 * storage; explicit availability covers every live or still-queued record.
 */
struct kd_linux_rwsem_binding {
	struct rw_semaphore *object;
	struct kd_rwsem *lock;
	bool source_calls;
	/* Separate cold opt-in; legacy bindings keep killable calls native. */
	bool killable_source_calls;
};

int kd_linux_rwsem_bind(struct rw_semaphore *object,
		struct kd_linux_rwsem_binding *binding, struct kd_rwsem *lock,
		bool source_calls);
/* Experimental source lane: ordinary pairs plus original-task killable writer
 * capture. Caller supplies the same immutable binding/native-pool contracts and
 * complete managed task/source resources. Selection has no support evidence.
 */
int kd_linux_rwsem_bind_killable_source(struct rw_semaphore *object,
		struct kd_linux_rwsem_binding *binding, struct kd_rwsem *lock);
int kd_linux_rwsem_unbind(struct kd_linux_rwsem_binding *binding);

/* Normal callable C ABI. Signal/try operations remain local on the KD gate;
 * every such target is a permanent pre-operation generated-code frontier.
 * Invalid ownership/provisioning is outside the supported API contract.
 */
void kd_linux_rwsem_down_read(struct kd_linux_rwsem_binding *binding);
int kd_linux_rwsem_down_read_interruptible(struct kd_linux_rwsem_binding *binding);
int kd_linux_rwsem_down_read_killable(struct kd_linux_rwsem_binding *binding);
int kd_linux_rwsem_down_read_trylock(struct kd_linux_rwsem_binding *binding);
void kd_linux_rwsem_down_write(struct kd_linux_rwsem_binding *binding);
int kd_linux_rwsem_down_write_killable(struct kd_linux_rwsem_binding *binding);
int kd_linux_rwsem_down_write_trylock(struct kd_linux_rwsem_binding *binding);
void kd_linux_rwsem_up_read(struct kd_linux_rwsem_binding *binding);
void kd_linux_rwsem_up_write(struct kd_linux_rwsem_binding *binding);
void kd_linux_rwsem_downgrade_write(struct kd_linux_rwsem_binding *binding);
void kd_linux_rwsem_down_read_non_owner(struct kd_linux_rwsem_binding *binding);
void kd_linux_rwsem_up_read_non_owner(struct kd_linux_rwsem_binding *binding);

bool kd_linux_rwsem_is_locked(const struct kd_linux_rwsem_binding *binding);
bool kd_linux_rwsem_is_write_locked(const struct kd_linux_rwsem_binding *binding);
bool kd_linux_rwsem_is_contended(const struct kd_linux_rwsem_binding *binding);
bool kd_linux_rwsem_is_reader_owned(const struct kd_linux_rwsem_binding *binding);
struct task_struct *kd_linux_rwsem_owner(const struct kd_linux_rwsem_binding *binding);

/* Original-task entry selection only. Active borrowed operations continue to
 * use their node's direct S_W, never a second per-task active-state pointer.
 * Helpers themselves require original-task execution before inspecting its own
 * native state; source metadata therefore keeps them permanent frontiers.
 */
bool kd_linux_rwsem_source_ready(const struct kd_linux_rwsem_binding *binding);
bool kd_linux_rwsem_source_release(const struct kd_linux_rwsem_binding *binding,
		bool read);
const unsigned long *kd_linux_rwsem_native_targets(unsigned int *count);
bool kd_linux_rwsem_is_native_target(unsigned long target);
#endif
