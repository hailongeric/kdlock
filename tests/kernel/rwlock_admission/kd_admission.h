/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_ADMISSION_DIAGNOSTIC_H
#define KD_ADMISSION_DIAGNOSTIC_H
#include <linux/percpu.h>

/*
 * This header is copied only into a private diagnostic provider. The measured
 * workload, production provider and two-word wrapper ABI remain unchanged.
 * Call sites own a CPU pin. These counters explain advisory decisions; they
 * must never become a condition for admission, ownership, ACK or retirement.
 */
enum kd_admission_field {
#define KD_ADMISSION_FIELD(name) KD_ADMISSION_##name,
#include "kd_admission_fields.def"
#undef KD_ADMISSION_FIELD
	KD_ADMISSION_FIELDS
};
struct kd_admission_counts {
	unsigned long value[KD_ADMISSION_FIELDS];
};
DECLARE_PER_CPU(struct kd_admission_counts, kd_admission);
#define KD_ADMISSION_NOTE(name) \
	this_cpu_inc(kd_admission.value[KD_ADMISSION_##name])
#define KD_ADMISSION_ADD(name, amount) \
	this_cpu_add(kd_admission.value[KD_ADMISSION_##name], (amount))

static __always_inline void kd_admission_clock(unsigned long entries,
					       unsigned long mcs)
{
	unsigned long smallest =
		this_cpu_read(kd_admission.value[KD_ADMISSION_cpu_entries_min]);
	unsigned long largest =
		this_cpu_read(kd_admission.value[KD_ADMISSION_cpu_entries_max]);

	/* Min/max are lifetime diagnostics, not resettable admission state. */
	if (!this_cpu_read(kd_admission.value[KD_ADMISSION_cpu_checks]) ||
	    entries < smallest)
		this_cpu_write(kd_admission.value[KD_ADMISSION_cpu_entries_min],
			       entries);
	if (entries > largest)
		this_cpu_write(kd_admission.value[KD_ADMISSION_cpu_entries_max],
			       entries);
	KD_ADMISSION_NOTE(cpu_checks);
	KD_ADMISSION_ADD(cpu_entries_sum, entries);
	KD_ADMISSION_ADD(cpu_mcs_sum, mcs);
}
#endif
