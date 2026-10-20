/* SPDX-License-Identifier: GPL-2.0 */
/* VM userspace fixture: compare the actual sampler with the independent reader. */
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include "../../../workload_modules/latency/operation_latency.h"

static struct kd_latency_slot slot;
/* Retained ELF CRC words exercise the module export reader without a module. */
const unsigned int __crc_fixture __attribute__((section("__kcrctab_gpl"))) = 0x12345678;
const unsigned int __ksymtab_fixture = 1;

int main(int argc, char **argv)
{
	unsigned int worker;
	unsigned long long done, ordinal;

	if (argc != 3)
		return 2;
	worker = strtoul(argv[1], NULL, 10);
	done = strtoull(argv[2], NULL, 10);
	kd_latency_reset(&slot, worker);
	for (ordinal = 0; ordinal < done; ordinal++)
		if (kd_latency_select(&slot, ordinal))
			kd_latency_record(&slot, ordinal, 100 + ordinal * 4,
					  102 + ordinal * 4);
	slot.completed = done;
	printf("%zu %zu %lu %llu %llu\n",
	       offsetof(struct kd_latency_chunk, samples),
	       sizeof(struct kd_latency_chunk), (unsigned long)KD_LATENCY_READ,
	       slot.selected, slot.dropped);
	for (ordinal = 0; ordinal < slot.selected && ordinal < KD_LATENCY_CAPACITY; ordinal++)
		printf("%llu %llu %llu\n", slot.samples[ordinal].ordinal,
		       slot.samples[ordinal].started_ns, slot.samples[ordinal].finished_ns);
	return 0;
}
