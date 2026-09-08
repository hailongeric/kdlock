/* Test the production daemon's result cache and header-only wire encoding. */
#include <assert.h>
#include <signal.h>
#include <stddef.h>

#define main kd_daemon_main
#include "../../daemon/daemon.c"
#undef main

static void test_compiler_launch(void)
{
	char root[] = "/tmp/kdlock-compiler-launch.XXXXXX";
	struct kd_exe_info exe = { .pid = 0, .tgid = 42, .RIP = 0x1234 };
	const char *kinds[] = { "unknown", "spin", "mutex" };
	struct daemon_config cfg = { .mode = MODE_V1 };
	int original_dir = open(".", O_RDONLY | O_DIRECTORY);
	FILE *script;

	assert(original_dir >= 0);
	assert(mkdtemp(root));
	assert(!chdir(root));
	assert(!mkdir("daemon", 0700));
	assert(!mkdir("disassem", 0700));
	assert(!chdir("daemon"));

	for (int mode = MODE_V1; mode <= MODE_V2; mode++) {
		cfg.mode = mode;
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
					       "import sys\nassert sys.argv[1:] == ['0', '0x1234', '%s']\nraise SystemExit(%d)\n",
					       kinds[kind], code) > 0);
				assert(!fclose(script));
				assert(compile_entry(&cfg, &exe) ==
				       (code == 1 ? -1 : code));
			}
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
}

int main(void)
{
	char path[] = "/tmp/kdlock-daemon-policy.XXXXXX";
	struct kd_exe_info exe = { .pid = 0, .RIP = 0x1234 };
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
	assert(!remember_cmd("rejected fixture", TRANSLATOR_NATIVE_ONLY));
	assert(cmd_seen("rejected fixture", &result));
	assert(result == TRANSLATOR_NATIVE_ONLY);
	assert(!remember_cmd("successful fixture", 0));
	assert(cmd_seen("successful fixture", &result));
	assert(result == 0);
	assert(!cmd_seen("failed fixture", &result));

	fd = mkstemp(path);
	assert(fd >= 0);
	sys_path = path;
	assert(!write_native_only(&exe));
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
	assert(sizeof(struct kd_recv_pkt) == 24);
	close(fd);
	unlink(path);
	for (int i = 0; i < cmd_cnt; i++)
		free(cmd_hist[i]);
	puts("[PASS] test_daemon_policy");
	return 0;
}
