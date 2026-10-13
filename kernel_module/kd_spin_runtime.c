// SPDX-License-Identifier: GPL-2.0
/* Compile both combiners and their shared execution helpers together. The ordinary
 * delegated path crosses all three layers on every request; one translation
 * unit lets the compiler inline those calls and reuse validated state without
 * LTO, duplicated implementations, or changing the source/owner protocol.
 *
 * The implementation files remain organized by responsibility. Do not also
 * link their separate objects: they share this one physical execution unit.
 * Spin and mutex retain their existing noipa stack-switch/restore boundaries.
 * Their private queue helpers use distinct names; public ABI entry points and
 * the original mutex ownership/ACK ledger are unchanged.
 */
#include "kd_exec.c"
#include "exe.c"
#include "kd_spinlock.c"
#include "kd_mutex.c"

#include "owned_mutex/delegation.c"
