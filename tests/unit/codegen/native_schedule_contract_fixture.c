/* SPDX-License-Identifier: GPL-2.0 */
/* VM-only policy fixture. It does not execute a kernel scheduling entry. */
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#define IS_ENABLED(option) (option)
#include "production.h"

#define CHECK(condition) do { \
	if (!(condition)) { \
		fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #condition); \
		return 1; \
	} \
	++checks; \
} while (0)

#define KD_SERVICE_CONTEXT(name, args, result_type, context) \
	{ .symbol = #name, .nargs = args, .result_kind = result_type, .context_kind = context },
#define KD_SERVICE_CALL(name, args, result_type) \
	KD_SERVICE_CONTEXT(name, args, result_type, KD_SERVICE_CALL_BALANCED_ORIGIN)
static const struct kd_service_call_desc primitives[] = {
#include "kd_service_calls.def"
};
#undef KD_SERVICE_CALL
#undef KD_SERVICE_CONTEXT

int main(void)
{
	struct kd_service_call_desc desc = {
		.nargs = 0, .result_kind = KD_SERVICE_CALL_VOID,
		.context_kind = KD_SERVICE_CALL_SCHEDULE_ORIGIN,
	};
	unsigned int checks = 0, schedules = 0, policies = 0;
	unsigned int context, pins, rcu;
	size_t i;

	CHECK(KD_SERVICE_CALL_SCHEDULE_ORIGIN == 10);
	CHECK(kd_service_call_context_valid(&desc));
	CHECK(!kd_service_call_requires_preempt_rcu(desc.context_kind));
	desc.nargs = 1;
	CHECK(!kd_service_call_context_valid(&desc));
	desc.nargs = 0;
	desc.result_kind = KD_SERVICE_CALL_WORD;
	CHECK(!kd_service_call_context_valid(&desc));
	desc.result_kind = KD_SERVICE_CALL_VOID;
	desc.context_kind = KD_SERVICE_CALL_NONRETURNING_ORIGIN + 1;
	CHECK(!kd_service_call_context_valid(&desc));

	for (pins = 0; pins != 3; ++pins) {
		for (rcu = 0; rcu != 3; ++rcu) {
			bool allowed = !pins && (!rcu || CONFIG_PREEMPT_RCU);

			CHECK(kd_service_schedule_origin_allowed(pins, rcu) == allowed);
		}
	}
	for (context = KD_SERVICE_CALL_BALANCED_ORIGIN;
	     context <= KD_SERVICE_CALL_SCHEDULE_ORIGIN; ++context) {
		bool owner_context = context >= KD_SERVICE_CALL_PTE_LOCK &&
			context <= KD_SERVICE_CALL_PTE_RCU;

		CHECK(kd_service_call_requires_preempt_rcu(context) == owner_context);
		CHECK(kd_service_native_executor_pinned(context, 0) == owner_context);
		CHECK(kd_service_native_executor_pinned(context, 1));
	}
	for (i = 0; i < sizeof(primitives) / sizeof(primitives[0]); ++i) {
		const struct kd_service_call_desc *primitive = &primitives[i];
		bool owner_context = kd_service_call_requires_preempt_rcu(primitive->context_kind);

		CHECK(kd_service_call_context_valid(primitive) ==
			(!owner_context || CONFIG_PREEMPT_RCU));
		if (primitive->context_kind == KD_SERVICE_CALL_SCHEDULE_ORIGIN) {
			++schedules;
			CHECK(!primitive->nargs && primitive->result_kind == KD_SERVICE_CALL_VOID);
			CHECK(strcmp(primitive->symbol, "preempt_schedule_irq"));
		}
		if (!strcmp(primitive->symbol, "security_vm_enough_memory_mm")) {
			++policies;
			CHECK(primitive->nargs == 2 && primitive->result_kind == KD_SERVICE_CALL_WORD &&
				primitive->context_kind == KD_SERVICE_CALL_BALANCED_ORIGIN);
		}
		if (!strcmp(primitive->symbol, "security_mmap_addr")) {
			++policies;
			CHECK(primitive->nargs == 1 && primitive->result_kind == KD_SERVICE_CALL_WORD &&
				primitive->context_kind == KD_SERVICE_CALL_BALANCED_ORIGIN);
		}
	}
	CHECK(schedules == 8);
	CHECK(policies == 2);
	printf("Native schedule context: checks=%u PREEMPT_RCU=%u\n", checks,
		(unsigned int)CONFIG_PREEMPT_RCU);
	return 0;
}
