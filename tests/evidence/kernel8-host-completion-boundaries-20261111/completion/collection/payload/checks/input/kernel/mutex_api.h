/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_MUTEX_API_CONTROL_H
#define KDLOCK_MUTEX_API_CONTROL_H

#include "episode.h"
#include "../include/kd_spin_api.h"
#include "../include/kd_rwsem_api.h"
#include "../include/kd_rwlock_api.h"

/* Current-task setup only, before first source admission. Caller owns immutable
 * resources/configuration, explicit request and complete control-stack bounds,
 * object/source/ABI lifetimes and scheduler/IRQ/unwinder compatibility. Binding
 * selects no numeric capacity and allocates nothing. Rebinding requires full
 * detach/drain, not an idle cursor. Other physical executors use explicit frames
 * and node->state, never this task's own native-entry configuration.
 */
int kd_mutex_bind_current(struct kd_episode_resources *resources,
			 unsigned long required_control_bytes);
/* Pure exact classifier for this declared ordinary pair. Additional API lanes
 * need their own exact registered target/context contract, never name matching.
 */
enum kd_operation_kind kd_mutex_resolve_entry_operation(void *context,
						unsigned long target);

enum kd_operation_kind kd_spin_resolve_entry_operation(unsigned long target);
enum kd_operation_kind kd_rw_resolve_entry_operation(unsigned long target);

/* Assembly-only native bootstrap endpoints; ordinary callers use the macros.
 * NULL means the native operation completed through its exact acquisition;
 * generic Linux aliases can also complete a native-pool acquisition this way.
 * A descriptor means auxiliary entry is prepared before source capture/lending.
 * Ordinary acquisition uses the common persistent MCS request protocol.
 * Invalid native context/ownership is outside this API.
 */
struct kd_mutex_entry *kd_mutex_prepare_lock_current(struct kd_mutex *lock);
struct kd_mutex_entry *kd_mutex_prepare_unlock_current(struct kd_mutex *lock);
struct kd_mutex_entry *kd_spin_prepare_lock_current(struct kd_spinlock *lock);
struct kd_mutex_entry *kd_spin_prepare_unlock_current(struct kd_spinlock *lock);

/* Generic Linux source aliases keep the same KD object argument and source
 * inputs. Only their original-task bootstrap chooses managed or native entry.
 */
void kd_linux_rwsem_down_read_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_linux_rwsem_up_read_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_linux_rwsem_down_write_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_linux_rwsem_up_write_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_linux_rwsem_downgrade_write_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
int kd_linux_rwsem_down_write_killable_entry_asm(struct kd_rwsem *lock,
		unsigned long source_sp, unsigned long continuation_ip,
		unsigned long source_bp);
struct kd_mutex_entry *kd_linux_rwsem_prepare_down_read_current(struct kd_rwsem *lock);
struct kd_mutex_entry *kd_linux_rwsem_prepare_up_read_current(struct kd_rwsem *lock);
struct kd_mutex_entry *kd_linux_rwsem_prepare_down_write_current(struct kd_rwsem *lock);
struct kd_mutex_entry *kd_linux_rwsem_prepare_up_write_current(struct kd_rwsem *lock);
struct kd_mutex_entry *kd_linux_rwsem_prepare_downgrade_write_current(struct kd_rwsem *lock);
struct kd_source_prepare_result kd_linux_rwsem_prepare_down_write_killable_current(
		struct kd_rwsem *lock);
/* Query source entries retain the integer clobber contract; original-task
 * preparation always completes the physical predicate locally.
 */
int kd_linux_rwsem_is_locked_entry_asm(struct kd_rwsem *lock,
		unsigned long source_sp, unsigned long continuation_ip, unsigned long source_bp);
int kd_linux_rwsem_is_write_locked_entry_asm(struct kd_rwsem *lock,
		unsigned long source_sp, unsigned long continuation_ip, unsigned long source_bp);
struct kd_source_prepare_result kd_linux_rwsem_prepare_is_locked_current(struct kd_rwsem *lock);
struct kd_source_prepare_result kd_linux_rwsem_prepare_is_write_locked_current(struct kd_rwsem *lock);

/* Read-only borrowed-source eligibility for the five generic Linux aliases.
 * Nonaliases leave private routes unchanged. The caller retains source/root and
 * exact grant backing, and revalidates its current JIT binding before advancing.
 */
bool kd_linux_rwsem_source_operation_ready(struct kd_thread_state *state,
		struct kd_execution_binding *binding, unsigned long target);

/* Internal bridge after exact original-task eligibility/grant selection. The
 * actual typed entry is retained through capture, rather than inferred by kind.
 */
struct kd_mutex_entry *kd_rwsem_prepare_source_current(struct kd_rwsem *lock,
		enum kd_operation_kind operation, unsigned long api_target);

struct kd_mutex_entry *kd_rwsem_prepare_down_read_current(struct kd_rwsem *lock);
struct kd_mutex_entry *kd_rwsem_prepare_up_read_current(struct kd_rwsem *lock);
struct kd_mutex_entry *kd_rwsem_prepare_down_write_current(struct kd_rwsem *lock);
struct kd_source_prepare_result kd_rwsem_prepare_down_write_killable_current(
		struct kd_rwsem *lock);
struct kd_mutex_entry *kd_rwsem_prepare_up_write_current(struct kd_rwsem *lock);
struct kd_mutex_entry *kd_rwsem_prepare_downgrade_write_current(struct kd_rwsem *lock);
struct kd_mutex_entry *kd_rwlock_prepare_read_lock_current(struct kd_rwlock *lock);
struct kd_mutex_entry *kd_rwlock_prepare_read_unlock_current(struct kd_rwlock *lock);
struct kd_mutex_entry *kd_rwlock_prepare_write_lock_current(struct kd_rwlock *lock);
struct kd_mutex_entry *kd_rwlock_prepare_write_unlock_current(struct kd_rwlock *lock);

#endif
