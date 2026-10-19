/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_AUX_H
#define KD_MUTEX_AUX_H

#include <linux/list.h>
#include "kd_mutex.h"

/* Delegation storage is separate from the caller's native-sized KD primitive.
 * Every active queue invocation and every gate owner holds an exact reference.
 * Frames borrow the enclosing invocation, including early outer release and
 * native owner ACKs; a retired waiter node is never their lifetime anchor. */
struct kd_mutex_aux {
	struct kd_mutex *lock;
	struct hlist_node link;
	unsigned int refs; /* Protected by this address's registry bucket. */
	struct task_struct *physical_owner __attribute__((aligned(64)));
	union {
		atomic_t state;
		struct {
			u8 locked;
		};
	};
	u32 tail __attribute__((aligned(64)));
	atomic_t waiter_count __attribute__((aligned(64)));
} __attribute__((aligned(128)));

int kd_mutex_aux_init(void);
void kd_mutex_aux_exit(void);
struct kd_mutex_aux *kd_mutex_aux_get(struct kd_mutex *lock);
struct kd_mutex_aux *kd_mutex_aux_lookup(struct kd_mutex *lock);
void kd_mutex_aux_ref(struct kd_mutex_aux *aux);
void kd_mutex_aux_put(struct kd_mutex_aux *aux);
bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task);
bool kd_mutex_combiner_active(struct kd_mutex *lock);
int kd_mutex_aux_waiter_count(struct kd_mutex *lock);
bool kd_mutex_aux_is_idle(struct kd_mutex *lock);
bool kd_mutex_aux_all_idle(void);
unsigned int kd_mutex_debug_aux_count(void);

#endif
