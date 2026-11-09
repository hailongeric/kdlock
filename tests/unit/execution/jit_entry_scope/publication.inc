/* Exercise the full production mismatch branch and immutable publisher under
 * both gate orderings. No source instruction or physical lock API runs here. */
static void *publication_mismatch(void *result)
{
	struct kd_jit_batch_call pending = {0};

	publication_mismatch_actor = true;
	if (publication_order == PUBLISHER_FIRST) {
		publication_thread_call(pthread_mutex_lock(&publication_schedule));
		while (!publication_checked)
			publication_thread_call(pthread_cond_wait(
				&publication_changed, &publication_schedule));
		publication_thread_call(pthread_mutex_unlock(&publication_schedule));
	}
	/* A pending frame already passed its original lookup. Exercise the real
	 * backend mismatch before its pending packet can be consumed or executed. */
	*(int *)result = kd_exe_dispatch(entry, &active.regs, active.entry_ip,
		active.outer_lock_addr, &pending, false, false);
	publication_thread_call(pthread_mutex_lock(&publication_schedule));
	publication_mismatch_finished = true;
	publication_thread_call(pthread_cond_broadcast(&publication_changed));
	publication_thread_call(pthread_mutex_unlock(&publication_schedule));
	return NULL;
}

static void check_mismatch_publication(void)
{
	const enum publication_order orders[] = { PUBLISHER_FIRST, TERMINAL_FIRST };

	for (unsigned int scenario = 0; scenario < ARRAY_SIZE(orders); ++scenario) {
		enum publication_order order = orders[scenario];
		unsigned char old_code[64], replacement_code[64];
		unsigned long stack_before[ARRAY_SIZE(stack)];
		struct kd_learning_record records[KD_LEARNING_CAPACITY];
		struct kd_image_learning_receipt receipt;
		struct kd_image_learning_state saved, *learning;
		struct kd_exe_info snapshot;
		struct kd_exec_frame frame_before;
		struct kd_jit_image old, replacement;
		unsigned long long overflow;
		unsigned int count, slot;
		pthread_t mismatch;
		int dispatch_result = -1, result;

		reset();
		publication_active = true;
		publication_order = PUBLICATION_IDLE;
		publication_gate_announced = false;
		publication_checked = publication_mismatch_waiting =
			publication_mismatch_finished = publication_terminal_locked =
			publication_publisher_waiting = false;
		CHECK(!kd_code_block_gate);
		memset(kd_image_learning, 0, sizeof(kd_image_learning));
		memset(kd_published_images, 0, sizeof(kd_published_images));
		memset(old_code, 0x51, sizeof(old_code));
		memset(replacement_code, 0x62, sizeof(replacement_code));
		entry->lock_kind = KD_EXE_LOCK_MUTEX;
		entry->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
		entry->requirements = KD_IMAGE_REQUIRE_SERVICE_QUEUE |
			KD_IMAGE_REQUIRE_ORIGIN_CALL | KD_IMAGE_REQUIRE_BUDGET_RESUME |
			KD_IMAGE_REQUIRE_RETAINED_MISS;
		entry->generation = 1;
		entry->code_block = old_code;
		old = (struct kd_jit_image) {
			.code = old_code, .length = sizeof(old_code), .generation = 1,
			.requirements = entry->requirements, .entry_abi = entry->entry_abi,
			.entry = entry, .immutable = 1,
		};
		replacement = (struct kd_jit_image) {
			.code = replacement_code, .length = sizeof(replacement_code),
			.requirements = entry->requirements, .entry_abi = entry->entry_abi,
			.immutable = 1,
		};
		slot = kd_exe_slot_index(entry);
		kd_published_images[slot] = &old;
		active.image = &old;
		/* The frame's spin backend deliberately conflicts with this mutex root.
		 * Its exact image, owner ledger and packet must remain untouched. */
		CHECK(!active.mutex_backend && kd_exec_frame_validate(&active));
		memcpy(&frame_before, &active, sizeof(frame_before));
		memcpy(stack_before, stack, sizeof(stack));
		publication_report(entry, &old, KD_EXE_CALL_MISS, 0x2000, 0);
		kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &receipt);
		learning = &kd_image_learning[slot];
		memcpy(&saved, learning, sizeof(saved));
		CHECK(count == 1 && !overflow && receipt.valid && receipt.batch);
		CHECK(snapshot.generation == 1 && records[0].admitted_generation == 1);
		publication_order = order;
		publication_thread_call(pthread_create(&mismatch, NULL,
			publication_mismatch, &dispatch_result));
		if (order == TERMINAL_FIRST) {
			publication_thread_call(pthread_mutex_lock(&publication_schedule));
			while (!publication_terminal_locked && !publication_mismatch_finished)
				publication_thread_call(pthread_cond_wait(
					&publication_changed, &publication_schedule));
			publication_thread_call(pthread_mutex_unlock(&publication_schedule));
		}
		result = kd_image_publish_learned(entry, &replacement, 1, &receipt);
		publication_thread_call(pthread_join(mismatch, NULL));
		publication_order = PUBLICATION_IDLE;
		CHECK(dispatch_result == KD_EXE_NO_RUN && warnings == 1);
		CHECK(!calls && !known_calls && !errors && !source_calls);
		CHECK(!memcmp(&active, &frame_before, sizeof(active)));
		CHECK(!memcmp(stack, stack_before, sizeof(stack)));
		CHECK(entry->status_code == KD_EXE_NATIVE_ONLY && !kd_code_block_gate);
		CHECK(old.entry == entry && old.generation == 1 && old.code == old_code);
		for (unsigned int i = 0; i < sizeof(old_code); ++i)
			CHECK(old_code[i] == 0x51);
		if (order == TERMINAL_FIRST) {
			CHECK(publication_terminal_locked && publication_publisher_waiting);
			CHECK(result == -ESHUTDOWN && !replacement.entry);
			CHECK(entry->generation == 1 && kd_image_current(entry) == &old);
			CHECK(!memcmp(learning, &saved, sizeof(saved)));
		} else {
			CHECK(publication_checked && publication_mismatch_waiting);
			CHECK(result == 0 && replacement.entry == entry);
			CHECK(entry->generation == 2 && kd_image_current(entry) == &replacement);
			CHECK(!learning->count && learning->revision == saved.revision);
			CHECK(!learning->records[0].sequence);
			/* This ACK completed before the later terminal decision. That
			 * decision remains sticky for subsequent publication attempts. */
			CHECK(kd_image_publish_learned(entry, &old, 2, &receipt) == -ESHUTDOWN);
			CHECK(entry->status_code == KD_EXE_NATIVE_ONLY &&
			      kd_image_current(entry) == &replacement && !learning->count);
		}
		publication_active = false;
	}
}
