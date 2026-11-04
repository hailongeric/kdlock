/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_REACHED_JIT_H
#define KD_REACHED_JIT_H
#include "kd_reached_decode.h"
#define KD_REACHED_JIT_SLOT_BYTES 2048U
#define KD_REACHED_JIT_CACHE_SLOTS 32U
int kd_reached_jit_compile(const struct decoded *instruction, void *code,
	unsigned int capacity, unsigned long return_target);
int kd_reached_jit_start(void *arena, unsigned long bytes, unsigned long return_target);
void kd_reached_jit_stop(void);
enum kd_reached_result kd_reached_jit_step(struct kd_reached_state *state);
#endif
