#ifndef KD_SEGMENT_H
#define KD_SEGMENT_H

/* Capture the origin CPU's kernel GS base at a pinned hook entry. This is
 * address metadata, not a remote current/IRQ/RCU or per-CPU concurrency switch. */
#include <linux/smp.h>
#include <asm/processor.h>

static __always_inline unsigned long kd_read_kernel_gsbase(void)
{
	return cpu_kernelmode_gs_base(raw_smp_processor_id());
}

#endif /* KD_SEGMENT_H */
