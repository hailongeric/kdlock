/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KD_TEST_NATIVE_CONTEXT_BOUNDARIES_INC
#define KD_TEST_NATIVE_CONTEXT_BOUNDARIES_INC

#include <linux/rcupdate.h>
#include <linux/spinlock.h>

#include "kernel/runtime.h"

/* Generic native-context input metadata, not an execution service. Read-side
 * RCU can begin before a later spin acquisition, so a spin-only frontier would
 * already be inside that context. Keep each API entry as a permanent cut
 * before its physical effects. The host may additionally cut at its actual
 * source CALL; entry metadata alone permits the CALL word to be staged first.
 *
 * These four linked entries describe the selected out-of-line plain-spin and
 * preemptible-RCU target. Inline effects and IRQ/BH/NMI variants require their
 * own exact pre-effect metadata. No mixed-family/context support follows.
 * The including provider retains this static array through its runtime users.
 */
static const struct kd_jit_runtime_boundary kd_test_native_context_boundaries[] = {
	{ (unsigned long)__rcu_read_lock, KD_JIT_RUNTIME_SPECIAL },
	{ (unsigned long)__rcu_read_unlock, KD_JIT_RUNTIME_SPECIAL },
	{ (unsigned long)_raw_spin_lock, KD_JIT_RUNTIME_SPECIAL },
	{ (unsigned long)_raw_spin_unlock, KD_JIT_RUNTIME_SPECIAL },
};

#endif
