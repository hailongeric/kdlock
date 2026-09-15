/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_SELECT_H
#define KD_SPIN_SELECT_H

#include "kd_comm.h"
#include "kd_source.h"
#include "kd_spin_entry.h"

/* Provider-private key, initialized before either hook interface is exposed. */
extern struct kd_comm_key kd_spin_target;

static __always_inline bool kd_spin_task_selected(void)
{
	/* Closing stops fresh selection, never an existing owner's unlock route. */
	return (kd_source_is_open() &&
		kd_comm_matches(&kd_spin_target, current->comm)) ||
		kd_spin_entry_task_active();
}

#endif
