/* Optional userspace provenance follows existing compiler and upload actions.
 * These files neither acknowledge kernel bytes nor retain a provider reference.
 * Every observation helper preserves errno and leaves production results alone. */
#define KD_PROVENANCE_LIMIT 64U

struct provenance_compile {
	unsigned int compile_attempt_id;
	char manifest_sha256[65];
};

struct provenance_upload {
	bool selected;
	int payload_fd;
	const char *error;
	unsigned long accepted_length;
	uint64_t final_write_end_ns;
	struct kd_recv_pkt packet;
	struct kd_exe_info entry;
	struct provenance_compile compiler;
	bool cache_hit;
	char directory[PATH_MAX];
};

static struct {
	bool ready;
	char root[PATH_MAX];
	char session_id[80];
	unsigned long entry;
	unsigned int compiler_attempts;
	unsigned int uploads;
} provenance;
static struct provenance_compile provenance_current;

static bool provenance_path(char *path, size_t size, const char *format, ...)
{
	va_list args;
	int length;

	va_start(args, format);
	length = vsnprintf(path, size, format, args);
	va_end(args);
	return length >= 0 && (size_t)length < size;
}

static bool provenance_json(const char *path, const char *format, ...)
{
	va_list args, counted;
	char partial[PATH_MAX];
	int descriptor, expected, written;
	bool complete;

	if (!provenance_path(partial, sizeof(partial), "%s.partial", path))
		return false;
	descriptor = open(partial, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
	if (descriptor < 0)
		return false;
	va_start(args, format);
	va_copy(counted, args);
	expected = vsnprintf(NULL, 0, format, counted);
	va_end(counted);
	written = vdprintf(descriptor, format, args);
	va_end(args);
	complete = expected >= 0 && written == expected;
	if (fsync(descriptor))
		complete = false;
	if (close(descriptor))
		complete = false;
	/* link publishes a complete file atomically and refuses an existing final
	 * name. Failed output stays at its exclusive partial path for inspection. */
	if (!complete || link(partial, path))
		return false;
	(void)unlink(partial);
	return true;
}

static bool provenance_text(const char *path, char *buffer, size_t size)
{
	int descriptor = open(path, O_RDONLY | O_CLOEXEC);
	ssize_t length;
	bool complete;

	if (descriptor < 0)
		return false;
	do {
		length = read(descriptor, buffer, size - 1);
	} while (length < 0 && errno == EINTR);
	complete = length > 0 && (size_t)length < size - 1;
	if (close(descriptor))
		complete = false;
	if (!complete)
		return false;
	buffer[length] = 0;
	return true;
}

static bool provenance_start_ticks(unsigned long long *ticks)
{
	char buffer[4096], *cursor, *end;
	int field;

	if (!provenance_text("/proc/self/stat", buffer, sizeof(buffer)))
		return false;
	cursor = strrchr(buffer, ')');
	if (!cursor || cursor[1] != ' ')
		return false;
	cursor += 2;
	for (field = 3; field < 22; field++) {
		cursor = strchr(cursor, ' ');
		if (!cursor)
			return false;
		cursor++;
	}
	errno = 0;
	*ticks = strtoull(cursor, &end, 10);
	return !errno && end != cursor && (*end == ' ' || *end == '\n') && *ticks;
}

static void provenance_start(int descriptor)
{
	int saved_errno = errno, flags, descriptor_flags;
	const char *directory = getenv("KD_PROVENANCE_DIR");
	const char *selected = getenv("KD_PROVENANCE_ENTRY");
	char boot_id[80], path[PATH_MAX], *end;
	unsigned long long ticks;
	struct stat identity;
	unsigned long entry;
	bool valid = false;

	if (!directory && !selected)
		goto out;
	if (!directory || directory[0] != '/' || !selected || !*selected)
		goto unavailable;
	errno = 0;
	entry = strtoul(selected, &end, 0);
	if (errno || *end || !entry || strlen(directory) >= sizeof(provenance.root))
		goto unavailable;
	if (!provenance_start_ticks(&ticks) ||
	    !provenance_text("/proc/sys/kernel/random/boot_id", boot_id, sizeof(boot_id)))
		goto unavailable;
	boot_id[strcspn(boot_id, "\n")] = 0;
	if (strlen(boot_id) != 36 || strspn(boot_id, "0123456789abcdef-") != 36)
		goto unavailable;
	flags = fcntl(descriptor, F_GETFL);
	descriptor_flags = fcntl(descriptor, F_GETFD);
	if (flags < 0 || descriptor_flags < 0 || fstat(descriptor, &identity))
		goto unavailable;
	if (descriptor_flags & FD_CLOEXEC)
		flags |= O_CLOEXEC;
	if (!provenance_path(path, sizeof(path), "%s/session.json", directory) ||
	    mkdir(directory, 0700))
		goto unavailable;
	snprintf(provenance.session_id, sizeof(provenance.session_id), "%ld-%llu",
		 (long)getpid(), ticks);
	valid = provenance_json(path,
		"{\"schema\":1,\"session_id\":\"%s\",\"boot_id\":\"%s\","
		"\"daemon\":{\"pid\":%ld,\"start_ticks\":%llu,\"fd\":%d,"
		"\"device\":%ju,\"inode\":%ju,\"rdev\":%ju,\"flags\":%d},\"entry\":%lu}\n",
		provenance.session_id, boot_id, (long)getpid(), ticks, descriptor,
		(uintmax_t)identity.st_dev, (uintmax_t)identity.st_ino,
		(uintmax_t)identity.st_rdev, flags, entry);
	if (!valid)
		goto unavailable;
	strcpy(provenance.root, directory);
	provenance.entry = entry;
	provenance.ready = true;
	goto out;
unavailable:
	fprintf(stderr, "daemon: optional provenance session unavailable\n");
out:
	errno = saved_errno;
}

static bool provenance_selected(const struct kd_exe_info *entry)
{
	return provenance.ready && entry->RIP == provenance.entry &&
		entry->lock_kind == KD_EXE_LOCK_MUTEX &&
		entry->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
}

static struct provenance_compile provenance_compile_begin(const struct kd_exe_info *entry)
{
	int saved_errno = errno;
	struct provenance_compile result = { 0 };
	char directory[PATH_MAX], path[PATH_MAX];
	unsigned int attempt;

	if (!provenance_selected(entry) ||
	    provenance.compiler_attempts >= KD_PROVENANCE_LIMIT)
		goto out;
	attempt = ++provenance.compiler_attempts;
	if (!provenance_path(directory, sizeof(directory), "%s/compile-%u",
			     provenance.root, attempt) || mkdir(directory, 0700) ||
	    !provenance_path(path, sizeof(path), "%s/context.json", directory))
		goto out;
	if (!provenance_json(path,
		"{\"schema\":1,\"session_id\":\"%s\",\"compile_attempt_id\":%u,"
		"\"entry\":{\"pid\":%d,\"tgid\":%d,\"entry\":%lu,\"lock_kind\":%d,"
		"\"entry_abi\":%u,\"base_generation\":%lu,\"status\":%d,"
		"\"target\":%lu,\"jump_from\":%lu}}\n",
		provenance.session_id, attempt, entry->pid, entry->tgid, entry->RIP,
		entry->lock_kind, entry->entry_abi, entry->generation, entry->status_code,
		entry->tgt_addr, entry->jump_from))
		goto out;
	result.compile_attempt_id = attempt;
out:
	errno = saved_errno;
	return result;
}

static void provenance_compile_child(const struct provenance_compile *compiler)
{
	int saved_errno = errno;
	char directory[PATH_MAX];

	/* A cached or failed context must never inherit an earlier attempt path. */
	unsetenv("KD_PROVENANCE_ATTEMPT_DIR");
	if (compiler->compile_attempt_id &&
	    provenance_path(directory, sizeof(directory), "%s/compile-%u",
			    provenance.root, compiler->compile_attempt_id))
		(void)setenv("KD_PROVENANCE_ATTEMPT_DIR", directory, 1);
	errno = saved_errno;
}

static void provenance_compile_end(struct provenance_compile *compiler)
{
	int saved_errno = errno;
	char path[PATH_MAX], digest[68];

	if (!compiler->compile_attempt_id ||
	    !provenance_path(path, sizeof(path), "%s/compile-%u/manifest.sha256",
			    provenance.root, compiler->compile_attempt_id) ||
	    !provenance_text(path, digest, sizeof(digest)) || strlen(digest) != 65 ||
	    digest[64] != '\n' || strspn(digest, "0123456789abcdef") != 64)
		goto out;
	memcpy(compiler->manifest_sha256, digest, 64);
	compiler->manifest_sha256[64] = 0;
out:
	errno = saved_errno;
}

static void provenance_upload_begin(struct provenance_upload *upload,
	const struct kd_exe_info *entry, const struct kd_recv_pkt *packet, bool cache_hit)
{
	int saved_errno = errno;
	char path[PATH_MAX], manifest[68] = "null";

	upload->payload_fd = -1;
	if (!provenance_selected(entry) || provenance.uploads >= KD_PROVENANCE_LIMIT)
		goto out;
	provenance.uploads++;
	upload->selected = true;
	upload->packet = *packet;
	upload->entry = *entry;
	upload->compiler = provenance_current;
	upload->cache_hit = cache_hit;
	if (upload->compiler.manifest_sha256[0])
		snprintf(manifest, sizeof(manifest), "\"%s\"", upload->compiler.manifest_sha256);
	else
		upload->error = "compile_manifest_unavailable";
	if (!provenance_path(upload->directory, sizeof(upload->directory), "%s/upload-%lu",
			     provenance.root, packet->upload_id) || mkdir(upload->directory, 0700)) {
		upload->selected = false;
		goto out;
	}
	if (!provenance_path(path, sizeof(path), "%s/context.json", upload->directory) ||
	    !provenance_json(path,
		"{\"schema\":1,\"session_id\":\"%s\",\"upload_id\":%lu,"
		"\"compile_attempt_id\":%u,\"manifest_sha256\":%s,\"cache_hit\":%s,"
		"\"entry\":{\"pid\":%d,\"tgid\":%d,\"entry\":%lu,\"lock_kind\":%d,\"entry_abi\":%u},"
		"\"base_generation\":%lu,\"protocol\":%u,\"requirements\":%u,\"image_length\":%lu}\n",
		provenance.session_id, packet->upload_id, upload->compiler.compile_attempt_id,
		manifest, cache_hit ? "true" : "false", entry->pid, entry->tgid, entry->RIP,
		entry->lock_kind, entry->entry_abi, packet->base_generation, packet->version,
		packet->requirements, packet->image_length))
		upload->error = "upload_context_unavailable";
	if (provenance_path(path, sizeof(path), "%s/payload.bin", upload->directory))
		upload->payload_fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
	if (upload->payload_fd < 0)
		upload->error = "payload_open_failed";
out:
	errno = saved_errno;
}

/* Called immediately after the existing final full write, before mirror I/O. */
static void provenance_upload_time(struct provenance_upload *upload)
{
	int saved_errno = errno;
	struct timespec now;

	if (!upload->selected)
		goto out;
	if (clock_gettime(CLOCK_MONOTONIC, &now) || now.tv_sec < 0 || now.tv_nsec < 0 ||
	    now.tv_nsec >= 1000000000L ||
	    (uint64_t)now.tv_sec > (UINT64_MAX - (uint64_t)now.tv_nsec) / 1000000000) {
		upload->error = "final_write_clock_failed";
		goto out;
	}
	upload->final_write_end_ns = (uint64_t)now.tv_sec * 1000000000 + now.tv_nsec;
out:
	errno = saved_errno;
}

static void provenance_upload_chunk(struct provenance_upload *upload,
	const unsigned char *payload, size_t length)
{
	int saved_errno = errno;
	size_t copied = 0;

	if (!upload->selected)
		goto out;
	upload->accepted_length += length;
	/* The caller still owns this exact write buffer until the next fread. */
	while (upload->payload_fd >= 0 && copied < length) {
		ssize_t count = write(upload->payload_fd, payload + copied, length - copied);

		if (count < 0 && errno == EINTR)
			continue;
		if (count <= 0) {
			upload->error = "payload_write_failed";
			(void)close(upload->payload_fd);
			upload->payload_fd = -1;
			break;
		}
		copied += (size_t)count;
	}
out:
	errno = saved_errno;
}

static void provenance_upload_end(struct provenance_upload *upload, bool complete)
{
	int saved_errno = errno;
	char path[PATH_MAX], manifest[68] = "null", error[80] = "null";
	const struct kd_recv_pkt *packet = &upload->packet;
	const struct kd_exe_info *entry = &upload->entry;

	if (!upload->selected)
		goto out;
	if (upload->payload_fd >= 0) {
		if (fsync(upload->payload_fd))
			upload->error = "payload_flush_failed";
		if (close(upload->payload_fd))
			upload->error = "payload_close_failed";
		upload->payload_fd = -1;
	}
	if (!complete)
		upload->error = "upload_incomplete";
	else if (upload->accepted_length != packet->image_length)
		upload->error = "accepted_length_mismatch";
	else if (!upload->final_write_end_ns)
		upload->error = "final_write_clock_failed";
	if (upload->compiler.manifest_sha256[0])
		snprintf(manifest, sizeof(manifest), "\"%s\"", upload->compiler.manifest_sha256);
	if (upload->error)
		snprintf(error, sizeof(error), "\"%s\"", upload->error);
	/* Recorder completion is separate from byte-to-manifest verification. The
	 * consumer must hash this mirror against the referenced compiler manifest. */
	if (provenance_path(path, sizeof(path), "%s/receipt.json", upload->directory))
		(void)provenance_json(path,
			"{\"schema\":1,\"session_id\":\"%s\",\"upload_id\":%lu,"
			"\"compile_attempt_id\":%u,\"manifest_sha256\":%s,\"cache_hit\":%s,"
			"\"entry\":{\"pid\":%d,\"tgid\":%d,\"entry\":%lu,\"lock_kind\":%d,\"entry_abi\":%u},"
			"\"base_generation\":%lu,\"protocol\":%u,\"requirements\":%u,\"image_length\":%lu,"
			"\"accepted_length\":%lu,\"upload_complete\":%s,\"evidence_complete\":%s,"
			"\"final_write_end_ns\":%" PRIu64 ",\"payload\":\"upload-%lu/payload.bin\",\"error\":%s}\n",
			provenance.session_id, packet->upload_id, upload->compiler.compile_attempt_id,
			manifest, upload->cache_hit ? "true" : "false", entry->pid, entry->tgid,
			entry->RIP, entry->lock_kind, entry->entry_abi, packet->base_generation,
			packet->version, packet->requirements, packet->image_length, upload->accepted_length,
			complete ? "true" : "false", complete && !upload->error ? "true" : "false",
			upload->final_write_end_ns, packet->upload_id, error);
out:
	errno = saved_errno;
}
