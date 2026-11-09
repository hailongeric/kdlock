/* Device reads and checked image publication, including ABI identity.
 * Uses the existing session fd; never reopens a provider after failure. */
static int write_native_only(const struct kd_exe_info *exe)
{
	const struct kd_recv_pkt pkt = {
		.status_code = KD_EXE_NATIVE_ONLY,
		.pid = exe->pid,
		.RIP = exe->RIP,
		.offset = 0,
		.version = KD_IMAGE_PROTOCOL,
		.entry_abi = exe->entry_abi,
		.base_generation = exe->generation,
	};
	ssize_t written;

	do {
		written = write(sys_fd, &pkt, sizeof(pkt));
	} while (written < 0 && errno == EINTR);
	if (written != sizeof(pkt)) {
		fprintf(stderr,
			"daemon: native-only status write failed: %zd\n",
			written);
		return -1;
	}
	return 0;
}

static ssize_t read_sys(void *buffer, size_t size)
{
	ssize_t len;

	do {
		len = read(sys_fd, buffer, size);
	} while (len < 0 && errno == EINTR);
	if (len < 0) {
		int error = errno;

		perror("read /dev/kd_dev");
		return -error;
	}
	return len;
}

/* Transfer bounded payload chunks on the original device. Final status marks
 * readiness, not protection for an executor of a previous in-place image. */
static int write_sys_at(const struct daemon_config *cfg,
		const struct kd_exe_info *exe, bool cache_hit, const char *jit_path,
		const struct kd_learning_snapshot *snapshot)
{
	unsigned char buffer[sizeof(struct kd_recv_pkt) + MAX_PAYLOAD];
	struct provenance_upload evidence = { 0 };
	static unsigned long upload_sequence;
	struct kd_recv_pkt pkt = {
		.version = KD_IMAGE_PROTOCOL,
		.entry_abi = exe->entry_abi,
		.base_generation = exe->generation,
	};
	size_t remaining;
	long image_size;
	FILE *fp;

	(void)cfg;
	fp = fopen(jit_path, "rb");
	if (!fp) {
		fprintf(stderr, "daemon: failed to open %s: %s\n", jit_path,
			strerror(errno));
		return -1;
	}
	if (fseek(fp, 0, SEEK_END)) {
		fprintf(stderr, "daemon: failed to seek %s\n", jit_path);
		fclose(fp);
		return -1;
	}
	image_size = ftell(fp);
	if (image_size <= 0 || (unsigned long)image_size > KD_CODE_BLOCK_SIZE ||
	    fseek(fp, 0, SEEK_SET)) {
		fprintf(stderr, "daemon: invalid JIT image size for %s\n",
			jit_path);
		fclose(fp);
		return -1;
	}
	{
		unsigned char header[KD_IMAGE_SERVICE_HEADER_SIZE];
		size_t header_size = (unsigned long)image_size < sizeof(header) ?
			(size_t)image_size : sizeof(header);
		unsigned int requirements;
		bool directory;

		if (fread(header, 1, header_size, fp) != header_size ||
		    header_size < KD_IMAGE_HEADER_SIZE) {
			fclose(fp);
			return -1;
		}
		directory = !memcmp(header + 9, "KDWB002", 7) &&
		            !memcmp(header + 25, "KDWC002", 7) &&
		            !memcmp(header + 41, "KDAB", 4);
		if (!kd_entry_abi_valid(exe->lock_kind, exe->entry_abi) ||
		    !directory || header[45] != exe->entry_abi ||
		    !kd_image_header_requirements(header, header_size, &requirements) ||
		    !kd_image_requirements_valid(exe->lock_kind, exe->entry_abi,
					requirements) ||
		    fseek(fp, 0, SEEK_SET)) {
			fprintf(stderr, "daemon: JIT entry ABI mismatch\n");
			fclose(fp);
			return -1;
		}
		pkt.requirements = requirements;
		pkt.version = header[KD_IMAGE_VERSION_OFFSET];
	}
	remaining = (size_t)image_size;
	pkt.image_length = remaining;
	pkt.upload_id = ++upload_sequence;

	pkt.pid = exe->pid;
	pkt.RIP = exe->RIP;
	pkt.offset = 0;
	if (snapshot) {
		struct kd_learning_bind binding = {
			.version = KD_LEARNING_API_VERSION,
			.size = sizeof(binding), .token = snapshot->token,
			.root = snapshot->root,
			.base_generation = snapshot->base_generation,
			.revision = snapshot->revision, .upload_id = pkt.upload_id,
		};
		int result;

		do {
			result = ioctl(sys_fd, KD_LEARNING_BIND, &binding);
		} while (result < 0 && errno == EINTR);
		if (result) {
			int error = errno;

			fclose(fp);
			errno = error;
			return -1;
		}
	}
	provenance_learning = snapshot;
	provenance_upload_begin(&evidence, exe, &pkt, cache_hit);
	provenance_learning = NULL;

	while (remaining) {
		size_t chunk = remaining < MAX_PAYLOAD ? remaining :
							 MAX_PAYLOAD;
		size_t packet_size = sizeof(pkt) + chunk;
		ssize_t written;

		if (fread(buffer + sizeof(pkt), 1, chunk, fp) != chunk) {
			fprintf(stderr, "daemon: failed to read %s\n",
				jit_path);
			goto error;
		}
		pkt.status_code = remaining == chunk ? KD_EXE_NORMAL :
						       KD_EXE_UNINIT;
		memcpy(buffer, &pkt, sizeof(pkt));

		do {
			written = write(sys_fd, buffer, packet_size);
		} while (written < 0 && errno == EINTR);
		if (written != (ssize_t)packet_size) {
			if (written < 0)
				perror("write /dev/kd_dev");
			else
				fprintf(stderr,
					"daemon: short device write: %zd of %zu bytes\n",
					written, packet_size);
			goto error;
		}
		if (remaining == chunk)
			provenance_upload_time(&evidence);
		provenance_upload_chunk(&evidence, buffer + sizeof(pkt), chunk);

		remaining -= chunk;
		pkt.offset += chunk;
	}

	provenance_upload_end(&evidence, true);
	fclose(fp);
	return 0;

error:
	provenance_upload_end(&evidence, false);
	fclose(fp);
	return -1;
}

static int write_sys(const struct daemon_config *cfg,
		     const struct kd_exe_info *exe, bool cache_hit)
{
	char jit_path[512], workspace[256];

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	snprintf(jit_path, sizeof(jit_path), "%s/asm/jit.bin", workspace);
	return write_sys_at(cfg, exe, cache_hit, jit_path, NULL);
}
