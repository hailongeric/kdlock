/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_DEPTH_SOURCE_H
#define KD_DEPTH_SOURCE_H

struct mutex;

/* Test-only CALL target; the record and locks remain owned by klock_module. */
void kd_depth_source_enter(struct mutex *locks);

#endif
