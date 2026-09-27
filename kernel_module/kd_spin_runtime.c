// SPDX-License-Identifier: GPL-2.0
/* Compile the spin combiner and its execution helpers together. The ordinary
 * delegated path crosses all three layers on every request; one translation
 * unit lets the compiler inline those calls and reuse validated state without
 * LTO, duplicated implementations, or changing the source/owner protocol.
 *
 * The implementation files remain organized by responsibility. Do not also
 * link their separate objects: they share this one physical execution unit.
 * kd_spinlock.c contains the existing non-standard stack-switch assembly.
 */
#include "kd_exec.c"
#include "exe.c"
#include "kd_spinlock.c"
