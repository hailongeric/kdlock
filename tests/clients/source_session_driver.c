/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise production fork/exec and descriptor inheritance against kd_dev.
 * The child probes the lease, not code generation; the enclosing complex
 * workload supplies independent returned-JIT and native-owner evidence. */
#define main kd_daemon_main
#include "../../daemon/daemon.c"
#undef main

int main(void)
{
	struct daemon_config cfg = { .mode = MODE_V2 };
	struct kd_exe_info exe = { .pid = 0, .tgid = 42, .RIP = 0x1234 };
	int result;

	sys_fd = open("/dev/kd_dev", O_RDWR | O_CLOEXEC);
	if (sys_fd < 0)
		return 1;
	result = compile_entry(&cfg, &exe);
	close(sys_fd);
	return result != 0;
}
