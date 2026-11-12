/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_IMAGE_INPUTS_H
#define KDLOCK_IMAGE_INPUTS_H

#include <linux/types.h>
#include "jit.h"

/* Exact retained decoded bytes, including sites not emitted as source code.
 * This table records construction inputs, never runtime coverage or a lease.
 */
struct kd_jit_image_source_bytes {
	unsigned long ip;
	const unsigned char *bytes;
	unsigned int length;
};

/*
 * Emitted beside the actual C descriptor by the same artifact construction.
 * The caller retains this record and its code/metadata through every observer.
 * image binds these version/GS/source records to that descriptor. Source load
 * addresses remain numeric original addresses; module relocation does not
 * substitute another source incarnation. The source epoch/provider establishes
 * and retains the actual coherent load/configuration/byte relationship.
 *
 * Matching these records is input consistency, not source/code retention,
 * executable publication, instruction equivalence or coverage acknowledgement.
 */
struct kd_jit_image_inputs {
	const struct kd_jit_image *image;
	const unsigned char *source_version;
	size_t source_version_length;
	unsigned long current_task_gs_offset;
	const struct kd_jit_image_source_bytes *source_bytes;
	unsigned int source_count;
};

#endif
