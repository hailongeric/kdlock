/*
 * Deterministic per-lock payload transitions and completion counters.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

#define KD_CS_LANES 4
#define KD_CS_VERIFY_LIMIT 10000000UL
#define KD_CS_ODD_BIAS 0x9e3779b97f4a7c15UL
#define KD_CS_EVEN_BIAS 0xc2b2ae3d27d4eb4fUL
#define KD_CS_COMMIT_BIAS 0x165667b19e3779f9UL

enum kd_cs_state_id {
	KD_CS_SPIN_GLOBAL,
	KD_CS_SPIN_A,
	KD_CS_SPIN_B,
	KD_CS_SPIN_C,
	KD_CS_MUTEX_GLOBAL,
	KD_CS_MUTEX_A,
	KD_CS_MUTEX_B,
	KD_CS_STATE_COUNT,
};

struct kd_cs_state {
	unsigned long sequence;
	unsigned long sum;
	unsigned long branch_mix;
	unsigned long rolling;
	unsigned long lanes[KD_CS_LANES];
	unsigned long commit;
};

static struct kd_cs_state kd_cs_states[KD_CS_STATE_COUNT];
/* A and B can execute concurrently. Each completion counter uses its own lock,
 * just like the state it checks; aggregate only after all workers have exited. */
static unsigned long kd_cs_completed[KD_CS_STATE_COUNT];
static const char *const kd_cs_state_names[KD_CS_STATE_COUNT] = {
	[KD_CS_SPIN_GLOBAL] = "spin-global",
	[KD_CS_SPIN_A] = "spin-a",
	[KD_CS_SPIN_B] = "spin-b",
	[KD_CS_SPIN_C] = "spin-c",
	[KD_CS_MUTEX_GLOBAL] = "mutex-global",
	[KD_CS_MUTEX_A] = "mutex-a",
	[KD_CS_MUTEX_B] = "mutex-b",
};

/* Keep this inline: every operation is part of the translated critical section. */
static __always_inline void kd_cs_transition(struct kd_cs_state *state)
{
	unsigned long next = state->sequence + 1;
	unsigned long sum = state->sum + next;
	unsigned long branch_mix = state->branch_mix;
	unsigned long rolling;
	unsigned long lane = next & (KD_CS_LANES - 1);

	state->sequence = next;
	state->sum = sum;
	if (next & 1)
		branch_mix += (next << 1) ^ KD_CS_ODD_BIAS;
	else
		branch_mix ^= (next << 2) + KD_CS_EVEN_BIAS;
	state->branch_mix = branch_mix;

	rolling = state->rolling ^ (sum + branch_mix);
	rolling = (rolling << 7) | (rolling >> 57);
	state->rolling = rolling;
	state->lanes[lane] += next + lane + (rolling & 0xffff);
	state->commit = (sum ^ branch_mix ^ rolling ^ state->lanes[0] ^
			 state->lanes[1] ^ state->lanes[2] ^ state->lanes[3]) +
			next * KD_CS_COMMIT_BIAS;
}

static __always_inline void kd_cs_step(enum kd_cs_state_id id)
{
	kd_cs_transition(&kd_cs_states[id]);
	kd_cs_completed[id]++;
}
