/* Mutex image lifetime is session-wide. Only private, never-published uploads
 * can return a block to the bounded pool. The publication gate also serializes
 * generation-scoped miss metadata; it is never held across copying or JIT. */
struct kd_jit_image *kd_image_alloc(void)
{
	unsigned long publish_flags;
	struct kd_jit_image *image = NULL;
	unsigned int i;

	publish_flags = kd_code_block_gate_lock();
	if (kd_code_block_free)
		for (i = 0; i < KD_CODE_BLOCK_POOL; i++)
			if (!kd_images[i].code) {
				image = &kd_images[i];
				image->code = kd_code_block_pool[--kd_code_block_free];
				image->entry = NULL;
				break;
			}
	kd_code_block_gate_unlock(publish_flags);
	return image;
}

void kd_image_discard(struct kd_jit_image *image)
{
	unsigned long publish_flags;
	if (!image)
		return;
	publish_flags = kd_code_block_gate_lock();
	BUG_ON(image->entry || !image->code || kd_code_block_free >= KD_CODE_BLOCK_POOL);
	kd_code_block_pool[kd_code_block_free++] = image->code;
	image->code = NULL;
	kd_code_block_gate_unlock(publish_flags);
}

const struct kd_jit_image *kd_image_current(const struct kd_exe_info *entry)
{
	if (!entry || entry->lock_kind != KD_EXE_LOCK_MUTEX)
		return NULL;
	return smp_load_acquire(&kd_published_images[entry - kd_exes]);
}

int kd_image_publish(struct kd_exe_info *entry, struct kd_jit_image *image,
		     unsigned long base_generation)
{
	unsigned long publish_flags;
	int ret = 0;

	publish_flags = kd_code_block_gate_lock();
	if (!kd_source_is_open() || entry->status_code == KD_EXE_NATIVE_ONLY)
		ret = -ESHUTDOWN;
	else if (entry->generation != base_generation || base_generation == ~0UL)
		ret = -ESTALE;
	else {
		image->entry = entry;
		image->generation = base_generation + 1;
		entry->code_block = image->code; /* status snapshot, never dispatch authority */
		entry->requirements = image->requirements;
		entry->generation = image->generation;
		entry->tgt_addr = 0;
		entry->jump_from = 0;
		smp_store_release(&kd_published_images[entry - kd_exes], image);
		smp_store_release(&entry->status_code, KD_EXE_NORMAL);
	}
	kd_code_block_gate_unlock(publish_flags);
	return ret;
}

void kd_image_report(struct kd_exe_info *entry, const struct kd_jit_image *image,
		     int status, unsigned long target, unsigned long from)
{
	unsigned long publish_flags;
	publish_flags = kd_code_block_gate_lock();
	if (entry->lock_kind != KD_EXE_LOCK_MUTEX ||
	    (image && image == kd_image_current(entry))) {
		if (entry->status_code != KD_EXE_NATIVE_ONLY) {
			entry->tgt_addr = target;
			entry->jump_from = from;
			kd_exe_publish_status(entry, status);
		}
	}
	kd_code_block_gate_unlock(publish_flags);
}

void kd_exe_snapshot(const struct kd_exe_info *entry, struct kd_exe_info *snapshot)
{
	unsigned long publish_flags;
	publish_flags = kd_code_block_gate_lock();
	memcpy(snapshot, entry, sizeof(*snapshot));
	kd_code_block_gate_unlock(publish_flags);
}
