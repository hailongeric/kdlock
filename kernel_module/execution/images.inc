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
				image->immutable = 1;
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
	if (!entry)
		return NULL;
	return smp_load_acquire(&kd_published_images[entry - kd_exes]);
}

int kd_image_validate_address_guards(const struct kd_jit_image *image)
{
	const struct kd_address_guard_site *sites;
	unsigned char opcode[16];
	unsigned int count, i, j;
	int ret;

	if (!(image->requirements & KD_IMAGE_REQUIRE_ADDRESS_GUARD))
		return 0;
	sites = kd_image_guard_sites(image, &count);
	if (!sites)
		return -EPROTO;
	for (i = 0; i < count; i++) {
		if (!kd_image_guard_site_valid(&sites[i]))
			return -EPROTO;
		for (j = 0; j < i; j++)
			if (sites[j].ip == sites[i].ip)
				return -EPROTO;
		/* Publication owns the device writer lease, not a running frame.
		 * Pin reviewed text under OPEN admission before publishing its PC. */
		ret = kd_source_pin_root(sites[i].ip);
		if (ret)
			return ret;
		if (copy_from_kernel_nofault(opcode, (void *)sites[i].ip,
					     sites[i].length) ||
		    memcmp(opcode, sites[i].opcode, sites[i].length))
			return -EILSEQ;
	}
	return 0;
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

/* Preserve historical ordinary spin uploads, but serialize their final
 * publication against the same permanent ban as immutable images. */
int kd_image_publish_mutable(struct kd_exe_info *entry, void *code,
			     unsigned long length)
{
	unsigned long publish_flags = kd_code_block_gate_lock();
	struct kd_jit_image *image =
		(struct kd_jit_image *)kd_image_current(entry);
	int ret;

	if (entry->status_code == KD_EXE_NATIVE_ONLY || !kd_source_is_open())
		ret = -ESHUTDOWN;
	else if (!image || image->immutable || image->code != code)
		ret = -ESTALE;
	else {
		image->length = length;
		kd_exe_publish_status(entry, KD_EXE_NORMAL);
		ret = 0;
	}
	kd_code_block_gate_unlock(publish_flags);
	return ret;
}

void kd_image_report(struct kd_exe_info *entry, const struct kd_jit_image *image,
		     int status, unsigned long target, unsigned long from)
{
	unsigned long publish_flags;
	publish_flags = kd_code_block_gate_lock();
	if ((!kd_image_current(entry) && entry->lock_kind != KD_EXE_LOCK_MUTEX) ||
	    (image && image == kd_image_current(entry))) {
		if (entry->status_code != KD_EXE_NATIVE_ONLY) {
			entry->tgt_addr = target;
			entry->jump_from = from;
			kd_exe_publish_status(entry, status);
		}
	}
	kd_code_block_gate_unlock(publish_flags);
}

/* A runtime marker is a decision about the source entry, not a stale miss
 * requesting another image. Serialize with the publisher's status check and
 * NORMAL store so no upload can reopen the entry after this decision. Bound
 * images stay resident and already admitted frames retain their source leases. */
void kd_image_disable(struct kd_exe_info *entry)
{
	unsigned long publish_flags = kd_code_block_gate_lock();

	kd_exe_publish_status(entry, KD_EXE_NATIVE_ONLY);
	kd_code_block_gate_unlock(publish_flags);
}

void kd_exe_snapshot(const struct kd_exe_info *entry, struct kd_exe_info *snapshot)
{
	unsigned long publish_flags;
	publish_flags = kd_code_block_gate_lock();
	memcpy(snapshot, entry, sizeof(*snapshot));
	kd_code_block_gate_unlock(publish_flags);
}
