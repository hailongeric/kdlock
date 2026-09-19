/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_GATE_H
#define KD_SPIN_GATE_H

#include <linux/spinlock.h>
#include "qspinlock_i.h"

/* The scheduling word is never overlaid on origin. Entries remain stable
 * until controlled module teardown; an idle entry may serve a reused address.
 * origin is release-published after initialization and acquire-read by find.
 * A pointer proves map membership, never current ownership of Linux L.
 */
struct kd_spin_gate {
	/* Align each gate, not just the table: unrelated locks must never share
	 * the cache line containing their independently modified scheduling words.
	 * Member alignment also rounds the array stride up to a full x86 line. */
	struct orig_qspinlock word __attribute__((aligned(64)));
	raw_spinlock_t *origin;
	struct task_struct *owner;
	unsigned long generation;
	int owner_cpu;
	bool held;
};

/* Physical ownership only, not the logical waiter's entry/preemption ticket.
 * Keep this token alive until the real owner releases origin; do not transfer
 * it to a delegated waiter or store it in a recyclable queue node.
 */
struct kd_spin_hold {
	struct kd_spin_gate *gate;
	struct task_struct *owner;
	unsigned long generation;
	int cpu;
};

struct kd_spin_gate *kd_spin_gate_get(raw_spinlock_t *origin);
struct kd_spin_gate *kd_spin_gate_find(raw_spinlock_t *origin);
int kd_spin_gate_claim(struct kd_spin_gate *gate, struct kd_spin_hold *hold);
int kd_spin_gate_release(struct kd_spin_hold *hold);
int kd_spin_gates_check_idle(void);

/* Claim requires exclusive scheduling-word ownership and a task-context CPU
 * pin established by the caller. Release preserves that pin and the private
 * word. Only after release may the caller publish the gate as available.
 */
#ifdef KDLOCK_SELFTEST
int kd_spin_gate_selftest(void);
#endif

#endif
