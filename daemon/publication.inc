/* Device reads and checked image publication, including ABI identity.
 * Uses the existing session fd; never reopens a provider after failure. */
static int write_native_only(const struct kd_exe_info *exe)
{
	const struct kd_recv_pkt pkt = {
		.status_code = KD_EXE_NATIVE_ONLY,
		.pid = exe->pid,
		.RIP = exe->RIP,
		.offset = 0,
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
static int write_sys(const struct daemon_config *cfg,
		     const struct kd_exe_info *exe)
{
	unsigned char buffer[sizeof(struct kd_recv_pkt) + MAX_PAYLOAD];
	struct kd_recv_pkt pkt;
	char jit_path[512];
	char workspace[256];
	size_t remaining;
	long image_size;
	FILE *fp;

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	snprintf(jit_path, sizeof(jit_path), "%s/asm/jit.bin", workspace);

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
		unsigned char header[46];
		bool directory;

		if (fread(header, 1, sizeof(header), fp) != sizeof(header)) {
			fclose(fp);
			return -1;
		}
		directory = !memcmp(header + 25, "KDWC001", 7) &&
		            !memcmp(header + 41, "KDAB", 4);
		if (!kd_entry_abi_valid(exe->lock_kind, exe->entry_abi) ||
		    (kd_entry_abi_clobber(exe->entry_abi) && !directory) ||
		    (directory && header[45] != exe->entry_abi) || fseek(fp, 0, SEEK_SET)) {
			fprintf(stderr, "daemon: JIT entry ABI mismatch\n");
			fclose(fp);
			return -1;
		}
	}
	remaining = (size_t)image_size;

	pkt.pid = exe->pid;
	pkt.RIP = exe->RIP;
	pkt.offset = 0;

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

		remaining -= chunk;
		pkt.offset += chunk;
	}

	fclose(fp);
	return 0;

error:
	fclose(fp);
	return -1;
}
