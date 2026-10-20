/* SPDX-License-Identifier: GPL-2.0 */
/* Private userspace query-client diagnostic; included after now(). */
#include "operation_latency.h"

static bool latency_sample;
static struct kd_latency_slot latency_slots[MAX_WORKERS];

static void latency_initialize(void)
{
	const char *mode = getenv("KD_LATENCY_SAMPLE");
	volatile unsigned char *bytes = (void *)latency_slots;
	size_t i;

	if (!mode || (strcmp(mode, "0") && strcmp(mode, "1"))) {
		fprintf(stderr, "KD_LATENCY_SAMPLE must explicitly be 0 or 1\n");
		exit(2);
	}
	latency_sample = !strcmp(mode, "1");
	/* Materialize every storage page before readiness and timing. Both
	 * disabled and sampled arms pay this untimed preparation cost. */
	for (i = 0; i < sizeof(latency_slots); i += 4096)
		bytes[i] = 0;
}

static void latency_json(int cohort)
{
	int worker;

	printf(",\"operation_latency\":{\"version\":1,\"enabled\":%s,\"rows\":[",
	       latency_sample ? "true" : "false");
	for (worker = 0; worker < cohort; worker++) {
		const struct kd_latency_slot *slot = &latency_slots[worker];
		__u64 i, count = slot->selected < KD_LATENCY_CAPACITY ?
			slot->selected : KD_LATENCY_CAPACITY;

		printf("%s{\"worker\":%d,\"completed\":%llu,\"selected\":%llu,"
		       "\"dropped\":%llu,\"enabled\":%s,\"samples\":[",
		       worker ? "," : "", worker, slot->completed, slot->selected,
		       slot->dropped, latency_sample && timed ? "true" : "false");
		for (i = 0; i < count; i++) {
			const struct kd_latency_sample *sample = &slot->samples[i];

			printf("%s[%llu,%llu,%llu]", i ? "," : "", sample->ordinal,
			       sample->started_ns, sample->finished_ns);
		}
		printf("]}");
	}
	printf("]}");
}
