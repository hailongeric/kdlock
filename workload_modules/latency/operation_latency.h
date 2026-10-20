/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_OPERATION_LATENCY_H
#define KD_OPERATION_LATENCY_H

#include <linux/types.h>
#include <linux/ioctl.h>

/*
 * Private diagnostic payload, never protocol storage. Each physical worker
 * owns one slot and records only after its complete operation returns. A
 * delegated lock return is not an acquisition timestamp: it can resume after
 * the corresponding unlock and ACK. Both timestamps therefore surround the
 * entire ordinary call, outside its admitted critical section.
 *
 * Pick one operation in each 256-operation block. Distinct worker seeds and
 * changing offsets avoid sampling the same deterministic batch position.
 * The sequence is reproducible from worker identity and completed operations.
 */
#define KD_LATENCY_VERSION 1U
#define KD_LATENCY_STRIDE 256U
#define KD_LATENCY_CAPACITY 131072U
#define KD_LATENCY_CHUNK 256U

struct kd_latency_sample {
	__u64 ordinal;
	__u64 started_ns;
	__u64 finished_ns;
};

struct kd_latency_slot {
	__u64 random;
	__u64 selected;
	__u64 dropped;
	__u64 completed;
	__u32 offset;
	__u32 reserved;
	struct kd_latency_sample samples[KD_LATENCY_CAPACITY];
};

static inline void kd_latency_reset(struct kd_latency_slot *slot,
				    unsigned int worker)
{
	slot->random = (worker + 1ULL) * 0x9e3779b97f4a7c15ULL;
	slot->selected = 0;
	slot->dropped = 0;
	slot->completed = 0;
	slot->offset = 0;
	slot->reserved = 0;
}

static inline int kd_latency_select(struct kd_latency_slot *slot,
				    __u64 ordinal)
{
	if (!(ordinal & (KD_LATENCY_STRIDE - 1U))) {
		__u64 state = slot->random;

		state ^= state >> 12;
		state ^= state << 25;
		state ^= state >> 27;
		slot->random = state;
		slot->offset = (state * 0x2545f4914f6cdd1dULL) &
			       (KD_LATENCY_STRIDE - 1U);
	}
	return (ordinal & (KD_LATENCY_STRIDE - 1U)) == slot->offset;
}

static inline void kd_latency_record(struct kd_latency_slot *slot,
				     __u64 ordinal, __u64 start, __u64 end)
{
	__u64 index = slot->selected++;

	if (index >= KD_LATENCY_CAPACITY) {
		slot->dropped++;
		return;
	}
	slot->samples[index].ordinal = ordinal;
	slot->samples[index].started_ns = start;
	slot->samples[index].finished_ns = end;
}

/* Read only while the original workload's control gate is quiescent. The
 * file descriptor pins the module; the ordinary gate excludes reconfiguration
 * during each copy. No reader runs concurrently with measured workers. */
struct kd_latency_chunk {
	__u32 version, worker, first, capacity;
	__u64 started_ns, completed, selected, dropped;
	__u32 count, enabled;
	__u64 reserved;
	struct kd_latency_sample samples[KD_LATENCY_CHUNK];
};
#define KD_LATENCY_READ _IOWR(0xB7, 0x40, struct kd_latency_chunk)

#endif
