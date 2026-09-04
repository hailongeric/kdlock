#ifndef KD_SEGMENT_H
#define KD_SEGMENT_H

#include <linux/sched.h>
#include <linux/smp.h>
#include <asm/processor.h>

static __always_inline unsigned long kd_read_kernel_gsbase(void)
{
	return cpu_kernelmode_gs_base(raw_smp_processor_id());
}

static __always_inline unsigned long
kd_kernel_gsbase_for_task(const struct task_struct *task)
{
	return task ? cpu_kernelmode_gs_base(task_cpu(task)) : 0;
}

#endif /* KD_SEGMENT_H */
