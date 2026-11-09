/* Exercise the production finite-view controls and upload decisions. Copy and
 * executable-memory primitives come from the registry fixture; no kernel code
 * is loaded and no generated instruction is executed. */
static struct kd_learning_snapshot learning_request(struct kd_exe_info *entry)
{
	return (struct kd_learning_snapshot) {
		.version = KD_LEARNING_API_VERSION,
		.header_size = KD_LEARNING_SNAPSHOT_HEADER_SIZE,
		.record_size = KD_LEARNING_RECORD_SIZE,
		.capacity = KD_LEARNING_CAPACITY,
		.root = { .slot = KD_LEARNING_SLOT_LOOKUP, .pid = entry->pid,
			.rip = entry->RIP, .lock_kind = entry->lock_kind,
			.entry_abi = entry->entry_abi },
		.base_generation = entry->generation,
	};
}

static struct kd_learning_bind learning_binding(const struct kd_learning_snapshot *view,
	unsigned long id)
{
	return (struct kd_learning_bind) {
		.version = KD_LEARNING_API_VERSION, .size = KD_LEARNING_BIND_SIZE,
		.token = view->token, .root = view->root,
		.base_generation = view->base_generation, .revision = view->revision,
		.upload_id = id,
	};
}

static void learning_cancel(struct file *channel, const struct kd_learning_snapshot *view)
{
	struct kd_learning_cancel request = {
		.version = KD_LEARNING_API_VERSION, .size = KD_LEARNING_CANCEL_SIZE,
		.token = view->token, .root = view->root,
		.base_generation = view->base_generation,
	};
	CHECK(kd_learning_ioctl(channel, KD_LEARNING_CANCEL, (unsigned long)&request) == 0);
}

static void check_learning_control(void)
{
	struct kd_image_upload writer = {0}, other_writer = {0};
	struct file channel = { .private_data = &writer };
	struct file other = { .private_data = &other_writer }, readonly = {0};
	struct kd_exe_info *entry;
	struct kd_learning_snapshot view, repeated, second;
	struct kd_learning_bind bind;
	struct {
		struct kd_recv_pkt head;
		unsigned char data[KD_IMAGE_SERVICE_HEADER_SIZE];
	} packet = {0};
	const unsigned int requirements = KD_IMAGE_REQUIRE_SERVICE_QUEUE |
		KD_IMAGE_REQUIRE_ORIGIN_CALL | KD_IMAGE_REQUIRE_BUDGET_RESUME |
		KD_IMAGE_REQUIRE_RETAINED_MISS;
	unsigned char original[KD_IMAGE_SERVICE_HEADER_SIZE];
	unsigned int slot;
	int available;

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	kd_exe_add_abi(0, key(0), KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	entry = kd_get_exe(0, key(0));
	slot = kd_exe_slot_index(entry);
	packet.head = (struct kd_recv_pkt) {
		.status_code = KD_EXE_NORMAL, .RIP = entry->RIP,
		.version = KD_IMAGE_PROTOCOL_SERVICE_QUEUE, .entry_abi = entry->entry_abi,
		.requirements = requirements, .image_length = sizeof(packet.data), .upload_id = 1,
	};
	memcpy(packet.data + 9, "KDWB002", 7);
	memcpy(packet.data + 25, "KDWC002", 7);
	memcpy(packet.data + 41, "KDAB", 4);
	packet.data[45] = entry->entry_abi;
	packet.data[46] = KD_IMAGE_PROTOCOL_SERVICE_QUEUE;
	packet.data[47] = requirements & 0xffU;
	memcpy(packet.data + KD_IMAGE_FULL_REQUIREMENTS_OFFSET, &requirements, sizeof(requirements));
	memcpy(original, packet.data, sizeof(original));
	CHECK(kd_dev_write_locked(&writer, (char *)&packet, sizeof(packet)) == (ssize_t)sizeof(packet));
	const struct kd_jit_image *old = kd_image_current(entry);
	CHECK(old && old->generation == 1);
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x1111, 0);
	kd_image_report(entry, old, KD_EXE_IJ_MISS, 0x2222, 0x3333);
	view = learning_request(entry);
	CHECK(kd_learning_ioctl(&readonly, KD_LEARNING_SNAPSHOT, (unsigned long)&view) == -EBADF);
	/* Failure on the outward copy grants no receipt, even if its token exists
	 * internally. Neither a copy nor a cancellation acknowledges a record. */
	fail_copy = copy_calls + 2;
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_SNAPSHOT, (unsigned long)&view) == -EFAULT);
	fail_copy = 0;
	CHECK(!writer.learning_view_valid && kd_image_learning[slot].count == 2);
	bind = learning_binding(&writer.learning_snapshot, 10);
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_BIND, (unsigned long)&bind) == -ESTALE);
	view = learning_request(entry);
	/* Records are output only; callers cannot supply compiler history through
	 * the request's record bytes, including bytes left from a previous view. */
	memset(view.records, 0xa5, sizeof(view.records));
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_SNAPSHOT, (unsigned long)&view) == 0);
	CHECK(view.count == 2 && view.token && view.base_generation == 1);
	CHECK(view.records[0].target == 0x1111 && view.records[1].from == 0x3333);
	CHECK(!view.records[2].sequence);
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x4444, 0);
	repeated = view;
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_SNAPSHOT, (unsigned long)&repeated) == 0);
	CHECK(!memcmp(&view, &repeated, sizeof(view)) && kd_image_learning[slot].count == 3);
	bind = learning_binding(&view, 11);
	CHECK(kd_learning_ioctl(&other, KD_LEARNING_BIND, (unsigned long)&bind) == -ESTALE);
	bind.revision++;
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_BIND, (unsigned long)&bind) == -ESTALE);
	bind = learning_binding(&view, 11);
	bind.root.entry_abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_BIND, (unsigned long)&bind) == -ESTALE);
	second = learning_request(entry);
	CHECK(kd_learning_ioctl(&other, KD_LEARNING_SNAPSHOT, (unsigned long)&second) == 0);
	CHECK(second.count == 3 && second.token != view.token);
	learning_cancel(&other, &second);
	CHECK(kd_image_learning[slot].count == 3 && kd_image_current(entry) == old);
	bind = learning_binding(&view, 11);
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_BIND, (unsigned long)&bind) == 0);
	packet.head.base_generation = 1;
	packet.head.upload_id = 12;
	CHECK(kd_dev_write_locked(&writer, (char *)&packet, sizeof(packet)) == -ESTALE);
	packet.head.upload_id = 11;
	packet.head.status_code = KD_EXE_UNINIT;
	available = kd_code_block_free;
	CHECK(kd_dev_write_locked(&writer, (char *)&packet, sizeof(packet.head) + 32) > 0);
	CHECK(kd_code_block_free == available - 1 && kd_image_current(entry) == old);
	packet.head.offset = 32;
	packet.head.base_generation = 2;
	packet.head.status_code = KD_EXE_NORMAL;
	CHECK(kd_dev_write_locked(&writer, (char *)&packet, sizeof(packet.head) + 32) == -ESTALE);
	learning_cancel(&channel, &view);
	CHECK(!writer.image && !writer.covered && kd_code_block_free == available);
	CHECK(kd_image_learning[slot].count == 3 && !memcmp(old->code, original, sizeof(original)));
	view = learning_request(entry);
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_SNAPSHOT, (unsigned long)&view) == 0);
	bind = learning_binding(&view, 21);
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_BIND, (unsigned long)&bind) == 0);
	packet.head.offset = 0;
	packet.head.base_generation = 1;
	packet.head.upload_id = 21;
	packet.head.status_code = KD_EXE_UNINIT;
	CHECK(kd_dev_write_locked(&writer, (char *)&packet, sizeof(packet.head) + 32) > 0);
	/* Restarting the same frozen view discards only its private partial
	 * staging block, then sends the same input-derived bytes under a new ID. */
	bind.upload_id = 22;
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_BIND, (unsigned long)&bind) == 0);
	CHECK(!writer.image && !writer.covered && kd_code_block_free == available);
	CHECK(kd_image_learning[slot].count == 3 && kd_image_current(entry) == old);
	packet.head.upload_id = 22;
	CHECK(kd_dev_write_locked(&writer, (char *)&packet, sizeof(packet.head) + 32) > 0);
	kd_image_report(entry, old, KD_EXE_IJ_MISS, 0x5555, 0x6666);
	packet.head.offset = 32;
	packet.head.status_code = KD_EXE_NORMAL;
	memcpy(packet.data, original + 32, 32);
	CHECK(kd_dev_write_locked(&writer, (char *)&packet, sizeof(packet.head) + 32) > 0);
	CHECK(entry->generation == 2 && kd_image_learning[slot].count == 1);
	CHECK(!writer.learning_view_valid && !writer.learning_bound && !writer.image);
	CHECK(entry->status_code == KD_EXE_IJ_MISS && entry->tgt_addr == 0x5555);
	CHECK(!memcmp(old->code, original, sizeof(original)));
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x7777, 0);
	CHECK(kd_image_learning[slot].count == 1);
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_BIND, (unsigned long)&bind) == -ESTALE);
	view = learning_request(entry);
	view.base_generation = 1;
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_SNAPSHOT, (unsigned long)&view) == -ESTALE);
	view = learning_request(entry);
	source_open = false;
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_SNAPSHOT, (unsigned long)&view) == -ESHUTDOWN);
	source_open = true;
	kd_image_disable(entry);
	CHECK(kd_learning_ioctl(&channel, KD_LEARNING_SNAPSHOT, (unsigned long)&view) == -ESHUTDOWN);
	CHECK(!writer.learning_view_valid && kd_image_learning[slot].count == 1);
	kd_exe_exit();
}
