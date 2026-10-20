// SPDX-License-Identifier: GPL-2.0
/* Read counters only at drained phase boundaries. No tracing or reset API. */
#include <linux/cpu.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/moduleparam.h>
#include <asm/page.h>
#include "kd_admission.h"

DEFINE_PER_CPU(struct kd_admission_counts, kd_admission);

static int kd_admission_get(char *buffer, const struct kernel_param *parameter)
{
	unsigned long field = (unsigned long)parameter->arg;
	int cpu, length = 0;

	if (field >= KD_ADMISSION_FIELDS)
		return -EINVAL;
	/* One field per file bounds 64 CPU values well below one sysfs page.
	 * CPU labels retain sparse identities instead of implying array order. */
	for_each_possible_cpu(cpu) {
		if (length > PAGE_SIZE - 48)
			return -EOVERFLOW;
		length += scnprintf(buffer + length, PAGE_SIZE - length,
				    "%s%d:%lu", length ? " " : "", cpu,
				    READ_ONCE(per_cpu(kd_admission, cpu).value[field]));
	}
	return length + scnprintf(buffer + length, PAGE_SIZE - length, "\n");
}
static const struct kernel_param_ops kd_admission_ops = {
	.get = kd_admission_get,
};
#define KD_ADMISSION_FIELD(name) \
	module_param_cb(admission_##name, &kd_admission_ops, \
			(void *)(unsigned long)KD_ADMISSION_##name, 0444);
#include "kd_admission_fields.def"
#undef KD_ADMISSION_FIELD
