/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_PHASE_CONTROLS_API_H
#define KD_PHASE_CONTROLS_API_H
#include "../../../../../workload_modules/mmap_phase_observer/api.h"
struct control_case {
	__u64 mode, task, tid, mm, sem, schedule_calls, first_return;
	__u64 voluntary, involuntary, injected, self_wake, peer_task, peer_wake;
	__u64 peer_done, joined, blocked_before_wake;
	__u64 count[PH_COUNT];
};
struct control_result {
	__u64 abi, checks, errors, idle, scenarios, missed;
	struct control_case cases[3];
};
#define CONTROL_RUN _IOR('c', 1, struct control_result)
#endif
