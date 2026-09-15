/*
 * After-drain integrity oracle: recompute every active per-lock payload.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static unsigned int kd_cs_validate(unsigned long *operations,
				   unsigned long *completed,
				   unsigned int *active_states)
{
	unsigned int failures = 0;
	unsigned int id;

	*operations = 0;
	*completed = 0;
	*active_states = 0;
	for (id = 0; id < KD_CS_STATE_COUNT; id++) {
		struct kd_cs_state expected = {};
		struct kd_cs_state *state = &kd_cs_states[id];
		unsigned long count = READ_ONCE(state->sequence);
		unsigned long done = READ_ONCE(kd_cs_completed[id]);
		unsigned long i;

		*operations += count;
		*completed += done;
		if (count != done) {
			failures++;
			pr_err("kd_cs operation mismatch: state=%s operations=%lu completed=%lu\n",
			       kd_cs_state_names[id], count, done);
		}
		if (!count)
			continue;
		(*active_states)++;
		if (count > KD_CS_VERIFY_LIMIT) {
			failures++;
			pr_err("kd_cs integrity limit: state=%s operations=%lu limit=%lu\n",
			       kd_cs_state_names[id], count,
			       KD_CS_VERIFY_LIMIT);
			continue;
		}

		for (i = 0; i < count; i++)
			kd_cs_transition(&expected);
		if (memcmp(state, &expected, sizeof(expected))) {
			failures++;
			pr_err("kd_cs integrity mismatch: state=%s operations=%lu commit=%lx/%lx\n",
			       kd_cs_state_names[id], count, state->commit,
			       expected.commit);
		}
	}

	return failures;
}
