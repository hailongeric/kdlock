/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_REACHED_SESSION_H
#define KD_REACHED_SESSION_H
#include "kd_family.h"
#include "kd_reached.h"

/* Root-owned, preallocated continuation storage. No packet or source stack is
 * copied here. The artifact lives through the service's actual completion ACK. */
struct kd_reached_session {
	struct kd_family family;
	struct kd_family_ref authority;
	struct kd_family_artifact artifact;
	struct kd_reached_state state;
	const struct kd_family_instruction *fetch_instruction;
	unsigned long recent_pc[32];
	unsigned int recent_count;
	unsigned int recent_cursor;
	unsigned long service_target;
	unsigned long service_sp;
	bool initialized;
};
#endif
