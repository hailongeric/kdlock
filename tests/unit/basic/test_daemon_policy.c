/* Test production result caching, wire encoding and opt-in child accounting. */
#include <assert.h>
#include <errno.h>
#include <signal.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <dirent.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include "../../../include/kd_learning_api.h"
#include "../../../include/kd_source_api.h"

static bool batch_ioctl_active;
static unsigned int batch_snapshots, batch_bindings, batch_cancels;
static int batch_bind_error, batch_cancel_error;
static bool batch_read_failure;
static unsigned int batch_payload_reads;
static bool batch_close_failure;
static unsigned int batch_close_failures;
static const char *batch_close_path;
static FILE *batch_close_stream;
static struct kd_learning_snapshot batch_response;
static struct kd_learning_bind batch_last_binding;

static int observed_ioctl(int descriptor, unsigned long command, ...)
{
	va_list args;
	void *packet;

	va_start(args, command);
	packet = va_arg(args, void *);
	va_end(args);
	assert(batch_ioctl_active && descriptor >= 3);
	if (command == KD_LEARNING_SNAPSHOT) {
		struct kd_learning_snapshot *request = packet;

		assert(!request->token && request->root.slot == KD_LEARNING_SLOT_LOOKUP);
		assert(request->root.rip == batch_response.root.rip);
		assert(request->base_generation == batch_response.base_generation);
		batch_snapshots++;
		*request = batch_response;
		return 0;
	}
	if (command == KD_LEARNING_BIND) {
		batch_last_binding = *(struct kd_learning_bind *)packet;
		assert(batch_last_binding.token == batch_response.token);
		assert(batch_last_binding.revision == batch_response.revision);
		assert(batch_last_binding.base_generation == batch_response.base_generation);
		assert(batch_last_binding.upload_id);
		batch_bindings++;
		batch_payload_reads = 0;
		if (batch_bind_error) {
			errno = batch_bind_error;
			return -1;
		}
		return 0;
	}
	assert(command == KD_LEARNING_CANCEL);
	assert(((struct kd_learning_cancel *)packet)->token == batch_response.token);
	batch_cancels++;
	if (batch_cancel_error) {
		errno = batch_cancel_error;
		return -1;
	}
	return 0;
}

static FILE *observed_fopen(const char *path, const char *mode)
{
	FILE *stream = fopen(path, mode);

	if (batch_ioctl_active && batch_close_failure && batch_close_path &&
	    !strcmp(path, batch_close_path) && !strcmp(mode, "r"))
		batch_close_stream = stream;
	return stream;
}

static int observed_fclose(FILE *stream)
{
	bool failed = batch_ioctl_active && batch_close_failure && stream == batch_close_stream;
	int result = fclose(stream);

	if (failed) {
		batch_close_failure = false;
		batch_close_stream = NULL;
		batch_close_failures++;
		errno = EIO;
		return EOF;
	}
	return result;
}

static size_t observed_fread(void *data, size_t size, size_t count, FILE *stream)
{
	if (batch_ioctl_active && size == 1 && count == 4000) {
		batch_payload_reads++;
		if (batch_close_failure && !batch_close_path)
			batch_close_stream = stream;
		if (batch_read_failure && batch_payload_reads == 2) {
			errno = EIO;
			return fread(data, size, count - 1, stream);
		}
	}
	return fread(data, size, count, stream);
}

static int clock_calls, clock_fault, wait_calls;
static int interrupt_wait;

/* Keep real fork/exec/reaping; substitute only clock faults and one interrupted
 * observation to prove telemetry cannot turn launch failures into refusals. */
static int observed_clock(clockid_t id, struct timespec *value)
{
	clock_calls++;
	if (clock_fault == clock_calls && clock_fault != 3) {
		errno = EIO;
		return -1;
	}
	if (clock_fault == 3) {
		*value = (struct timespec){ .tv_sec = clock_calls == 1 ? 2 : 1 };
		return 0;
	}
	return clock_gettime(id, value);
}

static pid_t observed_wait(pid_t child, int *status, int options,
			   struct rusage *usage)
{
	wait_calls++;
	if (interrupt_wait) {
		interrupt_wait = 0;
		errno = EINTR;
		return -1;
	}
	return wait4(child, status, options, usage);
}

#define main kd_daemon_main
#define clock_gettime observed_clock
#define wait4 observed_wait
#define ioctl observed_ioctl
#define fread observed_fread
#define fopen observed_fopen
#define fclose observed_fclose
#include "../../../daemon/daemon.c"
#undef main
#undef clock_gettime
#undef wait4
#undef ioctl
#undef fread
#undef fopen
#undef fclose

static void test_compiler_launch(void)
{
	char root[] = "/tmp/kdlock-compiler-launch.XXXXXX";
	char session_path[] = "/tmp/kdlock-compiler-session.XXXXXX";
	struct kd_exe_info exe = { .pid = 0, .tgid = 42, .RIP = 0x1234 };
	const char *kinds[] = { "unknown", "spin", "mutex" };
	struct daemon_config cfg = { .mode = MODE_V1 };
	int original_dir = open(".", O_RDONLY | O_DIRECTORY);
	FILE *script;
	struct stat session_stat;

	assert(original_dir >= 0);
	/* This regular file substitutes only device I/O. Real fork/exec children
	 * must inherit its open description even after the pathname disappears. */
	sys_fd = mkstemp(session_path);
	assert(sys_fd >= 3);
	assert(!unlink(session_path));
	assert(!fcntl(sys_fd, F_SETFD, FD_CLOEXEC));
	assert(mkdtemp(root));
	assert(!chdir(root));
	assert(!mkdir("daemon", 0700));
	assert(!mkdir("disassem", 0700));
	assert(!chdir("daemon"));

	for (int mode = MODE_V1; mode <= MODE_V2; mode++) {
		cfg.mode = mode;
		cfg.metrics = mode == MODE_V2;
		interrupt_wait = cfg.metrics;
		/* Neither a missing workspace nor a missing script is a refusal. */
		assert(compile_entry(&cfg, &exe) == -1);
		if (mode == MODE_V1)
			assert(!mkdir("0x1234", 0700));
		else
			assert(!mkdir("0x1234/42", 0700));
		assert(compile_entry(&cfg, &exe) == -1);

		for (int kind = KD_EXE_LOCK_UNKNOWN; kind <= KD_EXE_LOCK_MUTEX;
		     kind++) {
			exe.lock_kind = kind;
			for (int code = 0; code <= 2; code++) {
				script = fopen("../disassem/disassem.py", "w");
				assert(script);
				assert(fprintf(script,
					       "import os, sys\nassert sys.argv[1:] == ['0', '0x1234', '%s', '0']\nfd = int(os.environ['KD_DEVICE_FD'])\nassert os.write(fd, b'S') == 1\nraise SystemExit(%d)\n",
					       kinds[kind], code) > 0);
				assert(!fclose(script));
				assert(compile_entry(&cfg, &exe) ==
				       (code == 1 ? -1 : code));
			}
		}
		if (cfg.metrics) {
			assert(clock_calls == 22 && wait_calls == 12);
			/* Before-fork failure must launch nothing; after-wait failure
			 * still reaps the child and must not cache its native-only result. */
			for (int fault = 1; fault <= 3; fault++) {
				clock_calls = 0;
				clock_fault = fault;
				assert(compile_entry(&cfg, &exe) == -1);
			}
			clock_fault = 0;
			assert(wait_calls == 14);
		} else {
			assert(clock_calls == 0 && wait_calls == 0);
		}
		assert(!unlink("../disassem/disassem.py"));
	}
	assert(!rmdir("0x1234/42"));
	assert(!rmdir("0x1234"));
	assert(!chdir(".."));
	assert(!rmdir("daemon"));
	assert(!rmdir("disassem"));
	assert(!fchdir(original_dir));
	close(original_dir);
	assert(!rmdir(root));
	assert(!fstat(sys_fd, &session_stat));
	assert(session_stat.st_size == 20);
	assert(fcntl(sys_fd, F_GETFD) == FD_CLOEXEC);
	assert(!close(sys_fd));
	sys_fd = -1;
}

static void test_metrics_contract(void)
{
	struct daemon_config cfg = { .mode = MODE_V2 };
	char *argv[] = { "daemon", "--metrics", "--quiet", NULL };
	struct kd_exe_info exe = { .RIP = 0x1234, .lock_kind = KD_EXE_LOCK_MUTEX };
	struct rusage usage = { 0 };
	uint64_t value;

	assert(!cfg.metrics);
	assert(!parse_args(3, argv, &cfg) && cfg.metrics && !cfg.verbose);
	assert(!usage_ns((struct timeval){ 1, 999999 }, &value));
	assert(value == 1999999000);
	assert(usage_ns((struct timeval){ -1, 0 }, &value) == -1);
	assert(usage_ns((struct timeval){ 0, 1000000 }, &value) == -1);
	assert(usage_ns((struct timeval){ UINT64_MAX / 1000000000 + 1, 0 },
			&value) == -1);
	assert(report_translation(&exe, 1, 0, 0, 10, 10, &usage) == -1);
	usage.ru_maxrss = -1;
	assert(report_translation(&exe, 1, 0, 0, 10, 11, &usage) == -1);
	puts("[PASS] daemon opt-in metrics, real children and observation faults");
}

static void test_chunk_session(void)
{
	char root[] = "/tmp/kdlock-chunk-session.XXXXXX";
	struct kd_exe_info exe = { .pid = 0, .RIP = 0x1234, .lock_kind = KD_EXE_LOCK_MUTEX };
	struct daemon_config cfg = { .mode = MODE_V1 };
	unsigned char image[MAX_PAYLOAD * 2 + 17], chunk[MAX_PAYLOAD];
	int original_dir = open(".", O_RDONLY | O_DIRECTORY);
	char *argv[] = { "daemon", NULL };
	FILE *binary;

	assert(kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, 2,
					 KD_IMAGE_REQUIRE_NATIVE_ESCAPE));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, 0,
					  KD_IMAGE_REQUIRE_NATIVE_ESCAPE));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1,
					  KD_IMAGE_REQUIRE_NATIVE_ESCAPE));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, 2, 2));
	assert(kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1,
					KD_IMAGE_REQUIRE_ADDRESS_GUARD));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 3,
					 KD_IMAGE_REQUIRE_ADDRESS_GUARD));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1, 3));
	assert(kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1,
					KD_IMAGE_REQUIRE_STRING_SERVICES));
	assert(kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1,
		KD_IMAGE_REQUIRE_STRING_SERVICES | KD_IMAGE_REQUIRE_ADDRESS_GUARD));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 3,
					 KD_IMAGE_REQUIRE_STRING_SERVICES));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, 2,
					 KD_IMAGE_REQUIRE_STRING_SERVICES));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 0,
					 KD_IMAGE_REQUIRE_STRING_SERVICES));
	assert(kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1, KD_IMAGE_REQUIRE_STRING_WRITE));
	assert(kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1,
		KD_IMAGE_REQUIRE_STRING_WRITE | KD_IMAGE_REQUIRE_STRING_SERVICES));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 3, KD_IMAGE_REQUIRE_STRING_WRITE));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX, 2, KD_IMAGE_REQUIRE_STRING_WRITE));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 0, KD_IMAGE_REQUIRE_STRING_WRITE));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1, 16));
	assert(kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1,
		KD_IMAGE_REQUIRE_DIRECT_STRINGS | KD_IMAGE_REQUIRE_STRING_SERVICES));
	assert(kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1,
		KD_IMAGE_REQUIRE_DIRECT_STRINGS | KD_IMAGE_REQUIRE_STRING_WRITE));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 3,
		KD_IMAGE_REQUIRE_DIRECT_STRINGS | KD_IMAGE_REQUIRE_STRING_SERVICES));
	assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN, 1,
		KD_IMAGE_REQUIRE_DIRECT_STRINGS | KD_IMAGE_REQUIRE_STRING_SERVICES |
		KD_IMAGE_REQUIRE_ADDRESS_GUARD));

	assert(original_dir >= 0 && mkdtemp(root));
	assert(!chdir(root));
	assert(!mkdir("0x1234", 0700));
	assert(!mkdir("0x1234/asm", 0700));
	binary = fopen("0x1234/asm/jit.bin", "wb");
	assert(binary);
	for (size_t i = 0; i < sizeof(image); i++)
		image[i] = (unsigned char)i;
	memcpy(image + 9, "KDWB002", 7);
	memcpy(image + 25, "KDWC002", 7);
	memcpy(image + 41, "KDAB", 4);
	image[45] = exe.entry_abi;
	image[46] = KD_IMAGE_PROTOCOL;
	image[47] = 0;
	assert(fwrite(image, 1, sizeof(image), binary) == sizeof(image));
	assert(!fclose(binary));
	sys_fd = open("transport", O_CREAT | O_RDWR | O_CLOEXEC, 0600);
	assert(sys_fd >= 3);
	assert(!unlink("transport"));
	/* A dead path catches accidental reopen; headers/payload still travel
	 * through one shared file description, including the final publication. */
	sys_path = "/no-such-kdlock-device";
	assert(!write_sys(&cfg, &exe, false));
	assert(lseek(sys_fd, 0, SEEK_SET) == 0);
	for (size_t offset = 0; offset < sizeof(image);) {
		struct kd_recv_pkt packet;
		size_t size = sizeof(image) - offset;

		if (size > MAX_PAYLOAD)
			size = MAX_PAYLOAD;
		assert(read_sys(&packet, sizeof(packet)) == sizeof(packet));
		assert(packet.pid == exe.pid && packet.RIP == exe.RIP);
		assert(packet.offset == offset);
		assert(packet.status_code == (offset + size == sizeof(image) ?
						      KD_EXE_NORMAL :
						      KD_EXE_UNINIT));
		assert(read_sys(chunk, size) == (ssize_t)size);
		assert(!memcmp(chunk, image + offset, size));
		offset += size;
	}
	assert(read_sys(chunk, sizeof(chunk)) == 0);
	assert(!close(sys_fd));
	sys_fd = -1;
	assert(write_sys(&cfg, &exe, false) == -1);
	assert(read_sys(chunk, sizeof(chunk)) == -EBADF);
	assert(!unlink("0x1234/asm/jit.bin"));
	assert(!rmdir("0x1234/asm"));
	assert(!rmdir("0x1234"));
	/* Failure to acquire the provider must not clear existing workspaces. */
	assert(!mkdir("0xretained", 0700));
	assert(kd_daemon_main(1, argv) == EXIT_FAILURE);
	assert(!rmdir("0xretained"));
	assert(!fchdir(original_dir));
	assert(!close(original_dir));
	assert(!rmdir(root));
}

static void fixture_text(const char *path, const char *text)
{
	FILE *stream = fopen(path, "w");

	assert(stream && fputs(text, stream) >= 0 && !fclose(stream));
}

static size_t fixture_read(const char *path, unsigned char *data, size_t size)
{
	FILE *stream = fopen(path, "rb");
	size_t count;

	assert(stream);
	count = fread(data, 1, size, stream);
	assert(!ferror(stream) && !fclose(stream));
	return count;
}

/* Only the exact mkdtemp tree created below is removed. Never follow links. */
static void fixture_remove(const char *path)
{
	struct stat identity;

	assert(!lstat(path, &identity));
	if (S_ISDIR(identity.st_mode)) {
		DIR *directory = opendir(path);
		struct dirent *entry;

		assert(directory);
		while ((entry = readdir(directory))) {
			char child[PATH_MAX];

			if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, ".."))
				continue;
			assert(provenance_path(child, sizeof(child), "%s/%s", path, entry->d_name));
			fixture_remove(child);
		}
		assert(!closedir(directory) && !rmdir(path));
	} else {
		assert(!unlink(path));
	}
}

static void test_learning_batch_attempt(void)
{
	static const char script[] =
		"import os\n"
		"from pathlib import Path\n"
		"with open(os.environ['KD_BATCH_TEST_COUNTER'], 'ab') as f: f.write(b'C')\n"
		"for name in ('callee_table.txt', 'ij_table.txt'):\n"
		" rows = Path('asm', name).read_text().splitlines()\n"
		" assert len(rows) == len(set(rows))\n"
		"b = bytearray(8064)\n"
		"b[9:16], b[25:32], b[41:45] = b'KDWB002', b'KDWC002', b'KDAB'\n"
		"b[45], b[46] = 2, 3\n"
		"b[48:52] = (1 << 13).to_bytes(4, 'little')\n"
		"Path('asm/jit.bin').write_bytes(b)\n"
		"Path('asm/jit.S').write_text('frozen batch assembly\\n')\n";
	char root[] = "/tmp/kdlock-learning-batch.XXXXXX";
	char counter[PATH_MAX], path[PATH_MAX], workspace[256], storage[512], saved_session[512];
	struct daemon_config cfg = { .mode = MODE_V1 };
	struct kd_exe_info entry = { .pid = 0, .tgid = 42, .RIP = 0xffffffff81001000UL,
		.lock_kind = KD_EXE_LOCK_MUTEX, .entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
		.status_code = KD_EXE_CALL_MISS, .generation = 0 };
	unsigned char bytes[2048];
	struct kd_recv_pkt packet;
	unsigned int old_commands = cmd_cnt, old_bindings, old_cancels;
	int original_dir = open(".", O_RDONLY | O_DIRECTORY);
	struct stat before, after;

	assert(original_dir >= 0 && mkdtemp(root) && !chdir(root));
	assert(!mkdir("daemon", 0700) && !mkdir("disassem", 0700));
	fixture_text("disassem/disassem.py", script);
	assert(provenance_path(counter, sizeof(counter), "%s/compiles", root));
	assert(!setenv("KD_BATCH_TEST_COUNTER", counter, 1));
	assert(!chdir("daemon"));
	sys_fd = open("transport", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
	assert(sys_fd >= 3);
	learning.enabled = true;
	snprintf(learning.session, sizeof(learning.session), "{\"provider_session\":\"fixture-original\"}\n");
	strcpy(learning.scope_tag, "session-fixture-original");
	strcpy(saved_session, learning.session);
	batch_ioctl_active = true;
	batch_response = (struct kd_learning_snapshot) {
		.version = KD_LEARNING_API_VERSION,
		.header_size = KD_LEARNING_SNAPSHOT_HEADER_SIZE,
		.record_size = KD_LEARNING_RECORD_SIZE, .capacity = KD_LEARNING_CAPACITY,
		.root = { .slot = 4, .pid = entry.pid, .rip = entry.RIP,
			.lock_kind = entry.lock_kind, .entry_abi = entry.entry_abi },
		.base_generation = 0, .revision = 5, .token = 1, .count = 5,
		.records = {
			{1, 0, 0xffffffff81005000UL, 0, KD_LEARNING_CALL, 0},
			{2, 0, 0xffffffff81005000UL, 0, KD_LEARNING_CALL, 0},
			{3, 0, 0xffffffff81006000UL, 0xffffffff81002002UL, KD_LEARNING_IJ, 0},
			{4, 0, 0xffffffff81007000UL, 0xffffffff81002002UL, KD_LEARNING_IJ, 0},
			{5, 0, 0xffffffff81006000UL, 0, KD_LEARNING_CALL, 0},
		},
	};
	/* Later generations must follow real successful local uploads, never an
	 * unexplained jump from a manually seeded generation-zero history. */
	assert(learning_snapshot_valid(&batch_response, &entry));
	batch_response.root.slot = KD_MAX_EXE;
	assert(!learning_snapshot_valid(&batch_response, &entry));
	assert(!learning_generation_accept(&entry, &batch_response));
	batch_response.root.slot = 4;
	batch_response.records[4].reserved = 1;
	assert(!learning_snapshot_valid(&batch_response, &entry));
	batch_response.records[4].reserved = 0;
	batch_bind_error = EIO;
	assert(learning_step(&cfg, &entry) == 1 && learning.active && learning.compiled);
	assert(batch_snapshots == 1 && batch_bindings == 1 && !batch_cancels);
	assert(learning_generations[4].initialized && !learning_generations[4].expected);
	assert(cmd_cnt == (int)old_commands && fixture_read(counter, bytes, sizeof(bytes)) == 1);
	workspace_path(workspace, sizeof(workspace), &cfg, &entry);
	assert(provenance_path(path, sizeof(path), "%s/asm/callee_table.txt", workspace));
	assert(fixture_read(path, bytes, sizeof(bytes)) == strlen("0xffffffff81005000\n0xffffffff81006000\n"));
	assert(!memcmp(bytes, "0xffffffff81005000\n0xffffffff81006000\n",
		strlen("0xffffffff81005000\n0xffffffff81006000\n")));
	assert(provenance_path(path, sizeof(path), "%s/asm/ij_table.txt", workspace));
	assert(fixture_read(path, bytes, sizeof(bytes)) ==
		strlen("0xffffffff81002002 0xffffffff81006000\n0xffffffff81002002 0xffffffff81007000\n"));
	/* The mutable compatibility export cannot replace a frozen retry image. */
	assert(provenance_path(path, sizeof(path), "%s/asm/jit.bin", workspace));
	fixture_text(path, "replaced current workspace binary");
	batch_bind_error = 0;
	assert(!learning_step(&cfg, &entry) && !learning.active);
	assert(batch_snapshots == 1 && batch_bindings == 2 && !batch_cancels);
	assert(learning_generations[4].expected == 1);
	assert(fixture_read(counter, bytes, sizeof(bytes)) == 1);
	assert(lseek(sys_fd, 0, SEEK_SET) == 0);
	assert(read(sys_fd, &packet, sizeof(packet)) == sizeof(packet));
	assert(packet.upload_id == batch_last_binding.upload_id && packet.base_generation == 0);
	assert(read(sys_fd, bytes, 64) == 64 && bytes[45] == 2 && bytes[46] == 3);
	assert(!memcmp(bytes + 9, "KDWB002", 7));
	assert(lseek(sys_fd, 0, SEEK_END) >= 0);

	/* A later finite snapshot unions cumulative roots and keeps its own
	 * immutable attempt. A changed registry lifetime cancels that view. */
	entry.generation = 1;
	batch_response.base_generation = 1;
	batch_response.token = 2;
	batch_response.revision = 6;
	batch_response.count = 1;
	batch_response.records[0] = (struct kd_learning_record){6, 1,
		0xffffffff81008000UL, 0, KD_LEARNING_CALL, 0};
	batch_response.flags = KD_LEARNING_OVERFLOW;
	batch_response.overflow_report_events = 3;
	batch_bind_error = EIO;
	assert(learning_step(&cfg, &entry) == 1);
	assert(fixture_read(counter, bytes, sizeof(bytes)) == 2);
	assert(provenance_path(path, sizeof(path), "%s/asm/callee_table.txt", workspace));
	assert(fixture_read(path, bytes, sizeof(bytes)) ==
		strlen("0xffffffff81005000\n0xffffffff81006000\n0xffffffff81008000\n"));
	old_bindings = batch_bindings;
	entry.tgid++;
	assert(!learning_step(&cfg, &entry) && !learning.active);
	assert(batch_cancels == 1 && batch_bindings == old_bindings);
	entry.tgid--;

	/* A changed receipt identity cannot authorize this session's old histories. */
	snprintf(learning.session, sizeof(learning.session), "{\"provider_session\":\"fixture-other\"}\n");
	batch_response.token = 3;
	assert(!learning_step(&cfg, &entry));
	assert(batch_cancels == 2 && fixture_read(counter, bytes, sizeof(bytes)) == 2);
	strcpy(learning.session, saved_session);
	batch_bind_error = 0;

	/* Failed compilers do not bind/ACK; deliberate exit 2 is the existing
	 * NativeOnly decision after CANCEL, never successful batch publication. */
	fixture_text("../disassem/disassem.py", "raise SystemExit(1)\n");
	batch_response.token = 4;
	old_cancels = batch_cancels;
	assert(!fstat(sys_fd, &before));
	batch_cancel_error = EIO;
	assert(learning_step(&cfg, &entry) == 1 && learning.active && !learning.compiled);
	assert(batch_cancels == old_cancels + 1 && batch_bindings == old_bindings);
	{
		unsigned int snapshots = batch_snapshots;

		batch_cancel_error = 0;
		assert(!learning_step(&cfg, &entry) && !learning.active);
		assert(batch_snapshots == snapshots && batch_cancels == old_cancels + 2);
	}
	assert(learning_generations[4].expected == 1 && batch_bindings == old_bindings);
	assert(!fstat(sys_fd, &after) && after.st_size == before.st_size);
	old_cancels = batch_cancels;
	fixture_text("../disassem/disassem.py", "raise SystemExit(2)\n");
	batch_response.token = 5;
	assert(!learning_step(&cfg, &entry) && !learning.active);
	assert(batch_cancels == old_cancels + 1 && batch_bindings == old_bindings);
	assert(learning_generations[4].expected == 1);
	assert(!fstat(sys_fd, &after) && after.st_size == before.st_size + (off_t)sizeof(packet));
	assert(cmd_cnt == (int)old_commands);

	/* Even a complete history read with a failing close cannot prepare a new
	 * attempt, advance its generation, or acknowledge any pending records. */
	assert(learning_storage_path(storage, sizeof(storage), &cfg, &entry, &batch_response));
	assert(provenance_path(path, sizeof(path), "%s/asm/callee_table.txt", storage));
	batch_close_path = path;
	batch_close_failure = true;
	batch_response.token = 6;
	old_cancels = batch_cancels;
	assert(!learning_step(&cfg, &entry) && !learning.active);
	assert(batch_close_failures == 1 && !batch_close_failure);
	assert(batch_cancels == old_cancels + 1 && batch_bindings == old_bindings);
	assert(learning_generations[4].expected == 1);
	assert(fixture_read(counter, bytes, sizeof(bytes)) == 2);
	batch_close_path = NULL;
	assert(provenance_path(path, sizeof(path), "%s/batch-6", storage));
	assert(access(path, F_OK) == -1 && errno == ENOENT);

	/* A missing established leaf cannot turn acknowledged cumulative input
	 * into an empty history. The ledger view is canceled without a build. */
	assert(learning_storage_path(storage, sizeof(storage), &cfg, &entry, &batch_response));
	assert(provenance_path(path, sizeof(path), "%s/asm/ij_table.txt", storage));
	assert(!unlink(path));
	batch_response.token = 7;
	old_cancels = batch_cancels;
	assert(!learning_step(&cfg, &entry));
	assert(batch_cancels == old_cancels + 1 && batch_bindings == old_bindings);
	assert(fixture_read(counter, bytes, sizeof(bytes)) == 2);

	/* Distinct legal roots sharing RIP get independent authoritative inputs.
	 * A nonzero generation without history refuses before compilation. */
	entry.pid = 19;
	entry.tgid = 45;
	batch_response.root.pid = 19;
	batch_response.root.slot = 6;
	batch_response.token = 8;
	assert(!learning_step(&cfg, &entry));
	assert(batch_cancels == old_cancels + 2 && batch_bindings == old_bindings);
	fixture_text("../disassem/disassem.py", script);
	entry.pid = 17;
	entry.tgid = 43;
	batch_response.root.pid = 17;
	batch_response.root.slot = 5;
	entry.generation = batch_response.base_generation = 0;
	entry.status_code = KD_EXE_UNINIT;
	batch_response.token = 9;
	batch_response.count = 0;
	batch_response.revision = 0;
	batch_response.flags = 0;
	batch_response.overflow_report_events = 0;
	batch_read_failure = true;
	assert(learning_step(&cfg, &entry) == 1 && learning.active);
	assert(batch_bindings == old_bindings + 1 && batch_payload_reads == 2);
	assert(!learning_generations[5].expected);
	{
		unsigned long failed_id = batch_last_binding.upload_id;
		unsigned int snapshots = batch_snapshots;

		batch_read_failure = false;
		batch_close_failure = true;
		assert(!learning_step(&cfg, &entry) && !learning.active);
		assert(batch_close_failures == 2 && !batch_close_failure);
		assert(batch_last_binding.upload_id != failed_id);
		assert(batch_snapshots == snapshots && batch_bindings == old_bindings + 2);
		assert(learning_generations[5].expected == 1);
	}
	assert(fixture_read(counter, bytes, sizeof(bytes)) == 3);
	assert(learning_storage_path(path, sizeof(path), &cfg, &entry, &batch_response));
	assert(strcmp(path, storage));

	/* Two writer descriptions can freeze different finite views. B publishes
	 * {a,b}; A's stale {a} attempt must not later replace it with {a,c}. */
	{
		struct kd_learning_snapshot original, other;
		char script_path[PATH_MAX], binary_path[1024];
		unsigned int snapshots, bindings, cancels;
		size_t compiled;
		int original_fd = sys_fd, other_fd;

		entry.pid = 23;
		entry.tgid = 46;
		entry.RIP = 0xffffffff81003000UL;
		entry.generation = 0;
		entry.status_code = KD_EXE_CALL_MISS;
		batch_response = (struct kd_learning_snapshot) {
			.version = KD_LEARNING_API_VERSION,
			.header_size = KD_LEARNING_SNAPSHOT_HEADER_SIZE,
			.record_size = KD_LEARNING_RECORD_SIZE, .capacity = KD_LEARNING_CAPACITY,
			.root = { .slot = 7, .pid = entry.pid, .rip = entry.RIP,
				.lock_kind = entry.lock_kind, .entry_abi = entry.entry_abi },
			.base_generation = 0, .revision = 1, .token = 10, .count = 1,
			.records = { {1, 0, 0xffffffff8100a000UL, 0, KD_LEARNING_CALL, 0} },
		};
		batch_bind_error = EIO;
		assert(learning_step(&cfg, &entry) == 1 && learning.active && learning.compiled);
		assert(learning_generations[7].initialized && !learning_generations[7].expected);
		original = batch_response;
		assert(learning_storage_path(storage, sizeof(storage), &cfg, &entry, &batch_response));
		assert(provenance_path(path, sizeof(path), "%s/asm/callee_table.txt", storage));
		assert(fixture_read(path, bytes, sizeof(bytes)) == strlen("0xffffffff8100a000\n"));
		assert(!memcmp(bytes, "0xffffffff8100a000\n", strlen("0xffffffff8100a000\n")));
		assert(!fstat(original_fd, &before));

		other_fd = open("other-transport", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
		assert(other_fd >= 3 && other_fd != original_fd);
		sys_fd = other_fd;
		batch_response.token = 11;
		batch_response.revision = 2;
		batch_response.count = 2;
		batch_response.records[1] = (struct kd_learning_record){2, 0,
			0xffffffff8100b000UL, 0, KD_LEARNING_CALL, 0};
		other = original;
		other.token = 0;
		other.root.slot = KD_LEARNING_SLOT_LOOKUP;
		other.revision = other.count = 0;
		assert(!learning_ioctl(KD_LEARNING_SNAPSHOT, &other));
		assert(other.token != original.token && other.count == 2);
		assert(!mkdir("other-workspace", 0700) && !mkdir("other-workspace/asm", 0700));
		fixture_text("other-workspace/asm/callee_table.txt",
			"0xffffffff8100a000\n0xffffffff8100b000\n");
		fixture_text("other-workspace/asm/ij_table.txt", "");
		assert(realpath("../disassem/disassem.py", script_path));
		assert(!compile_at(&cfg, &entry, "other-workspace", script_path));
		batch_bind_error = 0;
		assert(!write_sys_at(&cfg, &entry, false, "other-workspace/asm/jit.bin", &other));
		assert(!fstat(other_fd, &after) && after.st_size > 0);
		assert(!learning_generations[7].expected);
		sys_fd = original_fd;
		batch_response = original;
		batch_bind_error = ESTALE;
		cancels = batch_cancels;
		assert(!learning_step(&cfg, &entry) && !learning.active);
		assert(batch_cancels == cancels + 1 && !learning_generations[7].expected);
		assert(!fstat(original_fd, &after) && after.st_size == before.st_size);
		compiled = fixture_read(counter, bytes, sizeof(bytes));
		bindings = batch_bindings;
		snapshots = batch_snapshots;

		entry.generation = batch_response.base_generation = 1;
		batch_response.token = 12;
		batch_response.revision = 3;
		batch_response.records[0] = (struct kd_learning_record){3, 1,
			0xffffffff8100c000UL, 0, KD_LEARNING_CALL, 0};
		batch_bind_error = 0;
		assert(!learning_step(&cfg, &entry) && !learning.active);
		assert(batch_snapshots == snapshots + 1 && batch_bindings == bindings);
		assert(batch_cancels == cancels + 2 && !learning_generations[7].expected);
		assert(fixture_read(counter, bytes, sizeof(bytes)) == compiled);
		assert(provenance_path(binary_path, sizeof(binary_path), "%s/batch-12", storage));
		assert(access(binary_path, F_OK) == -1 && errno == ENOENT);
		assert(fixture_read(path, bytes, sizeof(bytes)) == strlen("0xffffffff8100a000\n"));
		assert(!memcmp(bytes, "0xffffffff8100a000\n", strlen("0xffffffff8100a000\n")));
		assert(!fstat(original_fd, &after) && after.st_size == before.st_size);
		assert(entry.generation == 1 && entry.status_code == KD_EXE_CALL_MISS);
		assert(provenance_path(binary_path, sizeof(binary_path), "%s/asm/jit.bin", learning.directory));
		assert(!access(binary_path, F_OK));

		/* A matching receipt also cannot justify a larger unexplained jump. */
		entry.generation = batch_response.base_generation = 3;
		batch_response.token = 13;
		batch_response.records[0].admitted_generation = 3;
		assert(!learning_step(&cfg, &entry) && !learning.active);
		assert(batch_bindings == bindings && batch_cancels == cancels + 3);
		assert(fixture_read(counter, bytes, sizeof(bytes)) == compiled);
		assert(!learning_generations[7].expected);

		/* A restarted daemon has no local generation knowledge. Its new
		 * session and descriptor cannot bootstrap this already published root. */
		assert(!close(original_fd));
		sys_fd = open("restarted-transport", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
		assert(sys_fd >= 3);
		memset(learning_generations, 0, sizeof(learning_generations));
		strcpy(learning.scope_tag, "session-fixture-restarted");
		snprintf(learning.session, sizeof(learning.session), "{\"provider_session\":\"fixture-restarted\"}\n");
		batch_response.token = 14;
		assert(!learning_step(&cfg, &entry) && !learning.active);
		assert(!learning_generations[7].initialized);
		assert(batch_bindings == bindings && batch_cancels == cancels + 4);
		assert(fixture_read(counter, bytes, sizeof(bytes)) == compiled);
		assert(!fstat(sys_fd, &after) && !after.st_size);
		assert(!close(other_fd));
	}
	assert(!close(sys_fd));
	sys_fd = -1;
	learning.enabled = batch_ioctl_active = false;
	assert(!unsetenv("KD_BATCH_TEST_COUNTER"));
	assert(!fchdir(original_dir) && !close(original_dir));
	fixture_remove(root);
	puts("[PASS] finite batch union, frozen retry, scope and failure decisions");
}

int main(void)
{
	char path[] = "/tmp/kdlock-daemon-policy.XXXXXX";
	struct kd_exe_info exe = { .pid = 0, .RIP = 0x1234, .lock_kind = KD_EXE_LOCK_MUTEX };
	struct kd_recv_pkt packet;
	int result = -1;
	int fd;

	assert(compile_result(0) == 0);
	assert(compile_result(2 << 8) == TRANSLATOR_NATIVE_ONLY);
	assert(compile_result(1 << 8) == -1);
	assert(compile_result(127 << 8) == -1);
	assert(compile_result(SIGTERM) == -1);
	assert(compile_result(-1) == -1);
	test_compiler_launch();
	test_metrics_contract();
	test_chunk_session();
	test_learning_batch_attempt();
	assert(!remember_cmd("rejected fixture", 1, TRANSLATOR_NATIVE_ONLY));
	assert(cmd_seen("rejected fixture", 1, &result));
	assert(result == TRANSLATOR_NATIVE_ONLY);
	assert(!remember_cmd("successful fixture", 1, 0));
	assert(cmd_seen("successful fixture", 1, &result));
	assert(result == 0);
	assert(!cmd_seen("failed fixture", 1, &result));
	assert(!cmd_seen("successful fixture", 2, &result));

	fd = mkstemp(path);
	assert(fd >= 0);
	sys_fd = fd;
	assert(!unlink(path));
	assert(!write_native_only(&exe));
	assert(lseek(fd, 0, SEEK_SET) == 0);
	assert(read(fd, &packet, sizeof(packet)) == sizeof(packet));
	assert(packet.status_code == KD_EXE_NATIVE_ONLY);
	assert(packet.pid == exe.pid && packet.RIP == exe.RIP);
	assert(packet.offset == 0);
	assert(read(fd, &packet, sizeof(packet)) == 0);
	assert(sizeof(struct kd_exe_info) == 64);
	assert(offsetof(struct kd_exe_info, lock_kind) == 12);
	assert(offsetof(struct kd_exe_info, RIP) == 16);
	assert(offsetof(struct kd_exe_info, code_block) == 24);
	assert(offsetof(struct kd_exe_info, jump_from) == 32);
	assert(offsetof(struct kd_exe_info, tgt_addr) == 40);
	assert(sizeof(struct kd_recv_pkt) == 64);
	close(fd);
	sys_fd = -1;
	assert(write_native_only(&exe) == -1);
	for (int i = 0; i < cmd_cnt; i++)
		free(cmd_hist[i]);
	puts("[PASS] test_daemon_policy");
	return 0;
}
