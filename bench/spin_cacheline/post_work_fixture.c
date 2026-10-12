// SPDX-License-Identifier: GPL-2.0
/* Guest-only arithmetic and dead-result codegen check for the real helper. */
#include <linux/types.h>
#include <stdint.h>
#include <stdio.h>
#include "../../workload_modules/spin_cacheline/post_work.h"

__attribute__((noipa)) __u64 fixture_post_work(__u64 state)
{
	return sc_post_work(state);
}

/* Every configured round must remain even without a consumer of the result. */
__attribute__((noipa)) void fixture_discard(__u64 state)
{
	(void)sc_post_work(state);
}

int main(void)
{
	const __u64 seeds[] = {0, 1, UINT64_MAX, 0x123456789abcdef0ULL};

	for (unsigned int i = 0; i < sizeof(seeds) / sizeof(seeds[0]); i++) {
		__u64 actual = seeds[i], expected = seeds[i];

		for (unsigned int call = 0; call < 32; call++) {
			for (unsigned int round = 0; round < SC_POST_WORK_ROUNDS; round++)
				expected = expected * 1664525ULL + 1013904223ULL;
			actual = fixture_post_work(actual);
			if (actual != expected)
				return 1;
		}
		fixture_discard(seeds[i]);
	}
	puts("post-work arithmetic: 128 calls PASS");
	return 0;
}
