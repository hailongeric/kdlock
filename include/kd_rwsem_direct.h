/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_DIRECT_H
#define KD_RWSEM_DIRECT_H

#include "kd_rwsem.h"
#include "kd_mutex_direct.h"

/* Same-task, lexical outer writer only. The phase reservation remains on the
 * originating task across delegated execution; the unchanged mutex owns its
 * physical owner, request ACK and frame lifetime. This pair cannot downgrade,
 * cancel after publication, or appear inside another translated body. */
struct kd_rwsem_outer_cookie {
	struct kd_mutex_outer_cookie gate;
};

#define KD_RWSEM_OUTER_WRITE_LOCK(sem, cookie, continuation) do { \
	struct kd_rwsem *kd_rwsem_outer = (sem); \
	/* Reader drainage must finish while the caller is still schedulable. */ \
	kd_rwsem_delegate_enter(kd_rwsem_outer); \
	KD_MUTEX_OUTER_LOCK(&kd_rwsem_outer->gate, (cookie).gate, continuation); \
} while (0)

/* JIT stops at the mutex unlock. Only the resumed origin releases the phase,
 * after its request has completed the existing acknowledgement protocol. */
#define KD_RWSEM_OUTER_WRITE_UNLOCK(sem, cookie) do { \
	struct kd_rwsem *kd_rwsem_outer = (sem); \
	KD_MUTEX_OUTER_UNLOCK(&kd_rwsem_outer->gate, (cookie).gate); \
	kd_rwsem_delegate_exit(kd_rwsem_outer); \
} while (0)

#endif /* KD_RWSEM_DIRECT_H */
