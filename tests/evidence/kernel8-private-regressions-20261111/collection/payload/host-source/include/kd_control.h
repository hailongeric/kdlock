/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_CONTROL_ABI_H
#define KDLOCK_CONTROL_ABI_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define KD_CONTROL_ABI 1ULL
#define KD_CONTROL_QUERY 0ULL

/* x86_64 control channel, nine little-endian words. Payload addresses are user
 * addresses only; kernel object identities occur in bounded payload records.
 * sequence starts at one and never wraps. Repeat an ambiguous exchange with the
 * SAME sequence/op/input to recover its cached result without another dispatch.
 */
struct kd_control_exchange {
	__u64 abi;
	__u64 operation;
	__u64 sequence;
	__u64 input;
	__u64 input_length;
	__u64 output;
	__u64 output_capacity;
	__u64 output_length;
	__s64 status;
};

#define KD_CONTROL_EXCHANGE _IOWR('K', 0, struct kd_control_exchange)
_Static_assert(sizeof(struct kd_control_exchange) == 72, "control exchange size");

/* QUERY uses operation=sequence=input_length=0 and changes no cached state.
 * Output is six LE u64 words: ABI, last operation, last sequence, signed status,
 * input length, output length; then exact last input and output bytes. Empty
 * history has zero operation/sequence/status/lengths. A reconnect must reconcile
 * this retained exchange before submitting the next sequence.
 */
#endif
