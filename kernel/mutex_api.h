/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_MUTEX_API_CONTROL_H
#define KDLOCK_MUTEX_API_CONTROL_H

#include "episode.h"
#include "../include/kd_mutex_api.h"

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

/* Assembly-only native bootstrap endpoints; ordinary callers use the macros.
 * NULL means a native unlock completed through its exact retained acquisition.
 * A descriptor means auxiliary entry is prepared before source capture/lending.
 * Ordinary acquisition uses the common persistent MCS request protocol.
 * Invalid native context/ownership is outside this API.
 */
struct kd_mutex_entry *kd_mutex_prepare_lock_current(struct kd_mutex *lock);
struct kd_mutex_entry *kd_mutex_prepare_unlock_current(struct kd_mutex *lock);

#endif
