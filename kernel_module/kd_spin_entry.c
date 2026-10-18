// SPDX-License-Identifier: GPL-2.0
/*
 * Per-acquisition origin tickets, distinct from reusable scheduling nodes.
 * Generation, phase and native borrows share one atomic word: an old remote
 * CAS cannot mutate a recycled slot. Only the pinned owner allocates/ends.
 * Native suffix borrowing ends after the real owner's final ACK/frame pop.
 */
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/limits.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/string.h>

#include "kd_spin_entry.h"
#include "kd_spin_fast.h"

/*
 * One translation unit keeps private pool state and inline CAS helpers local.
 * The components follow the lifetime of a ticket, then expose diagnostics.
 */
#include "spin/ticket_state.inc"

#include "spin/ticket_origin.inc"

#include "spin/ticket_borrow.inc"

#include "spin/ticket_diagnostics.inc"

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/spin/spin_entry_selftest.c"
#endif
