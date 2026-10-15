// SPDX-License-Identifier: GPL-2.0
/*
 * Compile the spin and owned mutex combiners with their shared
 * execution helpers. Each delegated request crosses these layers; one translation
 * unit lets the compiler inline those calls and reuse validated state without
 * LTO, duplicated implementations, or changing the source/owner protocol.
 *
 * The implementation files remain organized by responsibility. Do not also
 * link their separate objects: they share this one physical execution unit.
 * Spin and mutex retain their existing noipa stack-switch/restore boundaries.
 * Their private queue helpers use distinct names; public ABI entry points and
 * the mutex ownership/ACK ledger are unchanged.
 */
#include "kd_exec.c"
#include "exe.c"
#include "kd_spinlock.c"

#include "owned_mutex/delegation.c"
