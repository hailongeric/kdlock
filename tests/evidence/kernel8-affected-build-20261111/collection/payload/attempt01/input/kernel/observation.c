// SPDX-License-Identifier: GPL-2.0-only
/* Optional scalar observation; protocol decisions never depend on listeners. */
#include "observation.h"

DEFINE_TRACE(kdlock_observe_tp,
	TP_PROTO(const struct kd_observation *event), TP_ARGS(event));
EXPORT_TRACEPOINT_SYMBOL_GPL(kdlock_observe_tp);
