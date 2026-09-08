// SPDX-License-Identifier: GPL-2.0
#include <asm/linkage.h>
#include "native_register_probe.h"

static bool native_resume_registers;
static bool native_regs_armed;
module_param(native_resume_registers, bool, 0444);
module_param(native_regs_armed, bool, 0644);
MODULE_PARM_DESC(
	native_resume_registers,
	"Stages 1..3: capture CALL-miss GPRs and stack, excluding flags");
MODULE_PARM_DESC(
	native_regs_armed,
	"Retain per-request register witnesses after translation is ready");
static struct kd_register_sample *register_samples;

static int kd_register_init(void)
{
	if (native_regs_armed)
		return -EINVAL;
	if (!native_resume_registers)
		return 0;
	if (!native_resume_stage || native_resume_stage > 3 ||
	    native_pending_contended || mixed_lock_probe)
		return -EINVAL;
	register_samples = kvcalloc(KD_RESUME_RECORDS,
				    sizeof(*register_samples), GFP_KERNEL);
	return register_samples ? 0 : -ENOMEM;
}

static __always_inline void kd_register_begin(unsigned int id)
{
	if (!native_resume_registers)
		return;
	register_samples[id].seed = (unsigned long)id + 1;
	register_samples[id].pid = current->pid;
}

static __always_inline void kd_register_invoke(struct kd_resume_record *record)
{
	struct kd_register_sample *sample;

	if (!native_resume_registers)
		return;
	sample = &register_samples[record - resume_records];
	sample->marked = READ_ONCE(native_regs_armed);
	kd_register_probe(sample);
}

/* Reporting occurs only after workers drain, never on a combiner stack. */
static void kd_register_report(unsigned int requests)
{
	unsigned int id, checked = 0, failures = 0, marked = 0, omitted = 0;

	if (!native_resume_registers)
		return;
	for (id = 0; id < min_t(unsigned int, requests, KD_RESUME_RECORDS);
	     id++) {
		const struct kd_register_sample *s = &register_samples[id];
		unsigned long errors =
			kd_register_mismatch(s, (unsigned long)id + 1);

		checked++;
		if (errors)
			failures++;
		if (!s->marked)
			continue;
		if (marked++ >= 128) {
			omitted++;
			continue;
		}
		pr_info("kd_regs sample: task=%lu record=%u seed=%lx buffer=%lx calls=%lu mask=%lx gpr0=%64phN gpr1=%64phN sp=%lx bp=%lx ip=%lx ret=%lx tag0=%lx tag1=%lx returned=%lx\n",
			s->pid, id, s->seed, (unsigned long)s, s->calls, errors,
			s->gpr, s->gpr + 8, s->expected_sp, s->expected_bp,
			s->expected_ip, s->return_ip, s->tag0, s->tag1,
			s->returned_ax);
	}
	pr_info("kd_regs summary: requests=%u checked=%u marked=%u omitted=%u failures=%u\n",
		requests, checked, marked, omitted, failures);
}
