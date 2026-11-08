/* Exercise optional provenance with regular-file transport and I/O faults.
 * Run only in the development VM; this program never opens a provider. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

static int transport_fd = -1;
static unsigned int transport_writes, transport_reads, mirror_writes, clock_reads;
static unsigned int interrupted_call, failed_call, short_call;
static bool mirror_failure, clock_failure;
static bool receipt_write_failure, receipt_flush_failure, receipt_close_failure;
static int receipt_descriptor = -1;

static ssize_t observed_write(int descriptor, const void *buffer, size_t length)
{
	if (descriptor == transport_fd) {
		transport_writes++;
		if (transport_writes == interrupted_call) {
			errno = EINTR;
			return -1;
		}
		if (transport_writes == failed_call) {
			errno = EIO;
			return -1;
		}
		if (transport_writes == short_call)
			return write(descriptor, buffer, length - 1);
	} else {
		mirror_writes++;
		if (mirror_failure) {
			errno = ENOSPC;
			return -1;
		}
	}
	return write(descriptor, buffer, length);
}

static ssize_t observed_read(int descriptor, void *buffer, size_t length)
{
	if (descriptor == transport_fd)
		transport_reads++;
	return read(descriptor, buffer, length);
}

static int observed_clock(clockid_t id, struct timespec *value)
{
	clock_reads++;
	if (clock_failure) {
		errno = EIO;
		return -1;
	}
	return clock_gettime(id, value);
}

static int observed_vdprintf(int descriptor, const char *format, va_list args)
{
	if (strstr(format, "\"upload_complete\"")) {
		receipt_descriptor = descriptor;
		if (receipt_write_failure) {
			errno = ENOSPC;
			return -1;
		}
	}
	return vdprintf(descriptor, format, args);
}

static int observed_fsync(int descriptor)
{
	if (descriptor == receipt_descriptor && receipt_flush_failure) {
		errno = EIO;
		return -1;
	}
	return fsync(descriptor);
}

static int observed_close(int descriptor)
{
	int result = close(descriptor);

	if (descriptor == receipt_descriptor) {
		receipt_descriptor = -1;
		if (receipt_close_failure) {
			errno = EIO;
			return -1;
		}
	}
	return result;
}

#define main kd_daemon_main
#define write observed_write
#define read observed_read
#define clock_gettime observed_clock
#define vdprintf observed_vdprintf
#define fsync observed_fsync
#define close observed_close
#include "../../../daemon/daemon.c"
#undef close
#undef fsync
#undef vdprintf
#undef clock_gettime
#undef read
#undef write
#undef main

static void path_join(char *path, const char *directory, const char *name)
{
	assert(provenance_path(path, PATH_MAX, "%s/%s", directory, name));
}

static void put_text(const char *path, const char *text)
{
	FILE *file = fopen(path, "w");

	assert(file && fputs(text, file) >= 0 && !fclose(file));
}

static void get_text(const char *path, char *text, size_t size)
{
	FILE *file = fopen(path, "r");
	size_t length;

	assert(file);
	length = fread(text, 1, size - 1, file);
	assert(!ferror(file) && feof(file) && !fclose(file));
	text[length] = 0;
}

static void remove_optional(const char *path)
{
	assert(!unlink(path) || errno == ENOENT);
}

static void reset_transport(void)
{
	assert(!ftruncate(transport_fd, 0));
	assert(lseek(transport_fd, 0, SEEK_SET) == 0);
	transport_writes = transport_reads = mirror_writes = clock_reads = 0;
	interrupted_call = failed_call = short_call = 0;
	mirror_failure = clock_failure = false;
	receipt_write_failure = receipt_flush_failure = receipt_close_failure = false;
	receipt_descriptor = -1;
}

static unsigned long wire_upload_id(void)
{
	struct kd_recv_pkt packet;

	assert(lseek(transport_fd, 0, SEEK_SET) == 0);
	assert(read(transport_fd, &packet, sizeof(packet)) == sizeof(packet));
	return packet.upload_id;
}

static void upload_text(unsigned long id, char *text, size_t size)
{
	char path[PATH_MAX];

	assert(provenance_path(path, sizeof(path), "%s/upload-%lu/receipt.json", provenance.root, id));
	get_text(path, text, size);
}

int main(void)
{
	char root[] = "/tmp/kdlock-daemon-provenance.XXXXXX";
	char directory[PATH_MAX], path[PATH_MAX], records[PATH_MAX], text[4096];
	const char digest[] = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n";
	struct daemon_config cfg = { .mode = MODE_V1 };
	struct kd_exe_info entry = { .pid = 0, .tgid = 42, .RIP = 0x1234,
		.lock_kind = KD_EXE_LOCK_MUTEX, .entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
		.generation = 7, .status_code = KD_EXE_CALL_MISS, .tgt_addr = 0x2000 };
	unsigned char image[MAX_PAYLOAD * 2 + 17], copied[sizeof(image)];
	unsigned long first, last;
	struct provenance_compile compiler;
	struct provenance_upload upload = { 0 };
	struct kd_recv_pkt packet = { .upload_id = 123, .image_length = sizeof(image) };
	int result, original_dir = open(".", O_RDONLY | O_DIRECTORY);
	FILE *binary;

	assert(original_dir >= 0 && mkdtemp(root));
	assert(!chdir(root));
	assert(!mkdir("0x1234", 0700) && !mkdir("0x1234/asm", 0700));
	for (size_t i = 0; i < sizeof(image); i++)
		image[i] = (unsigned char)i;
	memcpy(image + 9, "KDWB002", 7);
	memcpy(image + 25, "KDWC002", 7);
	memcpy(image + 41, "KDAB", 4);
	image[45] = entry.entry_abi;
	image[46] = KD_IMAGE_PROTOCOL;
	image[47] = 0;
	binary = fopen("0x1234/asm/jit.bin", "wb");
	assert(binary && fwrite(image, 1, sizeof(image), binary) == sizeof(image) && !fclose(binary));
	transport_fd = sys_fd = open("transport", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
	assert(transport_fd >= 3);
	sys_path = "/no-such-kdlock-device";

	/* Disabled recording leaves packet transfer and device read count alone. */
	assert(!unsetenv("KD_PROVENANCE_DIR") && !unsetenv("KD_PROVENANCE_ENTRY"));
	errno = EDOM;
	provenance_start(sys_fd);
	assert(errno == EDOM && !provenance.ready);
	reset_transport();
	assert(!write_sys(&cfg, &entry, false));
	assert(transport_writes == 3 && !transport_reads && !mirror_writes && !clock_reads);

	path_join(records, root, "records");
	assert(!setenv("KD_PROVENANCE_DIR", records, 1));
	assert(!setenv("KD_PROVENANCE_ENTRY", "0x1234", 1));
	errno = ERANGE;
	provenance_start(sys_fd);
	assert(errno == ERANGE && provenance.ready);
	{
		struct kd_exe_info other = entry;

		other.RIP++;
		assert(!provenance_selected(&other));
		other = entry;
		other.entry_abi = KD_ENTRY_ABI_LEGACY;
		assert(!provenance_selected(&other));
		other = entry;
		other.lock_kind = KD_EXE_LOCK_SPIN;
		assert(!provenance_selected(&other));
	}
	path_join(path, records, "session.json");
	get_text(path, text, sizeof(text));
	assert(strstr(text, "\"schema\":1") && strstr(text, "\"entry\":4660"));
	assert(fcntl(transport_fd, F_GETFD) == FD_CLOEXEC);

	/* Sidecar identity is retained with the original cached result, not a
	 * later compile. Byte-to-manifest comparison belongs to the offline gate. */
	errno = E2BIG;
	compiler = provenance_compile_begin(&entry);
	assert(errno == E2BIG && compiler.compile_attempt_id == 1);
	path_join(path, records, "compile-1/context.json");
	get_text(path, text, sizeof(text));
	assert(strstr(text, "\"base_generation\":7") && strstr(text, "\"target\":8192"));
	path_join(path, records, "compile-1/manifest.sha256");
	put_text(path, digest);
	errno = ENOTTY;
	provenance_compile_end(&compiler);
	assert(errno == ENOTTY && strlen(compiler.manifest_sha256) == 64);
	provenance_current = compiler;
	assert(!remember_cmd("compile A", 7, 0));
	provenance_current.compile_attempt_id = 2;
	memset(provenance_current.manifest_sha256, 'b', 64);
	assert(!remember_cmd("compile B", 7, 0));
	assert(cmd_seen("compile A", 7, &result) && !result);
	assert(provenance_current.compile_attempt_id == 1 && provenance_current.manifest_sha256[0] == 'a');
	assert(provenance.compiler_attempts == 1);

	reset_transport();
	interrupted_call = 1;
	assert(!write_sys(&cfg, &entry, true));
	assert(transport_writes == 4 && !transport_reads && mirror_writes == 3 && clock_reads == 1);
	first = last = wire_upload_id();
	upload_text(last, text, sizeof(text));
	assert(strstr(text, "\"compile_attempt_id\":1") && strstr(text, "\"cache_hit\":true"));
	assert(strstr(text, "\"upload_complete\":true") && strstr(text, "\"evidence_complete\":true"));
	assert(strstr(text, "\"accepted_length\":8017") && strstr(text, "\"error\":null"));
	assert(provenance_path(path, sizeof(path), "%s/upload-%lu/payload.bin", records, last));
	binary = fopen(path, "rb");
	assert(binary && fread(copied, 1, sizeof(copied), binary) == sizeof(copied));
	assert(fgetc(binary) == EOF && !fclose(binary) && !memcmp(copied, image, sizeof(image)));

	/* A mirror or clock failure cannot cause extra transport writes or turn a
	 * successful publication into a production error. */
	reset_transport();
	mirror_failure = true;
	assert(!write_sys(&cfg, &entry, true));
	assert(transport_writes == 3 && !transport_reads && clock_reads == 1);
	last = wire_upload_id();
	upload_text(last, text, sizeof(text));
	assert(strstr(text, "\"upload_complete\":true") && strstr(text, "\"evidence_complete\":false"));
	assert(strstr(text, "payload_write_failed"));
	reset_transport();
	clock_failure = true;
	assert(!write_sys(&cfg, &entry, true));
	last = wire_upload_id();
	upload_text(last, text, sizeof(text));
	assert(strstr(text, "\"upload_complete\":true") && strstr(text, "\"final_write_end_ns\":0"));
	assert(strstr(text, "\"evidence_complete\":false"));

	/* Complete-looking JSON from a failed final evidence write/flush/close is
	 * retained only as partial output. It cannot certify a successful upload. */
	for (int fault = 0; fault < 3; fault++) {
		reset_transport();
		receipt_write_failure = fault == 0;
		receipt_flush_failure = fault == 1;
		receipt_close_failure = fault == 2;
		assert(!write_sys(&cfg, &entry, true));
		assert(transport_writes == 3 && !transport_reads);
		last = wire_upload_id();
		assert(provenance_path(path, sizeof(path), "%s/upload-%lu/receipt.json", records, last));
		assert(access(path, F_OK) == -1 && errno == ENOENT);
		assert(provenance_path(path, sizeof(path), "%s/upload-%lu/receipt.json.partial", records, last));
		get_text(path, text, sizeof(text));
		if (fault)
			assert(strstr(text, "\"upload_complete\":true") && strstr(text, "\"evidence_complete\":true"));
	}

	/* Failed and short device writes retain only fully accepted chunks. */
	for (int fault = 0; fault < 4; fault++) {
		unsigned int call = fault < 2 ? 2 : 3;

		reset_transport();
		if (fault % 2)
			short_call = call;
		else
			failed_call = call;
		assert(write_sys(&cfg, &entry, true) == -1);
		assert(transport_writes == call && !transport_reads && !clock_reads && mirror_writes == call - 1);
		last = wire_upload_id();
		upload_text(last, text, sizeof(text));
		assert(strstr(text, "\"upload_complete\":false"));
		assert(strstr(text, call == 2 ? "\"accepted_length\":4000" : "\"accepted_length\":8000"));
	}

	/* Existing evidence is never replaced, and budgets affect recording only. */
	assert(provenance_path(directory, sizeof(directory), "%s/upload-%lu", records, last + 1));
	assert(!mkdir(directory, 0700));
	reset_transport();
	assert(!write_sys(&cfg, &entry, true));
	assert(transport_writes == 3 && !transport_reads && !mirror_writes && !clock_reads);
	last = wire_upload_id();
	path_join(path, directory, "receipt.json");
	assert(access(path, F_OK) == -1 && errno == ENOENT);
	provenance.compiler_attempts = provenance.uploads = KD_PROVENANCE_LIMIT;
	errno = EBUSY;
	compiler = provenance_compile_begin(&entry);
	provenance_upload_begin(&upload, &entry, &packet, true);
	assert(errno == EBUSY && !compiler.compile_attempt_id && !upload.selected);
	assert(!cmd_seen("compile A", 8, &result) && !provenance_current.compile_attempt_id);

	for (unsigned long id = first; id <= last; id++) {
		assert(provenance_path(directory, sizeof(directory), "%s/upload-%lu", records, id));
		path_join(path, directory, "payload.bin");
		remove_optional(path);
		path_join(path, directory, "receipt.json");
		remove_optional(path);
		path_join(path, directory, "receipt.json.partial");
		remove_optional(path);
		path_join(path, directory, "context.json");
		remove_optional(path);
		assert(!rmdir(directory));
	}
	path_join(path, records, "compile-1/context.json");
	assert(!unlink(path));
	path_join(path, records, "compile-1/manifest.sha256");
	assert(!unlink(path));
	path_join(path, records, "compile-1");
	assert(!rmdir(path));
	path_join(path, records, "session.json");
	assert(!unlink(path) && !rmdir(records));
	assert(!close(transport_fd) && !unlink("transport"));
	assert(!unlink("0x1234/asm/jit.bin") && !rmdir("0x1234/asm") && !rmdir("0x1234"));
	assert(!fchdir(original_dir) && !close(original_dir) && !rmdir(root));
	for (int i = 0; i < cmd_cnt; i++)
		free(cmd_hist[i]);
	assert(!unsetenv("KD_PROVENANCE_DIR") && !unsetenv("KD_PROVENANCE_ENTRY"));
	puts("[PASS] optional daemon provenance, exact buffers, cache identity and independent failures");
	return 0;
}
