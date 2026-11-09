/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SERVICE_API_H
#define KD_SERVICE_API_H

#include "kd_admission.h"

struct module;
struct task_struct;
struct kd_service_completion {
	struct module *owner;
	void (*resume)(struct module *owner, const void *full_packet) __noreturn;
};

/* The capture engine owns eligibility, exact publication, origin signal
 * arbitration and continuation retirement. Frontends pass the real caller's
 * SP/IP/BP; they never capture a returning helper's continuation. */
int kd_service_capture(void *object, enum kd_admission_kind kind,
	unsigned int state, unsigned long sp, unsigned long ip, unsigned long bp);
int kd_service_capture_bound(void *object, enum kd_admission_kind kind,
	unsigned int state, unsigned long sp, unsigned long ip, unsigned long bp,
	const struct kd_service_completion *completion);
bool kd_service_write_owned(void *object, struct task_struct *task);
int kd_service_init(void);
void kd_service_exit(void);
bool kd_service_idle(void);

#endif
