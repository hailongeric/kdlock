/* Test production result caching, wire encoding and opt-in child accounting. */
#include <assert.h>
#include <errno.h>
#include <signal.h>
#include <stddef.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>

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
#include "../../../daemon/daemon.c"
#undef main
#undef clock_gettime
#undef wait4

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
	assert(!write_sys(&cfg, &exe));
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
	assert(write_sys(&cfg, &exe) == -1);
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
