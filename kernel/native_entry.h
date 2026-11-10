/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_NATIVE_ENTRY_H
#define KDLOCK_NATIVE_ENTRY_H

#include "../include/kd_mutex.h"
#include "task_state.h"

/*
 * Prepare the no-failure compiler-clobber prefix before invoking it. This is a
 * private admission API, not a void mutex_lock failure result. The caller has
 * already reserved node/driver/endpoint/code/object and forward-route users,
 * and proved the complete callback's control-stack/depth requirement. A numeric
 * range check is not a scheduler/IRQ/unwinder or recursive-capacity proof.
 *
 * entry and all escaped control stay outside both stacks and survive their last
 * users. A failed preparation publishes no source or auxiliary reservation.
 * Ordinary native fallback must itself be reserved; this API supplies none.
 */
int kd_mutex_prepare_entry(struct kd_mutex_entry *entry,
		 struct kd_execution_binding *native_binding,
		 kd_mutex_entry_run_fn run, void *context,
		 unsigned long required_control_bytes);
/* Cancel only PREPARED control. Assembly marks ENTERED before the stack switch. */
int kd_mutex_cancel_entry(struct kd_mutex_entry *entry,
		 struct kd_execution_binding *native_binding);
/*
 * Final original-W route after the callback transferred to its fresh native
 * endpoint. Drop the exact auxiliary occupancy and immediately resume current
 * canonical IP/SP. Persistent descriptor/node/binding/code users remain held;
 * freeing them is separate from making the auxiliary stack reusable.
 */
void __noreturn kd_mutex_resume_entry(struct kd_mutex_entry *entry,
		 struct kd_execution_binding *native_binding);

#endif
