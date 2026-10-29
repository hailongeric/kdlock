// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
//
// Ported to kdlock: TCLocks komb.c → kd_spinlock.c
//
// kd_spinlock implements explicit delegation for KD spinlocks.
// The protocol uses a per-CPU MCS-style queue with a combiner/waiter model:
// the lock holder (combiner) executes critical sections on behalf of queued
// waiters by running JIT-translated code through kd_exe_on_call_hl_entry().
//
// Key differences from TCLocks komb.c:
//   - Calls kd_exe_on_call_hl_entry() inside execute_cs() for JIT delegation
//   - Uses kd_spin_node with a shared request/frame/register packet
//   - Delegation via sandbox JIT; a per-CPU shadow stack isolates waiter polling

/* Scheduling nodes carry packets, but kd_spin_entry owns origin tickets and
 * the KD word owns exclusion. Keep these lifetimes separate when reading the
 * nested queue paths: a remote executor may carry the same logical waiter.
 * Combiners use their task stack. Physical waiters switch to a shadow stack
 * before publication and return to their task stack after the release wake. */
#include "kd_spinlock.h"
#include "utils.h"
#include "exe.h"
#include "kd_exec.h"
#include "kd_jit_batch.h"
#include "kd_source.h"
#include "kd_segment.h"
#include "kd_spin_entry.h"
#include "kd_spin_fast.h"
#include "kd_spin_direct.h"
#include "kd_rwlock.h"
#include "kd_hotlock.h"
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <linux/static_call_types.h>
#include <linux/topology.h>
#include <linux/vmalloc.h>
#include <linux/kernel.h>
#include <linux/module.h>

/* This file assembles the spin implementation in declaration order:
 * state -> queues -> execution -> nested requests -> restore -> entry/unlock.
 * Keep one translation unit: stack-switch labels, static state and compiler
 * inlining form part of the existing entry ABI. See README.md for the map. */
#include "spin/state.inc"

#include "spin/context.inc"

#include "spin/shadow.inc"

#include "spin/diagnostics.inc"

#include "spin/queue.inc"

#include "spin/nondelegated.inc"

#include "spin/request.inc"

#include "spin/prefetch.inc"

#include "spin/combiner.inc"

#include "spin/wait.inc"

#include "spin/slowpath.inc"

#include "spin/lifecycle.inc"

#include "spin/nested.inc"

#include "spin/restore.inc"

#include "spin/entry.inc"

#include "spin/direct.inc"

#include "spin/unlock.inc"

#ifdef KDLOCK_SELFTEST
/* Keep access to private queue state out of the production API. */
#include "../tests/kernel/spin/spin_frame_trace.c"
#include "../tests/kernel/spin/spin_readmission_trace.c"
#include "../tests/kernel/spin/spin_refusal_trace.c"
#include "../tests/kernel/spin/spin_deferred_trace.c"
#include "../tests/kernel/spin/spin_shadow_selftest.c"
#include "../tests/kernel/spin/spin_virtual_selftest.c"
#endif
