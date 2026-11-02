/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SERVICE_API_H
#define KD_SERVICE_API_H

#include "kd_admission.h"

/* The capture engine owns eligibility, exact publication, origin signal
 * arbitration and continuation retirement. Frontends pass the real caller's
 * SP/IP/BP; they never capture a returning helper's continuation. */
int kd_service_capture(void *object, enum kd_admission_kind kind,
	unsigned int state, unsigned long sp, unsigned long ip, unsigned long bp);
int kd_service_init(void);
void kd_service_exit(void);
bool kd_service_idle(void);

#endif
