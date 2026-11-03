/* SPDX-License-Identifier: GPL-2.0 */
/* Family resolution happens only on E, between completed transactions. */
static const char *kd_reached_kind(unsigned int kind)
{
	return kind == KD_FAMILY_ARTIFACT_KD_CALL ? "control" :
		kind == KD_FAMILY_ARTIFACT_NATIVE_CALL ? "primitive" : "memory";
}

static void kd_reached_service_trace(struct kd_exec_continuation *cont,
	const char *event)
{
	const struct kd_reached_session *session = cont->reached;
	const struct kd_family_artifact *artifact = &session->artifact;

	if (unlikely(READ_ONCE(kd_service_trace)))
		pr_info("kd_reached event=%s origin=%d executor=%d identity=%px generation=%llu family_generation=%llu artifact_sequence=%llu kind=%s ip=%lx target=%lx sp=%lx\n",
			event, cont->request->logical_origin->pid, current->pid,
			cont->request->identity, (unsigned long long)cont->generation,
			(unsigned long long)session->family.generation,
			(unsigned long long)artifact->sequence, kd_reached_kind(artifact->kind),
			artifact->source_ip, session->service_target, session->service_sp);
}

static void kd_reached_hold(struct kd_exec_continuation *cont, unsigned int kind,
	unsigned long ip, const u8 *bytes, unsigned int length)
{
	struct kd_reached_session *session = cont->reached;

	BUG_ON(session->artifact.reference.held || !cont->reached_artifact_sequence ||
		kd_family_artifact_get(&session->artifact, &session->authority,
			kind, ip, bytes, length, cont->reached_artifact_sequence));
	session->service_target = cont->packet->ip;
	session->service_sp = cont->packet->sp;
	if (kind == KD_FAMILY_ARTIFACT_KD_CALL)
		atomic64_inc(&kd_reached_controls);
	else if (kind == KD_FAMILY_ARTIFACT_NATIVE_CALL)
		atomic64_inc(&kd_reached_primitives);
	else
		atomic64_inc(&kd_reached_memory);
	kd_reached_service_trace(cont, "service");
}

void kd_exe_reached_ack(struct kd_exec_frame *frame)
{
	struct kd_exec_continuation *cont = kd_exec_frame_continuation(frame);
	struct kd_reached_session *session = cont->reached;

	if (!session->artifact.reference.held) {
		BUG_ON(cont->reached_artifact_sequence);
		return;
	}
	BUG_ON(!kd_reached_frame_ready(frame) ||
		!kd_family_artifact_valid(&session->artifact, &session->authority,
			cont->reached_artifact_sequence));
	/* The GS instruction stopped cold decoding before its effect. Its one
	 * retired source instruction is accounted only after the actual ACK. */
	if (session->artifact.kind == KD_FAMILY_ARTIFACT_MEMORY) {
		BUG_ON(!session->state.budget);
		--session->state.budget;
		atomic64_inc(&kd_reached_instructions);
	}
	kd_reached_service_trace(cont, "resume");
	BUG_ON(kd_family_artifact_put(&session->artifact));
	cont->reached_artifact_sequence = 0;
}

static void kd_reached_cache_note(struct kd_exec_continuation *cont,
	unsigned long ip, const u8 *bytes, unsigned int length)
{
	struct kd_reached_session *session = cont->reached;
	unsigned int index;
	bool repeated = false;

	if (kd_family_cache_find(&session->authority, ip, bytes, length))
		atomic64_inc(&kd_reached_cache_hits);
	else {
		atomic64_inc(&kd_reached_cache_misses);
		for (index = 0; index < session->recent_count; ++index)
			if (session->recent_pc[index] == ip) {
				repeated = true;
				break;
			}
		/* Mutable history is only an admission hint for optional immutable
		 * cache storage. It never grants source or packet custody. */
		if (!repeated) {
			session->recent_pc[session->recent_cursor] = ip;
			session->recent_cursor = (session->recent_cursor + 1) %
				ARRAY_SIZE(session->recent_pc);
			if (session->recent_count < ARRAY_SIZE(session->recent_pc))
				++session->recent_count;
		}
		if (repeated && !kd_family_cache_publish(&session->authority, ip, bytes, length))
			atomic64_inc(&kd_reached_cache_full);
	}
}

static int kd_exe_reached_dispatch(struct kd_exec_frame *frame)
{
	struct kd_exec_continuation *cont = kd_exec_frame_continuation(frame);
	struct kd_reached_session *session = cont->reached;
	struct kd_reached_state *state = &session->state;
	unsigned int step;

	if (!kd_reached_frame_ready(frame) || !session->initialized ||
	    !kd_family_ref_valid(&session->authority) ||
	    state->owner_identity != cont->request->identity ||
	    state->owner_generation != cont->generation ||
	    session->artifact.reference.held || cont->reached_artifact_sequence)
		return KD_EXE_RUN_ERROR;
	for (step = 0; step < KD_REACHED_SEGMENT_MAX; ++step) {
		enum kd_reached_result result = kd_reached_step(state);
		struct kd_reached_event *event = &state->event;
		int status;

		if (result == KD_REACHED_BUDGET)
			return KD_EXE_RUN_YIELD;
		if (result == KD_REACHED_NEXT || result == KD_REACHED_EDGE) {
			frame->executed = true;
			kd_exec_frame_save_continuation(frame, state->regs);
			atomic64_inc(&kd_reached_instructions);
			kd_reached_cache_note(cont, event->source_ip, event->bytes, event->length);
			if (result != KD_REACHED_EDGE ||
			    (event->edge != KD_REACHED_CALL && event->edge != KD_REACHED_JUMP))
				continue;
			cont->reached_artifact_sequence = event->sequence;
			status = kd_jit_service_control(frame, state->regs);
			if (status == KD_EXE_KNOWN_SERVICE || status == KD_EXE_KNOWN_ORIGIN_CALL) {
				kd_reached_hold(cont, status == KD_EXE_KNOWN_SERVICE ?
					KD_FAMILY_ARTIFACT_KD_CALL : KD_FAMILY_ARTIFACT_NATIVE_CALL,
					event->source_ip, event->bytes, event->length);
				return status == KD_EXE_KNOWN_SERVICE ?
					KD_EXE_RUN_SERVICE : KD_EXE_RUN_ORIGIN_CALL;
			}
			if (status)
				goto unsupported;
			cont->reached_artifact_sequence = 0;
			/* An ordinary callee or tail is the next reached source PC. */
			continue;
		}
		if (result == KD_REACHED_UNSUPPORTED) {
			cont->reached_artifact_sequence = event->sequence;
			status = kd_exec_cont_memory_prepare_reached(frame);
			if (!status) {
				const struct kd_origin_memory_site *site = cont->origin_memory.site;

				kd_reached_cache_note(cont, site->ip, site->opcode, site->length);
				kd_reached_hold(cont, KD_FAMILY_ARTIFACT_MEMORY,
					site->ip, site->opcode, site->length);
				return KD_EXE_RUN_ORIGIN_MEMORY;
			}
		} else {
			status = result;
		}
unsupported:
		atomic64_inc(&kd_reached_unsupported);
		pr_err("kd_reached unsupported: origin=%d executor=%d generation=%llu ip=%lx sp=%lx result=%u status=%d length=%u bytes=%*ph\n",
			cont->request->logical_origin->pid, current->pid,
			(unsigned long long)cont->generation, cont->packet->ip,
			cont->packet->sp, result, status, event->length,
			event->length, event->bytes);
		return KD_EXE_RUN_ERROR;
	}
	return KD_EXE_RUN_YIELD;
}

int kd_exe_on_reached_entry(struct kd_exec_frame *frame)
{
	struct kd_exec_continuation *cont = frame ? kd_exec_frame_continuation(frame) : NULL;
	struct kd_reached_session *session;

	if (!cont || !cont->reached_active || !(session = cont->reached) ||
	    session->initialized || frame->image || frame->executed ||
	    kd_exe_reached_begin(frame, &session->state, 1UL << 24))
		return KD_EXE_RUN_ERROR;
	session->initialized = true;
	/* Entry witness is distinct from instruction effects and completion. */
	frame->executed = true;
	atomic64_inc(&kd_reached_roots);
	return kd_exe_reached_dispatch(frame);
}
