/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SC_DIRECT_H
#define SC_DIRECT_H

/* Each comparison binary contains only one backend. No selector, hotlock
 * discovery or function-pointer backend switch runs inside an operation. */
#if defined(SC_DIRECT_KDLOCK)
#include <linux/objtool.h>
#include "kd_spin_direct.h"
/* Every KD build routes by CPU heat. All call sites and lock objects share
 * the provider's one cookie per CPU; admission mode is a provider policy. */
#define SC_LOCK(n) KD_SPIN_DIRECT_LOCK(&sc_lock, kd_spin_direct_cookie, \
	".globl sc_entry_" #n "\nsc_entry_" #n ":\n\t" ANNOTATE_NOENDBR)
#define SC_UNLOCK() KD_SPIN_DIRECT_UNLOCK(&sc_lock, kd_spin_direct_cookie)
extern char sc_entry_1[], sc_entry_2[], sc_entry_4[], sc_entry_8[], sc_entry_16[];
extern char sc_entry_0[];
#elif defined(SC_DIRECT_TCLOCK)
void komb_spin_lock(struct qspinlock *lock);
void komb_spin_unlock(struct qspinlock *lock);
#define SC_LOCK(n) do { preempt_disable(); \
	komb_spin_lock((struct qspinlock *)&sc_lock); } while (0)
#define SC_UNLOCK() do { komb_spin_unlock((struct qspinlock *)&sc_lock); \
	preempt_enable(); } while (0)
#elif defined(SC_DIRECT_NATIVE)
#define SC_LOCK(n) __raw_spin_lock(&sc_lock.rlock)
#define SC_UNLOCK() __raw_spin_unlock(&sc_lock.rlock)
#else
/* Other existing workloads retain their source-level API. */
#define SC_LOCK(n) spin_lock(&sc_lock)
#define SC_UNLOCK() spin_unlock(&sc_lock)
#endif

#endif
