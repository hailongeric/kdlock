// SPDX-License-Identifier: GPL-2.0
#ifndef KD_JIT_COMPONENT_FIXTURE
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <asm/sync_core.h>
#endif
#include "kd_reached_jit.h"

#include "reached_jit_emit.inc"

#ifndef KD_JIT_COMPONENT_FIXTURE
struct jit_program {
	unsigned long source_ip;
	u8 bytes[KD_REACHED_MAX_BYTES];
	u8 length, edge;
	u8 *code;
	bool valid;
};
struct jit_cpu_cache {
	struct jit_program programs[KD_REACHED_JIT_CACHE_SLOTS];
	unsigned int cursor, slots;
	bool active;
};
static struct jit_cpu_cache __percpu *jit_caches;
static unsigned long jit_return;

int kd_reached_jit_start(void *arena, unsigned long bytes, unsigned long return_target)
{
	unsigned int slots, cpu, index;
	u8 *code = arena;

	if (!arena || !return_target || jit_caches)
		return -EINVAL;
	slots = min_t(unsigned long, KD_REACHED_JIT_CACHE_SLOTS,
		bytes / nr_cpu_ids / KD_REACHED_JIT_SLOT_BYTES);
	if (!slots)
		return -ENOSPC;
	jit_caches = alloc_percpu(struct jit_cpu_cache);
	if (!jit_caches)
		return -ENOMEM;
	for_each_possible_cpu(cpu) {
		struct jit_cpu_cache *cache = per_cpu_ptr(jit_caches, cpu);
		cache->slots = slots;
		cache->cursor = 0;
		cache->active = false;
		for (index = 0; index < slots; ++index) {
			cache->programs[index].valid = false;
			cache->programs[index].code = code;
			code += KD_REACHED_JIT_SLOT_BYTES;
		}
	}
	jit_return = return_target;
	return 0;
}

void kd_reached_jit_stop(void)
{
	unsigned int cpu;

	if (!jit_caches)
		return;
	for_each_possible_cpu(cpu)
		BUG_ON(per_cpu_ptr(jit_caches, cpu)->active);
	free_percpu(jit_caches);
	jit_caches = NULL;
	jit_return = 0;
}

static u8 jit_edge(unsigned int operation)
{
	return operation == OP_CALL ? KD_REACHED_CALL : operation == OP_JMP ? KD_REACHED_JUMP :
		operation == OP_RET ? KD_REACHED_RETURN : operation == OP_JCC ? KD_REACHED_JCC :
		KD_REACHED_FALLTHROUGH;
}

enum kd_reached_result kd_reached_jit_step(struct kd_reached_state *s)
{
	struct jit_cpu_cache *cache;
	struct jit_program *program = NULL;
	struct decoded d;
	u8 observed[KD_REACHED_MAX_BYTES];
	unsigned int index, byte;
	int ret;
	u64 retired;
	enum kd_reached_result result;

	if (!s || !s->regs || !s->ops || !s->ops->fetch || !s->ops->read ||
	    !s->ops->write || s->packet_state != KD_PACKET_FULL || !jit_caches ||
	    !preempt_count())
		return KD_REACHED_PACKET;
	s->event = (struct kd_reached_event) { .source_ip = s->regs->ip,
		.next_ip = s->regs->ip, .target = s->regs->ip, .sequence = ++s->sequence };
	if (!s->budget)
		return s->event.result = KD_REACHED_BUDGET;
	cache = this_cpu_ptr(jit_caches);
	if (cache->active)
		return s->event.result = KD_REACHED_PACKET;
	for (index = 0; index < cache->slots; ++index) {
		struct jit_program *candidate = &cache->programs[index];
		if (!candidate->valid || candidate->source_ip != s->regs->ip)
			continue;
		for (byte = 0; byte < candidate->length; ++byte)
			if (s->ops->fetch(s->context, candidate->source_ip + byte, &observed[byte], 1))
				break;
		if (byte == candidate->length && !memcmp(observed, candidate->bytes, byte)) {
			program = candidate;
			break;
		}
	}
	if (!program) {
		ret = kd_reached_decode(s, &d);
		s->event.length = d.length;
		memcpy(s->event.bytes, d.bytes, d.length);
		if (ret)
			return s->event.result = ret == -ENODATA ? KD_REACHED_SOURCE : KD_REACHED_UNSUPPORTED;
		program = &cache->programs[cache->cursor++ % cache->slots];
		program->valid = false;
		ret = kd_reached_jit_compile(&d, program->code, KD_REACHED_JIT_SLOT_BYTES, jit_return);
		if (ret < 0)
			return s->event.result = KD_REACHED_UNSUPPORTED;
		program->source_ip = s->regs->ip;
		program->length = d.length;
		program->edge = jit_edge(d.operation);
		memcpy(program->bytes, d.bytes, d.length);
		/* This CPU alone compiles/executes these slots. No generated frame
		 * remains pending across a runtime service or a scheduling point. */
		barrier();
		sync_core();
		program->valid = true;
	}
	s->event.length = program->length;
	s->event.next_ip = program->source_ip + program->length;
	s->event.edge = program->edge;
	memcpy(s->event.bytes, program->bytes, program->length);
	cache->active = true;
	retired = s->jit_retired;
	result = ((enum kd_reached_result (*)(struct kd_reached_state *))program->code)(s);
	cache->active = false;
	if (result == KD_REACHED_NEXT || result == KD_REACHED_EDGE) {
		BUG_ON(s->jit_retired != retired + 1);
		--s->budget;
		s->event.target = s->regs->ip;
		if (program->edge == KD_REACHED_CALL) {
			s->calls[s->call_next].ip = s->event.source_ip;
			s->calls[s->call_next].target = s->regs->ip;
			s->call_next = (s->call_next + 1) & 7;
			if (s->call_count < 8) ++s->call_count;
		}
	} else BUG_ON(s->jit_retired != retired);
	return s->event.result = result;
}
#endif
