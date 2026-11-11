/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_TASK_PROGRESS_H
#define KDLOCK_TASK_PROGRESS_H

#include <linux/types.h>

struct kd_task_root_context;
struct kd_execution_binding;

/*
 * One private native progress pass on the attached current task/root. Caller
 * retains root, the exact expected_native endpoint and all backing through the
 * final API access, including bound episode resources. Episode frame cleanup
 * follows its exact result-notification ownership contract; a native binding
 * address alone cannot prove old exported actors have finished. Current must
 * already own that NATIVE binding, outside any
 * auxiliary/borrowed control, in ordinary sleepable TASK_RUNNING context.
 * Operation must be IDLE/RESUMABLE with no pending image-exit triple.
 *
 * Pump actual physical-owner controls, collect logically closed physically
 * complete core grants (including episode-owned image/slot actors when bound),
 * pump owners again after their source users drop, then
 * collect fully ended request-pool slots. No source instruction runs; no source
 * register/cursor is read, copied or restored, and no binding is mutated.
 * There is no allocation, pending/drain loop or wait for an open source grant
 * or borrowed work. Inherited physical MCS release may poll/yield for a producer
 * already between tail exchange and its final predecessor-link store; this is
 * not a wait-free operation or an IRQ/atomic route.
 *
 * On success, pending reports exact remaining owner/grant/pool list
 * membership observed by this pass. It is metadata remaining, not a physical
 * blocker or permission to wait: the current native endpoint legitimately keeps
 * a finished pool slot occupied until atomic detach revokes that endpoint.
 * pending == false is not a complete last-user, task-exit or reclamation proof.
 * Close new admission and independently drain every escaped API/control/image/
 * return/notifier/auxiliary/binding observer before detach. A later retry may
 * collect asynchronous retirement; never self-wait for pending to become false.
 * Errors may follow partial metadata progress; pending remains true and confers
 * no conclusion. No source replay or alternative physical owner is introduced.
 */
int kd_task_progress_native(struct kd_task_root_context *root,
			    struct kd_execution_binding *expected_native,
			    bool *pending);

#endif
