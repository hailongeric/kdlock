/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_MUTEX_LOCAL_H
#define KDLOCK_MUTEX_LOCAL_H

#include "mutex.h"

struct kd_task_root_context;

/*
 * Native-only fallback within the SAME MCS queue as persistent requests. Caller
 * retains an attached current task root and has already validated its exact
 * native source binding before these calls; no source has been lent/exported.
 * The local functions inspect no canonical packet and capture no source GPRs.
 * Ordinary sleepable task context only, with valid source-stack temporary waiter
 * storage. They allocate nothing, select no capacity/default and do not execute
 * a proxy body. Errors describe private preconditions, never public lock results.
 *
 * The stack waiter is completely detached before local_lock returns. Its
 * physical queue head then lives in the mutex object, indexed by root.held_local
 * until local_unlock. Original task identity and that exact object/index remain
 * authoritative; a bare lock address does not invent a prior source grant.
 * The root retains its task, and object storage survives the final release.
 *
 * While any held_local entry exists, optional source delegation admission must
 * decline BEFORE capture/publication. Further native lock nesting still uses
 * this same local MCS lane. This is an admission boundary, not a prohibition of
 * mixed locking patterns, and supplies no claimed mixed JIT coverage. Persistent
 * grants acquired earlier keep their own exact unlock route; these functions
 * never release or reinterpret such a grant. No ancestor is waited on for space.
 */
int kd_mutex_local_lock(struct kd_mutex *lock, struct kd_task_root_context *root);
int kd_mutex_local_unlock(struct kd_mutex *lock, struct kd_task_root_context *root);
/* Exact actual local owner AND held-object index membership, metadata only. */
bool kd_mutex_local_held(struct kd_mutex *lock, struct kd_task_root_context *root);

#endif
