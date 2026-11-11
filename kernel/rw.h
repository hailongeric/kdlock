/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_RW_H
#define KDLOCK_RW_H

#include <linux/spinlock.h>
#include <linux/wait.h>
#include "mutex.h"

struct kd_execution_binding;

/* Writer queue ownership and concurrent reader credits are separate duties. */
struct kd_rw {
	struct kd_mutex queue;
	raw_spinlock_t guard;
	wait_queue_head_t changed;
	unsigned long readers;
	bool writer_pending;
	struct kd_mutex_batch *writer;
};

struct kd_rwsem { struct kd_rw core; };
struct kd_rwlock { struct kd_rw core; };

#define KD_RW_INITIALIZER(_name) { \
	.queue = KD_MUTEX_INITIALIZER, \
	.guard = __RAW_SPIN_LOCK_UNLOCKED((_name).guard), \
	.changed = __WAIT_QUEUE_HEAD_INITIALIZER((_name).changed), \
	.readers = 0, .writer_pending = false, .writer = NULL }
#define KD_RWSEM_INITIALIZER(_name) { .core = KD_RW_INITIALIZER((_name).core) }
#define KD_RWLOCK_INITIALIZER(_name) { .core = KD_RW_INITIALIZER((_name).core) }

/* Exact caller-preallocated shared credit, never an exclusive mutex owner.
 * Its containing user survives acquisition, release and final unlink. Fields
 * become immutable on preparation except active/released under credit->guard
 * together with the lock count. Released metadata has independent backing.
 * An active credit retains its lock object through release's final wakeup;
 * only this credit/control storage is needed by later completion checks.
 */
struct kd_rw_read_credit {
	raw_spinlock_t guard;
	struct kd_rw *lock;
	struct kd_thread_state *state;
	const void *acquisition;
	const void *user;
	bool active;
	bool released;
	bool atomic_wait;
};

struct kd_rw_wait_ops {
	int (*progress)(void *context, bool *blocked);
	bool (*ready)(void *context);
};

void kd_rwsem_init(struct kd_rwsem *lock);
void kd_rwlock_init(struct kd_rwlock *lock);
void kd_rw_read_credit_init(struct kd_rw_read_credit *credit);
int kd_rw_read_acquire(struct kd_rw *lock, struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, struct kd_execution_binding *binding,
		const void *acquisition, const void *user, bool atomic_wait,
		const struct kd_rw_wait_ops *ops, void *context);
int kd_rw_read_release(struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, struct kd_execution_binding *binding,
		const void *acquisition, const void *user);
int kd_rw_read_credit_check(struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, const void *acquisition,
		const void *user, bool require_active);
/* Released-credit validation before the containing node actor is dropped.
 * No independent reference/callback is hidden here. Historical scalar fields
 * remain retryable if that later actor drop fails; private init resets them.
 * Checking an inactive credit never dereferences its former lock object.
 */
int kd_rw_read_credit_unlink(struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, const void *acquisition, const void *user);

/* Configure private writer requests before publication. The common MCS turn
 * closes reader admission and drains existing credits before binding a writer.
 */
int kd_rw_write_prepare(struct kd_rw *lock, struct kd_mutex_node *node,
		       bool atomic_wait);
int kd_rw_write_acquire(struct kd_rw *lock, struct kd_mutex_node *node,
		struct kd_mutex_batch *batch, unsigned int proxy_limit,
		enum kd_mutex_outcome *outcome);
/* Native mode operation: reserve a real read credit, then ask the exact owner
 * to convert continuously and acknowledge writer release. This never means a
 * retained proxy downgrade, whose physical writer remains unchanged.
 */
int kd_rw_write_downgrade(struct kd_mutex_node *node,
		struct kd_rw_read_credit *credit, struct kd_thread_state *state,
		struct kd_execution_binding *binding,
		const void *acquisition, const void *user);
int kd_rw_write_held(struct kd_mutex_node *node, struct kd_thread_state *state);

/* Private common-queue hooks. No source work or packet access occurs here. */
void kd_rw_writer_enter(struct kd_rw *lock, struct kd_mutex_batch *batch,
			struct kd_mutex_node *waiter);
void kd_rw_writer_exit(struct kd_rw *lock, struct kd_mutex_batch *batch,
			struct kd_rw_read_credit *conversion);

#endif
