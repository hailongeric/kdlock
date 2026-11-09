/* Mutex image lifetime is session-wide. Only private, never-published uploads
 * can return a block to the bounded pool. The publication gate also serializes
 * session-bound miss metadata; it is never held across copying or JIT. */
static struct kd_image_learning_state kd_image_learning[KD_MAX_EXE];
static unsigned long kd_image_report_superseded;

void kd_image_learning_reset(void)
{
	memset(kd_image_learning, 0, sizeof(kd_image_learning));
	kd_image_report_superseded = 0;
}

unsigned int kd_exe_slot_index(const struct kd_exe_info *entry)
{
	return entry - kd_exes;
}

static bool kd_image_miss_kind(unsigned int kind)
{
	return kind == KD_EXE_CALL_MISS || kind == KD_EXE_IJ_MISS;
}

static bool kd_image_miss_matches(const struct kd_learning_record *record,
	unsigned int kind, unsigned long target, unsigned long from)
{
	return record->sequence && record->kind == kind &&
		record->target == target && record->from == from;
}

/* The scalar registry retains the latest admitted unresolved tuple for legacy
 * readers. Sequence IDs survive publication; carried rows keep the generation
 * that actually reported them, rather than claiming execution by a newer image. */
static void kd_image_pending_tuple(struct kd_exe_info *entry,
	const struct kd_image_learning_state *learning)
{
	const struct kd_learning_record *latest = NULL;
	unsigned int i;

	for (i = 0; i < KD_LEARNING_CAPACITY; ++i)
		if (learning->records[i].sequence &&
		    (!latest || learning->records[i].sequence > latest->sequence))
			latest = &learning->records[i];
	if (latest) {
		entry->tgt_addr = latest->target;
		entry->jump_from = latest->from;
		kd_exe_publish_status(entry, latest->kind);
	}
}

static bool kd_image_miss_acknowledged(const struct kd_learning_record *record,
	const struct kd_image_learning_state *learning, unsigned long base_generation,
	const struct kd_image_learning_receipt *receipt)
{
	if (!receipt || !receipt->valid || receipt->generation != base_generation ||
	    receipt->revision > learning->revision || receipt->batch > 1 ||
	    !record->sequence || record->sequence > receipt->revision)
		return false;
	return receipt->batch || kd_image_miss_matches(record, receipt->kind,
		receipt->target, receipt->from);
}

static bool kd_image_batch_has_survivors(const struct kd_image_learning_state *learning,
	unsigned long base_generation, const struct kd_image_learning_receipt *receipt)
{
	unsigned int i;

	for (i = 0; i < KD_LEARNING_CAPACITY; ++i)
		if (learning->records[i].sequence &&
		    !kd_image_miss_acknowledged(&learning->records[i], learning,
			base_generation, receipt))
			return true;
	return false;
}

static void kd_image_ack_misses(struct kd_image_learning_state *learning,
	unsigned long base_generation, const struct kd_image_learning_receipt *receipt)
{
	unsigned int i;

	for (i = 0; i < KD_LEARNING_CAPACITY; ++i) {
		struct kd_learning_record *record = &learning->records[i];

		if (!kd_image_miss_acknowledged(record, learning, base_generation, receipt))
			continue;
		/* Only successful publication calls this helper. Clearing the occupied
		 * marker transfers this exact slot back to report admission. */
		record->sequence = 0;
		learning->count--;
	}
}

static struct kd_jit_image *kd_image_alloc_pool(bool near_text)
{
	unsigned long publish_flags;
	struct kd_jit_image *image = NULL;
	unsigned int i;
	int *free = near_text ? &kd_near_block_free : &kd_code_block_free;
	void **pool = near_text ? kd_near_block_pool : kd_code_block_pool;

	publish_flags = kd_code_block_gate_lock();
	if (*free)
		for (i = 0; i < KD_CODE_BLOCK_POOL; i++)
			if (!kd_images[i].code) {
				image = &kd_images[i];
				image->code = pool[--*free];
				image->entry = NULL;
				image->immutable = 1;
				image->near_text = near_text;
				break;
			}
	kd_code_block_gate_unlock(publish_flags);
	return image;
}

struct kd_jit_image *kd_image_alloc(void)
{
	return kd_image_alloc_pool(false);
}

struct kd_jit_image *kd_image_alloc_direct(void)
{
	return kd_image_alloc_pool(true);
}

int kd_image_direct_available(void)
{
	/* Allocations survive the entire provider session, even when the free
	 * count reaches zero. Capability does not promise remaining capacity. */
	return kd_near_block_allocations[0] != NULL;
}

void kd_image_discard(struct kd_jit_image *image)
{
	unsigned long publish_flags;
	int *free;
	void **pool;
	if (!image)
		return;
	free = image->near_text ? &kd_near_block_free : &kd_code_block_free;
	pool = image->near_text ? kd_near_block_pool : kd_code_block_pool;
	publish_flags = kd_code_block_gate_lock();
	BUG_ON(image->entry || !image->code || *free >= KD_CODE_BLOCK_POOL);
	pool[(*free)++] = image->code;
	image->code = NULL;
	kd_code_block_gate_unlock(publish_flags);
}

/* The daemon supplies private generated CALL slots. Resolve only manifest
 * service identities, pin their source continuations, then patch signed rel32
 * displacements before publication. No helper or source CALL bytes are read. */
int kd_image_relocate_direct(struct kd_jit_image *image)
{
	const struct kd_direct_call_site *sites;
	unsigned int count, i, j, seen = 0;
	unsigned long target, next, directory;
	unsigned char *code = image->code;
	int displacement, ret;

	if (!(image->requirements & KD_IMAGE_REQUIRE_DIRECT_STRINGS))
		return 0;
	if (!image->near_text || !image->immutable || image->entry ||
	    image->entry_abi != KD_ENTRY_ABI_SPIN_CLOBBER_V1 ||
	    !kd_image_requirements_valid(KD_EXE_LOCK_SPIN, image->entry_abi,
					image->requirements))
		return -EPROTO;
	sites = kd_image_direct_sites(image, &count);
	if (!sites)
		return -EPROTO;
	directory = (const unsigned char *)sites - code;
	/* Validate every generated slot before writing any relocation. Duplicate
	 * or overlapping slots would otherwise turn a later row into code data. */
	for (i = 0; i < count; i++) {
		unsigned int requirement;

		if (sites[i].service_id == KD_HOSTCALL_STRCMP)
			requirement = KD_IMAGE_REQUIRE_STRING_SERVICES;
		else if (sites[i].service_id == KD_HOSTCALL_STRSCPY_PAD)
			requirement = KD_IMAGE_REQUIRE_STRING_WRITE;
		else
			return -EPROTO;
		if (!(image->requirements & requirement) || !sites[i].return_ip ||
		    sites[i].call_offset < KD_IMAGE_HEADER_SIZE ||
		    directory < 5 || sites[i].call_offset > directory - 5 ||
		    code[sites[i].call_offset] != 0xe8 ||
		    get_unaligned_le32(code + sites[i].call_offset + 1))
			return -EPROTO;
		for (j = 0; j < i; j++)
			if (sites[i].call_offset < sites[j].call_offset + 5 &&
			    sites[j].call_offset < sites[i].call_offset + 5)
				return -EPROTO;
		seen |= requirement;
	}
	if (seen != (image->requirements &
		     (KD_IMAGE_REQUIRE_STRING_SERVICES | KD_IMAGE_REQUIRE_STRING_WRITE)))
		return -EPROTO;
	for (i = 0; i < count; i++) {
		target = 0;
		for (j = 0; j < ARRAY_SIZE(kd_hostcalls); j++)
			if (kd_hostcalls[j].id == sites[i].service_id)
				target = kd_hostcalls[j].addr;
		if (!target)
			return -ENOENT;
		next = (unsigned long)code + sites[i].call_offset + 5;
		/* Unsigned subtraction avoids signed overflow for malformed inputs. */
		if (target >= next ? target - next > 0x7fffffffUL :
				     next - target > 0x80000000UL)
			return -ERANGE;
		ret = kd_source_pin_root(target);
		if (!ret)
			ret = kd_source_pin_root(sites[i].return_ip);
		if (ret)
			return ret;
		displacement = (int)(target - next);
		memcpy(code + sites[i].call_offset + 1, &displacement, sizeof(displacement));
		KD_PR_INFO("JIT direct relocation: code=%px length=%lu offset=%u service=%u target=%lx return=%lx rel32=%d\n",
			   code, image->length, sites[i].call_offset, sites[i].service_id,
			   target, sites[i].return_ip, displacement);
	}
	return 0;
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

int kd_image_validate_origin_sites(const struct kd_jit_image *image)
{
	const struct kd_origin_site *sites;
	unsigned int count, i, j;

	if (!(image->requirements & KD_IMAGE_REQUIRE_ORIGIN_INSN))
		return 0;
	sites = kd_image_origin_sites(image, &count);
	if (!sites || image->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1)
		return -EPROTO;
	for (i = 0; i < count; i++) {
		unsigned char opcode[8];
		int ret;

		if (!kd_image_origin_site_valid(image, &sites[i]))
			return -EPROTO;
		for (j = 0; j < i; j++)
			if (sites[j].ip == sites[i].ip)
				return -EPROTO;
		ret = kd_source_pin_root(sites[i].ip);
		if (!ret)
			ret = kd_source_pin_root(sites[i].next_ip);
		if (ret)
			return ret;
		if (copy_from_kernel_nofault(opcode, (void *)sites[i].ip, sites[i].length) ||
		    memcmp(opcode, sites[i].opcode, sites[i].length))
			return -EILSEQ;
	}
	return 0;
}

int kd_image_publish_learned(struct kd_exe_info *entry, struct kd_jit_image *image,
	unsigned long base_generation, const struct kd_image_learning_receipt *receipt)
{
	unsigned long publish_flags;
	struct kd_image_learning_state *learning = &kd_image_learning[kd_exe_slot_index(entry)];
	bool pending, acknowledged, had_records;
	int ret = 0;

	publish_flags = kd_code_block_gate_lock();
	if (!kd_source_is_open() || entry->status_code == KD_EXE_NATIVE_ONLY)
		ret = -ESHUTDOWN;
	else if (entry->generation != base_generation || base_generation == ~0UL)
		ret = -ESTALE;
	else if (receipt && receipt->batch && kd_image_current(entry) &&
		 (kd_image_current(entry)->requirements & KD_IMAGE_REQUIRE_RETAINED_MISS) &&
		 !(image->requirements & KD_IMAGE_REQUIRE_RETAINED_MISS) &&
		 kd_image_batch_has_survivors(learning, base_generation, receipt))
		ret = -EPROTO;
	else {
		pending = entry->lock_kind == KD_EXE_LOCK_MUTEX &&
			entry->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 &&
			kd_image_current(entry) && kd_image_current(entry)->immutable &&
			(kd_image_current(entry)->requirements & KD_IMAGE_REQUIRE_RETAINED_MISS) &&
			(entry->status_code == KD_EXE_CALL_MISS || entry->status_code == KD_EXE_IJ_MISS);
		acknowledged = receipt && receipt->valid &&
			!receipt->batch &&
			receipt->generation == base_generation &&
			receipt->revision == learning->revision &&
				receipt->kind == (unsigned int)entry->status_code &&
			receipt->target == entry->tgt_addr && receipt->from == entry->jump_from;
		had_records = learning->count != 0;
		kd_image_ack_misses(learning, base_generation, receipt);
		image->entry = entry;
		image->generation = base_generation + 1;
		entry->code_block = image->code; /* status snapshot, never dispatch authority */
		entry->requirements = image->requirements;
		entry->generation = image->generation;
		if (!learning->count && (had_records || !pending || acknowledged)) {
			entry->tgt_addr = 0;
			entry->jump_from = 0;
		}
		if (image->requirements & KD_IMAGE_REQUIRE_DIRECT_STRINGS)
			KD_PR_INFO("JIT direct published: entry=%lx generation=%lu code=%px length=%lu requirements=%u\n",
				   entry->RIP, image->generation, image->code, image->length,
				   image->requirements);
		smp_store_release(&kd_published_images[entry - kd_exes], image);
		/* Publication consumes only the frozen obligations. Reports admitted
		 * during compilation remain eligible input for the next generation. */
		if (learning->count)
			kd_image_pending_tuple(entry, learning);
		else if (had_records || !pending || acknowledged)
			smp_store_release(&entry->status_code, KD_EXE_NORMAL);
	}
	kd_code_block_gate_unlock(publish_flags);
	return ret;
}

int kd_image_publish(struct kd_exe_info *entry, struct kd_jit_image *image,
		     unsigned long base_generation)
{
	return kd_image_publish_learned(entry, image, base_generation, NULL);
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
			if (image && image->immutable && entry->lock_kind == KD_EXE_LOCK_MUTEX &&
			    entry->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 &&
			    (image->requirements & KD_IMAGE_REQUIRE_RETAINED_MISS) &&
			    kd_image_miss_kind(status)) {
				struct kd_image_learning_state *learning =
					&kd_image_learning[kd_exe_slot_index(entry)];
				struct kd_learning_record *available = NULL;
				unsigned int i;

				for (i = 0; i < KD_LEARNING_CAPACITY; ++i) {
					struct kd_learning_record *record = &learning->records[i];

					if (kd_image_miss_matches(record, status, target, from))
						goto out;
					if (!record->sequence && !available)
						available = record;
				}
				/* Rejected report events are observable, not an exact number of
				 * distinct lost tuples. No occupied row is ever evicted. Sequence
				 * exhaustion also refuses admission instead of reusing an ID. */
				if (!available || learning->revision == ~0UL) {
					if (learning->overflow_report_events != ~0ULL)
						learning->overflow_report_events++;
					goto out;
				}
				available->kind = status;
				available->reserved = 0;
				available->from = from;
				available->target = target;
				available->admitted_generation = image->generation;
				available->sequence = ++learning->revision;
				learning->count++;
				/* This compatibility counter tracks replacement of the scalar
				 * registry view; its earlier row is still retained in the ledger. */
				if (entry->status_code == KD_EXE_CALL_MISS ||
				    entry->status_code == KD_EXE_IJ_MISS)
					kd_image_report_superseded++;
			}
			entry->tgt_addr = target;
			entry->jump_from = from;
			kd_exe_publish_status(entry, status);
		}
	}
out:
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

void kd_exe_snapshot_learning(const struct kd_exe_info *entry,
	struct kd_exe_info *snapshot, struct kd_image_learning_receipt *receipt)
{
	unsigned long publish_flags;
	publish_flags = kd_code_block_gate_lock();
	memcpy(snapshot, entry, sizeof(*snapshot));
	if (receipt)
		*receipt = (struct kd_image_learning_receipt) {
			.valid = 1, .generation = entry->generation,
			.revision = kd_image_learning[kd_exe_slot_index(entry)].revision,
			.kind = kd_image_miss_kind(entry->status_code) ? entry->status_code : 0,
			.target = entry->tgt_addr, .from = entry->jump_from,
		};
	kd_code_block_gate_unlock(publish_flags);
}

void kd_exe_snapshot_misses(const struct kd_exe_info *entry,
	struct kd_exe_info *snapshot, struct kd_learning_record records[KD_LEARNING_CAPACITY],
	unsigned int *count, unsigned long long *overflow_report_events,
	struct kd_image_learning_receipt *receipt)
{
	const struct kd_image_learning_state *learning =
		&kd_image_learning[kd_exe_slot_index(entry)];
	unsigned long publish_flags = kd_code_block_gate_lock();
	unsigned int i, used = 0;

	memcpy(snapshot, entry, sizeof(*snapshot));
	for (i = 0; i < KD_LEARNING_CAPACITY; ++i) {
		const struct kd_learning_record *record = &learning->records[i];
		unsigned int position = used;

		if (!record->sequence)
			continue;
		/* Slot reuse need not preserve order. Return one immutable, ascending
		 * sequence view so a cursor never walks a changing live collection. */
		while (position && records[position - 1].sequence > record->sequence) {
			records[position] = records[position - 1];
			position--;
		}
		records[position] = *record;
		used++;
	}
	*count = used;
	*overflow_report_events = learning->overflow_report_events;
	*receipt = (struct kd_image_learning_receipt) {
		.valid = 1, .batch = 1, .generation = entry->generation,
		.revision = learning->revision,
	};
	kd_code_block_gate_unlock(publish_flags);
}

void kd_exe_snapshot(const struct kd_exe_info *entry, struct kd_exe_info *snapshot)
{
	kd_exe_snapshot_learning(entry, snapshot, NULL);
}
