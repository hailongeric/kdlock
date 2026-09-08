#ifndef KD_SEGMENT_H
#define KD_SEGMENT_H

#include <linux/smp.h>
#include <asm/processor.h>

static __always_inline unsigned long kd_read_kernel_gsbase(void)
{
	return cpu_kernelmode_gs_base(raw_smp_processor_id());
}

#endif /* KD_SEGMENT_H */
