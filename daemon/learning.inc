/* One finite kernel snapshot becomes one frozen full-root compiler input.
 * Cumulative histories belong to this held provider/session only. A failed
 * upload keeps its original files; another root never replaces that attempt. */
struct learning_edge {
	unsigned long from, target;
	unsigned int kind;
};

static struct {
	bool enabled, active, compiled, canceled;
	int result;
	struct kd_exe_info entry;
	struct kd_learning_snapshot snapshot;
	struct provenance_compile compiler;
	char directory[512];
	char session[512];
	char scope_tag[160];
} learning;

static int learning_ioctl(unsigned long command, void *packet)
{
	int result;

	do {
		result = ioctl(sys_fd, command, packet);
	} while (result < 0 && errno == EINTR);
	return result;
}

static int learning_start(void)
{
	struct kd_jit_caps caps = { .version = ~0U, .features = ~0U };
	struct stat identity;
	unsigned long long ticks;
	char boot[80];

	learning.enabled = false;
	if (learning_ioctl(KD_JIT_CAPS, &caps))
		return errno == ENOTTY ? 0 : -1;
	if (!caps.version || caps.version > KD_JIT_CAPS_VERSION)
		return -1;
	if (caps.version < 22 || !(caps.features & KD_JIT_CAP_LEARNING_BATCH))
		return 0;
	if (!(caps.features & KD_JIT_CAP_MUTEX_IMAGES) ||
	    !(caps.features & KD_JIT_CAP_MUTEX_EXCLUSIVE) ||
	    fstat(sys_fd, &identity) || !provenance_start_ticks(&ticks) ||
	    !provenance_text("/proc/sys/kernel/random/boot_id", boot, sizeof(boot)))
		return -1;
	boot[strcspn(boot, "\n")] = 0;
	if (!provenance_path(learning.scope_tag, sizeof(learning.scope_tag),
		"session-%s-%ld-%llu", boot, (long)getpid(), ticks))
		return -1;
	if (!provenance_path(learning.session, sizeof(learning.session),
		"{\"schema\":1,\"boot_id\":\"%s\",\"daemon_pid\":%ld,"
		"\"daemon_start_ticks\":%llu,\"device\":%ju,\"inode\":%ju,\"rdev\":%ju}\n",
		boot, (long)getpid(), ticks, (uintmax_t)identity.st_dev,
		(uintmax_t)identity.st_ino, (uintmax_t)identity.st_rdev))
		return -1;
	learning.enabled = true;
	return 0;
}

static int learning_cancel(void)
{
	struct kd_learning_cancel cancel = {
		.version = KD_LEARNING_API_VERSION, .size = sizeof(cancel),
		.token = learning.snapshot.token, .root = learning.snapshot.root,
		.base_generation = learning.snapshot.base_generation,
	};

	if (!learning.active || learning.canceled)
		return 0;
	/* A publication may already have consumed this token. ESTALE forgets
	 * only our local attempt; it never cancels a different kernel view. */
	if (learning_ioctl(KD_LEARNING_CANCEL, &cancel) && errno != ESTALE)
		return -1;
	learning.canceled = true;
	return 0;
}

static bool learning_entry_matches(const struct kd_exe_info *a,
				   const struct kd_exe_info *b)
{
	return a->pid == b->pid && a->tgid == b->tgid && a->RIP == b->RIP &&
		a->lock_kind == b->lock_kind && a->entry_abi == b->entry_abi &&
		a->generation == b->generation;
}

static int learning_edge_compare(const void *left, const void *right)
{
	const struct learning_edge *a = left, *b = right;

	if (a->kind != b->kind)
		return a->kind < b->kind ? -1 : 1;
	if (a->from != b->from)
		return a->from < b->from ? -1 : 1;
	return a->target == b->target ? 0 : a->target < b->target ? -1 : 1;
}

static int learning_directories(const char *path)
{
	char prefix[1024];
	struct stat identity;

	if (strlen(path) >= sizeof(prefix))
		return -1;
	strcpy(prefix, path);
	for (char *cursor = prefix; ; cursor++) {
		char saved = *cursor;

		if (saved && saved != '/')
			continue;
		*cursor = 0;
		if (*prefix && ((mkdir(prefix, 0700) && errno != EEXIST) ||
		    lstat(prefix, &identity) || !S_ISDIR(identity.st_mode)))
			return -1;
		*cursor = saved;
		if (!saved)
			return 0;
	}
}

static bool learning_storage_path(char *path, size_t size,
		const struct daemon_config *cfg, const struct kd_exe_info *entry,
		const struct kd_learning_snapshot *snapshot)
{
	char workspace[256];

	workspace_path(workspace, sizeof(workspace), cfg, entry);
	return *learning.scope_tag && provenance_path(path, size,
		"%s/%s/root-%u-pid-%d-tgid-%d-kind-%d-abi-%u", workspace, learning.scope_tag,
		snapshot->root.slot, entry->pid, entry->tgid, entry->lock_kind, entry->entry_abi);
}

static int learning_edge_add(struct learning_edge **edges, size_t *count,
			     unsigned int kind, unsigned long from,
			     unsigned long target)
{
	struct learning_edge *grown;

	if (target < X86_KERNEL_ADDRESS_MIN ||
	    (kind == KD_LEARNING_IJ && from < X86_KERNEL_ADDRESS_MIN) ||
	    (kind == KD_LEARNING_CALL && from) ||
	    (kind != KD_LEARNING_CALL && kind != KD_LEARNING_IJ) ||
	    *count >= SIZE_MAX / sizeof(**edges) - 1)
		return -1;
	grown = realloc(*edges, (*count + 1) * sizeof(**edges));
	if (!grown)
		return -1;
	*edges = grown;
	grown[(*count)++] = (struct learning_edge){ from, target, kind };
	return 0;
}

/* Strict bounded lines retain the existing numeric history grammar. Once a
 * workspace is scoped, both leaves are mandatory even when they are empty. */
static int learning_history_read(const char *path, unsigned int kind,
				struct learning_edge **edges, size_t *count)
{
	FILE *stream = fopen(path, "r");
	char line[128];
	int result = 0;

	if (!stream)
		return -1;
	while (fgets(line, sizeof(line), stream)) {
		unsigned long from = 0, target;
		char *cursor = line, *end;

		if (!strchr(line, '\n') && !feof(stream)) {
			result = -1;
			break;
		}
		errno = 0;
		while (*cursor == ' ' || *cursor == '\t')
			cursor++;
		if (*cursor == '-' || *cursor == '+') {
			result = -1;
			break;
		}
		target = strtoul(cursor, &end, 16);
		if (errno || end == cursor) {
			result = -1;
			break;
		}
		if (kind == KD_LEARNING_IJ) {
			from = target;
			cursor = end;
			while (*cursor == ' ' || *cursor == '\t')
				cursor++;
			if (*cursor == '-' || *cursor == '+') {
				result = -1;
				break;
			}
			errno = 0;
			target = strtoul(cursor, &end, 16);
			if (errno || end == cursor) {
				result = -1;
				break;
			}
		}
		while (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')
			end++;
		if (*end || learning_edge_add(edges, count, kind, from, target)) {
			result = -1;
			break;
		}
	}
	if (ferror(stream))
		result = -1;
	if (fclose(stream))
		result = -1;
	return result;
}

static int learning_history_write(const char *path,
		const struct learning_edge *edges, size_t count, unsigned int kind)
{
	FILE *stream = fopen(path, "wx");
	int result = 0;

	if (!stream)
		return -1;
	for (size_t i = 0; i < count; i++) {
		if (edges[i].kind != kind ||
		    (i && !learning_edge_compare(edges + i - 1, edges + i)))
			continue;
		if ((kind == KD_LEARNING_CALL ?
		     fprintf(stream, "0x%lx\n", edges[i].target) :
		     fprintf(stream, "0x%lx 0x%lx\n", edges[i].from, edges[i].target)) < 0)
			result = -1;
	}
	if (fflush(stream) || fsync(fileno(stream)))
		result = -1;
	if (fclose(stream))
		result = -1;
	return result;
}

static int learning_copy(const char *source, const char *target, bool optional)
{
	unsigned char buffer[8192];
	FILE *input = fopen(source, "rb"), *output;
	size_t count;
	int result = 0;

	if (!input)
		return optional && errno == ENOENT ? 0 : -1;
	output = fopen(target, "wb");
	if (!output) {
		fclose(input);
		return -1;
	}
	while ((count = fread(buffer, 1, sizeof(buffer), input)))
		if (fwrite(buffer, 1, count, output) != count) {
			result = -1;
			break;
		}
	if (ferror(input) || fflush(output) || fsync(fileno(output)))
		result = -1;
	if (fclose(input))
		result = -1;
	if (fclose(output))
		result = -1;
	return result;
}

static bool learning_snapshot_valid(const struct kd_learning_snapshot *snapshot,
				    const struct kd_exe_info *entry)
{
	if (snapshot->version != KD_LEARNING_API_VERSION ||
	    snapshot->header_size != offsetof(struct kd_learning_snapshot, records) ||
	    snapshot->record_size != sizeof(snapshot->records[0]) ||
	    snapshot->capacity != KD_LEARNING_CAPACITY ||
	    snapshot->root.slot >= KD_MAX_EXE || snapshot->root.pid != entry->pid ||
	    snapshot->root.rip != entry->RIP ||
	    snapshot->root.lock_kind != (unsigned int)entry->lock_kind ||
	    snapshot->root.entry_abi != entry->entry_abi ||
	    snapshot->base_generation != entry->generation || !snapshot->token ||
	    snapshot->count > KD_LEARNING_CAPACITY ||
	    snapshot->flags & ~KD_LEARNING_OVERFLOW ||
	    (!snapshot->count && (entry->status_code != KD_EXE_UNINIT || entry->generation)))
		return false;
	for (size_t i = 0; i < ARRAY_SIZE(snapshot->reserved); i++)
		if (snapshot->reserved[i])
			return false;
	for (unsigned int i = 0; i < snapshot->count; i++) {
		const struct kd_learning_record *record = snapshot->records + i;

		if (!record->sequence || record->admitted_generation > entry->generation ||
		    record->target < X86_KERNEL_ADDRESS_MIN || record->reserved ||
		    (record->kind != KD_LEARNING_CALL && record->kind != KD_LEARNING_IJ) ||
		    (record->kind == KD_LEARNING_CALL ? record->from != 0 :
		     record->from < X86_KERNEL_ADDRESS_MIN))
			return false;
		for (unsigned int j = 0; j < i; j++)
			if (snapshot->records[j].sequence == record->sequence)
				return false;
	}
	return true;
}

static int learning_prepare(const struct daemon_config *cfg)
{
	const char *names[] = { "callee_table.txt", "ij_table.txt" };
	char workspace[512], path[1024], target[1024], receipt[1024], observed[1024], expected[1024];
	struct learning_edge *edges = NULL;
	size_t count = 0;
	FILE *stream;
	int result = -1;

	if (!learning_storage_path(workspace, sizeof(workspace), cfg,
		&learning.entry, &learning.snapshot) || learning_directories(workspace))
		goto out;
	if (!provenance_path(expected, sizeof(expected),
		"{\"session\":%s,\"pid\":%d,\"tgid\":%d,\"entry\":%lu,\"lock_kind\":%d,\"entry_abi\":%u}\n",
		learning.session, learning.entry.pid, learning.entry.tgid, learning.entry.RIP,
		learning.entry.lock_kind, learning.entry.entry_abi))
		goto out;
	if (!provenance_path(path, sizeof(path), "%s/asm", workspace) ||
	    (mkdir(path, 0700) && errno != EEXIST) ||
	    !provenance_path(receipt, sizeof(receipt), "%s/learning-session.json", workspace))
		goto out;
	stream = fopen(receipt, "r");
	if (stream) {
		size_t length = fread(observed, 1, sizeof(observed) - 1, stream);
		bool match = !ferror(stream) && feof(stream);

		observed[length] = 0;
		if (fclose(stream) || !match || strcmp(observed, expected))
			goto out;
	} else {
		/* A new daemon cannot reconstruct already acknowledged inputs from
		 * the pending ledger. Only a genuinely cold root starts empty. */
		if (errno != ENOENT || learning.entry.generation)
			goto out;
		for (size_t i = 0; i < ARRAY_SIZE(names); i++) {
			if (!provenance_path(path, sizeof(path), "%s/asm/%s", workspace, names[i]) ||
			    !access(path, F_OK) || errno != ENOENT)
				goto out;
		}
		/* Establish both empty inputs before publishing the session scope.
		 * A partial setup has no receipt and cannot adopt surviving leaves. */
		for (size_t i = 0; i < ARRAY_SIZE(names); i++) {
			if (!provenance_path(path, sizeof(path), "%s/asm/%s", workspace, names[i]) ||
			    learning_history_write(path, NULL, 0,
				 i ? KD_LEARNING_IJ : KD_LEARNING_CALL))
				goto out;
		}
		stream = fopen(receipt, "wx");
		if (!stream)
			goto out;
		if (fputs(expected, stream) < 0) {
			fclose(stream);
			goto out;
		}
		if (fclose(stream))
			goto out;
	}
	for (size_t i = 0; i < ARRAY_SIZE(names); i++) {
		if (!provenance_path(path, sizeof(path), "%s/asm/%s", workspace, names[i]) ||
		    learning_history_read(path, i ? KD_LEARNING_IJ : KD_LEARNING_CALL, &edges, &count))
			goto out;
	}
	for (unsigned int i = 0; i < learning.snapshot.count; i++) {
		const struct kd_learning_record *record = learning.snapshot.records + i;

		if (learning_edge_add(&edges, &count, record->kind, record->from, record->target))
			goto out;
	}
	if (count > 1)
		qsort(edges, count, sizeof(*edges), learning_edge_compare);
	/* Invalid or missing cumulative input creates no apparent compile
	 * attempt. Real attempts remain intact once their frozen files begin. */
	if (!provenance_path(learning.directory, sizeof(learning.directory),
			     "%s/batch-%llu", workspace,
			     (unsigned long long)learning.snapshot.token) ||
	    mkdir(learning.directory, 0700) ||
	    !provenance_path(path, sizeof(path), "%s/asm", learning.directory) || mkdir(path, 0700))
		goto out;
	for (size_t i = 0; i < ARRAY_SIZE(names); i++) {
		if (!provenance_path(path, sizeof(path), "%s/asm/%s", learning.directory, names[i]) ||
		    learning_history_write(path, edges, count, i ? KD_LEARNING_IJ : KD_LEARNING_CALL) ||
		    !provenance_path(target, sizeof(target), "%s/asm/%s.batch-%llu", workspace,
			 names[i], (unsigned long long)learning.snapshot.token) ||
		    learning_copy(path, target, false) ||
		    !provenance_path(path, sizeof(path), "%s/asm/%s", workspace, names[i]) ||
		    rename(target, path))
			goto out;
	}
	if (!provenance_path(path, sizeof(path), "%s/learning-snapshot.bin", learning.directory))
		goto out;
	stream = fopen(path, "wx");
	if (!stream)
		goto out;
	if (fwrite(&learning.snapshot, 1, sizeof(learning.snapshot), stream) != sizeof(learning.snapshot)) {
		fclose(stream);
		goto out;
	}
	if (fclose(stream))
		goto out;
	result = 0;
out:
	free(edges);
	return result;
}

static int learning_export(const struct daemon_config *cfg)
{
	const char *names[] = { "jit.S", "jit.bin", "jit.o", "bin.txt",
		"callee_table.txt", "ij_table.txt" };
	char workspace[256], source[1024], target[1024], temporary[1024];

	workspace_path(workspace, sizeof(workspace), cfg, &learning.entry);
	if (!provenance_path(target, sizeof(target), "%s/asm", workspace) ||
	    learning_directories(target))
		return -1;
	for (size_t i = 0; i < ARRAY_SIZE(names); i++) {
		if (!provenance_path(source, sizeof(source), "%s/asm/%s", learning.directory, names[i]) ||
		    !provenance_path(target, sizeof(target), "%s/asm/%s", workspace, names[i]) ||
		    !provenance_path(temporary, sizeof(temporary), "%s.batch-%llu", target,
			 (unsigned long long)learning.snapshot.token))
			return -1;
		if ((i == 2 || i == 3) && access(source, F_OK) && errno == ENOENT)
			continue;
		if (learning_copy(source, temporary, false) || rename(temporary, target))
			return -1;
	}
	return 0;
}

/* Return one only while a failed upload retains this exact frozen attempt.
 * There is one view per writer description, so no other root may replace it. */
static int learning_step(const struct daemon_config *cfg,
			 const struct kd_exe_info *entry)
{
	char script[PATH_MAX], binary[1024];

	if (!learning.active) {
		struct kd_learning_snapshot snapshot = {
			.version = KD_LEARNING_API_VERSION,
			.header_size = offsetof(struct kd_learning_snapshot, records),
			.record_size = sizeof(snapshot.records[0]), .capacity = KD_LEARNING_CAPACITY,
			.root = { .slot = KD_LEARNING_SLOT_LOOKUP, .pid = entry->pid,
				.rip = entry->RIP, .lock_kind = entry->lock_kind,
				.entry_abi = entry->entry_abi }, .base_generation = entry->generation,
		};

		if (learning_ioctl(KD_LEARNING_SNAPSHOT, &snapshot))
			return 0;
		learning.entry = *entry;
		learning.snapshot = snapshot;
		learning.active = true;
		learning.compiled = learning.canceled = false;
		if (!learning_snapshot_valid(&snapshot, entry) || learning_prepare(cfg)) {
			fprintf(stderr,
				"daemon: batch input unavailable: pid=%d tgid=%d entry=0x%lx slot=%u generation=%lu token=%llu\n",
				entry->pid, entry->tgid, entry->RIP, snapshot.root.slot,
				entry->generation, (unsigned long long)snapshot.token);
			goto cancel;
		}
		if (!realpath("../disassem/disassem.py", script))
			goto cancel;
		provenance_learning = &learning.snapshot;
		learning.result = compile_at(cfg, entry, learning.directory, script);
		provenance_learning = NULL;
		learning.compiler = provenance_current;
		if (learning.result < 0)
			goto cancel;
		learning.compiled = true;
	}
	if (!learning.compiled || !learning_entry_matches(entry, &learning.entry) ||
	    entry->status_code == KD_EXE_NATIVE_ONLY)
		goto cancel;
	provenance_current = learning.compiler;
	if (learning.result == TRANSLATOR_NATIVE_ONLY) {
		if (learning_cancel())
			return 1;
		if (write_native_only(&learning.entry))
			return 1;
		learning.active = false;
		return 0;
	}
	if (learning_export(cfg) ||
	    !provenance_path(binary, sizeof(binary), "%s/asm/jit.bin", learning.directory) ||
	    write_sys_at(cfg, &learning.entry, false, binary, &learning.snapshot)) {
		if (errno == ESTALE || errno == ESHUTDOWN)
			goto cancel;
		return 1;
	}
	learning.active = false;
	return 0;
cancel:
	if (learning_cancel())
		return 1;
	learning.active = false;
	return 0;
}
