// SPDX-License-Identifier: GPL-2.0
/* Execute the shared assembly register probe on a private userspace stack.
 * Mutation checks validate its oracle, not kernel JIT or flags restoration. */
#include <stdio.h>
#include <string.h>

#define ASM_RET "ret\n\t"
register unsigned long current_stack_pointer asm("rsp");
#define ASM_CALL_CONSTRAINT "+r"(current_stack_pointer)
#include "../../../workload_modules/lock_scenarios/fragments/native_register_probe.h"

static unsigned int checks, failures;
#define CHECK(condition)            \
	do {                        \
		checks++;           \
		if (!(condition))   \
			failures++; \
	} while (0)

int main(void)
{
	const unsigned long seeds[] = { 0, 1, 0xffff, 0x12345678abcdef00,
					~0UL };
	struct kd_register_sample sample, saved;
	unsigned int i, field;

	for (i = 0; i < sizeof(seeds) / sizeof(seeds[0]); i++) {
		memset(&sample, 0, sizeof(sample));
		sample.seed = seeds[i];
		CHECK(kd_register_mismatch(&sample, seeds[i]) != 0);
		kd_register_probe(&sample);
		CHECK(kd_register_mismatch(&sample, seeds[i]) == 0);
		CHECK(sample.gpr[0] == (0x1122334455667788UL ^ seeds[i]));
		CHECK(sample.gpr[15] == (0xddeeff0011223344UL ^ seeds[i]));
		saved = sample;
		/* All captured values, dynamic expectations, return and seed must matter.
		 * Mutate in place so RDI still identifies the original buffer. */
		for (field = 0; field < 25; field++) {
			unsigned long word;

			sample = saved;
			memcpy(&word, (char *)&sample + field * sizeof(word),
			       sizeof(word));
			word ^= 1;
			memcpy((char *)&sample + field * sizeof(word), &word,
			       sizeof(word));
			CHECK(kd_register_mismatch(&sample, seeds[i]) != 0);
		}
		sample = saved;
		kd_register_probe(&sample);
		CHECK(kd_register_mismatch(&sample, seeds[i]) == (1UL << 20));
	}
	printf("native register probe: %u checks, %u failures; native only, no JIT\n",
	       checks, failures);
	return failures != 0;
}
